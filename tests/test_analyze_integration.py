"""Integration tests for analyze_track and _detect_bpm on synthetic audio."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
import soundfile as sf

from analyze import ANALYSIS_VERSION, TARGET_SR, _detect_bpm, analyze_track


def _click_track(bpm: float, duration_sec: float = 30.0, sr: int = TARGET_SR) -> np.ndarray:
    """Simple impulse train at a fixed tempo for BPM regression checks."""
    length = int(duration_sec * sr)
    y = np.zeros(length, dtype=np.float32)
    interval = 60.0 / bpm
    for beat in np.arange(0.0, duration_sec, interval):
        idx = int(beat * sr)
        if idx < length:
            y[idx] = 1.0
    return y


class AnalyzeIntegrationTests(unittest.TestCase):
    def test_detect_bpm_on_click_train(self) -> None:
        sr = TARGET_SR
        y = _click_track(128.0, duration_sec=30.0, sr=sr)
        bpm, raw_bpm, octave_fixed, onset_env, candidates = _detect_bpm(y, sr)
        self.assertGreater(len(onset_env), 0)
        self.assertTrue(candidates)
        self.assertIsNotNone(bpm)
        self.assertIsNotNone(raw_bpm)
        assert bpm is not None
        assert raw_bpm is not None
        self.assertFalse(octave_fixed)
        self.assertGreaterEqual(bpm, 118.0)
        self.assertLessEqual(bpm, 138.0)
        self.assertGreaterEqual(raw_bpm, 118.0)
        self.assertLessEqual(raw_bpm, 138.0)

    def test_analyze_track_on_temp_wav(self) -> None:
        sr = TARGET_SR
        y = _click_track(128.0, duration_sec=30.0, sr=sr)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            path = Path(tmp.name)
        try:
            sf.write(path, y, sr)
            result = analyze_track(path)
        finally:
            path.unlink(missing_ok=True)

        self.assertEqual(result["analysis_version"], ANALYSIS_VERSION)
        self.assertIsNone(result["analysis_error"])
        self.assertIsNotNone(result["bpm"])
        self.assertIn(result["vocals"], ("yes", "no", "unclear"))
        self.assertIsNotNone(result["waveform"])
        assert result["bpm"] is not None
        self.assertGreaterEqual(result["bpm"], 118.0)
        self.assertLessEqual(result["bpm"], 138.0)
        self.assertGreaterEqual(result["energy"], 0.0)
        self.assertLessEqual(result["energy"], 1.0)
        self.assertEqual(result["energy"], result["energy_effective"])
        self.assertGreaterEqual(result["energy_main"], 0.0)
        self.assertLessEqual(result["energy_main"], 1.0)
        self.assertGreaterEqual(result["energy_peak"], 0.0)
        self.assertLessEqual(result["energy_peak"], 1.0)
        self.assertIsInstance(result["energy_curve"], list)


if __name__ == "__main__":
    unittest.main()
