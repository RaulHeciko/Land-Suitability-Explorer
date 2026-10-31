"""Low-level raster I/O, alignment, cross-tabulation and display helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.enums import Resampling
from rasterio.features import geometry_mask
from rasterio.transform import Affine, array_bounds
from rasterio.warp import calculate_default_transform, reproject
from rasterio.windows import Window, from_bounds

from .utils import DEFAULT_CRS


@dataclass(frozen=True)
class Grid:
    crs: CRS
    transform: Affine
    width: int
    height: int

    @property
    def shape(self) -> tuple[int, int]:
        return self.height, self.width

    @property
    def pixel_area_km2(self) -> float:
        return abs(self.transform.a * self.transform.e) / 1e6

    def same_as(self, other: "Grid") -> bool:
        return (
            self.shape == other.shape
            and self.transform.almost_equals(other.transform)
            and self.crs == other.crs
        )


def dataset_crs(src) -> CRS:
    """Return the dataset CRS, substituting EPSG:3844 for the unregistered LOCAL_CS Stereo70 definition."""
    crs = src.crs
    if crs is None:
        return CRS.from_string(DEFAULT_CRS)
    try:
        if crs.to_epsg() is None and "stereo" in crs.to_wkt().lower():
            return CRS.from_string(DEFAULT_CRS)
    except Exception:
        return CRS.from_string(DEFAULT_CRS)
    return crs


def grid_of(path: Path) -> Grid:
    with rasterio.open(path) as src:
        return Grid(dataset_crs(src), src.transform, src.width, src.height)


def read_aligned(
    path: Path, grid: Grid, resampling: Resampling = Resampling.nearest
) -> np.ndarray:
    """Read band 1 as float32 (nodata -> NaN), reprojected onto `grid` when the source grid differs."""
    with rasterio.open(path) as src:
        src_grid = Grid(dataset_crs(src), src.transform, src.width, src.height)
        nodata = src.nodata
        if src_grid.same_as(grid):
            arr = src.read(1, out_dtype="float32")
        else:
            arr = np.full(grid.shape, np.nan, dtype="float32")
            reproject(
                source=rasterio.band(src, 1),
                destination=arr,
                src_transform=src.transform,
                src_crs=src_grid.crs,
                src_nodata=nodata,
                dst_transform=grid.transform,
                dst_crs=grid.crs,
                dst_nodata=np.nan,
                resampling=resampling,
            )
            return arr
    if nodata is not None and not np.isnan(nodata):
        arr[arr == nodata] = np.nan
    return arr


def write_geotiff(
    path: Path,
    arr: np.ndarray,
    grid: Grid,
    nodata,
    colormap: dict | None = None,
    descriptions: str | None = None,
    overviews: bool = True,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    dtype = arr.dtype.name
    profile = dict(
        driver="GTiff",
        width=grid.width,
        height=grid.height,
        count=1,
        dtype=dtype,
        crs=grid.crs,
        transform=grid.transform,
        nodata=nodata,
        tiled=True,
        blockxsize=512,
        blockysize=512,
        compress="deflate",
        zlevel=6,
        predictor=3 if dtype.startswith("float") else 2,
        BIGTIFF="IF_SAFER",
    )
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(arr, 1)
        if colormap:
            dst.write_colormap(1, colormap)
        if descriptions:
            dst.set_band_description(1, descriptions)
        if overviews:
            factors = [
                f for f in (2, 4, 8, 16, 32) if min(grid.width, grid.height) // f >= 8
            ]
            if factors:
                dst.build_overviews(
                    factors, Resampling.nearest if colormap else Resampling.average
                )
            dst.update_tags(
                ns="rio_overview", resampling="nearest" if colormap else "average"
            )
    return path


def crosstab(a: np.ndarray, b: np.ndarray, n_classes: int = 10) -> np.ndarray:
    """Pixel-count matrix M[i, j] = #pixels with a == i+1 and b == j+1 (classes 1..n, 0 = nodata)."""
    valid = (a > 0) & (b > 0)
    idx = (a[valid].astype(np.int64) - 1) * n_classes + (b[valid].astype(np.int64) - 1)
    return np.bincount(idx, minlength=n_classes * n_classes).reshape(
        n_classes, n_classes
    )


def read_window(path: Path, grid: Grid, window: Window) -> np.ndarray:
    """Native-resolution read of `window` (on `grid`) as float32 with NoData -> NaN."""
    with rasterio.open(path) as src:
        same = Grid(dataset_crs(src), src.transform, src.width, src.height).same_as(
            grid
        )
        if same:
            arr = src.read(1, window=window, out_dtype="float32")
            nodata = src.nodata
    if not same:
        full = read_aligned(path, grid)
        return full[window.toslices()].copy()
    if nodata is not None and not np.isnan(nodata):
        arr[arr == nodata] = np.nan
    return arr


# ---------------------------------------------------------------- region reads (dashboard)


def region_window(
    grid: Grid, bounds: tuple[float, float, float, float] | None
) -> Window:
    full = Window(0, 0, grid.width, grid.height)
    if bounds is None:
        return full
    w = from_bounds(*bounds, transform=grid.transform)
    c0, r0 = int(np.floor(w.col_off)), int(np.floor(w.row_off))
    c1, r1 = int(np.ceil(w.col_off + w.width)), int(np.ceil(w.row_off + w.height))
    c0, r0, c1, r1 = max(c0, 0), max(r0, 0), min(c1, grid.width), min(r1, grid.height)
    return Window(c0, r0, max(c1 - c0, 0), max(r1 - r0, 0))


def read_region(
    path: Path, window: Window, out_shape: tuple[int, int], categorical: bool
) -> np.ndarray:
    """Read a window of band 1 as float32 (nodata -> NaN), resampled to out_shape."""
    with rasterio.open(path) as src:
        resampling = Resampling.nearest if categorical else Resampling.average
        arr = src.read(
            1,
            window=window,
            out_shape=out_shape,
            resampling=resampling,
            out_dtype="float32",
            boundless=False,
        )
        nodata = src.nodata
    if nodata is not None and not np.isnan(nodata):
        arr[arr == nodata] = np.nan
    return arr


def window_transform(grid: Grid, window: Window, out_shape: tuple[int, int]) -> Affine:
    t = rasterio.windows.transform(window, grid.transform)
    return t * Affine.scale(window.width / out_shape[1], window.height / out_shape[0])


def geometry_inside(geoms, transform: Affine, shape: tuple[int, int]) -> np.ndarray:
    """Boolean mask, True inside the given geometries (raster CRS)."""
    return geometry_mask(
        geoms, out_shape=shape, transform=transform, invert=True, all_touched=False
    )


def to_web_mercator(rgba: np.ndarray, transform: Affine, crs: CRS):
    """Warp an RGBA image to EPSG:3857; returns (image, [[south, west], [north, east]]) for Leaflet."""
    h, w = rgba.shape[:2]
    left, bottom, right, top = array_bounds(h, w, transform)
    dst_crs = CRS.from_epsg(3857)
    dst_t, dw, dh = calculate_default_transform(
        crs, dst_crs, w, h, left, bottom, right, top
    )
    out = np.zeros((4, dh, dw), dtype=np.uint8)
    for b in range(4):
        reproject(
            rgba[..., b],
            out[b],
            src_transform=transform,
            src_crs=crs,
            dst_transform=dst_t,
            dst_crs=dst_crs,
            resampling=Resampling.nearest,
            src_nodata=None,
            dst_nodata=0,
        )
    from pyproj import Transformer

    l, btm, r, t = array_bounds(dh, dw, dst_t)
    tr = Transformer.from_crs(dst_crs, "EPSG:4326", always_xy=True)
    west, south = tr.transform(l, btm)
    east, north = tr.transform(r, t)
    return np.moveaxis(out, 0, -1), [[south, west], [north, east]]


def colorize(arr: np.ndarray, cmap, vmin: float, vmax: float) -> np.ndarray:
    """Continuous array -> RGBA uint8 using a matplotlib colormap; NaN is transparent."""
    norm = np.clip((arr - vmin) / (vmax - vmin), 0, 1)
    rgba = (cmap(np.nan_to_num(norm)) * 255).astype(np.uint8)
    rgba[np.isnan(arr), 3] = 0
    return rgba


def colorize_classes(
    arr: np.ndarray, colors: dict[int, tuple[int, int, int]]
) -> np.ndarray:
    rgba = np.zeros(arr.shape + (4,), dtype=np.uint8)
    for code, rgb in colors.items():
        m = arr == code
        rgba[m, :3] = rgb
        rgba[m, 3] = 255
    return rgba
