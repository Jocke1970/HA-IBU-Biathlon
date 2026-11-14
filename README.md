# HA-IBU-Biathlon

Research project for a future Home Assistant biathlon calendar and live-results integration.

**Current stage: data collection only.** No Home Assistant integration or live UI is implemented or verified.

## Experimental tools

- [`tools/ibu_api_probe.py`](tools/ibu_api_probe.py) — inspect IBU seasons, events, competitions, and optional race results.
- [`tools/ibu_live_logger.py`](tools/ibu_live_logger.py) — write timestamped JSONL snapshots for later comparison.

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

Output folders `ibu_probe_output/` and `ibu_live_logs/` are excluded from Git. Do **not** commit live response dumps until you have checked provider permissions and the data they contain.

## Development workflow

Later Home Assistant work will follow `dev → beta → main`. The present tools are research utilities, not a release of an integration.
