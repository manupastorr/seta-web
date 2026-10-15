"""Tests for scanner path logic and library shape."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import scan_library
import analyze
from scan_library import (
    build_edges,
    cached_analysis,
    cached_analysis_for_energy_upgrade,
    classify_path,
    configure_scan,
    discover_files,
    is_excluded_path,
    is_scannable_audio,
    parse_filename,
    track_id,
)

REQUIRED_TRACK_FIELDS = {
    "id",
    "path",
    "artist",
    "title",
    "source",
    "genre",
    "batch",
    "duration_sec",
    "bpm",
    "bpm_raw",
    "bpm_octave_corrected",
    "bpm_source",
    "bpm_confidence",
    "key",
    "energy",
    "analysis_error",
}

OPTIONAL_TRACK_FIELDS = {
    "vocals",
    "vocals_confidence",
    "energy_auto",
    "energy_effective",
    "energy_main",
    "energy_avg",
    "energy_peak",
    "energy_intro",
    "energy_outro",
    "energy_confidence",
    "energy_curve",
    "waveform_version",
    "waveform_peak",
    "waveform_low",
    "waveform_mid",
    "waveform_high",
}


def library_errors(library: dict) -> list[str]:
    """Return structural problems in a generated library payload."""
    errors: list[str] = []
    tracks = library.get("tracks")
    if not isinstance(tracks, list):
        return ["tracks must be a list"]

    count = library.get("track_count")
    if count != len(tracks):
        errors.append(f"track_count {count!r} != len(tracks) {len(tracks)}")

    seen_ids: set[str] = set()
    for idx, track in enumerate(tracks):
        missing = REQUIRED_TRACK_FIELDS - track.keys()
        if missing:
            errors.append(f"tracks[{idx}] missing fields: {sorted(missing)}")
        tid = track.get("id")
        if not isinstance(tid, str) or not tid:
            errors.append(f"tracks[{idx}] has invalid id")
        elif tid in seen_ids:
            errors.append(f"duplicate track id: {tid}")
        else:
            seen_ids.add(tid)

        source = track.get("source")
        if source not in {"tracks", "to_curate", "other"}:
            errors.append(f"tracks[{idx}] unexpected source: {source!r}")

        vocals = track.get("vocals")
        if vocals is not None and vocals not in {"yes", "no", "unclear"}:
            errors.append(f"tracks[{idx}] unexpected vocals: {vocals!r}")
        vocals_conf = track.get("vocals_confidence")
        if vocals_conf is not None and not isinstance(vocals_conf, (int, float)):
            errors.append(f"tracks[{idx}] vocals_confidence must be numeric")
        elif isinstance(vocals_conf, (int, float)) and (
            vocals_conf < 0 or vocals_conf > 1
        ):
            errors.append(f"tracks[{idx}] vocals_confidence out of range: {vocals_conf}")
        for field in (
            "energy",
            "energy_auto",
            "energy_effective",
            "energy_main",
            "energy_avg",
            "energy_peak",
            "energy_intro",
            "energy_outro",
            "energy_confidence",
        ):
            value = track.get(field)
            if value is not None and not isinstance(value, (int, float)):
                errors.append(f"tracks[{idx}] {field} must be numeric")
            elif isinstance(value, (int, float)) and (value < 0 or value > 1):
                errors.append(f"tracks[{idx}] {field} out of range: {value}")
        curve = track.get("energy_curve")
        if curve is not None:
            if not isinstance(curve, list):
                errors.append(f"tracks[{idx}] energy_curve must be a list")
            elif any(not isinstance(v, (int, float)) or v < 0 or v > 1 for v in curve):
                errors.append(f"tracks[{idx}] energy_curve contains invalid values")

    edges = library.get("edges")
    if not isinstance(edges, list):
        errors.append("edges must be a list")
        return errors

    for idx, edge in enumerate(edges):
        for field in ("source", "target", "score"):
            if field not in edge:
                errors.append(f"edges[{idx}] missing {field!r}")
        src, tgt, score = edge.get("source"), edge.get("target"), edge.get("score")
        if src not in seen_ids:
            errors.append(f"edges[{idx}] source {src!r} not in tracks")
        if tgt not in seen_ids:
            errors.append(f"edges[{idx}] target {tgt!r} not in tracks")
        if isinstance(score, (int, float)):
            if score < 0 or score > 1:
                errors.append(f"edges[{idx}] score out of range: {score}")
        else:
            errors.append(f"edges[{idx}] score must be numeric")

    return errors


class IsScannableAudioTests(unittest.TestCase):
    def test_supported_extensions(self) -> None:
        for ext in (".wav", ".WAV", ".flac", ".mp3", ".aiff", ".aif"):
            self.assertTrue(is_scannable_audio(Path(f"track{ext}")))

    def test_unsupported_extension(self) -> None:
        self.assertFalse(is_scannable_audio(Path("readme.txt")))

    def test_excludes_set_id_sample_clips(self) -> None:
        clip = Path("/tmp/tracks/samples/sample_abc123.wav")
        self.assertFalse(is_scannable_audio(clip))
        real = Path("/tmp/tracks/samples/loop.wav")
        self.assertTrue(is_scannable_audio(real))


class ParseFilenameTests(unittest.TestCase):
    def test_artist_title_split(self) -> None:
        self.assertEqual(
            parse_filename(Path("Artist Name - Track Title.wav")),
            ("Artist Name", "Track Title"),
        )

    def test_no_separator_uses_stem_as_title(self) -> None:
        self.assertEqual(parse_filename(Path("Standalone.wav")), ("", "Standalone"))


class ClassifyPathTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.tracks_root = Path(self.tmp.name) / "tracks"
        self.curate_root = Path(self.tmp.name) / "curate"
        self.tracks_root.mkdir()
        self.curate_root.mkdir()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _configure(self) -> None:
        configure_scan([self.tracks_root.resolve()], [self.curate_root.resolve()])

    def test_tracks_source_and_genre(self) -> None:
        self._configure()
        path = self.tracks_root / "Techno & Trance" / "A - B.wav"
        path.parent.mkdir(parents=True)
        path.touch()
        meta = classify_path(path)
        self.assertEqual(meta["source"], "tracks")
        self.assertEqual(meta["genre"], "Techno & Trance")
        self.assertIsNone(meta["batch"])

    def test_curate_source_batch_and_genre(self) -> None:
        self._configure()
        path = self.curate_root / "Playlist Batch" / "A - B.wav"
        path.parent.mkdir(parents=True)
        path.touch()
        meta = classify_path(path)
        self.assertEqual(meta["source"], "to_curate")
        self.assertEqual(meta["genre"], "Playlist Batch")
        self.assertEqual(meta["batch"], "Playlist Batch")

    def test_direct_child_uses_root_name_as_genre(self) -> None:
        self._configure()
        path = self.tracks_root / "Melodic House & Techno" / "A - B.wav"
        path.parent.mkdir(parents=True)
        path.touch()
        meta = classify_path(path)
        self.assertEqual(meta["genre"], "Melodic House & Techno")

        genre_root = Path(self.tmp.name) / "genre-folder"
        genre_root.mkdir()
        direct = genre_root / "Artist - Song.wav"
        direct.touch()
        configure_scan([genre_root.resolve()], [])
        meta_direct = classify_path(direct)
        self.assertEqual(meta_direct["genre"], "genre-folder")

    def test_outside_roots(self) -> None:
        self._configure()
        meta = classify_path(Path(self.tmp.name) / "elsewhere.wav")
        self.assertEqual(meta["source"], "other")


class MultiRootTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root_a = Path(self.tmp.name) / "library-a"
        self.root_b = Path(self.tmp.name) / "library-b"
        self.curate_a = Path(self.tmp.name) / "incoming-a"
        self.root_a.mkdir()
        self.root_b.mkdir()
        self.curate_a.mkdir()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_multiple_tracks_roots(self) -> None:
        file_a = self.root_a / "House" / "A - One.wav"
        file_b = self.root_b / "Techno" / "B - Two.wav"
        file_a.parent.mkdir(parents=True)
        file_b.parent.mkdir(parents=True)
        file_a.touch()
        file_b.touch()
        configure_scan([self.root_a.resolve(), self.root_b.resolve()], [])
        files = discover_files()
        self.assertEqual(files, [file_a.resolve(), file_b.resolve()])

    def test_empty_curate_roots_not_replaced_by_default(self) -> None:
        only = self.root_a / "Only.wav"
        only.touch()
        configure_scan([self.root_a.resolve()], [])
        files = discover_files()
        self.assertEqual(files, [only.resolve()])

    def test_excluded_path_skipped(self) -> None:
        kept = self.root_a / "A - Keep.wav"
        hidden = self.root_a / "B - Hide.wav"
        kept.touch()
        hidden.touch()
        configure_scan([self.root_a.resolve()], [], excluded_paths=[str(hidden.resolve())])
        self.assertTrue(is_excluded_path(hidden))
        files = discover_files()
        self.assertEqual(files, [kept.resolve()])


class DiscoverFilesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.tracks_root = Path(self.tmp.name) / "tracks"
        self.curate_root = Path(self.tmp.name) / "curate"
        self.tracks_root.mkdir()
        self.curate_root.mkdir()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _discover(self, limit: int | None = None) -> list[Path]:
        configure_scan([self.tracks_root.resolve()], [self.curate_root.resolve()])
        return discover_files(limit=limit)

    def test_finds_audio_skips_tools_and_samples(self) -> None:
        good = self.tracks_root / "House & Deep House" / "Artist - Song.wav"
        good.parent.mkdir(parents=True)
        good.touch()
        tools_file = self.tracks_root / "tools" / "seta" / "hidden.wav"
        tools_file.parent.mkdir(parents=True)
        tools_file.touch()
        sample_clip = self.tracks_root / "samples" / "sample_xyz.wav"
        sample_clip.parent.mkdir(parents=True)
        sample_clip.touch()
        txt = self.tracks_root / "notes.txt"
        txt.touch()

        files = self._discover()
        self.assertEqual(files, [good.resolve()])

    def test_respects_limit(self) -> None:
        for name in ("a.wav", "b.wav", "c.wav"):
            (self.tracks_root / name).touch()
        self.assertEqual(len(self._discover(limit=2)), 2)


class TrackIdTests(unittest.TestCase):
    def test_stable_for_same_path(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".wav") as fh:
            path = Path(fh.name)
            self.assertEqual(track_id(path), track_id(path))
            self.assertEqual(len(track_id(path)), 16)


class CacheTests(unittest.TestCase):
    def test_cached_analysis_requires_current_file_signature_and_version(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".wav") as fh:
            path = Path(fh.name)
            sig = scan_library.file_sig(path)
            cache = {
                str(path.resolve()): {
                    **sig,
                    "analysis_version": 999,
                    "bpm": 123,
                }
            }
            with patch("analyze.ANALYSIS_VERSION", 999):
                self.assertEqual(cached_analysis(path, cache)["bpm"], 123)
            with patch("analyze.ANALYSIS_VERSION", 1000):
                self.assertIsNone(cached_analysis(path, cache))

    def test_version_12_cache_can_upgrade_energy_only(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".wav") as fh:
            path = Path(fh.name)
            sig = scan_library.file_sig(path)
            cache = {
                str(path.resolve()): {
                    **sig,
                    "analysis_version": 12,
                    "bpm": 124,
                    "energy": 0.4,
                }
            }
            self.assertIsNotNone(cached_analysis_for_energy_upgrade(path, cache))
            with patch("analyze.analyze_track_energy", return_value={"energy": 0.7, "energy_curve": [0.7]}):
                result = scan_library.analyze_if_needed(path, cache)
            self.assertEqual(result["analysis_version"], analyze.ANALYSIS_VERSION)
            self.assertEqual(result["bpm"], 124)
            self.assertEqual(result["energy"], 0.7)
            self.assertEqual(result["energy_curve"], [0.7])


class BuildEdgesTests(unittest.TestCase):
    def test_skips_tracks_without_bpm_or_key(self) -> None:
        tracks = [
            {"id": "a", "key": "8A", "bpm": 128.0},
            {"id": "b", "key": None, "bpm": 128.0},
            {"id": "c", "key": "8B", "bpm": None},
        ]
        self.assertEqual(build_edges(tracks), [])

    def test_emits_compatible_pairs_above_threshold(self) -> None:
        tracks = [
            {"id": "a", "key": "8A", "bpm": 128.0},
            {"id": "b", "key": "8A", "bpm": 128.0},
            {"id": "c", "key": "10A", "bpm": 128.0},
        ]
        edges = build_edges(tracks, min_score=0.55)
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0]["source"], "a")
        self.assertEqual(edges[0]["target"], "b")
        self.assertEqual(edges[0]["score"], 1.0)

    def test_caps_edge_count(self) -> None:
        tracks = [{"id": f"t{i}", "key": "8A", "bpm": 128.0} for i in range(5)]
        edges = build_edges(tracks, min_score=0.55, max_edges=2)
        self.assertEqual(len(edges), 2)


class LibrarySanityTests(unittest.TestCase):
    def test_valid_minimal_library(self) -> None:
        library = {
            "generated_at": "2026-01-01T00:00:00+00:00",
            "tracks_root": "/tracks",
            "curate_root": "/curate",
            "track_count": 2,
            "tracks": [
                self._track("aa", "a"),
                self._track("bb", "b"),
            ],
            "edges": [{"source": "aa", "target": "bb", "score": 0.9}],
        }
        self.assertEqual(library_errors(library), [])

    def test_detects_count_mismatch_and_bad_edge(self) -> None:
        library = {
            "track_count": 99,
            "tracks": [self._track("aa", "a")],
            "edges": [{"source": "aa", "target": "missing", "score": 1.5}],
        }
        errors = library_errors(library)
        self.assertTrue(any("track_count" in e for e in errors))
        self.assertTrue(any("not in tracks" in e for e in errors))
        self.assertTrue(any("score out of range" in e for e in errors))

    def test_existing_library_json_if_present(self) -> None:
        library_path = scan_library.APP_DIR / "library.json"
        if not library_path.exists():
            self.skipTest("library.json not generated locally")
        library = json.loads(library_path.read_text())
        errors = library_errors(library)
        self.assertEqual(errors, [], "\n".join(errors))

    @staticmethod
    def _track(tid: str, suffix: str) -> dict:
        return {
            "id": tid,
            "path": f"/tracks/Artist - Title {suffix}.wav",
            "artist": "Artist",
            "title": f"Title {suffix}",
            "source": "tracks",
            "genre": "House & Deep House",
            "batch": None,
            "duration_sec": 300.0,
            "bpm": 124.0,
            "bpm_raw": 124.0,
            "bpm_octave_corrected": False,
            "bpm_source": "tag",
            "bpm_confidence": 0.35,
            "key": "8A",
            "energy": 0.7,
            "energy_auto": 0.7,
            "energy_effective": 0.7,
            "energy_main": 0.68,
            "energy_avg": 0.69,
            "energy_peak": 0.75,
            "energy_intro": 0.55,
            "energy_outro": 0.6,
            "energy_confidence": 0.72,
            "energy_curve": [0.55, 0.68, 0.75, 0.6],
            "vocals": "unclear",
            "vocals_confidence": 0.42,
            "analysis_error": None,
        }


class ScanLibraryCliTests(unittest.TestCase):
    def test_cli_main_writes_library_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tracks_root = root / "tracks"
            tracks_root.mkdir()
            (tracks_root / "Artist - Song.wav").touch()
            script = scan_library.APP_DIR / "scan_library.py"
            library_path = scan_library.APP_DIR / "library.json"
            library_path.unlink(missing_ok=True)
            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--explicit-roots",
                    "--skip-edges",
                    "--tracks-root",
                    str(tracks_root),
                    "--limit",
                    "1",
                ],
                cwd=scan_library.APP_DIR,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
            self.assertTrue(library_path.exists(), "scan_library.py CLI must write library.json")
            library = json.loads(library_path.read_text())
            self.assertEqual(library["track_count"], 1)


if __name__ == "__main__":
    unittest.main()
