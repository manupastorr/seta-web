# Seta Energy Model

Date: 2026-05-26

## Goal

Use energy as a practical DJ navigation aid, not as audio truth. The map, set-zone filters, draft sorting, and Mac app all use the same effective intensity value.

## Scanner Contract

`analyze.py` now writes additive fields:

| Field | Meaning |
| --- | --- |
| `energy` | Backward-compatible generated intensity, same value as `energy_auto` on new scans |
| `energy_auto` | Scanner-generated full-track score |
| `energy_effective` | Scanner effective score before local manual overrides |
| `energy_main` | Median score over the main phrase windows |
| `energy_avg` | Average score over all phrase windows |
| `energy_peak` | 90th percentile phrase score |
| `energy_intro` / `energy_outro` | First and last phrase scores |
| `energy_confidence` | Confidence that one scalar is representative; lower when the curve varies a lot |
| `energy_curve` | Ordered phrase scores in the 0-1 range |

Phrase windows use 32 bars from detected BPM. When BPM is unavailable, the fallback window is 45 seconds.

## Consumers

Use this fallback order:

1. Local manual override
2. `energy_effective`
3. `energy_auto`
4. `energy_main`
5. `energy`
6. `0.5`

Web stores manual overrides in browser `localStorage` at `seta-energy-overrides-v1`.

SetaMac stores manual overrides in `UserDefaults` at `seta-energy-overrides-v1`.

Manual overrides are intentionally not written into `library.json`; that file remains scanner output and can be regenerated safely.

## Cache Behavior

`ANALYSIS_VERSION` is now `13`. Version-12 cache entries with the same file mtime and size are upgraded by running only the full-track energy pass, keeping cached BPM, key, vocals, and waveform fields. Older cache versions still re-run full analysis because their BPM/key behavior may differ from current code.

## Accuracy Notes

This is more useful than the old first-window estimate because it reads the full track and summarizes phrase-level movement. It is still heuristic: it does not know crowd response, arrangement intent, or genre-specific DJ context. Manual ratings are the future training signal.

## Required Verification

```bash
.venv/bin/python -m unittest discover -s tests -v
node --test tests/test_playback.mjs tests/test_draft.mjs tests/test_mix_links.mjs tests/test_render_safe.mjs

cd ../seta-mac
swift run SetaMacChecks
swift build --product SetaMac
```
