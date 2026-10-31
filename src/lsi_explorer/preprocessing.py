"""Module 0 - cleaning, alignment and masking of LSI rasters.

- Continuous LS (0-100): values < 0 or > 100 become NaN.
- Categorical LS (10 classes): values < 1 or > 10 become NoData (0 in the returned uint8 array).
- Every raster is aligned to the reference grid (present-day continuous raster of the crop) and
  multiplied by the study-area mask (data/mask/study_area.tif if present; otherwise the valid-pixel
  footprint of the reference raster is used).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from rasterio.enums import Resampling

from .raster_ops import Grid, grid_of, read_aligned
from .utils import MASK_PATH, PRESENT, categorical_path, continuous_path


def clean_continuous(arr: np.ndarray) -> np.ndarray:
    arr = arr.astype("float32", copy=False)
    with np.errstate(invalid="ignore"):
        arr[(arr < 0) | (arr > 100)] = np.nan
    return arr


def clean_categorical(arr: np.ndarray) -> np.ndarray:
    """Float class raster -> uint8 with 0 = NoData."""
    with np.errstate(invalid="ignore"):
        r = np.rint(arr)
        valid = np.isfinite(r) & (r >= 1) & (r <= 10)
    out = np.zeros(arr.shape, dtype=np.uint8)
    out[valid] = r[valid].astype(np.uint8)
    return out


def reference_grid(crop: str) -> Grid:
    return grid_of(continuous_path(crop, PRESENT))


_mask_cache: dict[tuple, np.ndarray] = {}


def _external_mask(grid: Grid) -> np.ndarray | None:
    if not MASK_PATH.exists():
        return None
    key = (grid.shape, tuple(grid.transform)[:6])
    if key not in _mask_cache:
        m = read_aligned(MASK_PATH, grid, Resampling.nearest)
        _mask_cache.clear()
        _mask_cache[key] = np.isfinite(m) & (m != 0)
    return _mask_cache[key]


def study_mask(grid: Grid, reference: np.ndarray | None = None) -> np.ndarray:
    """True for pixels inside the study area."""
    ext = _external_mask(grid)
    if ext is not None:
        return ext
    if reference is None:
        return np.ones(grid.shape, dtype=bool)
    return np.isfinite(reference) if reference.dtype.kind == "f" else reference > 0


def apply_mask(arr: np.ndarray, mask: np.ndarray) -> np.ndarray:
    if arr.dtype.kind == "f":
        arr[~mask] = np.nan
    else:
        arr[~mask] = 0
    return arr


def load_continuous(
    path: Path, grid: Grid, mask: np.ndarray | None = None
) -> np.ndarray:
    arr = clean_continuous(read_aligned(path, grid, Resampling.bilinear))
    return apply_mask(arr, mask) if mask is not None else arr


def load_categorical(
    path: Path, grid: Grid, mask: np.ndarray | None = None
) -> np.ndarray:
    arr = clean_categorical(read_aligned(path, grid, Resampling.nearest))
    return apply_mask(arr, mask) if mask is not None else arr


def load_crop_period(
    crop: str,
    period_folder: str,
    grid: Grid,
    mask: np.ndarray | None,
    kind: str = "continuous",
) -> np.ndarray:
    if kind == "continuous":
        return load_continuous(continuous_path(crop, period_folder), grid, mask)
    return load_categorical(categorical_path(crop, period_folder), grid, mask)
