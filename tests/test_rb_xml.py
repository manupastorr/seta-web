"""The rekordbox XML export: order, kept cues, mix points as memory cues."""

from __future__ import annotations

import sys
import unittest
import xml.dom.minidom
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import rb_xml  # noqa: E402


class RbXmlTests(unittest.TestCase):
    def test_keeps_cues_adds_mix_points_and_replaces_old_seta_cues(self) -> None:
        track = {
            "path": "/Music/My Track.wav",
            "title": "My & Track",
            "artist": "A",
            "bpm": 124.0,
            "key": "8A",
            "rating": 3,
            "length_s": 300,
            "cues": [
                {"ms": 1000, "end_ms": None, "hot": "A", "name": "drop"},
                {"ms": 64000, "end_ms": None, "hot": None, "name": ""},
                {"ms": 90000, "end_ms": 92000, "hot": None, "name": "loop"},
                {"ms": 5000, "end_ms": None, "hot": None, "name": "Seta mix in"},
            ],
            "mix_points": [{"ms": 64020, "name": "Seta next in"}, {"ms": 128000, "name": "Seta cut"}],
        }
        doc = xml.dom.minidom.parseString(rb_xml.build("Set (arranged)", [track, {**track, "path": "/Music/Two.mp3", "cues": [], "mix_points": []}]))
        first = doc.getElementsByTagName("COLLECTION")[0].getElementsByTagName("TRACK")[0]
        self.assertEqual(first.getAttribute("Location"), "file://localhost/Music/My%20Track.wav")
        self.assertEqual(first.getAttribute("Name"), "My & Track")
        self.assertEqual(first.getAttribute("Rating"), "153")
        marks = [(m.getAttribute("Name"), m.getAttribute("Start"), m.getAttribute("Num"), m.getAttribute("Type")) for m in first.getElementsByTagName("POSITION_MARK")]
        self.assertIn(("drop", "1.000", "0", "0"), marks)
        self.assertIn(("loop", "90.000", "-1", "4"), marks)
        self.assertIn(("Seta cut", "128.000", "-1", "0"), marks)
        names = [m[0] for m in marks]
        self.assertNotIn("Seta mix in", names, "old Seta cues are replaced")
        self.assertNotIn("Seta next in", names, "a mix point on an existing memory cue is not added twice")
        playlist = doc.getElementsByTagName("NODE")[1]
        self.assertEqual(playlist.getAttribute("Name"), "Set (arranged)")
        self.assertEqual([t.getAttribute("Key") for t in playlist.getElementsByTagName("TRACK")], ["1", "2"])


if __name__ == "__main__":
    unittest.main()
