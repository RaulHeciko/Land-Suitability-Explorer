"""FastMCP server construction (requires the optional ``mcp`` extra, imported lazily)."""

from __future__ import annotations

from . import tools


def build_server(
    host: str = "127.0.0.1", port: int = 8000, allow_destructive: bool = False
):
    """FastMCP server with the LSI tools registered.

    Read and write tools register unconditionally; destructive tools only when
    ``allow_destructive`` is set (``lsi mcp serve --allow-destructive``).
    """
    from mcp.server.fastmcp import FastMCP
    from mcp.types import ToolAnnotations

    server = FastMCP("lsi-explorer", host=host, port=port)
    for func in tools.READ_TOOLS:
        server.add_tool(func, annotations=ToolAnnotations(readOnlyHint=True))
    for func in tools.WRITE_TOOLS:
        server.add_tool(
            func,
            annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
        )
    if allow_destructive:
        for func in tools.DESTRUCTIVE_TOOLS:
            server.add_tool(
                func,
                annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True),
            )
    return server
