"""Regression tests for chart layout (few drivers, overlapping titles) and app assets."""

from pathlib import Path

import numpy as np

import lsi_explorer  # noqa: F401
from lsi_explorer import charts

ROOT = Path(__file__).resolve().parents[1]
SSPS, PERIODS = ["SSP1-2.6", "SSP2-4.5"], ["2041-2070", "2071-2100"]


def _driver_tables(areas: dict[int, float]):
    counts = np.zeros(9)
    counts[0] = 50
    for code, v in areas.items():
        counts[code] = v
    table = charts.driver_summary_table(counts, 1.0)
    return {(s, p): table for s in SSPS for p in PERIODS}


def test_zero_driver_bars_have_no_label():
    tables = _driver_tables({1: 17.7})
    tables[("SSP1-2.6", "2071-2100")] = charts.driver_summary_table(
        np.array([50, 0, 0, 17.5, 0, 0, 0, 0, 0.0]), 1.0
    )
    fig = charts.drivers_grid_figure(tables, SSPS, PERIODS, "Hemp (CN)")
    labels = [t for tr in fig.data for t in tr.text]
    assert "" in labels and not any(t.startswith("0.0") for t in labels)


def test_driver_panel_size_scales_with_driver_count():
    h1 = charts.drivers_grid_figure(_driver_tables({1: 5}), SSPS, PERIODS, "X").layout
    h4 = charts.drivers_grid_figure(
        _driver_tables({1: 5, 3: 6, 5: 7, 6: 1}), SSPS, PERIODS, "X"
    ).layout
    assert h1.height < h4.height
    per_driver = (h4.height - h1.height) / (2 * 3)  # 2 panel rows, 3 extra drivers
    assert 40 <= per_driver <= 70


def test_x_axis_title_only_on_bottom_row():
    m = {(s, p): np.ones((10, 10)) for s in SSPS for p in PERIODS}
    for fig in (
        charts.class_dynamics_figure(m, SSPS, PERIODS, "X"),
        charts.drivers_grid_figure(_driver_tables({1: 5}), SSPS, PERIODS, "X"),
    ):
        titled = [
            ax["title"]["text"]
            for name, ax in fig.layout.to_plotly_json().items()
            if name.startswith("xaxis") and ax.get("title", {}).get("text")
        ]
        assert len(titled) == len(PERIODS)


def test_logo_assets_exist():
    for name in ("geolass_icon.png",):
        data = (
            ROOT / "src" / "lsi_explorer" / "dashboard" / "assets" / name
        ).read_bytes()
        assert data[:8] == b"\x89PNG\r\n\x1a\n"
