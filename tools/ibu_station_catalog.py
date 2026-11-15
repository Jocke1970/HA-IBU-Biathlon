#!/usr/bin/env python3
"""Build an evidence-based station catalog from Idre merged checkpoint history.

No station labels are inferred. Chronological edges are counted only when two
checkpoints belong to the SAME athlete, with valid increasing elapsed runtime.
A strict consensus order is proposed, but candidate finish remains unverified.
"""
import argparse
from collections import defaultdict
import json
from pathlib import Path
from statistics import median


def build_catalog(athletes):
    per_class = defaultdict(list)
    for person in athletes:
        per_class[(str(person.get("race_id")), str(person.get("class_id")))].append(person)
    output = {}
    for (race, cls), competitors in sorted(per_class.items()):
        stats = defaultdict(list)
        predecessor_votes = defaultdict(lambda: defaultdict(int))
        contradicts = defaultdict(int)
        for person in competitors:
            ordered = []
            seen = set()
            for cp in person.get("checkpoints", []):
                station = cp.get("intermediate_id")
                runtime = cp.get("runtime_ms")
                if not station or type(runtime) not in (int, float) or not 0 < runtime < 86_400_000:
                    continue
                if station in seen:
                    continue
                seen.add(station)
                stats[str(station)].append({
                    "ipos": str(cp.get("ipos")), "runtime_ms": runtime,
                    "athlete_id": str(person.get("athlete_id"))
                })
                ordered.append((runtime, str(station)))
            ordered.sort()
            for (_, before), (_, after) in zip(ordered, ordered[1:]):
                predecessor_votes[after][before] += 1
            for earlier_idx, (time_a, name_a) in enumerate(ordered):
                for time_b, name_b in ordered[earlier_idx + 1:]:
                    if time_a >= time_b or name_a == name_b:
                        contradicts[name_b] += 1
        stations = []
        for station, entries in stats.items():
            ipos_counts = defaultdict(int)
            for row in entries:
                ipos_counts[row["ipos"]] += 1
            common_ipos = max(ipos_counts, key=lambda ipos: (ipos_counts[ipos], ipos))
            stations.append({
                "station_id": station,
                "ipos": common_ipos,
                "ipos_conflict": len(ipos_counts) != 1,
                "athletes_with_valid_times": len(entries),
                "median_elapsed_ms": median(x["runtime_ms"] for x in entries),
                "min_elapsed_ms": min(x["runtime_ms"] for x in entries),
                "max_elapsed_ms": max(x["runtime_ms"] for x in entries),
                "official_label": None,
                "label_verified": False,
                "finish_verified": False,
                "contradictory_order_samples": contradicts.get(station, 0)
            })
        stations.sort(key=lambda x: (x["median_elapsed_ms"], x["station_id"]))
        for index, item in enumerate(stations):
            item["proposed_sequence"] = index + 1
            item["preceding_station"] = stations[index - 1]["station_id"] if index else None
            item["following_station"] = (
                stations[index + 1]["station_id"] if index + 1 < len(stations) else None)
            item["immediate_predecessor_votes"] = dict(
                sorted(predecessor_votes[item["station_id"]].items(),
                       key=lambda pair: (-pair[1], pair[0])))
        finish_candidate = stations[-1]["station_id"] if stations else None
        output[f"{race}:{cls}"] = {
            "race_id": race, "class_id": cls,
            "athletes_in_startlist": len(competitors),
            "station_count": len(stations),
            "order_method": "median_elapsed_time_with_per_athlete_adjacency_votes",
            "order_verified": False,
            "finish_candidate_unverified": finish_candidate,
            "stations": stations
        }
    return {
        "status": "provisional_source_derived_catalog",
        "warnings": [
            "Numeric ipos is a provider selector, NOT a guaranteed course sequence.",
            "Official station names and finish meaning require independent verification.",
            "A median sequence is provisional where checkpoint coverage is incomplete."
        ],
        "classes": output
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--merged", required=True)
    parser.add_argument("--out", default="captures/station_catalog.json")
    args = parser.parse_args()
    rows = json.loads(Path(args.merged).read_text(encoding="utf-8"))
    result = build_catalog(rows)
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "classes": {cls: {"stations": v["station_count"],
                          "finish_candidate_unverified": v["finish_candidate_unverified"],
                          "sequence": [
                              {"order": s["proposed_sequence"], "ipos": s["ipos"],
                               "station_id": s["station_id"],
                               "median_elapsed_s": round(s["median_elapsed_ms"] / 1000, 1),
                               "observed_athletes": s["athletes_with_valid_times"]}
                              for s in v["stations"]]}
                    for cls, v in result["classes"].items()}
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
