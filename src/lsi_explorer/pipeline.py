"""Batch processing of Phases 1-3 for a set of crops (shared by the CLI and the MCP tools)."""

from __future__ import annotations

import time

from .utils import LSI_DIR, RESULTS_DIR, get_logger, list_crops, list_scenarios

log = get_logger()
PHASES = (1, 2, 3)


def run(
    crops: list[str] | None = None,
    phases: tuple[int, ...] = PHASES,
    overwrite: bool = False,
    figures: bool = True,
) -> dict:
    """Run the requested phases for `crops` (default: every crop found).

    :param crops: crop codes, e.g. ``["GR", "PB"]``; ``None`` processes all crops
    :param phases: any of 1 (deltas), 2 (transitions), 3 (drivers)
    :param overwrite: recompute rasters that already exist
    :param figures: export the HTML/PNG summary figures
    :return: ``{"crops": [...], "phases": [...], "seconds": {crop: s}, "results_dir": str}``
    :raises ValueError: when no crops/scenarios are found or a crop/phase is unknown
    """
    from . import phase1_deltas, phase2_transitions, phase3_attribution

    available, scenarios = list_crops(), list_scenarios()
    crops = list(crops) if crops else available
    if not crops or not scenarios:
        raise ValueError(f"No crops/scenarios found under {LSI_DIR}")
    unknown = sorted(set(crops) - set(available))
    if unknown:
        raise ValueError(f"Unknown crop code(s): {', '.join(unknown)}")
    bad = sorted(set(phases) - set(PHASES))
    if bad:
        raise ValueError(f"Unknown phase(s): {bad}")

    log.info("Input: %s | Output: %s", LSI_DIR, RESULTS_DIR)
    seconds, delta_rows = {}, []
    for k, crop in enumerate(crops, 1):
        t0 = time.time()
        log.info("=== [%d/%d] %s ===", k, len(crops), crop)
        if 1 in phases:
            delta_rows += phase1_deltas.run_crop(crop, scenarios, overwrite)
            phase1_deltas.write_summary(delta_rows)
        if 2 in phases:
            phase2_transitions.run_crop(crop, scenarios, figures=figures)
        if 3 in phases:
            frame = phase3_attribution.run_crop(crop, scenarios, overwrite, figures)
            phase3_attribution.write_global_summary([frame])
        seconds[crop] = round(time.time() - t0, 1)
        log.info("[%s] finished in %.0f s", crop, seconds[crop])
    return dict(
        crops=crops,
        phases=sorted(phases),
        seconds=seconds,
        results_dir=str(RESULTS_DIR),
    )
