#!/usr/bin/env python3
"""Replay recorded SignalR messages as actually observed, without future leakage.

Input: original events.jsonl and (optionally) merged athlete_summary.json.
The capture clock is UTC and is explicitly converted to Europe/Stockholm.
The observed source InTime/OutTime is provisionally corrected by the given
hour offset; this offset is NOT assumed to be universal for other providers.
A snapshot cannot show messages captured after --at. No network calls.\nShooting rows persist until confirmed exit or a subsequent athlete takes the lane.
"""
import argparse
from datetime import datetime, timedelta
import json
from pathlib import Path
from zoneinfo import ZoneInfo

LOCAL_ZONE = ZoneInfo("Europe/Stockholm")


def local_capture_time(s):
    if not isinstance(s, str):
        return None
    try:
        stamp = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            return None
        return stamp.astimezone(LOCAL_ZONE).replace(tzinfo=None)
    except ValueError:
        return None


def source_clock(s, offset_hours):
    if not isinstance(s, str) or not s:
        return None
    try:
        stamp = datetime.fromisoformat(s)
        if stamp.tzinfo is not None:
            # Source might eventually supply a true timezone. Respect it.
            return stamp.astimezone(LOCAL_ZONE).replace(tzinfo=None)
        return stamp + timedelta(hours=offset_hours)
    except ValueError:
        return None


def chronological_messages(files):
    stream = []
    for path in files:
        with Path(path).open(encoding="utf-8") as f:
            for line_nr, line in enumerate(f, 1):
                if not line.strip():
                    continue
                try:
                    raw = json.loads(line)
                except ValueError as exc:
                    raise ValueError(f"{path}:{line_nr}: invalid JSON") from exc
                if raw.get("kind") != "shooting":
                    continue
                event_at = local_capture_time(raw.get("captured_utc"))
                nr = raw.get("shoot_nr")
                athlete = raw.get("athlete_id")
                race = raw.get("race_id")
                if event_at and race and athlete and type(nr) is int and nr > 0:
                    stream.append((event_at, len(stream), raw))
    stream.sort(key=lambda row: (row[0], row[1]))
    return stream


def replay_messages(files, at, metadata=None, offset_hours=1, hold_seconds=15):
    """Return occupied lanes as known at query time (no timed after-display)."""
    if at.tzinfo is not None:
        raise ValueError("Query time must be a naive local race clock")
    if hold_seconds < 0:
        raise ValueError("hold_seconds must be >= 0")
    people = {(str(a.get("race_id")), str(a.get("athlete_id"))): a
              for a in (metadata or [])}
    state = {}
    counts = {}
    anomalies = {}
    consumed = 0
    for received, _, raw in chronological_messages(files):
        if received > at:
            break
        consumed += 1
        key = (str(raw["race_id"]), str(raw["athlete_id"]), raw["shoot_nr"])
        number = raw.get("sum_shooted")
        previous = state.get(key)
        counts.setdefault(key, set())
        if type(number) is int:
            counts[key].add(number)
        if previous is not None and number == 0 and (previous.get("sum_shooted") or 0) > 0:
            anomalies.setdefault(key, set()).add("late_zero_reset_ignored")
            continue
        # A late correction may shift both source wall-clock times backwards
        # exactly one hour while retaining the same completed five-shot result.
        # Keep the newly corrected shot data but preserve trustworthy clock.
        updated = dict(raw)
        if previous and number == previous.get("sum_shooted") == 5:
            unchanged = (raw.get("shoot_string") == previous.get("shoot_string")
                         and raw.get("missed") == previous.get("missed")
                         and raw.get("lane") == previous.get("lane"))
            a = source_clock(previous.get("in_time"), offset_hours)
            b = source_clock(raw.get("in_time"), offset_hours)
            c = source_clock(previous.get("out_time"), offset_hours)
            d = source_clock(raw.get("out_time"), offset_hours)
            if unchanged and all(x is not None for x in (a, b, c, d)):
                if abs((b-a).total_seconds()+3600) < 0.02 and abs((d-c).total_seconds()+3600) < 0.02:
                    updated["in_time"] = previous["in_time"]
                    updated["out_time"] = previous["out_time"]
                    anomalies.setdefault(key, set()).add("late_hour_shift_corrected")
        state[key] = updated

    rows = []
    for key, raw in state.items():
        start = source_clock(raw.get("in_time"), offset_hours)
        end = source_clock(raw.get("out_time"), offset_hours)
        if start is None or start > at:
            continue
        # Keep a lane until its athlete's confirmed departure OR the next
        # observed athlete takes that same lane. No arbitrary hold timer.
        if end is not None and end >= start and at >= end:
            continue
        if end is not None and end < start:
            # Discard an impossible end clock rather than claiming departure.
            end = None
        count = raw.get("sum_shooted")
        state_label = ("shooting_complete_exit_unconfirmed"
                       if type(count) is int and count >= 5
                       else "active_unconfirmed")
        athlete = people.get(key[:2], {})
        # Information from final compiled metadata is allowed only for identity,
        # not for timing, finish status, or results.
        count = raw.get("sum_shooted")
        shots = raw.get("shots") or []
        rows.append({
            "race_id": key[0], "athlete_id": key[1],
            "class_id": athlete.get("class_id"), "bib": athlete.get("bib") or raw.get("start_no"),
            "name": athlete.get("name"), "nation": athlete.get("nation"),
            "shoot_nr": key[2], "lane": raw.get("lane"),
            "state": state_label,
            "in_time": start.isoformat(),
            "out_time": end.isoformat() if end and at >= end else None,
            "elapsed_on_range_seconds": round(
                ((end if end and at >= end else at) - start).total_seconds(), 3),
            "shots_count": count,
            "missed": raw.get("missed"),
            "shoot_string": raw.get("shoot_string"),
            "shots_with_timestamps": shots,
            "individual_shot_times_available": bool(shots),
            "observed_shot_counts": sorted(counts[key]),
            "anomalies": sorted(anomalies.get(key, set())),
        })
    # One physical lane can hold only the newest observed occupant.
    # A valid arrival timestamp provides event order; ingestion order breaks
    # ties, without relying on a fabricated departure for the previous athlete.
    occupied = {}
    other = []
    for index, row in enumerate(rows):
        lane = row.get("lane")
        if type(lane) is not int or not 1 <= lane <= 30:
            other.append(row)
            continue
        key = (row["race_id"], lane)
        order = (row["in_time"], index)
        current = occupied.get(key)
        if current is None or order > current[0]:
            occupied[key] = (order, row)
    rows = [item[1] for item in occupied.values()] + other
    rows.sort(key=lambda x: (x["in_time"], x["bib"] or 99999))
    return {
        "at": at.isoformat(), "retention_policy": "until_confirmed_exit_or_lane_reoccupied",
        "source_offset_hours_provisional": offset_hours,
        "processed_shooting_messages": consumed, "shooting_range": rows,
        "replay_accuracy": "observed_message_arrival_not_true_provider_event_time",
        "warning": "Shot states reflect last received update. Exact individual shot timing "
                   "is unavailable unless a captured shot timestamp exists. "
                   "Unconfirmed in/out values must not be mistaken for actual physical presence."
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--events", nargs="+", required=True)
    p.add_argument("--merged", help="Merged metadata; identity fields only")
    p.add_argument("--at", required=True, help="Local race datetime, e.g. 2026-11-15T12:08:30")
    p.add_argument("--out", default="captures/incremental_state.json")
    p.add_argument("--offset-hours", type=int, default=1)
    p.add_argument("--hold-seconds", type=int, default=15)
    args = p.parse_args()
    try:
        at = datetime.fromisoformat(args.at)
    except ValueError:
        p.error("Invalid ISO datetime")
    meta = json.loads(Path(args.merged).read_text(encoding="utf-8")) if args.merged else []
    result = replay_messages(args.events, at, meta, args.offset_hours, args.hold_seconds)
    destination = Path(args.out)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "at": result["at"], "processed_messages": result["processed_shooting_messages"],
        "range_count": len(result["shooting_range"]),
        "range_preview": result["shooting_range"][:5]
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
