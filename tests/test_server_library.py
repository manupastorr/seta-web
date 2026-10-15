"""Tests for in-memory library reload when library.json changes."""

from __future__ import annotations

import importlib
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch


class ServerLibraryReloadTests(unittest.TestCase):
    def test_load_library_reloads_when_mtime_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            lib_path = Path(tmp) / "library.json"
            lib_path.write_text(json.dumps({"tracks": [], "edges": [], "track_count": 0}))

            if "server" in sys.modules:
                del sys.modules["server"]

            with patch("server.LIBRARY_PATH", lib_path):
                server = importlib.import_module("server")
                server.LIBRARY_CACHE = None
                server.LIBRARY_MTIME = None
                server.TRACK_INDEX.clear()

                first = server.load_library(force=True)
                self.assertEqual(first["track_count"], 0)

                time.sleep(0.01)
                lib_path.write_text(
                    json.dumps(
                        {
                            "tracks": [{"id": "abc", "path": "/tmp/x.wav", "title": "T"}],
                            "edges": [],
                            "track_count": 1,
                        }
                    )
                )
                second = server.load_library()
                self.assertEqual(second["track_count"], 1)
                self.assertIn("abc", server.TRACK_INDEX)


class ServerLibraryScanTests(unittest.TestCase):
    def test_api_library_scan_runs_scanner_and_reloads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            lib_path = Path(tmp) / "library.json"
            lib_path.write_text(json.dumps({"tracks": [], "edges": [], "track_count": 0}))

            if "server" in sys.modules:
                del sys.modules["server"]

            with patch("server.LIBRARY_PATH", lib_path):
                with patch("server._run_scan", return_value=(0, "Wrote library.json")) as run_scan:
                    server = importlib.import_module("server")
                    server.LIBRARY_CACHE = None
                    server.LIBRARY_MTIME = None
                    server.TRACK_INDEX.clear()
                    server.app.config["TESTING"] = True
                    client = server.app.test_client()

                    response = client.post("/api/library/scan?skip_edges=1")

                    self.assertEqual(response.status_code, 200)
                    payload = response.get_json()
                    self.assertTrue(payload["ok"])
                    self.assertEqual(payload["track_count"], 0)
                    run_scan.assert_called_once_with(skip_edges=True)

    def test_api_library_scan_rejects_parallel_requests(self) -> None:
        if "server" in sys.modules:
            del sys.modules["server"]

        server = importlib.import_module("server")
        server.app.config["TESTING"] = True
        client = server.app.test_client()

        acquired = server._SCAN_LOCK.acquire(blocking=False)
        self.assertTrue(acquired)
        try:
            response = client.post("/api/library/scan")
            self.assertEqual(response.status_code, 409)
            payload = response.get_json()
            self.assertFalse(payload["ok"])
            self.assertIn("progress", payload["error"])
        finally:
            server._SCAN_LOCK.release()


class ArrangeOnlyTests(unittest.TestCase):
    """SETA_ARRANGE_ONLY=1 (sharing on the home network) answers only the Arrange page's read-only routes."""

    def test_only_arrange_routes_answer(self) -> None:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        server = importlib.import_module("server")
        client = server.app.test_client()
        with patch.dict(os.environ, {"SETA_ARRANGE_ONLY": "1"}):
            self.assertEqual(client.get("/arrange").status_code, 200)
            self.assertEqual(client.get("/static/arrange.html").status_code, 200)
            self.assertEqual(client.get("/").status_code, 302)
            self.assertEqual(client.get("/tags").status_code, 404)
            self.assertEqual(client.get("/api/library").status_code, 404)
            self.assertEqual(client.post("/api/rb/edit", json={}).status_code, 404)
            self.assertEqual(client.post("/api/rb/apply").status_code, 404)
        with patch.dict(os.environ, {"SETA_ARRANGE_ONLY": "0"}):
            self.assertEqual(client.get("/tags").status_code, 200)


class CrossSiteWriteTests(unittest.TestCase):
    def test_other_websites_cannot_post(self) -> None:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        server = importlib.import_module("server")
        client = server.app.test_client()
        with patch.object(server.rb_tags, "apply_pending", return_value={}) as apply:
            self.assertEqual(client.post("/api/rb/apply", headers={"Origin": "https://evil.example"}).status_code, 403)
            self.assertEqual(client.post("/api/rb/apply", headers={"Sec-Fetch-Site": "cross-site"}).status_code, 403)
            self.assertEqual(apply.call_count, 0)
            self.assertEqual(client.post("/api/rb/apply", headers={"Origin": "http://localhost"}).status_code, 200)
            self.assertEqual(client.post("/api/rb/apply").status_code, 200)


class RbXmlExportTests(unittest.TestCase):
    def test_export_replaces_one_fixed_file(self) -> None:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        server = importlib.import_module("server")
        client = server.app.test_client()
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "rekordbox" / "seta.xml"
            snapshot = patch.object(server.rb_tags, "snapshot_library", return_value=Path(tmp) / "library-x")
            with patch.dict(os.environ, {"SETA_RB_XML": str(target)}), patch.object(server.rb_tags, "_open_db") as db, snapshot as backup:
                for name in ("first set", "second set"):
                    res = client.post("/api/rb/xml", json={"name": name, "tracks": []})
                    self.assertEqual(res.get_json()["path"], str(target.resolve()))
            self.assertIn('Name="second set"', target.read_text())
            self.assertEqual(sorted(p.name for p in target.parent.iterdir()), ["seta-exports", "seta.xml"])
            self.assertIn('Name="first set"', next((target.parent / "seta-exports").iterdir()).read_text(), "the earlier export is kept")
            self.assertEqual(backup.call_count, 2, "the library is backed up before every export")
            db.return_value.close.assert_called()


class SnapshotLibraryTests(unittest.TestCase):
    def test_copies_db_with_wal_and_keeps_the_newest(self) -> None:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        rb_tags = importlib.import_module("rb_tags")
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "master.db"
            db.write_text("db")
            (Path(tmp) / "master.db-wal").write_text("wal")
            backups = Path(tmp) / "backups"
            for n in range(3):
                (backups / f"library-2026010{n}-000000").mkdir(parents=True)
            made = rb_tags.snapshot_library(db, keep=2, backup_dir=backups)
            self.assertEqual(sorted(p.name for p in made.iterdir()), ["master.db", "master.db-wal"])
            self.assertEqual((made / "master.db-wal").read_text(), "wal")
            self.assertEqual(len(list(backups.iterdir())), 2)
            self.assertIn(made, list(backups.iterdir()))


class RbAudioTests(unittest.TestCase):
    def test_audio_paths_load_on_demand_after_a_restart(self) -> None:
        """A page opened before the server restarted still gets audio: the paths load on first use."""
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        server = importlib.import_module("server")
        server.RB_PATHS.clear()
        tracks = {"tracks": [{"id": "7", "path": "/music/a.wav"}], "playlists": []}
        with patch.object(server.rb_tags, "load_tracks", return_value=tracks) as load:
            self.assertEqual(server.rb_path("7"), Path("/music/a.wav"))
            self.assertIsNone(server.rb_path("8"))
        self.assertEqual(load.call_count, 1)
        server.RB_PATHS.clear()


if __name__ == "__main__":
    unittest.main()
