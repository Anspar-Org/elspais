"""Entry point for running elspais MCP server directly.

Usage:
    python -m elspais.mcp
"""

from elspais.mcp.server import run_server

if __name__ == "__main__":
    run_server()
