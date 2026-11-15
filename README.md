# HA-IBU-Biathlon

Research project for a future Home Assistant biathlon calendar and live-results integration.

**Current stage: data collection only.** No Home Assistant integration or live UI is implemented or verified.

## Experimental tools

- [`tools/ibu_api_probe.py`](tools/ibu_api_probe.py) — inspect IBU seasons, events, competitions, and optional race results.
- [`tools/ibu_live_logger.py`](tools/ibu_live_logger.py) — write timestamped IBU JSONL snapshots for later comparison.
- [`tools/elite_timing_logger.py`](tools/elite_timing_logger.py) — collect timestamped EliteTiming/NSF Timing results for the observed Idre men's race endpoint (experimental).
- [`tools/signalr_offline.py`](tools/signalr_offline.py) — decode manually saved SignalR MessagePack hex frames, group shooting observations, and export JSONL/CSV **without any network requests**.

These tools use an **unofficial/undocumented** public-facing IBU Sport API. Access, API key discovery, endpoints, and data freshness are not guaranteed. Check the provider's usage terms before polling.

## Setup (Linux Mint)

```bash
git clone https://github.com/Jocke1970/HA-IBU-Biathlon.git
cd HA-IBU-Biathlon
python3 -m venv .venv
source .venv/bin/activate
python -m pip install requests
```

Run a basic probe:

```bash
python tools/ibu_api_probe.py --season 2627
```

Identify a valid race ID in the competition output before starting a short snapshot test:

```bash
python tools/ibu_live_logger.py --race-id YOUR_RACE_ID --interval 60 --minutes 5
```

If that works, add `--analytics` to gather selected shooting/range/skiing analyses. This makes 10 requests per cycle. Use responsibly and stop on authentication or rate-limit failures.

For the observed Idre endpoint, use:

```bash
python tools/elite_timing_logger.py --minutes 5 --interval 60
```

The EliteTiming script defaults to the exact endpoint observed in browser DevTools on 14 November 2026. It might stop working after the race; another class or timing point needs its own URL via `--url`. This third-party endpoint is not documented as public for automated use. Test gently, respect terms, and stop on denial/rate limits.

Output folders `ibu_probe_output/`, `ibu_live_logs/`, and `elite_timing_logs/` are excluded from Git. Do **not** commit live response dumps until you have checked provider permissions and the data they contain.

## Development workflow

Later Home Assistant work will follow `dev → beta → main`. The present tools are research utilities, not a release of an integration.

## SignalR offline diagnostic

Install the one extra local library:

```bash
python -m pip install msgpack
```

Paste one complete **binary message's hex string** per line in a UTF-8 text file named `frames.txt`, without WebSocket headers, cookies or connection tokens. Save it locally, then run:

```bash
python tools/signalr_offline.py frames.txt
python -m unittest discover -s tools -p 'test_signalr_offline.py'
```

Outputs are saved under `captures/decoded/`: `messages.jsonl`, `shooting_summary.json` and `shots.csv`. Multiple snapshots of one athlete's shooting can be compared using `AthleteID` and `ShootNr`. Not every SignalR event has shooting data; fields and `Source` meanings remain provisional. **Do not commit captured frames or outputs.** This tool does not capture live network traffic; automated access is a separate unresolved permissions issue.
