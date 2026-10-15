"""Arrangements from the Arrange page, saved on this Mac (not only in one browser).

`arrangements.json` holds {"sets": {playlist id: [items]}, "stamps": {playlist id: ms since epoch}};
the page keeps whichever copy (this file or its browser's) changed last. Every save first appends
the set's previous version to `arrangements-history.jsonl`, so an overwrite (another browser, a second person
on the home network) can be recovered by hand. These files are git-ignored personal data.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
STORE_PATH = APP_DIR / "arrangements.json"
HISTORY_PATH = APP_DIR / "arrangements-history.jsonl"
HISTORY_MAX_BYTES = 20 * 1024 * 1024  # trimmed to the newest half when it grows past this
PLAYLIST_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
MAX_ITEMS = 2000

_LOCK = threading.Lock()


def load(path: Path = STORE_PATH) -> dict:
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        data = {}
    sets = data.get("sets") if isinstance(data.get("sets"), dict) else {}
    stamps = data.get("stamps") if isinstance(data.get("stamps"), dict) else {}
    return {"sets": sets, "stamps": stamps}


def save_set(playlist_id: str, items: list, at: float | None = None, *, path: Path = STORE_PATH, history: Path = HISTORY_PATH) -> None:
    """Replace one playlist's arrangement, keeping the old one in the history file."""
    if not PLAYLIST_ID.match(playlist_id):
        raise ValueError("bad playlist id")
    if not isinstance(items, list) or len(items) > MAX_ITEMS or not all(isinstance(i, dict) and "id" in i for i in items):
        raise ValueError("items must be a list of {id, ...}")
    with _LOCK:
        data = load(path)
        old = data["sets"].get(playlist_id)
        if old == items:
            return
        if old is not None:
            with history.open("a") as f:
                f.write(json.dumps({"at": time.time(), "playlist": playlist_id, "items": old}) + "\n")
            _trim(history)
        data["sets"][playlist_id] = items
        data["stamps"][playlist_id] = at if isinstance(at, (int, float)) else time.time() * 1000
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data))
        os.replace(tmp, path)


def _trim(history: Path) -> None:
    if history.stat().st_size <= HISTORY_MAX_BYTES:
        return
    lines = history.read_text().splitlines(keepends=True)
    history.write_text("".join(lines[len(lines) // 2 :]))
