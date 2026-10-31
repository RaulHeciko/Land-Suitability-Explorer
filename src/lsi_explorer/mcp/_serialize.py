"""Error handling and JSON serialization for MCP tools (same contract as eocube.mcp)."""

from __future__ import annotations

import functools
import math
from pathlib import Path


def error_result(operation: str, exc: Exception) -> dict:
    """Structured error returned instead of raising (``{"ok": false, ...}``)."""
    not_found = (
        isinstance(exc, (FileNotFoundError, KeyError))
        or "not found" in str(exc).lower()
    )
    return {
        "ok": False,
        "error": f"{operation}: {exc}",
        "status": 404 if not_found else 400 if isinstance(exc, ValueError) else 500,
        "not_found": not_found,
    }


def guarded(operation: str):
    """Decorator: a tool never raises; any exception becomes an ``error_result`` dict."""

    def wrap(func):
        @functools.wraps(func)
        def inner(*args, **kwargs) -> dict:
            try:
                return func(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001 - tools must never raise
                return error_result(operation, exc)

        return inner

    return wrap


def jsonable(value):
    """Recursively convert paths, numpy scalars/arrays and NaN into JSON-safe values."""
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "tolist"):
        return jsonable(value.tolist())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value
