"""Download Romanian county (judet) and UAT boundaries into data/admin/ for the dashboard filter.

Uses the same public geo-spatial.org WFS layers as eocube.services.geospatialorg
(geospatial:ro_judete_poligon and geospatial:ro_uat_poligon). Only the attributes the
dashboard needs are kept and outlines are simplified by 20 m (well below the 100 m pixel).

    python scripts/fetch_admin_boundaries.py [--out data/admin]
"""

from __future__ import annotations

import argparse
from pathlib import Path

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


def fetch(out_dir: Path) -> dict[str, Path]:
    """Download all layers to <out_dir>/<name>.gpkg; returns the written paths."""
    import geopandas as gpd

    out_dir.mkdir(parents=True, exist_ok=True)
    written = {}
    for name, (layer, columns) in LAYERS.items():
        gdf = tidy(gpd.read_file(wfs_url(layer)), columns)
        path = out_dir / f"{name}.gpkg"
        gdf.to_file(path, driver="GPKG")
        written[name] = path
        print(f"{name}: {len(gdf)} features -> {path}")
    return written


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--out", default=str(Path(__file__).resolve().parents[1] / "data" / "admin")
    )
    fetch(Path(ap.parse_args(argv).out))


if __name__ == "__main__":
    main()
