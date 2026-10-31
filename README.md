# EOCube - Land Suitability Index (LSI) pipeline and dashboard

Batch processing (Phases 1-3) of present and future land-suitability rasters, plus a Streamlit
dashboard to explore them by crop, climate scenario, period and administrative unit.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install -r requirements-dev.txt  # tests and formatting
```

If PostGIS/ArcGIS is installed, a system-wide `PROJ_LIB` may point to an incompatible `proj.db`;
`src/__init__.py` drops such variables automatically for this project.

## Input layout

```
LSI/  (or data/LSI/, or set LSI_DATA_DIR)
  prezent/<CROP>/_<CROP>_land_suitability.tif                 continuous score 0-100
  prezent/<CROP>/_<CROP>_land_suitability_10_categories.tif   classes 1-10
  ssp126_2041-2070/<CROP>/...   ssp126_2071-2100/...   ssp245_2041-2070/...   ssp245_2071-2100/...
data/climate/<period>/tas.tif, pr.tif     optional - needed to compute new driver maps (Phase 3)
data/mask/study_area.tif                  optional - otherwise the valid-pixel footprint is used
data/admin/judete.gpkg, uat.gpkg          county / UAT boundaries for the area filter (see below)
data/crop_names.csv                       optional - columns: code,name; overrides the built-in names
```

County and UAT boundaries come from the public geo-spatial.org WFS (the same layers used by
`eocube.services.geospatialorg`). Download them once (about 15 MB):

```bash
python scripts/fetch_admin_boundaries.py
```

Any scenario folder named `sspXXX_YYYY-YYYY` is picked up automatically. The rasters use Stereo70
(assigned as EPSG:3844); a 100 m pixel is 0.01 km2. All areas (CSVs, charts, dashboard) are in km2.

Crop codes are shown with their names (e.g. CN = Hemp, GR = Wheat, PB = Corn); the full list is
`CROP_NAMES` in `src/utils.py`.

### Classes

- Suitability classes C1-C10: C1 is the most suitable (score 90-100), C10 the least (0-10).
  Colours run from dark green (C1) to red (C10).
- Change in suitability (future - present, score points), 5 classes:
  `< -10`, `-10 to -5`, `-5 to +5` (no significant change), `+5 to +10`, `> +10`.

## Run the pipeline

```bash
python run_pipeline.py                            # all crops, phases 1-3 (~100 s per crop)
python run_pipeline.py --crops GR PB --phases 1 2  # subset
python run_pipeline.py --overwrite --no-figures
```

Each phase also runs on its own: `python -m src.phase1_deltas`, `python -m src.phase2_transitions`,
`python -m src.phase3_attribution` (all accept `--crops`).

| Phase | Module | Outputs |
|---|---|---|
| 0 | `src/preprocessing.py` | cleaning (score outside 0-100 and class outside 1-10 become NoData), alignment to the reference grid, study-area masking |
| 1 | `src/phase1_deltas.py` | `results/deltas/<CROP>/Delta_Suitability_<SSP>_<period>_<CROP>.tif`, `results/deltas/delta_summary.csv` |
| 2 | `src/phase2_transitions.py` | `results/transitions/<CROP>/Matrix_*.csv`, `SideBySide_*.csv`, `Transitions_long_*.csv`, `Class_Dynamics_*.csv`; `results/figures/<CROP>/Transition_Matrix_Combined_AllSSPs_<CROP>` and `Diverging_Bars_AllScenarios_<CROP>` (.html/.png) |
| 3 | `src/phase3_attribution.py` | `results/drivers/<CROP>/Dominant_Driver_*.tif` (uint8 + colour table), `Driver_Summary_<CROP>.csv`, `results/drivers/driver_summary_all.csv`; `results/figures/<CROP>/Dominant_Drivers_Grid_<CROP>` (.html/.png) |

Phase 3 classifies pixels with |dS| > 5 into 8 driver classes from the signs of dS, dT and dP
(code 0 = no significant change). dT or dP exactly 0 counts as "cold"/"dry".
Without climate rasters, Phase 3 falls back to the driver rasters already in
`results/<CROP>/Dominant_Driver_*.tif` (from the earlier workflow) for summaries and charts; the
`source` column in the summary CSVs says which was used.

## Dashboard

```bash
streamlit run app/main.py
```

- Sidebar: crop, climate scenario, future period, area of interest (whole area / county / UAT), map style.
- Map: one layer at a time (suitability present, suitability future, change, climate driver) with an
  in-map legend. Click any pixel to read all values at that location.
- Present vs future: two synchronised maps, share of area per change class, all-scenario table.
- Class changes and Climate drivers: the reference figures, recomputed for the selected area.

The current selection (crop, scenario, period, county / UAT) is kept in the page URL, so a link
such as `?crop=GR&ssp=SSP2-4.5&period=2071-2100&area=judet&judet=Alba` opens directly on that view.
Charts export as high-resolution PNG from their toolbar; the map has a full-screen button.

Rasters are served by a small tile server (`src/tileserver.py`, started automatically on 127.0.0.1)
at their native 100 m resolution. All statistics use every pixel of the selected area and are cached
on disk after the first view.

## Deploying on EOCube.Ro (JupyterHub)

The EOCube.Ro notebook image (Pangeo based) ships `jupyter-server-proxy`, which the dashboard uses to
reach both Streamlit and its tile server:

```bash
pip install -r requirements.txt
export LSI_DATA_DIR=/path/to/LSI          # if the data is not in ./LSI
export LSI_TILE_PORT=8765                 # fixed tile-server port (optional)
streamlit run app/main.py --server.port 8501 --server.headless true \
    --server.enableCORS false --server.enableXsrfProtection false
```

Open `https://<hub>/user/<name>/proxy/8501/`. On JupyterHub the tile URLs are built automatically from
`JUPYTERHUB_SERVICE_PREFIX` as `<prefix>proxy/<tile port>/...`; set `LSI_TILE_BASE_URL` (may contain
`{port}`) to override them, e.g. behind another reverse proxy.

## Development

```bash
python -m pytest tests -v     # unit, end-to-end (synthetic rasters) and ASCII charset tests
python -m black .             # formatting
```

Source files, configuration and this README must be ASCII only (enforced by
`tests/test_charset_policy.py`); user-facing symbols in code are written as `\uXXXX` escapes.
