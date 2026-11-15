#!/usr/bin/env python3
"""Experimental offline replay of merged CCResult athlete histories.

Uses final snapshots, NOT incremental live shot events. Consequently shooting
progress cannot be replayed shot-by-shot. PassTime is source-local, and
shooting offset must be explicit. Rankings are checkpoint-local only.
"""
import argparse
from datetime import datetime, timedelta
import json
from pathlib import Path


def parse_time(value):
    try:
        return datetime.fromisoformat(value) if value else None
    except (TypeError, ValueError):
        return None


def chronological_events(athletes, shooting_offset_hours=1):
    events = []
    for a in athletes:
        key = (str(a.get("race_id")), str(a["athlete_id"]))
        start = parse_time(a.get("start_time"))
        if start:
            events.append({"at": start, "kind": "start", "key": key})
        for cp in a.get("checkpoints", []):
            at = parse_time(cp.get("pass_time"))
            inferred = False
            if at is None and start and isinstance(cp.get("runtime_ms"), (int, float)):
                at = start + timedelta(milliseconds=cp["runtime_ms"])
                inferred = True
            if at and cp.get("intermediate_id"):
                events.append({"at": at, "kind": "checkpoint", "key": key,
                               "station_id": cp["intermediate_id"],
                               "ipos": str(cp.get("ipos")),
                               "runtime_ms": cp.get("runtime_ms"),
                               "rank": cp.get("rank_at_checkpoint"),
                               "inferred": inferred})
        for s in a.get("shootings", []):
            nr = s.get("shoot_nr")
            if not isinstance(nr, int) or nr < 1:
                continue
            arrival = parse_time(s.get("in_time"))
            departure = parse_time(s.get("out_time"))
            if arrival:
                arrival += timedelta(hours=shooting_offset_hours)
            if departure:
                departure += timedelta(hours=shooting_offset_hours)
            if arrival:
                events.append({"at": arrival, "kind": "shoot_in", "key": key,
                               "shoot_nr": nr, "lane": s.get("lane"),
                               "out_at": departure, "range_seconds": s.get("range_seconds"),
                               "result": s.get("shoot_string"), "missed": s.get("missed")})
            if departure and arrival and departure >= arrival:
                events.append({"at": departure, "kind": "shoot_out", "key": key, "shoot_nr": nr})
    priority = {"start": 0, "checkpoint": 1, "shoot_in": 2, "shoot_out": 3}
    events.sort(key=lambda e: (e["at"], priority[e["kind"]], e["key"]))
    return events


def replay(athletes, at, shooting_offset_hours=1, hold_seconds=15, finish_stations=None):
    if at.tzinfo is not None:
        raise ValueError("Replay time must be naive local race time")
    if hold_seconds < 0:
        raise ValueError("hold_seconds must be >= 0")
    finish_stations = set(finish_stations or [])
    by_key = {}
    for a in athletes:
        key = (str(a.get("race_id")), str(a["athlete_id"]))
        by_key[key] = {"race_id": key[0], "athlete_id": key[1],
                       "class_id": a.get("class_id"), "bib": a.get("bib"),
                       "name": a.get("name"), "nation": a.get("nation"),
                       "status": "not_started", "last_checkpoint": None,
                       "checkpoint_rank": None, "latest_elapsed_ms": None,
                       "checkpoint_history": [], "shootings": []}
    shooting_entries = {}
    for event in chronological_events(athletes, shooting_offset_hours):
        if event["at"] > at:
            break
        person = by_key[event["key"]]
        kind = event["kind"]
        if kind == "start":
            person["status"] = "on_course"
        elif kind == "checkpoint":
            cp = {"station_id": event["station_id"], "ipos": event["ipos"],
                  "runtime_ms": event["runtime_ms"], "checkpoint_rank": event["rank"],
                  "pass_time": event["at"].isoformat(), "inferred_pass_time": event["inferred"]}
            person["checkpoint_history"].append(cp)
            person["last_checkpoint"] = cp["station_id"]
            person["checkpoint_rank"] = cp["checkpoint_rank"]
            person["latest_elapsed_ms"] = cp["runtime_ms"]
            if cp["station_id"] in finish_stations:
                person["status"] = "finished"
            elif person["status"] != "finished":
                person["status"] = "on_course"
        elif kind == "shoot_in":
            shooting_entries[(*event["key"], event["shoot_nr"])] = event
            person["status"] = "shooting"
            person["shootings"].append({"shoot_nr": event["shoot_nr"],
                                        "lane": event["lane"],
                                        "in_time": event["at"].isoformat(),
                                        "out_time": None, "final_result_available": False})
        elif kind == "shoot_out":
            initial = shooting_entries.get((*event["key"], event["shoot_nr"]))
            if initial:
                for item in person["shootings"]:
                    if item["shoot_nr"] == event["shoot_nr"] and item["out_time"] is None:
                        item.update({"out_time": event["at"].isoformat(),
                                     "final_result_available": True,
                                     "shoot_string": initial["result"],
                                     "missed": initial["missed"],
                                     "range_seconds": initial["range_seconds"]})
                        break
                if person["status"] != "finished":
                    person["status"] = "on_course"
    range_rows = []
    for key, source in shooting_entries.items():
        departure = source["out_at"]
        if departure is None:
            state = "active_unconfirmed"
        elif source["at"] <= at < departure:
            state = "active"
        elif departure <= at < departure + timedelta(seconds=hold_seconds):
            state = "recently_finished"
        else:
            continue
        person = by_key[source["key"]]
        elapsed_until = min(at, departure) if departure else at
        range_rows.append({
            "race_id": person["race_id"], "athlete_id": person["athlete_id"],
            "class_id": person["class_id"], "bib": person["bib"],
            "name": person["name"], "nation": person["nation"],
            "shoot_nr": source["shoot_nr"], "lane": source["lane"],
            "state": state, "in_time": source["at"].isoformat(),
            "out_time": departure.isoformat() if departure else None,
            "elapsed_on_range_seconds": round((elapsed_until - source["at"]).total_seconds(), 3),
            "final_shoot_string": source["result"] if state == "recently_finished" else None,
            "final_missed": source["missed"] if state == "recently_finished" else None,
            "shot_progress_unavailable": state != "recently_finished",
        })
    range_rows.sort(key=lambda row: (row["in_time"], row["bib"] or 999999))
    classes = {}
    for cls in sorted({str(p["class_id"]) for p in by_key.values()}):
        records = [p for p in by_key.values() if str(p["class_id"]) == cls]
        records.sort(key=lambda p: (p["checkpoint_rank"] is None,
                                   p["checkpoint_rank"] or 999999, p["bib"] or 999999))
        classes[cls] = records
    return {
        "at": at.isoformat(), "shooting_offset_hours": shooting_offset_hours,
        "hold_seconds": hold_seconds,
        "ranking_semantics": "checkpoint_local_only_not_overall_live_position",
        "replay_accuracy": "from_final_snapshots_not_live_progressive_shot_events",
        "classes": classes, "shooting_range": range_rows
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--merged", required=True)
    parser.add_argument("--at", required=True, help="Naive race-local ISO datetime")
    parser.add_argument("--out", default="captures/live_state.json")
    parser.add_argument("--shooting-offset-hours", type=int, default=1)
    parser.add_argument("--hold-seconds", type=int, default=15)
    parser.add_argument("--finish-station", action="append", default=[],
                        help="Explicitly verified finish station ID; may repeat")
    args = parser.parse_args()
    timestamp = parse_time(args.at)
    if timestamp is None:
        parser.error("Invalid ISO datetime")
    data = json.loads(Path(args.merged).read_text(encoding="utf-8"))
    result = replay(data, timestamp, args.shooting_offset_hours,
                    args.hold_seconds, args.finish_station)
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"at": result["at"],
                      "classes": {k: len(v) for k, v in result["classes"].items()},
                      "shooting_range_count": len(result["shooting_range"]),
                      "shooting_range_preview": result["shooting_range"][:5]},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
