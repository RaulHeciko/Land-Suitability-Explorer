"""MCP transport entry point (lives in the CLI layer so lsi_explorer.mcp stays transport-pure)."""

from __future__ import annotations

import click

from ..i18n import t


def serve(
    use_http: bool = False,
    host: str = "127.0.0.1",
    port: int = 8000,
    allow_destructive: bool = False,
) -> None:
    """Build the MCP server and run it over stdio or streamable HTTP."""
    try:
        from ..mcp.server import build_server
    except ImportError as exc:  # optional 'mcp' extra not installed
        raise click.ClickException(t("cli.mcp_missing")) from exc
    try:
        server = build_server(host=host, port=port, allow_destructive=allow_destructive)
    except ImportError as exc:
        raise click.ClickException(t("cli.mcp_missing")) from exc
    server.run(transport="streamable-http" if use_http else "stdio")
