# Seta Swift Migration Handoff

Date: 2026-05-26

## Goal

Create a native macOS Seta app without removing or destabilizing the current Python/Flask/D3 app.

## Current State

This repo remains the web app and scanner. A sibling project has been started at:

```text
../seta-mac
```

The sibling Swift project now covers the native workflow slice:
- It decodes the current `library.json`.
- It validates core library invariants.
- It implements Camelot/mix scoring parity.
- It has pure helpers for search/source/BPM/Camelot/genre/set-zone/draft-only filtering.
- It has pure set-draft helpers for add/remove/final marks/notes/reorder/sort/export.
- It persists drafts in `UserDefaults` under `seta-drafts-v1`.
- It has neighbor queue + play queue helpers ported from `static/playback.js`.
- It has a SwiftUI macOS app with auto-load, filters, set zones, explore links, map, neighbors, multi-draft panel, export buttons, player dock (waveform/seek/shortcuts), and Python rescan bridge.
- It consumes the current effective-energy fields and supports local manual intensity overrides in `UserDefaults` (`seta-energy-overrides-v1`).
- It has unsigned `.app` packaging plus optional sign/notarize scripts.
- It has a dependency-free Swift check executable because this local Swift CLI does not expose `XCTest` or `Testing` to SwiftPM test targets.
- It has a manual native E2E checklist at `../seta-mac/docs/native-e2e-checklist.md`.
- It opens with the player dock idle (`Nothing playing`) and does not auto-play on launch.

## Recommended Next Implementation Path

1. Keep `library.json` as the app boundary.
2. Continue visual parity polish against the web app, especially filter-bar density, map overlay intensity, and player-dock details.
3. Add automated native UI tests if/when XCTest becomes available in this toolchain.
4. Only after the native browsing experience is fully signed off, evaluate migrating audio analysis.

## Do Not Do Yet

- Do not delete or move `tools/seta`.
- Do not rewrite `analyze.py` in Swift until there are golden fixture parity tests.
- Do not add Swift package dependencies for simple parsing, scoring, or UI state.
- Do not commit generated `library.json`, `cache.json`, `.env`, or audio.

## Commands

Current web app tests:

```bash
cd ~/Music/tracks/tools/seta
.venv/bin/python -m unittest discover -s tests -v
node --test tests/test_playback.mjs tests/test_draft.mjs tests/test_mix_links.mjs tests/test_render_safe.mjs
```

Optional browser smoke:

```bash
cd ~/Music/tracks/tools/seta
./start.sh --quick
SETA_RUN_BROWSER_SMOKE=1 SETA_BASE_URL=http://127.0.0.1:8765 node --test tests/test_browser_smoke.mjs
```

Swift tests:

```bash
cd ~/Music/tracks/tools/seta-mac
swift run SetaMacChecks
```

Full verification:

```bash
cd ~/Music/tracks/tools/seta-mac
./scripts/verify-all.sh
```

Swift app:

```bash
cd ~/Music/tracks/tools/seta-mac
swift run SetaMac
```

## Blockers Before Replacement

- Signing/notarization scripts exist, but require your Apple Developer credentials to run locally.
- Native audio analysis is intentionally still Python (`analyze.py`); the app rescans through the existing scanner instead.
- No automated XCTest UI suite on this toolchain; use `SetaMacChecks`, `./scripts/verify-all.sh`, browser smoke, and the manual native E2E checklist.
- Computer Use can inspect SetaMac state, but click actions were unreliable during the latest pass; do not count it as full native UI automation.

## Acceptance Target

Confidence can approach replacement-level after:
- All current Python/Node/browser tests pass.
- Swift checks pass.
- Manual native E2E passes with a real `library.json`.
- Native app supports the core DJ workflow: load library, filter (including set zones), inspect map/explore links, preview/play with waveform seek, neighbors, multi-draft, export.
- Optional sign/notarize succeeds for distribution outside your machine.

## Latest Verification Notes

Latest pass on 2026-05-26:
- `./scripts/verify-all.sh`: passed.
- Web browser smoke: passed.
- Native debug build and release app bundle packaging: passed.
- Current scanner/library state: 807 tracks with `energy_effective` and `energy_curve`.
