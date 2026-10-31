"""Area-level statistics shared by the dashboard, the CLI and the MCP tools."""

from __future__ import annotations

import numpy as np

from .preprocessing import reference_grid
from .raster_ops import Grid, geometry_inside, region_window
from .region_stats import region_summary
from .utils import CHANGE_CLASSES, DRIVERS, list_crops, list_scenarios


def area_window(grid: Grid, geom):
    """Raster window covering `geom` (whole grid when ``None``) and the inside-mask.

    :return: ``(window, mask)``; ``mask`` is ``None`` for the whole grid
    :raises ValueError: when the geometry does not overlap the raster
    """
    from rasterio.windows import transform as window_transform

    window = region_window(grid, geom.bounds if geom is not None else None)
    if window.width < 1 or window.height < 1:
        raise ValueError("The selected area does not overlap the raster extent")
    if geom is None:
        return window, None
    shape = (int(window.height), int(window.width))
    mask = geometry_inside([geom], window_transform(window, grid.transform), shape)
    return window, mask


def _jsonable_summary(summary: dict, ssp: str | None, period: str | None) -> dict:
    out = {}
    for key in sorted(set(summary["delta"]) | set(summary["mats"])):
        if (ssp and key[0] != ssp) or (period and key[1] != period):
            continue
        d = summary["delta"].get(key, {})
        item = {
            "mean_future": d.get("mean_future"),
            "mean_change": d.get("mean_delta"),
            "loss_km2": d.get("degraded_km2"),
            "gain_km2": d.get("improved_km2"),
        }
        if "change_km2" in d:
            item["change_classes_km2"] = {
                name: float(v)
                for (name, _), v in zip(CHANGE_CLASSES.values(), d["change_km2"])
            }
        if key in summary["mats"]:
            item["transitions_km2"] = np.round(summary["mats"][key], 3).tolist()
        if key in summary["drivers"]:
            item["drivers_km2"] = {
                DRIVERS[c][0]: float(v) for c, v in enumerate(summary["drivers"][key])
            }
        out[f"{key[0]} {key[1]}"] = item
    return out


def area_statistics(
    crop: str,
    judet: str | None = None,
    uat: str | None = None,
    ssp: str | None = None,
    period: str | None = None,
) -> dict:
    """Full-resolution statistics of `crop` for the whole study area, a county or a UAT.

    :param crop: crop code, e.g. ``"GR"``
    :param judet: county name (optional)
    :param uat: UAT name, ``"Name"`` or ``"Name (Type)"`` (optional; use with ``judet``)
    :param ssp: restrict to one scenario label, e.g. ``"SSP2-4.5"``
    :param period: restrict to one period, e.g. ``"2041-2070"``
    :return: JSON-serializable dict with the area, present mean and per-scenario results (km2)
    :raises ValueError: unknown crop, missing boundaries or unit not found
    """
    from .admin import load_admin_layer, select_area

    if crop not in list_crops():
        raise ValueError(f"Unknown crop code: {crop}")
    grid = reference_grid(crop)
    judete = load_admin_layer("judet", grid.crs) if (judet or uat) else None
    uats = load_admin_layer("uat", grid.crs) if uat else None
    geom, name = select_area(judete, uats, judet, uat)
    window, mask = area_window(grid, geom)
    summary = region_summary(crop, list_scenarios(), grid, window, mask)
    return {
        "crop": crop,
        "area": name or "Whole study area",
        "area_km2": summary["area_km2"],
        "present_mean": summary["present_mean"],
        "scenarios": _jsonable_summary(summary, ssp, period),
    }
