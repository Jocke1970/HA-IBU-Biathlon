#!/usr/bin/env python3
"""Offline audit of merged CCResult athlete data. No calls to a timing provider.

Produces class-specific checkpoint catalogs and an evidence-based assessment
of plausible REST-local vs SignalR clock offsets. Never modifies source timestamps.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timedelta
import json
from pathlib import Path
import statistics


def parse_timestamp(value):
    try:
        return datetime.fromisoformat(value) if value else None
    except (ValueError, TypeError):
        return None


def audit(records, offsets=(0, 1, 2)):
    catalog = defaultdict(lambda: defaultdict(lambda: {
        "intermediate_ids": Counter(), "runtime_ms": [], "rank_count": 0
    }))
    timezone = {str(h): {"valid_finish_window": 0, "valid_start_window": 0,
                          "compared": 0, "outside_finish": 0} for h in offsets}
    shooting_data = 0
    invalid_chronology = []
    by_class = Counter()
    for athlete in records:
        cls = athlete.get("class_id") or "unknown"
        by_class[cls] += 1
        checkpoint_times = []
        for point in athlete.get("checkpoints", []):
            ipos = str(point.get("ipos"))
            row = catalog[cls][ipos]
            row["intermediate_ids"][point.get("intermediate_id") or "missing"] += 1
            runtime = point.get("runtime_ms")
            if isinstance(runtime, (int, float)) and runtime > 0:
                row["runtime_ms"].append(int(runtime))
                checkpoint_times.append(int(runtime))
            if point.get("rank_at_checkpoint") is not None:
                row["rank_count"] += 1
        if checkpoint_times and checkpoint_times != sorted(checkpoint_times):
            invalid_chronology.append(athlete.get("bib"))
        start = parse_timestamp(athlete.get("start_time"))
        if not start:
            continue
        last_checkpoint_ms = max(checkpoint_times) if checkpoint_times else None
        for shooting in athlete.get("shootings", []):
            in_time = parse_timestamp(shooting.get("in_time"))
            if in_time is None or (in_time.tzinfo is None) != (start.tzinfo is None):
                continue
            shooting_data += 1
            for h in offsets:
                candidate = in_time + timedelta(hours=h)
                elapsed = (candidate - start).total_seconds()
                result = timezone[str(h)]
                result["compared"] += 1
                if 0 <= elapsed <= 3600:
                    result["valid_start_window"] += 1
                if last_checkpoint_ms is not None:
                    if 0 <= elapsed <= last_checkpoint_ms / 1000:
                        result["valid_finish_window"] += 1
                    else:
                        result["outside_finish"] += 1
    station_catalog = {}
    for cls, stations in sorted(catalog.items()):
        catalog_rows = []
        for ipos, data in stations.items():
            ms = data["runtime_ms"]
            catalog_rows.append({
                "ipos": ipos,
                "intermediate_ids": dict(data["intermediate_ids"]),
                "samples": len(ms),
                "median_elapsed_seconds": round(statistics.median(ms) / 1000, 3) if ms else None,
                "min_elapsed_seconds": round(min(ms) / 1000, 3) if ms else None,
                "max_elapsed_seconds": round(max(ms) / 1000, 3) if ms else None,
                "rank_samples": data["rank_count"],
                "official_label": None,
                "label_verified": False
            })
        station_catalog[cls] = sorted(catalog_rows, key=lambda r: (
            r["median_elapsed_seconds"] is None,
            r["median_elapsed_seconds"] if r["median_elapsed_seconds"] is not None else 999999))
    return {
        "athletes_by_class": dict(sorted(by_class.items())),
        "checkpoint_catalog": station_catalog,
        "shot_series_with_in_time": shooting_data,
        "candidate_signalr_to_rest_offsets_hours": timezone,
        "provisional_best_offset_hours": (
            max(offsets, key=lambda h: timezone[str(h)]["valid_finish_window"])
            if shooting_data and any(timezone[str(h)]["valid_finish_window"] for h in offsets)
            else None
        ),
        "chronology_warnings": invalid_chronology,
        "methodology": "Candidate offset is inferred from whether SignalR InTime falls after "
                       "athlete REST StartTime and before the latest checkpoint runtime. "
                       "This is a consistency test, not independent timezone proof. "
                       "No timestamps are converted. Checkpoint names are unknown until "
                       "official station metadata is verified; station ordering is based on medians."
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--merged", required=True, help="athlete_summary.json from elite_merge_offline.py")
    parser.add_argument("--out", default="captures/merged/timing_audit.json")
    args = parser.parse_args()
    records = json.loads(Path(args.merged).read_text(encoding="utf-8"))
    if not isinstance(records, list):
        parser.error("Expected a list of athletes")
    result = audit(records)
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "athletes_by_class": result["athletes_by_class"],
        "stations_per_class": {k: len(v) for k, v in result["checkpoint_catalog"].items()},
        "candidate_offsets": result["candidate_signalr_to_rest_offsets_hours"],
        "provisional_best_offset_hours": result["provisional_best_offset_hours"],
        "chronology_warnings": result["chronology_warnings"]
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
