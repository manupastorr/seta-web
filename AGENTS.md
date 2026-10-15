# Seta 🍄 — agent notes

## Scope

This repo is the **Seta map browser** only (`tools/seta/`). It does not own track sorting, genre folders, or Rekordbox workflows.

For moving/sorting/classifying audio files, follow the parent library rules:

**`~/Music/tracks/AGENTS.md`**

## Paths

Defaults (override with `.env` or env vars):

| Variable | Default |
|----------|---------|
| `SETA_TRACKS_ROOT` | `~/Music/tracks` |
| `SETA_CURATE_ROOT` | `~/Downloads/To Curate` |
| `SETA_PORT` | `8765` |

Copy `.env.example` → `.env` per machine. Do not commit `.env`.

| Path | Purpose |
|------|---------|
| `~/Music/tracks` | Approved library (`source: tracks`) |
| `~/Downloads/To Curate` | Intake (`source: to_curate`) |
| `.venv/` | Local Python venv (created by `start.sh`) |
| `library.json` / `cache.json` | Generated locally — do not commit |

## Run / develop

```bash
./start.sh                    # scan + serve; open printed URL (default :8765)
.venv/bin/python scan_library.py
.venv/bin/python server.py
```

`start.sh` creates `.venv` on first run, installs `requirements.txt`, sources `.env` if present, then scans and execs `server.py` (it does not auto-open a browser).

`server.py` reloads `library.json` automatically when the file changes on disk (mtime check). `POST /api/library/reload` forces a refresh without restarting.

After changing `analyze.py`, bump `ANALYSIS_VERSION` so the cache re-analyzes stale entries.

## Tests

After `./start.sh` has created `.venv` once:

```bash
.venv/bin/python -m unittest discover -s tests -v
node --test tests/test_playback.mjs
node --test tests/test_draft.mjs
node --test tests/test_mix_links.mjs tests/test_render_safe.mjs tests/test_rb_waveform.mjs tests/test_tempo_map.mjs tests/test_mix_recipe.mjs
```

Optional browser smoke test when the local server is running:

```bash
SETA_RUN_BROWSER_SMOKE=1 SETA_BASE_URL=http://127.0.0.1:8765 node --test tests/test_browser_smoke.mjs
```

Covers scanner path rules, Camelot/mix scoring, play-queue navigation (`static/playback.js`), and optional sanity check against a local `library.json` if present.

## Analysis vs Rekordbox

BPM and Camelot key prefer **Rekordbox** when a local analyzed track matches the scanned file path (or same filename stem across `.wav`/`.aiff`). Set `SETA_USE_REKORDBOX=0` to disable. Override DB path with `SETA_REKORDBOX_DB`.

Energy, waveform, and vocals still come from Seta's local analysis. When Rekordbox has no match, BPM/key fall back to librosa/tags as before. Track fields: `bpm_source` / `key_source` can be `rekordbox`.

When `bpm_confidence` is low (UI/tooltip threshold **0.45**), verify tempo in Rekordbox before trusting grid position or mix links.

## Scanner rules

- Audio: `.wav`, `.aiff`, `.aif`, `.flac`, `.mp3`
- Skip `tools/` tree while walking
- **Skip** `…/samples/sample_*.wav` — soundcloud-set-id Shazam clips, not tracks
- Do not sort or move `To Curate` unless the user explicitly asks

## BPM analysis

Unified resolver in `analyze.py` (see `ANALYSIS_VERSION`):

1. **Tagged ≥100 BPM** — trust store tag (Soundeo/Beatport full-tempo tags).
2. **Tagged 68–92 BPM** — half-time tag zone; double only when librosa also anchors ~140–165 BPM (peak techno) or ambiguous raw + close margin. Organic/cumbia tags stay slow.
3. **No tag** — `librosa.feature.tempo` on onset strength (not `beat_track`; avoids native crashes on some librosa builds), then score octave candidates; prefer primary tempo when a half-time octave was picked; lift obvious psy/techno false halves (~72 → ~140 when scores are close). Prefer half-time when librosa primary is ~155–180 but onset favours ~78–95 (downtempo/organic).

UI fields: `bpm`, `bpm_raw`, `bpm_octave_corrected`, `bpm_source`, `bpm_confidence`, `vocals`, `vocals_confidence`

`vocals` is heuristic (`yes` / `no` / `unclear`) from HPSS harmonic/percussive split, mel-band contrast, and harmonic periodicity (autocorrelation — not `librosa.yin`) on the first ~45s — not speech recognition. Show the player badge only when `vocals_confidence` ≥ 0.45.

Energy fields on each track: `energy` is retained for old consumers. Current consumers should use `energy_effective` with fallback to `energy_auto`, `energy_main`, then `energy`. The scanner writes `energy_main`, `energy_avg`, `energy_peak`, `energy_intro`, `energy_outro`, `energy_confidence`, and `energy_curve` from full-track 32-bar phrase windows; when BPM is unknown, the phrase window falls back to 45 seconds. Web manual overrides live in `localStorage` (`seta-energy-overrides-v1`) and are not written to `library.json`.

Waveform fields on each track: `waveform_version`, `waveform_peak`, `waveform_low`, `waveform_mid`, `waveform_high` (400 bars from the first ~90s analysis window — intro/main preview, not full-track shape).

Map BPM domain: **70–180**. Intensity **values** stay **0–1** in `library.json`; the map **Y axis** runs from a filtered adaptive floor (p3 of effective energies, padded, min span 0.4) up to **1.0** so dense libraries spread vertically without clipping peak tracks. Set-zone filters use effective energy. Bump `ANALYSIS_VERSION` after analysis logic changes.

## UI conventions

- Single frontend file: `static/index.html` (D3 from `static/vendor/d3.min.js`, no build step)
- Bottom **player dock** (full-width, SoundCloud-style): transport, title/artist, badges, wide waveform; left **mix dock** holds Neighbors/Draft tabs, mix queue, and set draft (add/discard, energy ramp, export); filters stay in the top bar
- **Set draft** — local shortlist with add/remove (`a` / `Backspace` on queue focus or map selection), final marks (★), notes, energy/BPM/manual sort, draft-only map filter, M3U + text export; persisted in `localStorage` (`seta-drafts-v1`)
- **Keyboard shortcuts** (`?` opens help): Space play/pause, ←/→ prev/next track, Shift+←/→ seek, `/` search, `s` toggle mix sidebar, `m` neighbors tab, `n` neighbor mode on map, `a`/`Backspace` add/remove from draft, `d` draft tab, `f` toggle final, `p` play draft, `e`/`b` sort draft by energy/BPM, `z`/`k` toggle set zones/Camelot panels, `r` reset view, ↑/↓ mix queue when sidebar open, Esc peels filters/search/sidebar/neighbor mode/view
- Player uses a Serato-style RGB canvas waveform (red bass / green mids / blue highs); peaks come from `library.json` when present (scan-time, 400 bars from first ~90s); otherwise one `fetch` + client decode. Playback uses the same fetch (blob URL), cached in memory (24 tracks)
- `./start.sh --quick` runs `scan_library.py --skip-edges` for faster rescans when only adding tracks
- **Mix map** — BPM/energy placement; **Explore** — same BPM/energy grid with link forces and draggable nodes
- Changing filters (set zones, Camelot, genre, BPM range, search, library source) auto-zooms to the visible filtered nodes; clearing all filters resets the map view. Active filters show in a header summary chip; filter state persists in `sessionStorage` for the tab session
- Set-zone clouds are fixed BPM×energy regions (visual only); legend order follows set flow: **Open / low** → **Floor** → **Late** → **Wind-down** (Closing last). Title: **Set zones**
- Keep changes minimal; no new dependencies without good reason

## Tags page (`/tags`)

- `static/tags.html` + `rb_tags.py`: Rekordbox playlist tree in a sidebar (smart playlists evaluated at page load, so tracks stay put while you tag), play a list back to back, and edit **energy** (Rekordbox stars, `DjmdContent.Rating`) and **Function**, **Source** and **State** My Tags (`TAG_GROUPS` in `rb_tags.py`; Function and Source take one tag, `MULTI_TAG_GROUPS` like State take several).
- Edits queue in `rb_pending.json` (gitignored). **Save to Rekordbox** writes them only while Rekordbox is closed (pyrekordbox refuses to commit otherwise), after copying `master.db` to `rb_backups/` (last 5 kept).
- **Filter** panel (`F`): energy and every My Tag group, plus `(none)`; OR inside a group, AND across groups. Ticks persist in `localStorage` (`seta-tags-nav-v1`).
- Keys: Space, ←/→ tracks, Shift+←/→ seek, `1`–`5` energy, `0` clear, first letter of a Function (I/H/M/L/R) toggles it, `F` filter panel.
- `tests/test_rb_tags.py` writes only into a temp copy of `master.db`.
- Each row shows **Rekordbox's own waveform** (Preview column look): `rb_waveform.py` reads the PWV4 color preview from the track's `ANLZ0000.EXT` and cues from `master.db` (read-only, cached until `master.db` changes); `static/rbWaveform.js` draws it with Beat Link's color math and hot cue badges. `GET /api/rb/waveform/<content_id>`; `GET /api/waveform/<track_id>` does the same for a library track. Click a waveform to play from that point.

## Arrange page (`/arrange`)

- `static/arrange.html` + `static/tempoMap.js`: pick a Rekordbox playlist and lay its tracks out as waveform blocks on two lanes, like a DJ timeline. Drag a block (title or waveform) sideways to move where it mixes into the previous track; drag its number badge (or Alt+drag) to reorder; drag its edges to trim (snaps to phrase starts, Shift: to bars).
- Each mix is anchored to a point in the previous track (`entry: {prevId, ms}` on the incoming item), so trimming A's end only shortens the mix; B keeps its place in A. A dragged track lands on a phrase alignment within 1.5 bars (some phrase of B on some phrase of A: B's start, or B's drop on A's drop; B's offsets scale by B BPM / A BPM while it runs at A's tempo), else on the nearest bar of A (Shift: bars only); a click without moving selects (title) or plays (waveform). The mix chip only shows the length; `[` `]` step through alignments (Shift: one bar). Lined-up phrase lines turn yellow.
- **Sync** (default on): the incoming track enters at the outgoing tempo (key kept), holds it through the mix, then glides back to its own BPM over 16 bars (`tempoMap.js`, tested). Mixes start on a phrase of B and on a bar of A; phrases come from Rekordbox's PSSI analysis (`/api/rb/waveform` returns `phrases`, `downbeats` and every `beats` time), else every 16 bars from the first downbeat.
- **Playback engine**: Web Audio, sample-accurate. Each track is decoded once (`decodeAudioData`, the 5 most recently used kept; finished sources are released) and scheduled on the audio clock, so tracks in a mix cannot drift. The part of a synced track not at its own tempo (hold + glide) is time-stretched ahead of time in `static/stretchWorker.js` with SoundTouch (`static/vendor/soundtouch.js`, LGPL-2.1, license beside it; 40 ms sequence, 10 ms seek window), then played at rate 1; the worker trims SoundTouch's delay by matching transients beat by beat (median). Measured: stretched beats sit a median 1–3 ms from where the grid puts them. Play and seek wait until the audio for that spot is decoded and stretched (the play button spins), so nothing is skipped. Scheduling and mixer levels run on a 40 ms timer, not animation frames, so a background tab keeps mixing. Voices are keyed by place in the set, so a track can appear twice. Tracks within 45 s are scheduled and the next ones decoded/stretched ahead; a layout change while playing restarts playback from the current spot (once, when a drag ends). At most two tracks play at once: a track cannot enter before the one two places back has ended. Synced blocks are drawn in set time (`RbWaveform.paint` `timeAt` / `fractionAt`), so a click plays exactly what is under the mouse.
- Each block's **M** button mutes that track (saved with the arrangement); in a mix with one side muted, the other plays alone at full volume and full bass.
- Each block's top bar holds only its number, M and title; BPM (and mix tempo), key, length, artist and EQ sit on a line under its waveform.
- Each block has **H / M / L** EQ buttons stacked at the left of its waveform: click kills a band (−26 dB) or restores it to 0, the wheel nudges it ±3 dB; grey = flat, green = boosted, orange = cut, red = killed.
- Click a block's title to select it (keys act on the selected track). While playing, the bottom bar shows a live strip for every track sounding (two during a mix): volume and Low/Mid/High including the automatic bass swap (which adds to the track's own Low); click a strip to select that track.
- **Keys** (`?` lists them): Space, Enter (play from selected), 1–9 select by number (two quick digits for 10+; numbers show on each block), ←/→ select, Alt+←/→ move, M mute, Q/A W/S E/D EQ ±3 dB, R reset EQ, [ ] mix in earlier/later (Shift: 1 bar), , . trim start, < > trim end, T sync, + − F zoom.
- Output: every track's chain feeds a master bus with headroom (×0.6, about −4.4 dB) and a limiter (−1.5 dB, 20:1, 1 ms attack), so two full tracks in a mix do not clip (measured: peaks +0.9 dB before, −1.1 dB after, no clipping). Each track is loudness-matched on decode to −9 LUFS integrated (ITU BS.1770 / EBU R128: K-weighting, 400 ms blocks, −70 LUFS and relative −10 LU gates; `static/loudness.js`, tested against the standard's 997 Hz calibration; about 0.1 s per track), within −8 to +4 dB, like Rekordbox's Auto Gain.
- Mixing: one Web Audio chain per sounding track (3-band EQ + fader). Default blend (`static/mixRecipe.js`, tested), in bars from B's start; values follow DJ practice (one bassline at a time, swap on a phrase) and studies of real mixes (Kim et al., ISMIR 2020: transitions cluster at whole phrases; 86% of tempo changes under 5%). The EQ does the blend and the faders only move at the ends, one layer at a time (onion): B enters with highs 66%, mids 13%, lows killed (linear gains); its fader comes up to 100% over 2 bars; B mids rise to 66% over 4 bars; over 8 bars B highs and mids ramp to 100% while A mids ramp to 50% and A highs to 75%; bass swap (B lows 100%, A lows killed) on the first phrase start (every 8 bars from B's start) after the blend where B has bass (PWV4 low band ≥ 40% of its loudest, `RbWaveform.bandLevel`), else the first bar with bass, else none; from the swap (or the blend's end) A ramps out over 8 bars, then its fader cuts (half-beat ramp; on A's last downbeat if that comes first). The timeline dims A after that cut (red line). Mixes under 22 bars squeeze the steps. Each track's own EQ adds on top. A new mix starts 32 bars before A ends (`DEFAULT_BARS`); a mix label shows ⚠ and the percentage when sync stretches the tempo more than 5%. It also shows "⚠ short" when a mix is under 32 bars for similar tracks (Camelot-compatible keys, `keysCompatible`, and BPM within 3%) or under 16 bars for different ones (`SEAMLESS_BARS`; real DJ mixes cluster at whole phrases, and an automatic DJ with 16–32 bar fades was rated seamless in a listening test); 0 bars counts as a deliberate cut. "⚠ key" flags keys that do not mix on the Camelot wheel (`keysCompatible`), "⚠ energy −2" a drop of 2+ stars (stars = energy). The set waveform carries a white energy line (stars per track, changing mid-mix). "⚠ vocals" flags a mix where both tracks have an audible voice (volume > 5% and mids ≥ 30% on the mix lines) for 2 s or more, using rekordbox's own AI vocal detection: the `PVDI` tag in each track's `ANLZ0000.2EX` (reverse-engineered here: header hop u32 = 1024, sample rate u16 = 22050, u16 = 1, count u32; body one byte 0–4 per 46.4 ms; ≥ 2 counts as a voice), read by `rb_waveform.read_vocals` (tested) and sent as `vocals: {step_ms, levels (base64)}` in `/api/rb/waveform`. Blocks show it as a thin blue strip on top, like rekordbox. (A home-made spectral heuristic was tried first and dropped: it rated instrumental tracks as vocal.)
- **Mix curves**: each mix has 8 lines, volume / low / mid / high for the outgoing (`out`) and incoming (`inc`) track, as points `{b, v, m?}` (bars from B's start, linear gain 0–1, `m` = the value halfway to the next point, so a segment bends as u^k; two points on one bar make a step; `MixRecipe.valueAt` / `recipeLine` / `silentFrom`, tested). Untouched lines come from the recipe (`recipeLine`: 1–4 key points per line, ramps between them, a step only for the bass swap; `mixLevels` reads the same lines), so they follow mix length changes; an edited line is stored on the incoming item as `curves: {prevId, lines: {"inc.mid": [...]}}` and wins. Playback reads the lines every 40 ms; A's red cut line is where its volume line reaches 0 for good. The selected track's mix shows its lines as an SVG over both waveforms (`drawCurves`); click a line to edit it, drag points (bars; Shift free), drag the hollow square at a line's held start / end (it becomes a point once dragged), double-click to add, Alt+click / Delete to remove, drag the dot between points to bend; the mix label gets two groups of Vol L M H buttons, **Out** (the previous track leaving) and **In** (this track coming in), and **↺ recipe**, and clicking a mix label zooms to it.
- **Mixes only** (header toggle, key `X`, saved): playback covers only windows around each mix, from 8 bars before B enters to 4 bars after A's cut (`mixWindows`, merged when they touch), and jumps to the next window at the end of each one (next mix's audio is prepared 10 s ahead); play / click land on a mix. On each jump the mix is selected (curves show) and the timeline follows. `N` / `P` jump to the next / previous mix in either mode. The timeline then shows only those windows side by side (`spans`, `timeX` / `xTime` map set time to pixels with a 56 px striped "skip" gap per skipped stretch; each track is drawn as one piece per window it touches, trim handles only on its real start / end; 1× fits all windows). The set waveform dims what is skipped; the footer shows "Mix 4→5 · 4 of 10". Following the playhead pauses 4 s after a hand scroll (wheel or scrollbar), not after redraws.
- Zoom: − / + / Fit buttons (keys `-`, `+`, `F`) step from 1× (whole set fits) to 64×. Arrangements are saved on this Mac (`arrange_store.py`, tested: `GET /api/arrange/sets`, `PUT /api/arrange/sets/<playlist id>` with `{items, at}`; `arrangements.json` plus `arrangements-history.jsonl`, which keeps every overwritten version; both git-ignored) and also in `localStorage` (`seta-arrange-v1`, with a per-set `stamps` time). On load the newer copy wins; when the Mac's copy wins over a different browser copy, a toast offers "Use this browser's" (undoable). A browser-only set moves to the Mac on first load. The Arrange-only share mode reads and writes the same store, so a second person's edits reach the Mac (last change wins per playlist). The view (`views`: zoom, scroll, play spot, selected track), saved on change, every 2 s while playing and on unload; Every edit goes through `commit()` and can be undone (⌘Z / ⇧⌘Z, or the ↶ ↷ buttons; 200 steps, per page load); Reset returns to the playlist order and is undoable too. A time ruler sits under the lanes, lanes grow with the window, the set waveform dims what is off screen, and the timeline follows the playhead unless you just scrolled. **Export XML** posts the order and each track's mix points to `POST /api/rb/xml` (`rb_xml.py`, tested) and writes a rekordbox XML to one fixed file, `~/Music/rekordbox/seta.xml` (`SETA_RB_XML` overrides; atomic replace, no browser download, so rekordbox's Imported Library keeps pointing at it and only needs ↻). Before writing, it backs up the rekordbox library (`rb_tags.snapshot_library`: master.db with -wal and -shm, since recent changes live in -wal, into `rb_backups/library-<time>/`, newest 5 kept; restore = quit rekordbox, copy the three files back) and moves the previous export to `seta-exports/seta-<time>.xml` (newest 20 kept). The XML: the playlist in set order, every track with its current cues (hot cues, memory cues, loops, comments; colors are not carried) plus memory cues (they follow the mix lines: "bass swap" where the new track's low line first reaches 50%, "cut" where the old track's volume line reaches 0 for good, so edited curves move them; a mix without a swap gets no swap cue) "Seta mix in", "Seta next in", "Seta bass swap", "Seta cut" (older "Seta …" cues are left out, mix points on an existing memory cue are skipped). In rekordbox, set it once under Preferences → Advanced → Database → rekordbox xml; after each export refresh "rekordbox xml", select the playlist's tracks → Import To Collection (yes to overwrite): only that applies the cues to tracks already in the collection (verified: 31/31 cues, hot cues kept); dragging the playlist or Import Playlist brings only the order. `GET /api/rb/m3u` (order only) still exists. Nothing is written to Rekordbox.

## Always-on servers (this Mac)

Two LaunchAgents keep Seta running: they start at login and restart within 10 s after a crash.

| Label | Port | Mode |
|---|---|---|
| `com.manuel.seta.web` | 8777 | everything, this Mac only |
| `com.manuel.seta.shared` | 8778 | Arrange only, home network (`SETA_HOST=0.0.0.0`, `SETA_ARRANGE_ONLY=1`) |

Plists in `~/Library/LaunchAgents/`, logs in `~/Library/Logs/<label>.log`. After changing Python code, restart with `launchctl kickstart -k gui/$(id -u)/com.manuel.seta.web` (and `.shared`); static files need only a page reload. Stop for good with `launchctl bootout gui/$(id -u)/<label>` and remove the plist.

## Sharing Arrange on the home network

```bash
SETA_HOST=0.0.0.0 SETA_PORT=8778 SETA_ARRANGE_ONLY=1 .venv/bin/python server.py
```

Writes (`POST`) from another website are refused (`Origin` / `Sec-Fetch-Site` check). `/api/rb/audio` loads Rekordbox paths on demand, so a page opened before a server restart still plays. `/api/rb/tracks` returns `arrange_only`, and the page then hides Tags and Export. `SETA_ARRANGE_ONLY=1` answers only `/arrange`, `/static/` and the read-only routes it uses (`/api/rb/tracks`, `/waveform`, `/audio`, `/m3u`); `/` redirects to `/arrange`, everything else (Tags, library scans, Rekordbox edits) is 404. Others open `http://<Mac name>.local:8778/arrange` on the same Wi-Fi. Arrangements stay in each viewer's browser, so they are not shared between people. Keep `SETA_HOST` at its default (127.0.0.1) for normal use.

## Git

- Commit app code only (`library.json`, `cache.json`, audio stay ignored)
- Remote: `manupastorr/seta` on GitHub
