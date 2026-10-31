"""Helpers for the county (judet) / UAT spatial filter of the dashboard."""

from __future__ import annotations


def uats_in_county(uats, judete, county: str):
    """UATs belonging to `county` (by name): uses the UAT 'county' attribute when present,
    otherwise a point-in-polygon test against the county outline."""
    if "county" in uats.columns:
        return uats[uats["county"].astype(str).str.strip() == county]
    outline = judete[judete._label == county].union_all()
    return uats[uats.representative_point().within(outline)]


def option_index(options: list, value, default: int = 0) -> int:
    """Position of `value` in `options` (e.g. a choice read from the page URL), else `default`."""
    try:
        return list(options).index(value)
    except ValueError:
        return default


UAT_TYPES = {
    "Comuna": "Comuna",
    "Oras": "Ora\u0219",
    "Municipiu": "Municipiu",
    "Sectoarele": "Sector",
}


def uat_type(kind) -> str:
    """Short UAT type from the long geo-spatial.org name, e.g.
    'Municipiu, altul decat resedinta de judet' -> 'Municipiu'."""
    if not isinstance(kind, str) or not kind:
        return ""
    return next((v for k, v in UAT_TYPES.items() if kind.startswith(k)), kind)


def uat_label(row) -> str:
    """Display name of a UAT, e.g. 'Lugoj (Municipiu)'."""
    kind = uat_type(row.get("natLevName"))
    return f"{row['_label']} ({kind})" if kind else row["_label"]
