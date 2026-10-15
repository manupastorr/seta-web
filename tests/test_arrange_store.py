"""Arrangements saved on this Mac, with a history of overwritten versions."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import arrange_store  # noqa: E402


class ArrangeStoreTests(unittest.TestCase):
    def test_save_load_and_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "a.json"
            history = Path(tmp) / "h.jsonl"
            self.assertEqual(arrange_store.load(store), {"sets": {}, "stamps": {}})
            arrange_store.save_set("123", [{"id": "1"}], path=store, history=history)
            arrange_store.save_set("123", [{"id": "1"}], path=store, history=history)  # unchanged: no history
            self.assertFalse(history.exists())
            arrange_store.save_set("123", [{"id": "2"}], 1234.0, path=store, history=history)
            self.assertEqual(arrange_store.load(store)["stamps"]["123"], 1234.0)
            self.assertEqual(arrange_store.load(store)["sets"]["123"], [{"id": "2"}])
            old = [json.loads(line) for line in history.read_text().splitlines()]
            self.assertEqual([h["items"] for h in old], [[{"id": "1"}]])

    def test_rejects_bad_input(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "a.json"
            for pid, items in [("../x", []), ("1", "nope"), ("1", [{"no_id": 1}])]:
                with self.assertRaises(ValueError):
                    arrange_store.save_set(pid, items, path=store, history=Path(tmp) / "h")


if __name__ == "__main__":
    unittest.main()
