"""Full-resolution statistics for a region (window + optional polygon mask) used by the dashboard."""

from __future__ import annotations

import numpy as np
from rasterio.windows import Window

from .preprocessing import clean_categorical, clean_continuous
from .raster_ops import Grid, crosstab, read_window
from .utils import (
    PRESENT,
    change_class,
    SIGNIFICANCE_THRESHOLD,
    Scenario,
    categorical_path,
    continuous_path,
    find_driver_raster,
)


def _sel(arr: np.ndarray, mask: np.ndarray | None) -> np.ndarray:
    return arr[mask] if mask is not None else arr.ravel()


def region_summary(
    crop: str,
    scenarios: list[Scenario],
    grid: Grid,
    window: Window,
    mask: np.ndarray | None,
) -> dict:
    """Everything the dashboard charts need, computed pixel by pixel at native resolution.

    Returns dict with keys (per scenario key = (ssp_label, period)):
      mats[key]      10x10 transition matrix in km2 (present class -> future class)
      drivers[key]   areas in km2 for driver codes 0..8 (missing when no driver raster)
      delta[key]     dict(mean_future, mean_delta, degraded_km2, improved_km2, change_km2[5 classes])
      present_mean, area_km2
    """
    px_km2 = grid.pixel_area_km2
    p_cont = _sel(
        clean_continuous(read_window(continuous_path(crop, PRESENT), grid, window)),
        mask,
    )
    p_cls = _sel(
        clean_categorical(read_window(categorical_path(crop, PRESENT), grid, window)),
        mask,
    )
    out = dict(
        mats={},
        drivers={},
        delta={},
        present_mean=float(np.nanmean(p_cont)) if p_cont.size else np.nan,
        area_km2=float(np.isfinite(p_cont).sum() * px_km2),
    )
    thr = SIGNIFICANCE_THRESHOLD
    for sc in scenarios:
        key = (sc.ssp_label, sc.period)
        if categorical_path(crop, sc.folder).exists():
            f_cls = _sel(
                clean_categorical(
                    read_window(categorical_path(crop, sc.folder), grid, window)
                ),
                mask,
            )
            out["mats"][key] = crosstab(p_cls, f_cls) * px_km2
        if continuous_path(crop, sc.folder).exists():
            f_cont = _sel(
                clean_continuous(
                    read_window(continuous_path(crop, sc.folder), grid, window)
                ),
                mask,
            )
            d = f_cont - p_cont
            d = d[np.isfinite(d)]
            cls = np.bincount(change_class(d), minlength=6)[1:6]
            out["delta"][key] = dict(
                mean_future=(
                    float(np.nanmean(f_cont)) if np.isfinite(f_cont).any() else np.nan
                ),
                mean_delta=float(d.mean()) if d.size else np.nan,
                degraded_km2=float((d < -thr).sum() * px_km2),
                improved_km2=float((d > thr).sum() * px_km2),
                valid_km2=float(d.size * px_km2),
                change_km2=cls * px_km2,
            )
        drv = find_driver_raster(crop, sc)
        if drv is not None:
            a = _sel(read_window(drv, grid, window), mask)
            a = a[np.isfinite(a) & (a >= 0) & (a <= 8)].astype(np.int64)
            out["drivers"][key] = np.bincount(a, minlength=9)[:9] * px_km2
    return out
