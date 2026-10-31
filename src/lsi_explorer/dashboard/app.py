"""Land Suitability Explorer - interactive dashboard (Streamlit).

Start with ``lsi app`` (applies the project theme). The UI layer may use any dependency;
all computations come from the lsi_explorer library.
"""

from __future__ import annotations

import base64
import hashlib
from pathlib import Path

import folium
import numpy as np
import pandas as pd
import streamlit as st
from branca.element import MacroElement
from folium.plugins import DualMap, Fullscreen
from jinja2 import Template
from pyproj import Transformer
from rasterio.transform import array_bounds
from rasterio.windows import Window
from rasterio.windows import transform as window_transform
from streamlit_folium import st_folium

from lsi_explorer import charts, tileserver
from lsi_explorer.admin import load_admin_layer, option_index, uat_label, uats_in_county
from lsi_explorer.analysis import area_window
from lsi_explorer.charts import fmt_km2
from lsi_explorer.i18n import available_languages, get_language, set_language, t
from lsi_explorer.preprocessing import reference_grid
from lsi_explorer.raster_ops import Grid
from lsi_explorer.region_stats import region_summary
from lsi_explorer.tileserver import REGISTRY
from lsi_explorer.utils import (
    CHANGE_CLASSES,
    DRIVERS,
    PRESENT,
    SIGNIFICANCE_THRESHOLD,
    Scenario,
    categorical_path,
    continuous_path,
    crop_label,
    crop_names,
    find_driver_raster,
    list_crops,
    list_scenarios,
)

ASSETS = Path(__file__).resolve().parent / "assets"

# language of this run only: ?lang=xx, else detected from the environment
_lang = st.query_params.get("lang")
set_language(_lang if _lang in available_languages() else None)

st.set_page_config(
    page_title=t("app.page_title"),
    page_icon=str(ASSETS / "geolass_icon.png"),
    layout="wide",
)

ESRI = "https://server.arcgisonline.com/ArcGIS/rest/services/{}/MapServer/tile/{{z}}/{{y}}/{{x}}"
BASEMAPS = {
    "light": (ESRI.format("Canvas/World_Light_Gray_Base"), 16),
    "satellite": (ESRI.format("World_Imagery"), 18),
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
def catalogue(lang: str):
    """Crops, scenarios and crop names (names depend on the interface language)."""
    return list_crops(), list_scenarios(), crop_names()


@st.cache_resource(show_spinner=False)
def tile_port() -> int:
    return tileserver.start()


@st.cache_resource(show_spinner=False)
def grid_for(crop: str) -> Grid:
    return reference_grid(crop)


@st.cache_resource(show_spinner=False)
def admin_layer(level: str, crs_wkt: str):
    return load_admin_layer(level, crs_wkt)


@st.cache_data(show_spinner=False)
def asset_uri(name: str) -> str:
    """Image from dashboard/assets/ as a data URI, for use inside st.markdown HTML."""
    data = (ASSETS / name).read_bytes()
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

crops, scenarios, names = catalogue(get_language())
if not crops:
    st.error(t("app.no_data"))
    st.stop()

with st.sidebar:
    st.markdown(
        f"<div class='brand'><img src='{asset_uri('geolass_icon.png')}' alt='GeoLaSS'><div>"
        f"<div class='brand-name'>{t('app.page_title')}</div>"
        f"<div class='brand-sub'>{t('app.brand_sub')}</div></div></div>"
        f"<div class='side-section'>{t('app.side.selection')}</div>",
        unsafe_allow_html=True,
    )
    qp = st.query_params  # selection restored from / written to the page URL
    crops = sorted(crops, key=lambda c: names.get(c, c))
    crop = st.selectbox(
        t("app.crop"),
        crops,
        index=option_index(crops, qp.get("crop")),
        format_func=crop_label,
    )
    ssp_labels = sorted({s.ssp_label for s in scenarios})
    ssp = st.radio(
        t("app.scenario"),
        ssp_labels,
        index=option_index(ssp_labels, qp.get("ssp"), len(ssp_labels) - 1),
        horizontal=True,
        help=t("app.scenario_help"),
    )
    ssp_scs = sorted(
        [s for s in scenarios if s.ssp_label == ssp], key=lambda s: s.start
    )
    periods_ssp = [s.period for s in ssp_scs]
    period = st.radio(
        t("app.period"),
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
        ["all"]
        + (["judet"] if judete is not None else [])
        + (["uat"] if uats is not None else [])
    )
    if len(levels) > 1:
        st.markdown(
            f"<div class='side-section'>{t('app.side.area')}</div>",
            unsafe_allow_html=True,
        )
        level = st.radio(
            t("app.side.area"),
            levels,
            index=option_index(levels, qp.get("area")),
            format_func=lambda lv: t(f"app.area.{lv}"),
            label_visibility="collapsed",
        )
        county_names = sorted(judete._label.unique()) if judete is not None else []
        if level == "judet":
            jname = st.selectbox(
                t("app.judet"),
                county_names,
                index=option_index(county_names, qp.get("judet")),
            )
            geom = judete[judete._label == jname].union_all()
            region_name = t("app.region.judet", name=jname)
            url_area = {"area": "judet", "judet": jname}
        elif level == "uat":
            pool, jname = uats, ""
            if judete is not None:
                jname = st.selectbox(
                    t("app.judet"),
                    county_names,
                    index=option_index(county_names, qp.get("judet")),
                )
                pool = uats_in_county(uats, judete, jname)
            pool = pool.assign(_ui=pool.apply(uat_label, axis=1)).sort_values("_ui")
            idx = st.selectbox(
                t("app.uat"),
                pool.index.tolist(),
                index=option_index(pool["_ui"].tolist(), qp.get("uat")),
                format_func=lambda i: pool.at[i, "_ui"],
                help=t("app.uat_help"),
            )
            geom = pool.at[idx, "geometry"]
            region_name = t("app.region.uat", name=pool.at[idx, "_ui"])
            url_area = {"area": "uat", "judet": jname, "uat": pool.at[idx, "_ui"]}

    url_state = {"crop": crop, "ssp": ssp, "period": period}
    url_state.update(url_area or {"area": "all"})
    if qp.get("lang"):
        url_state["lang"] = qp.get("lang")
    st.query_params.from_dict(url_state)
    st.markdown(
        f"<div class='side-section'>{t('app.side.display')}</div>",
        unsafe_allow_html=True,
    )
    with st.expander(t("app.map_style")):
        basemap = st.radio(
            t("app.basemap"),
            list(BASEMAPS),
            format_func=lambda b: t(f"app.basemaps.{b}"),
            horizontal=True,
        )
        place_names = st.checkbox(t("app.place_names"), value=False)
        opacity = st.slider(t("app.opacity"), 0.3, 1.0, 1.0, 0.05)
    with st.expander(t("app.howto.title")):
        st.markdown(t("app.howto.body"))
    if len(levels) == 1:
        st.caption(t("app.no_admin"))

# ------------------------------------------------------------------ region

try:
    window, mask = area_window(grid, geom)
except ValueError:
    st.error(t("app.no_overlap"))
    st.stop()
win = (int(window.col_off), int(window.row_off), int(window.width), int(window.height))
wt = window_transform(window, grid.transform)
if geom is not None:
    region_key = hashlib.md5(geom.wkb).hexdigest()[:12]
    REGISTRY.add_region(region_key, win[1], win[0], mask)
else:
    region_key = "all"

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
with st.spinner(t("app.spinner")):
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
    """HTML card for one key figure (left border in the `accent` colour)."""
    return (
        f"<div class='kpi' style='--kpi:{accent}'><div class='kpi-label'>{label}</div>"
        f"<div class='kpi-value'>{value}</div><div class='kpi-sub'>{sub}</div></div>"
    )


st.markdown(
    "<div class='app-header'>"
    f"<div class='overline'>{t('app.header.overline')}</div>"
    f"<div class='app-title'>{names.get(crop, crop)}<span class='code'>{crop}</span></div>"
    "<div class='chips'>"
    f"<span class='chip'>{region_name or t('app.area.all')}</span>"
    f"<span class='chip'>{t('app.header.assessed', area=fmt_km2(S['area_km2']))}</span>"
    f"<span class='chip'>{t('app.header.scenario', ssp=sc.ssp_label)}</span>"
    f"<span class='chip'>{t('app.header.period', period=sc.period)}</span>"
    "</div></div>",
    unsafe_allow_html=True,
)
vk = D.get("valid_km2", 0) or 1
mf, dm = D.get("mean_future", np.nan), D.get("mean_delta", np.nan)
st.markdown(
    "<div class='kpis'>"
    + kpi(
        t("app.kpi.mean", period=sc.period),
        f"{mf:.1f}",
        f"{t('app.kpi.present')} {S['present_mean']:.1f} &nbsp;"
        f"{signed(mf - S['present_mean'], '+.1f')}",
        "#1c355d",
    )
    + kpi(
        t("app.kpi.change"),
        f"{signed(dm, '+.2f')} <span style='font-size:.9rem;color:#6B7780'>"
        f"{t('app.kpi.points')}</span>",
        t("app.kpi.change_sub"),
        "#1c355d",
    )
    + kpi(
        t("app.kpi.loss"),
        fmt_km2(D.get("degraded_km2", np.nan)),
        t(
            "app.kpi.loss_sub",
            pct=f"{D.get('degraded_km2', 0) / vk * 100:.1f}",
            thr=f"{THR:g}",
        ),
        "#b3261e",
    )
    + kpi(
        t("app.kpi.gain"),
        fmt_km2(D.get("improved_km2", np.nan)),
        t(
            "app.kpi.gain_sub",
            pct=f"{D.get('improved_km2', 0) / vk * 100:.1f}",
            thr=f"{THR:g}",
        ),
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
    reg(t("app.inspect.score_present"), "score", continuous_path(crop, PRESENT)),
    reg(t("app.inspect.class_present"), "classes", categorical_path(crop, PRESENT)),
    reg(
        t("app.inspect.score_future", period=sc.period),
        "score",
        continuous_path(crop, sc.folder),
    ),
    reg(
        t("app.inspect.class_future", period=sc.period),
        "classes",
        categorical_path(crop, sc.folder),
    ),
    reg(
        t("app.inspect.change"),
        "delta",
        continuous_path(crop, PRESENT),
        continuous_path(crop, sc.folder),
    ),
]
if drv_path is not None:
    INSPECT.append(reg(t("app.inspect.driver"), "driver", drv_path))
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
        f"<div style='text-align:center;font-size:10px;color:#333'>{label}"
        f"<div style='width:{w}px;height:11px;background:{c};border:1px solid #0003;margin-top:1px'></div></div>"
        for label, c in items
    )
    return f"<div style='display:flex;gap:2px;margin-top:3px'>{cells}</div>"


def legend_classes(title):
    """C1..C10 swatches with 'most / least suitable' under the ends."""
    return (
        f"<b>{title}</b>"
        + _swatch_row([(f"C{c}", charts.CLASS_COLORS[c - 1]) for c in range(1, 11)], 19)
        + "<div style='display:flex;justify-content:space-between;color:#777;font-size:10px'>"
        f"<span>{t('app.legend.most')}</span><span>{t('app.legend.least')}</span></div>"
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
        f"<b>{t('app.legend.change')}</b> <span style='color:#777'>{t('app.legend.points')}</span>"
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
    return f"<b>{t('app.legend.drivers')}</b><div style='margin-top:3px'>{rows}</div>"


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
    """Small caption box in the top-left corner of a map."""

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
        name=t(f"app.basemaps.{basemap}"),
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
    [
        t("app.tabs.map"),
        t("app.tabs.compare"),
        t("app.tabs.classes"),
        t("app.tabs.drivers"),
    ]
)

with tab_map:
    st.markdown(
        f"<span class='hint'>{t('app.map.hint')}</span>", unsafe_allow_html=True
    )
    initial = t("app.layer.present")
    choices = [
        (initial, L_PRESENT, legend_classes(t("app.legend.classes_present"))),
        (
            t("app.layer.future", period=sc.period),
            L_FUT,
            legend_classes(t("app.legend.classes_future", period=sc.period)),
        ),
        (t("app.layer.change"), L_CHG, legend_change()),
    ]
    if L_DRV:
        choices.append(
            (t("app.layer.driver"), L_DRV, legend_drivers(S["drivers"].get(key)))
        )
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
        position="topleft",
        title=t("app.map.fullscreen"),
        title_cancel=t("app.map.exit_fullscreen"),
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
        f"<span class='hint'>{t('app.compare.hint')}</span>", unsafe_allow_html=True
    )
    dmap = DualMap(
        location=view_center, zoom_start=view_zoom, tiles=None, control_scale=True
    )
    for side, lk, label in (
        (dmap.m1, L_PRESENT, t("app.compare.present")),
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
        f"<div style='font-size:12px;max-width:300px'>{legend_classes(t('app.legend.classes'))}</div>",
        unsafe_allow_html=True,
    )

    st.markdown(
        f"<div class='section-title'>{t('app.compare.dist_title')}</div>"
        f"<span class='hint'>{t('app.compare.dist_hint')}</span>",
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
                    t("app.table.scenario"): f"{s.ssp_label} \u00b7 {s.period}",
                    t("app.table.mean_score"): d["mean_future"],
                    t("app.table.mean_change"): d["mean_delta"],
                    t("app.table.loss"): d["degraded_km2"],
                    t("app.table.gain"): d["improved_km2"],
                }
            )
    st.markdown(
        f"<div class='section-title'>{t('app.compare.summary_title')}</div>"
        f"<span class='hint'>"
        f"{t('app.compare.summary_hint', value=format(S['present_mean'], '.1f'))}</span>",
        unsafe_allow_html=True,
    )
    st.dataframe(
        pd.DataFrame(rows).style.format(
            {
                t("app.table.mean_score"): "{:.1f}",
                t("app.table.mean_change"): "{:+.2f}",
                t("app.table.loss"): "{:,.0f}",
                t("app.table.gain"): "{:,.0f}",
            }
        ),
        width="stretch",
        hide_index=True,
    )

ssps = sorted({k_[0] for k_ in S["mats"]})
periods = sorted({k_[1] for k_ in S["mats"]})

with tab_cls:
    if S["mats"]:
        p1, p2 = (periods + [""])[:2]
        st.markdown(
            f"<span class='hint'>{t('app.classes.hint_matrix', p1=p1, p2=p2)}</span>",
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
            f"<span class='hint'>{t('app.classes.hint_dynamics')}</span>",
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
        with st.expander(t("app.classes.tables")):
            st.markdown(
                f"**{t('app.classes.matrix_title', ssp=sc.ssp_label, period=sc.period)}**"
            )
            st.dataframe(
                charts.transition_table(S["mats"][key]).style.format("{:,.1f}"),
                width="stretch",
            )
            rows = []
            for (s_, p_), m in S["mats"].items():
                lost, gained, net = charts.class_flows(m)
                rows += [
                    {
                        t("app.table.scenario"): s_,
                        t("app.table.period"): p_,
                        t("app.table.class"): f"C{c}",
                        t("app.table.lost"): lost[c - 1],
                        t("app.table.gained"): gained[c - 1],
                        t("app.table.net"): net[c - 1],
                    }
                    for c in range(1, 11)
                ]
            st.markdown(f"**{t('app.classes.balance')}**")
            st.dataframe(
                pd.DataFrame(rows).style.format(
                    {
                        t("app.table.lost"): "{:,.1f}",
                        t("app.table.gained"): "{:,.1f}",
                        t("app.table.net"): "{:+,.1f}",
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
                t("app.classes.download"),
                long.to_csv(index=False).encode(),
                f"transitions_{crop}_{region_key}.csv",
                "text/csv",
            )

with tab_drv:
    if not S["drivers"]:
        st.info(t("app.drivers.none"))
    else:
        st.markdown(
            f"<span class='hint'>{t('app.drivers.hint', thr=f'{THR:g}')}</span>",
            unsafe_allow_html=True,
        )
        tables = {
            k_: charts.driver_summary_table(v, 1.0) for k_, v in S["drivers"].items()
        }
        d_ssps = sorted({k_[0] for k_ in tables})
        d_periods = sorted({k_[1] for k_ in tables})
        st.plotly_chart(
            charts.drivers_grid_figure(
                tables, d_ssps, d_periods, crop_label(crop), region_name
            ),
            width="stretch",
            theme=None,
            config=chart_config(crop, sc),
        )
        if key in tables:
            with st.expander(
                t("app.drivers.table", ssp=sc.ssp_label, period=sc.period)
            ):
                show = tables[key][
                    ["driver", "interpretation", "area_km2", "pct", "pct_of_changed"]
                ].rename(
                    columns={
                        "driver": t("app.table.driver"),
                        "interpretation": t("app.table.meaning"),
                        "area_km2": t("app.table.area"),
                        "pct": t("app.table.pct"),
                        "pct_of_changed": t("app.table.pct_changed"),
                    }
                )
                st.dataframe(
                    show.style.format(
                        {
                            t("app.table.area"): "{:,.1f}",
                            t("app.table.pct"): "{:.1f}",
                            t("app.table.pct_changed"): "{:.1f}",
                        },
                        na_rep="-",
                    ),
                    width="stretch",
                    hide_index=True,
                )

st.markdown(
    f"<div class='app-footer'><span>{t('app.footer.left')}</span>"
    f"<span>{t('app.footer.right')}</span></div>",
    unsafe_allow_html=True,
)
