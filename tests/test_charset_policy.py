"""Enforce the EOCube character-set policy: source, config and README files are ASCII only."""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CHECKED_SUFFIXES = {
    ".py",
    ".md",
    ".txt",
    ".toml",
    ".cfg",
    ".ini",
    ".yml",
    ".yaml",
    ".json",
}
SKIPPED_DIRS = {
    ".venv",
    "venv",
    "LSI",
    "data",
    "results",
    "__pycache__",
    ".git",
    ".pytest_cache",
}


def _project_files():
    """Text files that belong to the project (inputs, outputs and environments excluded)."""
    for path in ROOT.rglob("*"):
        rel = path.relative_to(ROOT)
        if (
            path.is_file()
            and path.suffix in CHECKED_SUFFIXES
            and not SKIPPED_DIRS & set(rel.parts)
        ):
            yield path


@pytest.mark.parametrize(
    "path", list(_project_files()), ids=lambda p: str(p.relative_to(ROOT))
)
def test_file_is_ascii(path):
    text = path.read_text(encoding="utf-8")
    bad = [
        (i + 1, line) for i, line in enumerate(text.splitlines()) if not line.isascii()
    ]
    assert (
        not bad
    ), f"non-ASCII characters in {path.name}: lines {[n for n, _ in bad][:10]}"
