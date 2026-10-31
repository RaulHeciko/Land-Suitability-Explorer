"""MCP tools. Each wraps the same library function as the matching ``lsi`` CLI command.

| Tool                       | CLI                                 | Kind        |
|----------------------------|-------------------------------------|-------------|
| catalog_list               | lsi catalog list                    | read-only   |
| area_statistics            | lsi stats area                      | read-only   |
| area_transitions           | (reads an area_statistics result)   | read-only   |
| pipeline_run               | lsi pipeline run                    | write       |
| pipeline_rebuild           | lsi pipeline run --overwrite        | destructive |
| admin_fetch_boundaries     | lsi admin fetch-boundaries          | write       |
"""

from __future__ import annotations

from ._artifacts import load_json, save_json
from ._serialize import guarded, jsonable


@guarded("catalog_list")
def catalog_list() -> dict:
    """Crops and climate scenarios available in the input data."""
    from ..utils import catalog_info

    return {"ok": True, **catalog_info()}


@guarded("area_statistics")
def area_statistics(
    crop: str,
    judet: str | None = None,
    uat: str | None = None,
    ssp: str | None = None,
    period: str | None = None,
) -> dict:
    """Statistics of a crop for the whole area, a county (``judet``) or a UAT.

    The full result (including 10x10 transition matrices and driver areas) is written to a
    server-side JSON file; the response holds a compact summary and ``result_file``.
    """
    from ..analysis import area_statistics as compute

    res = jsonable(compute(crop, judet=judet, uat=uat, ssp=ssp, period=period))
    path = save_json(res, f"area-{crop}")
    compact = {
        key: {k: v[k] for k in ("mean_future", "mean_change", "loss_km2", "gain_km2")}
        for key, v in res["scenarios"].items()
    }
    return {
        "ok": True,
        "crop": res["crop"],
        "area": res["area"],
        "area_km2": res["area_km2"],
        "present_mean": res["present_mean"],
        "scenarios": compact,
        "result_file": str(path),
    }


@guarded("area_transitions")
def area_transitions(result_file: str, scenario: str) -> dict:
    """Transition matrix (km2, present class rows -> future class columns) and change-class
    areas for one ``scenario`` (e.g. ``"SSP2-4.5 2041-2070"``) of an area_statistics result.
    """
    res = load_json(result_file)
    if scenario not in res["scenarios"]:
        raise KeyError(f"scenario not found: {scenario}")
    item = res["scenarios"][scenario]
    return {
        "ok": True,
        "crop": res["crop"],
        "area": res["area"],
        "scenario": scenario,
        "transitions_km2": item.get("transitions_km2"),
        "change_classes_km2": item.get("change_classes_km2"),
        "drivers_km2": item.get("drivers_km2"),
    }


@guarded("pipeline_run")
def pipeline_run(
    crops: list[str] | None = None, phases: list[int] | None = None
) -> dict:
    """Run Phases 1-3 for the given crops, keeping rasters that already exist."""
    from .. import pipeline

    res = pipeline.run(crops, tuple(phases or pipeline.PHASES), overwrite=False)
    return {"ok": True, **res}


@guarded("pipeline_rebuild")
def pipeline_rebuild(
    crops: list[str] | None = None, phases: list[int] | None = None
) -> dict:
    """Like pipeline_run but recomputes and overwrites existing output rasters."""
    from .. import pipeline

    res = pipeline.run(crops, tuple(phases or pipeline.PHASES), overwrite=True)
    return {"ok": True, **res}


@guarded("admin_fetch_boundaries")
def admin_fetch_boundaries(out_dir: str | None = None) -> dict:
    """Download county and UAT boundaries from geo-spatial.org (default: data/admin)."""
    from ..boundaries import fetch

    return {"ok": True, "files": jsonable(fetch(out_dir))}


READ_TOOLS = (catalog_list, area_statistics, area_transitions)
WRITE_TOOLS = (pipeline_run, admin_fetch_boundaries)
DESTRUCTIVE_TOOLS = (pipeline_rebuild,)
