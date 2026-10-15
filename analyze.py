"""Lightweight BPM / key / energy analysis for DJ library tracks."""

from __future__ import annotations

from pathlib import Path

import librosa
import numpy as np
import soundfile as sf

from camelot import pitch_class_to_camelot

ANALYSIS_SECONDS = 90
TARGET_SR = 22050
ANALYSIS_VERSION = 14
WAVEFORM_BARS = 400
WAVEFORM_VERSION = 1
BPM_MIN = 70.0
BPM_MAX = 180.0
BPM_MAP_MIN = 70.0
HOP_LENGTH = 512
PHRASE_BARS = 32
BEATS_PER_BAR = 4
FALLBACK_ENERGY_WINDOW_SECONDS = 45.0
MIN_ENERGY_WINDOW_SECONDS = 8.0

# Embedded tags below this are often half-time grids on peak-time electronic tracks.
HALFTIME_TAG_MIN = 68.0
HALFTIME_TAG_MAX = 92.0
FULL_TEMPO_TAG_MIN = 100.0
TECHNO_RAW_CLUSTER_MIN = 130.0
TECHNO_RAW_CLUSTER_MAX = 165.0
AMBIGUOUS_RAW_MIN = 90.0
AMBIGUOUS_RAW_MAX = 110.0

MAJOR_PROFILE = np.array(
    [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
)
MINOR_PROFILE = np.array(
    [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.28, 4.12, 2.52, 5.19, 2.39, 3.67]
)


def _load_mono(path: Path, *, max_seconds: float | None = ANALYSIS_SECONDS) -> tuple[np.ndarray, int]:
    try:
        info = sf.info(path)
        frames = info.frames
        if max_seconds is not None:
            frames = min(frames, int(max_seconds * info.samplerate))
        audio, sr = sf.read(path, frames=frames, always_2d=True)
        mono = np.mean(audio, axis=1)
        if sr != TARGET_SR:
            mono = librosa.resample(mono, orig_sr=sr, target_sr=TARGET_SR)
            sr = TARGET_SR
        return mono.astype(np.float32), sr
    except Exception:
        duration = max_seconds
        mono, sr = librosa.load(
            path, sr=TARGET_SR, mono=True, duration=duration
        )
        return mono, sr


def _detect_key(y: np.ndarray, sr: int) -> tuple[str | None, str | None]:
    if len(y) < sr * 8:
        return None, None
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    chroma_mean = np.mean(chroma, axis=1)
    if np.allclose(chroma_mean, 0):
        return None, None

    best_score = -np.inf
    best_pc = 0
    best_mode = "major"
    for shift in range(12):
        rotated = np.roll(chroma_mean, -shift)
        major_score = float(np.dot(rotated, MAJOR_PROFILE))
        minor_score = float(np.dot(rotated, MINOR_PROFILE))
        if major_score > best_score:
            best_score = major_score
            best_pc = shift
            best_mode = "major"
        if minor_score > best_score:
            best_score = minor_score
            best_pc = shift
            best_mode = "minor"

    camelot = pitch_class_to_camelot(best_pc, best_mode)
    return camelot, best_mode


def _read_tagged_bpm(path: Path) -> float | None:
    """Read embedded BPM from download/store tags (TBPM) when present."""
    try:
        from mutagen import File as MutagenFile

        audio = MutagenFile(path, easy=False)
        if audio is None:
            return None
        for key in ("TBPM", "BPM"):
            if key not in audio:
                continue
            val = audio[key]
            if hasattr(val, "text"):
                raw = val.text[0]
            else:
                raw = val[0] if isinstance(val, list) else val
            bpm = float(str(raw).strip())
            if BPM_MIN <= bpm <= BPM_MAX:
                return round(bpm, 2)
            normalized = _normalize_bpm(bpm)
            if normalized is not None:
                return float(normalized)
    except Exception:
        return None
    return None


def _normalize_bpm(bpm: float) -> float | None:
    if not np.isfinite(bpm) or bpm <= 0:
        return None
    value = float(bpm)
    while value < BPM_MIN:
        value *= 2
    while value > BPM_MAX:
        value /= 2
    if BPM_MIN <= value <= BPM_MAX:
        return round(value, 1)
    return None


def _tempo_candidates(raw_tempos: np.ndarray) -> list[float]:
    candidates: set[float] = set()
    for tempo in np.atleast_1d(raw_tempos):
        if not np.isfinite(tempo) or tempo <= 0:
            continue
        for factor in (0.5, 1.0, 2.0):
            normalized = _normalize_bpm(float(tempo) * factor)
            if normalized is not None:
                candidates.add(normalized)
    return sorted(candidates)


def _score_bpm(onset_env: np.ndarray, sr: int, bpm: float) -> float:
    if len(onset_env) < 3:
        return 0.0
    ac = librosa.autocorrelate(onset_env, max_size=len(onset_env))
    peak = float(np.max(ac))
    if peak <= 0:
        return 0.0
    ac = ac / peak

    lag = 60.0 * sr / (bpm * HOP_LENGTH)
    total = 0.0
    weight = 0.0
    for harmonic, harmonic_weight in ((1.0, 1.0), (2.0, 0.35), (0.5, 0.2)):
        idx = int(round(lag * harmonic))
        if 1 <= idx < len(ac):
            lo = max(0, idx - 2)
            hi = min(len(ac), idx + 3)
            total += harmonic_weight * float(np.max(ac[lo:hi]))
            weight += harmonic_weight
    return total / weight if weight else 0.0


def _double_tag_bpm(tag: float) -> float:
    return round(tag * 2, 1)


def _tempo_near(value: float, target: float) -> bool:
    return abs(value - target) <= max(8.0, target * 0.08)


def _build_bpm_pool(
    raw: float | None, candidates: list[float], tag: float | None
) -> list[float]:
    pool: set[float] = set(candidates or [])
    if raw is not None and np.isfinite(raw):
        for factor in (0.5, 1.0, 2.0):
            normalized = _normalize_bpm(float(raw) * factor)
            if normalized is not None:
                pool.add(normalized)
    if tag is not None:
        pool.add(round(tag, 1))
        normalized_tag = _normalize_bpm(tag)
        if normalized_tag is not None:
            pool.add(normalized_tag)
        if HALFTIME_TAG_MIN <= tag <= HALFTIME_TAG_MAX:
            pool.add(_double_tag_bpm(tag))
    return sorted(bpm for bpm in pool if BPM_MIN <= bpm <= BPM_MAX)


def _rank_bpm_candidates(
    onset_env: np.ndarray, sr: int, pool: list[float]
) -> list[tuple[float, float]]:
    return sorted(
        ((bpm, _score_bpm(onset_env, sr, bpm)) for bpm in pool),
        key=lambda item: (item[1], item[0]),
        reverse=True,
    )


def _has_techno_double_anchor(
    tag: float, raw: float | None, candidates: list[float]
) -> bool:
    if raw is not None and TECHNO_RAW_CLUSTER_MIN <= raw <= TECHNO_RAW_CLUSTER_MAX:
        return True
    if raw is not None and AMBIGUOUS_RAW_MIN <= raw <= AMBIGUOUS_RAW_MAX:
        doubled = _double_tag_bpm(tag)
        return any(
            TECHNO_RAW_CLUSTER_MIN <= candidate <= TECHNO_RAW_CLUSTER_MAX
            and _tempo_near(candidate, doubled)
            for candidate in candidates
        )
    return False


def _resolve_tagged_bpm(
    onset_env: np.ndarray,
    sr: int,
    tag: float,
    raw: float | None,
    candidates: list[float],
) -> tuple[float, float, bool, str]:
    """Resolve BPM when a store/download tag exists."""
    tag = round(tag, 2)

    # Full-tempo tags from Soundeo/Beatport are usually trustworthy in this library.
    if tag >= FULL_TEMPO_TAG_MIN:
        return round(tag, 1), round(tag, 1), False, "tag"

    if HALFTIME_TAG_MIN <= tag <= HALFTIME_TAG_MAX:
        doubled = _double_tag_bpm(tag)
        tag_score = _score_bpm(onset_env, sr, tag)
        double_score = _score_bpm(onset_env, sr, doubled)

        if _has_techno_double_anchor(tag, raw, candidates):
            if double_score >= tag_score * 0.92:
                return doubled, round(tag, 1), True, "tag"
            margin = (tag_score - double_score) / tag_score if tag_score else 0.0
            if margin <= 0.13:
                return doubled, round(tag, 1), True, "tag"
            if (
                raw is not None
                and AMBIGUOUS_RAW_MIN <= raw <= AMBIGUOUS_RAW_MAX
                and margin <= 0.16
            ):
                return doubled, round(tag, 1), True, "tag"

        if (
            raw is not None
            and 166.0 <= raw <= 180.0
            and _tempo_near(raw, doubled)
            and double_score >= tag_score
            and _has_techno_double_anchor(tag, raw, candidates)
        ):
            return doubled, round(tag, 1), True, "tag"

        if double_score > tag_score * 1.15 and _has_techno_double_anchor(
            tag, raw, candidates
        ):
            return doubled, round(tag, 1), True, "tag"

        return round(tag, 1), round(tag, 1), False, "tag"

    return round(tag, 1), round(tag, 1), False, "tag"


def _resolve_analysis_bpm(
    onset_env: np.ndarray,
    sr: int,
    raw: float | None,
    candidates: list[float],
) -> tuple[float | None, float | None, bool]:
    """Resolve BPM from audio when no embedded tag exists."""
    pool = _build_bpm_pool(raw, candidates, None)
    if not pool:
        if raw is None:
            return None, None, False
        normalized = _normalize_bpm(float(raw))
        return normalized, round(float(raw), 1), False

    ranked = _rank_bpm_candidates(onset_env, sr, pool)
    best, best_score = ranked[0]
    octave_fixed = False

    # Lift to faster octave only for clear club-tempo grids (psy/techno/house).
    if raw is not None and np.isfinite(raw):
        raw_norm = _normalize_bpm(float(raw))
        if raw_norm is not None and best < raw_norm * 0.78:
            raw_score = _score_bpm(onset_env, sr, raw_norm)
            if 118.0 <= raw_norm <= 155.0 and raw_score >= best_score * 0.93:
                octave_fixed = True
                best = raw_norm
                best_score = raw_score
            elif (
                118.0 <= raw_norm <= 132.0
                and best <= 95.0
                and raw_score >= best_score * 0.82
            ):
                octave_fixed = True
                best = raw_norm
                best_score = raw_score

    # Librosa often doubles downtempo/organic (~82 heard as ~164).
    if best > 150.0:
        half = round(best / 2, 1)
        if 70.0 <= half <= 95.0:
            half_score = _score_bpm(onset_env, sr, half)
            if half_score >= best_score * 0.95:
                best = half
                best_score = half_score
                octave_fixed = True

    # Untagged psy/techno can score oddly on half-time; prefer floor tempo when close.
    if best < 78.0:
        for candidate, score in ranked:
            if 136.0 <= candidate <= 148.0 and score >= best_score * 0.80:
                if candidate != best:
                    octave_fixed = True
                best = candidate
                best_score = score
                break

    if (
        raw is not None
        and np.isfinite(raw)
        and best <= 95.0
        and float(raw) >= 150.0
        and best < float(raw) * 0.6
    ):
        octave_fixed = True

    return round(best, 1), round(float(raw), 1) if raw is not None else None, octave_fixed


def _detect_bpm(
    y: np.ndarray, sr: int
) -> tuple[float | None, float | None, bool, np.ndarray, list[float]]:
    if len(y) < sr * 8:
        return None, None, False, np.array([]), []

    onset_env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=HOP_LENGTH)
    tempos = librosa.feature.tempo(
        onset_envelope=onset_env,
        sr=sr,
        hop_length=HOP_LENGTH,
        aggregate=None,
        max_tempo=220,
    )
    flat = np.atleast_1d(tempos).astype(float)
    if flat.size == 0:
        return None, None, False, onset_env, []
    raw_bpm = float(flat[0])
    candidates = _tempo_candidates(flat)
    bpm, _, octave_fixed = _resolve_analysis_bpm(
        onset_env, sr, raw_bpm, candidates
    )
    return bpm, round(raw_bpm, 1), octave_fixed, onset_env, candidates


def _clip01(value: float) -> float:
    return float(np.clip(value, 0.0, 1.0))


def _harmonic_voiced_strength(y_harm: np.ndarray, sr: int) -> float:
    """Estimate tonal voicing via harmonic periodicity (avoids librosa.yin native crashes)."""
    window = min(len(y_harm), sr * 12)
    segment = y_harm[:window]
    if len(segment) < sr // 2:
        return 0.0
    ac = librosa.autocorrelate(segment, max_size=sr // 4)
    if len(ac) < 3:
        return 0.0
    ac = ac / (float(ac[0]) + 1e-9)
    peak = float(np.max(ac[1:]))
    return _clip01((peak - 0.15) / 0.55)


def _detect_vocals(y: np.ndarray, sr: int) -> tuple[str, float | None]:
    """Heuristic vocal presence: yes, no, or unclear, plus confidence in that label."""
    if len(y) < sr * 8:
        return "unclear", None

    vocal_window = sr * 45
    if len(y) > vocal_window:
        y = y[:vocal_window]

    y_harm, y_perc = librosa.effects.hpss(y, margin=2.0)
    harm_rms = float(np.sqrt(np.mean(y_harm**2)))
    perc_rms = float(np.sqrt(np.mean(y_perc**2)))
    harm_ratio = harm_rms / (harm_rms + perc_rms + 1e-9)

    mel = librosa.feature.melspectrogram(y=y_harm, sr=sr, n_mels=48, fmax=6000)
    mel_db = librosa.power_to_db(mel, ref=np.max)
    mel_mean = np.mean(mel_db, axis=1)
    vocal_band = float(np.mean(mel_mean[5:28]))
    edge_band = float(np.mean(np.concatenate([mel_mean[:5], mel_mean[28:]])))
    vocal_contrast = vocal_band - edge_band

    voiced_strength = _harmonic_voiced_strength(y_harm, sr)

    flatness = librosa.feature.spectral_flatness(y=y_harm)[0]
    tonal_harm = _clip01(1.0 - float(np.mean(flatness)) * 10.0)

    vocal_score = (
        0.28 * _clip01((harm_ratio - 0.52) / 0.22)
        + 0.28 * _clip01((vocal_contrast - 1.5) / 4.0)
        + 0.30 * _clip01((voiced_strength - 0.12) / 0.28)
        + 0.14 * tonal_harm
    )
    inst_score = (
        0.40 * _clip01((0.48 - harm_ratio) / 0.18)
        + 0.35 * _clip01((0.08 - voiced_strength) / 0.08)
        + 0.25 * _clip01((2.0 - vocal_contrast) / 2.0)
    )

    if (
        vocal_score >= 0.58
        and vocal_score >= inst_score + 0.15
        and voiced_strength >= 0.2
        and vocal_contrast >= 2.0
    ):
        conf = _clip01(0.45 + (vocal_score - 0.58) * 1.2)
        return "yes", round(conf, 3)
    if inst_score >= 0.52 and inst_score >= vocal_score + 0.15:
        conf = _clip01(0.45 + (inst_score - 0.52) * 1.1)
        return "no", round(conf, 3)
    spread = abs(vocal_score - inst_score)
    conf = round(_clip01(0.35 + spread * 0.5), 3)
    return "unclear", conf


def _normalize_waveform_display(values: np.ndarray) -> None:
    sorted_vals = np.sort(values)
    n = len(sorted_vals)
    if n == 0:
        return
    p5 = sorted_vals[int(n * 0.05)]
    p95 = sorted_vals[int(n * 0.95)]
    span = max(float(p95 - p5), 1e-6)
    floor = 0.05
    gamma = 0.62
    for i in range(n):
        v = (float(values[i]) - p5) / span
        v = _clip01(v)
        v = v**gamma
        values[i] = floor + v * (1.0 - floor)


def _compute_waveform_peaks(y: np.ndarray, sr: int, bar_count: int = WAVEFORM_BARS) -> dict | None:
    if len(y) < sr:
        return None

    per_bar = max(1, len(y) // bar_count)
    peak = np.zeros(bar_count, dtype=np.float32)
    low = np.zeros(bar_count, dtype=np.float32)
    mid = np.zeros(bar_count, dtype=np.float32)
    high = np.zeros(bar_count, dtype=np.float32)
    alpha_low = 1 - np.exp((-2 * np.pi * 280) / sr)
    alpha_high = 1 - np.exp((-2 * np.pi * 4200) / sr)
    lp = 0.0
    hp = 0.0

    for j, x in enumerate(y):
        bar = min(bar_count - 1, j // per_bar)
        peak[bar] += x * x
        lp += alpha_low * (x - lp)
        low_sig = lp
        hp += alpha_high * (x - hp)
        high_sig = x - hp
        mid_sig = x - low_sig - high_sig
        low[bar] += low_sig * low_sig
        mid[bar] += mid_sig * mid_sig
        high[bar] += high_sig * high_sig

    for i in range(bar_count):
        n = min(per_bar, len(y) - i * per_bar)
        peak[i] = np.sqrt(peak[i] / n)
        low[i] = np.sqrt(low[i] / n)
        mid[i] = np.sqrt(mid[i] / n)
        high[i] = np.sqrt(high[i] / n)

    _normalize_waveform_display(peak)
    top_band = float(np.max(low + mid + high))
    if top_band > 0:
        low /= top_band
        mid /= top_band
        high /= top_band

    return {
        "version": WAVEFORM_VERSION,
        "bars": bar_count,
        "peak": [round(float(v), 5) for v in peak],
        "low": [round(float(v), 5) for v in low],
        "mid": [round(float(v), 5) for v in mid],
        "high": [round(float(v), 5) for v in high],
    }


def _detect_energy_value(y: np.ndarray, sr: int) -> float:
    if len(y) < sr:
        return 0.5
    rms = librosa.feature.rms(y=y)[0]
    centroid = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
    rms_n = float(np.clip(np.mean(rms) * 8, 0, 1))
    cent_n = float(np.clip(np.mean(centroid) / 5000, 0, 1))
    flux = librosa.onset.onset_strength(y=y, sr=sr)
    flux_n = float(np.clip(np.std(flux) * 4, 0, 1))
    return round(0.5 * rms_n + 0.35 * cent_n + 0.15 * flux_n, 3)


def _energy_window_seconds(bpm: float | None) -> float:
    if bpm is None or not np.isfinite(bpm) or bpm <= 0:
        return FALLBACK_ENERGY_WINDOW_SECONDS
    return PHRASE_BARS * BEATS_PER_BAR * 60.0 / float(bpm)


def _detect_energy_profile(y: np.ndarray, sr: int, bpm: float | None = None) -> dict:
    if len(y) < sr:
        return {
            "energy": 0.5,
            "energy_auto": 0.5,
            "energy_effective": 0.5,
            "energy_main": 0.5,
            "energy_avg": 0.5,
            "energy_peak": 0.5,
            "energy_intro": 0.5,
            "energy_outro": 0.5,
            "energy_confidence": 0.0,
            "energy_curve": [],
        }

    window_seconds = _energy_window_seconds(bpm)
    window_samples = max(int(MIN_ENERGY_WINDOW_SECONDS * sr), int(window_seconds * sr))
    min_samples = int(MIN_ENERGY_WINDOW_SECONDS * sr)
    scores: list[float] = []

    for start in range(0, len(y), window_samples):
        segment = y[start : start + window_samples]
        if len(segment) < min_samples and scores:
            break
        if len(segment) >= sr:
            scores.append(_detect_energy_value(segment, sr))

    if not scores:
        scores = [_detect_energy_value(y, sr)]

    values = np.asarray(scores, dtype=float)
    core = values[1:-1] if len(values) >= 4 else values
    energy_main = float(np.median(core))
    energy_avg = float(np.mean(values))
    energy_peak = float(np.percentile(values, 90))
    energy_intro = float(values[0])
    energy_outro = float(values[-1])
    energy_auto = float(np.clip(0.55 * energy_main + 0.25 * energy_avg + 0.20 * energy_peak, 0, 1))

    spread = float(np.std(values))
    coverage = min(1.0, len(values) / 6.0)
    confidence = float(np.clip(0.35 + coverage * 0.45 - spread * 0.45, 0.05, 0.95))

    return {
        "energy": round(energy_auto, 3),
        "energy_auto": round(energy_auto, 3),
        "energy_effective": round(energy_auto, 3),
        "energy_main": round(energy_main, 3),
        "energy_avg": round(energy_avg, 3),
        "energy_peak": round(energy_peak, 3),
        "energy_intro": round(energy_intro, 3),
        "energy_outro": round(energy_outro, 3),
        "energy_confidence": round(confidence, 3),
        "energy_curve": [round(float(v), 3) for v in values],
    }


def _detect_energy(y: np.ndarray, sr: int) -> float:
    return _detect_energy_value(y, sr)


def analyze_track_energy(path: Path, bpm: float | None = None) -> dict:
    try:
        y, sr = _load_mono(path, max_seconds=None)
        return _detect_energy_profile(y, sr, bpm)
    except Exception as exc:
        return {
            "energy": 0.5,
            "energy_auto": 0.5,
            "energy_effective": 0.5,
            "energy_main": 0.5,
            "energy_avg": 0.5,
            "energy_peak": 0.5,
            "energy_intro": 0.5,
            "energy_outro": 0.5,
            "energy_confidence": 0.0,
            "energy_curve": [],
            "analysis_error": str(exc),
        }


def _estimate_bpm_confidence(
    onset_env: np.ndarray, sr: int, bpm: float | None, pool: list[float]
) -> float | None:
    if bpm is None or not pool:
        return None
    ranked = _rank_bpm_candidates(onset_env, sr, pool)
    if not ranked:
        return None
    chosen_score = next((score for candidate, score in ranked if candidate == bpm), ranked[0][1])
    if chosen_score <= 0:
        return None
    others = [score for candidate, score in ranked if candidate != bpm]
    second_score = max(others) if others else 0.0
    margin = max(0.0, (chosen_score - second_score) / chosen_score)
    return round(min(1.0, 0.35 + margin * 0.65), 3)


def analyze_track(path: Path) -> dict:
    duration_sec = None
    try:
        duration_sec = round(sf.info(path).duration, 2)
    except Exception:
        pass

    try:
        y, sr = _load_mono(path)
    except Exception as exc:
        return {
            "analysis_version": ANALYSIS_VERSION,
            "duration_sec": duration_sec,
            "bpm": None,
            "bpm_raw": None,
            "bpm_octave_corrected": False,
            "bpm_source": None,
            "bpm_confidence": None,
            "key": None,
            "energy": 0.5,
            "energy_auto": 0.5,
            "energy_effective": 0.5,
            "energy_main": 0.5,
            "energy_avg": 0.5,
            "energy_peak": 0.5,
            "energy_intro": 0.5,
            "energy_outro": 0.5,
            "energy_confidence": 0.0,
            "energy_curve": [],
            "vocals": "unclear",
            "vocals_confidence": None,
            "waveform": None,
            "analysis_error": str(exc),
        }

    vocals, vocals_confidence = _detect_vocals(y, sr)
    waveform = _compute_waveform_peaks(y, sr)
    bpm, bpm_raw, bpm_octave_corrected, onset_env, tempo_candidates = _detect_bpm(y, sr)
    bpm_source = "analysis"

    tagged = _read_tagged_bpm(path)
    if tagged is not None:
        bpm, bpm_raw, bpm_octave_corrected, bpm_source = _resolve_tagged_bpm(
            onset_env, sr, tagged, bpm_raw, tempo_candidates
        )

    pool = _build_bpm_pool(bpm_raw, tempo_candidates, tagged)
    bpm_confidence = _estimate_bpm_confidence(onset_env, sr, bpm, pool)
    energy_profile = analyze_track_energy(path, bpm)
    if energy_profile.get("analysis_error"):
        energy_profile = _detect_energy_profile(y, sr, bpm)

    return {
        "analysis_version": ANALYSIS_VERSION,
        "duration_sec": duration_sec,
        "bpm": bpm,
        "bpm_raw": bpm_raw,
        "bpm_octave_corrected": bpm_octave_corrected,
        "bpm_source": bpm_source,
        "bpm_confidence": bpm_confidence,
        "key": _detect_key(y, sr)[0],
        **energy_profile,
        "vocals": vocals,
        "vocals_confidence": vocals_confidence,
        "waveform": waveform,
        "analysis_error": None,
    }
