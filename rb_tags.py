"""Read and write Rekordbox energy (stars) and My Tag groups (Function, Source, State) for the Tags page.

Edits wait in `rb_pending.json` and are written to master.db only while
Rekordbox is closed, after a backup copy of the database.
"""

from __future__ import annotations

import datetime
import json
import logging
import shutil
import threading
from pathlib import Path
from uuid import uuid4

# Imported once at load: lazy imports race when Flask serves two requests at once.
from pyrekordbox import Rekordbox6Database
from pyrekordbox.db6.tables import (
    DjmdContent,
    DjmdMyTag,
    DjmdPlaylist,
    DjmdSongMyTag,
    DjmdSongPlaylist,
)
from pyrekordbox.utils import get_rekordbox_pid

from rekordbox import key_to_camelot, rekordbox_bpm, rekordbox_db_path

APP_DIR = Path(__file__).resolve().parent
PENDING_PATH = APP_DIR / "rb_pending.json"
BACKUP_DIR = APP_DIR / "rb_backups"
KEEP_BACKUPS = 5
# Editable My Tag groups; the track field is the lowercased name.
TAG_GROUPS = ("Function", "Source", "State")
# Groups that allow several tags per track (value is a list); the rest are one choice.
MULTI_TAG_GROUPS = {"state"}
SKIP_PLAYLIST_IDS = {"100000", "200000"}  # Rekordbox internal / CUE Analysis
_PENDING_LOCK = threading.Lock()


def _quiet() -> None:
    logging.getLogger("pyrekordbox").setLevel(logging.ERROR)


def rekordbox_running() -> bool:
    return bool(get_rekordbox_pid())


def _open_db(db_path: Path | None = None):
    _quiet()
    return Rekordbox6Database(path=str(db_path or rekordbox_db_path()))


def _playlists(db) -> list[dict]:
    """Rekordbox playlist tree in sidebar order; smart playlists are evaluated now."""
    out = []
    for pl in db.get_playlist().order_by(DjmdPlaylist.Seq):
        if str(pl.ID) in SKIP_PLAYLIST_IDS:
            continue
        item = {
            "id": str(pl.ID),
            "parent": str(pl.ParentID),
            "name": pl.Name,
            "folder": bool(pl.is_folder),
            "smart": bool(pl.is_smart_playlist),
            "track_ids": [],
        }
        if pl.is_smart_playlist:
            try:
                rows = db.get_playlist_contents(pl, DjmdContent.ID)
                item["track_ids"] = [str(cid) for (cid,) in rows]
            except Exception:  # noqa: BLE001 - a smart rule pyrekordbox cannot parse
                item["error"] = True
        elif not pl.is_folder:
            rows = (
                db.query(DjmdSongPlaylist.ContentID)
                .filter(DjmdSongPlaylist.PlaylistID == pl.ID)
                .order_by(DjmdSongPlaylist.TrackNo)
            )
            item["track_ids"] = [str(cid) for (cid,) in rows]
        out.append(item)
    return out


def _tag_tree(db) -> dict[str, dict[str, str]]:
    """Every My Tag group as field -> {child tag ID -> name}, in Rekordbox order."""
    tree = {}
    for parent in db.query(DjmdMyTag).filter_by(ParentID="root").order_by(DjmdMyTag.Seq):
        children = db.query(DjmdMyTag).filter_by(ParentID=parent.ID).order_by(DjmdMyTag.Seq)
        tree[parent.Name.strip().lower()] = {str(tag.ID): tag.Name.strip() for tag in children}
    return tree


def _group_tags(db) -> dict[str, dict[str, str]]:
    """The editable TAG_GROUPS subset of `_tag_tree`."""
    tree = _tag_tree(db)
    return {name.lower(): tree.get(name.lower(), {}) for name in TAG_GROUPS}


def load_pending() -> dict[str, dict]:
    if not PENDING_PATH.exists():
        return {}
    return json.loads(PENDING_PATH.read_text())


def save_pending(pending: dict[str, dict]) -> None:
    if pending:
        PENDING_PATH.write_text(json.dumps(pending, indent=2))
    elif PENDING_PATH.exists():
        PENDING_PATH.unlink()


def queue_edit(content_id: str, field: str, value) -> dict[str, dict]:
    """Queue one edit: `energy` (0-5), a one-choice group (tag name or None) or a multi group (list)."""
    if field == "energy":
        value = int(value)
        if not 0 <= value <= 5:
            raise ValueError("energy must be 0-5")
    elif field not in {name.lower() for name in TAG_GROUPS}:
        raise ValueError(f"unknown field {field}")
    elif field in MULTI_TAG_GROUPS and not isinstance(value, list):
        raise ValueError(f"{field} takes a list of tags")
    with _PENDING_LOCK:
        pending = load_pending()
        pending.setdefault(str(content_id), {})[field] = value
        save_pending(pending)
    return pending


def _field_value(field: str, current: dict[str, list[str]]):
    names = current.get(field, [])
    return names if field in MULTI_TAG_GROUPS else (names or [None])[0]


def load_tracks(db_path: Path | None = None) -> dict:
    """All Rekordbox tracks with stars and group tags (pending edits applied) plus playlists."""
    db = _open_db(db_path)
    try:
        tree = _tag_tree(db)
        groups = {name.lower(): tree.get(name.lower(), {}) for name in TAG_GROUPS}
        field_by_tag = {tag_id: field for field, tags in tree.items() for tag_id in tags}
        names = {tag_id: name for tags in tree.values() for tag_id, name in tags.items()}
        tags_by_content: dict[str, dict[str, list[str]]] = {}
        for row in db.query(DjmdSongMyTag).filter(DjmdSongMyTag.MyTagID.in_(names)):
            tag_id = str(row.MyTagID)
            tags_by_content.setdefault(str(row.ContentID), {}).setdefault(
                field_by_tag[tag_id], []
            ).append(names[tag_id])
        playlists = _playlists(db)
        keys = {key.ID: key_to_camelot(key.ScaleName) for key in db.get_key()}

        pending = load_pending()
        tracks = []
        for content in db.get_content():
            if not content.FolderPath:
                continue
            path = Path(content.FolderPath).expanduser()
            cid = str(content.ID)
            edit = pending.get(cid, {})
            current = tags_by_content.get(cid, {})
            tracks.append(
                {
                    "id": cid,
                    "title": content.Title or path.stem,
                    "artist": content.ArtistName or "",
                    "bpm": rekordbox_bpm(content.BPM),
                    "key": keys.get(content.KeyID),
                    "path": str(path),
                    "added": str(content.DateCreated or ""),
                    "energy": edit.get("energy", content.Rating or 0),
                    **{field: edit.get(field, _field_value(field, current)) for field in groups},
                    # Read-only groups, used for filtering.
                    "tags": {f: v for f, v in current.items() if f not in groups},
                    "pending": bool(edit),
                }
            )
    finally:
        db.close()
    tracks.sort(key=lambda t: t["added"], reverse=True)
    return {
        "groups": {field: list(tags.values()) for field, tags in groups.items()},
        "multi": sorted(MULTI_TAG_GROUPS),
        "filters": [
            {"field": field, "tags": list(tags.values())} for field, tags in tree.items() if tags
        ],
        "tracks": tracks,
        "playlists": playlists,
    }


def _backup(db_path: Path) -> Path:
    BACKUP_DIR.mkdir(exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    target = BACKUP_DIR / f"master-{stamp}.db"
    shutil.copy2(db_path, target)
    for old in sorted(BACKUP_DIR.glob("master-*.db"))[:-KEEP_BACKUPS]:
        old.unlink()
    return target


def snapshot_library(db_path: Path | None = None, *, keep: int = KEEP_BACKUPS, backup_dir: Path | None = None) -> Path:
    """Copy master.db with its -wal and -shm files (rekordbox's newest changes live in -wal) into
    rb_backups/library-<time>/, keeping the newest `keep` copies. To restore: quit rekordbox and
    copy the files back into its folder."""
    path = db_path or rekordbox_db_path()
    root = backup_dir or BACKUP_DIR
    target = root / f"library-{datetime.datetime.now():%Y%m%d-%H%M%S}"
    target.mkdir(parents=True, exist_ok=True)
    for suffix in ("", "-wal", "-shm"):
        part = path.with_name(path.name + suffix)
        if part.exists():
            shutil.copy2(part, target / part.name)
    for old in sorted(root.glob("library-*"))[:-keep]:
        shutil.rmtree(old)
    return target


def apply_pending(db_path: Path | None = None) -> dict:
    """Write queued edits into master.db. Refuses while Rekordbox is running."""
    pending = load_pending()
    if not pending:
        return {"applied": 0}
    if rekordbox_running():
        raise RuntimeError("Close Rekordbox first, then save.")

    path = db_path or rekordbox_db_path()
    backup = _backup(path)
    db = _open_db(path)
    try:
        groups = _group_tags(db)
        now = datetime.datetime.now()
        for cid, edit in pending.items():
            content = db.get_content(ID=cid)
            if content is None:
                continue
            if "energy" in edit:
                content.Rating = edit["energy"]
            for field, tags in groups.items():
                if field not in edit:
                    continue
                rows = db.query(DjmdSongMyTag).filter(
                    DjmdSongMyTag.ContentID == cid,
                    DjmdSongMyTag.MyTagID.in_(tags),
                )
                for row in rows:
                    db.delete(row)
                wanted = edit[field] if isinstance(edit[field], list) else [edit[field]]
                for tag_id in [i for i, name in tags.items() if name in wanted]:
                    db.add(
                        DjmdSongMyTag.create(
                            ID=str(uuid4()),
                            MyTagID=tag_id,
                            ContentID=cid,
                            UUID=str(uuid4()),
                            created_at=now,
                            updated_at=now,
                        )
                    )
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    save_pending({})
    return {"applied": len(pending), "backup": str(backup)}
