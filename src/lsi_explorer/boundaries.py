"""Romanian county (judet) and UAT boundaries for the area filter.

Uses the same public geo-spatial.org WFS layers as eocube.services.geospatialorg
(geospatial:ro_judete_poligon and geospatial:ro_uat_poligon). Only the attributes the
dashboard needs are kept and outlines are simplified by 20 m (well below the 100 m pixel).
CLI: ``lsi admin fetch-boundaries``; MCP: ``admin_fetch_boundaries``.
"""

from __future__ import annotations

from pathlib import Path

from .utils import ADMIN_DIR, get_logger

log = get_logger()

WFS = "https://services.geo-spatial.org/geoserver/ows"
LAYERS = {
    "judete": ("geospatial:ro_judete_poligon", ["name", "mnemonic"]),
    "uat": ("geospatial:ro_uat_poligon", ["name", "natLevName", "county", "natcode"]),
}
TOLERANCE_M = 20


def wfs_url(layer: str, endpoint: str = WFS) -> str:
    """GetFeature URL returning every feature of `layer` as GeoJSON in EPSG:4326."""
    return (
        f"{endpoint}?service=WFS&version=1.1.0&request=GetFeature&typeName={layer}"
        "&outputFormat=application/json&srsName=EPSG:4326"
    )


def tidy(gdf, columns: list[str], tolerance_m: float = TOLERANCE_M):
    """Keep `columns`, simplify outlines in Stereo70 metres and return in EPSG:3844."""
    gdf = gdf[columns + ["geometry"]].to_crs(3844)
    gdf["geometry"] = gdf.geometry.simplify(tolerance_m, preserve_topology=True)
    return gdf


def fetch(out_dir: Path | None = None) -> dict[str, Path]:
    """Download all layers to ``<out_dir>/<name>.gpkg`` (default: data/admin).

    :return: ``{"judete": path, "uat": path}``
    """
    import geopandas as gpd

    out_dir = Path(out_dir) if out_dir else ADMIN_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    written = {}
    for name, (layer, columns) in LAYERS.items():
        gdf = tidy(gpd.read_file(wfs_url(layer)), columns)
        path = out_dir / f"{name}.gpkg"
        gdf.to_file(path, driver="GPKG")
        written[name] = path
        log.info("%s: %d features -> %s", name, len(gdf), path)
    return written
