"""Rekordbox's own waveform preview, beat grid and cues, so Seta draws a track the way Rekordbox does.

The color preview comes from the PWV4 tag in each track's ANLZ0000.EXT (1,200 columns of
6 bytes), downbeats from the PQTZ beat grid in ANLZ0000.DAT, phrases from the PSSI phrase analysis,
vocals from the PVDI tag in ANLZ0000.2EX (rekordbox's AI vocal detection); cues come from master.db. Read-only: nothing here writes Rekordbox files.
Tag layout: https://djl-analysis.deepsymmetry.org/rekordbox-export-analysis/anlz.html
"""

from __future__ import annotations

import base64
import struct
import threading
from pathlib import Path

from pyrekordbox.anlz import AnlzFile
from pyrekordbox.db6.tables import DjmdCue

import rb_tags
from rekordbox import lookup_rekordbox, rekordbox_db_path

PREVIEW_TAG = b"PWV4"
PREVIEW_ENTRY_BYTES = 6
BEAT_GRID_TAG = b"PQTZ"
BEAT_ENTRY_BYTES = 8  # beat number (u16), tempo x100 (u16), time ms (u32)
VOCAL_TAG = b"PVDI"  # header: hop (u32), sample rate (u16) + 1 (u16), count (u32); body: 1 byte per hop, 0-4
# djmdCue.Kind -> hot cue letter; Kind 0 is a memory cue (Kind 4 only ever holds loops).
HOT_CUE_LETTERS = {1: "A", 2: "B", 3: "C", 5: "D", 6: "E", 7: "F", 8: "G", 9: "H"}

_LOCK = threading.Lock()
_CACHE: dict = {"stamp": None, "tracks": {}, "paths": None, "waves": {}}


def _find_tag(data: bytes, code: bytes) -> tuple[int, int, int] | None:
    """(position, header length, tag length) of the first `code` tag in an ANLZ file's bytes."""
    if len(data) < 12 or data[:4] != b"PMAI":
        return None
    pos = struct.unpack(">I", data[4:8])[0]
    while pos + 12 <= len(data):
        len_header, len_tag = struct.unpack(">II", data[pos + 4 : pos + 12])
        if len_tag < 12 or pos + len_tag > len(data):
            return None
        if data[pos : pos + 4] == code:
            return pos, len_header, len_tag
        pos += len_tag
    return None


def _read(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError:
        return b""


def read_color_preview(ext_path: Path) -> bytes | None:
    """The raw PWV4 entries, or None when the file or tag is missing or malformed."""
    data = _read(ext_path)
    found = _find_tag(data, PREVIEW_TAG)
    if not found:
        return None
    pos, len_header, len_tag = found
    if len_header < 20:
        return None
    entry_bytes, entries = struct.unpack(">II", data[pos + 12 : pos + 20])
    body = data[pos + len_header : pos + len_tag]
    size = entries * PREVIEW_ENTRY_BYTES
    if entry_bytes != PREVIEW_ENTRY_BYTES or len(body) < size:
        return None
    return body[:size]


def read_beats(dat_path: Path) -> list[tuple[int, int]]:
    """(beat number in bar, ms) for every beat of the PQTZ beat grid, or []."""
    data = _read(dat_path)
    found = _find_tag(data, BEAT_GRID_TAG)
    if not found:
        return []
    pos, len_header, len_tag = found
    if len_header < 24:
        return []
    (count,) = struct.unpack(">I", data[pos + 20 : pos + 24])
    body = data[pos + len_header : pos + len_tag]
    beats = []
    for i in range(min(count, len(body) // BEAT_ENTRY_BYTES)):
        beat, _tempo, ms = struct.unpack(">HHI", body[i * BEAT_ENTRY_BYTES : (i + 1) * BEAT_ENTRY_BYTES])
        beats.append((beat, ms))
    return beats


def read_vocals(two_ex_path: Path) -> dict | None:
    """Rekordbox's vocal detection: {"step_ms", "levels" (base64, one byte 0-4 per step)}, or None.

    Reverse-engineered from rekordbox 7 files: a 1024-sample hop at 22,050 Hz (46.4 ms); the level
    is how sure the model is that a voice sings or speaks there (0 = none, 4 = clearly).
    """
    data = _read(two_ex_path)
    found = _find_tag(data, VOCAL_TAG)
    if not found:
        return None
    pos, len_header, len_tag = found
    if len_header < 24:
        return None
    hop, rate, _, count = struct.unpack(">IHHI", data[pos + 12 : pos + 24])
    body = data[pos + len_header : pos + len_tag][:count]
    if not hop or not rate or not body:
        return None
    return {"step_ms": hop / rate * 1000, "levels": base64.b64encode(body).decode("ascii")}


def read_downbeats(dat_path: Path) -> list[int]:
    """Milliseconds of every downbeat (beat 1 of a bar) from the PQTZ beat grid, or []."""
    return [ms for beat, ms in read_beats(dat_path) if beat == 1]


def read_phrases(ext_path: Path, beats: list[tuple[int, int]]) -> list[dict]:
    """Rekordbox's phrase analysis (PSSI) as [{ms, kind, mood}], or [] when the track has none.

    PSSI is masked in Rekordbox 6+; pyrekordbox unmasks it. Phrase `beat` counts from 1 in the beat grid.
    """
    if not beats or not ext_path.exists():
        return []
    try:
        tag = AnlzFile.parse_file(str(ext_path)).get_tag("PSSI")
    except Exception:  # noqa: BLE001 - a few EXT files fail pyrekordbox's parser; no phrases then
        return []
    if tag is None:
        return []
    content = tag.content
    phrases = []
    for entry in content.entries:
        index = int(entry.beat) - 1
        if 0 <= index < len(beats):
            phrases.append({"ms": beats[index][1], "kind": int(entry.kind), "mood": int(content.mood)})
    return phrases


def _cue(row) -> dict:
    end = row.OutMsec if row.OutMsec and row.OutMsec > 0 else None
    return {"ms": row.InMsec or 0, "end_ms": end, "hot": HOT_CUE_LETTERS.get(row.Kind), "name": row.Comment or ""}


def _stamp() -> tuple:
    db = rekordbox_db_path()
    wal = db.with_name(db.name + "-wal")
    return tuple(p.stat().st_mtime if p.exists() else 0 for p in (db, wal))


def _index() -> dict:
    """Per-track ANLZ path, duration and cues, rebuilt when master.db changes."""
    with _LOCK:
        stamp = _stamp()
        if _CACHE["stamp"] == stamp:
            return _CACHE
        db = rb_tags._open_db()
        try:
            tracks: dict[str, dict] = {}
            by_path: dict[str, dict] = {}
            by_stem: dict[str, list[dict]] = {}
            for content in db.get_content():
                cid = str(content.ID)
                tracks[cid] = {
                    "anlz": content.AnalysisDataPath,
                    "duration_ms": (content.Length or 0) * 1000,
                    "cues": [],
                }
                if content.FolderPath:
                    try:
                        path = Path(content.FolderPath).expanduser().resolve()
                    except OSError:
                        continue
                    entry = {"id": cid, "path": str(path), "size": content.FileSize, "ext": path.suffix.lower()}
                    by_path[str(path)] = entry
                    by_stem.setdefault(path.stem.lower(), []).append(entry)
            for row in db.query(DjmdCue).filter(DjmdCue.rb_local_deleted == 0).order_by(DjmdCue.InMsec):
                track = tracks.get(str(row.ContentID))
                if track is not None:
                    track["cues"].append(_cue(row))
        finally:
            db.close()
        _CACHE.update(stamp=stamp, tracks=tracks, paths={"by_path": by_path, "by_stem": by_stem}, waves={})
        return _CACHE


def waveform(content_id: str) -> dict | None:
    """Preview bytes (base64), duration, cues, downbeats and phrases for one track, or None.

    Cached until master.db changes: parsing the phrase analysis takes ~40 ms per track.
    """
    cache = _index()
    key = str(content_id)
    if key not in cache["waves"]:
        cache["waves"][key] = _waveform(key)
    return cache["waves"][key]


def _waveform(content_id: str) -> dict | None:
    track = _index()["tracks"].get(str(content_id))
    if not track or not track["anlz"]:
        return None
    dat = rekordbox_db_path().parent / "share" / track["anlz"].lstrip("/")
    preview = read_color_preview(dat.with_suffix(".EXT"))
    if preview is None:
        return None
    beats = read_beats(dat)
    return {
        "id": str(content_id),
        "preview": base64.b64encode(preview).decode("ascii"),
        "columns": len(preview) // PREVIEW_ENTRY_BYTES,
        "duration_ms": track["duration_ms"],
        "cues": track["cues"],
        "downbeats": [ms for beat, ms in beats if beat == 1],
        "beats": [ms for _beat, ms in beats],
        "phrases": read_phrases(dat.with_suffix(".EXT"), beats),
        "vocals": read_vocals(dat.with_suffix(".2EX")),
    }


def content_id_for_path(path: Path) -> str | None:
    """The Rekordbox track for a library file, matched the same way as BPM and key."""
    hit = lookup_rekordbox(path, _index()["paths"])
    return hit["id"] if hit else None
