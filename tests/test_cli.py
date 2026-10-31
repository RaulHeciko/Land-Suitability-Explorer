"""CLI command tree and behaviour on the synthetic dataset (external services mocked)."""

import json

import pytest
from click.testing import CliRunner

from lsi_explorer.cli import main as cli_main
from lsi_explorer.cli.main import cli


@pytest.fixture
def runner():
    return CliRunner()


def test_command_tree():
    assert set(cli.commands) == {"pipeline", "catalog", "stats", "admin", "app", "mcp"}
    assert set(cli.commands["pipeline"].commands) == {"run"}
    assert set(cli.commands["stats"].commands) == {"area"}
    assert set(cli.commands["admin"].commands) == {"fetch-boundaries"}
    assert set(cli.commands["mcp"].commands) == {"serve"}


def test_version(runner):
    res = runner.invoke(cli, ["--version"])
    assert res.exit_code == 0 and res.output.startswith("lsi-explorer ")


def test_catalog_list(runner, dataset):
    res = runner.invoke(cli, ["catalog", "list"])
    assert res.exit_code == 0
    assert "XX" in res.output and "SSP2-4.5 2041-2070" in res.output


def test_stats_area_to_file(runner, dataset, tmp_path):
    out = tmp_path / "stats.json"
    res = runner.invoke(cli, ["stats", "area", "--crop", "XX", "--output", str(out)])
    assert res.exit_code == 0, res.output
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["scenarios"]["SSP2-4.5 2041-2070"]["loss_km2"] == pytest.approx(0.31)


def test_stats_unknown_crop_is_a_clean_error(runner, dataset):
    res = runner.invoke(cli, ["stats", "area", "--crop", "ZZ"])
    assert res.exit_code != 0 and "Unknown crop code: ZZ" in res.output
    assert "Traceback" not in res.output


def test_pipeline_run_calls_library(runner, monkeypatch):
    calls = {}

    def fake_run(crops, phases, overwrite=False, figures=True):
        calls.update(crops=crops, phases=phases, overwrite=overwrite, figures=figures)
        return {
            "crops": crops,
            "phases": list(phases),
            "results_dir": "R",
            "seconds": {},
        }

    monkeypatch.setattr("lsi_explorer.pipeline.run", fake_run)
    res = runner.invoke(
        cli, ["pipeline", "run", "--crop", "GR", "--phase", "2", "--no-figures"]
    )
    assert res.exit_code == 0, res.output
    assert calls == {
        "crops": ["GR"],
        "phases": (2,),
        "overwrite": False,
        "figures": False,
    }


def test_admin_fetch_boundaries_is_mocked(runner, monkeypatch, tmp_path):
    monkeypatch.setattr(
        "lsi_explorer.boundaries.fetch",
        lambda out: {"judete": tmp_path / "judete.gpkg", "uat": tmp_path / "uat.gpkg"},
    )
    res = runner.invoke(cli, ["admin", "fetch-boundaries", "--out", str(tmp_path)])
    assert res.exit_code == 0 and "judete.gpkg" in res.output


def test_dashboard_command_carries_theme():
    cmd = cli_main.dashboard_command(8600, headless=True)
    assert cmd[1:4] == ["-m", "streamlit", "run"] and cmd[4].endswith("app.py")
    assert "--server.port" in cmd and "8600" in cmd
    assert "--theme.primaryColor" in cmd and "#0A7470" in cmd


def test_romanian_help(runner):
    res = runner.invoke(cli, ["--lang", "ro", "catalog", "--help"])
    assert res.exit_code == 0
