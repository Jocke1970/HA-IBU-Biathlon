#!/usr/bin/env python3
"""CCResult checkpoint leaderboard prototype, offline and class-isolated.

Modes:
  reconstructed - rebuild passing order from merged final athlete history.
                  This is NOT a faithful observed live feed.
  observed      - replay only REST snapshot rows received by the requested
                  capture time; do not invent earlier knowledge.

Rank at each station is recomputed from comparable recorded elapsed times.
No overall race rank is asserted for athletes at different stations.
No requests, authentication or Home Assistant access.
"""
import argparse
from collections import defaultdict
from datetime import datetime
import json
from pathlib import Path
from zoneinfo import ZoneInfo

LOCAL = ZoneInfo("Europe/Stockholm")
MAX_RUNTIME = 86_400_000
# Status semantics confirmed against Idre 2026-11-15 provider display.
RESULT_STATUSES = {101: "DNF", 102: "DNS"}


def datetime_local(value, utc_expected=False):
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo:
            return parsed.astimezone(LOCAL).replace(tzinfo=None)
        if utc_expected:
            return None  # captured_utc without timezone is untrusted
        return parsed
    except ValueError:
        return None


def valid_ms(value):
    return type(value) in (int, float) and 0 < value < MAX_RUNTIME


def identity(athlete, race, class_id):
    return {
        "race_id": str(race), "class_id": str(class_id),
        "athlete_id": str(athlete.get("AthleteID")),
        "bib": athlete.get("Startno"),
        "name": (athlete.get("Athlete") or {}).get("FormatedName"),
        "nation": (athlete.get("Athlete") or {}).get("Nation"),
        "result_status": RESULT_STATUSES.get(athlete.get("Status")),
        "source_status_code": athlete.get("Status"),
    }


def from_rest(paths, at):
    """Return all *known as of at* station readings, including overwritten copies."""
    people = {}
    readings = []
    observed_snapshots = 0
    skipped_future = 0
    invalid_rows = 0
    for path in paths:
        with Path(path).open(encoding="utf-8") as stream:
            for line_num, line in enumerate(stream, 1):
                if not line.strip():
                    continue
                try:
                    frame = json.loads(line)
                except ValueError as exc:
                    raise ValueError(f"{path}:{line_num}: invalid JSON") from exc
                received = datetime_local(frame.get("captured_utc"), utc_expected=True)
                if received is None:
                    invalid_rows += 1
                    continue
                if received > at:
                    skipped_future += 1
                    continue
                if frame.get("endpoint") not in ("startlist", "results"):
                    continue
                observed_snapshots += 1
                race = frame.get("race_id")
                cls = frame.get("class_id")
                payload = frame.get("payload")
                rows = payload.get("Data", []) if isinstance(payload, dict) else []
                if not isinstance(rows, list):
                    invalid_rows += 1
                    continue
                for row in rows:
                    if not isinstance(row, dict) or not row.get("AthleteID"):
                        continue
                    cls_row = row.get("ClassID") or cls
                    if not cls_row or not race:
                        invalid_rows += 1
                        continue
                    person = identity(row, race, cls_row)
                    key = (person["race_id"], person["class_id"], person["athlete_id"])
                    if key not in people:
                        people[key] = person
                    else:
                        for field in ("bib", "name", "nation"):
                            if people[key][field] is None:
                                people[key][field] = person[field]
                        if person["result_status"]:
                            people[key]["result_status"] = person["result_status"]
                            people[key]["source_status_code"] = person["source_status_code"]
                    if frame.get("endpoint") != "results":
                        continue
                    timing = row.get("Time")
                    if not isinstance(timing, dict) or not valid_ms(timing.get("RunTimeMS")):
                        invalid_rows += 1
                        continue
                    station = timing.get("IntermediateID")
                    if not station:
                        invalid_rows += 1
                        continue
                    readings.append({
                        "key": key, "station": str(station),
                        "ipos": str(frame.get("ipos") or ""),
                        "runtime_ms": int(timing["RunTimeMS"]),
                        "pass_time": datetime_local(timing.get("PassTime")),
                        "known_at": received,
                        "source": "observed_rest_response",
                    })
    return people, readings, {
        "observed_snapshots": observed_snapshots, "skipped_future_snapshots": skipped_future,
        "invalid_rows_or_snapshots": invalid_rows
    }


def from_merged(path, at):
    people = {}
    readings = []
    source = json.loads(Path(path).read_text(encoding="utf-8"))
    for a in source:
        key = (str(a.get("race_id")), str(a.get("class_id")), str(a["athlete_id"]))
        people[key] = {
            "race_id": key[0], "class_id": key[1], "athlete_id": key[2],
            "bib": a.get("bib"), "name": a.get("name"), "nation": a.get("nation"),
            "result_status": a.get("result_status"),
            "source_status_code": a.get("source_status_code"),
            "result_status_observed_utc": a.get("result_status_observed_utc")
        }
        for cp in a.get("checkpoints", []):
            elapsed = cp.get("runtime_ms")
            stamp = datetime_local(cp.get("pass_time"))
            if stamp is None or stamp > at or not valid_ms(elapsed) or not cp.get("intermediate_id"):
                continue
            readings.append({
                "key": key, "station": str(cp["intermediate_id"]),
                "ipos": str(cp.get("ipos") or ""),
                "runtime_ms": int(elapsed), "pass_time": stamp,
                "known_at": stamp, "source": "retrospective_final_result",
            })
    return people, readings, {"retrospective_readings": len(readings)}


def checkpoint_state(people, readings, at, mode, finish_stations=()):
    """Build station-local rankings; latest physical pass is separate from rank."""
    finish_stations = set(str(s) for s in finish_stations)
    observations = {}
    for row in readings:
        if row["known_at"] > at or (row["pass_time"] is not None and row["pass_time"] > at):
            # A response may contain a pass timestamp later than the replay
            # clock. Never let that observation affect either ranking or UI.
            continue
        key = (*row["key"], row["station"])
        old = observations.get(key)
        if old is None or row["known_at"] >= old["known_at"]:
            observations[key] = row

    groups = defaultdict(list)
    latest_by_athlete = defaultdict(list)
    for row in observations.values():
        groups[(*row["key"][:2], row["station"])].append(row)
        latest_by_athlete[row["key"]].append(row)
    station_ranks = {}
    station_leaders = {}
    for station_key, candidates in groups.items():
        candidates.sort(key=lambda row: (row["runtime_ms"], row["key"][-1]))
        leader = candidates[0]["runtime_ms"]
        station_leaders[station_key] = leader
        for index, row in enumerate(candidates):
            # Competition rank: equal times are tied at the same rank.
            rank = 1 + sum(other["runtime_ms"] < row["runtime_ms"] for other in candidates)
            station_ranks[(*row["key"], row["station"])] = {
                "position": rank, "diff_ms": row["runtime_ms"] - leader,
                "observed_competitors": len(candidates),
            }
    classes = defaultdict(list)
    for key, person in people.items():
        readings_for_person = latest_by_athlete.get(key, [])
        # Prefer physical pass time, not latest downloaded checkpoint.
        # Some REST snapshots may contain future pass timestamps relative
        # to their receipt: flag them and do not use them to assert progress.
        readings_for_person = [r for r in readings_for_person
                               if r["pass_time"] is None or r["pass_time"] <= at]
        readings_for_person.sort(
            key=lambda x: (x["pass_time"] is not None,
                           x["pass_time"] or x["known_at"], x["runtime_ms"]))
        latest = readings_for_person[-1] if readings_for_person else None
        point = None
        if latest:
            detail = station_ranks[(*key, latest["station"])]
            point = {
                "station_id": latest["station"], "ipos": latest["ipos"],
                "elapsed_ms": latest["runtime_ms"],
                "passed_at": latest["pass_time"].isoformat() if latest["pass_time"] else None,
                "checkpoint_position": detail["position"],
                "checkpoint_diff_ms": detail["diff_ms"],
                "comparable_athletes": detail["observed_competitors"],
                "position_scope": "same_class_and_checkpoint_only",
            }
        explicit_status = person.get("result_status")
        if mode == "reconstructed" and explicit_status:
            # The merged file is a final-state artifact. A terminal status
            # is not known during replay until a source response was received.
            status_received = datetime_local(person.get("result_status_observed_utc"), utc_expected=True)
            if status_received is None or status_received > at:
                explicit_status = None
        display_person = dict(person)
        display_person["result_status"] = explicit_status
        if explicit_status is None:
            display_person["source_status_code"] = None
        classes[key[1]].append({
            **display_person,
            "status": explicit_status if explicit_status else (
                "finished" if latest and latest["station"] in finish_stations else (
                    "passed_checkpoint" if latest else "no_verified_passing")),
            "last_checkpoint": point,
            "overall_position": None,
        })
    for cls in classes:
        # Neutral start-number sorting: checkpoint positions from different
        # stations must never appear as a single overall leaderboard.
        classes[cls].sort(key=lambda row: (
            row["bib"] if type(row["bib"]) is int else 999999,
            row["athlete_id"]))
    station_groups = {}
    for (race, cls, station), candidates in sorted(groups.items()):
        ranked = sorted(candidates, key=lambda x: (x["runtime_ms"], x["key"][-1]))
        station_groups[f"{race}:{cls}:{station}"] = {
            "race_id": race, "class_id": cls, "station_id": station,
            "comparable_athletes": len(ranked),
            "leader_elapsed_ms": ranked[0]["runtime_ms"],
            "results": [{
                "athlete_id": row["key"][2],
                "bib": people[row["key"]].get("bib"),
                "position": station_ranks[(*row["key"], station)]["position"],
                "elapsed_ms": row["runtime_ms"],
                "diff_ms": station_ranks[(*row["key"], station)]["diff_ms"]
            } for row in ranked]
        }
    return {
        "at": at.isoformat(), "mode": mode,
        "ranking_semantics": "checkpoint_local_no_overall_race_position",
        "classes": dict(sorted(classes.items())),
        "athlete_list_sort": "bib_ascending_not_overall_position",
        "checkpoint_groups": station_groups,
        "stations_observed": len(groups),
        "station_leader_ms": {
            f"{race}:{cls}:{station}": ms
            for (race, cls, station), ms in station_leaders.items()
        }
    }


def build_snapshot(mode, at, rest_paths=None, merged_path=None, finish_stations=()):
    if at.tzinfo is not None:
        raise ValueError("Provide naive Europe/Stockholm local clock for --at")
    if mode == "observed":
        if not rest_paths:
            raise ValueError("observed mode requires --rest")
        people, readings, audit = from_rest(rest_paths, at)
    elif mode == "reconstructed":
        if not merged_path:
            raise ValueError("reconstructed mode requires --merged")
        people, readings, audit = from_merged(merged_path, at)
    else:
        raise ValueError("Unknown mode")
    output = checkpoint_state(people, readings, at, mode, finish_stations)
    output["audit"] = audit
    output["limitations"] = (
        "Only station-local rankings are comparable. No inferred global race position. "
        "Observed mode uses receipt time; reconstructed mode uses final-result pass time "
        "and is not proof of what a live observer saw at that time. "
        "Missing official station names are shown as IDs."
    )
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", required=True, choices=("observed", "reconstructed"))
    parser.add_argument("--at", required=True, help="Race-local YYYY-MM-DDTHH:MM:SS")
    parser.add_argument("--rest", nargs="*", default=[])
    parser.add_argument("--merged")
    parser.add_argument("--finish-station", action="append", default=[])
    parser.add_argument("--out", default="captures/leaderboard_snapshot.json")
    args = parser.parse_args()
    stamp = datetime_local(args.at)
    if stamp is None:
        parser.error("--at must be valid ISO datetime")
    result = build_snapshot(args.mode, stamp, args.rest, args.merged, args.finish_station)
    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "at": result["at"], "mode": result["mode"],
        "athletes_by_class": {cls: len(rows) for cls, rows in result["classes"].items()},
        "athletes_with_checkpoints": {
            cls: sum(row["last_checkpoint"] is not None for row in rows)
            for cls, rows in result["classes"].items()
        },
        "station_count": result["stations_observed"],
        "audit": result["audit"],
        "preview": {
            cls: [row for row in rows if row["last_checkpoint"]][:3]
            for cls, rows in result["classes"].items()
        }
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
