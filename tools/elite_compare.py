#!/usr/bin/env python3
"""Compare two manually saved EliteTiming JSON responses, entirely offline.

Export the Response body (JSON) from a browser request you are authorized to
view, without request headers, tokens, cookies or private keys.

Usage:
  python tools/elite_compare.py sample1.json sample2.json
"""
import argparse
import json
from pathlib import Path


def load(path):
    with Path(path).open(encoding="utf-8-sig") as f:
        obj = json.load(f)
    if not isinstance(obj, dict) or not isinstance(obj.get("Data"), list):
        raise ValueError(f"{path}: expected JSON object with Data array")
    return obj


def identity(row):
    athlete = row.get("Athlete") or {}
    return str(row.get("AthleteID") or athlete.get("ID") or row.get("ID") or "")


def snapshot(obj):
    output = {}
    for row in obj["Data"]:
        if not isinstance(row, dict):
            continue
        athlete = row.get("Athlete") or {}
        timing = row.get("Time") or {}
        ident = identity(row)
        if not ident:
            continue
        output[ident] = {
            "name": athlete.get("FormatedName") or " ".join(
                str(athlete.get(k) or "") for k in ("FirstName", "LastName")
            ).strip(),
            "bib": row.get("Startno"),
            "rank": timing.get("RankClass"),
            "time_ms": timing.get("RunTimeMS"),
            "behind": timing.get("DiffClass"),
            "pass_time": timing.get("PassTime"),
            "checkpoint": timing.get("IntermediateID"),
            "shooting": athlete.get("ShootString") or athlete.get("Shooting"),
            "status": row.get("Status"),
        }
    return output


def describe(values):
    pairs = [f"{key}={value}" for key, value in values.items() if key != "name"]
    return values.get("name", "(unknown)") + " [" + ", ".join(pairs) + "]"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("earlier", help="Earlier exported JSON response")
    parser.add_argument("later", help="Later exported JSON response")
    parser.add_argument("--limit", type=int, default=30, help="Maximum changed athletes shown")
    args = parser.parse_args()
    a, b = load(args.earlier), load(args.later)
    old, new = snapshot(a), snapshot(b)
    print(f"EARLIER: TotalCount={a.get('TotalCount')} Data={len(a['Data'])} timed={sum(x['time_ms'] is not None for x in old.values())}")
    print(f"LATER:   TotalCount={b.get('TotalCount')} Data={len(b['Data'])} timed={sum(x['time_ms'] is not None for x in new.values())}")
    print(f"IDs: earlier={len(old)}, later={len(new)}")
    added, removed = sorted(new.keys()-old.keys()), sorted(old.keys()-new.keys())
    changed = [
        (key, {field: (old[key].get(field), new[key].get(field))
               for field in new[key] if field != "name" and old[key].get(field) != new[key].get(field)})
        for key in sorted(old.keys() & new.keys())
        if any(old[key].get(field) != new[key].get(field)
               for field in new[key] if field != "name")
    ]
    print(f"ADDED={len(added)} REMOVED={len(removed)} CHANGED={len(changed)}")
    for key in added[:args.limit]:
        print("  +", describe(new[key]))
    for key in removed[:args.limit]:
        print("  -", describe(old[key]))
    for key, differences in changed[:args.limit]:
        name = new[key]["name"]
        diff = "; ".join(f"{field}: {before!r} -> {after!r}"
                         for field, (before, after) in differences.items())
        print(f"  * {name} [{key}]: {diff}")
    if len(changed) > args.limit:
        print(f"  ... {len(changed) - args.limit} more changed athletes")
    if a.get("TotalCount") != b.get("TotalCount"):
        print("NOTE: TotalCount changed between snapshots")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f"ERROR: {exc}")
