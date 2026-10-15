"""Tests for Camelot wheel helpers."""

from __future__ import annotations

import unittest

from camelot import (
    bpm_compatible,
    camelot_color,
    camelot_compatible,
    mix_score,
    pitch_class_to_camelot,
    UNKNOWN_COLOR,
)


class PitchClassToCamelotTests(unittest.TestCase):
    def test_minor_pitch_classes(self) -> None:
        self.assertEqual(pitch_class_to_camelot(0, "minor"), "5A")
        self.assertEqual(pitch_class_to_camelot(8, "minor"), "1A")

    def test_major_pitch_classes(self) -> None:
        self.assertEqual(pitch_class_to_camelot(0, "major"), "8B")
        self.assertEqual(pitch_class_to_camelot(8, "major"), "4B")

    def test_wraps_pitch_class_mod_12(self) -> None:
        self.assertEqual(pitch_class_to_camelot(12, "minor"), "5A")
        self.assertEqual(pitch_class_to_camelot(-1, "minor"), "10A")


class CamelotCompatibleTests(unittest.TestCase):
    def test_same_key(self) -> None:
        self.assertEqual(camelot_compatible("8A", "8A"), 1.0)
        self.assertEqual(camelot_compatible("4a", "4A"), 1.0)

    def test_relative_major_minor(self) -> None:
        self.assertEqual(camelot_compatible("8A", "8B"), 0.82)

    def test_adjacent_same_mode(self) -> None:
        self.assertEqual(camelot_compatible("8A", "9A"), 0.72)
        self.assertEqual(camelot_compatible("1A", "12A"), 0.72)

    def test_adjacent_different_mode(self) -> None:
        self.assertEqual(camelot_compatible("8A", "9B"), 0.55)

    def test_incompatible(self) -> None:
        self.assertEqual(camelot_compatible("8A", "10A"), 0.0)

    def test_missing_or_invalid(self) -> None:
        self.assertEqual(camelot_compatible(None, "8A"), 0.0)
        self.assertEqual(camelot_compatible("8A", None), 0.0)
        self.assertEqual(camelot_compatible("bad", "8A"), 0.0)


class BpmCompatibleTests(unittest.TestCase):
    def test_missing_bpm(self) -> None:
        self.assertEqual(bpm_compatible(None, 128.0), 0.35)
        self.assertEqual(bpm_compatible(128.0, None), 0.35)

    def test_tight_match(self) -> None:
        self.assertEqual(bpm_compatible(128.0, 128.5), 1.0)
        self.assertEqual(bpm_compatible(128.0, 130.0), 0.9)

    def test_far_apart(self) -> None:
        self.assertEqual(bpm_compatible(120.0, 130.0), 0.0)


class MixScoreTests(unittest.TestCase):
    def test_perfect_mix(self) -> None:
        self.assertEqual(mix_score("8A", "8A", 128.0, 128.0), 1.0)

    def test_harmonic_only_when_bpm_missing(self) -> None:
        self.assertAlmostEqual(mix_score("8A", "8B", 128.0, None), 0.82 * 0.35)

    def test_zero_when_keys_incompatible(self) -> None:
        self.assertEqual(mix_score("8A", "10A", 128.0, 128.0), 0.0)


class CamelotColorTests(unittest.TestCase):
    def test_known_code(self) -> None:
        self.assertEqual(camelot_color("8A"), "#00838F")

    def test_unknown_or_empty(self) -> None:
        self.assertEqual(camelot_color(None), UNKNOWN_COLOR)
        self.assertEqual(camelot_color("XX"), UNKNOWN_COLOR)


if __name__ == "__main__":
    unittest.main()
