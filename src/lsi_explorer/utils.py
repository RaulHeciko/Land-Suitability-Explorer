"""Shared paths, constants and discovery helpers for the LSI pipeline."""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path

# Base folder for data/ and results/ (default: the current working directory).
ROOT = Path(os.environ.get("LSI_HOME") or Path.cwd())


def _first_existing(*candidates: Path) -> Path:
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]


# Input LSI rasters: data/LSI (spec layout) or ./LSI (current layout). Override with LSI_DATA_DIR.
LSI_DIR = Path(
    os.environ.get("LSI_DATA_DIR")
    or _first_existing(ROOT / "data" / "LSI", ROOT / "LSI")
)
CLIMATE_DIR = Path(os.environ.get("LSI_CLIMATE_DIR") or ROOT / "data" / "climate")
ADMIN_DIR = Path(os.environ.get("LSI_ADMIN_DIR") or ROOT / "data" / "admin")
MASK_PATH = Path(
    os.environ.get("LSI_MASK") or ROOT / "data" / "mask" / "study_area.tif"
)
CROP_NAMES_CSV = ROOT / "data" / "crop_names.csv"
RESULTS_DIR = Path(os.environ.get("LSI_RESULTS_DIR") or ROOT / "results")

DELTAS_DIR = RESULTS_DIR / "deltas"
TRANSITIONS_DIR = RESULTS_DIR / "transitions"
DRIVERS_DIR = RESULTS_DIR / "drivers"
FIGURES_DIR = RESULTS_DIR / "figures"

PRESENT = "prezent"
SCENARIO_RE = re.compile(r"^(ssp\d{3})_(\d{4})-(\d{4})$", re.IGNORECASE)

# The source rasters carry a LOCAL_CS "Pulkovo 1942(58) / Stereo70" definition without an EPSG code.
DEFAULT_CRS = "EPSG:3844"

CLASSES = list(range(1, 11))
# The 10-class rasters are inverted relative to the score: class 1 = most suitable (90-100),
# class 10 = least suitable (0-10). A transition to a lower class number is an improvement.
CLASS_RANGES = {c: f"{100 - 10 * c}-{110 - 10 * c}" for c in CLASSES}
# Suitability class palette, C1 (dark green) -> C10 (red).
CLASS_COLORS = [
    "#267A26",
    "#3D9B35",
    "#6CB22D",
    "#A3CB2C",
    "#D9E528",
    "#F5EE2E",
    "#FCCB2F",
    "#FBA62C",
    "#F8812E",
    "#F44D27",
]

# Change in suitability (future - present, score points), 5 classes: code -> (label, colour).
CHANGE_CLASSES = {
    1: ("< -10", "#F1471D"),
    2: ("-10 to -5", "#F7A21B"),
    3: ("-5 to +5", "#FFFFBE"),
    4: ("+5 to +10", "#8CC63E"),
    5: ("> +10", "#2F8F2F"),
}


def change_class(delta):
    """dS -> change class 1..5 (0 where NaN). Bounds: <-10 | -10...<-5 | -5...5 | >5...10 | >10."""
    import numpy as np

    d = np.asarray(delta)
    with np.errstate(invalid="ignore"):
        out = np.select([d < -10, d < -5, d <= 5, d <= 10, d > 10], [1, 2, 3, 4, 5], 0)
    return out.astype(np.uint8)


# Driver lookup table (code -> name, interpretation, hex colour).
DRIVERS = {
    0: ("No Significant Change", "Stable conditions / minor change", "#E0E0E0"),
    1: (
        "Warming and drying (Suitability drop)",
        "Compound stress: heatwave + drought",
        "#D7191C",
    ),
    2: (
        "Cooling and drying (Suitability drop)",
        "Cooling associated with precipitation deficit",
        "#8C510A",
    ),
    3: (
        "Warming and wetting (Suitability drop)",
        "Warming with water excess (pathogen/anoxia risk)",
        "#FDAE61",
    ),
    4: (
        "Cooling and wetting (Suitability drop)",
        "Cooling with moisture excess / waterlogging",
        "#2B83BA",
    ),
    5: (
        "Warming and wetting (Suitability gain)",
        "Optimal climate: longer season + sufficient water",
        "#1A9641",
    ),
    6: (
        "Warming and drying (Suitability gain)",
        "Thermal benefit (xerotolerant / former cold limit)",
        "#A6D96A",
    ),
    7: (
        "Cooling and wetting (Suitability gain)",
        "Thermal stress mitigation via rainfall input",
        "#41B6C4",
    ),
    8: (
        "Cooling and drying (Suitability gain)",
        "Adaptation / optimization in cooler/drier regime",
        "#F6E8C3",
    ),
}
DRIVER_NODATA = 255
SIGNIFICANCE_THRESHOLD = 5.0


def hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))


@dataclass(frozen=True)
class Scenario:
    folder: str  # e.g. "ssp245_2041-2070"
    ssp: str  # e.g. "ssp245"
    start: int
    end: int

    @property
    def ssp_label(self) -> str:
        n = self.ssp[3:]
        return f"SSP{n[0]}-{n[1]}.{n[2]}"

    @property
    def horizon(self) -> int:
        """Nominal horizon year (2041-2070 -> 2050, 2071-2100 -> 2080)."""
        return {2041: 2050, 2071: 2080}.get(self.start, (self.start + self.end) // 2)

    @property
    def period(self) -> str:
        return f"{self.start}-{self.end}"

    @property
    def tag(self) -> str:
        return f"{self.ssp.upper()}_{self.period}"

    @property
    def label(self) -> str:
        return f"{self.ssp_label} \u00b7 {self.horizon} ({self.period})"


def parse_scenario(folder: str) -> Scenario | None:
    m = SCENARIO_RE.match(folder)
    if not m:
        return None
    return Scenario(folder, m.group(1).lower(), int(m.group(2)), int(m.group(3)))


def list_scenarios() -> list[Scenario]:
    if not LSI_DIR.exists():
        return []
    out = [parse_scenario(p.name) for p in LSI_DIR.iterdir() if p.is_dir()]
    return sorted([s for s in out if s], key=lambda s: (s.ssp, s.start))


def list_crops() -> list[str]:
    present = LSI_DIR / PRESENT
    if not present.exists():
        return []
    return sorted(
        p.name
        for p in present.iterdir()
        if p.is_dir() and continuous_path(p.name, PRESENT).exists()
    )


CROP_NAMES = {
    "PS": "Pasture",
    "FN": "Meadow",
    "AR": "Arable land",
    "MR": "Apple",
    "PR": "Pear",
    "PN": "Plum",
    "CV": "Cherry",
    "CS": "Apricot",
    "PC": "Peach",
    "VV": "Grapery for wine",
    "GR": "Wheat",
    "OR": "Barley",
    "PB": "Corn",
    "FS": "Sunflower",
    "VM": "Grapery for food",
    "CT": "Potato",
    "SF": "Sugar beet",
    "SO": "Soy",
    "MF": "Pea-bean",
    "IU": "Linseed for oil",
    "CN": "Hemp",
    "LU": "Alfalfa-lucerne",
    "TR": "Clover",
    "LG": "Vegetables",
    "IF": "Linseed for tow",
}


def crop_names() -> dict[str, str]:
    """Crop code -> display name in the active language (locale ``crops.<code>``, else
    ``CROP_NAMES``); data/crop_names.csv (columns: code,name) overrides both."""
    from .i18n import t

    names = {c: t(f"crops.{c}") for c in CROP_NAMES}
    names = {c: (n if n != f"crops.{c}" else CROP_NAMES[c]) for c, n in names.items()}
    if CROP_NAMES_CSV.exists():
        import pandas as pd

        df = pd.read_csv(CROP_NAMES_CSV)
        names.update(zip(df.iloc[:, 0].astype(str), df.iloc[:, 1].astype(str)))
    return names


def crop_label(code: str) -> str:
    """Human-readable crop label, e.g. 'Hemp (CN)'."""
    name = crop_names().get(code)
    return f"{name} ({code})" if name else code


def continuous_path(crop: str, period_folder: str) -> Path:
    return LSI_DIR / period_folder / crop / f"_{crop}_land_suitability.tif"


def categorical_path(crop: str, period_folder: str) -> Path:
    return (
        LSI_DIR / period_folder / crop / f"_{crop}_land_suitability_10_categories.tif"
    )


def delta_path(crop: str, sc: Scenario) -> Path:
    return DELTAS_DIR / crop / f"Delta_Suitability_{sc.tag}_{crop}.tif"


def driver_path(crop: str, sc: Scenario) -> Path:
    return DRIVERS_DIR / crop / f"Dominant_Driver_{sc.tag}_{crop}.tif"


def legacy_driver_path(crop: str, sc: Scenario) -> Path:
    """Driver rasters produced by an earlier workflow (results/<CROP>/Dominant_Driver_*.tif)."""
    return RESULTS_DIR / crop / f"Dominant_Driver_{sc.tag}_{crop}.tif"


def find_driver_raster(crop: str, sc: Scenario) -> Path | None:
    for p in (driver_path(crop, sc), legacy_driver_path(crop, sc)):
        if p.exists():
            return p
    return None


_CLIMATE_NAMES = {
    "T": ("tas", "tmean", "tavg", "temp", "temperature", "t"),
    "P": ("pr", "prec", "precip", "precipitation", "ppt", "p"),
}


def climate_path(var: str, period_folder: str) -> Path | None:
    """Locate a climate raster: data/climate/<period_folder>/<tas|pr|...>.tif (case-insensitive stem)."""
    folder = CLIMATE_DIR / period_folder
    if not folder.exists():
        return None
    names = _CLIMATE_NAMES[var]
    for p in sorted(folder.glob("*.tif")):
        if p.stem.lower() in names:
            return p
    return None


def admin_layer_path(level: str) -> Path | None:
    """level is 'judet' or 'uat'; any vector file whose name starts with that word (or county/municip)."""
    if not ADMIN_DIR.exists():
        return None
    prefixes = {
        "judet": ("judet", "judete", "county", "counties"),
        "uat": ("uat", "municip", "comune"),
    }[level]
    for p in sorted(ADMIN_DIR.iterdir()):
        if p.suffix.lower() in (
            ".geojson",
            ".json",
            ".shp",
            ".gpkg",
        ) and p.stem.lower().startswith(prefixes):
            return p
    return None


def catalog_info() -> dict:
    """Crops and climate scenarios available in the input folder (JSON-serializable)."""
    names = crop_names()
    return {
        "data_dir": str(LSI_DIR),
        "crops": [{"code": c, "name": names.get(c, c)} for c in list_crops()],
        "scenarios": [
            {
                "ssp": s.ssp_label,
                "period": s.period,
                "horizon": s.horizon,
                "folder": s.folder,
            }
            for s in list_scenarios()
        ],
    }


def get_logger(name: str = "lsi") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        h = logging.StreamHandler()
        h.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S"
            )
        )
        logger.addHandler(h)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger
