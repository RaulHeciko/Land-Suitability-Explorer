"""``lsi`` command line entry point.

Every command is a thin wrapper around a library function; the same functions back the MCP
tools in ``lsi_explorer.mcp`` (CLI <-> MCP parity). ``lsi app`` and ``lsi mcp serve`` start
servers and are therefore CLI-only.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from ..i18n import set_language, t
from ..version import format_version_string


def _fail(exc: Exception) -> None:
    raise click.ClickException(str(exc))


def _print_version(ctx: click.Context, _param, value: bool) -> None:
    if value and not ctx.resilient_parsing:
        click.echo(format_version_string())
        ctx.exit()


@click.group(help=t("cli.help"))
@click.option(
    "--version",
    is_flag=True,
    expose_value=False,
    is_eager=True,
    callback=_print_version,
    help=t("cli.version_help"),
)
@click.option("--lang", default=None, help=t("cli.lang_help"))
def cli(lang: str | None) -> None:
    set_language(lang)


# ------------------------------------------------------------------ pipeline


@cli.group(help=t("cli.pipeline_help"))
def pipeline() -> None:
    pass


@pipeline.command("run", help=t("cli.pipeline_run_help"))
@click.option("--crop", "crops", multiple=True, help=t("cli.crops_help"))
@click.option(
    "--phase",
    "phases",
    multiple=True,
    type=click.IntRange(1, 3),
    help=t("cli.phases_help"),
)
@click.option("--overwrite", is_flag=True, help=t("cli.overwrite_help"))
@click.option("--no-figures", is_flag=True, help=t("cli.no_figures_help"))
def pipeline_run(crops, phases, overwrite: bool, no_figures: bool) -> None:
    from .. import pipeline as lib

    try:
        res = lib.run(
            list(crops) or None,
            tuple(phases) or lib.PHASES,
            overwrite=overwrite,
            figures=not no_figures,
        )
    except ValueError as exc:
        _fail(exc)
    click.echo(
        t(
            "cli.pipeline_done",
            n=len(res["crops"]),
            phases=",".join(map(str, res["phases"])),
            path=res["results_dir"],
        )
    )


# ------------------------------------------------------------------ catalog


@cli.group(help=t("cli.catalog_help"))
def catalog() -> None:
    pass


@catalog.command("list", help=t("cli.catalog_list_help"))
def catalog_list() -> None:
    from ..utils import catalog_info

    info = catalog_info()
    click.echo(t("cli.crops_title", n=len(info["crops"])))
    for c in info["crops"]:
        click.echo(f"  {c['code']:<4} {c['name']}")
    click.echo(t("cli.scenarios_title", n=len(info["scenarios"])))
    for s in info["scenarios"]:
        click.echo(f"  {s['ssp']} {s['period']}")


# ------------------------------------------------------------------ stats


@cli.group(help=t("cli.stats_help"))
def stats() -> None:
    pass


@stats.command("area", help=t("cli.stats_area_help"))
@click.option("--crop", required=True, help=t("cli.crop_help"))
@click.option("--judet", default=None, help=t("cli.judet_help"))
@click.option("--uat", default=None, help=t("cli.uat_help"))
@click.option("--ssp", default=None, help=t("cli.ssp_help"))
@click.option("--period", default=None, help=t("cli.period_help"))
@click.option(
    "--output",
    type=click.Path(dir_okay=False, path_type=Path),
    help=t("cli.output_help"),
)
def stats_area(crop, judet, uat, ssp, period, output: Path | None) -> None:
    from ..analysis import area_statistics

    try:
        res = area_statistics(crop, judet=judet, uat=uat, ssp=ssp, period=period)
    except ValueError as exc:
        _fail(exc)
    text = json.dumps(res, indent=2, ensure_ascii=False)
    if output:
        output.write_text(text, encoding="utf-8")
        click.echo(t("cli.written", path=output))
    else:
        click.echo(text)


# ------------------------------------------------------------------ admin boundaries


@cli.group(help=t("cli.admin_help"))
def admin() -> None:
    pass


@admin.command("fetch-boundaries", help=t("cli.fetch_help"))
@click.option(
    "--out", type=click.Path(file_okay=False, path_type=Path), help=t("cli.out_help")
)
def admin_fetch(out: Path | None) -> None:
    from ..boundaries import fetch

    for name, path in fetch(out).items():
        click.echo(t("cli.fetched", name=name, path=path))


# ------------------------------------------------------------------ servers (CLI only)


DASHBOARD_THEME = {
    "theme.base": "light",
    "theme.primaryColor": "#0A7470",
    "theme.backgroundColor": "#F4F6F9",
    "theme.secondaryBackgroundColor": "#ECEFF4",
    "theme.textColor": "#131C2E",
    "theme.font": "sans serif",
    "browser.gatherUsageStats": "false",
}


def dashboard_command(port: int, headless: bool) -> list[str]:
    """Streamlit command line that starts the dashboard with the project theme."""
    app = Path(__file__).resolve().parents[1] / "dashboard" / "app.py"
    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(app),
        "--server.port",
        str(port),
    ]
    cmd += ["--server.headless", "true" if headless else "false"]
    for key, value in DASHBOARD_THEME.items():
        cmd += [f"--{key}", value]
    return cmd


@cli.command("app", help=t("cli.app_help"))
@click.option("--port", default=8501, show_default=True, help=t("cli.port_help"))
@click.option("--headless", is_flag=True, help=t("cli.headless_help"))
def app(port: int, headless: bool) -> None:
    import subprocess

    raise SystemExit(subprocess.call(dashboard_command(port, headless)))


@cli.group(help=t("cli.mcp_help"))
def mcp() -> None:
    pass


@mcp.command("serve", help=t("cli.mcp_serve_help"))
@click.option("--http", "use_http", is_flag=True, help=t("cli.http_help"))
@click.option("--host", default="127.0.0.1", show_default=True, help=t("cli.host_help"))
@click.option("--port", default=8000, show_default=True, help=t("cli.port_help"))
@click.option("--allow-destructive", is_flag=True, help=t("cli.destructive_help"))
def mcp_serve(use_http: bool, host: str, port: int, allow_destructive: bool) -> None:
    from .mcp import serve

    serve(use_http=use_http, host=host, port=port, allow_destructive=allow_destructive)


if __name__ == "__main__":
    cli()
