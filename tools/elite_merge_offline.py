#!/usr/bin/env python3
"""Merge local CCResult REST checkpoint snapshots with SignalR shooting events.

Offline only: does not contact APIs, open browsers, or read credentials.
Input: one or more REST JSONL files and optional SignalR events JSONL.
Output: athlete_summary.json, athlete_summary.csv, quality_report.json.
No assumption that a given ipos has the same meaning for each class.
"""
import argparse
import csv
from datetime import datetime
import json
from collections import Counter, defaultdict
from pathlib import Path
import sys

MAX_VALID_MS = 24 * 60 * 60 * 1000
# Grounded in Idre 2026-11-15 result page and raw REST statuses.
STATUS_LABELS = {101: "DNF", 102: "DNS"}


def read_jsonl(paths):
    for path in paths:
        with Path(path).open(encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, 1):
                if not line.strip():
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"{path}:{line_number}: bad JSON: {exc}") from exc


def milliseconds(value):
    """Return validated elapsed time, or None for missing/invalid sentinel."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not 0 < value < MAX_VALID_MS:
        return None
    return int(value)


def parse_time(value):
    """Parse source's local naive timestamps without inventing UTC offset."""
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def seconds_between(start, end):
    a, b = parse_time(start), parse_time(end)
    if a is None or b is None:
        return None
    if (a.tzinfo is None) != (b.tzinfo is None):
        return None
    value = round((b - a).total_seconds(), 3)
    return value if 0 <= value <= 3600 else None


def merge(rest_paths, events_paths):
    athletes = {}
    checkpoints = {}
    classes = defaultdict(set)
    warnings = Counter()
    stats = Counter()

    def athlete_record(race_id, athlete_id):
        key = (str(race_id), str(athlete_id))
        if key not in athletes:
            athletes[key] = {
                "race_id": key[0], "athlete_id": key[1],
                "bib": None, "name": None, "nation": None, "class_id": None,
                "start_time": None, "result_status": None, "source_status_code": None,
                "checkpoints": [], "shootings": [],
                "quality_flags": []
            }
        return athletes[key]

    for frame in read_jsonl(rest_paths):
        stats["rest_snapshots"] += 1
        endpoint = frame.get("endpoint")
        race_id = frame.get("race_id")
        rows = frame.get("payload", {}).get("Data", [])
        if not isinstance(rows, list) or not race_id:
            warnings["invalid_rest_snapshot"] += 1
            continue
        if endpoint not in ("startlist", "results"):
            continue
        for item in rows:
            if not isinstance(item, dict):
                continue
            athlete_id = item.get("AthleteID")
            if not athlete_id:
                continue
            person = athlete_record(race_id, athlete_id)
            metadata = item.get("Athlete") or {}
            person["name"] = person["name"] or metadata.get("FormatedName")
            person["nation"] = person["nation"] or metadata.get("Nation")
            person["bib"] = person["bib"] or item.get("Startno")
            person["start_time"] = person["start_time"] or item.get("UsedStartTime") or item.get("StartTime")
            class_id = item.get("ClassID") or frame.get("class_id")
            if class_id:
                person["class_id"] = class_id
                classes[str(class_id)].add(str(athlete_id))
            if endpoint != "results":
                continue
            source_status = item.get("Status")
            if source_status in STATUS_LABELS:
                person["source_status_code"] = source_status
                person["result_status"] = STATUS_LABELS[source_status]
            timing = item.get("Time")
            if not isinstance(timing, dict):
                continue
            pos = timing.get("Ipos") or frame.get("ipos")
            intermediate_id = timing.get("IntermediateID")
            ms = milliseconds(timing.get("RunTimeMS"))
            key = (str(race_id), str(athlete_id), str(class_id), str(pos))
            if ms is None:
                warnings["invalid_or_missing_runtime"] += 1
                continue
            checkpoint = {
                "ipos": str(pos), "intermediate_id": intermediate_id,
                "runtime_ms": ms, "pass_time": timing.get("PassTime"),
                "rank_at_checkpoint": timing.get("RankClass"),
                "diff_at_checkpoint": timing.get("DiffClass"),
                "captured_utc": frame.get("captured_utc"),
            }
            old = checkpoints.get(key)
            if old is None or (frame.get("captured_utc") or "") >= (old.get("captured_utc") or ""):
                checkpoints[key] = checkpoint
            stats["valid_checkpoint_rows_seen"] += 1

    for (race_id, athlete_id, _, _), point in checkpoints.items():
        athlete_record(race_id, athlete_id)["checkpoints"].append(point)
    for athlete in athletes.values():
        athlete["checkpoints"].sort(key=lambda p: (p["runtime_ms"], int(p["ipos"]) if p["ipos"].isdigit() else 999))
    shooting_state = {}
    counts = defaultdict(set)
    shooting_resets = set()
    shooting_clock_corrections = set()
    for event in read_jsonl(events_paths):
        stats["signalr_events"] += 1
        if event.get("kind") != "shooting":
            continue
        race_id, athlete_id, shoot_nr = event.get("race_id"), event.get("athlete_id"), event.get("shoot_nr")
        if not race_id or not athlete_id or not isinstance(shoot_nr, int) or shoot_nr < 1:
            warnings["unidentified_shooting_updates"] += 1
            continue
        key = (str(race_id), str(athlete_id), shoot_nr)
        n = event.get("sum_shooted")
        if isinstance(n, int) and not isinstance(n, bool):
            counts[key].add(n)
        previous = shooting_state.get(key)
        # A source may issue a later empty/tombstone-like snapshot with
        # zero shots and zero-duration in/out times. Keep the raw event,
        # but do not overwrite the last meaningful shooting observation.
        is_reset = (
            previous is not None
            and isinstance(n, int) and n == 0
            and isinstance(previous.get("sum_shooted"), int)
            and previous["sum_shooted"] > 0
        )
        if is_reset:
            shooting_resets.add(key)
            warnings["shooting_reset_after_shots"] += 1
        elif previous is None or (event.get("captured_utc") or "", event.get("db_id") or 0) >= (
            previous.get("captured_utc") or "", previous.get("db_id") or 0
        ):
            chosen = event
            # Observed in Idre: a late result correction retained the same
            # five-shot result but rewrote both wall-clock timestamps exactly
            # one hour earlier. Prefer timestamps from the preceding message
            # when it reports the SAME completed series and both fields move
            # by exactly one hour. Do not alter the shot result or raw input.
            if previous is not None and (
                previous.get("sum_shooted") == event.get("sum_shooted") == 5
                and previous.get("shoot_string") == event.get("shoot_string")
                and previous.get("missed") == event.get("missed")
                and previous.get("lane") == event.get("lane")
                and previous.get("out_time") and event.get("out_time")
            ):
                old_in, new_in = parse_time(previous.get("in_time")), parse_time(event.get("in_time"))
                old_out, new_out = parse_time(previous.get("out_time")), parse_time(event.get("out_time"))
                if all((old_in, new_in, old_out, new_out)):
                    in_shift = (new_in - old_in).total_seconds()
                    out_shift = (new_out - old_out).total_seconds()
                    if abs(in_shift + 3600) < 0.02 and abs(out_shift + 3600) < 0.02:
                        chosen = dict(event)
                        chosen["in_time"] = previous["in_time"]
                        chosen["out_time"] = previous["out_time"]
                        shooting_clock_corrections.add(key)
                        warnings["shooting_late_hour_shift"] += 1
            shooting_state[key] = chosen
        stats["identified_shooting_updates"] += 1

    for (race_id, athlete_id, shoot_nr), event in shooting_state.items():
        person = athlete_record(race_id, athlete_id)
        if person["bib"] is None:
            person["bib"] = event.get("start_no")
        in_time, out_time = event.get("in_time"), event.get("out_time")
        shots = event.get("shots") or []
        shot_times = sorted(x["time"] for x in shots if isinstance(x, dict) and x.get("time"))
        if (race_id, athlete_id, shoot_nr) in shooting_resets:
            person["quality_flags"].append(f"shoot_{shoot_nr}_reset_after_shots")
        if (race_id, athlete_id, shoot_nr) in shooting_clock_corrections:
            person["quality_flags"].append(f"shoot_{shoot_nr}_late_hour_shift")
        shooting = {
            "shoot_nr": shoot_nr, "lane": event.get("lane"),
            "prone": event.get("prone"),
            "in_time": in_time, "out_time": out_time,
            "range_seconds": seconds_between(in_time, out_time),
            "shots_count": event.get("sum_shooted"),
            "missed": event.get("missed"),
            "shoot_string": event.get("shoot_string"),
            "is_open": event.get("is_open"),
            "observed_counts": sorted(counts[(race_id, athlete_id, shoot_nr)]),
            "individual_shots": shots,
            "first_to_last_shot_seconds": seconds_between(shot_times[0], shot_times[-1]) if len(shot_times) >= 2 else None,
        }
        if shooting["range_seconds"] is None:
            person["quality_flags"].append(f"shoot_{shoot_nr}_range_duration_missing")
        if not shot_times:
            person["quality_flags"].append(f"shoot_{shoot_nr}_individual_shot_timestamps_missing")
        if shooting["shots_count"] != 5:
            person["quality_flags"].append(f"shoot_{shoot_nr}_not_five_shots")
        person["shootings"].append(shooting)

    for person in athletes.values():
        person["shootings"].sort(key=lambda s: s["shoot_nr"])
        if not person["checkpoints"] and person["result_status"] not in ("DNF", "DNS"):
            person["quality_flags"].append("no_valid_checkpoints")
        if not person["shootings"]:
            person["quality_flags"].append("no_shooting_events")
        if person["class_id"] is None:
            person["quality_flags"].append("class_unknown")

    output = sorted(athletes.values(), key=lambda r: (
        r["class_id"] or "", r["bib"] if isinstance(r["bib"], int) else 99999,
        r["athlete_id"]
    ))
    report = {
        "athletes": len(output),
        "classes": {k: len(v) for k, v in sorted(classes.items())},
        "rest_snapshots": stats["rest_snapshots"],
        "signalr_events": stats["signalr_events"],
        "valid_checkpoint_rows_seen": stats["valid_checkpoint_rows_seen"],
        "distinct_checkpoints": len(checkpoints),
        "identified_shooting_updates": stats["identified_shooting_updates"],
        "unique_shooting_series": len(shooting_state),
        "warnings": dict(warnings),
        "quality_flags": dict(Counter(f for a in output for f in a["quality_flags"])),
        "result_statuses": dict(Counter(a["result_status"] for a in output if a["result_status"])),
        "note": "All checkpoint runtimes are elapsed; pass/in/out times remain source-local timestamps. "
                "RankClass is checkpoint-local, not a live overall ranking. "
                "ShootTime here means first-to-last shot only when individual shot timestamps exist."
    }
    return output, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rest", nargs="+", required=True, help="One or more REST snapshots JSONL files")
    parser.add_argument("--events", nargs="*", default=[], help="SignalR events JSONL files")
    parser.add_argument("--out", default="captures/merged", help="Output directory")
    args = parser.parse_args()
    try:
        athletes, report = merge(args.rest, args.events)
        target = Path(args.out)
        target.mkdir(parents=True, exist_ok=True)
        (target / "athlete_summary.json").write_text(
            json.dumps(athletes, ensure_ascii=False, indent=2), encoding="utf-8")
        (target / "quality_report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        columns = ["race_id", "class_id", "athlete_id", "bib", "name", "nation",
                   "start_time", "result_status", "source_status_code",
                   "checkpoint_count", "latest_checkpoint_ipos",
                   "latest_runtime_ms", "shoot_1_range_s", "shoot_1_missed",
                   "shoot_2_range_s", "shoot_2_missed", "quality_flags"]
        with (target / "athlete_summary.csv").open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=columns)
            writer.writeheader()
            for a in athletes:
                cps = a["checkpoints"]
                shoots = {x["shoot_nr"]: x for x in a["shootings"]}
                writer.writerow({
                    "race_id": a["race_id"], "class_id": a["class_id"],
                    "athlete_id": a["athlete_id"], "bib": a["bib"],
                    "name": a["name"], "nation": a["nation"], "start_time": a["start_time"],
                    "result_status": a["result_status"], "source_status_code": a["source_status_code"],
                    "checkpoint_count": len(cps),
                    "latest_checkpoint_ipos": cps[-1]["ipos"] if cps else "",
                    "latest_runtime_ms": cps[-1]["runtime_ms"] if cps else "",
                    "shoot_1_range_s": shoots.get(1, {}).get("range_seconds"),
                    "shoot_1_missed": shoots.get(1, {}).get("missed"),
                    "shoot_2_range_s": shoots.get(2, {}).get("range_seconds"),
                    "shoot_2_missed": shoots.get(2, {}).get("missed"),
                    "quality_flags": ";".join(a["quality_flags"])
                })
        print(json.dumps(report, ensure_ascii=False, indent=2))
        print(f"Files written to {target}")
    except (OSError, ValueError) as exc:
        print(f"Merge failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
