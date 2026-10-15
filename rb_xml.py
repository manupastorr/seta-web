"""A rekordbox XML for an arranged set: the playlist order, plus the mix points as memory cues.

Each track keeps its current cues (hot cues, memory cues, loops, with their comments) and gets
Seta's mix points ("Seta mix in", "Seta bass swap", ...) as extra memory cues, so importing the
file in rekordbox adds the mix points whether rekordbox merges cues or replaces them.
Older "Seta ..." cues are left out, so a new export replaces them.
Read-only: this only writes a file to download; nothing touches master.db.
"""

from __future__ import annotations

from urllib.parse import quote
from xml.sax.saxutils import quoteattr

SETA_PREFIX = "Seta "
HOT_NUM = {letter: n for n, letter in enumerate("ABCDEFGH")}
STARS = {0: 0, 1: 51, 2: 102, 3: 153, 4: 204, 5: 255}  # rekordbox XML rating per star count
KINDS = {".wav": "WAV File", ".mp3": "MP3 File", ".aif": "AIFF File", ".aiff": "AIFF File", ".flac": "FLAC File", ".m4a": "M4A File"}
SAME_SPOT_MS = 50  # a mix point this close to an existing memory cue is not added again


def _mark(ms: float, *, name: str = "", end_ms: float | None = None, num: int = -1) -> str:
    attrs = f"Name={quoteattr(name)} Type=\"{4 if end_ms else 0}\" Start=\"{ms / 1000:.3f}\""
    if end_ms:
        attrs += f' End="{end_ms / 1000:.3f}"'
    return f'      <POSITION_MARK {attrs} Num="{num}"/>'


def _marks(existing: list[dict], mix_points: list[dict]) -> list[str]:
    kept = [c for c in existing if not (c.get("name") or "").startswith(SETA_PREFIX)]
    marks = [_mark(c["ms"], name=c.get("name") or "", end_ms=c.get("end_ms"), num=HOT_NUM.get(c.get("hot"), -1)) for c in kept]
    memory = [c["ms"] for c in kept if not c.get("hot")]
    for point in sorted(mix_points, key=lambda p: p["ms"]):
        if all(abs(point["ms"] - ms) > SAME_SPOT_MS for ms in memory):
            marks.append(_mark(point["ms"], name=point["name"]))
            memory.append(point["ms"])
    return marks


def build(playlist_name: str, tracks: list[dict]) -> str:
    """`tracks` in set order: {path, title, artist, genre, bpm, key, rating, length_s, cues, mix_points}."""
    entries = []
    for n, t in enumerate(tracks, 1):
        location = "file://localhost" + quote(t["path"], safe="/")
        suffix = t["path"][t["path"].rfind(".") :].lower() if "." in t["path"] else ""
        head = (
            f'    <TRACK TrackID="{n}" Name={quoteattr(t.get("title") or "")} Artist={quoteattr(t.get("artist") or "")} '
            f'Genre={quoteattr(t.get("genre") or "")} Kind={quoteattr(KINDS.get(suffix, ""))} TotalTime="{t.get("length_s") or 0}" '
            f'AverageBpm="{(t.get("bpm") or 0):.2f}" Tonality={quoteattr(t.get("key") or "")} '
            f'Rating="{STARS.get(t.get("rating") or 0, 0)}" Location={quoteattr(location)}>'
        )
        entries.append("\n".join([head, *_marks(t.get("cues") or [], t.get("mix_points") or []), "    </TRACK>"]))
    keys = "\n".join(f'        <TRACK Key="{n}"/>' for n in range(1, len(entries) + 1))
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n<DJ_PLAYLISTS Version="1.0.0">\n'
        '  <PRODUCT Name="rekordbox" Version="7.0.0" Company="AlphaTheta"/>\n'
        f'  <COLLECTION Entries="{len(entries)}">\n' + "\n".join(entries) + "\n  </COLLECTION>\n"
        '  <PLAYLISTS>\n    <NODE Type="0" Name="ROOT" Count="1">\n'
        f'      <NODE Name={quoteattr(playlist_name)} Type="1" KeyType="0" Entries="{len(entries)}">\n'
        + keys + "\n      </NODE>\n    </NODE>\n  </PLAYLISTS>\n</DJ_PLAYLISTS>\n"
    )
