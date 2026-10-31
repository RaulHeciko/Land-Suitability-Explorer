"""End-to-end checks on a tiny synthetic dataset (no real LSI data needed)."""

import pytest
from rasterio.windows import Window

from lsi_explorer import phase1_deltas, tileserver, utils
from lsi_explorer.raster_ops import grid_of
from lsi_explorer.region_stats import region_summary


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
