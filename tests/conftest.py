"""Shared fixtures: a tiny synthetic LSI dataset (no real data, no network access)."""

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

import lsi_explorer  # noqa: F401  (drops foreign PROJ_LIB before rasterio is used)
from lsi_explorer import i18n, phase1_deltas, phase2_transitions, pipeline, utils

CRS = "EPSG:3844"
TRANSFORM = from_origin(500000, 500000, 100, 100)
PATCHED_DIRS = (
    "RESULTS_DIR",
    "DELTAS_DIR",
    "TRANSITIONS_DIR",
    "DRIVERS_DIR",
    "FIGURES_DIR",
)


def write_raster(path, arr):
    """Write a float32 single-band GeoTIFF on the synthetic grid (nodata -99)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    profile = dict(
        driver="GTiff",
        width=arr.shape[1],
        height=arr.shape[0],
        count=1,
        dtype="float32",
        crs=CRS,
        transform=TRANSFORM,
        nodata=-99.0,
    )
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(arr.astype("float32"), 1)


@pytest.fixture(autouse=True)
def english():
    """Run every test with the default language, whatever the machine locale is."""
    i18n.set_language("en")
    yield
    i18n.set_language(None)


@pytest.fixture
def dataset(tmp_path, monkeypatch):
    """Present + one future scenario for crop 'XX'; score drops by 12 on the left half."""
    lsi, res = tmp_path / "LSI", tmp_path / "results"
    present = np.full((8, 8), 55.0)
    future = present.copy()
    future[:, :4] -= 12
    present[0, 0] = -99.0  # nodata pixel
    for folder, score in (("prezent", present), ("ssp245_2041-2070", future)):
        write_raster(lsi / folder / "XX" / "_XX_land_suitability.tif", score)
        cls = np.where(score < 0, -99.0, np.clip(10 - score // 10, 1, 10))
        write_raster(
            lsi / folder / "XX" / "_XX_land_suitability_10_categories.tif", cls
        )
    monkeypatch.setattr(utils, "LSI_DIR", lsi)
    monkeypatch.setattr(pipeline, "LSI_DIR", lsi)
    monkeypatch.setattr(utils, "ADMIN_DIR", tmp_path / "admin")
    for name in PATCHED_DIRS:
        sub = {"RESULTS_DIR": ""}.get(name, name.split("_")[0].lower())
        for mod in (utils, phase1_deltas, phase2_transitions, pipeline):
            if hasattr(mod, name):
                monkeypatch.setattr(mod, name, res / sub)
    return lsi
