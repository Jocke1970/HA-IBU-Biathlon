#!/usr/bin/env python3
"""Audit observed REST capture coverage, status evidence, and finish candidates.

Read-only analysis. Status codes are NOT assigned meanings from guesswork.
A captured response is dated by captured_utc, not its athletes' PassTime.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime
import json
from pathlib import Path
from zoneinfo import ZoneInfo

LOCAL = ZoneInfo("Europe/Stockholm")


def local_time(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.astimezone(LOCAL).replace(tzinfo=None) if dt.tzinfo else None
    except ValueError:
        return None


def audit_rest(paths):
    classes = defaultdict(lambda: {
        "results_snapshots": 0,
        "startlist_snapshots": 0,
        "first_received": None,
        "last_received": None,
        "stations": defaultdict(lambda: {
            "ipos_values": set(), "valid_passes": 0,
            "athlete_ids": set(), "statuses": Counter(),
            "finish_field_true": 0, "finish_field_false": 0,
            "finish_field_missing": 0, "first_received": None,
            "last_received": None, "pass_after_capture": 0}),
    })
    seen_snapshots = set()
    invalid = 0
    for path in paths:
        with Path(path).open(encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                if not line.strip():
                    continue
                try:
                    frame = json.loads(line)
                except ValueError as exc:
                    raise ValueError(f"{path}:{line_no}: invalid JSON") from exc
                capture = local_time(frame.get("captured_utc"))
                race = frame.get("race_id")
                endpoint = frame.get("endpoint")
                if capture is None or not race or endpoint not in ("results", "startlist"):
                    invalid += 1
                    continue
                snapshot_key = (frame.get("sha256"), str(race), str(frame.get("class_id")),
                                str(frame.get("ipos")), endpoint, capture.isoformat())
                if snapshot_key in seen_snapshots:
                    continue
                seen_snapshots.add(snapshot_key)
                payload = frame.get("payload") or {}
                rows = payload.get("Data", []) if isinstance(payload, dict) else []
                if not isinstance(rows, list):
                    invalid += 1
                    continue
                class_ids = {str(x.get("ClassID")) for x in rows
                             if isinstance(x, dict) and x.get("ClassID")}
                if endpoint == "startlist":
                    for cls in class_ids:
                        classes[f"{race}:{cls}"]["startlist_snapshots"] += 1
                    continue
                cls = str(frame.get("class_id") or "")
                if not cls:
                    invalid += 1
                    continue
                group = classes[f"{race}:{cls}"]
                group["results_snapshots"] += 1
                stamp = capture.isoformat()
                group["first_received"] = min(group["first_received"] or stamp, stamp)
                group["last_received"] = max(group["last_received"] or stamp, stamp)
                station_id = None
                for athlete in rows:
                    if not isinstance(athlete, dict):
                        continue
                    result = athlete.get("Time")
                    if not isinstance(result, dict):
                        continue
                    station_id = result.get("IntermediateID") or station_id
                    if not result.get("IntermediateID"):
                        continue
                    station = group["stations"][str(result["IntermediateID"])]
                    station["ipos_values"].add(str(frame.get("ipos")))
                    station["statuses"][str(athlete.get("Status"))] += 1
                    if result.get("FFStatus") is True:
                        station["finish_field_true"] += 1
                    elif result.get("FFStatus") is False:
                        station["finish_field_false"] += 1
                    else:
                        station["finish_field_missing"] += 1
                    ms = result.get("RunTimeMS")
                    if type(ms) in (int, float) and 0 < ms < 86_400_000:
                        station["valid_passes"] += 1
                        station["athlete_ids"].add(str(athlete.get("AthleteID")))
                        passed = result.get("PassTime")
                        try:
                            pass_dt = datetime.fromisoformat(passed) if passed else None
                        except ValueError:
                            pass_dt = None
                        if pass_dt and pass_dt.tzinfo is None and pass_dt > capture:
                            station["pass_after_capture"] += 1
                    station["first_received"] = min(station["first_received"] or stamp, stamp)
                    station["last_received"] = max(station["last_received"] or stamp, stamp)
                # Count the requested endpoint even if all rows have null Time.
                if station_id is None:
                    invalid += 1
    output = {}
    for cls, raw in sorted(classes.items()):
        stations = {}
        for station_id, stat in sorted(raw["stations"].items()):
            stations[station_id] = {
                "ipos_values": sorted(stat["ipos_values"]),
                "valid_passes_seen": stat["valid_passes"],
                "unique_athletes_with_pass": len(stat["athlete_ids"]),
                "status_codes_observed": dict(sorted(stat["statuses"].items())),
                "FFStatus_true": stat["finish_field_true"],
                "FFStatus_false": stat["finish_field_false"],
                "FFStatus_missing": stat["finish_field_missing"],
                "pass_after_capture": stat["pass_after_capture"],
                "first_received": stat["first_received"],
                "last_received": stat["last_received"],
                "verified_finish": False,
            }
        output[cls] = {
            "results_snapshots": raw["results_snapshots"],
            "startlist_snapshots": raw["startlist_snapshots"],
            "first_received": raw["first_received"],
            "last_received": raw["last_received"],
            "station_count": len(stations),
            "stations": stations,
        }
    return {
        "classes": output, "invalid_or_missing_capture_records": invalid,
        "unique_snapshots": len(seen_snapshots),
        "conclusions": [
            "A result row with status 5 does not prove that its selected station is the finish.",
            "FFStatus must not be treated as the finish flag without provider documentation.",
            "Recorded REST responses are snapshots and may be captured well after the race.",
            "No finish station is verified automatically."
        ]
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--rest", nargs="+", required=True)
    p.add_argument("--out", default="captures/rest_coverage_audit.json")
    args = p.parse_args()
    result = audit_rest(args.rest)
    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "unique_snapshots": result["unique_snapshots"],
        "classes": {c: {
            "results_snapshots": v["results_snapshots"],
            "station_count": v["station_count"],
            "first_received": v["first_received"],
            "last_received": v["last_received"],
            "stations": [
                {"station": station_id, "ipos": stat["ipos_values"],
                 "valid_passes": stat["unique_athletes_with_pass"],
                 "status_codes": stat["status_codes_observed"],
                 "FFStatus_true": stat["FFStatus_true"]}
                for station_id, stat in v["stations"].items()
            ]
        } for c, v in result["classes"].items()},
        "conclusions": result["conclusions"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
