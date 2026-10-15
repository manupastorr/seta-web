"""Tests for queued Rekordbox energy / Function edits (rb_tags)."""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import rb_tags  # noqa: E402
from rekordbox import rekordbox_db_path  # noqa: E402


class QueueEditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.pending = patch.object(rb_tags, "PENDING_PATH", Path(self.tmp.name) / "p.json")
        self.pending.start()

    def tearDown(self) -> None:
        self.pending.stop()
        self.tmp.cleanup()

    def test_edits_merge_per_track(self) -> None:
        rb_tags.queue_edit("1", "energy", 3)
        pending = rb_tags.queue_edit("1", "function", "Lift")
        self.assertEqual(pending, {"1": {"energy": 3, "function": "Lift"}})

    def test_rejects_bad_input(self) -> None:
        with self.assertRaises(ValueError):
            rb_tags.queue_edit("1", "energy", 6)
        with self.assertRaises(ValueError):
            rb_tags.queue_edit("1", "genre", "House")
        with self.assertRaises(ValueError):
            rb_tags.queue_edit("1", "state", "Warm")

    def test_apply_refuses_while_rekordbox_runs(self) -> None:
        rb_tags.queue_edit("1", "energy", 3)
        with patch.object(rb_tags, "rekordbox_running", return_value=True):
            with self.assertRaises(RuntimeError):
                rb_tags.apply_pending()
        self.assertEqual(len(rb_tags.load_pending()), 1)


@unittest.skipUnless(rekordbox_db_path().exists(), "no local Rekordbox database")
class ApplyOnCopyTests(unittest.TestCase):
    """Writes into a copy of the local master.db; the real one is never opened for writing."""

    def test_apply_writes_energy_and_replaces_group_tags(self) -> None:
        import pyrekordbox.db6.database as rbdb

        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "master.db"
            shutil.copy2(rekordbox_db_path(), copy)
            with (
                patch.object(rb_tags, "PENDING_PATH", Path(tmp) / "p.json"),
                patch.object(rb_tags, "BACKUP_DIR", Path(tmp) / "backups"),
                patch.object(rb_tags, "rekordbox_running", return_value=False),
                patch.object(rbdb, "get_rekordbox_pid", return_value=0),
            ):
                data = rb_tags.load_tracks(copy)
                if not data["tracks"] or len(data["groups"]["function"]) < 2:
                    self.skipTest("library has no tracks or Function tags")
                track = data["tracks"][0]
                first, second = data["groups"]["function"][:2]
                source = (data["groups"]["source"] or [None])[0]
                states = data["groups"]["state"][:2]

                rb_tags.queue_edit(track["id"], "energy", 4)
                rb_tags.queue_edit(track["id"], "function", first)
                rb_tags.queue_edit(track["id"], "source", source)
                rb_tags.queue_edit(track["id"], "state", states)
                rb_tags.apply_pending(copy)
                rb_tags.queue_edit(track["id"], "function", second)
                result = rb_tags.apply_pending(copy)

                self.assertTrue(Path(result["backup"]).exists())
                self.assertEqual(rb_tags.load_pending(), {})
                after = {t["id"]: t for t in rb_tags.load_tracks(copy)["tracks"]}[track["id"]]
                self.assertEqual(after["energy"], 4)
                self.assertEqual(after["function"], second)
                self.assertEqual(after["source"], source)
                self.assertEqual(sorted(after["state"]), sorted(states))

                rb_tags.queue_edit(track["id"], "function", None)
                rb_tags.apply_pending(copy)
                after = {t["id"]: t for t in rb_tags.load_tracks(copy)["tracks"]}[track["id"]]
                self.assertIsNone(after["function"])


if __name__ == "__main__":
    unittest.main()
