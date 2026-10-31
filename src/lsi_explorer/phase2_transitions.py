"""Phase 2 - class transition matrices (km2) and class-dynamics charts.

Outputs per crop:
  results/transitions/<CROP>/Transitions_long_<CROP>.csv              (tidy: every scenario/interval)
  results/transitions/<CROP>/Matrix_<SSP>_Present_to_<horizon>_<CROP>.csv   (10x10 pivot, km2)
  results/transitions/<CROP>/SideBySide_Present_to_<horizon>_<CROP>.csv     (class pairs x SSP, km2)
  results/transitions/<CROP>/Class_Dynamics_<CROP>.csv               (lost / gained / net km2 per class)
  results/figures/<CROP>/Transition_Matrix_Combined_AllSSPs_<CROP>.html/.png
  results/figures/<CROP>/Diverging_Bars_AllScenarios_<CROP>.html/.png
"""

from __future__ import annotations

from collections import defaultdict

import numpy as np
import pandas as pd

from . import charts
from .preprocessing import load_categorical, reference_grid, study_mask
from .raster_ops import crosstab
from .utils import (
    crop_label,
    CLASSES,
    FIGURES_DIR,
    PRESENT,
    TRANSITIONS_DIR,
    Scenario,
    categorical_path,
    get_logger,
    list_crops,
    list_scenarios,
)

log = get_logger()


def matrix_frame(m_km2: np.ndarray, from_label: str, to_label: str) -> pd.DataFrame:
    labels = [str(c) for c in CLASSES]
    df = pd.DataFrame(
        m_km2,
        index=pd.Index(labels, name=f"{from_label} class"),
        columns=pd.Index(labels, name=f"{to_label} class"),
    )
    df["Total"] = df.sum(axis=1)
    df.loc["Total"] = df.sum(axis=0)
    return df


def long_rows(m_km2: np.ndarray, **keys) -> list[dict]:
    return [
        dict(**keys, from_class=i + 1, to_class=j + 1, area_km2=float(m_km2[i, j]))
        for i in range(m_km2.shape[0])
        for j in range(m_km2.shape[1])
    ]


def run_crop(crop: str, scenarios: list[Scenario], figures: bool = True) -> None:
    grid = reference_grid(crop)
    px_km2 = grid.pixel_area_km2
    present = load_categorical(categorical_path(crop, PRESENT), grid)
    mask = study_mask(grid, present)
    present[~mask] = 0

    by_ssp: dict[str, list[Scenario]] = defaultdict(list)
    for sc in scenarios:
        if categorical_path(crop, sc.folder).exists():
            by_ssp[sc.ssp].append(sc)

    out_dir = TRANSITIONS_DIR / crop
    out_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    dyn_rows: list[dict] = []
    side: dict[int, dict[str, np.ndarray]] = defaultdict(dict)
    mats: dict[tuple[str, str], np.ndarray] = {}

    for ssp, scs in sorted(by_ssp.items()):
        scs = sorted(scs, key=lambda s: s.start)
        prev = None
        for sc in scs:
            fut = load_categorical(categorical_path(crop, sc.folder), grid, mask)
            m = crosstab(present, fut) * px_km2
            mats[(sc.ssp_label, sc.period)] = m
            rows += long_rows(
                m,
                crop=crop,
                ssp=sc.ssp_label,
                from_period="Present",
                to_period=str(sc.horizon),
            )
            matrix_frame(m, "Present", str(sc.horizon)).to_csv(
                out_dir / f"Matrix_{ssp.upper()}_Present_to_{sc.horizon}_{crop}.csv",
                float_format="%.1f",
            )
            side[sc.horizon][sc.ssp_label] = m
            lost, gained, net = charts.class_flows(m)
            dyn_rows += [
                dict(
                    crop=crop,
                    ssp=sc.ssp_label,
                    period=sc.period,
                    cls=c,
                    lost_km2=lost[c - 1],
                    gained_km2=gained[c - 1],
                    net_km2=net[c - 1],
                )
                for c in CLASSES
            ]
            if prev is not None:
                rows += long_rows(
                    crosstab(prev[1], fut) * px_km2,
                    crop=crop,
                    ssp=sc.ssp_label,
                    from_period=str(prev[0].horizon),
                    to_period=str(sc.horizon),
                )
            prev = (sc, fut)
        del prev
        log.info("[%s] transitions done for %s", crop, ssp)

    pd.DataFrame(rows).to_csv(
        out_dir / f"Transitions_long_{crop}.csv", index=False, float_format="%.1f"
    )
    pd.DataFrame(dyn_rows).rename(columns={"cls": "class"}).to_csv(
        out_dir / f"Class_Dynamics_{crop}.csv", index=False, float_format="%.1f"
    )
    for horizon, hm in side.items():
        idx = pd.MultiIndex.from_product(
            [CLASSES, CLASSES], names=["Present class", f"{horizon} class"]
        )
        df = pd.DataFrame({k: v.ravel() for k, v in sorted(hm.items())}, index=idx)
        df = df[df.sum(axis=1) > 0]
        if len(df.columns) == 2:
            a, b = df.columns
            df[f"{b} - {a}"] = df[b] - df[a]
        df.to_csv(
            out_dir / f"SideBySide_Present_to_{horizon}_{crop}.csv", float_format="%.1f"
        )

    if figures and mats:
        ssps = sorted({k[0] for k in mats})
        periods = sorted({k[1] for k in mats})
        fig_dir = FIGURES_DIR / crop
        charts.save_figure(
            charts.transition_matrices_figure(mats, ssps, periods, crop_label(crop)),
            fig_dir / f"Transition_Matrix_Combined_AllSSPs_{crop}.html",
            fig_dir / f"Transition_Matrix_Combined_AllSSPs_{crop}.png",
        )
        charts.save_figure(
            charts.class_dynamics_figure(mats, ssps, periods, crop_label(crop)),
            fig_dir / f"Diverging_Bars_AllScenarios_{crop}.html",
            fig_dir / f"Diverging_Bars_AllScenarios_{crop}.png",
        )
