# Frontend – HA-IBU-Biathlon (development only)

This is the first working **custom-card prototype**, not a HACS release or a
complete Home Assistant integration. No changes have been made to beta/main.

## Permanent directory layout

```text
frontend/
  ha-ibu-biathlon-card.js
  card_config.schema.json
  translations/
    sv.js
    en.js
```

For a future Home Assistant **beta test** (after the beta branch is prepared
and smoke-tested), copy the **whole**
`frontend/` folder's contents to
`/config/www/ha-ibu-biathlon/` and register a **JavaScript module**
Lovelace resource with path
`/local/ha-ibu-biathlon/ha-ibu-biathlon-card.js`.
The sibling `translations/` directory must travel with the JS module.
Do not copy just the main JS file. This persistent path is intentional:
future beta packaging should use the same file organization or a managed
distribution path. Do not install the unverified dev build in the user's Home Assistant.
Package and validate beta before requesting any HA testing.
Remove the manual resource when switching to HACS packaging to avoid
loading two versions.

## Demo card

```yaml
type: custom:ha-ibu-biathlon-card
demo: true
```

Demo rows are synthetic, visually marked DEMO and never say LIVE.
Use the visual card editor for `demo`, `entity`, `class_id`,
`layout`, `clock_display`, `range_sort`, `source_details`,
`show_flags` and `show_version`. The editor emits `config-changed`.
The card follows the HA language for Swedish/English.

## Actual data from HA

An eventual Home Assistant sensor should carry the combined JSON object in
**attributes.livetiming**. The regular entity state stays concise
(e.g. `replay` or `live`), never put large JSON in an HA state string.
Example configuration (once a corresponding entity exists):

```yaml
type: custom:ha-ibu-biathlon-card
entity: sensor.ibu_biathlon_livetiming
demo: false
```

This prototype does **not** register that sensor. For beta UI testing,
the alternative `replay_url` loads a static offline JSON file from HA's
`/config/www/` (served as `/local/`) without creating entities.

## What works in this first prototype

- Two result/range panels, responsive to small screens; stacked/compact.
- Names, bib, flag emoji, checkpoint-local rank and elapsed time (rank is
  never claimed as overall race rank).
- Recorded shooting lanes, target pattern, misses, range elapsed, and
  current observation state.
- Distinct race event/receipt clocks, source attribution, explicit
  replay/demo badge, and expandable source details.
- Swedish and English translation modules, version label and visual editor.

## What is NOT implemented yet

- Live CCResult and IBU adapters, authentication, stream updates,
  mixed-source joining/automatic source failover.
- Real-time course sort, complete checkpoint hierarchy, class selector
  controls, athlete popup/full checkpoint history, and complete range
  interactions.
- All configuration schema options: `source_preference`,
  `timezone_display`, `finished_hold_seconds` and others remain
  design targets until the necessary underlying behavior is implemented.
- A complete HA test run / verified JavaScript bundle, HACS publication.

Always preserve provider-received timestamps separately from race event
timestamps. Source-local event clock offset is provisional.

## HACS dashboard distribution (dev validation)

The repository includes `hacs.json` and the generated, self-contained
`dist/HA-IBU-Biathlon.js`. This is the **dashboard/plugin** packaging
target, not a Home Assistant custom integration. Source modules remain
under `frontend/`, and the reproducible build is:

```bash
node scripts/build-card.cjs
node scripts/build-card.cjs --check
node scripts/test-card.cjs
```

A release-ready dashboard repository must pass both GitHub CI and the
`hacs/action` plugin validation; it must then receive a beta release
and be checked inside a running Home Assistant frontend. No backend
`custom_components/ibu_biathlon/manifest.json` or config flow exists yet.
Once a genuine HA integration is implemented, packaging and HACS
repository category must be decided explicitly; a dashboard-only
`hacs.json` cannot substitute for an integration manifest.

For an official beta HACS test, use the HACS-managed
`/hacsfiles/HA-IBU-Biathlon/HA-IBU-Biathlon.js` resource URL that HACS
provides, and do not retain a duplicate manually registered resource.
The `dist` bundle intentionally contains both language maps inline so
its HACS install does **not** depend on separately copied
`frontend/translations/` files.

Current GitHub test validates custom element registration, picker stub,
editor creation, demo rendering, language selection and HTML escaping.
It does not emulate the complete Home Assistant browser UI.

## Static Idre replay into HA (beta test, no backend integration)

This is an **offline fixture**, not a live REST/SignalR adapter.
On the Linux Mint development machine, after producing a combined JSON:

```bash
python tools/ibu_combined_replay.py \
  --mode reconstructed \
  --merged captures/merged_idre_timeline/athlete_summary.json \
  --events captures/browser_20261115_120008/events.jsonl \
  --at 2026-11-15T12:08:50 \
  --out captures/merged_idre_timeline/combined_120850.json

python tools/ibu_export_ha_fixture.py \
  --input captures/merged_idre_timeline/combined_120850.json \
  --out exports/idre_120850.json
```

Copy `exports/idre_120850.json` to the future test HA installation's
`/config/www/ibu/idre_120850.json` using your existing HA file access.
Do not guess HA hostnames, tokens or SSH connectivity. The URL in a
Home Assistant browser should then be
`/local/ibu/idre_120850.json`.

Set the **visual editor** field `Local replay JSON` to that URL, or
configure:

```yaml
type: custom:ha-ibu-biathlon-card
replay_url: /local/ibu/idre_120850.json
class_id: "36810_2854"
demo: false
```

Keep the fixture away from private/sensitive information: files under
`/config/www/` can be served to clients as static resources, unlike
private backend entity state. This capture contains public sports
timing data only; do not put HA secrets into the JSON.

The card only fetches local `/local/...json` paths and labels the
output REPLAY, never LIVE. A URL change requests a new JSON file.
The `v=` query string is supported for explicit cache busting, but
no automatic polling is implemented. A 404/invalid JSON yields an
explicit error in the card instead of fake data. Editor/demo mode
overrides a replay URL. The static fixture also does not advance time
automatically.

The `replay_url` mode is intentionally a test bridge; it is not the
final HA integration architecture. Complete the beta release before
installing the dashboard module into HA.

## Wide desktop layout (b2 development)

The default `two_column` card uses **equal 50/50 columns** when the
card's actual available width is at least approximately 960 CSS pixels.
Each panel can then reach roughly 450–500px within a 1000–1100px card.
Below this threshold the panels stack vertically, avoiding the cramped
~240px columns from the b1 screenshot. This uses CSS container queries
against the card host, not just the browser viewport.

**Important:** the card cannot enlarge a narrow Home Assistant Sections
column by itself. For the intended wide two-column desktop layout,
place it in a sufficiently wide dashboard view (for instance a Panel
view or an appropriately configured full-width layout). In a normal
narrow Sections column it will deliberately stack rather than show
two tiny columns. Mobile continues to stack. There is no horizontal
scroll or forced fixed-width overflow.

Do not change the `www` directory structure for this UI-only
modification. Beta b1 remains the known working reference until the
new release passes CI and HA testing.

## b3 development UI

- Header renders competition name, city and country from the replay's
  optional `race.name`, `race.city` and `race.country`, or the
  visual editor's `competition_name`, `competition_city`,
  `competition_country` overrides. No location is guessed.
- Results show checkpoint-local position, latest cumulative elapsed time,
  gap at the same station, and real section deltas (`segment_ms`)
  between known cumulative passing times. Missing or not-yet-mapped
  lap numbers remain `–` rather than invented.
- A standard sprint has three skiing loops and two shooting stages;
  **lap times must not be inferred simply from checkpoint count**.
  Mapping checkpoint IDs to verified skiing lap boundaries remains
  a separate backend job.
- Range puts clock values to the left and five targets bottom-right.
  If only elapsed presence time exists it is marked `*`, never
  presented as completed range duration. Shot series timing is
  withheld unless five actual individual timestamps are available.
- This is a `dev` prototype until code tests and a real HA beta test.

## b4 shooting-range board prototype (dev)

The board displays the physical range, not a chronological list of notifications.
`range_layout: lane_board` (default) fixes empty and occupied rows to their
actual lane numbers. Capacity follows a verified `range_metadata.lane_count`
or `race.shooting_lanes` value when provided. Otherwise **30 lanes is a
configurable international-competition default**, explicitly labelled as an
assumption in the UI. The manual `lane_count` (default 0 = automatic fallback,
1–30 accepted) overrides that assumption to support smaller national venues,
e.g. 20 lanes. A real lane observed outside the configured capacity is shown
separately rather than silently reassigned. No historic race's actual
capacity is claimed verified by this assumption.
`range_layout: occupied` displays only captured occupied/recently finished
lanes, suitable for a compact dashboard.

Within each lane, the athlete and five targets share the top row. The second
row shows **arrival timestamp | verified shot-to-shot intervals | departure
timestamp**, using the source-local `in_time`, `shots_with_timestamps`, and
`out_time` fields. These are shown as local wall-clock values only; their
timezone remains unverified. If the provider has not supplied five trustworthy
shot times the intervals and full shot-series duration remain dashes.
The display of an unconfirmed range exit remains visibly unconfirmed.

This is a frontend-only dev change: the existing b3 HA beta is untouched.
