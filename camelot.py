"""Camelot wheel helpers."""

from __future__ import annotations

MINOR_PC_TO_CAMELOT: dict[int, str] = {
    0: "5A",
    1: "12A",
    2: "7A",
    3: "2A",
    4: "9A",
    5: "4A",
    6: "11A",
    7: "6A",
    8: "1A",
    9: "8A",
    10: "3A",
    11: "10A",
}

MAJOR_PC_TO_CAMELOT: dict[int, str] = {
    0: "8B",
    1: "3B",
    2: "10B",
    3: "5B",
    4: "12B",
    5: "7B",
    6: "2B",
    7: "9B",
    8: "4B",
    9: "11B",
    10: "6B",
    11: "1B",
}

CAMELOT_NUMBER: dict[str, int] = {}

for i in range(1, 13):
    CAMELOT_NUMBER[f"{i}A"] = i
    CAMELOT_NUMBER[f"{i}B"] = i

# Spotify-style wheel colors (A = deeper, B = lighter).
CAMELOT_COLORS: dict[str, str] = {
    "1A": "#C62828",
    "1B": "#EF5350",
    "2A": "#E65100",
    "2B": "#FF9800",
    "3A": "#F57F17",
    "3B": "#FFCA28",
    "4A": "#9E9D24",
    "4B": "#CDDC39",
    "5A": "#558B2F",
    "5B": "#8BC34A",
    "6A": "#2E7D32",
    "6B": "#66BB6A",
    "7A": "#00695C",
    "7B": "#26A69A",
    "8A": "#00838F",
    "8B": "#4DD0E1",
    "9A": "#1565C0",
    "9B": "#42A5F5",
    "10A": "#4527A0",
    "10B": "#7E57C2",
    "11A": "#6A1B9A",
    "11B": "#AB47BC",
    "12A": "#AD1457",
    "12B": "#EC407A",
}

UNKNOWN_COLOR = "#555770"


def pitch_class_to_camelot(pitch_class: int, mode: str = "minor") -> str:
    pc = pitch_class % 12
    if mode == "major":
        return MAJOR_PC_TO_CAMELOT[pc]
    return MINOR_PC_TO_CAMELOT[pc]


def camelot_color(code: str | None) -> str:
    if not code:
        return UNKNOWN_COLOR
    return CAMELOT_COLORS.get(code.upper(), UNKNOWN_COLOR)


def camelot_compatible(a: str | None, b: str | None) -> float:
    if not a or not b:
        return 0.0
    a = a.upper()
    b = b.upper()
    if a == b:
        return 1.0
    na, la = a[:-1], a[-1]
    nb, lb = b[:-1], b[-1]
    if na == nb and la != lb:
        return 0.82
    try:
        diff = abs(int(na) - int(nb))
    except ValueError:
        return 0.0
    diff = min(diff, 12 - diff)
    if la == lb and diff == 1:
        return 0.72
    if diff == 1:
        return 0.55
    return 0.0


def bpm_compatible(bpm_a: float | None, bpm_b: float | None) -> float:
    if bpm_a is None or bpm_b is None:
        return 0.35
    diff = abs(bpm_a - bpm_b)
    if diff <= 1:
        return 1.0
    if diff <= 2:
        return 0.9
    if diff <= 4:
        return 0.7
    if diff <= 6:
        return 0.45
    return 0.0


def mix_score(
    key_a: str | None,
    key_b: str | None,
    bpm_a: float | None,
    bpm_b: float | None,
) -> float:
    harmonic = camelot_compatible(key_a, key_b)
    if harmonic <= 0:
        return 0.0
    return harmonic * bpm_compatible(bpm_a, bpm_b)
