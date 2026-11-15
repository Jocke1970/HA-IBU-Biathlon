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

## Browser-side SignalR capture (experimental)

The supervised recorder observes incoming WebSocket messages in a **separate Brave window**; it does not use the API key, call timing APIs, or open an independent SignalR session. It only records Source 4 shooting updates and Source 203 race-change notifications. It doesn't store cookies, request headers, or WebSocket connection URLs. Only use on events and services you are permitted to access.

```bash
cd ~/IBU-Biathlon
source .venv/bin/activate
python -m pip install playwright msgpack
curl -fL -o signalr_browser_capture.py https://raw.githubusercontent.com/Jocke1970/HA-IBU-Biathlon/main/tools/signalr_browser_capture.py
python signalr_browser_capture.py --race 2854
```

In the newly opened browser window, navigate manually to the public CCResult event, then keep that window open while collecting. Use **Ctrl+C** in the terminal to stop. Captures are saved in `captures/browser_YYYYMMDD_HHMMSS/events.jsonl`. A session started after the event has finished will not magically replay the live events. The browser is an isolated, temporary session, not your everyday Brave profile. This captures only events that arrive while the recording session is open; it may miss updates during disconnects.

This is **not** a standalone API client and its end-to-end live behavior is not yet verified. Message formats and permissions may change. Don't commit captures, profile data, or credentials.

## CCResult REST checkpoint recording (experimental)

The standalone `tools/elite_rest_browser_capture.py` listens to **JSON responses the
CCResult page itself fetches**. It does not fetch any endpoint separately or
extract API keys. It records only `GetStartlist` and
`GetResultlistWithAthletes`, preserving the JSON payload and sanitized
`RaceID`, class, level and `ipos` metadata (never cookies, access tokens,
request headers or complete request URLs).

Run in the local Linux Mint working directory:

```bash
cd ~/IBU-Biathlon
source .venv/bin/activate
python -m pip install playwright
curl -fL -o elite_rest_browser_capture.py \
  https://raw.githubusercontent.com/Jocke1970/HA-IBU-Biathlon/main/tools/elite_rest_browser_capture.py
python elite_rest_browser_capture.py --race 2854
```

Navigate to the public event in the newly opened Brave window. Select
different checkpoint columns in the results interface. Stop with Ctrl+C.
Output: `captures/rest_YYYYMMDD_HHMMSS/rest_snapshots.jsonl`.
Changes at the same checkpoint are stored as new snapshots. Responses with
unchanged content are skipped. **Selecting a checkpoint is not proof that a
new request occurred.** Only actual observed network responses are recorded;
unrequested checkpoints, historical placement changes before capture, and
officially defined skiing/range times are **not** automatically available.
The endpoint-to-checkpoint label mapping still needs confirmation.

The capture saves publicly visible athlete result payloads locally, so keep
these files private and out of Git. The tool has not yet been validated
end-to-end in a live race. It is separate from the working SignalR capture
and does not modify it.

Offline tests (if using the full Git checkout):

```bash
python -m unittest discover -s tools -p 'test_elite_rest_browser_capture.py'
python -m unittest discover -s tools -p 'test_signalr_browser_capture.py'
```
