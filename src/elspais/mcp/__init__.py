"""elspais.mcp - Model Context Protocol server for elspais.

This module provides an MCP server that exposes elspais functionality
to AI agents. The server is a pure interface layer that consumes
TraceGraph directly (REQ-p00060-B).

Usage:
    # Check if MCP is available
    from elspais.mcp import MCP_AVAILABLE

    if MCP_AVAILABLE:
        from elspais.mcp import create_server, run_server

        # Create server
        server = create_server()

        # Or run directly
        run_server()
"""

try:
    from mcp.server.fastmcp import FastMCP

    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    FastMCP = None


def create_server(*args, **kwargs):
    """Create the MCP server.

    Raises:
        ImportError: If MCP dependencies are not installed.
    """
    if not MCP_AVAILABLE:
        raise ImportError("MCP dependencies not installed. Install with: pip install elspais[mcp]")
    from elspais.mcp.server import create_server as _create

    return _create(*args, **kwargs)


def run_server(*args, **kwargs):
    """Run the MCP server.

    Raises:
        ImportError: If MCP dependencies are not installed.
    """
    if not MCP_AVAILABLE:
        raise ImportError("MCP dependencies not installed. Install with: pip install elspais[mcp]")
    from elspais.mcp.server import run_server as _run

    return _run(*args, **kwargs)


__all__ = [
    "MCP_AVAILABLE",
    "create_server",
    "run_server",
]
