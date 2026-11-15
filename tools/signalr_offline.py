#!/usr/bin/env python3
"""Offline SignalR MessagePack hex decoder for CCResult biathlon observations.

One hex-encoded WebSocket binary message per line in input file.
No network access, tokens, cookies or credentials are used.
Install: python -m pip install msgpack
Run: python tools/signalr_offline.py frames.txt
"""
import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

try:
    import msgpack
except ImportError:
    sys.exit("Missing dependency: python -m pip install msgpack")


def frames(data):
    pos = 0
    while pos < len(data):
        length = 0
        for i in range(5):
            if pos >= len(data):
                raise ValueError("Incomplete SignalR length prefix")
            byte = data[pos]
            pos += 1
            length |= (byte & 127) << (7 * i)
            if byte < 128:
                break
        else:
            raise ValueError("SignalR length prefix too long")
        if not length or pos + length > len(data):
            raise ValueError("Incomplete SignalR payload")
        yield data[pos:pos + length]
        pos += length


def decode(raw):
    frame = msgpack.unpackb(raw, raw=False, strict_map_key=False)
    if not isinstance(frame, list) or len(frame) < 5:
        return {"kind": "other"}
    if frame[0] != 1 or frame[3] != "ReceiveMessage":
        return {"kind": "other", "type": frame[0]}
    args = frame[4]
    if not isinstance(args, list) or not args:
        return {"kind": "empty"}
    value = args[0]
    if isinstance(value, str):
        value = json.loads(value)
    return {"kind": "receive", "payload": value}


def process(messages):
    groups = defaultdict(list)
    events = []
    for i, item in enumerate(messages, start=1):
        if item.get("kind") != "receive":
            continue
        payload = item.get("payload", {})
        if not isinstance(payload, dict) or payload.get("Source") != 4:
            continue
        shoot = payload.get("Object")
        if not isinstance(shoot, dict):
            continue
        athlete, nr = shoot.get("AthleteID"), shoot.get("ShootNr")
        if not athlete or not isinstance(nr, int):
            continue
        key = (str(athlete), nr)
        groups[key].append((i, shoot))
        for n in range(1, 9):
            target = shoot.get(f"Target{n}")
            if isinstance(target, dict) and target.get("ShootTime"):
                events.append({
                    "frame": i, "athlete_id": athlete, "start_no": shoot.get("StartNo"),
                    "shoot_nr": nr, "shot_nr": target.get("ShootNr", n),
                    "hit": target.get("Hit"), "shot_time": target.get("ShootTime"),
                    "shoot_runtime": target.get("ShootRunTime"),
                    "sum_shooted": shoot.get("SumShooted"), "missed": shoot.get("Missed"),
                    "prone": shoot.get("Prone"), "lane": shoot.get("Lane"),
                    "is_open": shoot.get("IsOpen")
                })
    summary = []
    for (athlete, nr), observations in sorted(groups.items()):
        latest = observations[-1][1]
        counts = []
        shots = {}
        for index, obs in observations:
            count = obs.get("SumShooted")
            if not counts or count != counts[-1]["count"]:
                counts.append({"frame": index, "count": count})
            for n in range(1, 9):
                t = obs.get(f"Target{n}")
                if isinstance(t, dict) and t.get("ShootTime"):
                    shots[n] = t
        summary.append({
            "athlete_id": athlete, "shoot_nr": nr, "start_no": latest.get("StartNo"),
            "prone": latest.get("Prone"), "lane": latest.get("Lane"),
            "sum_shooted": latest.get("SumShooted"), "missed": latest.get("Missed"),
            "is_open": latest.get("IsOpen"),
            "pattern": "".join("o" if shots[n].get("Hit") else "x" for n in sorted(shots)),
            "observed_counts": counts
        })
    return summary, events


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("input", help="File containing one copied WebSocket message hex string per line")
    p.add_argument("--out", default="captures/decoded", help="Output directory")
    args = p.parse_args()
    output = Path(args.out)
    output.mkdir(parents=True, exist_ok=True)
    messages = []
    errors = 0
    try:
        lines = Path(args.input).read_text(encoding="utf-8-sig").splitlines()
    except OSError as exc:
        p.error(str(exc))
    for number, line in enumerate(lines, start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        compact = re.sub(r"\s+", "", line)
        try:
            if len(compact) % 2 or not re.fullmatch(r"[a-fA-F0-9]+", compact):
                raise ValueError("Not a valid hex string")
            for raw in frames(bytes.fromhex(compact)):
                messages.append(decode(raw))
        except (ValueError, TypeError, msgpack.exceptions.UnpackException) as exc:
            errors += 1
            print(f"Line {number}: {exc}", file=sys.stderr)
    summary, events = process(messages)
    with (output / "messages.jsonl").open("w", encoding="utf-8") as f:
        for message in messages:
            f.write(json.dumps(message, ensure_ascii=False) + "\n")
    (output / "shooting_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    columns = ["frame", "athlete_id", "start_no", "shoot_nr", "shot_nr", "hit",
               "shot_time", "shoot_runtime", "sum_shooted", "missed", "prone",
               "lane", "is_open"]
    with (output / "shots.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(events)
    print(f"Decoded {len(messages)} messages; {errors} errors; {len(summary)} shooting groups")
    for s in summary:
        counts = ",".join(str(x["count"]) for x in s["observed_counts"])
        print(f"Bib {s['start_no']} | {s['athlete_id']} shoot {s['shoot_nr']} | "
              f"shots={s['sum_shooted']} missed={s['missed']} pattern={s['pattern']} "
              f"observed counts={counts}")
    print(f"Saved to {output}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
