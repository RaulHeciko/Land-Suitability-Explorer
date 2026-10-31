"""Localization of user-facing strings (same model as eocube.common.i18n).

Strings live in ``lsi_explorer/locales/{lang}.yml`` under a top-level language key and are
looked up with ``t("dot.path", **kwargs)``. The language is detected from ``EOCUBE_LANG``,
then ``LC_ALL`` / ``LC_MESSAGES`` / ``LANG`` (``C`` / ``POSIX`` skipped), then
``locale.getlocale()``, falling back to ``en``. Only the first two letters are kept.
"""

from __future__ import annotations

import locale
import os
from contextvars import ContextVar
from functools import lru_cache
from pathlib import Path

DEFAULT_LANGUAGE = "en"
LOCALES_DIR = Path(__file__).resolve().parent / "locales"

# Per thread / task override, so concurrent dashboard sessions never share a language.
_current: ContextVar[str | None] = ContextVar("lsi_language", default=None)


def _normalize(value: str | None) -> str | None:
    if not value:
        return None
    code = value.split(".")[0].split("_")[0].split("-")[0].strip().lower()
    if not code or code in ("c", "posix"):
        return None
    return code[:2]


def detect_language() -> str:
    """Language code from the environment / system locale, defaulting to ``en``."""
    for var in ("EOCUBE_LANG", "LC_ALL", "LC_MESSAGES", "LANG"):
        code = _normalize(os.environ.get(var))
        if code:
            return code
    try:
        code = _normalize(locale.getlocale()[0])
    except ValueError:
        code = None
    return code or DEFAULT_LANGUAGE


def available_languages() -> list[str]:
    """Language codes that have a locale file."""
    return sorted(p.stem for p in LOCALES_DIR.glob("*.yml"))


@lru_cache(maxsize=None)
def _catalog(lang: str) -> dict:
    import yaml

    path = LOCALES_DIR / f"{lang}.yml"
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data.get(lang, {})


def set_language(lang: str | None) -> None:
    """Override the detected language for the current thread / task (``None`` restores
    detection)."""
    _current.set(_normalize(lang) if lang else None)


def get_language() -> str:
    """Active language: explicit override, else detected, else ``en``."""
    lang = _current.get() or detect_language()
    return lang if lang in available_languages() else DEFAULT_LANGUAGE


def _lookup(catalog: dict, path: str):
    node = catalog
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node if isinstance(node, str) else None


def t(key: str, /, **kwargs) -> str:
    """Translated string for the dotted ``key``; falls back to English, then to the key.

    ``kwargs`` are interpolated with ``str.format`` (any placeholder name, ``path`` included).
    """
    text = _lookup(_catalog(get_language()), key)
    if text is None:
        text = _lookup(_catalog(DEFAULT_LANGUAGE), key)
    if text is None:
        return key
    return text.format(**kwargs) if kwargs else text
