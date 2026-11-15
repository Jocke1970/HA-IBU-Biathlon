# Beta 2026.11.0b1 – Home Assistant dashboard test

This is a **beta branch preview**, not a tagged GitHub release and not
the final Home Assistant backend integration. Use this branch, never dev,
for Home Assistant test installations. Main remains untouched.

## Requirements

- HACS/plugin repository checks and GitHub CI green for the beta commit
- Working Home Assistant dashboard (Lovelace)
- File access to `/config/www/` in Home Assistant
- The recorded local combined Idre replay JSON on Linux Mint

## One-time frontend install from the beta branch

Get the self-contained **dist/HA-IBU-Biathlon.js** from the *pinned
successful beta commit*, and place the file at:

`/config/www/ha-ibu-biathlon/HA-IBU-Biathlon.js`

Register ONE JavaScript module resource with this URL:

`/local/ha-ibu-biathlon/HA-IBU-Biathlon.js`

Do not register the source file `frontend/ha-ibu-biathlon-card.js`.
Do not register the HACS resource and the manual resource together.
For later HACS installs, remove this manual resource and let HACS manage
`/hacsfiles/HA-IBU-Biathlon/HA-IBU-Biathlon.js`.

## Export a real static Idre JSON file

From the Linux Mint working directory:

```bash
python tools/ibu_export_ha_fixture.py \
  --input captures/merged_idre_timeline/combined_clocks.json \
  --out exports/idre_120850.json
```

Copy that JSON to:

`/config/www/ibu/idre_120850.json`

The Home Assistant URL should now be:

`/local/ibu/idre_120850.json`

The JSON is a **snapshot**. No polling and no ongoing data collection.

## Card configuration

```yaml
type: custom:ha-ibu-biathlon-card
demo: false
replay_url: /local/ibu/idre_120850.json
class_id: "36810_2854"
layout: two_column
clock_display: both
source_details: expanded
```

The visual editor includes a text field for the replay path; the card
also supports a small built-in demo without a file.

## Acceptance test in Home Assistant

1. Confirm the heading shows REPLAY, never LIVE.
2. Confirm male athletes appear under results; for selected replay
   12:08:50 Axel Mannelqvist appears on range lane 3 with 5 shots,
   2 misses and source state `active_unconfirmed`.
3. Confirm the results clock has a recorded race event but **no**
   recorded REST receipt at 12:08:50.
4. Confirm the shooting source reports CCResult / EliteTiming and a
   SignalR receipt around 12:08:46.
5. Open the visual editor; change stacked/two-column and event/receipt/
   both; save, reload and verify persistence.
6. Verify mobile width, light/dark theme, Swedish/English and versions.
7. Remove or corrupt the JSON path; verify an explicit error rather
   than fake live data. Restore the path afterward.

## Known limitations

- Dashboard-only, no true HA entity, integration manifest or config flow.
- HACS repository validation is not the same as full HA runtime testing.
- No native athlete details popup or continuous live backend yet.
- Source-local event times remain provisionally normalized.
- The README architecture image is a schematic, not a real HA screenshot.

When the test passes, capture genuine HA screenshots for README and
prepare the next beta iteration; do not move to main prematurely.

## b2 – wide responsive layout

Version `2026.11.0b2` retains the existing single-file bundled dashboard
installation. On a sufficiently wide card (~960px or more), results and
shooting get **equal-width columns** with wider spacing and padding.
On a narrower HA card container they stack vertically, independent
of the physical browser width. This is intentional to avoid two cramped
240px columns.

**Existing HA installation:** replace only the contents of the
already registered bundled JavaScript file. If your one resource is
`/local/ha-ibu-biathlon-card.js`, keep it; ensure the file behind
that URL is the standalone **dist/HA-IBU-Biathlon.js** bundle, with
version `2026.11.0b2`. Do not register a second resource or install
the `frontend/` development source. Keep the existing
`/local/ibu/idre_120850.json` snapshot unchanged.

For genuine 50/50 wide columns, give the card enough width in the
dashboard (such as a Panel view or a full-width Sections arrangement).
The card cannot override HA's available column width.

## b3 – event header, course sections, range layout

Version `2026.11.0b3` retains the single-bundle dashboard installation.
Upgrading requires **only replacing the existing registered JS file** with
`dist/HA-IBU-Biathlon.js`. Do not install the development frontend
or create additional HA resources.

- Results use a wider table with checkpoint-local ranking and gap,
  accumulated running time, and the latest **observed course section**
  (delta of cumulative checkpoint readings). Up to three available
  section values appear beneath the latest split. Old replay JSONs
  remain valid, but without `checkpoint_history` they cannot show
  computed sections until regenerated with the updated backend.
- The sprint's three ski laps are not fabricated: a lap number is
  displayed only when the backend supplies `current_lap`. Official
  checkpoint-to-lap mapping is still pending.
- Shooting rows show measured range duration when available; an
  ongoing elapsed duration is marked `*` as provisional. Missing shot
  series duration and shot-to-shot gaps are shown as `–`.
  Five verified individual timestamps are required for series/gaps.
  Targets align bottom-right of the shooting row.
- Name, city, country can be provided via visual editor fields
  `competition_name`, `competition_city`, `competition_country`;
  if no override exists, optional `race` metadata from the backend is
  used. No race location is inferred from the race ID.
- Use a wide panel/section in Home Assistant to view both columns
  side-by-side. Narrow container sizes intentionally stack the panels.

Retain the existing `/local/ibu/idre_120850.json` for an immediate
visual smoke test. For actual section-time values, the offline replay
JSON must be re-generated with updated `ibu_leaderboard_replay.py`
and `ibu_combined_replay.py` using the user's original captures.

## b4 – physical shooting-lane board

Version `2026.11.0b4` replaces the shooting entry list with a 30-position
range board. Each shooting athlete appears on the reported lane. The five
targets align with the name on the upper row, with arrival, shot interval
and departure timestamps below. Missing individual shot times remain dashes;
unconfirmed departure remains a dash. No invented shot timing.

The default `range_layout: lane_board` renders all 30 positions. A smaller
venue capacity from optional source metadata (`range_metadata.lane_count`,
`race.shooting_lanes`) or a visual editor override `lane_count: 20`
dims lanes 21–30 as **unavailable**, distinct from normal **vacant** lanes.
Without capacity metadata or override, 30 is an explicitly marked
international-range assumption, not verified venue capacity. An observed
athlete beyond a configured capacity remains visible rather than silently
reassigned. `range_layout: occupied` is available for a compact view.

Replace only the one registered HA JS file with the contents of
`dist/HA-IBU-Biathlon.js`. The current `replay_url`, local JSON file,
Lovelace resource URL and overall dashboard configuration remain unchanged.
No extra translation modules or resources are required.

## b5 – HA visual check: range header, vacant lanes, retained targets

Version `2026.11.0b5`, one bundled JS resource only.

- Vacant (available) lanes use a subtle green strip with legible primary
  text and bold lane number. Unavailable lanes remain grey.
- Removes the redundant capacity summary `Banor: 30` from the card.
- Range panel title is larger, bold, primary-text colored; event/receipt
  timestamps align to the right on the same heading row.
- Shooting-complete targets remain on the lane until a confirmed range
  departure **or** the next athlete arrives on that same lane, whichever
  occurs first. No fixed time-based expiration. Missing departure remains
  explicitly unconfirmed; no assumption of current physical presence.
- Internal range status values are localized in both Swedish and English.

**Test notes:** Upgrading the existing standalone JS bundle will verify the
visual changes using the existing `/local/ibu/idre_120850.json`. That
snapshot is static and cannot test the changed **backend event retention**
without rebuilding a replay for later timestamps. The backend rule is
covered by the offline tests. Keep the old JSON and one registered resource
for this visual smoke test; do not copy source translation files.
