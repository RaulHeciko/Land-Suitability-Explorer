"""Land Suitability Index - interactive local dashboard.

Run:  streamlit run app/main.py
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import folium  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402
from branca.element import MacroElement  # noqa: E402
from folium.plugins import DualMap, Fullscreen  # noqa: E402
from jinja2 import Template  # noqa: E402
from pyproj import Transformer  # noqa: E402
from rasterio.transform import array_bounds  # noqa: E402
from rasterio.windows import Window, transform as window_transform  # noqa: E402
from streamlit_folium import st_folium  # noqa: E402

from src import charts, tileserver  # noqa: E402
from src.charts import fmt_km2  # noqa: E402
from src.preprocessing import reference_grid  # noqa: E402
from src.admin import option_index, uat_label, uats_in_county  # noqa: E402
from src.raster_ops import Grid, geometry_inside, region_window  # noqa: E402
from src.region_stats import region_summary  # noqa: E402
from src.tileserver import REGISTRY  # noqa: E402
from src.utils import (
    CHANGE_CLASSES,
    CLASS_RANGES,
    DRIVERS,
    PRESENT,
    SIGNIFICANCE_THRESHOLD,
    Scenario,  # noqa: E402
    admin_layer_path,
    categorical_path,
    continuous_path,
    crop_label,
    crop_names,
    find_driver_raster,
    list_crops,
    list_scenarios,
)

st.set_page_config(
    page_title="Land Suitability Explorer",
    page_icon=str(ROOT / "app" / "assets" / "geolass_icon.png"),
    layout="wide",
)

ESRI = "https://server.arcgisonline.com/ArcGIS/rest/services/{}/MapServer/tile/{{z}}/{{y}}/{{x}}"
BASEMAPS = {
    "Light gray": (ESRI.format("Canvas/World_Light_Gray_Base"), 16),
    "Satellite": (ESRI.format("World_Imagery"), 18),
}
LABELS_URL = ESRI.format("Canvas/World_Light_Gray_Reference")
ESRI_ATTR = "Tiles \u00a9 Esri -- Esri, HERE, Garmin, \u00a9 OpenStreetMap contributors"
THR = SIGNIFICANCE_THRESHOLD

st.markdown(
    """
<style>
  :root {--page:#f4f6f9; --surface:#ffffff; --surface-2:#eceff4; --border:#d5dbe4; --ink:#131c2e;
         --ink-2:#3b4658; --ink-muted:#5c6879; --navy:#1c355d; --teal:#09b3ad; --accent:#0a7470;
         --danger:#b3261e; --success:#1f7a45; --shadow-sm:0 1px 2px #131c2e14;}
  #MainMenu, footer, [data-testid="stDecoration"], [data-testid="stToolbarActions"],
  [data-testid="stAppDeployButton"], [data-testid="stMainMenu"] {display: none;}
  [data-testid="stExpandSidebarButton"] {visibility: visible !important; background: var(--surface);
                                         border: 1px solid var(--border); border-radius: 8px;}
  [data-testid="stAppViewContainer"], [data-testid="stMain"] {background: var(--page);}
  [data-testid="stHeader"] {background: transparent;}
  .block-container {padding-top: 2.2rem; padding-bottom: 1.5rem; max-width: 1440px;}
  [data-testid="stSidebar"] {background: var(--surface); border-right: 1px solid var(--border);}
  [data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {padding-top: 1.2rem;}
  [data-testid="stSidebarHeader"] {margin-bottom: -3.4rem; position: relative; z-index: 5;
                                   pointer-events: none;}
  [data-testid="stSidebarCollapseButton"] {visibility: visible !important; pointer-events: auto;}
  [data-testid="stSidebarCollapseButton"] button {border: 1px solid var(--border); border-radius: 8px;
                                                  background: var(--surface);}
  .brand {display:flex; align-items:center; gap:12px; margin:0 44px 8px 0;}
  .brand img {width:52px; height:52px; border-radius:12px; display:block; flex:none;}
  .brand-name {font-weight:700; font-size:1.2rem; line-height:1.15; color:var(--ink);}
  .brand-sub {font-size:0.82rem; color:var(--ink-muted); margin-top:2px;}
  .side-section {font-size: 0.70rem; font-weight: 600; letter-spacing: .09em; text-transform: uppercase;
                 color: var(--ink-muted); margin: 18px 0 4px 0; padding-top: 12px; border-top: 1px solid var(--border);}
  .app-header {margin-bottom: 18px;}
  .overline {font-size: 0.74rem; font-weight: 600; letter-spacing: .10em; text-transform: uppercase; color: var(--ink-muted);}
  .app-title {font-size: 2.0rem; font-weight: 600; letter-spacing: -0.02em; color: var(--ink); line-height: 1.2;
              margin: 4px 0 10px 0;}
  .app-title .code {font-size: 0.85rem; font-weight: 600; color: var(--navy); background: #e4ebf5;
                    border-radius: 6px; padding: 3px 8px; margin-left: 10px; vertical-align: middle;}
  .chips {display: flex; flex-wrap: wrap; gap: 8px;}
  .chip {font-size: 0.82rem; color: var(--ink-2); background: var(--surface); border: 1px solid var(--border);
         border-radius: 999px; padding: 3px 12px;}
  .chip b {color: var(--ink); font-weight: 600;}
  .kpis {display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 16px; margin-bottom: 10px;}
  .kpi {background: var(--surface); border: 1px solid var(--border); border-left: 4px solid var(--kpi);
        border-radius: 8px; box-shadow: var(--shadow-sm); padding: 14px 18px;}
  .kpi-label {font-size: 0.72rem; font-weight: 600; letter-spacing: .08em; text-transform: uppercase;
              color: var(--ink-muted);}
  .kpi-value {font-size: 1.7rem; font-weight: 600; letter-spacing: -0.01em; color: var(--ink); margin-top: 4px;
              line-height: 1.2;}
  .kpi-sub {font-size: 0.82rem; color: var(--ink-muted); margin-top: 4px;}
  .neg {color: var(--danger); font-weight: 600;} .pos {color: var(--success); font-weight: 600;}
  [data-baseweb="tab-list"] {gap: 4px; border-bottom: 1px solid var(--border);}
  [data-baseweb="tab"] p {font-size: 0.95rem; font-weight: 500;}
  [data-baseweb="tab"][aria-selected="true"] p {color: var(--accent); font-weight: 600;}
  [data-testid="stPlotlyChart"] {background: var(--surface); border: 1px solid var(--border); border-radius: 8px;
                                 padding: 6px; box-shadow: var(--shadow-sm);}
  [data-testid="stExpander"] details {background: var(--surface); border-color: var(--border); border-radius: 8px;}
  .section-title {font-size: 1.1rem; font-weight: 600; color: var(--ink); margin: 24px 0 2px 0;}
  .hint {color: var(--ink-muted); font-size: 0.88rem;}
  .app-footer {margin-top: 28px; padding-top: 12px; border-top: 1px solid var(--border); color: var(--ink-muted);
               font-size: 0.78rem; display: flex; justify-content: space-between; flex-wrap: wrap; gap: 8px;}
  @media (max-width: 900px) {.kpis {grid-template-columns: repeat(2, minmax(0, 1fr));}}
</style>""",
    unsafe_allow_html=True,
)


# ------------------------------------------------------------------ cached resources


@st.cache_data(show_spinner=False)
def catalogue():
    return list_crops(), list_scenarios(), crop_names()


@st.cache_resource(show_spinner=False)
def tile_port() -> int:
    return tileserver.start()


@st.cache_resource(show_spinner=False)
def grid_for(crop: str) -> Grid:
    return reference_grid(crop)


@st.cache_resource(show_spinner=False)
def admin_layer(level: str, crs_wkt: str):
    path = admin_layer_path(level)
    if path is None:
        return None
    import geopandas as gpd

    gdf = gpd.read_file(path)
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    gdf = gdf.to_crs(crs_wkt)
    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].reset_index(drop=True)
    candidates = [
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
    lower = {c.lower(): c for c in gdf.columns}
    col = next((lower[c] for c in candidates if c in lower), None)
    if col is None:
        col = next(c for c in gdf.columns if c != "geometry" and gdf[c].dtype == object)
    gdf["_label"] = gdf[col].astype(str).str.strip()
    return gdf


@st.cache_data(show_spinner=False)
def asset_uri(name: str) -> str:
    """Image from app/assets/ as a data URI, for use inside st.markdown HTML."""
    import base64

    data = (ROOT / "app" / "assets" / name).read_bytes()
    return "data:image/png;base64," + base64.b64encode(data).decode("ascii")


def _mtimes(paths) -> tuple:
    return tuple(p.stat().st_mtime if p and p.exists() else 0 for p in paths)


@st.cache_data(show_spinner=False, persist="disk", max_entries=64)
def summary(
    crop: str,
    region_key: str,
    win: tuple,
    _mask: np.ndarray | None,
    mtimes: tuple,
    units: str,
) -> dict:
    return region_summary(crop, list_scenarios(), grid_for(crop), Window(*win), _mask)


# ------------------------------------------------------------------ sidebar

crops, scenarios, names = catalogue()
if not crops:
    st.error(
        "No LSI rasters found. Put them in data/LSI/<period>/<CROP>/ (or ./LSI) and reload."
    )
    st.stop()

with st.sidebar:
    st.markdown(
        f"<div class='brand'><img src='{asset_uri('geolass_icon.png')}' alt='GeoLaSS'><div>"
        "<div class='brand-name'>Land Suitability Explorer</div>"
        "<div class='brand-sub'>Climate change impact on crops</div></div></div>"
        "<div class='side-section'>Selection</div>",
        unsafe_allow_html=True,
    )
    qp = st.query_params  # selection restored from / written to the page URL
    crops = sorted(crops, key=lambda c: names.get(c, c))
    crop = st.selectbox(
        "Crop", crops, index=option_index(crops, qp.get("crop")), format_func=crop_label
    )
    ssp_labels = sorted({s.ssp_label for s in scenarios})
    ssp = st.radio(
        "Climate scenario",
        ssp_labels,
        index=option_index(ssp_labels, qp.get("ssp"), len(ssp_labels) - 1),
        horizontal=True,
        help="SSP1-2.6: strong mitigation \u00b7 SSP2-4.5: intermediate emissions",
    )
    ssp_scs = sorted(
        [s for s in scenarios if s.ssp_label == ssp], key=lambda s: s.start
    )
    periods_ssp = [s.period for s in ssp_scs]
    period = st.radio(
        "Future period",
        periods_ssp,
        index=option_index(periods_ssp, qp.get("period")),
        horizontal=True,
    )
    sc: Scenario = next(s for s in ssp_scs if s.period == period)

    grid = grid_for(crop)
    crs_wkt = grid.crs.to_wkt()
    judete, uats = admin_layer("judet", crs_wkt), admin_layer("uat", crs_wkt)
    geom, region_name, url_area = None, "", {}
    levels = (
        ["Whole study area"]
        + (["County (Jude\u021b)"] if judete is not None else [])
        + (["Municipality (UAT)"] if uats is not None else [])
    )
    if len(levels) > 1:
        st.markdown(
            "<div class='side-section'>Area of interest</div>", unsafe_allow_html=True
        )
        area_codes = ["all", "judet", "uat"][: len(levels)]
        level = st.radio(
            "Area of interest",
            levels,
            index=option_index(area_codes, qp.get("area")),
            label_visibility="collapsed",
        )
        county_names = sorted(judete._label.unique()) if judete is not None else []
        if level == "County (Jude\u021b)":
            jname = st.selectbox(
                "Jude\u021b",
                county_names,
                index=option_index(county_names, qp.get("judet")),
            )
            geom, region_name = (
                judete[judete._label == jname].union_all(),
                f"Jude\u021b {jname}",
            )
            url_area = {"area": "judet", "judet": jname}
        elif level == "Municipality (UAT)":
            pool, jname = uats, ""
            if judete is not None:
                jname = st.selectbox(
                    "Jude\u021b",
                    county_names,
                    index=option_index(county_names, qp.get("judet")),
                )
                pool = uats_in_county(uats, judete, jname)
            pool = pool.assign(_ui=pool.apply(uat_label, axis=1)).sort_values("_ui")
            idx = st.selectbox(
                "UAT",
                pool.index.tolist(),
                index=option_index(pool["_ui"].tolist(), qp.get("uat")),
                format_func=lambda i: pool.at[i, "_ui"],
                help="Type to search",
            )
            geom, region_name = pool.at[idx, "geometry"], f"UAT {pool.at[idx, '_ui']}"
            url_area = {"area": "uat", "judet": jname, "uat": pool.at[idx, "_ui"]}

    st.query_params.from_dict(
        {"crop": crop, "ssp": ssp, "period": period, **(url_area or {"area": "all"})}
    )
    st.markdown("<div class='side-section'>Display</div>", unsafe_allow_html=True)
    with st.expander("Map style"):
        basemap = st.radio("Basemap", list(BASEMAPS), horizontal=True)
        place_names = st.checkbox("Show place names", value=False)
        opacity = st.slider("Layer opacity", 0.3, 1.0, 1.0, 0.05)
    with st.expander("How to read the data"):
        st.markdown(
            f"- **Suitability** is a 0-100 score grouped into 10 classes: **C1 = most suitable** (90-100) "
            f"... **C10 = least** (0-10).\n"
            f"- **Change** = future - present, grouped into 5 classes: < -10, -10 to -5, -5 to 5 (no significant change), 5 to 10, > 10 points.\n"
            f"- **Climate driver** combines the direction of the suitability change with the direction of "
            f"temperature and precipitation change.\n"
            f"- Areas are in km\u00b2; every 100 m pixel (0.01 km\u00b2) is counted."
        )
    if len(levels) == 1:
        st.caption(
            "Add county / UAT boundaries to `data/admin/` (`judete.geojson`, `uat.geojson`) "
            "to analyse a single Jude\u021b or UAT."
        )

# ------------------------------------------------------------------ region

window = region_window(grid, geom.bounds if geom is not None else None)
if window.width < 1 or window.height < 1:
    st.error("The selected area does not overlap the raster extent.")
    st.stop()
win = (int(window.col_off), int(window.row_off), int(window.width), int(window.height))
wt = window_transform(window, grid.transform)
if geom is not None:
    mask = geometry_inside([geom], wt, (win[3], win[2]))
    region_key = hashlib.md5(geom.wkb).hexdigest()[:12]
    REGISTRY.add_region(region_key, win[1], win[0], mask)
else:
    mask, region_key = None, "all"

_l, _b, _r, _t = array_bounds(win[3], win[2], wt)
_xs, _ys = Transformer.from_crs(grid.crs, "EPSG:4326", always_xy=True).transform(
    [_l, _l, _r, _r], [_b, _t, _b, _t]
)
view_bounds = [[min(_ys), min(_xs)], [max(_ys), max(_xs)]]
view_center = [(min(_ys) + max(_ys)) / 2, (min(_xs) + max(_xs)) / 2]
view_zoom = int(
    np.clip(
        np.floor(
            np.log2(360 / max(max(_xs) - min(_xs), (max(_ys) - min(_ys)) * 1.4, 1e-3))
        )
        + 1,
        5,
        15,
    )
)

files = [continuous_path(crop, PRESENT), categorical_path(crop, PRESENT)] + [
    p
    for s in scenarios
    for p in (
        continuous_path(crop, s.folder),
        categorical_path(crop, s.folder),
        find_driver_raster(crop, s),
    )
]
with st.spinner(
    "Computing statistics from every pixel of this area (first time only)..."
):
    S = summary(crop, region_key, win, mask, _mtimes(files), "km2-classes")
key = (sc.ssp_label, sc.period)
D = S["delta"].get(key, {})

# ------------------------------------------------------------------ header + KPIs


def signed(v: float, fmt: str) -> str:
    """Value with sign, coloured red (negative) or green (positive)."""
    if not np.isfinite(v):
        return "-"
    cls = "neg" if v < 0 else "pos" if v > 0 else ""
    return f"<span class='{cls}'>{format(v, fmt)}</span>"


def chart_config(crop: str, sc) -> dict:
    """Plotly toolbar: no logo, only useful tools, PNG export at 3x for reports."""
    return {
        "displaylogo": False,
        "modeBarButtonsToRemove": [
            "select2d",
            "lasso2d",
            "autoScale2d",
            "toggleSpikelines",
            "hoverClosestCartesian",
            "hoverCompareCartesian",
        ],
        "toImageButtonOptions": {
            "format": "png",
            "scale": 3,
            "filename": f"LSI_{crop}_{sc.tag}",
        },
    }


def kpi(label: str, value: str, sub: str, accent: str) -> str:
    return (
        f"<div class='kpi' style='--kpi:{accent}'><div class='kpi-label'>{label}</div>"
        f"<div class='kpi-value'>{value}</div><div class='kpi-sub'>{sub}</div></div>"
    )


st.markdown(
    "<div class='app-header'>"
    "<div class='overline'>Land Suitability Index \u00b7 climate scenarios</div>"
    f"<div class='app-title'>{names.get(crop, crop)}<span class='code'>{crop}</span></div>"
    "<div class='chips'>"
    f"<span class='chip'>{region_name or 'Whole study area'}</span>"
    f"<span class='chip'>{fmt_km2(S['area_km2'])} assessed</span>"
    f"<span class='chip'>Scenario <b>{sc.ssp_label}</b></span>"
    f"<span class='chip'>Period <b>{sc.period}</b> vs present</span>"
    "</div></div>",
    unsafe_allow_html=True,
)
vk = D.get("valid_km2", 0) or 1
mf, dm = D.get("mean_future", np.nan), D.get("mean_delta", np.nan)
st.markdown(
    "<div class='kpis'>"
    + kpi(
        f"Mean suitability \u00b7 {sc.period}",
        f"{mf:.1f}",
        f"present {S['present_mean']:.1f} &nbsp;"
        f"{signed(mf - S['present_mean'], '+.1f')}",
        "#1c355d",
    )
    + kpi(
        "Mean change",
        f"{signed(dm, '+.2f')} <span style='font-size:.9rem;color:#6B7780'>points</span>",
        "average of future \u2212 present per pixel",
        "#1c355d",
    )
    + kpi(
        "Significant loss",
        fmt_km2(D.get("degraded_km2", np.nan)),
        f"{D.get('degraded_km2', 0) / vk * 100:.1f}% of the area \u00b7 drop &gt; {THR:g} points",
        "#b3261e",
    )
    + kpi(
        "Significant gain",
        fmt_km2(D.get("improved_km2", np.nan)),
        f"{D.get('improved_km2', 0) / vk * 100:.1f}% of the area \u00b7 rise &gt; {THR:g} points",
        "#1f7a45",
    )
    + "</div>",
    unsafe_allow_html=True,
)

# ------------------------------------------------------------------ map building blocks

tiles_base = tileserver.public_url(tile_port())
drv_path = find_driver_raster(crop, sc)


def reg(label, kind, *paths):
    return REGISTRY.add_layer(label, kind, tuple(paths), grid)


# layers read by the click inspector (score layers are never drawn, only queried)
INSPECT = [
    reg("Score present", "score", continuous_path(crop, PRESENT)),
    reg("Class present", "classes", categorical_path(crop, PRESENT)),
    reg(f"Score {sc.period}", "score", continuous_path(crop, sc.folder)),
    reg(f"Class {sc.period}", "classes", categorical_path(crop, sc.folder)),
    reg(
        "Change",
        "delta",
        continuous_path(crop, PRESENT),
        continuous_path(crop, sc.folder),
    ),
]
if drv_path is not None:
    INSPECT.append(reg("Climate driver", "driver", drv_path))
L_PRESENT, L_FUT, L_CHG = INSPECT[1], INSPECT[3], INSPECT[4]
L_DRV = INSPECT[5] if drv_path is not None else None


def tile_url(layer_key: str) -> str:
    return f"{tiles_base}/tile/{layer_key}/{region_key}/{{z}}/{{x}}/{{y}}.png"


def _chip(color):
    return (
        f"<span style='display:inline-block;width:12px;height:12px;border-radius:2px;background:{color};"
        f"border:1px solid #0002;margin-right:5px;vertical-align:-2px'></span>"
    )


def _swatch_row(items, w=30):
    cells = "".join(
        f"<div style='text-align:center;font-size:10px;color:#333'>{t}"
        f"<div style='width:{w}px;height:11px;background:{c};border:1px solid #0003;margin-top:1px'></div></div>"
        for t, c in items
    )
    return f"<div style='display:flex;gap:2px;margin-top:3px'>{cells}</div>"


def legend_classes(title):
    return (
        f"<b>{title}</b>"
        + _swatch_row([(f"C{c}", charts.CLASS_COLORS[c - 1]) for c in range(1, 11)], 19)
        + "<div style='display:flex;justify-content:space-between;color:#777;font-size:10px'>"
        "<span>most suitable</span><span>least suitable</span></div>"
    )


def legend_change():
    """5-class bar with each class range written under its colour (same labels as the charts)."""
    w = 50
    segs = "".join(
        f"<div style='width:{w}px;height:11px;background:{c}'></div>"
        for _, c in CHANGE_CLASSES.values()
    )
    labels = "".join(
        f"<div style='width:{w}px;text-align:center'>{n}</div>"
        for n, _ in CHANGE_CLASSES.values()
    )
    return (
        "<b>Change in land suitability</b> <span style='color:#777'>(points)</span>"
        f"<div style='display:flex;margin-top:5px;border:1px solid #0003;border-radius:3px;"
        f"overflow:hidden;width:{5 * w}px'>{segs}</div>"
        f"<div style='display:flex;font-size:10px;color:#333;margin-top:2px'>{labels}</div>"
    )


def legend_drivers(areas=None):
    """Only drivers that occur in the area (plus 'no significant change')."""
    rows = "".join(
        f"<div>{_chip(c)}{n}</div>"
        for code, (n, _, c) in DRIVERS.items()
        if areas is None or code == 0 or areas[code] > 0
    )
    return f"<b>Dominant climate driver</b><div style='margin-top:3px'>{rows}</div>"


class MapLegend(MacroElement):
    """Legend box that follows the selected data layer (Leaflet base-layer radio)."""

    _template = Template("""
    {% macro script(this, kwargs) %}
    (function() {
      var map = {{ this._parent.get_name() }};
      var legends = {{ this.legends|tojson }};
      var ctl = L.control({position: 'bottomleft'});
      ctl.onAdd = function() {
        var d = L.DomUtil.create('div');
        d.style.cssText = 'background:rgba(255,255,255,.94);padding:6px 9px;border-radius:7px;' +
                          'box-shadow:0 1px 5px rgba(0,0,0,.25);font:11px/1.4 system-ui,Segoe UI,sans-serif;color:#222';
        this._div = d; return d;
      };
      ctl.addTo(map);
      function show(n) { ctl._div.innerHTML = legends[n] || ''; ctl._div.style.display = legends[n] ? '' : 'none'; }
      show({{ this.initial|tojson }});
      map.on('baselayerchange', function(e) { show(e.name); });
    })();
    {% endmacro %}""")

    def __init__(self, legends: dict, initial: str):
        super().__init__()
        self._name = "MapLegend"
        self.legends, self.initial = legends, initial


class FitOnLoad(MacroElement):
    """Fit the map to `bounds` once it has its final size (streamlit-folium sizes the map
    after Leaflet's own fitBounds would run, which otherwise leaves the zoom too close).
    """

    _template = Template("""
    {% macro script(this, kwargs) %}
    (function() {
      var m = {{ this._parent.get_name() }};
      setTimeout(function() {
        m.invalidateSize();
        m.fitBounds({{ this.bounds|tojson }}, {padding: [{{ this.pad }}, {{ this.pad }}]});
      }, 250);
    })();
    {% endmacro %}""")

    def __init__(self, bounds, pad: int = 30):
        super().__init__()
        self._name = "FitOnLoad"
        self.bounds, self.pad = bounds, pad


class MapLabel(MacroElement):
    _template = Template("""
    {% macro script(this, kwargs) %}
    (function() {
      var c = L.control({position: 'topleft'});
      c.onAdd = function() { var d = L.DomUtil.create('div');
        d.style.cssText = 'background:rgba(255,255,255,.94);padding:4px 10px;border-radius:6px;' +
                          'box-shadow:0 1px 4px rgba(0,0,0,.25);font:600 13px system-ui,Segoe UI,sans-serif';
        d.innerHTML = {{ this.text|tojson }}; return d; };
      c.addTo({{ this._parent.get_name() }});
    })();
    {% endmacro %}""")

    def __init__(self, text: str):
        super().__init__()
        self._name = "MapLabel"
        self.text = text


class ClickInspector(MacroElement):
    """Click a pixel -> popup with every layer value at that location."""

    _template = Template("""
    {% macro script(this, kwargs) %}
    {{ this._parent.get_name() }}.on('click', function(e) {
        var m = {{ this._parent.get_name() }};
        fetch('{{ this.url }}&lat=' + e.latlng.lat + '&lon=' + e.latlng.lng)
          .then(function(r) { return r.json(); })
          .then(function(rows) {
            var html = '<table style="font:12px system-ui,Segoe UI,sans-serif;border-collapse:collapse">';
            rows.forEach(function(r) {
              html += '<tr><td style="padding:2px 10px 2px 0;color:#666">' + r.label +
                      '</td><td style="padding:2px 0"><b>' + r.text + '</b></td></tr>';
            });
            html += '</table>';
            L.popup({maxWidth: 380}).setLatLng(e.latlng).setContent(html).openOn(m);
          });
    });
    {% endmacro %}""")

    def __init__(self, url: str):
        super().__init__()
        self._name = "ClickInspector"
        self.url = url


def base_tiles(m):
    url, mz = BASEMAPS[basemap]
    folium.TileLayer(
        url,
        attr=ESRI_ATTR,
        name=basemap,
        max_native_zoom=mz,
        max_zoom=18,
        overlay=True,
        control=False,
    ).add_to(m)


def top_tiles(m):
    if place_names:
        folium.TileLayer(
            LABELS_URL,
            attr=ESRI_ATTR,
            name="Place names",
            overlay=True,
            control=False,
            max_native_zoom=16,
            max_zoom=18,
            z_index=50,
        ).add_to(m)
    if geom is not None:
        import geopandas as gpd

        outline = gpd.GeoSeries([geom], crs=grid.crs).to_crs(4326).simplify(0.0005)
        folium.GeoJson(
            outline.__geo_interface__,
            control=False,
            style_function=lambda _: {"color": "#222", "weight": 2, "fillOpacity": 0},
        ).add_to(m)


def data_tiles(m, layer_key, name, base: bool, show: bool = True):
    folium.TileLayer(
        tile_url(layer_key),
        attr="LSI",
        name=name,
        overlay=not base,
        control=base,
        show=show,
        opacity=opacity,
        max_zoom=18,
        max_native_zoom=18,
        z_index=10,
    ).add_to(m)


# ------------------------------------------------------------------ tabs

tab_map, tab_cmp, tab_cls, tab_drv = st.tabs(
    ["Map", "Present vs future", "Class changes", "Climate drivers"]
)

with tab_map:
    st.markdown(
        "<span class='hint'>Select the layer in the panel at the top right. Rasters are displayed at "
        "their native 100 m resolution; click any pixel to inspect its values.</span>",
        unsafe_allow_html=True,
    )
    choices = [
        (
            "Suitability \u00b7 present",
            L_PRESENT,
            legend_classes("Land suitability classes \u00b7 present"),
        ),
        (
            f"Suitability \u00b7 {sc.period}",
            L_FUT,
            legend_classes(f"Land suitability classes \u00b7 {sc.period}"),
        ),
        ("Change in suitability", L_CHG, legend_change()),
    ]
    if L_DRV:
        choices.append(("Climate driver", L_DRV, legend_drivers(S["drivers"].get(key))))
    initial = "Suitability \u00b7 present"
    fmap = folium.Map(
        location=view_center,
        zoom_start=view_zoom,
        tiles=None,
        control_scale=True,
        zoom_snap=0.5,
    )
    fmap.get_root().header.add_child(
        folium.Element(
            "<style>.leaflet-control-layers-expanded{padding:7px 12px;border-radius:8px;"
            "font:13px/1.7 system-ui,Segoe UI,sans-serif}"
            ".leaflet-control-layers-scrollbar{overflow:visible!important;height:auto!important}"
            ".leaflet-tile-container img{width:256.5px!important;height:256.5px!important}</style>"
        )
    )
    base_tiles(fmap)
    for name, lk, _ in choices:
        data_tiles(fmap, lk, name, base=True, show=name == initial)
    top_tiles(fmap)
    folium.LayerControl(collapsed=False, position="topright").add_to(fmap)
    Fullscreen(
        position="topleft", title="Full screen", title_cancel="Exit full screen"
    ).add_to(fmap)
    fmap.add_child(MapLegend({n: lg for n, _, lg in choices}, initial))
    fmap.add_child(
        ClickInspector(f"{tiles_base}/value/{region_key}?layers=" + ",".join(INSPECT))
    )
    fmap.add_child(FitOnLoad(view_bounds, pad=30))
    st_folium(
        fmap,
        height=660,
        use_container_width=True,
        returned_objects=[],
        key=f"map-{crop}-{sc.tag}-{region_key}-{basemap}-{place_names}-{opacity}",
    )

with tab_cmp:
    st.markdown(
        "<span class='hint'>Suitability class at present (left) and in the selected future (right). "
        "The two maps move together.</span>",
        unsafe_allow_html=True,
    )
    dmap = DualMap(
        location=view_center, zoom_start=view_zoom, tiles=None, control_scale=True
    )
    for side, lk, label in (
        (dmap.m1, L_PRESENT, "Present"),
        (dmap.m2, L_FUT, f"{sc.period} \u00b7 {sc.ssp_label}"),
    ):
        base_tiles(side)
        data_tiles(side, lk, label, base=False)
        top_tiles(side)
        side.add_child(MapLabel(label))
    st_folium(
        dmap,
        height=520,
        use_container_width=True,
        returned_objects=[],
        key=f"dual-{crop}-{sc.tag}-{region_key}-{basemap}-{place_names}-{opacity}",
    )
    st.markdown(
        f"<div style='font-size:12px;max-width:300px'>{legend_classes('Land suitability classes')}</div>",
        unsafe_allow_html=True,
    )

    st.markdown(
        "<div class='section-title'>Distribution of suitability change</div>"
        "<span class='hint'>Share of the area in each change class, for every scenario and period.</span>",
        unsafe_allow_html=True,
    )
    areas = {
        f"{s.ssp_label} \u00b7 {s.period}": S["delta"][(s.ssp_label, s.period)][
            "change_km2"
        ]
        for s in scenarios
        if (s.ssp_label, s.period) in S["delta"]
    }
    if areas:
        st.plotly_chart(
            charts.change_classes_figure(areas),
            width="stretch",
            theme=None,
            config=chart_config(crop, sc),
        )
    rows = []
    for s in scenarios:
        d = S["delta"].get((s.ssp_label, s.period))
        if d:
            rows.append(
                {
                    "Scenario": f"{s.ssp_label} \u00b7 {s.period}",
                    "Mean score": d["mean_future"],
                    "Mean change (points)": d["mean_delta"],
                    "Loss > 5 points (km\u00b2)": d["degraded_km2"],
                    "Gain > 5 points (km\u00b2)": d["improved_km2"],
                }
            )
    st.markdown(
        "<div class='section-title'>Scenario summary</div>"
        f"<span class='hint'>Present mean suitability score: {S['present_mean']:.1f}</span>",
        unsafe_allow_html=True,
    )
    st.dataframe(
        pd.DataFrame(rows).style.format(
            {
                "Mean score": "{:.1f}",
                "Mean change (points)": "{:+.2f}",
                "Loss > 5 points (km\u00b2)": "{:,.0f}",
                "Gain > 5 points (km\u00b2)": "{:,.0f}",
            }
        ),
        width="stretch",
        hide_index=True,
    )

ssps = sorted({k_[0] for k_ in S["mats"]})
periods = sorted({k_[1] for k_ in S["mats"]})

with tab_cls:
    if S["mats"]:
        st.markdown(
            "<span class='hint'>Area (km\u00b2) moving from each present class (rows) to each future class "
            "(columns). Black = 2041-2070, red = 2071-2100; the diagonal (no change) is blank.</span>",
            unsafe_allow_html=True,
        )
        st.plotly_chart(
            charts.transition_matrices_figure(
                S["mats"], ssps, periods, crop_label(crop), region_name
            ),
            width="stretch",
            theme=None,
            config=chart_config(crop, sc),
        )
        st.markdown(
            "<span class='hint'>For each class: area leaving it (orange), area entering it (blue) and "
            "the net balance (\u25c6).</span>",
            unsafe_allow_html=True,
        )
        st.plotly_chart(
            charts.class_dynamics_figure(
                S["mats"], ssps, periods, crop_label(crop), region_name
            ),
            width="stretch",
            theme=None,
            config=chart_config(crop, sc),
        )
        with st.expander("Tables and download (km\u00b2)"):
            st.markdown(f"**Transition matrix \u00b7 {sc.ssp_label}, {sc.period}**")
            st.dataframe(
                charts.transition_table(S["mats"][key]).style.format("{:,.1f}"),
                width="stretch",
            )
            rows = []
            for (s_, p_), m in S["mats"].items():
                lost, gained, net = charts.class_flows(m)
                rows += [
                    {
                        "Scenario": s_,
                        "Period": p_,
                        "Class": f"C{c}",
                        "Lost (km\u00b2)": lost[c - 1],
                        "Gained (km\u00b2)": gained[c - 1],
                        "Net (km\u00b2)": net[c - 1],
                    }
                    for c in range(1, 11)
                ]
            dyn = pd.DataFrame(rows)
            st.markdown("**Class balance**")
            st.dataframe(
                dyn.style.format(
                    {
                        "Lost (km\u00b2)": "{:,.1f}",
                        "Gained (km\u00b2)": "{:,.1f}",
                        "Net (km\u00b2)": "{:+,.1f}",
                    }
                ),
                width="stretch",
                hide_index=True,
            )
            long = pd.concat(
                [
                    charts.transition_table(m)
                    .iloc[:-1, :-1]
                    .stack()
                    .rename("area_km2")
                    .reset_index()
                    .assign(ssp=k_[0], period=k_[1])
                    for k_, m in S["mats"].items()
                ]
            )
            st.download_button(
                "\u2b07\ufe0f Download transitions (CSV, km\u00b2)",
                long.to_csv(index=False).encode(),
                f"transitions_{crop}_{region_key}.csv",
                "text/csv",
            )

with tab_drv:
    if not S["drivers"]:
        st.info(
            "No dominant-driver rasters for this crop yet. Add climate rasters to "
            "`data/climate/<period>/tas.tif|pr.tif` and run `python run_pipeline.py --phases 3`."
        )
    else:
        st.markdown(
            f"<span class='hint'>Area where suitability changed by more than {THR:g} points, grouped by the "
            "climate signal behind it. Labels: area and share of the changed area.</span>",
            unsafe_allow_html=True,
        )
        tables = {
            k_: charts.driver_summary_table(v, 1.0) for k_, v in S["drivers"].items()
        }
        d_ssps, d_periods = sorted({k_[0] for k_ in tables}), sorted(
            {k_[1] for k_ in tables}
        )
        st.plotly_chart(
            charts.drivers_grid_figure(
                tables, d_ssps, d_periods, crop_label(crop), region_name
            ),
            width="stretch",
            theme=None,
            config=chart_config(crop, sc),
        )
        if key in tables:
            with st.expander(f"Table \u00b7 {sc.ssp_label}, {sc.period} (km\u00b2)"):
                show = tables[key][
                    ["driver", "interpretation", "area_km2", "pct", "pct_of_changed"]
                ].rename(
                    columns={
                        "driver": "Driver",
                        "interpretation": "Meaning",
                        "area_km2": "Area (km\u00b2)",
                        "pct": "% of area",
                        "pct_of_changed": "% of changed area",
                    }
                )
                st.dataframe(
                    show.style.format(
                        {
                            "Area (km\u00b2)": "{:,.1f}",
                            "% of area": "{:.1f}",
                            "% of changed area": "{:.1f}",
                        },
                        na_rep="-",
                    ),
                    width="stretch",
                    hide_index=True,
                )

st.markdown(
    "<div class='app-footer'><span>Land suitability rasters: 100 m resolution, Stereo70 (EPSG:3844). "
    "Areas in km\u00b2. Change classes in score points (future - present).</span>"
    "<span>Basemap \u00a9 Esri \u00b7 EOCube.Ro</span></div>",
    unsafe_allow_html=True,
)
