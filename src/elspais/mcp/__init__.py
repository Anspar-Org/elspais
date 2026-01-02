"""
elspais.mcp - MCP (Model Context Protocol) server for elspais.

This module provides an MCP server that exposes elspais functionality
to AI agents and LLMs. Requires the optional 'mcp' dependency:

    pip install elspais[mcp]

Usage:
    elspais mcp serve                    # Start with stdio transport
    python -m elspais.mcp                # Alternative entry point
"""

from elspais.mcp.context import WorkspaceContext
from elspais.mcp.serializers import (
    serialize_assertion,
    serialize_content_rule,
    serialize_requirement,
    serialize_requirement_summary,
    serialize_violation,
)

__all__ = [
    "WorkspaceContext",
    "serialize_assertion",
    "serialize_content_rule",
    "serialize_requirement",
    "serialize_requirement_summary",
    "serialize_violation",
]


def create_server(working_dir=None):
    """Create MCP server instance."""
    from elspais.mcp.server import create_server as _create
    return _create(working_dir)


def run_server(working_dir=None, transport="stdio"):
    """Run MCP server."""
    from elspais.mcp.server import run_server as _run
    return _run(working_dir, transport)
