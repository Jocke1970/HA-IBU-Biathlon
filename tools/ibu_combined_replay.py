#!/usr/bin/env python3
"""Join offline checkpoint and progressive SignalR shooting snapshots.

The output is a UI-facing data contract, not yet a Home Assistant integration.
The leaderboard and range both obey the requested local replay time.
Only station-local ranks are exposed; no fabricated overall position.
"""
import argparse
from datetime import datetime
import json
from pathlib import Path
from ibu_leaderboard_replay import build_snapshot
from ibu_signalr_replay import replay_messages


def joined_state(at, *, merged, event_files, mode="reconstructed", rest_files=None,
                 offset_hours=1, hold_seconds=15, finish_stations=()):
    board = build_snapshot(mode, at, rest_files, merged, finish_stations)
    meta = json.loads(Path(merged).read_text(encoding="utf-8"))
    range_state = replay_messages(event_files, at, meta, offset_hours, hold_seconds)
    by_athlete = {}
    for shoot in range_state["shooting_range"]:
        key = (str(shoot["race_id"]), str(shoot["class_id"]), str(shoot["athlete_id"]))
        by_athlete.setdefault(key, []).append(shoot)
    classes = {}
    for cls, people in board["classes"].items():
        decorated = []
        for person in people:
            key = (str(person["race_id"]), str(cls), str(person["athlete_id"]))
            range_rows = by_athlete.get(key, [])
            status = person["status"]
            # A range status is only as current as the last observed message.
            # Active_unconfirmed must not be treated as proof of presence.
            confirmed_range = [r for r in range_rows if r["state"] == "active"]
            if confirmed_range and status != "finished":
                status = "shooting_observed"
            decorated.append({
                **person, "display_status": status,
                "shooting_range_rows": len(range_rows),
                "shooting_presence_confirmed": bool(confirmed_range),
            })
        classes[cls] = decorated
    return {
        "at": at.isoformat(),
        "backend_type": "offline_joined_replay",
        "leaderboard_mode": mode,
        "ranking_semantics": board["ranking_semantics"],
        "classes": classes,
        "checkpoint_groups": board["checkpoint_groups"],
        "shooting_range": range_state["shooting_range"],
        "audit": {
            "leaderboard": board["audit"],
            "signalr_processed_messages": range_state["processed_shooting_messages"],
        },
        "data_limits": [
            "Leaderboard reconstructed mode is retrospective, not observed live state.",
            "Shooting events are displayed at capture arrival time.",
            "No overall race position across different course checkpoints.",
            "An unconfirmed range exit does not prove ongoing physical presence.",
            "Finish status requires a separately verified finish station."
        ]
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--merged", required=True)
    p.add_argument("--events", nargs="+", required=True)
    p.add_argument("--rest", nargs="*", default=[])
    p.add_argument("--mode", choices=("observed", "reconstructed"), default="reconstructed")
    p.add_argument("--at", required=True)
    p.add_argument("--offset-hours", type=int, default=1)
    p.add_argument("--hold-seconds", type=int, default=15)
    p.add_argument("--finish-station", action="append", default=[])
    p.add_argument("--out", default="captures/combined_livetiming.json")
    args = p.parse_args()
    try:
        clock = datetime.fromisoformat(args.at)
    except ValueError:
        p.error("--at must be ISO datetime")
    result = joined_state(clock, merged=args.merged, event_files=args.events,
                          rest_files=args.rest, mode=args.mode,
                          offset_hours=args.offset_hours, hold_seconds=args.hold_seconds,
                          finish_stations=args.finish_station)
    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "at": result["at"], "mode": args.mode,
        "classes": {c: len(rows) for c, rows in result["classes"].items()},
        "checkpoint_groups": len(result["checkpoint_groups"]),
        "range_rows": len(result["shooting_range"]),
        "range_preview": result["shooting_range"][:3],
        "audit": result["audit"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
