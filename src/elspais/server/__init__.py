# Implements: REQ-d00010-A, REQ-d00010-F, REQ-d00010-G
"""elspais.server - Starlette REST API server for trace-edit.

Provides a thin REST wrapper over the MCP server pure functions,
exposing the traceability graph via HTTP endpoints for the
interactive trace-edit UI.
"""

from elspais.server.app import create_app
from elspais.server.state import AppState

__all__ = ["AppState", "create_app"]
