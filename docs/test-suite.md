# Seta Test Suite

Date: 2026-05-26

## Purpose

The test suite protects the current web app and creates a migration safety net for the Swift sibling app. The most important contract is `library.json`; every native migration step should either preserve that contract or document a deliberate versioned change.

## Full Local Test Command

Run from `tools/seta/`:

```bash
.venv/bin/python -m unittest discover -s tests -v
node --test tests/test_playback.mjs tests/test_draft.mjs tests/test_mix_links.mjs tests/test_render_safe.mjs
```

Optional browser smoke test when the local server is already running:

```bash
SETA_RUN_BROWSER_SMOKE=1 SETA_BASE_URL=http://127.0.0.1:8765 node --test tests/test_browser_smoke.mjs
```

Swift sibling project checks:

```bash
cd ../seta-mac
swift run SetaMacChecks
```

Full cross-project verification:

```bash
cd ../seta-mac
./scripts/verify-all.sh
```

## Current Coverage Map

Python:
- `tests/test_scan_library.py`: scanner rules, path classification, cache validity, version-12 energy-only cache upgrades, edge generation, and `library.json` sanity.
- `tests/test_camelot.py`: Camelot mappings, color fallback, harmonic compatibility, BPM compatibility, and mix score.
- `tests/test_server_library.py`: server reloads `library.json` when mtime changes.
- `tests/test_analyze_integration.py`: generated WAV analysis returns expected fields, phrase energy fields, and detects click-train tempo.
- `tests/test_analyze_vocals.py`: vocals helper behavior and error payload fields.
- `tests/test_analyze_waveform.py`: waveform shape and version bump guard.

Node:
- `tests/test_playback.mjs`: queue building, neighbor playback, draft playback, and next/previous navigation.
- `tests/test_draft.mjs`: draft mutations, effective-energy sorting, reorder, export, energy ramp, and storage roundtrip.
- `tests/test_mix_links.mjs`: Explore layout fallback when no precomputed edges exist.
- `tests/test_render_safe.mjs`: HTML escaping for metadata rendering.

Browser:
- `tests/test_browser_smoke.mjs`: app boot, no console errors, key UI elements, no helper copy, draft persistence/export/draft-only filter.

Swift:
- `../seta-mac/Sources/SetaMacChecks`: `library.json` decoding, validation, Camelot/mix scoring parity, filter helpers, draft helper exports, effective-energy decode, and real-library smoke.

## Acceptance Criteria For Migration Work

For every migration step:
- Existing Python and Node tests pass.
- New Swift tests pass when Swift code changes.
- If the web UI changes, run the browser smoke test against a local server.
- If `analyze.py` changes, bump `ANALYSIS_VERSION`.
- If `library.json` changes shape, update this document and add a contract test.

## Manual E2E Checklist

Use this when browser smoke is not enough:

1. Run `./start.sh --quick`.
2. Open the printed URL.
3. Confirm the map renders and no browser console errors appear.
4. Search for a known track.
5. Select a node and confirm the player dock updates.
6. Toggle Neighbors and confirm the queue changes.
7. Add a selected track to Set draft.
8. Add a note and final mark.
9. Reload and confirm the draft persists.
10. Export text and M3U.
11. Toggle source, BPM, Camelot, and set-zone filters.
12. Reset the view.

For the Swift sibling:

1. `cd ../seta-mac && ./scripts/verify-all.sh`.
2. `open dist/SetaMac.app`.
3. Confirm the app auto-loads the sibling `library.json`.
4. Confirm the map populates and the player dock starts idle (`Nothing playing`).
5. Select/play a track from the map and confirm player metadata, waveform, and elapsed time update.
6. Confirm manual intensity override changes map/draft order and `Auto` clears it.
7. Confirm search/source/genre/BPM/Camelot/set-zone/draft-only filters work.
8. Confirm neighbors, draft add/remove/final/notes/export, and restart persistence.

## Remaining Test Gaps

- No generated large realistic fixture committed.
- No shared JSON schema file yet.
- No automated native UI test for the Swift app.
- No automated playback test for local audio streaming.
- No visual regression screenshots for the map.
- Computer Use can inspect native app state, but click automation was unreliable in SetaMac during the latest pass.
