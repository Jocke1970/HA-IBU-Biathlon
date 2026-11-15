#!/usr/bin/env python3
"""Record public biathlon SignalR updates from a normal, supervised Brave session.

This script does not call the timing API or open a separate SignalR connection.
It observes the page's incoming WebSocket frames through Playwright and stores
only decoded ReceiveMessage notifications from Source 4 (shooting) or 203.
It never logs request headers, cookies, WebSocket URLs or access tokens.

Install: python -m pip install playwright msgpack
Run: python tools/signalr_browser_capture.py
Then navigate the opened Brave window to the public live result page.
Press Ctrl+C in the terminal to stop.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sys

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sys.exit("Playwright missing. Run: python -m pip install playwright msgpack")

from signalr_offline import frames, decode
from ibu_signalr_target_probe import ShotFieldProbe


def safe_messages(frame):
    """Yield whitelisted decoded messages and corresponding binary frames."""
    if not isinstance(frame, bytes):
        return
    try:
        for raw in frames(frame):
            event = decode(raw)
            if event.get("kind") != "receive":
                continue
            payload = event.get("payload")
            if not isinstance(payload, dict):
                continue
            source = payload.get("Source")
            if source not in (4, 203):
                continue
            obj = payload.get("Object")
            if not isinstance(obj, dict):
                continue
            race_id = str(payload.get("RaceId") or obj.get("RaceID") or obj.get("RaceId") or "")
            if not race_id:
                continue
            yield payload, race_id
    except (ValueError, TypeError, KeyError):
        return
    except Exception:
        # A malformed or unfamiliar message must not interrupt recording.
        return


def target_shot_time(target):
    """The observed provider field is 'Shootime'; accept alternate spelling too."""
    return target.get("Shootime") or target.get("ShootTime")


def compact_record(payload, race_id):
    """Keep only known public result fields, never arbitrary messages."""
    source = payload["Source"]
    obj = payload["Object"]
    base = {
        "captured_utc": datetime.now(timezone.utc).isoformat(),
        "race_id": race_id,
        "source": source,
        "db_id": payload.get("DbId"),
    }
    if source == 203:
        base["kind"] = "race_change"
        base["changed_utc"] = obj.get("ChangedUtc")
        return base
    base.update({
        "kind": "shooting",
        "athlete_id": obj.get("AthleteID"),
        "start_no": obj.get("StartNo"),
        "shoot_nr": obj.get("ShootNr"),
        "prone": obj.get("Prone"),
        "lane": obj.get("Lane"),
        "is_open": obj.get("IsOpen"),
        "sum_shooted": obj.get("SumShooted"),
        "missed": obj.get("Missed"),
        "shoot_string": obj.get("ShootString"),
        "in_time": obj.get("InTime"),
        "out_time": obj.get("OutTime"),
        "shots": [
            {"number": n, "hit": obj[f"Target{n}"].get("Hit"),
             "time": target_shot_time(obj[f"Target{n}"]),
             "shoot_runtime": obj[f"Target{n}"].get("ShootRunTime")}
            for n in range(1, 9)
            if isinstance(obj.get(f"Target{n}"), dict)
            and target_shot_time(obj[f"Target{n}"])
        ],
    })
    return base


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--race", help="Optional race ID to retain, e.g. 2854")
    parser.add_argument("--out", help="Output directory (defaults to dated capture folder)")
    parser.add_argument("--probe-targets", action="store_true",
                        help="Count raw Source=4 target timing fields before compacting")
    args = parser.parse_args()

    browser_path = next((shutil.which(name) for name in (
        "brave-browser", "brave-browser-stable", "brave", "chromium", "google-chrome"
    ) if shutil.which(name)), None)
    if not browser_path:
        parser.error("Brave/Chromium not found. Install Brave or specify a supported browser.")

    folder = Path(args.out) if args.out else Path("captures") / (
        "browser_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    )
    folder.mkdir(parents=True, exist_ok=True)
    outfile = folder / "events.jsonl"
    stats = {"received": 0, "stored": 0}
    probe = ShotFieldProbe() if args.probe_targets else None
    # Deduplicate consecutive identical snapshots per source, race and athlete+shoot.
    last = {}

    print("Opening an isolated Brave window. Navigate to the public CCResult live page.")
    print(f"Recording only public Source 4/203 messages to {outfile}")
    print("No keys, cookies, headers or URLs are saved. Ctrl+C stops.")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=browser_path, headless=False)
        context = browser.new_context()
        with outfile.open("a", encoding="utf-8") as out:
            def on_page(page):
                def on_ws(ws):
                    # Show only the hostname, never full URL/query (may contain tokens).
                    from urllib.parse import urlsplit
                    host = (urlsplit(ws.url).hostname or "").lower()
                    print(f"WebSocket detected on host: {host or '(unknown)'}", flush=True)
                    # Allow known result-provider domains; ignore unrelated sites.
                    if not (host == "ccresult.com" or host.endswith(".ccresult.com")
                            or host == "nsftiming.no" or host.endswith(".nsftiming.no")
                            or host == "sr-sgtiming.service.signalr.net"):
                        print("Ignored unrelated WebSocket host.", flush=True)
                        return
                    print("Timing WebSocket connected (address withheld).", flush=True)

                    def received(frame):
                        stats["received"] += 1
                        for payload, race_id in safe_messages(frame):
                            if args.race and race_id != args.race:
                                continue
                            if probe is not None and payload["Source"] == 4:
                                probe.add(payload["Object"])
                            record = compact_record(payload, race_id)
                            key = (
                                race_id, record["source"], record.get("athlete_id"),
                                record.get("shoot_nr")
                            )
                            comparison = {k: v for k, v in record.items() if k != "captured_utc"}
                            fingerprint = json.dumps(comparison, sort_keys=True)
                            if last.get(key) == fingerprint:
                                continue
                            last[key] = fingerprint
                            out.write(json.dumps(record, ensure_ascii=False) + "\n")
                            out.flush()
                            stats["stored"] += 1
                            if record["kind"] == "shooting":
                                print(f"Bib {record['start_no']} · shoot {record['shoot_nr']} · "
                                      f"shots {record['sum_shooted']} · missed {record['missed']}")
                            else:
                                print(f"Race {race_id}: change notification")

                    ws.on("framereceived", received)

                page.on("websocket", on_ws)

            context.on("page", on_page)
            page = context.new_page()
            page.goto("https://ccresult.com/", wait_until="domcontentloaded")
            try:
                while context.pages:
                    page.wait_for_timeout(1000)
            except KeyboardInterrupt:
                print("\nStopping recording.")
            finally:
                print(f"Saved {stats['stored']} updates from {stats['received']} received frames.")
                context.close()
                browser.close()

    print(f"Result: {outfile}")
    if probe is not None:
        target = folder / "source4_target_probe.json"
        target.write_text(json.dumps(probe.report(), ensure_ascii=False, indent=2) + "\\n",
                          encoding="utf-8")
        print(json.dumps(probe.report(), ensure_ascii=False, indent=2))
        print(f"Sanitized field-presence report: {target}")


if __name__ == "__main__":
    main()
