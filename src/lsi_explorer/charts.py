"""Plotly figures shared by the pipeline (static exports) and the dashboard.

The three summary figures reproduce the project's reference layouts:
  transition_matrices_figure - 10x10 matrices per SSP, two periods per cell (black / red)
  class_dynamics_figure      - area lost / gained / net per class, SSP rows x period columns
  drivers_grid_figure        - dominant-driver areas, SSP rows x period columns
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from . import utils
from .i18n import t
from .utils import CHANGE_CLASSES, CLASSES, DRIVERS, get_logger

log = get_logger()

CLASS_COLORS = utils.CLASS_COLORS  # class 1 (dark green, best) .. 10 (red)
PERIOD2_COLOR = "#D7191C"
# light part of YlGnBu only, so black (period 1) and red (period 2) numbers stay readable
MATRIX_SCALE = [
    [0, "#ffffd9"],
    [0.3, "#edf8b1"],
    [0.55, "#c7e9b4"],
    [0.8, "#7fcdbb"],
    [1, "#4fb9c6"],
]
LOST_COLOR, GAIN_COLOR = "#E66100", "#0B6FB0"
FONT = dict(
    family="Source Sans Pro, Segoe UI, Arial, sans-serif", size=12, color="#131C2E"
)

# key for every scenario-indexed dict below: (ssp_label, period) e.g. ("SSP2-4.5", "2041-2070")
Key = tuple[str, str]


def area_unit(max_km2: float) -> tuple[float, str]:
    """Pick a readable unit for a set of areas given in km2 -> (divisor, label)."""
    if max_km2 >= 1e3:
        return 1e3, "10\u00b3 km\u00b2"
    return 1.0, "km\u00b2"


def fmt_km2(v: float) -> str:
    """Compact km2 label: 57,960 km2 - 412 km2 - 3.7 km2."""
    if not np.isfinite(v):
        return "-"
    return f"{v:,.0f} km\u00b2" if abs(v) >= 100 else f"{v:,.1f} km\u00b2"


def _rows_geometry(
    rows: int, row_px: float, gap_px: float, top: int = 120, bottom: int = 70
) -> tuple[int, float]:
    """Figure height and plotly vertical_spacing for `rows` panels of `row_px` pixels
    separated by `gap_px` pixels (keeps panel size independent of the number of rows).
    """
    plot = rows * row_px + (rows - 1) * gap_px
    return int(plot + top + bottom), (gap_px / plot if rows > 1 else 0.0)


def _layout(
    fig: go.Figure, title: str, subtitle: str, height: int, bottom: int = 40
) -> go.Figure:
    fig.update_layout(
        title=dict(
            text=f"<b>{title}</b><br><span style='font-size:13px;color:#555'>{subtitle}</span>",
            x=0.02,
            xanchor="left",
            yref="container",
            y=1,
            yanchor="top",
            pad=dict(t=16),
        ),
        font=FONT,
        height=height,
        plot_bgcolor="white",
        paper_bgcolor="white",
        margin=dict(l=20, r=20, t=120, b=bottom),
    )
    fig.update_xaxes(automargin=True)
    fig.update_yaxes(automargin=True, title_standoff=10)
    return fig


# ------------------------------------------------------------------ transition matrices


def transition_matrices_figure(
    mats: dict[Key, np.ndarray],
    ssps: list[str],
    periods: list[str],
    crop: str,
    region: str = "",
) -> go.Figure:
    """mats[(ssp, period)][i, j] = km2 moving from present class i+1 to future class j+1."""
    allv = np.concatenate([m.ravel() for m in mats.values()]) if mats else np.zeros(1)
    off = allv[allv > 0]
    div, unit = 1.0, "km\u00b2"
    nf = (
        ".0f" if (off.max() if off.size else 0) >= 100 else ".1f"
    )  # small areas keep a decimal
    zmax = np.log10(1 + (off.max() / div if off.size else 1))
    labels = [f"C{c}" for c in CLASSES]
    fig = make_subplots(
        rows=1,
        cols=len(ssps),
        subplot_titles=[t("charts.scenario", ssp=s) for s in ssps],
        horizontal_spacing=0.07,
    )
    for k, ssp in enumerate(ssps, 1):
        a = mats.get((ssp, periods[0]), np.zeros((10, 10))) / div
        b = (
            mats.get((ssp, periods[1]), np.zeros((10, 10))) / div
            if len(periods) > 1
            else None
        )
        both = a + (b if b is not None else 0)
        z = np.log10(1 + np.maximum(a, b if b is not None else a))
        empty = (both <= 0) | np.eye(10, dtype=bool)
        z[empty] = np.nan
        custom = np.dstack([a, b if b is not None else a])
        hover = (
            f"Present %{{y}} -> %{{x}}<br>{periods[0]}: %{{customdata[0]:,.1f}} {unit}"
            + (
                f"<br>{periods[1]}: %{{customdata[1]:,.1f}} {unit}"
                if b is not None
                else ""
            )
            + "<extra></extra>"
        )
        fig.add_trace(
            go.Heatmap(
                z=z,
                x=labels,
                y=labels,
                customdata=custom,
                colorscale=MATRIX_SCALE,
                zmin=0,
                zmax=zmax,
                showscale=False,
                xgap=0,
                ygap=0,
                hovertemplate=hover,
                hoverongaps=False,
            ),
            row=1,
            col=k,
        )
        for i in range(10):
            for j in range(10):
                if empty[i, j]:
                    continue
                txt = f"<b><span style='color:#111'>{a[i, j]:{nf}}</span></b>"
                if b is not None:
                    txt += (
                        f"<br><span style='color:{PERIOD2_COLOR}'>{b[i, j]:{nf}}</span>"
                    )
                fig.add_annotation(
                    x=labels[j],
                    y=labels[i],
                    text=txt,
                    showarrow=False,
                    font=dict(size=10.5),
                    xref=f"x{k if k > 1 else ''}",
                    yref=f"y{k if k > 1 else ''}",
                )
        fig.update_xaxes(
            title_text=t("charts.future_class"),
            row=1,
            col=k,
            showgrid=False,
            ticks="",
            side="bottom",
            constrain="domain",
        )
        fig.update_yaxes(
            title_text=t("charts.present_class"),
            row=1,
            col=k,
            autorange="reversed",
            showgrid=False,
            ticks="",
            scaleanchor=f"x{k if k > 1 else ''}",
            constrain="domain",
        )
    sub = (
        f"{t('charts.crop', crop=crop)}{' | ' + region if region else ''} | "
        f"{t('charts.cell_values', unit=unit)}: <b>{periods[0]}</b>"
    )
    if len(periods) > 1:
        sub += f" | <span style='color:{PERIOD2_COLOR}'><b>{periods[1]}</b></span>"
    return _layout(fig, t("charts.matrices_title"), sub, 640)


def transition_table(m_km2: np.ndarray, div: float = 1.0) -> pd.DataFrame:
    labels = [f"C{c}" for c in CLASSES]
    df = pd.DataFrame(
        m_km2 / div,
        index=pd.Index(labels, name="Present"),
        columns=pd.Index(labels, name="Future"),
    )
    df["Total"] = df.sum(axis=1)
    df.loc["Total"] = df.sum(axis=0)
    return df


# ------------------------------------------------------------------ class dynamics


def class_flows(m_km2: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(lost, gained, net) km2 per class from a present->future matrix."""
    off = m_km2 * (1 - np.eye(m_km2.shape[0]))
    lost, gained = off.sum(axis=1), off.sum(axis=0)
    return lost, gained, gained - lost


def class_dynamics_figure(
    mats: dict[Key, np.ndarray],
    ssps: list[str],
    periods: list[str],
    crop: str,
    region: str = "",
) -> go.Figure:
    flows = {k: class_flows(m) for k, m in mats.items()}
    mx = max([max(l.max(), g.max()) for l, g, _ in flows.values()] + [1])
    div, unit = area_unit(mx)
    lim = mx / div * 1.08
    labels = [f"C{c}" for c in CLASSES]
    height, vspace = _rows_geometry(len(ssps), 300, 90, bottom=90)
    fig = make_subplots(
        rows=len(ssps),
        cols=len(periods),
        subplot_titles=[p for s in ssps for p in periods],
        horizontal_spacing=0.08,
        vertical_spacing=vspace,
        shared_yaxes=False,
    )
    for r, ssp in enumerate(ssps, 1):
        for c, period in enumerate(periods, 1):
            if (ssp, period) not in flows:
                continue
            lost, gained, net = (v / div for v in flows[(ssp, period)])
            first = r == 1 and c == 1
            fig.add_bar(
                y=labels,
                x=-lost,
                orientation="h",
                marker=dict(color=LOST_COLOR, line=dict(color="#7a3600", width=0.6)),
                name=t("charts.lost"),
                legendgroup="lost",
                showlegend=first,
                row=r,
                col=c,
                customdata=lost,
                hovertemplate=f"%{{y}} lost %{{customdata:,.2f}} {unit}<extra></extra>",
            )
            fig.add_bar(
                y=labels,
                x=gained,
                orientation="h",
                marker=dict(color=GAIN_COLOR, line=dict(color="#05385a", width=0.6)),
                name=t("charts.gain"),
                legendgroup="gain",
                showlegend=first,
                row=r,
                col=c,
                hovertemplate=f"%{{y}} gained %{{x:,.2f}} {unit}<extra></extra>",
            )
            txt = [f"{v:.1f}" if abs(v) >= 0.05 else "" for v in net]
            pos = ["middle left" if v < 0 else "middle right" for v in net]
            fig.add_scatter(
                y=labels,
                x=net,
                mode="markers+text",
                text=txt,
                textposition=pos,
                textfont=dict(size=10),
                marker=dict(symbol="diamond", size=8, color="black"),
                name=t("charts.net"),
                legendgroup="net",
                showlegend=first,
                row=r,
                col=c,
                hovertemplate=f"%{{y}} net %{{x:+,.2f}} {unit}<extra></extra>",
            )
            fig.update_xaxes(
                range=[-lim, lim],
                title_text=(
                    t("charts.area_change", unit=unit) if r == len(ssps) else None
                ),
                zeroline=True,
                zerolinecolor="black",
                zerolinewidth=1.2,
                gridcolor="#eee",
                row=r,
                col=c,
            )
            fig.update_yaxes(
                autorange="reversed",
                gridcolor="#eee",
                row=r,
                col=c,
                title_text=(
                    f"{ssp}<br>{t('charts.suitability_class')}" if c == 1 else None
                ),
            )
    fig.update_layout(
        barmode="overlay",
        bargap=0.18,
        legend=dict(
            orientation="h",
            x=0.5,
            xanchor="center",
            yref="container",
            y=0.005,
            yanchor="bottom",
        ),
    )
    return _layout(
        fig,
        t("charts.dynamics_title"),
        f"{t('charts.crop', crop=crop)}{' | ' + region if region else ''}",
        height,
        bottom=90,
    )


# ------------------------------------------------------------------ drivers


def driver_summary_table(counts: np.ndarray, pixel_area_km2: float) -> pd.DataFrame:
    """counts[code] for codes 0..8 -> table with km2 and percentages."""
    rows = []
    total = counts[:9].sum()
    for code, (name, interp, color) in DRIVERS.items():
        px_km2 = counts[code] * pixel_area_km2
        rows.append(
            dict(
                code=code,
                driver=name,
                interpretation=interp,
                color=color,
                area_km2=px_km2,
                pct=(counts[code] / total * 100) if total else 0.0,
            )
        )
    df = pd.DataFrame(rows)
    active = df.loc[df.code > 0, "area_km2"].sum()
    df["pct_of_changed"] = np.where(
        df.code > 0, df.area_km2 / active * 100 if active else 0.0, np.nan
    )
    return df


def drivers_grid_figure(
    tables: dict[Key, pd.DataFrame],
    ssps: list[str],
    periods: list[str],
    crop: str,
    region: str = "",
) -> go.Figure:
    """tables[(ssp, period)] = driver_summary_table(...). Shows drivers with area in any scenario."""
    present = sorted(
        {
            int(c)
            for tbl in tables.values()
            for c in tbl.loc[(tbl.code > 0) & (tbl.area_km2 > 0), "code"]
        }
    )
    mx = max([tbl.loc[tbl.code > 0, "area_km2"].max() for tbl in tables.values()] + [1])
    div, unit = area_unit(mx)
    n = max(len(present), 1)
    height, vspace = _rows_geometry(len(ssps), 54 * n + 10, 80)
    fig = make_subplots(
        rows=len(ssps),
        cols=len(periods),
        subplot_titles=[p for s in ssps for p in periods],
        horizontal_spacing=0.06,
        vertical_spacing=vspace,
    )
    for r, ssp in enumerate(ssps, 1):
        for c, period in enumerate(periods, 1):
            tbl = tables.get((ssp, period))
            if tbl is None:
                continue
            d = tbl.set_index("code").loc[present]
            v = d.area_km2 / div
            fig.add_bar(
                y=d.driver,
                x=v,
                orientation="h",
                marker=dict(color=d.color, line=dict(color="#333", width=0.8)),
                text=[
                    f"{a:.1f} ({p:.1f}%)" if a > 0 else ""
                    for a, p in zip(v, d.pct_of_changed.fillna(0))
                ],
                textposition="outside",
                textfont=dict(size=11),
                cliponaxis=False,
                showlegend=False,
                customdata=d.interpretation,
                hovertemplate=f"%{{y}}<br>%{{x:,.2f}} {unit}<br>%{{customdata}}<extra></extra>",
                row=r,
                col=c,
            )
            fig.update_xaxes(
                range=[0, mx / div * 1.3],
                title_text=t("charts.area", unit=unit) if r == len(ssps) else None,
                gridcolor="#eee",
                showline=True,
                linecolor="black",
                row=r,
                col=c,
            )
            fig.update_yaxes(
                range=[n - 0.5, -0.5],
                showline=True,
                linecolor="black",
                row=r,
                col=c,
                showticklabels=c == 1,
                title_text=f"<b>{ssp}</b>" if c == 1 else None,
            )
    fig.update_layout(bargap=0.4)
    return _layout(
        fig,
        t("charts.drivers_title"),
        f"{t('charts.crop', crop=crop)}{' | ' + region if region else ''} | "
        f"{t('charts.drivers_labels', unit=unit)}",
        height,
        bottom=70,
    )


# ------------------------------------------------------------------ misc


def change_classes_figure(areas: dict[str, np.ndarray], title: str = "") -> go.Figure:
    """areas[scenario label] = km2 in change classes 1..5 -> one 100 % stacked bar per scenario."""
    labels = list(areas)
    fig = go.Figure()
    for code, (name, color) in CHANGE_CLASSES.items():
        km2 = np.array([areas[l][code - 1] for l in labels])
        tot = np.array([areas[l].sum() or 1 for l in labels])
        pct = km2 / tot * 100
        fig.add_bar(
            y=labels,
            x=pct,
            orientation="h",
            name=name,
            marker=dict(color=color, line=dict(color="#666", width=0.5)),
            customdata=km2,
            text=[f"{p:.0f}%" if p >= 3 else "" for p in pct],
            textposition="inside",
            insidetextanchor="middle",
            textfont=dict(size=[11 if p >= 7 else 9 for p in pct], color="#222"),
            textangle=0,
            constraintext="none",
            hovertemplate=f"%{{y}}<br>{name}: %{{customdata:,.0f}} km\u00b2 (%{{x:.1f}}%)<extra></extra>",
        )
    fig.update_layout(
        barmode="stack",
        title=title,
        font=FONT,
        plot_bgcolor="white",
        paper_bgcolor="white",
        height=110 + 46 * len(labels),
        xaxis=dict(range=[0, 100.5], dtick=20, ticksuffix="%", gridcolor="#eee"),
        yaxis=dict(autorange="reversed", automargin=True),
        legend=dict(
            orientation="h",
            x=0,
            y=-0.18,
            title_text=t("charts.change_legend"),
            traceorder="normal",
        ),
        margin=dict(l=10, r=10, t=50 if title else 10, b=10),
        bargap=0.35,
    )
    return fig


_png_ok = True


def save_figure(
    fig: go.Figure,
    html_path: Path,
    png_path: Path | None = None,
    width: int = 1400,
    scale: float = 1.5,
) -> None:
    """Write interactive HTML and, when kaleido/Chrome are available, a static PNG."""
    global _png_ok
    html_path.parent.mkdir(parents=True, exist_ok=True)
    fig.write_html(html_path, include_plotlyjs="cdn")
    if png_path is None or not _png_ok:
        return
    try:
        fig.write_image(
            png_path, scale=scale, width=width, height=fig.layout.height or 700
        )
    except Exception as e:  # kaleido missing or no Chrome available
        _png_ok = False
        log.warning(
            "PNG export disabled (%s). Install Chrome for kaleido: `plotly_get_chrome`.",
            e,
        )
