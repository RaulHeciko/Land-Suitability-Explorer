"""End-to-end checks on a tiny synthetic dataset (no real LSI data needed)."""

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from rasterio.windows import Window

import src  # noqa: F401
from src import phase1_deltas, phase2_transitions, tileserver, utils
from src.raster_ops import grid_of
from src.region_stats import region_summary

CRS = "EPSG:3844"
TRANSFORM = from_origin(500000, 500000, 100, 100)


def _write(path, arr):
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


@pytest.fixture
def dataset(tmp_path, monkeypatch):
    """Present + one future scenario for crop 'XX'; score drops by 12 on the left half."""
    lsi, res = tmp_path / "LSI", tmp_path / "results"
    present = np.full((8, 8), 55.0)
    future = present.copy()
    future[:, :4] -= 12
    present[0, 0] = -99.0  # nodata pixel
    for folder, score in (("prezent", present), ("ssp245_2041-2070", future)):
        _write(lsi / folder / "XX" / "_XX_land_suitability.tif", score)
        cls = np.where(score < 0, -99.0, np.clip(10 - score // 10, 1, 10))
        _write(lsi / folder / "XX" / "_XX_land_suitability_10_categories.tif", cls)
    monkeypatch.setattr(utils, "LSI_DIR", lsi)
    for name in (
        "RESULTS_DIR",
        "DELTAS_DIR",
        "TRANSITIONS_DIR",
        "DRIVERS_DIR",
        "FIGURES_DIR",
    ):
        sub = {"RESULTS_DIR": ""}.get(name, name.split("_")[0].lower())
        monkeypatch.setattr(utils, name, res / sub)
        for mod in (phase1_deltas, phase2_transitions):
            if hasattr(mod, name):
                monkeypatch.setattr(mod, name, res / sub)
    return lsi


def test_region_summary(dataset):
    grid = grid_of(utils.continuous_path("XX", "prezent"))
    scs = utils.list_scenarios()
    s = region_summary("XX", scs, grid, Window(0, 0, 8, 8), None)
    key = ("SSP2-4.5", "2041-2070")
    d = s["delta"][key]
    assert s["area_km2"] == pytest.approx(63 * 0.01)
    assert d["degraded_km2"] == pytest.approx(
        31 * 0.01
    )  # left half minus the nodata pixel
    assert d["change_km2"].tolist() == pytest.approx([0.31, 0, 0.32, 0, 0])
    assert s["mats"][key].sum() == pytest.approx(0.63)


def test_phase1_writes_delta(dataset):
    rows = phase1_deltas.run_crop("XX", utils.list_scenarios())
    assert rows[0]["degraded_sig_km2"] == pytest.approx(0.31)
    assert utils.delta_path("XX", utils.list_scenarios()[0]).exists()


def test_tiles_render(dataset):
    grid = grid_of(utils.continuous_path("XX", "prezent"))
    sc = utils.list_scenarios()[0]
    key = tileserver.REGISTRY.add_layer(
        "chg",
        "delta",
        (
            utils.continuous_path("XX", "prezent"),
            utils.continuous_path("XX", sc.folder),
        ),
        grid,
    )
    layer = tileserver.REGISTRY.layers[key]
    # Web Mercator tile containing the synthetic raster (around 46N 25E) at zoom 12
    png = tileserver.render_tile(
        layer, tileserver.REGISTRY.regions["all"], 12, 2332, 1462
    )
    assert png is None or png[:8] == b"\x89PNG\r\n\x1a\n"
    assert layer.pyramid[0].tolist()[0][:5] == [tileserver.NODATA, 1, 1, 1, 3]
