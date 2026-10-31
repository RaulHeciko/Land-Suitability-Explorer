# AGENTS.md

Guidance for AI coding assistants and developers working on this repository. It follows the
EOCube.Ro development conventions (eocube-tools AGENTS.md).

## Core rules

- Keep code as simple as possible; reuse existing code and maintained libraries.
- Docstrings describe the purpose and interface of functions; avoid unnecessary comments.
- Do not break function interfaces without confirmation; update the documentation.
- Add tests for new functionality and regression tests for every bug fix.
- ASCII only in code, configuration, `README.md` and `CHANGELOG.md`; user-facing strings live in
  `src/lsi_explorer/locales/{lang}.yml` (exempt) and symbols in code use `\uXXXX` escapes.
  Enforced by `tests/test_charset_policy.py`.
- Format with `black`.
- Library modules must not import `lsi_explorer.cli`, `lsi_explorer.mcp`, the dashboard or
  CLI/UI-only dependencies (`click`, `rich`, `keyring`, `flask`, `matplotlib`, `streamlit`,
  `folium`). Enforced by `tests/test_architecture.py`.
- Heavy/optional dependencies are lazy-imported inside the functions that need them.
- CLI <-> MCP parity: every user-facing capability has a Click command and an MCP tool calling
  the same library function. MCP tools are `@guarded`, annotated `-> dict`, marked with
  `ToolAnnotations`; destructive tools register only with `allow_destructive`; large results
  are handed off by file (`mcp/_artifacts.py`). Starting servers is CLI-only.
- Never commit directly to `main`: use a feature branch and a merge/pull request.

## Development

```bash
poetry install --with dev --all-extras
poetry run pytest tests/ -v
poetry run black .
```

Tests must not access the network (use the `dataset` fixture and mocks).
See `ARCHITECTURE.md` for the layer overview.
