# Land Suitability Explorer

Prototype web application and Python library for analysing how climate change scenarios affect
the land suitability of crops in Romania. It processes the land suitability rasters produced with
GeoLaSS (Geospatial Land Suitability System) and presents them in an interactive dashboard, for
deployment on the EOCube.Ro platform.

The project follows the EOCube.Ro development conventions (see `AGENTS.md`): a library layer, a
Click CLI and an MCP server exposing the same capabilities, Poetry packaging with optional extras,
English/Romanian localization, ASCII-only sources and `black` formatting.

## Installing

```bash
pip install poetry
poetry install --with dev --all-extras    # development: everything + tests and black
```

or with pip, choosing only the extras you need:

```bash
pip install -e ".[app]"      # dashboard + CLI
pip install -e ".[full]"     # everything, including the MCP server
```

| Extra | Purpose | Packages |
|---|---|---|
| `raster` | Raster I/O and statistics | numpy, pandas, rasterio, pyproj, shapely, pillow |
| `charts` | Figures and PNG export | plotly, kaleido |
| `services` | County / UAT boundaries | geopandas |
| `cli` | `lsi` command line | click |
| `app` | Dashboard | streamlit, folium, streamlit-folium + raster, charts, services, cli |
| `mcp` | MCP server | mcp, click |
| `full` | Everything | all of the above |

The only hard runtime dependency is `pyyaml` (translations). If PostGIS/ArcGIS set a
system-wide `PROJ_LIB`, `lsi_explorer/__init__.py` drops it so rasterio uses its own `proj.db`.

## Input data

Data paths are relative to the working directory (or `LSI_HOME`); each can be overridden.

```
LSI/  (or data/LSI/, or LSI_DATA_DIR)
  prezent/<CROP>/_<CROP>_land_suitability.tif                 continuous score 0-100
  prezent/<CROP>/_<CROP>_land_suitability_10_categories.tif   classes 1-10
  ssp126_2041-2070/<CROP>/...   ssp126_2071-2100/...   ssp245_2041-2070/...   ssp245_2071-2100/...
data/climate/<period>/tas.tif, pr.tif   optional - needed to compute new driver maps (Phase 3)
data/mask/study_area.tif                optional - otherwise the valid-pixel footprint is used
data/admin/judete.gpkg, uat.gpkg        county / UAT boundaries (lsi admin fetch-boundaries)
data/crop_names.csv                     optional - code,name; overrides the built-in crop names
results/                                outputs (LSI_RESULTS_DIR)
```

Rasters use Stereo70 (EPSG:3844); a 100 m pixel is 0.01 km2 and all areas are reported in km2.
Suitability classes: C1 = most suitable (score 90-100) ... C10 = least suitable (0-10).
Change in suitability (future - present, score points): `< -10`, `-10 to -5`, `-5 to +5`
(no significant change), `+5 to +10`, `> +10`.

## Command line

```bash
lsi --version                                   # version and build commit
lsi catalog list                                # crops and scenarios found
lsi admin fetch-boundaries                      # county + UAT boundaries from geo-spatial.org
lsi pipeline run --crop GR --phase 1 --phase 2  # Phases 1-3 (default: all crops, all phases)
lsi stats area --crop GR --judet Alba --ssp SSP2-4.5 --output alba.json
lsi app --port 8501                             # dashboard
lsi mcp serve                                   # MCP server over stdio (--http for HTTP)
lsi --lang ro ...                               # Romanian interface
```

| Phase | Module | Outputs |
|---|---|---|
| 0 | `preprocessing.py` | cleaning (score outside 0-100 and class outside 1-10 become NoData), alignment, study-area masking |
| 1 | `phase1_deltas.py` | `results/deltas/<CROP>/Delta_Suitability_<SSP>_<period>_<CROP>.tif`, `delta_summary.csv` |
| 2 | `phase2_transitions.py` | transition matrices and class dynamics (CSV, km2) and their figures |
| 3 | `phase3_attribution.py` | dominant climate driver rasters, area summaries and figures |

Phase 3 classifies pixels with |dS| > 5 into 8 driver classes from the signs of dS, dT and dP.
Without climate rasters it summarises the driver rasters already in
`results/<CROP>/Dominant_Driver_*.tif`.

## MCP server

`lsi mcp serve` (stdio) or `lsi mcp serve --http` exposes the same capabilities as the CLI:

| Tool | CLI | Kind |
|---|---|---|
| `catalog_list` | `lsi catalog list` | read-only |
| `area_statistics` | `lsi stats area` | read-only; full result written to a server-side JSON file |
| `area_transitions` | - | read-only; reads one scenario from an `area_statistics` result file |
| `pipeline_run` | `lsi pipeline run` | write |
| `pipeline_rebuild` | `lsi pipeline run --overwrite` | destructive; only with `--allow-destructive` |
| `admin_fetch_boundaries` | `lsi admin fetch-boundaries` | write |

Tools never raise: errors are returned as `{"ok": false, "error", "status", "not_found"}`.
Large results are handed off by file; set `LSI_MCP_ARTIFACT_DIR` (or `EOCUBE_MCP_ARTIFACT_DIR`)
to a shared volume for multi-replica HTTP deployments.

## Dashboard

`lsi app` starts the Streamlit dashboard with the project theme:

- sidebar: crop, climate scenario, future period, area of interest (whole area / county / UAT);
- Map: suitability (present / future), change classes and climate drivers at native 100 m
  resolution (local tile server), click any pixel to read its values, full-screen button;
- Present vs future: synchronised maps, change-class distribution and scenario summary;
- Class changes and Climate drivers: transition matrices, class dynamics and driver charts.

The selection is kept in the page URL (shareable links), e.g.
`?crop=GR&ssp=SSP2-4.5&period=2071-2100&area=judet&judet=Alba`; add `&lang=ro` for Romanian.
Charts export as high-resolution PNG from their toolbar.

## Deploying on EOCube.Ro (JupyterHub)

The EOCube.Ro notebook image (Pangeo based) ships `jupyter-server-proxy`:

```bash
pip install -e ".[app]"
export LSI_DATA_DIR=/path/to/LSI     # if the data is not in ./LSI
export LSI_TILE_PORT=8765            # fixed tile-server port (optional)
lsi app --port 8501 --headless
```

Open `https://<hub>/user/<name>/proxy/8501/`. Tile URLs are built from
`JUPYTERHUB_SERVICE_PREFIX` as `<prefix>proxy/<tile port>/...`; set `LSI_TILE_BASE_URL`
(may contain `{port}`) to override them.

## Development

```bash
poetry run pytest tests/ -v     # unit, CLI, MCP, architecture and end-to-end tests
poetry run black .              # formatting (checked in CI)
```

- Library modules must not import the CLI layer, the dashboard or CLI-only dependencies;
  `tests/test_architecture.py` enforces it.
- Every user-facing capability has a CLI command and an MCP tool calling the same library
  function; `tests/test_mcp.py` checks the parity.
- Source files, configuration and this README are ASCII only (`tests/test_charset_policy.py`);
  user-facing strings live in `src/lsi_explorer/locales/{en,ro}.yml`.
- Tests never access the network: they use synthetic rasters and mocks.
- Work on a feature branch and open a merge/pull request; never commit directly to `main`.
- CI (`.gitlab-ci.yml`, `.github/workflows/ci.yml`) runs `black --check` and `pytest`.

### Versioning

`lsi --version` prints `lsi-explorer <version>, commit <sha12> (clean|dirty)`. For a release
build, stamp the commit and restore the placeholder afterwards:

```bash
./scripts/stamp-build-info.sh && poetry build && git checkout -- src/lsi_explorer/_build_info.py
```

### Licensing

After changing dependencies, regenerate the third-party notice file:

```bash
pip-licenses --from=mixed --format=plain --with-urls -i lsi-explorer > NOTICE
```
