# Seta 🍄

Local web app to browse a DJ library on a **BPM × energy** map, with **Camelot** mix hints, playback, and set-moment overlays. BPM, energy, and key come from local analysis: useful for exploration, not a substitute for Rekordbox when confidence is low.

Default scan folders (override with `.env`):

- `~/Music/tracks` — approved library
- `~/Downloads/To Curate` — intake / uncured batches

## Quick start

```bash
git clone https://github.com/manupastorr/seta-web.git
cd seta-web
./start.sh
```

`./start.sh` scans then starts the server. Open the URL printed in the terminal (default **http://127.0.0.1:8765**). Cached analysis is reused when files are unchanged.

**Demo / landing page:** https://manupastorr.github.io/seta-landing/

For a faster scan after adding only a few tracks (skips mix-edge rebuild):

```bash
./start.sh --quick
```

First run creates a local `.venv` and installs dependencies from `requirements.txt`.

## Share with someone else (separate Mac, own tracks)

Each person runs their **own copy** with **their own music folders**. The app does not sync libraries over the network.

### 1. GitHub access

Repo owner: **Settings → Collaborators → Add people** on [github.com/manupastorr/seta](https://github.com/manupastorr/seta).

### 2. Clone and install

```bash
git clone https://github.com/manupastorr/seta-web.git
cd seta-web
cp .env.example .env   # optional — only if paths differ from defaults
./start.sh
```

### 3. Music folders

Use the same layout on her Mac (or set paths in `.env`):

```
~/Music/tracks/
  House & Deep House/
  Melodic House & Techno/
  …

~/Downloads/To Curate/
  some playlist batch/
```

Supported audio: `.wav`, `.aiff`, `.aif`, `.flac`, `.mp3`

### 4. Custom paths (`.env`)

```bash
cp .env.example .env
```

Edit `.env`:

```bash
SETA_TRACKS_ROOT=~/Music/tracks
SETA_CURATE_ROOT=~/Downloads/To Curate
SETA_PORT=8765
```

Multiple roots (colon-separated on macOS):

```bash
SETA_TRACKS_ROOTS=~/Music/tracks:~/Other/Approved
SETA_CURATE_ROOTS=~/Downloads/To Curate:~/Incoming
```

CLI equivalents:

```bash
.venv/bin/python scan_library.py --tracks-root ~/Music/tracks --curate-root ~/Downloads/To\ Curate
.venv/bin/python scan_library.py --tracks-root ~/Music/tracks/House --tracks-root ~/Music/tracks/Techno
```

Then `./start.sh` again. Each machine keeps its own `library.json` and `cache.json` (not in git).

**SetaMac (native app):** download from [seta-mac releases](https://github.com/manupastorr/seta-mac/releases) — first launch runs in-app setup (no Terminal); then use **Library → Library Folders…** instead of editing `.env`.

## Manual commands

```bash
# Scan only
.venv/bin/python scan_library.py

# Scan with options
.venv/bin/python scan_library.py --workers 4 --skip-edges

# Server only (requires library.json)
.venv/bin/python server.py
```

## What it does

| Piece | Role |
|-------|------|
| `config.py` | Paths and port from env / `.env` |
| `scan_library.py` | Walks audio folders, analyzes tracks, writes `library.json` + mix edges |
| `analyze.py` | BPM (`bpm_confidence`), Camelot key, phrase-based energy, vocals hint, Serato-style waveform peaks (400 bars from first ~90s window) |
| `camelot.py` | Wheel colors + mix compatibility scoring |
| `server.py` | Flask: UI, `/api/library`, audio streaming |
| `static/index.html` | Single-page D3 map + player |

### Layouts

- **Mix map** — tracks placed by BPM (x) and energy (y); soft clustering when many share the same values
- **Explore** — force graph by mix links; BPM/energy grid + set-moment clouds stay as background reference
- **Set draft** — shortlist tracks for a set (~50 target): add/remove, final marks, notes, energy ramp, draft-only filter, M3U/text export (persisted in browser `localStorage`)
- **Manual intensity** — hover a track and adjust the tooltip slider to override map/draft energy locally; click `Auto` to return to scanner output.

### Energy fields

The scanner keeps `energy` for backward compatibility and also writes:

- `energy_auto` / `energy_effective`: generated score used by current web/mac UIs unless a local manual override exists.
- `energy_main`, `energy_avg`, `energy_peak`, `energy_intro`, `energy_outro`: full-track phrase summary scores.
- `energy_confidence`: confidence in one scalar representing the full track; high variation lowers it.
- `energy_curve`: ordered 32-bar phrase scores, using a 45s fallback window when BPM is unknown.

Manual overrides are not written into `library.json`; the web app stores them in browser `localStorage` under `seta-energy-overrides-v1`.

### Generated files (gitignored)

- `library.json` — scan output for the UI
- `cache.json` — per-file analysis cache
- `scan.log`
- `.env` — local path overrides

Re-scan after adding tracks or changing analysis (`ANALYSIS_VERSION` in `analyze.py`). Version-12 cache entries are upgraded with an energy-only pass; older cache versions still require full re-analysis.

## Tests

From the repo root after `./start.sh` has created `.venv` once:

```bash
.venv/bin/python -m unittest discover -s tests -v
node --test tests/test_playback.mjs tests/test_draft.mjs tests/test_mix_links.mjs tests/test_render_safe.mjs
```

Optional browser smoke test against a running local server:

```bash
SETA_RUN_BROWSER_SMOKE=1 SETA_BASE_URL=http://127.0.0.1:8765 node --test tests/test_browser_smoke.mjs
```

## Scanner exclusions

Not indexed as library tracks:

- `samples/sample_*.wav` under `To Curate` — short clips from **soundcloud-set-id** set identification (Shazam probes). Keep `tracklist.md` / `tracklist.json`; delete `samples/` when done.

## Library organization (Manuel’s setup)

Genre folders, sorting rules, and curation workflow for the main library live in a separate notes file at `~/Music/tracks/AGENTS.md`. Seta only **reads** audio folders; it does not move or classify files.

## Requirements

- Python 3.10+
- See `requirements.txt` — installed automatically by `start.sh`
