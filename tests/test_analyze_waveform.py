"""Tests for scan-time waveform peak generation."""

from __future__ import annotations

import unittest

import numpy as np

from analyze import (
    ANALYSIS_VERSION,
    WAVEFORM_BARS,
    WAVEFORM_VERSION,
    _compute_waveform_peaks,
)


class AnalyzeWaveformTests(unittest.TestCase):
    def test_analysis_version_bumped(self) -> None:
        self.assertEqual(ANALYSIS_VERSION, 14)

    def test_compute_waveform_peaks_shape(self) -> None:
        sr = 22050
        t = np.linspace(0, 4, sr * 4, dtype=np.float32)
        y = (0.4 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
        wf = _compute_waveform_peaks(y, sr)
        self.assertIsNotNone(wf)
        assert wf is not None
        self.assertEqual(wf["version"], WAVEFORM_VERSION)
        self.assertEqual(wf["bars"], WAVEFORM_BARS)
        self.assertEqual(len(wf["peak"]), WAVEFORM_BARS)
        self.assertEqual(len(wf["low"]), WAVEFORM_BARS)
        self.assertTrue(all(0 <= v <= 1 for v in wf["peak"]))

    def test_compute_waveform_peaks_short_audio(self) -> None:
        self.assertIsNone(_compute_waveform_peaks(np.zeros(100), 22050))


if __name__ == "__main__":
    unittest.main()
