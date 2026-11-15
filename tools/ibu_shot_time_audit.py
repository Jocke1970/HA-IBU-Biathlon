#!/usr/bin/env python3
"""Audit already-recorded CCResult shooting payloads for individual shot clocks.

Input formats:
  * browser events.jsonl (compact_record output)
  * offline SignalR messages.jsonl (decoded ReceiveMessage objects)
  * one-or-more saved REST snapshots (only known public shooting field names)

No HTTP calls, browser access or secrets; no output of raw payloads.
Time field presence is not proof of meaning, accuracy or timezone.
"""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path

SHOT_CLOCK_KEYS = ("Shootime", "ShootTime", "ShootRunTime")
SHOT_ROOT_KEYS = ("ShootTime", "Shootime", "ShootRunTime", "InTime", "OutTime")
CANDIDATES = ("shoot", "shot", "target", "range", "firing")


def read_jsonl(paths):
    for path in paths:
        with Path(path).open(encoding="utf-8") as stream:
            for number, line in enumerate(stream, 1):
                if not line.strip():
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"{path}:{number}: invalid JSON") from exc
                yield str(path), number, item


def iter_shooting_objects(record):
    """Yield compact or raw Source4 object; never concatenate across athletes."""
    if not isinstance(record, dict):
        return
    if record.get("kind") == "shooting":
        yield "compact", record
    payload = record.get("payload")
    if not isinstance(payload, dict):
        return
    if payload.get("Source") == 4 and isinstance(payload.get("Object"), dict):
        yield "source4", payload["Object"]


def inspect_object(kind, obj):
    counts = Counter()
    names = Counter()
    times = []
    count = obj.get("sum_shooted") if kind == "compact" else obj.get("SumShooted")
    if type(count) is int and count >= 0:
        counts["updates_with_shot_count"] += 1
        counts[f"reported_count_{count}"] += 1
    if kind == "compact":
        shots = obj.get("shots") or []
        if not isinstance(shots, list):
            shots = []
        for shot in shots:
            if not isinstance(shot, dict):
                continue
            if shot.get("time"):
                counts["shot_timestamps_present"] += 1
                times.append(str(shot["time"]))
            if shot.get("shoot_runtime") is not None:
                counts["shot_runtime_present"] += 1
    else:
        for key, value in obj.items():
            if any(word in key.lower() for word in CANDIDATES):
                names[key] += 1
        for key in SHOT_ROOT_KEYS:
            if obj.get(key) is not None:
                counts[f"root_{key}_present"] += 1
        for i in range(1, 9):
            target = obj.get(f"Target{i}")
            if not isinstance(target, dict):
                continue
            counts["target_objects_present"] += 1
            for key in target:
                names[f"Target*.{key}"] += 1
            # Both spellings are observed in earlier prototype/test samples.
            shot_time = target.get("Shootime") or target.get("ShootTime")
            if shot_time:
                counts["shot_timestamps_present"] += 1
                times.append(str(shot_time))
            if target.get("ShootRunTime") is not None:
                counts["shot_runtime_present"] += 1
    if times:
        counts["updates_with_timestamps"] += 1
        if len(times) >= 2:
            counts["updates_with_multiple_timestamps"] += 1
    return counts, names


def audit(paths):
    counters = Counter()
    field_names = Counter()
    files = Counter()
    individual = defaultdict(lambda: {"updates": 0, "with_timestamps": 0})
    for path, number, record in read_jsonl(paths):
        counters["json_records"] += 1
        for kind, item in iter_shooting_objects(record):
            files[path] += 1
            counters[f"{kind}_shooting_updates"] += 1
            summary, fields = inspect_object(kind, item)
            counters.update(summary)
            field_names.update(fields)
            race = item.get("race_id") if kind == "compact" else item.get("RaceID") or item.get("RaceId")
            athlete = item.get("athlete_id") if kind == "compact" else item.get("AthleteID")
            shoot = item.get("shoot_nr") if kind == "compact" else item.get("ShootNr")
            if race and athlete and shoot is not None:
                key = (str(race), str(athlete), str(shoot))
                individual[key]["updates"] += 1
                if summary["updates_with_timestamps"]:
                    individual[key]["with_timestamps"] += 1
    return {
        "records_read": counters["json_records"],
        "shooting_updates": counters["compact_shooting_updates"] + counters["source4_shooting_updates"],
        "compact_updates": counters["compact_shooting_updates"],
        "raw_source4_updates": counters["source4_shooting_updates"],
        "target_objects_present": counters["target_objects_present"],
        "individual_shot_timestamp_values": counters["shot_timestamps_present"],
        "shot_runtime_values": counters["shot_runtime_present"],
        "updates_with_shot_timestamps": counters["updates_with_timestamps"],
        "updates_with_multiple_shot_timestamps": counters["updates_with_multiple_timestamps"],
        "reported_shot_counts": {
            k.replace("reported_count_", ""): v for k, v in sorted(counters.items())
            if k.startswith("reported_count_")
        },
        "identified_shooting_series": len(individual),
        "series_with_any_shot_timestamp": sum(x["with_timestamps"] > 0 for x in individual.values()),
        "source4_field_names": sorted(k for k in field_names if not k.startswith("Target*.")),
        "target_field_names": sorted(k for k in field_names if k.startswith("Target*.")),
        "files_with_shooting_updates": dict(files),
        "caveat": "Field presence only, never assume timezone, timestamp semantics or ShootRunTime units."
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+", help="Captured JSONL files")
    parser.add_argument("--out", help="Optional JSON report path")
    args = parser.parse_args()
    result = audit(args.files)
    result_json = json.dumps(result, ensure_ascii=False, indent=2)
    print(result_json)
    if args.out:
        target = Path(args.out)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(result_json + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
