"""MCP server construction (requires the optional ``mcp`` extra, mcp 2.x, imported lazily)."""

from __future__ import annotations

from . import tools


def build_server(allow_destructive: bool = False):
    """``MCPServer`` with the LSI tools registered.

    Read and write tools register unconditionally; destructive tools only when
    ``allow_destructive`` is set (``lsi mcp serve --allow-destructive``).
    """
    from mcp.server.mcpserver import MCPServer
    from mcp.types import ToolAnnotations

    server = MCPServer("lsi-explorer")
    for func in tools.READ_TOOLS:
        server.add_tool(func, annotations=ToolAnnotations(read_only_hint=True))
    for func in tools.WRITE_TOOLS:
        server.add_tool(
            func,
            annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False),
        )
    if allow_destructive:
        for func in tools.DESTRUCTIVE_TOOLS:
            server.add_tool(
                func,
                annotations=ToolAnnotations(
                    read_only_hint=False, destructive_hint=True
                ),
            )
    return server
