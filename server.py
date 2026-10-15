#!/usr/bin/env python3
"""Local server for the Seta UI and audio streaming."""

from __future__ import annotations

import datetime
import json
import mimetypes
import os
import shutil
import subprocess
import threading
from pathlib import Path
from urllib.parse import urlsplit

from flask import Flask, Response, abort, jsonify, redirect, request, send_from_directory

import arrange_store
import rb_tags
import rb_waveform
import rb_xml
from config import KEEP_EXPORTS, allowed_roots, arrange_only, host, port, rekordbox_xml_path, tracks_root

APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"
LIBRARY_PATH = APP_DIR / "library.json"

app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="/static")
TRACK_INDEX: dict[str, dict] = {}
LIBRARY_CACHE: dict | None = None
LIBRARY_MTIME: float | None = None
_SCAN_LOCK = threading.Lock()


def _library_mtime() -> float | None:
    if not LIBRARY_PATH.exists():
        return None
    return LIBRARY_PATH.stat().st_mtime


def load_library(*, force: bool = False) -> dict:
    global LIBRARY_CACHE, LIBRARY_MTIME
    mtime = _library_mtime()
    if LIBRARY_CACHE is not None and not force and mtime == LIBRARY_MTIME:
        return LIBRARY_CACHE
    if not LIBRARY_PATH.exists():
        LIBRARY_CACHE = {"tracks": [], "edges": [], "track_count": 0}
    else:
        LIBRARY_CACHE = json.loads(LIBRARY_PATH.read_text())
    LIBRARY_MTIME = mtime
    TRACK_INDEX.clear()
    for track in LIBRARY_CACHE.get("tracks", []):
        TRACK_INDEX[track["id"]] = track
    return LIBRARY_CACHE


def allowed_path(path: Path) -> bool:
    resolved = path.resolve()
    return any(resolved == root or resolved.is_relative_to(root) for root in allowed_roots())


@app.get("/")
def index() -> Response:
    return send_from_directory(STATIC_DIR, "index.html")


@app.get("/api/library")
def api_library() -> Response:
    return jsonify(load_library())


@app.post("/api/library/reload")
def api_library_reload() -> Response:
    data = load_library(force=True)
    return jsonify({"ok": True, "track_count": data.get("track_count", 0)})


def _run_scan(*, skip_edges: bool) -> tuple[int, str]:
    python = APP_DIR / ".venv/bin/python"
    script = APP_DIR / "scan_library.py"
    if not python.is_file():
        return 127, f"Python scanner not found at {python}"
    args = [str(python), str(script)]
    if skip_edges:
        args.append("--skip-edges")
    try:
        result = subprocess.run(
            args,
            cwd=str(APP_DIR),
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        return 1, str(exc)
    output = "\n".join(part for part in (result.stdout, result.stderr) if part).strip()
    return result.returncode, output


@app.post("/api/library/scan")
def api_library_scan() -> Response:
    skip_edges = request.args.get("skip_edges", "1").lower() not in {"0", "false", "no"}
    if not _SCAN_LOCK.acquire(blocking=False):
        return jsonify({"ok": False, "error": "Scan already in progress"}), 409
    try:
        code, output = _run_scan(skip_edges=skip_edges)
        if code != 0:
            return jsonify({"ok": False, "error": output or f"scan exited {code}"}), 500
        data = load_library(force=True)
        return jsonify(
            {
                "ok": True,
                "track_count": data.get("track_count", 0),
                "output": output,
            }
        )
    finally:
        _SCAN_LOCK.release()


@app.get("/api/audio/<track_id>")
def api_audio(track_id: str) -> Response:
    load_library()
    track = TRACK_INDEX.get(track_id)
    if not track:
        abort(404)
    path = Path(track["path"])
    if not allowed_path(path) or not path.exists():
        abort(404)
    mime, _ = mimetypes.guess_type(path.name)
    return send_from_directory(path.parent, path.name, mimetype=mime or "audio/wav")


RB_PATHS: dict[str, Path] = {}

# With SETA_ARRANGE_ONLY=1 (sharing on the home network) only these read-only routes answer.
ARRANGE_ROUTES = ("/arrange", "/static/", "/api/rb/tracks", "/api/rb/waveform/", "/api/rb/audio/", "/api/rb/m3u", "/api/arrange/")


@app.before_request
def block_cross_site_writes() -> None:
    """Writes (Rekordbox edits, scans) only from Seta's own pages, never from another website."""
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return None
    origin = request.headers.get("Origin")
    if request.headers.get("Sec-Fetch-Site") == "cross-site" or (origin and urlsplit(origin).netloc != request.host):
        abort(403)
    return None


@app.before_request
def limit_to_arrange() -> Response | None:
    if arrange_only() and not request.path.startswith(ARRANGE_ROUTES):
        if request.path == "/":
            return redirect("/arrange")
        abort(404)
    return None


@app.get("/tags")
def tags_page() -> Response:
    return send_from_directory(STATIC_DIR, "tags.html")


@app.get("/gig")
def gig_page() -> Response:
    return send_from_directory(STATIC_DIR, "gig.html")


@app.get("/arrange")
def arrange_page() -> Response:
    return send_from_directory(STATIC_DIR, "arrange.html")


@app.get("/api/rb/m3u")
def api_rb_m3u() -> Response:
    """An M3U8 playlist of Rekordbox tracks in the given order (ids from /api/rb/tracks)."""
    lines = ["#EXTM3U"]
    for content_id in request.args.get("ids", "").split(","):
        path = rb_path(content_id)
        if path:
            lines.append(str(path))
    name = "".join(c for c in request.args.get("name", "set") if c.isalnum() or c in " -_") or "set"
    return Response(
        "\n".join(lines) + "\n",
        mimetype="audio/x-mpegurl",
        headers={"Content-Disposition": f'attachment; filename="{name}.m3u8"'},
    )


def _load_rb_tracks() -> dict:
    data = rb_tags.load_tracks()
    RB_PATHS.clear()
    for track in data["tracks"]:
        RB_PATHS[track["id"]] = Path(track.pop("path"))
    return data


def rb_path(content_id: str) -> Path | None:
    """A Rekordbox track's file; loads the collection when the server restarted since the page did."""
    if not RB_PATHS:
        _load_rb_tracks()
    return RB_PATHS.get(content_id)


@app.get("/api/arrange/sets")
def api_arrange_sets() -> Response:
    """Every saved arrangement, by playlist id (see arrange_store.py)."""
    return jsonify(arrange_store.load())


@app.put("/api/arrange/sets/<playlist_id>")
def api_arrange_save(playlist_id: str) -> Response:
    try:
        body = request.get_json(force=True)
        arrange_store.save_set(playlist_id, body.get("items"), body.get("at"))
    except (ValueError, AttributeError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True})


@app.post("/api/rb/xml")
def api_rb_xml() -> Response:
    """Write a rekordbox XML of the arranged set (order plus mix points as memory cues, see rb_xml.py)
    to one fixed file, replacing the last export, so rekordbox only needs a refresh.

    Safety first: the rekordbox library is copied (rb_tags.snapshot_library) and the previous export
    is kept with its date in seta-exports/, so a bad import can be undone."""
    library_backup = rb_tags.snapshot_library()
    body = request.get_json(force=True)
    wanted = [t for t in body.get("tracks", []) if rb_path(str(t.get("id")))]
    db = rb_tags._open_db()
    try:
        tracks = []
        for item in wanted:
            cid = str(item["id"])
            content = db.get_content(ID=int(cid))
            tracks.append(
                {
                    "path": str(rb_path(cid)),
                    "title": content.Title,
                    "artist": content.ArtistName,
                    "genre": content.GenreName,
                    "bpm": (content.BPM or 0) / 100,
                    "key": content.KeyName,
                    "rating": content.Rating,
                    "length_s": content.Length,
                    "cues": rb_waveform._index()["tracks"].get(cid, {}).get("cues", []),
                    "mix_points": [{"ms": float(p["ms"]), "name": str(p["name"])} for p in item.get("cues", [])],
                }
            )
    finally:
        db.close()
    name = "".join(c for c in str(body.get("name", "set")) if c.isalnum() or c in " -_()") or "set"
    target = rekordbox_xml_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        history = target.parent / "seta-exports"
        history.mkdir(exist_ok=True)
        stamp = datetime.datetime.fromtimestamp(target.stat().st_mtime)
        shutil.copy2(target, history / f"{target.stem}-{stamp:%Y%m%d-%H%M%S}.xml")
        for old in sorted(history.glob(f"{target.stem}-*.xml"))[:-KEEP_EXPORTS]:
            old.unlink()
    tmp = target.with_suffix(".tmp")
    tmp.write_text(rb_xml.build(name, tracks), encoding="utf-8")
    os.replace(tmp, target)
    return jsonify({"ok": True, "path": str(target), "tracks": len(tracks), "library_backup": str(library_backup)})


@app.get("/api/rb/tracks")
def api_rb_tracks() -> Response:
    data = _load_rb_tracks()
    data["pending"] = len(rb_tags.load_pending())
    data["rekordbox_running"] = rb_tags.rekordbox_running()
    data["arrange_only"] = arrange_only()
    return jsonify(data)


@app.get("/api/rb/status")
def api_rb_status() -> Response:
    return jsonify(
        {
            "pending": len(rb_tags.load_pending()),
            "rekordbox_running": rb_tags.rekordbox_running(),
        }
    )


@app.post("/api/rb/edit")
def api_rb_edit() -> Response:
    body = request.get_json(force=True)
    try:
        pending = rb_tags.queue_edit(body["id"], body["field"], body.get("value"))
    except (KeyError, ValueError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "pending": len(pending)})


@app.post("/api/rb/apply")
def api_rb_apply() -> Response:
    try:
        result = rb_tags.apply_pending()
    except RuntimeError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 409
    return jsonify({"ok": True, **result})


@app.get("/api/rb/waveform/<content_id>")
def api_rb_waveform(content_id: str) -> Response:
    data = rb_waveform.waveform(content_id)
    return jsonify(data) if data else abort(404)


@app.get("/api/waveform/<track_id>")
def api_waveform(track_id: str) -> Response:
    """Rekordbox's waveform for a library track, when Rekordbox knows the file."""
    load_library()
    track = TRACK_INDEX.get(track_id)
    content_id = rb_waveform.content_id_for_path(Path(track["path"])) if track else None
    data = rb_waveform.waveform(content_id) if content_id else None
    return jsonify(data) if data else abort(404)


@app.get("/api/rb/audio/<content_id>")
def api_rb_audio(content_id: str) -> Response:
    # Paths come from the local Rekordbox collection, so they may sit outside the Seta roots.
    path = rb_path(content_id)
    if not path or not path.exists():
        abort(404)
    mime, _ = mimetypes.guess_type(path.name)
    return send_from_directory(path.parent, path.name, mimetype=mime or "audio/wav")


def main() -> None:
    load_library()
    listen_port = port()
    listen_host = host()
    print(f"Seta: http://127.0.0.1:{listen_port}{'/arrange (Arrange only)' if arrange_only() else ''}")
    if listen_host != "127.0.0.1":
        print(f"Also on the network at http://<this Mac>.local:{listen_port}/arrange")
    print(f"Library: {LIBRARY_PATH}")
    print(f"Tracks root: {tracks_root()}")
    app.run(host=listen_host, port=listen_port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
