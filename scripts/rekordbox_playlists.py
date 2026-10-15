#!/usr/bin/env python3
"""Export Rekordbox playlist names and file paths as JSON for Seta Mac."""

from __future__ import annotations

import contextlib
import io
import json
import logging
import sys

SKIP_IDS = {"100000", "200000"}
SKIP_NAMES = {"CUE Analysis Playlist"}


def _quiet_pyrekordbox() -> None:
    logging.disable(logging.WARNING)
    for name in ("pyrekordbox", "pyrekordbox.db6.database"):
        logging.getLogger(name).setLevel(logging.ERROR)


def main() -> int:
    _quiet_pyrekordbox()

    try:
        from pyrekordbox import Rekordbox6Database
        from pyrekordbox.db6.tables import DjmdSongPlaylist
    except ImportError:
        print("pyrekordbox is not installed in this environment.", file=sys.stderr)
        return 2

    try:
        capture = io.StringIO()
        with contextlib.redirect_stdout(capture):
            db = Rekordbox6Database()
            playlists = []
            for playlist in db.get_playlist():
                if str(playlist.ID) in SKIP_IDS or playlist.Name in SKIP_NAMES:
                    continue
                songs = (
                    db.query(DjmdSongPlaylist)
                    .filter(DjmdSongPlaylist.PlaylistID == playlist.ID)
                    .order_by(DjmdSongPlaylist.TrackNo)
                    .all()
                )
                paths = []
                for song in songs:
                    content = song.Content
                    folder_path = getattr(content, "FolderPath", None) if content else None
                    if folder_path:
                        paths.append(folder_path)
                if paths:
                    playlists.append({"name": playlist.Name, "paths": paths})
    except Exception as exc:  # noqa: BLE001
        print(str(exc), file=sys.stderr)
        return 1

    json.dump({"playlists": playlists}, sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
