"""Unit tests for the classification rules and small helpers."""

import numpy as np
import pytest

import src  # noqa: F401  (drops foreign PROJ_LIB before rasterio is imported)
from src import charts, tileserver
from src.phase3_attribution import classify_drivers
from src.preprocessing import clean_categorical, clean_continuous
from src.raster_ops import crosstab
from src.utils import CROP_NAMES, change_class, crop_label, parse_scenario


@pytest.mark.parametrize(
    "delta, expected",
    [
        (-25, 1),
        (-10.01, 1),
        (-10, 2),
        (-5.01, 2),
        (-5, 3),
        (0, 3),
        (5, 3),
        (5.01, 4),
        (10, 4),
        (10.01, 5),
    ],
)
def test_change_class_bounds(delta, expected):
    assert change_class(np.array([delta]))[0] == expected


def test_change_class_nan_is_zero():
    assert change_class(np.array([np.nan]))[0] == 0


def test_driver_lookup_table():
    s = np.array([0, -10, -10, -10, -10, 10, 10, 10, 10, np.nan, -10], "f4")
    t = np.array([1, 1, -1, 1, -1, 1, 1, -1, -1, 1, np.nan], "f4")
    p = np.array([1, -1, -1, 1, 1, 1, -1, 1, -1, 1, 1], "f4")
    assert classify_drivers(s, t, p).tolist() == [0, 1, 2, 3, 4, 5, 6, 7, 8, 255, 255]


def test_cleaning_rules():
    cont = clean_continuous(np.array([-1, 0, 50, 100, 101], "f4"))
    assert np.isnan(cont[[0, 4]]).all() and cont[1:4].tolist() == [0, 50, 100]
    cat = clean_categorical(np.array([0, 1, 10, 11, np.nan], "f4"))
    assert cat.tolist() == [0, 1, 10, 0, 0]


def test_crosstab_counts_only_valid_pairs():
    a = np.array([1, 1, 2, 0], np.uint8)
    b = np.array([1, 2, 2, 3], np.uint8)
    m = crosstab(a, b)
    assert m[0, 0] == 1 and m[0, 1] == 1 and m[1, 1] == 1 and m.sum() == 3


def test_class_flows():
    m = np.zeros((10, 10))
    m[0, 1] = 5  # C1 -> C2
    m[2, 2] = 7  # unchanged
    lost, gained, net = charts.class_flows(m)
    assert lost[0] == 5 and gained[1] == 5 and net[0] == -5 and net[2] == 0


def test_area_units_are_km2():
    assert charts.area_unit(500) == (1.0, "km\u00b2")
    assert charts.area_unit(50_000)[0] == 1e3
    assert charts.fmt_km2(57966.4) == "57,966 km\u00b2"


def test_crop_names():
    assert CROP_NAMES["CN"] == "Hemp"
    assert crop_label("GR") == "Wheat (GR)"
    assert crop_label("ZZ") == "ZZ"


def test_scenario_parsing():
    sc = parse_scenario("ssp245_2041-2070")
    assert (sc.ssp_label, sc.period, sc.horizon) == ("SSP2-4.5", "2041-2070", 2050)
    assert parse_scenario("prezent") is None


def test_delta_encoding_uses_change_classes():
    idx = tileserver.encode(np.array([-20, -7, 0, 7, 20, np.nan], "f4"), "delta")
    assert idx.tolist() == [1, 2, 3, 4, 5, tileserver.NODATA]


def test_public_url(monkeypatch):
    monkeypatch.delenv("LSI_TILE_BASE_URL", raising=False)
    monkeypatch.delenv("JUPYTERHUB_SERVICE_PREFIX", raising=False)
    assert tileserver.public_url(8765) == "http://127.0.0.1:8765"
    monkeypatch.setenv("JUPYTERHUB_SERVICE_PREFIX", "/user/ana/")
    assert tileserver.public_url(8765) == "/user/ana/proxy/8765"
    monkeypatch.setenv("LSI_TILE_BASE_URL", "https://hub.example/proxy/{port}/")
    assert tileserver.public_url(8765) == "https://hub.example/proxy/8765"
