# Implements: REQ-p00006-B
# Implements: REQ-d00010-A, REQ-d00010-F, REQ-d00010-G
"""elspais.server.app - Starlette app factory and route wiring.

This is a THIN REST wrapper -- all logic delegates to pure functions
in ``elspais.mcp.server``. No graph logic is duplicated here.

State is stored on ``app.state.app_state`` as an ``AppState`` instance.
"""
from __future__ import annotations

from pathlib import Path

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from elspais.server.middleware import AutoRefreshMiddleware, NoCacheMiddleware
from elspais.server.routes_api import (
    api_check_freshness,
    api_code_coverage,
    api_dirty,
    api_file_content,
    api_hierarchy,
    api_journey_files,
    api_mutate_assertion,
    api_mutate_assertion_add,
    api_mutate_assertion_delete,
    api_mutate_edge,
    api_mutate_journey_add,
    api_mutate_journey_delete,
    api_mutate_journey_field,
    api_mutate_journey_section,
    api_mutate_move_to_file,
    api_mutate_rename_file,
    api_mutate_requirement_add,
    api_mutate_requirement_delete,
    api_mutate_status,
    api_mutate_title,
    api_mutate_undo,
    api_next_req_id,
    api_node,
    api_query,
    api_reload,
    api_repos,
    api_requirement,
    api_revert,
    api_run_analysis,
    api_run_broken,
    api_run_checks,
    api_run_gaps,
    api_run_summary,
    api_run_trace,
    api_run_unlinked,
    api_save,
    api_search,
    api_shutdown,
    api_spec_files,
    api_status,
    api_test_coverage,
    api_tree_data,
    api_uat_coverage,
)
from elspais.server.routes_git import (
    api_git_branch,
    api_git_branches,
    api_git_checkout,
    api_git_checkout_commit,
    api_git_commit,
    api_git_commit_message,
    api_git_commits,
    api_git_monorepo_eligible,
    api_git_pull,
    api_git_push,
    api_git_repo_status,
    api_git_status,
    api_git_suggest_branch_name,
)
from elspais.server.routes_ui import _extract_viewer_config, index
from elspais.server.state import AppState


class DetachedGuardMiddleware:
    """Block mutation endpoints when in detached HEAD (read-only) mode."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["path"].startswith("/api/mutate/"):
            request = Request(scope, receive)
            state = request.app.state.app_state
            if state.is_detached:
                response = JSONResponse(
                    {
                        "success": False,
                        "error": "Read-only: in detached HEAD mode. Switch to a branch to edit.",
                    },
                    status_code=409,
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


# Re-export for backward compatibility (used by tests/core/test_viewer_config.py)
__all__ = ["create_app", "_extract_viewer_config"]


def create_app(state: AppState, mount_mcp: bool = True) -> Starlette:
    """Create the Starlette application with REST API routes.

    REQ-d00010-A: Application with factory function.
    REQ-d00010-F: CORS enabled for cross-origin requests.
    REQ-d00010-G: Static file serving from templates/static/.

    Args:
        state: Pre-built AppState instance with graph, config, etc.
        mount_mcp: Whether to mount the MCP sub-app at /mcp.

    Returns:
        Configured Starlette application.
    """
    routes: list[Route | Mount] = [
        # UI
        Route("/", index),
        # Read-only GET endpoints
        Route("/api/status", api_status),
        Route("/api/repos", api_repos),
        Route("/api/requirement/{req_id:path}", api_requirement),
        Route("/api/node/{node_id:path}", api_node),
        Route("/api/query", api_query),
        Route("/api/hierarchy/{req_id:path}", api_hierarchy),
        Route("/api/search", api_search),
        Route("/api/test-coverage/{req_id:path}", api_test_coverage),
        Route("/api/code-coverage/{req_id:path}", api_code_coverage),
        Route("/api/uat-coverage/{req_id:path}", api_uat_coverage),
        Route("/api/tree-data", api_tree_data),
        Route("/api/file-content", api_file_content),
        Route("/api/spec-files", api_spec_files),
        Route("/api/dirty", api_dirty),
        Route("/api/check-freshness", api_check_freshness),
        # CLI command endpoints
        Route("/api/run/checks", api_run_checks),
        Route("/api/run/broken", api_run_broken),
        Route("/api/run/summary", api_run_summary),
        Route("/api/run/gaps", api_run_gaps),
        Route("/api/run/unlinked", api_run_unlinked),
        Route("/api/run/analysis", api_run_analysis),
        Route("/api/run/trace", api_run_trace),
        # Mutation POST endpoints
        Route("/api/mutate/status", api_mutate_status, methods=["POST"]),
        Route("/api/mutate/title", api_mutate_title, methods=["POST"]),
        Route("/api/mutate/assertion", api_mutate_assertion, methods=["POST"]),
        Route("/api/mutate/assertion/add", api_mutate_assertion_add, methods=["POST"]),
        Route("/api/mutate/assertion/delete", api_mutate_assertion_delete, methods=["POST"]),
        Route("/api/next-req-id", api_next_req_id),
        Route("/api/mutate/requirement/add", api_mutate_requirement_add, methods=["POST"]),
        Route(
            "/api/mutate/requirement/delete",
            api_mutate_requirement_delete,
            methods=["POST"],
        ),
        Route("/api/mutate/edge", api_mutate_edge, methods=["POST"]),
        Route("/api/mutate/journey/field", api_mutate_journey_field, methods=["POST"]),
        Route("/api/mutate/journey/section", api_mutate_journey_section, methods=["POST"]),
        Route("/api/mutate/journey/add", api_mutate_journey_add, methods=["POST"]),
        Route("/api/mutate/journey/delete", api_mutate_journey_delete, methods=["POST"]),
        Route("/api/journey-files", api_journey_files),
        Route("/api/mutate/move-to-file", api_mutate_move_to_file, methods=["POST"]),
        Route("/api/mutate/rename-file", api_mutate_rename_file, methods=["POST"]),
        Route("/api/mutate/undo", api_mutate_undo, methods=["POST"]),
        # Lifecycle
        Route("/api/shutdown", api_shutdown, methods=["POST"]),
        # Persistence
        Route("/api/save", api_save, methods=["POST"]),
        Route("/api/revert", api_revert, methods=["POST"]),
        Route("/api/reload", api_reload, methods=["POST"]),
        # Git endpoints
        Route("/api/git/status", api_git_status),
        Route("/api/git/branch", api_git_branch, methods=["POST"]),
        Route("/api/git/push", api_git_push, methods=["POST"]),
        Route("/api/git/pull", api_git_pull, methods=["POST"]),
        Route("/api/git/branches", api_git_branches),
        Route("/api/git/checkout", api_git_checkout, methods=["POST"]),
        Route("/api/git/commits", api_git_commits),
        Route("/api/git/commit", api_git_commit, methods=["POST"]),
        Route("/api/git/checkout-commit", api_git_checkout_commit, methods=["POST"]),
        Route("/api/git/commit-message", api_git_commit_message),
        Route("/api/git/suggest-branch-name", api_git_suggest_branch_name),
        Route("/api/git/repo-status", api_git_repo_status),
        Route("/api/git/monorepo-eligible", api_git_monorepo_eligible),
    ]

    # Mount MCP sub-app at /mcp
    if mount_mcp:
        try:
            from elspais.mcp.server import create_server

            mcp = create_server(graph=state.graph, working_dir=state.repo_root)
            routes.append(Mount("/mcp", app=mcp.streamable_http_app()))
        except Exception:
            pass  # MCP not available or setup failed

    # Mount static files if directory exists
    templates_dir = Path(__file__).parent.parent / "html" / "templates"
    static_dir = templates_dir / "static"
    if static_dir.exists():
        from starlette.staticfiles import StaticFiles

        routes.append(Mount("/static", app=StaticFiles(directory=str(static_dir))))

    # REQ-d00010-F: CORS support
    middleware = [
        Middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        ),
        Middleware(NoCacheMiddleware),
        Middleware(AutoRefreshMiddleware),
        Middleware(DetachedGuardMiddleware),
    ]

    app = Starlette(routes=routes, middleware=middleware)
    app.state.app_state = state

    return app
