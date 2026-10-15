# Seta Repository Report

Date: 2026-05-26

## Executive Summary

Seta is a local DJ-library browser. It scans two local folders, analyzes audio into a generated `library.json`, serves a Flask-backed single-page web UI, and lets the user explore tracks by BPM, energy, Camelot key, mix compatibility, playback, and set-draft workflows.

The Swift migration now has a functional sibling macOS app at `../seta-mac`. The stable app boundary is still `library.json`: the native app reads the Python scanner output while the current Python scanner and web UI remain intact. Audio analysis remains Python-owned until there are golden parity fixtures for a native analyzer.

Assumptions:
- "Native mac app" means macOS first, not iOS or Windows.
- The existing Python scanner can remain as the first producer of `library.json`.
- Generated local files (`library.json`, `cache.json`, audio, `.env`) stay uncommitted.
- No new dependencies should be introduced unless a migration step cannot be completed without them.

## Current Repo Shape

Top-level runtime files:
- `config.py`: loads `.env` and resolves `SETA_TRACKS_ROOT`, `SETA_CURATE_ROOT`, and `SETA_PORT`.
- `scan_library.py`: discovers files, applies scanner path rules, analyzes/caches tracks, writes `library.json`, and builds mix edges.
- `analyze.py`: local audio analysis for BPM, BPM confidence, key, phrase-based energy, vocals heuristic, and waveform peaks.
- `camelot.py`: Camelot mapping, colors, harmonic compatibility, BPM compatibility, and combined mix scoring.
- `server.py`: Flask static app server, `/api/library`, reload endpoint, and safe audio streaming.
- `static/index.html`: main D3 UI, player dock, mix map, explore graph, filters, legends, keyboard shortcuts, and draft UI.
- `static/playback.js`: pure play-queue and neighbor helpers.
- `static/draft.js`: pure set-draft helpers and export logic.
- `static/mixLinks.js`: pure explore-layout fallback helpers.
- `static/renderSafe.js`: HTML escaping helpers.

Generated local files:
- `library.json`: scan output consumed by the web UI and now treated as the first Swift contract.
- `cache.json`: analysis cache keyed by absolute track path, mtime, size, and `ANALYSIS_VERSION`.
- `scan.log`: local scan output.

## Runtime Flow

1. `./start.sh` creates `.venv` if needed, installs `requirements.txt`, loads `.env`, runs `scan_library.py`, then runs `server.py`.
2. `scan_library.py` walks `SETA_TRACKS_ROOT` and `SETA_CURATE_ROOT`, skipping `tools/` and `samples/sample_*.wav`.
3. Each audio file is analyzed or loaded from cache.
4. A track record is written with metadata, analysis fields, and optional waveform fields.
5. Compatible track pairs become `edges`.
6. `server.py` serves the web UI and streams track audio only from allowed roots.
7. `static/index.html` fetches `/api/library` and renders the map, legends, filters, player, neighbors, and set draft.

## Data Contract

`library.json` is the migration boundary. Important top-level fields:
- `generated_at`: ISO timestamp.
- `tracks_root`: absolute path used for approved library scan.
- `curate_root`: absolute path used for intake scan.
- `track_count`: expected length of `tracks`.
- `tracks`: track records.
- `edges`: precomputed compatible pairs for Explore layout.

Core track fields:
- Identity/path: `id`, `path`, `artist`, `title`, `source`, `genre`, `batch`.
- Analysis: `duration_sec`, `bpm`, `bpm_raw`, `bpm_octave_corrected`, `bpm_source`, `bpm_confidence`, `key`, `energy`, `energy_auto`, `energy_effective`, `energy_main`, `energy_avg`, `energy_peak`, `energy_intro`, `energy_outro`, `energy_confidence`, `energy_curve`, `vocals`, `vocals_confidence`, `analysis_error`.
- Waveform: `waveform_version`, `waveform_peak`, `waveform_low`, `waveform_mid`, `waveform_high`.

Compatibility edge fields:
- `source`: source track id.
- `target`: target track id.
- `score`: 0-1 compatibility score.

Migration-critical invariants:
- `track_count == tracks.count`.
- Track ids are unique and stable for the absolute path hash.
- `source` is one of `tracks`, `to_curate`, or `other`.
- Energy values stay in the raw 0-1 domain.
- Consumers should use effective energy fallback: manual override, `energy_effective`, `energy_auto`, `energy_main`, `energy`, then `0.5`.
- Map BPM domain is 70-180.
- Waveform arrays, when present, should have matching lengths.
- Edge ids must reference existing tracks.
- Edge scores must stay in 0-1.

## Audio Analysis

`analyze.py` is the most domain-specific part of the app. It should be migrated last unless native offline scanning becomes the primary goal.

Current behavior:
- Loads the first 90 seconds at 22050 Hz for BPM/key/vocals/waveform preview.
- Loads full tracks for phrase-based energy.
- Reads embedded BPM tags when present.
- Resolves half-time/full-time ambiguity with onset autocorrelation and heuristics.
- Computes key by chroma profile against major/minor profiles, then maps to Camelot.
- Computes phrase energy from RMS, spectral centroid, and onset flux over 32-bar windows, with a 45-second fallback when BPM is unknown.
- Computes vocals as a heuristic label (`yes`, `no`, `unclear`) with confidence.
- Computes 400 waveform bars with low/mid/high bands.

Risks:
- BPM/key/vocal heuristics are tuned by local library experience, not objective ground truth.
- Native reimplementation would need audio DSP parity tests before replacing Python.
- The existing cache invalidates on `ANALYSIS_VERSION`; every analysis logic change must bump it. Version-12 cache entries can upgrade to version 13 by running only the full-track energy pass.

## Frontend UI

The current web UI is feature-rich but concentrated in `static/index.html` at roughly 6k lines. The native app is split by screen/state instead of copying that file:
- Library store and filters.
- Map projection and node placement.
- Selection/playback state.
- Neighbor queue.
- Set draft store.
- Export actions.

Existing helper modules already identify logic that is safe to port first:
- `playback.js`
- `draft.js`
- `mixLinks.js`
- `renderSafe.js`

## Existing Test Surface

Python unit tests cover:
- Scanner path rules and source classification.
- Filename parsing.
- Cache invalidation by file signature and analysis version.
- Camelot mapping and mix scoring.
- Library payload sanity checks.
- Server reload behavior.
- Integration-ish generated WAV analysis.
- Vocals and waveform helper behavior.

Node tests cover:
- Playback queue and neighbor navigation.
- Draft add/remove/sort/reorder/export/localStorage normalization.
- Mix-link layout fallback.
- Render escaping.

Browser smoke tests cover:
- UI boot against a running local server.
- Map/player/legends/filter state sanity.
- Draft add/persist/export/draft-only filter flow.

Swift checks cover:
- Current `library.json` decode and validation.
- Camelot/mix scoring parity.
- Filter helpers.
- Draft helpers and export text.
- Real-library smoke using the sibling `../seta/library.json`.

Native manual E2E currently covers:
- App bundle launch and auto-load.
- Idle player dock on launch (`Nothing playing`).
- Native map population and top-bar layout.
- Browser reference screenshot comparison for map/player/filter parity.

## Known Gaps

Current gaps:
- `static/index.html` still holds most UI state and rendering logic.
- No machine-readable schema file for `library.json` yet.
- Unsigned app packaging works; signing/notarization scripts exist but need Apple Developer credentials.
- Browser smoke tests are opt-in and require a running server plus Playwright.
- Native UI automation is manual because this local Swift CLI does not expose XCTest/Testing targets and Computer Use click actions were unreliable in SetaMac during this pass.
- Audio playback is not covered by full automated E2E because real audio files are local and large.
- The Python scanner uses absolute paths, which is fine for local use but not portable between machines.

Lower-priority gaps:
- No CI config was inspected in this report.
- No screenshot-based visual regression suite.
- No golden fixtures for a larger realistic `library.json`.
- No native audio-analysis parity suite yet.

## Recommended Swift Migration Path

1. Keep this repo as the source of truth while creating a sibling `seta-mac` project.
2. In `seta-mac`, keep `library.json` decoding, validation, Camelot/mix scoring, filters, draft helpers, playback helpers, and map layout behind small pure Swift types.
3. Use the Python scanner to generate `library.json`; load that file in the Swift app.
4. Continue parity work on native UI polish: exact filter-bar density, map overlays, keyboard edge cases, and any subjective web-vs-native differences.
5. Only then evaluate native audio analysis. If analysis is migrated, use Python output as golden fixtures until parity is proven.

Done criteria for a real native replacement:
- Swift app opens without a terminal.
- It can choose/load a `library.json`.
- It displays tracks on a BPM x energy map.
- It supports source/search/BPM/Camelot/set-zone filters.
- It plays local audio safely from allowed roots.
- It supports neighbors and draft workflows.
- It exports M3U/text drafts.
- Swift tests cover model decoding, validation, scoring, filters, draft persistence, and map projection.
- E2E test or manual verification covers first-run app launch, library load, map selection, playback, draft add/remove/export.

## Refactor Candidates

Keep scope incremental:
- Extract map projection/filter logic from `static/index.html` into pure JS modules before porting it.
- Add a JSON schema or Python validator module for `library.json`.
- Add fixture-based contract tests shared by Python, Node, and Swift.
- Keep the Swift app split into small files: models, scoring, store, map view, list view.
- Do not port audio analysis until core browsing workflows are native and tested.

## Current Verification Baseline

Run on 2026-05-26:
- `.venv/bin/python -m unittest discover -s tests -v`: 47 passed.
- `node --test tests/test_playback.mjs tests/test_draft.mjs tests/test_mix_links.mjs tests/test_render_safe.mjs`: 26 passed.
- `SETA_RUN_BROWSER_SMOKE=1 SETA_BASE_URL=http://127.0.0.1:8765 node --test tests/test_browser_smoke.mjs`: 2 passed.
- `cd ../seta-mac && ./scripts/verify-all.sh`: passed.

Recent bugs fixed during verification:
- `tests/test_browser_smoke.mjs` now handles the valid auto-open state after reloading with an existing draft. Previously it clicked the already-open Draft tab, closed the panel, and timed out waiting for it to be visible.
- SetaMac launch now suppresses startup playback, so the app opens with `Nothing playing` instead of immediately starting a restored/selected track.
- SetaMac player dock now shows track metadata/waveform only for the actively playing track, not merely the selected track.
- SetaMac top filter bar controls were tightened to avoid chip wrapping and right-edge clipping at the default native window width.
- SetaMac set-zone overlay opacity was reduced to better match the web map.
