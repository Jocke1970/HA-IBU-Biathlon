# IBU 2026/27 – one-pass data collection plan

The focus is complete **source evidence**, not immediate Home Assistant UI work.
Use the provider's public IBU Sport API only as permitted. This is an
undocumented interface, not a guaranteed public integration contract.

## What we capture

**Phase A, season catalog:** `Seasons`, `Events(SeasonId=2627, Level=0)`,
`Cups(SeasonId=2627)`, and optionally `Competitions(EventId=...)`.
Save raw replies, field paths and metadata. Select concrete RaceIds from
the competition list instead of inferring IDs.

**Phase B, one chosen RaceId:** `Results(RaceId=...)` and the nine
currently known `AnalyticResults` categories:

| TypeId | Working group | Confidence |
|---|---|---|
| S1TM–S4TM | shooting-stage time analyses | Candidate; verify with raw response |
| RNG1–RNG4 | range-stage analyses | Candidate; verify with raw response |
| SKIT | skiing analysis | Candidate; verify with raw response |

Never assert those codes' semantics from the identifier alone. Nonexistent
analytics may legitimately return empty/error for particular race formats.
Always inspect response keys, nullability, status codes and timestamps first.

Archive *complete* JSON rather than extract a narrow field whitelist:
competition/event titles, location, nation, distance, event format,
scheduled start, official status, participating athlete identities, bib,
nation and team/relay metadata, final result and gaps, split/lap/section
timing, penalties, shooting misses, range time, shooting series time and
any per-shot fields that might appear. Not all will be provided; report
availability, never manufacture fields.

Every response is recorded as a separate UTF-8 JSON file. `manifest.json`
contains capture time, endpoint, sanitized parameters, HTTP status, byte
size, SHA-256, response type and sampled nested field **names**. A catalog
or race run is finite, read-only, with no automatic retries or live polling.
Do not publish raw captures containing athletes' personal information.

## Linux Mint – first discovery

From `~/IBU-Biathlon` in the current `.venv`:

```bash
python tools/ibu_archive_capture.py --mode catalog --season 2627
```

Read `captures/ibu_archive/season_2627/events.json` and choose an
`EventId`; then run again with a **new output root** to avoid overwriting:

```bash
python tools/ibu_archive_capture.py --mode catalog --season 2627 \
  --event-id ACTUAL_EVENT_ID --out captures/ibu_events_selected
```

Use the returned competition `RaceId` for phase B:

```bash
python tools/ibu_archive_capture.py --mode race \
  --race-id ACTUAL_RACE_ID
```

The race phase writes ten raw JSON response files plus a manifest, where
available. It is intended as a **single broad baseline capture** from a
specific race. Use different output roots for another capture or race.

### Limits and next discovery

- This baseline does **not** prove true real-time access, skott-för-skott
  timing, or skjutbaneplacering. We need successive snapshots during a
  competition to measure updates and fields that change.
- There may be further undocumented API endpoints/analytics codes. Record
  them in a subsequent targeted discovery pass rather than guessing
  request paths or issuing an unbounded scan.
- If the source has personal or credential-related values embedded in a
  response, keep the archive private; redact before sharing snippets.
- The existing `ibu_live_logger.py` is for a *short, controlled* live
  comparison after we understand the baseline. It already supports the nine
  candidate analysis types, 60 s minimum cadence and a hard duration limit.
- Existing Home Assistant b5 beta and CCResult frontend are untouched by
  this archival collector.

## Review checklist after first capture

1. Verify actual competition and venue fields, including location/country,
   format, scheduled start, start mode, shooting stages and status.
2. Compare results and analytic records by `IBUId` / `RaceId`; check
   data shape and whether comparable timestamps exist.
3. List all observed timing fields and classifications (ski, lap, range,
   shooting, first-to-last shot and individual shots), including nulls.
4. Inspect athlete, class, relay-team, and penalty structures before
   writing our provider adapter.
5. Distinguish archived final results from verified live information.
