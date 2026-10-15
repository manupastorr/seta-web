"""Tests for heuristic vocal detection."""

from __future__ import annotations

import unittest

import numpy as np

from analyze import ANALYSIS_VERSION, _detect_vocals, _harmonic_voiced_strength, analyze_track


class AnalyzeVocalsTests(unittest.TestCase):
    def test_analysis_version_bumped(self) -> None:
        self.assertEqual(ANALYSIS_VERSION, 14)

    def test_detect_vocals_short_audio(self) -> None:
        y = np.zeros(22050 * 4, dtype=np.float32)
        label, conf = _detect_vocals(y, 22050)
        self.assertEqual(label, "unclear")
        self.assertIsNone(conf)

    def test_harmonic_voiced_strength_returns_clamped_value(self) -> None:
        sr = 22050
        t = np.linspace(0, 8, sr * 8, dtype=np.float32)
        y = (0.35 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
        strength = _harmonic_voiced_strength(y, sr)
        self.assertGreaterEqual(strength, 0.0)
        self.assertLessEqual(strength, 1.0)

    def test_detect_vocals_returns_valid_label_and_confidence(self) -> None:
        rng = np.random.default_rng(0)
        y = rng.standard_normal(22050 * 12).astype(np.float32) * 0.05
        label, conf = _detect_vocals(y, 22050)
        self.assertIn(label, ("yes", "no", "unclear"))
        if label != "unclear" or conf is not None:
            self.assertIsNotNone(conf)
            self.assertGreaterEqual(conf, 0.0)
            self.assertLessEqual(conf, 1.0)

    def test_analyze_track_error_payload_includes_vocals(self) -> None:
        from pathlib import Path
        from unittest.mock import patch

        with patch("analyze._load_mono", side_effect=RuntimeError("boom")):
            result = analyze_track(Path("/tmp/missing.wav"))
        self.assertEqual(result["vocals"], "unclear")
        self.assertIsNone(result["vocals_confidence"])


if __name__ == "__main__":
    unittest.main()
