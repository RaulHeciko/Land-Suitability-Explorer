"""Phase 1 - continuous suitability change rasters: dS = Future - Present.

Outputs results/deltas/<CROP>/Delta_Suitability_<SSP>_<period>_<CROP>.tif (float32, NaN = NoData)
and results/deltas/delta_summary.csv.
"""

from __future__ import annotations


import numpy as np
import pandas as pd

from .preprocessing import load_continuous, reference_grid, study_mask
from .raster_ops import write_geotiff
from .utils import (
    DELTAS_DIR,
    PRESENT,
    SIGNIFICANCE_THRESHOLD,
    Scenario,
    continuous_path,
    delta_path,
    get_logger,
    list_crops,
    list_scenarios,
)

log = get_logger()


def delta_stats(delta: np.ndarray, pixel_area_km2: float) -> dict:
    v = delta[np.isfinite(delta)]
    t = SIGNIFICANCE_THRESHOLD
    n = v.size or 1
    return dict(
        valid_km2=v.size * pixel_area_km2,
        mean_delta=float(v.mean()) if v.size else np.nan,
        median_delta=float(np.median(v)) if v.size else np.nan,
        degraded_km2=float((v < 0).sum() * pixel_area_km2),
        improved_km2=float((v > 0).sum() * pixel_area_km2),
        degraded_sig_km2=float((v < -t).sum() * pixel_area_km2),
        improved_sig_km2=float((v > t).sum() * pixel_area_km2),
        degraded_sig_pct=float((v < -t).sum() / n * 100),
        improved_sig_pct=float((v > t).sum() / n * 100),
    )


def run_crop(
    crop: str, scenarios: list[Scenario], overwrite: bool = False
) -> list[dict]:
    grid = reference_grid(crop)
    present = None
    rows = []
    for sc in scenarios:
        fut_path = continuous_path(crop, sc.folder)
        if not fut_path.exists():
            log.warning("[%s] missing %s", crop, fut_path)
            continue
        out = delta_path(crop, sc)
        if out.exists() and not overwrite:
            log.info("[%s] %s exists - reading for stats", crop, out.name)
            from .raster_ops import read_aligned

            delta = read_aligned(out, grid)
        else:
            if present is None:
                present = load_continuous(continuous_path(crop, PRESENT), grid)
                mask = study_mask(grid, present)
                present[~mask] = np.nan
            future = load_continuous(fut_path, grid, mask)
            delta = future - present  # NaN propagates where either is NoData
            del future
            write_geotiff(
                out,
                delta,
                grid,
                nodata=np.nan,
                descriptions=f"Delta suitability {sc.label}",
            )
            log.info("[%s] wrote %s", crop, out.relative_to(DELTAS_DIR.parent))
        rows.append(
            dict(
                crop=crop,
                ssp=sc.ssp_label,
                horizon=sc.horizon,
                period=sc.period,
                **delta_stats(delta, grid.pixel_area_km2),
            )
        )
        del delta
    return rows


def write_summary(rows: list[dict]) -> None:
    if not rows:
        return
    path = DELTAS_DIR / "delta_summary.csv"
    new = pd.DataFrame(rows)
    if path.exists():
        old = pd.read_csv(path)
        old = old[~old.crop.isin(new.crop.unique())]
        new = pd.concat([old, new], ignore_index=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    new.sort_values(["crop", "ssp", "horizon"]).to_csv(
        path, index=False, float_format="%.3f"
    )
