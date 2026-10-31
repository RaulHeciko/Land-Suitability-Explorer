"""Phase 3 - dominant eco-climatic driver maps (9 classes) and area summaries.

dT = T_future - T_present, dP = P_future - P_present, dS from Phase 1.
Pixels with -5 <= dS <= 5 -> code 0; otherwise the code is set by the sign of dS, dT and dP
(see utils.DRIVERS). A climate delta of exactly 0 is treated as "cold"/"dry".

Climate inputs: data/climate/<period folder>/tas.tif and pr.tif (period folder = "prezent",
"ssp245_2041-2070", ...). When they are missing but a driver raster from the earlier workflow exists
(results/<CROP>/Dominant_Driver_*.tif), the summaries and charts are computed from that raster.

Outputs:
  results/drivers/<CROP>/Dominant_Driver_<SSP>_<period>_<CROP>.tif   (uint8, colour table, 255 = NoData)
  results/drivers/<CROP>/Driver_Summary_<CROP>.csv
  results/drivers/driver_summary_all.csv
  results/figures/<CROP>/Dominant_Drivers_Grid_<CROP>.html/.png
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd
from rasterio.enums import Resampling

from . import charts
from .preprocessing import load_continuous, reference_grid, study_mask
from .raster_ops import Grid, read_aligned, write_geotiff
from .utils import (
    crop_label,
    DRIVER_NODATA,
    DRIVERS,
    DRIVERS_DIR,
    FIGURES_DIR,
    PRESENT,
    SIGNIFICANCE_THRESHOLD,
    Scenario,
    climate_path,
    continuous_path,
    delta_path,
    driver_path,
    get_logger,
    hex_to_rgb,
    legacy_driver_path,
    list_crops,
    list_scenarios,
)

log = get_logger()

DRIVER_COLORMAP = {code: hex_to_rgb(c) + (255,) for code, (_, _, c) in DRIVERS.items()}
DRIVER_COLORMAP[DRIVER_NODATA] = (0, 0, 0, 0)


def classify_drivers(
    ds: np.ndarray,
    dt: np.ndarray,
    dp: np.ndarray,
    threshold: float = SIGNIFICANCE_THRESHOLD,
) -> np.ndarray:
    out = np.full(ds.shape, DRIVER_NODATA, dtype=np.uint8)
    with np.errstate(invalid="ignore"):
        valid_s = np.isfinite(ds)
        stable = valid_s & (ds >= -threshold) & (ds <= threshold)
        clim_ok = np.isfinite(dt) & np.isfinite(dp)
        drop = valid_s & clim_ok & (ds < -threshold)
        gain = valid_s & clim_ok & (ds > threshold)
        hot, wet = dt > 0, dp > 0
    out[stable] = 0
    out[drop & hot & ~wet] = 1
    out[drop & ~hot & ~wet] = 2
    out[drop & hot & wet] = 3
    out[drop & ~hot & wet] = 4
    out[gain & hot & wet] = 5
    out[gain & hot & ~wet] = 6
    out[gain & ~hot & wet] = 7
    out[gain & ~hot & ~wet] = 8
    return out


def climate_available(sc: Scenario) -> bool:
    return all(climate_path(v, p) for v in ("T", "P") for p in (PRESENT, sc.folder))


def climate_delta(var: str, sc: Scenario, grid: Grid) -> np.ndarray:
    pres = read_aligned(climate_path(var, PRESENT), grid, Resampling.bilinear)
    fut = read_aligned(climate_path(var, sc.folder), grid, Resampling.bilinear)
    return fut - pres


def suitability_delta(crop: str, sc: Scenario, grid: Grid) -> np.ndarray:
    p = delta_path(crop, sc)
    if p.exists():
        return read_aligned(p, grid)
    present = load_continuous(continuous_path(crop, PRESENT), grid)
    mask = study_mask(grid, present)
    return load_continuous(continuous_path(crop, sc.folder), grid, mask) - present


def driver_counts(codes: np.ndarray) -> np.ndarray:
    return np.bincount(codes[codes != DRIVER_NODATA].ravel(), minlength=9)[:9]


def run_crop(
    crop: str, scenarios: list[Scenario], overwrite: bool = False, figures: bool = True
) -> pd.DataFrame:
    grid = reference_grid(crop)
    frames = []
    for sc in scenarios:
        out = driver_path(crop, sc)
        if out.exists() and not overwrite:
            codes, source = read_aligned(out, grid), "pipeline"
        elif climate_available(sc):
            codes = classify_drivers(
                suitability_delta(crop, sc, grid),
                climate_delta("T", sc, grid),
                climate_delta("P", sc, grid),
            )
            write_geotiff(
                out,
                codes,
                grid,
                nodata=DRIVER_NODATA,
                colormap=DRIVER_COLORMAP,
                descriptions=f"Dominant driver {sc.label}",
            )
            log.info("[%s] wrote %s", crop, out.name)
            source = "pipeline"
        elif legacy_driver_path(crop, sc).exists():
            codes, source = read_aligned(legacy_driver_path(crop, sc), grid), "legacy"
            log.info(
                "[%s] %s: no climate rasters, summarising legacy %s",
                crop,
                sc.tag,
                legacy_driver_path(crop, sc).name,
            )
        else:
            log.warning(
                "[%s] %s: no climate rasters in data/climate and no existing driver raster - skipped",
                crop,
                sc.tag,
            )
            continue
        if codes.dtype.kind == "f":
            codes = np.where(np.isfinite(codes), codes, DRIVER_NODATA).astype(np.uint8)
        df = charts.driver_summary_table(driver_counts(codes), grid.pixel_area_km2)
        del codes
        df.insert(0, "crop", crop)
        df.insert(1, "scenario", sc.label)
        df.insert(2, "ssp", sc.ssp_label)
        df.insert(3, "horizon", sc.horizon)
        df.insert(4, "period", sc.period)
        df["source"] = source
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    summary = pd.concat(frames, ignore_index=True)
    (DRIVERS_DIR / crop).mkdir(parents=True, exist_ok=True)
    summary.to_csv(
        DRIVERS_DIR / crop / f"Driver_Summary_{crop}.csv",
        index=False,
        float_format="%.3f",
    )
    if figures:
        tables = {(f.ssp.iloc[0], f.period.iloc[0]): f for f in frames}
        ssps, periods = sorted({k[0] for k in tables}), sorted({k[1] for k in tables})
        charts.save_figure(
            charts.drivers_grid_figure(tables, ssps, periods, crop_label(crop)),
            FIGURES_DIR / crop / f"Dominant_Drivers_Grid_{crop}.html",
            FIGURES_DIR / crop / f"Dominant_Drivers_Grid_{crop}.png",
        )
    return summary


def write_global_summary(frames: list[pd.DataFrame]) -> None:
    frames = [f for f in frames if not f.empty]
    if not frames:
        return
    path = DRIVERS_DIR / "driver_summary_all.csv"
    new = pd.concat(frames, ignore_index=True)
    if path.exists():
        old = pd.read_csv(path)
        new = pd.concat(
            [old[~old.crop.isin(new.crop.unique())], new], ignore_index=True
        )
    new.to_csv(path, index=False, float_format="%.3f")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--crops", nargs="*")
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--no-figures", action="store_true")
    a = ap.parse_args(argv)
    write_global_summary(
        [
            run_crop(c, list_scenarios(), a.overwrite, not a.no_figures)
            for c in a.crops or list_crops()
        ]
    )


if __name__ == "__main__":
    main()
