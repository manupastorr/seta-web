"""Tests for Rekordbox BPM/key lookup helpers."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from rekordbox import (
    apply_rekordbox,
    key_to_camelot,
    load_rekordbox_index,
    lookup_rekordbox,
    rekordbox_bpm,
    use_rekordbox,
)


class RekordboxHelperTests(unittest.TestCase):
    def test_key_to_camelot_accepts_camelot_and_standard(self) -> None:
        self.assertEqual(key_to_camelot("9A"), "9A")
        self.assertEqual(key_to_camelot("3b"), "3B")
        self.assertEqual(key_to_camelot("Em"), "9A")
        self.assertEqual(key_to_camelot("Dbm"), "12A")

    def test_rekordbox_bpm_scales_hundredths(self) -> None:
        self.assertEqual(rekordbox_bpm(12000), 120.0)
        self.assertEqual(rekordbox_bpm(12199), 121.99)
        self.assertIsNone(rekordbox_bpm(0))

    def test_lookup_prefers_exact_path_then_stem(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wav = root / "Artist - Track.wav"
            aiff = root / "Artist - Track.aiff"
            wav.write_bytes(b"x" * 100)
            aiff.write_bytes(b"y" * 200)
            index = {
                "by_path": {
                    str(aiff.resolve()): {
                        "path": str(aiff.resolve()),
                        "bpm": 120.0,
                        "key": "3B",
                        "size": 200,
                        "ext": ".aiff",
                    }
                },
                "by_stem": {
                    "artist - track": [
                        {
                            "path": str(aiff.resolve()),
                            "bpm": 120.0,
                            "key": "3B",
                            "size": 200,
                            "ext": ".aiff",
                        }
                    ]
                },
            }
            self.assertEqual(lookup_rekordbox(aiff, index)["key"], "3B")
            self.assertEqual(lookup_rekordbox(wav, index)["key"], "3B")

    def test_apply_rekordbox_overrides_analysis(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".wav") as tmp:
            path = Path(tmp.name)
            index = {
                "by_path": {
                    str(path.resolve()): {
                        "path": str(path.resolve()),
                        "bpm": 120.0,
                        "key": "3B",
                        "size": 0,
                        "ext": ".wav",
                    }
                },
                "by_stem": {},
            }
            merged = apply_rekordbox(
                {"bpm": 118.0, "bpm_source": "analysis", "key": "9A"},
                path,
                index,
            )
            self.assertEqual(merged["bpm"], 120.0)
            self.assertEqual(merged["bpm_source"], "rekordbox")
            self.assertEqual(merged["key"], "3B")
            self.assertEqual(merged["key_source"], "rekordbox")

    def test_load_rekordbox_index_disabled_by_env(self) -> None:
        with patch.dict(os.environ, {"SETA_USE_REKORDBOX": "0"}):
            self.assertFalse(use_rekordbox())
            self.assertIsNone(load_rekordbox_index())


if __name__ == "__main__":
    unittest.main()
