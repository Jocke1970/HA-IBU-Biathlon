# Idre sprint – research plan (2026-11-15)

## Confirmed competition schedule
- Women sprint 7.5 km: 10:00 Europe/Stockholm
- Men sprint 10 km: 12:00 Europe/Stockholm
- Sources: https://www.idrefjall.se/hander-pa-idre-fjall/skidtavlingar/sverigepremiaren/ and https://www.skidskytte.se/folj-oss/sverigepremiar-idre-fjall

## Findings 2026-11-14
- IBU Sport API: `Seasons`, `Events`, `Competitions`, `Results` confirmed via Linux Mint, HTTP 200 with frontend-provided API key. Munich race returned 54 individual results, `Shootings` and `ShootingTotal`. `AnalyticResults` S1TM/RNG1/SKIT responded 200 but had empty `Results` for tested Munich event.
- EliteTiming/CCResult live website: `GET https://live.api.nsftiming.no/api/livePG/GetResultlistWithAthletes/2847/36789_2847?level=67233_2847&ipos=2&count=1000` returned 200 in browser and a JSON result list including intermediate timing and athletes.
- A separate Python GET returned 401, and the browser request showed an `x-api-key` header. The key was exposed in chat and MUST NOT be copied into this repo, logs, or tests. Whether the client key is authorized for third-party automation remains unknown. Seek permission/documented access first.
- The above event/class/level/ipos identifiers refer to a particular **Saturday race checkpoint**, and are NOT assumed valid for Sunday's sprint.

## Sunday checklist (manual, no authenticated scraping)
1. Before each race, open https://live.skidskytte.se/ and locate the relevant Sunday sprint.
2. In Brave DevTools > Network > Fetch/XHR, identify the result-list request. Save **URL only** (without cookies, request headers, secrets, tokens). Also note the class and checkpoint names associated with each `ipos`.
3. Observe browser-provided updates and keep limited, manually exported JSON examples only where permitted. Exclude credentials and unnecessary personal information from shared files.
4. Record timing-checkpoint semantics: first/second shooting, laps, finish; confirm by matching names and times, not by assuming `ipos` values.
5. For automated logging, obtain authorized API access and written/clear provider terms. Do not bypass HTTP 401 or reuse the exposed key.
6. Once access is approved, run a 5-minute conservative test, then compare response hashes, row counts, athlete IDs, checkpoint IDs, ranks and shooting fields.
7. During future IBU international races, use the independent IBU logger and collect snapshots, subject to provider terms and rate limits.

## Unknown / to verify
- Permission and documented credentials for external EliteTiming clients.
- Whether ResultlistWithAthletes is suitable for polling or only for browser-origin access.
- How SignalR update messages are structured and whether independent client use is permitted.
- Does Sunday use a new race ID, class ID, level ID, and which checkpoints map to shooting/finish?
- Whether IBU `Results` fills incrementally in an actual live IBU World Cup.

## Repo scope
This is a research-only plan, not a Home Assistant integration. Follow `dev → beta → main` once implementation begins.


## Offline comparison (no external API credentials)

The file `tools/elite_compare.py` compares two manually exported JSON response bodies from **the same event, class and checkpoint**. It performs no network requests.

1. On the live page, inspect DevTools > Network > Fetch/XHR and select the relevant `GetResultlistWithAthletes` request. Confirm the *Response* contains a JSON object with a `Data` array.
2. Manually save its **Response body only** as `before.json` (without headers, cookies, keys or credentials). Repeat a few minutes later for the **same full Request URL**, saving `after.json`.
3. On your laptop, run:
   ```bash
   python elite_compare.py before.json after.json
   ```
   Or when using a Git clone: `python tools/elite_compare.py before.json after.json`.
4. Record observed change count, race/class/checkpoint identifier and timestamps, then repeat for shooting and finish checkpoints if available.

Results may include athlete birth dates and other personal details. Keep the raw response files local; share only redacted excerpts or the comparison summary. Do not commit them to GitHub.

This is a manual diagnostic fallback while external API access remains unverified.
