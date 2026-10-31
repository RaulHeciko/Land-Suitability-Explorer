"""MCP tools: never raise, large results handed off by file, CLI <-> MCP parity."""

import inspect
import json

import pytest

from lsi_explorer.cli.main import cli
from lsi_explorer.mcp import _artifacts, _serialize, tools

# MCP tool -> CLI command path (parity contract; see the table in mcp/tools.py)
PARITY = {
    "catalog_list": ("catalog", "list"),
    "area_statistics": ("stats", "area"),
    "pipeline_run": ("pipeline", "run"),
    "pipeline_rebuild": ("pipeline", "run"),
    "admin_fetch_boundaries": ("admin", "fetch-boundaries"),
}


@pytest.fixture(autouse=True)
def artifacts(tmp_path, monkeypatch):
    monkeypatch.setenv("LSI_MCP_ARTIFACT_DIR", str(tmp_path / "artifacts"))


def test_every_tool_is_guarded_and_returns_dict():
    for func in tools.READ_TOOLS + tools.WRITE_TOOLS + tools.DESTRUCTIVE_TOOLS:
        assert inspect.signature(func).return_annotation in (dict, "dict"), func
        assert hasattr(func, "__wrapped__"), f"{func.__name__} is not @guarded"


def test_cli_parity():
    for name, path in PARITY.items():
        group = cli
        for part in path:
            group = group.commands[part]
        assert group is not None, name
    tool_names = {
        f.__name__
        for f in tools.READ_TOOLS + tools.WRITE_TOOLS + tools.DESTRUCTIVE_TOOLS
    }
    assert tool_names - {"area_transitions"} == set(PARITY)


def test_guarded_never_raises():
    res = tools.area_statistics("ZZ")
    assert res["ok"] is False and res["status"] == 400
    assert "Unknown crop code" in res["error"]


def test_error_result_marks_not_found():
    res = _serialize.error_result("op", FileNotFoundError("artifact not found: x"))
    assert res == {
        "ok": False,
        "error": "op: artifact not found: x",
        "status": 404,
        "not_found": True,
    }


def test_catalog_list(dataset):
    res = tools.catalog_list()
    assert res["ok"] and res["crops"][0]["code"] == "XX"


def test_area_statistics_hands_off_by_file(dataset):
    res = tools.area_statistics("XX")
    assert res["ok"] and "transitions_km2" not in json.dumps(res)
    full = _artifacts.load_json(res["result_file"])
    assert full["scenarios"]["SSP2-4.5 2041-2070"]["transitions_km2"]
    detail = tools.area_transitions(res["result_file"], "SSP2-4.5 2041-2070")
    assert detail["ok"] and len(detail["transitions_km2"]) == 10


def test_area_transitions_unknown_file_is_404():
    res = tools.area_transitions("missing.json", "SSP2-4.5 2041-2070")
    assert res["ok"] is False and res["not_found"] is True


def test_pipeline_run_does_not_overwrite(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        "lsi_explorer.pipeline.run",
        lambda crops, phases, overwrite=False: seen.update(overwrite=overwrite) or {},
    )
    assert tools.pipeline_run(["GR"])["ok"] and seen["overwrite"] is False
    assert tools.pipeline_rebuild(["GR"])["ok"] and seen["overwrite"] is True


def test_destructive_tools_registered_only_on_request():
    pytest.importorskip("mcp")
    from lsi_explorer.mcp.server import build_server

    import anyio

    def tools_of(server):
        return {tool.name: tool for tool in anyio.run(server.list_tools)}

    default = tools_of(build_server())
    assert "pipeline_rebuild" not in default
    assert set(default) == {f.__name__ for f in tools.READ_TOOLS + tools.WRITE_TOOLS}
    assert default["area_statistics"].annotations.read_only_hint is True
    assert default["pipeline_run"].annotations.destructive_hint is False
    opted_in = tools_of(build_server(allow_destructive=True))
    assert opted_in["pipeline_rebuild"].annotations.destructive_hint is True
