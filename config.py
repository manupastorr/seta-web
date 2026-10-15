"""Local paths and settings for Seta (override via env or .env)."""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_TRACKS_ROOT = Path.home() / "Music" / "tracks"
DEFAULT_CURATE_ROOT = Path.home() / "Downloads" / "To Curate"
DEFAULT_PORT = 8765


def _load_dotenv() -> None:
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


_load_dotenv()


def _resolve_path(raw: str) -> Path:
    return Path(raw).expanduser().resolve()


def _path_from_env(name: str, default: Path) -> Path:
    raw = os.environ.get(name)
    if not raw:
        return default.expanduser().resolve()
    return _resolve_path(raw)


def _split_path_list(raw: str) -> list[str]:
    """Split env list on os.pathsep or newline."""
    parts: list[str] = []
    for chunk in raw.replace("\n", os.pathsep).split(os.pathsep):
        item = chunk.strip()
        if item:
            parts.append(item)
    return parts


def _paths_from_env_list(list_name: str, single_name: str, default: Path) -> list[Path]:
    plural = os.environ.get(list_name)
    if plural:
        paths = [_resolve_path(item) for item in _split_path_list(plural)]
        return _dedupe_paths(paths)
    return [_path_from_env(single_name, default)]


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    out: list[Path] = []
    for path in paths:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        out.append(path)
    return out


def tracks_root() -> Path:
    return _path_from_env("SETA_TRACKS_ROOT", DEFAULT_TRACKS_ROOT)


def curate_root() -> Path:
    return _path_from_env("SETA_CURATE_ROOT", DEFAULT_CURATE_ROOT)


def tracks_roots() -> list[Path]:
    return _paths_from_env_list("SETA_TRACKS_ROOTS", "SETA_TRACKS_ROOT", DEFAULT_TRACKS_ROOT)


def curate_roots() -> list[Path]:
    return _paths_from_env_list("SETA_CURATE_ROOTS", "SETA_CURATE_ROOT", DEFAULT_CURATE_ROOT)


def allowed_roots() -> tuple[Path, ...]:
    return tuple(tracks_roots() + curate_roots())


def port() -> int:
    return int(os.environ.get("SETA_PORT", DEFAULT_PORT))


def host() -> str:
    """Interface to listen on: 127.0.0.1 (this Mac only) unless SETA_HOST says otherwise, e.g. 0.0.0.0 for the home network."""
    return os.environ.get("SETA_HOST", "127.0.0.1")


def rekordbox_xml_path() -> Path:
    """Where Arrange's Export XML writes, always the same file, so rekordbox's "Imported Library" keeps pointing at it."""
    return _path_from_env("SETA_RB_XML", Path.home() / "Music" / "rekordbox" / "seta.xml")


KEEP_EXPORTS = 20  # dated copies of earlier exports kept next to seta.xml, in seta-exports/


def arrange_only() -> bool:
    """SETA_ARRANGE_ONLY=1 serves just the Arrange page and the read-only routes it needs."""
    return os.environ.get("SETA_ARRANGE_ONLY", "0").strip().lower() in {"1", "true", "yes", "on"}
