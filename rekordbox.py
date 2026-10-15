"""Read BPM and Camelot key from the local Rekordbox library when available."""

from __future__ import annotations

import os
import re
from pathlib import Path

_CAMELOT_RE = re.compile(r"^(\d{1,2})([AB])$", re.IGNORECASE)

_STANDARD_TO_CAMELOT: dict[str, str] = {
    "Abm": "1A",
    "G#m": "1A",
    "Ebm": "2A",
    "D#m": "2A",
    "Bbm": "3A",
    "A#m": "3A",
    "Fm": "4A",
    "Cm": "5A",
    "Gm": "6A",
    "Dm": "7A",
    "Am": "8A",
    "Em": "9A",
    "Bm": "10A",
    "F#m": "11A",
    "Gbm": "11A",
    "Dbm": "12A",
    "C#m": "12A",
    "B": "1B",
    "Gb": "2B",
    "F#": "2B",
    "Db": "3B",
    "C#": "3B",
    "Ab": "4B",
    "G#": "4B",
    "Eb": "5B",
    "D#": "5B",
    "Bb": "6B",
    "A#": "6B",
    "F": "7B",
    "C": "8B",
    "G": "9B",
    "D": "10B",
    "A": "11B",
    "E": "12B",
}

DEFAULT_RB_DB = Path.home() / "Library/Pioneer/rekordbox/master.db"


def use_rekordbox() -> bool:
    return os.environ.get("SETA_USE_REKORDBOX", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def rekordbox_db_path() -> Path:
    raw = os.environ.get("SETA_REKORDBOX_DB")
    if raw:
        return Path(raw).expanduser().resolve()
    return DEFAULT_RB_DB


def key_to_camelot(raw: str | None) -> str | None:
    if not raw:
        return None
    text = raw.strip()
    if not text or text == "0":
        return None
    match = _CAMELOT_RE.match(text)
    if match:
        return f"{int(match.group(1))}{match.group(2).upper()}"
    return _STANDARD_TO_CAMELOT.get(text) or _STANDARD_TO_CAMELOT.get(text.title())


def rekordbox_bpm(raw_bpm: int | float | None) -> float | None:
    if raw_bpm is None:
        return None
    value = float(raw_bpm) / 100.0
    if value <= 0:
        return None
    return round(value, 2)


def _entry(path: Path, bpm: float | None, key: str | None, size: int | None) -> dict:
    return {
        "path": str(path),
        "bpm": bpm,
        "key": key,
        "size": size,
        "ext": path.suffix.lower(),
    }


def load_rekordbox_index(db_path: Path | None = None) -> dict | None:
    """Build a Rekordbox lookup index, or None when Rekordbox integration is disabled."""
    if not use_rekordbox():
        return None

    path = db_path or rekordbox_db_path()
    if not path.exists():
        return None

    try:
        from pyrekordbox import Rekordbox6Database
    except ImportError:
        return None

    try:
        db = Rekordbox6Database(path=str(path))
        keys = {key.ID: key_to_camelot(key.ScaleName) for key in db.get_key()}
    except Exception:
        return None

    by_path: dict[str, dict] = {}
    by_stem: dict[str, list[dict]] = {}

    for content in db.get_content():
        folder_path = content.FolderPath
        if not folder_path:
            continue
        file_path = Path(folder_path).expanduser()
        if not file_path.is_absolute():
            continue
        try:
            resolved = file_path.resolve()
        except OSError:
            continue

        bpm = rekordbox_bpm(content.BPM)
        key = keys.get(content.KeyID) if content.KeyID not in (None, "0", 0) else None
        if key is None and content.KeyName:
            key = key_to_camelot(content.KeyName)
        if bpm is None and not key:
            continue

        entry = _entry(resolved, bpm, key, content.FileSize)
        by_path[str(resolved)] = entry
        by_stem.setdefault(resolved.stem.lower(), []).append(entry)

    if not by_path:
        return None
    return {"by_path": by_path, "by_stem": by_stem}


def lookup_rekordbox(path: Path, index: dict | None) -> dict | None:
    if not index:
        return None

    resolved = path.resolve()
    hit = index["by_path"].get(str(resolved))
    if hit:
        return hit

    try:
        size = resolved.stat().st_size
    except OSError:
        size = None

    candidates = index["by_stem"].get(resolved.stem.lower(), [])
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]

    if size is not None:
        size_matches = [entry for entry in candidates if entry.get("size") == size]
        if len(size_matches) == 1:
            return size_matches[0]

    ext = resolved.suffix.lower()
    ext_matches = [entry for entry in candidates if entry.get("ext") == ext]
    if len(ext_matches) == 1:
        return ext_matches[0]

    keyed = [entry for entry in candidates if entry.get("key")]
    if len(keyed) == 1:
        return keyed[0]
    return None


def apply_rekordbox(analysis: dict, path: Path, index: dict | None) -> dict:
    hit = lookup_rekordbox(path, index)
    if not hit:
        return analysis

    merged = dict(analysis)
    if hit.get("bpm") is not None:
        merged["bpm"] = hit["bpm"]
        merged["bpm_raw"] = hit["bpm"]
        merged["bpm_octave_corrected"] = False
        merged["bpm_source"] = "rekordbox"
        merged["bpm_confidence"] = 1.0
    if hit.get("key"):
        merged["key"] = hit["key"]
        merged["key_source"] = "rekordbox"
    return merged
