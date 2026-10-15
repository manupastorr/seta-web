#!/usr/bin/env python3
"""Scan tracks + To Curate, analyze audio, build library.json for the Seta UI."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from concurrent.futures.process import BrokenProcessPool
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from camelot import mix_score
from config import curate_roots, tracks_roots
from rekordbox import apply_rekordbox, load_rekordbox_index

APP_DIR = Path(__file__).resolve().parent
CACHE_PATH = APP_DIR / "cache.json"
LIBRARY_PATH = APP_DIR / "library.json"
AUDIO_EXTS = {".wav", ".aiff", ".aif", ".flac", ".mp3"}
PARALLEL_CACHE_SAVE_EVERY = 25
ENERGY_CACHE_UPGRADE_FROM_VERSIONS = {12}
# soundcloud-set-id writes short Shazam probe clips here — not library tracks.
SET_ID_SAMPLE_DIR = "samples"
SET_ID_SAMPLE_PREFIX = "sample_"


@dataclass(frozen=True)
class ScanRoot:
    category: str  # "tracks" | "curate"
    path: Path

    @property
    def source(self) -> str:
        return "tracks" if self.category == "tracks" else "to_curate"


# Module-level scan configuration (set by configure_scan / CLI).
TRACKS_ROOTS: list[Path] = []
CURATE_ROOTS: list[Path] = []
SCAN_ROOTS: list[ScanRoot] = []
EXCLUDED_PATHS: set[str] = set()


def configure_scan(
    tracks_root_paths: list[Path] | None = None,
    curate_root_paths: list[Path] | None = None,
    excluded_paths: list[str] | None = None,
) -> list[str]:
    """Apply scan roots and exclusions. Returns overlap warnings."""
    global TRACKS_ROOTS, CURATE_ROOTS, SCAN_ROOTS, EXCLUDED_PATHS

    TRACKS_ROOTS = _dedupe_paths(tracks_roots() if tracks_root_paths is None else tracks_root_paths)
    CURATE_ROOTS = _dedupe_paths(curate_roots() if curate_root_paths is None else curate_root_paths)
    SCAN_ROOTS = [
        *[ScanRoot("tracks", path) for path in TRACKS_ROOTS],
        *[ScanRoot("curate", path) for path in CURATE_ROOTS],
    ]
    EXCLUDED_PATHS = {
        str(Path(p).expanduser().resolve())
        for p in (excluded_paths or [])
    }
    return _root_overlap_warnings()


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    out: list[Path] = []
    for path in paths:
        resolved = path.expanduser().resolve()
        key = str(resolved)
        if key in seen:
            continue
        seen.add(key)
        out.append(resolved)
    return out


def _root_overlap_warnings() -> list[str]:
    warnings: list[str] = []
    roots = [(root.category, root.path) for root in SCAN_ROOTS]
    for i, (cat_a, path_a) in enumerate(roots):
        for cat_b, path_b in roots[i + 1 :]:
            try:
                if path_a == path_b:
                    warnings.append(f"duplicate scan root: {path_a}")
                elif path_a.is_relative_to(path_b):
                    warnings.append(f"{path_a} is inside {path_b}; nested roots may classify oddly")
                elif path_b.is_relative_to(path_a):
                    warnings.append(f"{path_b} is inside {path_a}; nested roots may classify oddly")
            except ValueError:
                continue
    return warnings


def is_scannable_audio(path: Path) -> bool:
    if path.suffix.lower() not in AUDIO_EXTS:
        return False
    if SET_ID_SAMPLE_DIR in path.parts and path.stem.startswith(SET_ID_SAMPLE_PREFIX):
        return False
    return True


def is_excluded_path(path: Path) -> bool:
    return str(path.resolve()) in EXCLUDED_PATHS


def owning_root(path: Path) -> ScanRoot | None:
    path = path.resolve()
    matches: list[tuple[int, ScanRoot]] = []
    for root in SCAN_ROOTS:
        try:
            if path.is_relative_to(root.path):
                matches.append((len(root.path.parts), root))
        except ValueError:
            continue
    if not matches:
        return None
    matches.sort(key=lambda item: item[0], reverse=True)
    return matches[0][1]


def discover_files(limit: int | None = None) -> list[Path]:
    files: list[Path] = []
    for root in SCAN_ROOTS:
        if not root.path.exists():
            continue
        for dirpath, _, filenames in os.walk(root.path):
            if "tools" in Path(dirpath).parts:
                continue
            for name in filenames:
                path = Path(dirpath) / name
                if not is_scannable_audio(path):
                    continue
                if is_excluded_path(path):
                    continue
                files.append(path)
    files.sort()
    if limit:
        files = files[:limit]
    return files


def parse_filename(path: Path) -> tuple[str, str]:
    stem = path.stem
    if " - " in stem:
        artist, title = stem.split(" - ", 1)
        return artist.strip(), title.strip()
    return "", stem.strip()


def classify_path(path: Path) -> dict:
    path = path.resolve()
    root = owning_root(path)
    if root is None:
        return {"source": "other", "genre": "Other", "batch": None}

    rel = path.relative_to(root.path)
    dir_parts = rel.parts[:-1] if len(rel.parts) > 1 else ()

    if root.category == "tracks":
        genre = dir_parts[0] if dir_parts else root.path.name
        return {"source": "tracks", "genre": genre, "batch": None}

    batch = dir_parts[0] if dir_parts else None
    genre = dir_parts[0] if dir_parts else root.path.name
    return {"source": "to_curate", "genre": genre, "batch": batch}


def track_id(path: Path) -> str:
    return hashlib.sha1(str(path.resolve()).encode()).hexdigest()[:16]


def file_sig(path: Path) -> dict:
    stat = path.stat()
    return {"mtime": int(stat.st_mtime), "size": stat.st_size}


def waveform_track_fields(analysis: dict) -> dict:
    wf = analysis.get("waveform")
    if not wf or not wf.get("peak"):
        return {}
    return {
        "waveform_version": wf.get("version"),
        "waveform_peak": wf.get("peak"),
        "waveform_low": wf.get("low"),
        "waveform_mid": wf.get("mid"),
        "waveform_high": wf.get("high"),
    }


def load_cache() -> dict:
    if CACHE_PATH.exists():
        return json.loads(CACHE_PATH.read_text())
    return {}


def save_cache(cache: dict) -> None:
    CACHE_PATH.write_text(json.dumps(cache, indent=2))


def cached_analysis(path: Path, cache: dict) -> dict | None:
    from analyze import ANALYSIS_VERSION

    key = str(path.resolve())
    sig = file_sig(path)
    cached = cache.get(key)
    if (
        cached
        and cached.get("mtime") == sig["mtime"]
        and cached.get("size") == sig["size"]
        and cached.get("analysis_version") == ANALYSIS_VERSION
    ):
        return cached
    return None


def cached_analysis_for_energy_upgrade(path: Path, cache: dict) -> dict | None:
    key = str(path.resolve())
    sig = file_sig(path)
    cached = cache.get(key)
    if (
        cached
        and cached.get("mtime") == sig["mtime"]
        and cached.get("size") == sig["size"]
        and cached.get("analysis_version") in ENERGY_CACHE_UPGRADE_FROM_VERSIONS
        and cached.get("energy_curve") is None
    ):
        return cached
    return None


def analyze_if_needed(path: Path, cache: dict, rb_index: dict | None = None) -> dict:
    from analyze import ANALYSIS_VERSION, analyze_track, analyze_track_energy

    key = str(path.resolve())
    cached = cached_analysis(path, cache)
    if cached:
        return apply_rekordbox(cached, path, rb_index)
    sig = file_sig(path)
    upgrade = cached_analysis_for_energy_upgrade(path, cache)
    if upgrade:
        energy = analyze_track_energy(path, upgrade.get("bpm"))
        entry = apply_rekordbox(
            {**upgrade, **sig, **energy, "analysis_version": ANALYSIS_VERSION},
            path,
            rb_index,
        )
        cache[key] = entry
        return entry

    result = apply_rekordbox(analyze_track(path), path, rb_index)
    entry = {**sig, **result}
    cache[key] = entry
    return entry


def _analyze_worker(path_str: str, rb_index: dict | None = None) -> tuple[str, dict, dict]:
    from analyze import analyze_track

    path = Path(path_str)
    sig = file_sig(path)
    result = apply_rekordbox(analyze_track(path), path, rb_index)
    return path_str, sig, result


def _energy_upgrade_worker(
    path_str: str, cached: dict, rb_index: dict | None = None
) -> tuple[str, dict, dict]:
    from analyze import ANALYSIS_VERSION, analyze_track_energy

    path = Path(path_str)
    sig = file_sig(path)
    result = apply_rekordbox(
        {**cached, **analyze_track_energy(path, cached.get("bpm")), "analysis_version": ANALYSIS_VERSION},
        path,
        rb_index,
    )
    return path_str, sig, result


def build_edges(tracks: list[dict], min_score: float = 0.55, max_edges: int = 12000) -> list[dict]:
    edges: list[dict] = []
    for i, a in enumerate(tracks):
        if a.get("bpm") is None or not a.get("key"):
            continue
        for b in tracks[i + 1 :]:
            if b.get("bpm") is None or not b.get("key"):
                continue
            score = mix_score(a["key"], b["key"], a["bpm"], b["bpm"])
            if score >= min_score:
                edges.append(
                    {
                        "source": a["id"],
                        "target": b["id"],
                        "score": round(score, 3),
                    }
                )
    edges.sort(key=lambda e: e["score"], reverse=True)
    return edges[:max_edges]


def track_record(path: Path, analysis: dict) -> dict:
    path_str = str(path.resolve())
    meta = classify_path(path)
    artist, title = parse_filename(path)
    return {
        "id": track_id(path),
        "path": path_str,
        "artist": artist,
        "title": title,
        "source": meta["source"],
        "genre": meta["genre"],
        "batch": meta["batch"],
        "duration_sec": analysis.get("duration_sec"),
        "bpm": analysis.get("bpm"),
        "bpm_raw": analysis.get("bpm_raw"),
        "bpm_octave_corrected": analysis.get("bpm_octave_corrected", False),
        "bpm_source": analysis.get("bpm_source"),
        "bpm_confidence": analysis.get("bpm_confidence"),
        "key": analysis.get("key"),
        "key_source": analysis.get("key_source"),
        "energy": analysis.get("energy", 0.5),
        "energy_auto": analysis.get("energy_auto", analysis.get("energy", 0.5)),
        "energy_effective": analysis.get("energy_effective", analysis.get("energy", 0.5)),
        "energy_main": analysis.get("energy_main"),
        "energy_avg": analysis.get("energy_avg"),
        "energy_peak": analysis.get("energy_peak"),
        "energy_intro": analysis.get("energy_intro"),
        "energy_outro": analysis.get("energy_outro"),
        "energy_confidence": analysis.get("energy_confidence"),
        "energy_curve": analysis.get("energy_curve"),
        "vocals": analysis.get("vocals"),
        "vocals_confidence": analysis.get("vocals_confidence"),
        "analysis_error": analysis.get("analysis_error"),
        **waveform_track_fields(analysis),
    }


def scan_sequential(files: list[Path], cache: dict, rb_index: dict | None = None) -> list[dict]:
    tracks: list[dict] = []
    for idx, path in enumerate(files, 1):
        analysis = analyze_if_needed(path, cache, rb_index)
        if idx % 25 == 0 or idx == len(files):
            print(f"  analyzed {idx}/{len(files)}")
        tracks.append(track_record(path, analysis))
    save_cache(cache)
    return tracks


def scan_parallel(
    files: list[Path], cache: dict, workers: int, rb_index: dict | None = None
) -> list[dict]:
    pending: list[str] = []
    upgrade_pending: list[tuple[str, dict]] = []
    results: dict[str, dict] = {}

    for path in files:
        path_str = str(path.resolve())
        cached = cached_analysis(path, cache)
        if cached:
            results[path_str] = apply_rekordbox(cached, path, rb_index)
        elif upgrade := cached_analysis_for_energy_upgrade(path, cache):
            upgrade_pending.append((path_str, upgrade))
        else:
            pending.append(path_str)

    done = len(results)
    if done:
        print(f"  cached {done}/{len(files)}")
    work_count = len(pending) + len(upgrade_pending)
    if work_count:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(_analyze_worker, p, rb_index) for p in pending]
            futures.extend(
                pool.submit(_energy_upgrade_worker, p, c, rb_index) for p, c in upgrade_pending
            )
            for future in as_completed(futures):
                path_str, sig, result = future.result()
                entry = {**sig, **result}
                cache[path_str] = entry
                results[path_str] = entry
                done += 1
                if done % 25 == 0 or done == len(files):
                    print(f"  analyzed {done}/{len(files)}")
                if done % PARALLEL_CACHE_SAVE_EVERY == 0 or done == len(files):
                    save_cache(cache)
    save_cache(cache)
    return [track_record(path, results[str(path.resolve())]) for path in files]


def library_metadata() -> dict:
    tracks_list = [str(p) for p in TRACKS_ROOTS]
    curate_list = [str(p) for p in CURATE_ROOTS]
    return {
        "tracks_root": tracks_list[0] if tracks_list else "",
        "curate_root": curate_list[0] if curate_list else "",
        "tracks_roots": tracks_list,
        "curate_roots": curate_list,
    }


def scan(
    limit: int | None = None,
    workers: int = 4,
    skip_edges: bool = False,
    tracks_root_paths: list[Path] | None = None,
    curate_root_paths: list[Path] | None = None,
    excluded_paths: list[str] | None = None,
) -> dict:
    warnings = configure_scan(tracks_root_paths, curate_root_paths, excluded_paths)
    for warning in warnings:
        print(f"  warning: {warning}")

    if not SCAN_ROOTS:
        print("No scan roots configured.")
        library = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            **library_metadata(),
            "track_count": 0,
            "tracks": [],
            "edges": [],
        }
        LIBRARY_PATH.write_text(json.dumps(library, indent=2))
        print(f"Wrote {LIBRARY_PATH} (0 tracks)")
        return library

    files = discover_files(limit=limit)
    print(f"Found {len(files)} audio files")
    if EXCLUDED_PATHS:
        print(f"  excluded paths: {len(EXCLUDED_PATHS)}")

    rb_index = load_rekordbox_index()
    if rb_index:
        print(f"  rekordbox: {len(rb_index['by_path'])} analyzed tracks")
    else:
        print("  rekordbox: not used")

    cache = load_cache()
    if workers > 1 and len(files) > 1:
        try:
            tracks = scan_parallel(files, cache, workers, rb_index)
        except BrokenProcessPool:
            print("Parallel scan worker crashed; retrying with one worker.")
            tracks = scan_sequential(files, cache, rb_index)
    else:
        tracks = scan_sequential(files, cache, rb_index)

    tracks.sort(key=lambda t: (t["source"], t["genre"], t["artist"].lower(), t["title"].lower()))

    library = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        **library_metadata(),
        "track_count": len(tracks),
        "tracks": tracks,
        "edges": [] if skip_edges else build_edges(tracks),
    }
    LIBRARY_PATH.write_text(json.dumps(library, indent=2))
    print(f"Wrote {LIBRARY_PATH} ({len(tracks)} tracks, {len(library['edges'])} edges)")
    return library


def main() -> None:
    parser = argparse.ArgumentParser(description="Scan DJ library for Seta")
    parser.add_argument("--limit", type=int, default=None, help="Only scan first N files")
    parser.add_argument("--workers", type=int, default=max(2, os.cpu_count() or 4) - 1)
    parser.add_argument("--skip-edges", action="store_true")
    parser.add_argument(
        "--explicit-roots",
        action="store_true",
        help="Use only --tracks-root / --curate-root args; do not fall back to config.py defaults",
    )
    parser.add_argument(
        "--tracks-root",
        action="append",
        default=[],
        dest="tracks_roots",
        metavar="PATH",
        help="Curated library folder (repeatable)",
    )
    parser.add_argument(
        "--curate-root",
        action="append",
        default=[],
        dest="curate_roots",
        metavar="PATH",
        help="Uncurated / intake folder (repeatable)",
    )
    parser.add_argument(
        "--exclude-path",
        action="append",
        default=[],
        dest="exclude_paths",
        metavar="PATH",
        help="Skip this absolute audio path (repeatable)",
    )
    args = parser.parse_args()

    if args.explicit_roots:
        tracks_paths = [Path(p) for p in args.tracks_roots]
        curate_paths = [Path(p) for p in args.curate_roots]
    else:
        tracks_paths = [Path(p) for p in args.tracks_roots] if args.tracks_roots else None
        curate_paths = [Path(p) for p in args.curate_roots] if args.curate_roots else None

    scan(
        limit=args.limit,
        workers=args.workers,
        skip_edges=args.skip_edges,
        tracks_root_paths=tracks_paths,
        curate_root_paths=curate_paths,
        excluded_paths=args.exclude_paths or None,
    )


# Default configuration on import for tests and legacy callers.
configure_scan()

if __name__ == "__main__":
    main()
