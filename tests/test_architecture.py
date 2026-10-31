"""Boundary enforcement (same rules as eocube's tests/test_architecture.py).

- library modules never import the CLI layer, the dashboard or CLI-only dependencies;
- the MCP layer stays transport-pure (no click / rich);
- no module uses keyring;
- importing the package does not pull in heavy optional dependencies.
"""

import ast
import subprocess
import sys
from pathlib import Path

import pytest

PKG = Path(__file__).resolve().parents[1] / "src" / "lsi_explorer"
CLI_ONLY = {"click", "rich", "keyring", "flask", "ascii_magic", "matplotlib"}
UI_ONLY = {"streamlit", "streamlit_folium", "folium", "branca"}


def _modules(*parts):
    base = PKG.joinpath(*parts)
    return sorted(base.rglob("*.py")) if base.is_dir() else [base]


def _imports(path: Path) -> set[str]:
    """Absolute dotted names imported by `path` (relative imports resolved)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    rel = path.relative_to(PKG.parent).with_suffix("").parts
    pkg_parts = list(rel[:-1])
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = pkg_parts[: len(pkg_parts) - node.level + 1] if node.level else []
            mod = ".".join(base + ([node.module] if node.module else []))
            names.add(mod)
            if node.level:
                names.update(f"{mod}.{a.name}" for a in node.names)
    return names


LIBRARY = [
    p
    for p in _modules()
    if not {"cli", "mcp", "dashboard"} & set(p.relative_to(PKG).parts)
]


@pytest.mark.parametrize("path", LIBRARY, ids=lambda p: p.relative_to(PKG).as_posix())
def test_library_does_not_import_cli_or_ui(path):
    for name in _imports(path):
        top = name.split(".")[0]
        assert top not in CLI_ONLY | UI_ONLY, f"{path.name} imports {name}"
        assert not name.startswith(
            ("lsi_explorer.cli", "lsi_explorer.dashboard")
        ), f"{path.name} imports {name}"


@pytest.mark.parametrize(
    "path", _modules("mcp"), ids=lambda p: p.relative_to(PKG).as_posix()
)
def test_mcp_layer_is_transport_pure(path):
    for name in _imports(path):
        assert name.split(".")[0] not in {
            "click",
            "rich",
        }, f"{path.name} imports {name}"
        assert not name.startswith("lsi_explorer.cli"), f"{path.name} imports {name}"


def test_no_module_uses_keyring():
    for path in _modules():
        assert not any(n.split(".")[0] == "keyring" for n in _imports(path)), path


def test_importing_package_is_lightweight():
    code = (
        "import sys, lsi_explorer, lsi_explorer.i18n, lsi_explorer.utils;"
        "heavy = {'rasterio', 'geopandas', 'plotly', 'streamlit', 'matplotlib', 'click', 'mcp'};"
        "print(sorted(heavy & set(sys.modules)))"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert out.stdout.strip() == "[]"
