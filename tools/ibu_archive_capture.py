#!/usr/bin/env python3
"""IBU Sport API archival collector: discover first, then capture one race.

Two supervised, finite, read-only phases. Every API response is archived once
with timestamps, content hash, HTTP status, and a field-schema summary. Uses
the existing research API session/key loader; never serializes credentials.
No polling, guessing endpoints, or automatic harvesting of entire seasons.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time

import requests
from ibu_api_probe import API, SESSION, find_key, rows

# Full set of named analysis types documented in the independent
# biathlonresults client. Availability depends on competition/discipline.
# These are known TypeId candidates, not guaranteed enabled endpoints.
ANALYSIS = (
    "CRST", "RNGT", "STTM", "SKIT", "PURS", "BSTW", "BSTM",
    *(f"CRS{i}" for i in range(1, 13)),
    *(f"RNG{i}" for i in range(1, 9)),
    *(f"S{i}TM" for i in range(1, 9)),
    *(f"FI{i}L" for i in range(1, 5)),
    *(f"CRST{i}" for i in range(1, 5)),
    *(f"RNGT{i}" for i in range(1, 5)),
)


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def safe_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{2,90}", value):
        raise ValueError("Invalid season/event/race identifier")
    return value


def fields(value, prefix="", counter=None, limit=3):
    """Inventory nested field paths without copying sample personal data."""
    counter = counter if counter is not None else Counter()
    if limit < 0:
        return counter
    if isinstance(value, dict):
        for key, child in value.items():
            name = f"{prefix}.{key}" if prefix else str(key)
            counter[name] += 1
            fields(child, name, counter, limit - 1)
    elif isinstance(value, list):
        counter[f"{prefix}[]"] += len(value)
        for child in value[:5]:  # bounded schema sampling; full raw data saved
            fields(child, f"{prefix}[]", counter, limit - 1)
    return counter


def fetch(session, endpoint, params, *, pause=0.7):
    """One GET, no retries; return raw JSON, metadata and observed paths."""
    if endpoint not in ("Seasons", "Events", "Competitions", "Cups",
                        "Results", "AnalyticResults"):
        raise ValueError("Unsupported endpoint")
    started = time.monotonic()
    try:
        response = session.get(API + endpoint, params=params, timeout=25)
    except requests.RequestException as exc:
        return None, {
            "captured_utc": utc_now(), "endpoint": endpoint, "parameters": params,
            "request_error_type": type(exc).__name__,
            "duration_ms": round((time.monotonic() - started)*1000),
        }
    data = response.content
    record = {
        "captured_utc": utc_now(), "endpoint": endpoint, "parameters": params,
        "status": response.status_code,
        "duration_ms": round((time.monotonic() - started)*1000),
        "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
        "content_type": response.headers.get("content-type", ""),
    }
    if response.status_code == 200:
        try:
            payload = response.json()
        except ValueError:
            record["error"] = "Non-JSON response: body not archived"
            payload = None
    else:
        record["error"] = "Non-success response: body not archived"
        payload = None
    if payload is not None:
        record["type"] = type(payload).__name__
        record["field_paths"] = sorted(fields(payload))
    if pause:
        time.sleep(pause)
    return payload, record


def archive(folder, label, response, meta):
    """Atomically archive one raw JSON response and a separate audit record."""
    folder.mkdir(parents=True, exist_ok=True)
    if response is not None:
        dest = folder / f"{label}.json"
        tmp = dest.with_suffix(".tmp")
        tmp.write_text(json.dumps(response, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, dest)
        meta["file"] = dest.name
    return meta


def run_requests(folder, requests_spec, session, pause):
    report = []
    for label, endpoint, params in requests_spec:
        data, meta = fetch(session, endpoint, params, pause=pause)
        report.append(archive(folder, label, data, meta))
        print(f"{label}: HTTP {meta.get('status','ERR')}, {meta.get('bytes',0)} bytes")
        if meta.get("status") in (401, 403, 429):
            print("Provider access/rate limit encountered; stopping.", file=sys.stderr)
            break
    return report


def first_id(data, key):
    for item in rows(data):
        if isinstance(item, dict) and item.get(key):
            return str(item[key])
    return None


def save_manifest(folder, report, mode, identifiers):
    manifest = {
        "format": "ibu_archival_capture_v1", "created_utc": utc_now(),
        "mode": mode, "identifiers": identifiers, "requests": report,
        "caveats": [
            "Endpoint accessibility and field semantics are not verified solely by a 200 response.",
            "Analysis TypeIds are candidates; not every discipline has every type.",
            "No automatic event-to-race, athlete or split mapping is asserted.",
            "Raw archived responses may contain personal competition data; keep locally private.",
            "Timing of a response does not establish provider event timing.",
        ]
    }
    dest = folder / "manifest.json"
    dest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(f"Manifest: {dest}")
    return manifest


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode", required=True, choices=("catalog", "race"))
    p.add_argument("--season", default="2627")
    p.add_argument("--event-id", help="Specific event to fetch competitions in catalog mode")
    p.add_argument("--race-id", help="IBU RaceId in race mode")
    p.add_argument("--out", default="captures/ibu_archive")
    p.add_argument("--pause", type=float, default=1.0, help="Seconds between GET requests, min 0.5")
    args = p.parse_args(argv)
    try:
        season = safe_id(args.season)
        event = safe_id(args.event_id) if args.event_id else None
        race = safe_id(args.race_id) if args.race_id else None
    except ValueError as exc:
        p.error(str(exc))
    if args.mode == "race" and not race:
        p.error("--race-id is required in race mode")
    if args.mode == "catalog" and race:
        p.error("--race-id only applies to race mode")
    if not 0.5 <= args.pause <= 60:
        p.error("--pause must be between 0.5 and 60 seconds")
    folder = Path(args.out) / (f"season_{season}" if args.mode == "catalog"
                               else f"race_{race}")
    if folder.exists() and any(folder.iterdir()):
        p.error(f"{folder} already contains data; use a fresh --out to avoid overwriting evidence")
    folder.mkdir(parents=True, exist_ok=True)
    try:
        key = find_key()
    except (requests.RequestException, RuntimeError) as exc:
        print(f"API initialization failed: {type(exc).__name__}", file=sys.stderr)
        return 1
    # Existing research helper uses its preconfigured session. Key is never printed or saved.
    SESSION.headers["apikey"] = key
    if args.mode == "catalog":
        specs = [
            ("seasons", "Seasons", {}),
            ("events", "Events", {"SeasonId": season, "Level": "0"}),
            ("cups", "Cups", {"SeasonId": season}),
        ]
        if event:
            specs.append(("competitions", "Competitions", {"EventId": event}))
    else:
        specs = [("results", "Results", {"RaceId": race})]
        specs.extend((f"analysis_{x}", "AnalyticResults", {"RaceId": race, "TypeId": x})
                     for x in ANALYSIS)
    report = run_requests(folder, specs, SESSION, args.pause)
    save_manifest(folder, report, args.mode, {"season":season, "event_id":event,"race_id":race})
    # We intentionally do not log raw URLs, authentication keys or response bodies to console.
    return 2 if any(x.get("status") in (401,403,429) for x in report) else 0


if __name__ == "__main__":
    sys.exit(main())
