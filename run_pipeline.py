"""Run Phases 1-3 sequentially for every crop (or a subset).

Examples:
    python run_pipeline.py                         # all crops, all phases
    python run_pipeline.py --crops GR PB --phases 1 2
    python run_pipeline.py --overwrite --no-figures
"""

from __future__ import annotations

import argparse
import time

from src import phase1_deltas, phase2_transitions, phase3_attribution
from src.utils import LSI_DIR, RESULTS_DIR, get_logger, list_crops, list_scenarios

log = get_logger()


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--crops",
        nargs="*",
        help="crop codes (default: all found in the present folder)",
    )
    ap.add_argument(
        "--phases", nargs="*", type=int, default=[1, 2, 3], choices=[1, 2, 3]
    )
    ap.add_argument(
        "--overwrite", action="store_true", help="recompute rasters that already exist"
    )
    ap.add_argument(
        "--no-figures", action="store_true", help="skip Sankey/driver chart export"
    )
    a = ap.parse_args(argv)

    crops = a.crops or list_crops()
    scenarios = list_scenarios()
    if not crops or not scenarios:
        raise SystemExit(f"No crops/scenarios found under {LSI_DIR}")
    log.info("Input: %s | Output: %s", LSI_DIR, RESULTS_DIR)
    log.info("Crops (%d): %s", len(crops), " ".join(crops))
    log.info("Scenarios: %s", ", ".join(s.label for s in scenarios))

    delta_rows, driver_frames = [], []
    for k, crop in enumerate(crops, 1):
        t0 = time.time()
        log.info("=== [%d/%d] %s ===", k, len(crops), crop)
        if 1 in a.phases:
            delta_rows += phase1_deltas.run_crop(crop, scenarios, a.overwrite)
            phase1_deltas.write_summary(delta_rows)
        if 2 in a.phases:
            phase2_transitions.run_crop(crop, scenarios, figures=not a.no_figures)
        if 3 in a.phases:
            driver_frames.append(
                phase3_attribution.run_crop(
                    crop, scenarios, a.overwrite, not a.no_figures
                )
            )
            phase3_attribution.write_global_summary(driver_frames[-1:])
        log.info("[%s] finished in %.0f s", crop, time.time() - t0)


if __name__ == "__main__":
    main()
