# CCResult shot-time field investigation (2026-11-15)

## Verified in code

- Public Source=4 SignalR shooting payloads can include `Target1` …
  `Target8` objects. Their documented-by-observation candidate keys
  are `Shootime`, `ShootTime`, `ShootRunTime` and `Hit`.
- The browser recorder already accepts both spellings of shot time.
- The offline MessagePack decoder previously accepted only `ShootTime`;
  fixed in dev with regression coverage.
- The browser recorder previously dropped the optional `ShootRunTime`
  field during compacting; fixed in dev without interpreting its units.
- `tools/ibu_shot_time_audit.py` reports field presence in both compact
  browser capture JSONL and decoded raw SignalR message JSONL.

## Idre 2026-11-15 observed recording

Review of the locally supplied `events.jsonl` showed 1,660
`kind=shooting` events and 201 `kind=race_change` events; **none**
of those compact shooting events contained a nonempty `shots` entry.
A separate small decoded `messages.jsonl` sample contained
`Target*.ShootTime` and `Target*.ShootRunTime` keys with **null**
values. These observations do not prove that CCResult never provides
per-shot timings, only that the present snapshots did not record them.

## Next investigation

1. For a future public competition, inspect one complete Source=4
   Target1–Target5 payload and its `Shootime`/`ShootRunTime` fields.
2. Inspect public provider pages' network calls for additional shooting
   details endpoints, while never retaining cookies, secrets or tokens.
3. If one series provides 2+ verified per-shot timestamps, compute
   exact shot-to-shot intervals; if all 5 are available, compute
   first-to-last shot-series duration. Do not infer intervals from
   cumulative shot count message arrivals.
4. Keep `ShootRunTime` raw until its units and semantics are confirmed.
   Do not assume first shot start, interval or milliseconds.
5. Only then display verified skottserietid and mellan skotten in UI.

## Audit command

Run from `~/IBU-Biathlon` after downloading the dev audit tool:

```bash
python tools/ibu_shot_time_audit.py \
  captures/browser_20261115_120008/events.jsonl \
  --out captures/shot_clock_audit.json
```

For decoded raw frames, add a `messages.jsonl` path to the same
command to compare actual target field keys, not just compact events.
No network requests are performed.
