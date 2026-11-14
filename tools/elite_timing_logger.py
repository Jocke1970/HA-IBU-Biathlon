#!/usr/bin/env python3
"""Collect timestamped, read-only EliteTiming/NSF Timing result snapshots.

Research utility, not an official client. Does not require or extract
credentials. Check provider terms; use a conservative interval and stop
if access is denied or rate limited.

Example:
  python tools/elite_timing_logger.py --minutes 5 --interval 60
  python tools/elite_timing_logger.py --url 'https://live.api.nsftiming.no/api/livePG/GetResultlistWithAthletes/2847/36789_2847?level=67233_2847&ipos=2&count=1000'
"""
import argparse
import datetime as datetime
import hashlib
import json
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

DEFAULT_URL = (
    "https://live.api.nsftiming.no/api/livePG/GetResultlistWithAthletes/"
    "2847/36789_2847?level=67233_2847&ipos=2&count=1000"
)
ALLOWED_HOST = "live.api.nsftiming.no"


def now_utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="milliseconds")


def validate_url(url):
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != ALLOWED_HOST:
        raise ValueError("Only HTTPS URLs on live.api.nsftiming.no are accepted")
    if not parsed.path.startswith("/api/livePG/GetResultlistWithAthletes/"):
        raise ValueError("Only GetResultlistWithAthletes endpoint is supported")
    if parsed.username or parsed.password:
        raise ValueError("Credentials in URL are not supported")
    return url


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=DEFAULT_URL, help="Observed result endpoint URL")
    parser.add_argument("--interval", type=int, default=60, help="Seconds between polling cycles, minimum 60")
    parser.add_argument("--minutes", type=int, default=5, help="Duration in minutes, 1–180")
    parser.add_argument("--out", default="elite_timing_logs", help="Directory for JSONL output")
    args = parser.parse_args()
    if args.interval < 60 or not 1 <= args.minutes <= 180:
        parser.error("Interval must be >= 60 seconds and duration must be 1–180 minutes")
    try:
        url = validate_url(args.url)
    except ValueError as error:
        parser.error(str(error))

    output_dir = Path(args.out)
    output_dir.mkdir(parents=True, exist_ok=True)
    filepath = output_dir / (
        "elite_" + datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".jsonl"
    )
    session = requests.Session()
    session.headers.update({"Accept": "application/json", "User-Agent": "BiathlonDataResearch/0.1"})
    deadline = time.monotonic() + args.minutes * 60
    cycle = 0
    previous_hash = None
    print("Read-only logger starting:", url)
    print("Output:", filepath, "| interval:", args.interval, "seconds | duration:", args.minutes, "minutes")
    print("Stop at any time with Ctrl+C.")
    try:
        with filepath.open("w", encoding="utf-8", buffering=1) as outfile:
            while time.monotonic() < deadline:
                started = time.monotonic()
                cycle += 1
                record = {"captured_at_utc": now_utc(), "cycle": cycle, "url": url}
                stop = False
                try:
                    response = session.get(url, timeout=20, allow_redirects=False)
                    record["http_status"] = response.status_code
                    record["content_type"] = response.headers.get("Content-Type")
                    record["elapsed_ms"] = round((time.monotonic() - started) * 1000)
                    record["sha256"] = hashlib.sha256(response.content).hexdigest()
                    if response.status_code == 200:
                        try:
                            payload = response.json()
                        except ValueError:
                            record["error"] = "HTTP 200 but not valid JSON"
                        else:
                            record["payload"] = payload
                            if isinstance(payload, dict):
                                record["total_count"] = payload.get("TotalCount")
                                rows = payload.get("Data")
                                record["rows_received"] = len(rows) if isinstance(rows, list) else None
                    else:
                        record["error"] = "HTTP status not 200; response body omitted"
                        if response.status_code in (301, 302, 307, 308, 401, 403, 404, 429):
                            stop = True
                except requests.RequestException as exc:
                    record["error"] = type(exc).__name__
                outfile.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
                digest = record.get("sha256")
                change = "CHANGED" if digest and previous_hash and digest != previous_hash else "same/first"
                if digest:
                    previous_hash = digest
                print(
                    f"{record['captured_at_utc']} #{cycle} "
                    f"HTTP {record.get('http_status', 'ERR')} "
                    f"rows={record.get('rows_received', '-')} "
                    f"total={record.get('total_count', '-')} {change}"
                )
                if record.get("error"):
                    print("  ", record["error"])
                if stop:
                    print("Stopping after access/rate-limit/redirect/not-found status.")
                    break
                delay = min(started + args.interval, deadline) - time.monotonic()
                if delay > 0:
                    time.sleep(delay)
    except KeyboardInterrupt:
        print("\nStopped by user; all completed samples saved.")
    print("Log saved:", filepath)
    return 0


if __name__ == "__main__":
    sys.exit(main())
