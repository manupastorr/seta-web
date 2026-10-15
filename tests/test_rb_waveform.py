"""Tests for reading Rekordbox's color waveform preview (rb_waveform)."""

from __future__ import annotations

import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import base64  # noqa: E402

from rb_waveform import read_color_preview, read_downbeats, read_vocals  # noqa: E402


def tag(code: bytes, header_extra: bytes, body: bytes) -> bytes:
    len_header = 12 + len(header_extra)
    return code + struct.pack(">II", len_header, len_header + len(body)) + header_extra + body


def anlz(*tags: bytes) -> bytes:
    header_len = 28
    body = b"".join(tags)
    return b"PMAI" + struct.pack(">II", header_len, header_len + len(body)) + b"\0" * 16 + body


def preview_tag(columns: int, entry_bytes: int = 6) -> tuple[bytes, bytes]:
    data = bytes(range(columns * entry_bytes))
    extra = struct.pack(">III", entry_bytes, columns, 0)
    return tag(b"PWV4", extra, data), data


class ReadColorPreviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "ANLZ0000.EXT"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write(self, data: bytes) -> Path:
        self.path.write_bytes(data)
        return self.path

    def test_reads_preview_after_other_tags(self) -> None:
        pwv4, data = preview_tag(20)
        path = self.write(anlz(tag(b"PPTH", b"\0" * 4, b"x" * 10), pwv4))
        self.assertEqual(read_color_preview(path), data)

    def test_missing_tag_or_file_returns_none(self) -> None:
        self.assertIsNone(read_color_preview(self.write(anlz(tag(b"PPTH", b"\0" * 4, b"x")))))
        self.assertIsNone(read_color_preview(Path(self.tmp.name) / "missing.EXT"))

    def test_malformed_files_return_none(self) -> None:
        pwv4, _ = preview_tag(20)
        self.assertIsNone(read_color_preview(self.write(b"NOPE" + pwv4)))
        self.assertIsNone(read_color_preview(self.write(anlz(pwv4)[:-10])))
        wrong_entry, _ = preview_tag(20, entry_bytes=3)
        self.assertIsNone(read_color_preview(self.write(anlz(wrong_entry))))


class ReadDownbeatsTests(unittest.TestCase):
    def test_keeps_beat_one_of_each_bar(self) -> None:
        beats = [(1, 12000, 100), (2, 12000, 600), (3, 12000, 1100), (4, 12000, 1600), (1, 12000, 2100)]
        body = b"".join(struct.pack(">HHI", *b) for b in beats)
        pqtz = tag(b"PQTZ", struct.pack(">III", 0, 0x80000, len(beats)), body)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ANLZ0000.DAT"
            path.write_bytes(anlz(pqtz))
            self.assertEqual(read_downbeats(path), [100, 2100])
            path.write_bytes(anlz(tag(b"PPTH", b"\0" * 4, b"x")))
            self.assertEqual(read_downbeats(path), [])


class ReadVocalsTests(unittest.TestCase):
    def test_reads_rekordbox_vocal_levels_and_timing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ANLZ0000.2EX"
            levels = bytes([0, 0, 2, 4, 1])
            path.write_bytes(anlz(tag(b"PWVC", b"\0\0", b""), tag(b"PVDI", struct.pack(">IHHI", 1024, 22050, 1, len(levels)), levels)))
            vocals = read_vocals(path)
            self.assertAlmostEqual(vocals["step_ms"], 1024 / 22050 * 1000)
            self.assertEqual(base64.b64decode(vocals["levels"]), levels)
            self.assertIsNone(read_vocals(Path(tmp) / "missing.2EX"))


if __name__ == "__main__":
    unittest.main()
