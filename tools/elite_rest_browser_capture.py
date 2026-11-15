#!/usr/bin/env python3
"""Supervised CCResult REST response recorder: captures responses browser already requested.

No independent API requests, key extraction, cookies, headers or full URLs.
Captures startlists and result snapshots including selected checkpoint (ipos).
This is research tooling; only browser-requested points can be observed.
Install: python -m pip install playwright
Run: python tools/elite_rest_browser_capture.py --race 2854
Navigate in the opened Brave window to the public competition; choose checkpoints.
Press Ctrl+C to stop.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
from urllib.parse import parse_qs, urlsplit

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sys.exit("Install Playwright: python -m pip install playwright")

HOST = "live.api.nsftiming.no"
BASE = "/api/livePG/"
# Explicit allowlist. Ignore all other responses (incl. auth and negotiate).
RESULT = re.compile(r"^GetResultlistWithAthletes/(\d+)/([A-Za-z0-9_-]+)$")
START = re.compile(r"^GetStartlist/(\d+)$")
MAX_BYTES = 4_000_000


def describe_request(url, race_filter=None):
    """Only return safe, known metadata; never retain the full URL."""
    parts = urlsplit(url)
    if parts.scheme != "https" or (parts.hostname or "").lower() != HOST:
        return None
    if not parts.path.startswith(BASE):
        return None
    endpoint = parts.path[len(BASE):]
    result = RESULT.fullmatch(endpoint)
    start = START.fullmatch(endpoint)
    if not result and not start:
        return None
    race_id = (result or start).group(1)
    if race_filter and race_id != str(race_filter):
        return None
    params = parse_qs(parts.query, keep_blank_values=False)
    safe = {
        "endpoint": "results" if result else "startlist",
        "race_id": race_id,
    }
    if result:
        safe["class_id"] = result.group(2)
    for field in ("level", "ipos", "count"):
        if field in params and len(params[field]) == 1:
            value = params[field][0]
            if re.fullmatch(r"[A-Za-z0-9_-]{1,60}", value):
                safe[field] = value
    return safe


def capture_record(meta, payload, received_utc):
    """Preserve provider data as-is; endpoint metadata is the allowed subset."""
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return {
        "captured_utc": received_utc,
        **meta,
        "sha256": digest,
        "payload": payload,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--race", help="Optional RaceID, e.g. 2854")
    p.add_argument("--out", help="Output folder (default captures/rest_YYYYMMDD_HHMMSS)")
    args = p.parse_args()
    browser = next((shutil.which(x) for x in (
        "brave-browser", "brave-browser-stable", "brave", "chromium", "google-chrome"
    ) if shutil.which(x)), None)
    if not browser:
        p.error("Brave/Chromium executable not found")
    folder = Path(args.out) if args.out else Path("captures") / (
        "rest_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    folder.mkdir(parents=True, exist_ok=True)
    outfile = folder / "rest_snapshots.jsonl"
    last_hash = {}
    counts = {"seen": 0, "stored": 0, "errors": 0, "unchanged": 0}
    print("Opening separate Brave window; navigate to CCResult and select result checkpoints.")
    print("Observes existing page REST responses. No extra API requests.")
    print(f"Saving: {outfile}. Ctrl+C stops.", flush=True)

    with sync_playwright() as pw:
        instance = pw.chromium.launch(executable_path=browser, headless=False)
        context = instance.new_context()
        with outfile.open("a", encoding="utf-8") as out:
            def received(response):
                meta = describe_request(response.url, args.race)
                if meta is None:
                    return
                counts["seen"] += 1
                if response.status != 200:
                    print(f"{meta['endpoint']} race={meta['race_id']} HTTP {response.status} (not saved)")
                    return
                try:
                    # Avoid capturing arbitrary content types or huge responses.
                    content_type = response.header_value("content-type") or ""
                    if "json" not in content_type.lower():
                        print(f"Skipped {meta['endpoint']} (content-type missing or not JSON)", flush=True)
                        return
                    body = response.body()
                    if len(body) > MAX_BYTES:
                        print("Skipped oversized response")
                        return
                    payload = json.loads(body)
                    record = capture_record(
                        meta, payload, datetime.now(timezone.utc).isoformat())
                    key = tuple((k, meta.get(k)) for k in (
                        "endpoint", "race_id", "class_id", "level", "ipos"))
                    if last_hash.get(key) == record["sha256"]:
                        counts["unchanged"] += 1
                        return
                    last_hash[key] = record["sha256"]
                    out.write(json.dumps(record, ensure_ascii=False,
                                         separators=(",", ":")) + "\n")
                    out.flush()
                    counts["stored"] += 1
                    row_count = (payload.get("TotalCount") if isinstance(payload, dict)
                                 else len(payload) if isinstance(payload, list) else "?")
                    print(f"Saved {meta['endpoint']} race={meta['race_id']} "
                          f"class={meta.get('class_id', '-')} ipos={meta.get('ipos', '-')} "
                          f"records={row_count}", flush=True)
                except Exception as exc:
                    counts["errors"] += 1
                    print(f"Failed {meta['endpoint']} race={meta['race_id']} "
                          f"class={meta.get('class_id', '-')} ipos={meta.get('ipos', '-')} "
                          f"({type(exc).__name__})", flush=True)

            context.on("response", received)
            page = context.new_page()
            page.goto("https://ccresult.com/", wait_until="domcontentloaded")
            try:
                while context.pages:
                    page.wait_for_timeout(1000)
            except KeyboardInterrupt:
                print("\nStopped by user")
            finally:
                print("REST responses: {seen} seen, {stored} saved, {unchanged} unchanged, "
                      "{errors} errors".format(**counts))
                context.close()
                instance.close()
    print(f"Saved to {outfile}")


if __name__ == "__main__":
    sys.exit(main())
