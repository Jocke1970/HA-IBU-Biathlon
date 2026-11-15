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

This prototype does **not** automatically import local Python replay files
into HA and does not yet register that sensor. Real-data testing requires
a separate, explicitly installed HA data bridge or future integration.

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
