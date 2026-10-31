"""Tests for the county / UAT filter helpers and the boundary download script."""

import geopandas as gpd
from shapely.geometry import box

import lsi_explorer  # noqa: F401
from lsi_explorer import boundaries as fetch_admin
from lsi_explorer.admin import uat_label, uats_in_county


def _judete():
    j = gpd.GeoDataFrame(
        {"name": ["Timis", "Cluj"]},
        geometry=[box(0, 0, 10, 10), box(20, 0, 30, 10)],
        crs=3844,
    )
    return j.assign(_label=j["name"])


def test_uats_by_county_attribute():
    uats = gpd.GeoDataFrame(
        {"name": ["Lugoj", "Dej"], "county": ["Timis", "Cluj"]},
        geometry=[box(25, 1, 26, 2), box(1, 1, 2, 2)],  # deliberately misplaced
        crs=3844,
    ).assign(_label=lambda d: d["name"])
    assert uats_in_county(uats, _judete(), "Timis")["name"].tolist() == ["Lugoj"]


def test_uats_by_location_without_attribute():
    uats = gpd.GeoDataFrame(
        {"name": ["Lugoj", "Dej"]},
        geometry=[box(1, 1, 2, 2), box(21, 1, 22, 2)],
        crs=3844,
    ).assign(_label=lambda d: d["name"])
    assert uats_in_county(uats, _judete(), "Cluj")["name"].tolist() == ["Dej"]


def test_uat_label():
    assert uat_label({"_label": "Lugoj", "natLevName": "Municipiu"}) == (
        "Lugoj (Municipiu)"
    )
    assert uat_label({"_label": "Lugoj"}) == "Lugoj"


def test_wfs_url_requests_geojson_in_wgs84():
    url = fetch_admin.wfs_url("geospatial:ro_uat_poligon")
    assert "typeName=geospatial:ro_uat_poligon" in url
    assert "outputFormat=application/json" in url and "srsName=EPSG:4326" in url


def test_tidy_keeps_columns_and_projects_to_stereo70():
    gdf = gpd.GeoDataFrame(
        {"name": ["A"], "pop2011": [1]}, geometry=[box(21, 45, 21.1, 45.1)], crs=4326
    )
    out = fetch_admin.tidy(gdf, ["name"])
    assert list(out.columns) == ["name", "geometry"]
    assert out.crs.to_epsg() == 3844


def test_option_index_from_url():
    from lsi_explorer.admin import option_index

    opts = ["SSP1-2.6", "SSP2-4.5"]
    assert option_index(opts, "SSP1-2.6", 1) == 0
    assert option_index(opts, "bogus", 1) == 1
    assert option_index(opts, None) == 0


def test_uat_type_is_shortened():
    long = {
        "_label": "Lugoj",
        "natLevName": "Municipiu, altul decat resedinta de judet",
    }
    assert uat_label(long) == "Lugoj (Municipiu)"
    assert uat_label(
        {"_label": "Sector 1", "natLevName": "Sectoarele municipiului Bucuresti"}
    ) == ("Sector 1 (Sector)")
