"""Server-side JSON hand-off for large MCP results (same pattern as eocube.mcp._artifacts).

A producing tool writes the full payload with ``save_json`` and returns a compact summary
plus the path; a consuming tool reads it back with ``load_json``. Set
``LSI_MCP_ARTIFACT_DIR`` (or ``EOCUBE_MCP_ARTIFACT_DIR``) to a shared volume when several
server replicas must see the same files.
"""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from pathlib import Path


def artifact_dir() -> Path:
    """Folder where artifacts are written (created on demand)."""
    base = os.environ.get("LSI_MCP_ARTIFACT_DIR") or os.environ.get(
        "EOCUBE_MCP_ARTIFACT_DIR"
    )
    path = Path(base) if base else Path(tempfile.gettempdir()) / "lsi-mcp-artifacts"
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_json(payload, prefix: str) -> Path:
    """Write `payload` to a new JSON artifact file and return its path."""
    path = artifact_dir() / f"{prefix}-{uuid.uuid4().hex[:12]}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def resolve_json(path: str | os.PathLike) -> Path:
    """Artifact path, accepting either a full path or a bare file name in the artifact dir."""
    p = Path(path)
    if not p.is_absolute() and not p.exists():
        p = artifact_dir() / p
    if not p.exists():
        raise FileNotFoundError(f"artifact not found: {path}")
    return p


def load_json(path: str | os.PathLike):
    """Read an artifact written by ``save_json``."""
    return json.loads(resolve_json(path).read_text(encoding="utf-8"))
