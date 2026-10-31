"""County (judet) / UAT boundaries: loading, filtering and area selection."""

from __future__ import annotations

from .utils import admin_layer_path

LABEL_CANDIDATES = [
    "name",
    "nume",
    "denumire",
    "judet",
    "county",
    "uat",
    "name_2",
    "name_1",
    "shapename",
    "natlevname",
    "nat_name",
    "localitate",
]


def load_admin_layer(level: str, crs):
    """Boundary layer for `level` ('judet' or 'uat') reprojected to `crs`, with a `_label`
    column holding the unit name; ``None`` when no boundary file is available."""
    path = admin_layer_path(level)
    if path is None:
        return None
    import geopandas as gpd

    gdf = gpd.read_file(path)
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    gdf = gdf.to_crs(crs)
    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].reset_index(drop=True)
    lower = {c.lower(): c for c in gdf.columns}
    col = next((lower[c] for c in LABEL_CANDIDATES if c in lower), None)
    if col is None:
        col = next(c for c in gdf.columns if c != "geometry" and gdf[c].dtype == object)
    gdf["_label"] = gdf[col].astype(str).str.strip()
    return gdf


def select_area(judete, uats, judet: str | None = None, uat: str | None = None):
    """Geometry and display name for a county or a UAT (``uat`` as 'Name' or 'Name (Type)').

    :return: ``(geometry, name)``; ``(None, "")`` for the whole study area
    :raises ValueError: when the boundaries are missing or the unit is not found
    """
    if not judet and not uat:
        return None, ""
    if uat:
        if uats is None:
            raise ValueError(
                "UAT boundaries not available (run: lsi admin fetch-boundaries)"
            )
        pool = (
            uats_in_county(uats, judete, judet)
            if judet and judete is not None
            else uats
        )
        labels = pool.apply(uat_label, axis=1)
        hit = pool[(labels == uat) | (pool["_label"] == uat)]
        if hit.empty:
            raise ValueError(f"UAT not found: {uat}")
        if len(hit) > 1:
            raise ValueError(f"UAT name is ambiguous, add the county: {uat}")
        return hit.geometry.iloc[0], f"UAT {uat_label(hit.iloc[0])}"
    if judete is None:
        raise ValueError(
            "County boundaries not available (run: lsi admin fetch-boundaries)"
        )
    hit = judete[judete._label == judet]
    if hit.empty:
        raise ValueError(f"County not found: {judet}")
    return hit.union_all(), f"Judet {judet}"


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
