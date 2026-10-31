# Changelog

## 0.1.0 - unreleased

### Added
- `lsi_explorer` package (src layout, Poetry, optional extras).
- Library: preprocessing, Phases 1-3, area statistics for the whole area, a county or a UAT,
  county/UAT boundaries from geo-spatial.org, Plotly figures, native-resolution tile server.
- `lsi` command line (Click): `catalog list`, `pipeline run`, `stats area`,
  `admin fetch-boundaries`, `app`, `mcp serve`, `--version`, `--lang`.
- MCP tools with CLI parity: `catalog_list`, `area_statistics`, `area_transitions`,
  `pipeline_run`, `pipeline_rebuild` (destructive, opt-in), `admin_fetch_boundaries`.
- English and Romanian localization (`locales/en.yml`, `locales/ro.yml`).
- Streamlit dashboard: maps, present vs future, class changes, climate drivers, shareable links.
- Build provenance (`lsi --version`), CI for GitLab and GitHub, architecture and charset tests.

### Changed
- Replaced `run_pipeline.py` and `scripts/fetch_admin_boundaries.py` with `lsi` commands.
- Replaced `requirements*.txt` with `pyproject.toml`.
- Removed the matplotlib dependency from the library (colour ramps computed directly).

### Fixed
- `t()` accepts placeholders named like its own parameter (e.g. `path`).
