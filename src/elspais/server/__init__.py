# Implements: REQ-d00010-A, REQ-d00010-F, REQ-d00010-G
"""elspais.server - Flask REST API server for trace-edit.

Provides a thin REST wrapper over the MCP server pure functions,
exposing the traceability graph via HTTP endpoints for the
interactive trace-edit UI.
"""

from elspais.server.app import create_app

__all__ = ["create_app"]
