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

## Offline REST + SignalR merge (dev only)

The experimental `tools/elite_merge_offline.py` combines local saved REST
checkpoint snapshots and SignalR shooting events by `RaceID` + `AthleteID`.
It does **not** fetch any new data, modify the original captures or guess
missing shot times. It retains checkpoint-specific ranks and never promotes
them to an overall live leaderboard. `ipos` remains class-specific until
the official station labels are mapped.

Example on a Linux Mint checkout, with your own paths:

```bash
python tools/elite_merge_offline.py \
  --rest captures/rest_MEN/rest_snapshots.jsonl captures/rest_WOMEN/rest_snapshots.jsonl \
  --events captures/browser_MEN/events.jsonl \
  --out captures/merged_idre
python -m unittest discover -s tools -p 'test_elite_merge_offline.py'
```

Files produced: `athlete_summary.json`, `athlete_summary.csv`,
`quality_report.json`. CSV contains a compact overview. JSON retains
each checkpoint and shooting series, plus flags for invalid or missing data.
There is no women's shooting telemetry in the current local collection, so
those athletes will correctly show a missing-shooting flag.

`range_seconds` is derived from `OutTime - InTime` when both exist.
`first_to_last_shot_seconds` is only computed if at least two individual
timestamped shots are actually present. Neither quantity is automatically
equal to the provider's official 'ski time' or 'shoot time'. Public REST and
SignalR timestamps have not yet been independently verified for timezone
semantics, so timestamp text is preserved in the report.

This is a research utility on the **dev** branch, not a beta or stable
Home Assistant release. Run regression tests and review the quality report
before considering promotion to beta.


### Idre two-class replay and timing audit

Use **both** saved REST recordings. They include the same startlist,
but different result classes; the merger deduplicates checkpoint observations
by race, athlete, class and `ipos`. Do not omit the women's REST file:

```bash
python tools/elite_merge_offline.py \
  --rest 'captures/rest_MEN/rest_snapshots.jsonl' 'captures/rest_WOMEN/rest_snapshots.jsonl' \
  --events 'captures/browser_MEN/events.jsonl' \
  --out captures/merged_idre_both

python tools/elite_timing_audit.py \
  --merged captures/merged_idre_both/athlete_summary.json \
  --out captures/merged_idre_both/timing_audit.json

python -m unittest discover -s tools -p 'test_elite_*py'
```

`timing_audit.json` provides checkpoint IDs and elapsed-time ranges **per
class**, without fabricating station names. The inferred one-hour offset is
a consistency check against known start and end times, **not** license to
globally rewrite timestamps. A late correction of men's bib 128, shoot 2,
changed its original in/out timestamps backward by an hour after the result
was corrected from six to five shots. The merger retains the valid prior
timestamps when a later otherwise identical five-shot record shifts both
clock values exactly one hour. This repair gets a visible quality flag.
Do not apply it to other shapes or assume all source timestamps use a fixed
timezone. Raw captures are never rewritten.

Any shooting time that is unavailable stays unavailable. A 15-second
post-`OutTime` UI retention policy is a future presentation concern and is
not a substitute for event validation.


### Offline live-state replay (experimental, dev only)

`tools/ibu_live_state.py` reconstructs a historical event-time **snapshot**
from the merged Idre dataset. It is not a provider-connected live service.

```bash
python tools/ibu_live_state.py \
  --merged captures/merged_idre_both/athlete_summary.json \
  --at 2026-11-15T12:08:30 \
  --shooting-offset-hours 1 \
  --hold-seconds 15 \
  --out captures/merged_idre_both/live_state_120830.json

python -m unittest discover -s tools -p 'test_ibu_live_state.py'
```

The snapshot has separately keyed classes, individual checkpoint histories,
checkpoint-local source rank, athlete status, and a shooting range list.
A shooting row appears at `InTime`, enters `recently_finished` at
`OutTime`, and disappears exactly 15 seconds later. **No shot-by-shot
progress is possible from these final merged snapshots**: hits and misses
only become visible after `OutTime`. Replaying the original incremental
SignalR messages will be a later backend step.

The candidate one-hour SignalR-to-REST offset is explicit in the command;
do not treat it as a universally validated provider timezone. By design,
there is no speculative global live position: each athlete's source rank
belongs to their latest checkpoint only, and ranks across different
checkpoints cannot be compared. The `finished` status requires an
explicitly verified `--finish-station` mapping; otherwise a passed
checkpoint does not imply a finish. Missing `OutTime` leaves the range
record in `active_unconfirmed` for later data-quality handling.


### Incremental shooting replay from observed SignalR messages (dev only)

`tools/ibu_signalr_replay.py` uses the recorded `events.jsonl` sequence,
not the final snapshot, to expose only information that had arrived at the
requested local playback time. This supports 0→1→2→3→4→5 shot progression,
source result corrections and 15-second post-`OutTime` display.

```bash
python tools/ibu_signalr_replay.py \
  --events captures/browser_20261115_120008/events.jsonl \
  --merged captures/merged_idre_both/athlete_summary.json \
  --at 2026-11-15T12:08:30 \
  --out captures/merged_idre_both/shooting_replay_120830.json

python -m unittest -v test_ibu_signalr_replay
```

Captured UTC times are converted with `Europe/Stockholm`; the source's
naive shooting timestamps use the **provisional** +1 hour offset, configurable
with `--offset-hours`. Message receipt time is not the precise shot time:
if the original capture omitted per-shot timestamps, interval statistics must
remain unavailable. The tool never surfaces a later message or a future
`OutTime` before it has been observed. The `active_unconfirmed` status
means the last received record did not contain a verified exit; it is not
proof of current physical presence. This remains offline research software,
not a finished Home Assistant integration.


### Checkpoint leaderboard replay (experimental, dev only)

`tools/ibu_leaderboard_replay.py` produces a provisional livetiming
snapshot for the **left-hand** UI panel: athlete, nation, most recent
known checkpoint, accumulated elapsed time, class/checkpoint-local
rank and difference to the fastest observed runner at that station.

Two deliberately distinct modes:

- **reconstructed**: uses final merged records and their `PassTime`
  timestamps to reconstruct historical passing order. Helpful for offline
  presentation tests; it does **not** represent what the timing operator
  knew at the time.
- **observed**: uses only REST snapshots *received* by the requested
  clock time (`captured_utc` converted to Europe/Stockholm). Later
  responses cannot leak into earlier snapshots. This is the correct
  basis for testing observed information availability, though archived
  browser recordings only cover the checkpoints the user opened.

Run with the existing recordings (filenames are from the November 15 Idre capture):

```bash
python tools/ibu_leaderboard_replay.py \
  --mode reconstructed \
  --merged captures/merged_idre_both/athlete_summary.json \
  --at 2026-11-15T12:08:30 \
  --out captures/merged_idre_both/leaderboard_reconstructed.json

python tools/ibu_leaderboard_replay.py \
  --mode observed \
  --rest captures/rest_*/rest_snapshots.jsonl \
  --at 2026-11-15T14:40:00 \
  --out captures/merged_idre_both/leaderboard_observed.json

python -m unittest -v test_ibu_leaderboard_replay
```

No race-wide current rank is computed because checkpoint ranks from
different stations are not comparable. `overall_position` is null by
design; `checkpoint_position` is derived only from observed/retrospectively
replayed comparable station elapsed times. The sorting of athletes in the
JSON is purely for preview, **not a reliable overall ordering**.

The future HA list needs verified official station names, explicit finish
metadata, ongoing result snapshots with the capture clock, and a policy
for ranking mixed-progress athletes. The current data cannot establish
all those. No UI or Home Assistant integration is implemented here.


#### Checkpoint ranking safety update

After the first Idre replay, the athlete list is now deliberately sorted
by **bib**, not by checkpoint rank (ranks from different course points
must not be interleaved as an overall leaderboard). The output adds
`checkpoint_groups`, each keyed by race + class + station with
independently comparable runner placements. The observed replay also
excludes pass timestamps later than `--at` from **the rank calculation
itself**, not only the athlete's selected latest passage.

These checks remain development-only and need a user-run regression test.


### Provisional Idre station catalog and combined UI state (dev only)

`tools/ibu_station_catalog.py` builds a class-specific course station
catalog from the merged athlete histories. It orders stations by median
elapsed runtime and records adjacent transition counts per athlete.
`ipos` is retained as an API selector, **not used as course sequence**.
All official station labels and finish status remain unverified.

`tools/ibu_combined_replay.py` joins the checkpoint leaderboard and
incremental SignalR range state into one UI-facing JSON. It is **offline
only** and deliberately does not invent a global race ranking.

```bash
python tools/ibu_station_catalog.py \
  --merged captures/merged_idre_both/athlete_summary.json \
  --out captures/merged_idre_both/station_catalog.json

python tools/ibu_combined_replay.py \
  --mode reconstructed \
  --merged captures/merged_idre_both/athlete_summary.json \
  --events captures/browser_20261115_120008/events.jsonl \
  --at 2026-11-15T12:08:50 \
  --out captures/merged_idre_both/combined_120850.json

python -m unittest -v test_ibu_station_catalog test_ibu_combined_replay
```

The recording-derived station order is **provisional**. In combined
reconstructed mode, checkpoint passings are retrospective while shooting
data is constrained to observed SignalR message receipt. Do not describe
this hybrid as actual historic live state. Use observed mode with REST
capture files when validating what the browser had truly received.
No beta release until both class mappings and receipt-time replay have
been checked against real files.
