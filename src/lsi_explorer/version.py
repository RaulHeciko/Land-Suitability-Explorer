"""Package version and build provenance (same scheme as eocube.version).

``format_version_string()`` -> ``lsi-explorer <pep440>, commit <sha12> (clean|dirty)``. The
commit comes from ``_build_info`` when stamped at build time, otherwise from a live
``git rev-parse`` against the working tree (editable checkouts).
"""

from __future__ import annotations

import subprocess
from importlib import metadata
from pathlib import Path

DIST_NAME = "lsi-explorer"


def package_version() -> str:
    """Installed distribution version, or ``0+unknown`` when running from a plain checkout."""
    try:
        return metadata.version(DIST_NAME)
    except metadata.PackageNotFoundError:
        return "0+unknown"


def _git(*args: str) -> str | None:
    try:
        out = subprocess.run(
            ["git", *args],
            cwd=Path(__file__).resolve().parent,
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip()


def build_commit() -> tuple[str | None, bool | None]:
    """(commit sha, dirty flag): stamped values first, then the live git working tree."""
    from . import _build_info

    if _build_info.COMMIT:
        return _build_info.COMMIT, bool(_build_info.DIRTY)
    sha = _git("rev-parse", "HEAD")
    if not sha:
        return None, None
    status = _git("status", "--porcelain", "--untracked-files=no")
    return sha, bool(status)


def format_version_string() -> str:
    """Human-readable version line used by ``lsi --version``."""
    text = f"{DIST_NAME} {package_version()}"
    sha, dirty = build_commit()
    if sha:
        text += f", commit {sha[:12]} ({'dirty' if dirty else 'clean'})"
    return text


__version__ = package_version()
