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
