# Implements: REQ-p00006-B
# Implements: REQ-d00010-A, REQ-d00010-F, REQ-d00010-G
"""elspais.server.app - Starlette app factory and route wiring.

This is a THIN REST wrapper -- all logic delegates to pure functions
in ``elspais.mcp.server``. No graph logic is duplicated here.

State is stored on ``app.state.app_state`` as an ``AppState`` instance.
"""

from __future__ import annotations

import contextlib
import re
import sys
from pathlib import Path

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from elspais.server.middleware import APIErrorMiddleware, AutoRefreshMiddleware, NoCacheMiddleware
from elspais.server.routes_api import (
    api_attach_client,
    api_check_freshness,
    api_code_coverage,
    api_comment_add,
    api_comment_reply,
    api_comment_resolve,
    api_dirty,
    api_events,
    api_export,
    api_file_content,
    api_get_comments,
    api_get_comments_card,
    api_get_comments_orphaned,
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
    api_mutate_remainder,
    api_mutate_remainder_add,
    api_mutate_remainder_delete,
    api_mutate_rename_file,
    api_mutate_requirement_add,
    api_mutate_requirement_delete,
    api_mutate_status,
    api_mutate_template,
    api_mutate_title,
    api_mutate_undo,
    api_next_req_id,
    api_node,
    api_query,
    api_refines_coverage,
    api_reload,
    api_repos,
    api_requirement,
    api_revert,
    api_run_analysis,
    api_run_checks,
    api_run_gaps,
    api_run_summary,
    api_run_trace,
    api_save,
    api_scope,
    api_search,
    api_shutdown,
    api_spec_files,
    api_status,
    api_term,
    api_terms,
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
    api_git_pr,
    api_git_pull,
    api_git_push,
    api_git_repo_status,
    api_git_status,
    api_git_suggest_branch_name,
)
from elspais.server.routes_ui import _extract_viewer_config, index
from elspais.server.state import AppState

# One or more segments, each introduced by a single slash and made of
# unreserved ASCII characters only: the form the page, a router and the
# mount all spell identically. A space, a "?", a "#" or a "%" is spelt
# differently by each, so one such prefix would name a different path in
# each; a "." or ".." segment is normalised away by the client before the
# request arrives, to the same effect.
_BASE_PATH_FORM = re.compile(r"^(?:/[A-Za-z0-9._~-]+)+$")
_BASE_PATH_DESCRIPTION = (
    "empty, or one or more path segments each introduced by a single '/' and "
    "made only of ASCII letters and digits, '-', '_', '.' and '~', with no "
    "segment being '.' or '..' (for example '/w/abc')"
)


# Implements: REQ-d00295-E
def validate_base_path(base_path: str) -> str:
    """Return ``base_path`` when it has the one accepted form, else raise.

    The refusal names that form; it is the one message both the viewer
    command and the application factory give.
    """
    if base_path == "":
        return base_path
    if _BASE_PATH_FORM.match(base_path) and not any(
        segment in (".", "..") for segment in base_path.split("/")[1:]
    ):
        return base_path
    raise ValueError(
        f"base path {base_path!r} is not accepted: it must be {_BASE_PATH_DESCRIPTION}"
    )


class DetachedGuardMiddleware:
    """Block mutation endpoints when in detached HEAD (read-only) mode.

    The check is a string test on the request path, so it is told the
    prefix the routes are mounted under: under ``/w/abc`` the mutation
    routes answer at ``/w/abc/api/mutate/...`` and nowhere else, and a path
    that merely contains the prefix further along is not one of them.
    """

    def __init__(self, app, base_path: str = ""):
        self.app = app
        self._mutate_prefix = base_path + "/api/mutate/"

    # Implements: REQ-d00295-A
    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["path"].startswith(self._mutate_prefix):
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


# `_extract_viewer_config` is imported above from routes_ui and re-exported
# here, where callers of the app module reach it.
__all__ = ["create_app", "validate_base_path", "_extract_viewer_config"]

# Bundled static assets, served at /static under the prefix when present.
_STATIC_DIR = Path(__file__).parent.parent / "html" / "templates" / "static"


# Implements: REQ-o00074-A, REQ-d00295-A, REQ-d00295-C
def create_app(state: AppState, mount_mcp: bool = True, base_path: str = "") -> Starlette:
    """Create the Starlette application with REST API routes.

    REQ-d00010-A: Application with factory function.
    REQ-d00010-F: CORS enabled for cross-origin requests.
    REQ-d00010-G: Static file serving from templates/static/.

    Args:
        state: Pre-built AppState instance with graph, config, etc.
        mount_mcp: Whether to mount the MCP sub-app at /mcp.
        base_path: Prefix the whole route table is mounted under (empty for
            the root). Validated by ``validate_base_path``.

    Returns:
        Configured Starlette application.
    """
    # Implements: REQ-o00074-A, REQ-o00079-A
    # One tracker for every stream a client can hold: an agent's MCP
    # session and a page's change stream are handles of the same kind,
    # and the watchdog reads one count. Created before either mount and
    # published on the holder so the watchdog can read it as a liveness
    # source.
    from starlette.routing import request_response

    from elspais.server.session_track import HeldSessionTracker

    tracker = HeldSessionTracker()
    state.shared["session_tracker"] = tracker

    base_path = validate_base_path(base_path)
    routes: list[Route | Mount] = [
        # UI
        Route("/", index),
        # Read-only GET endpoints
        Route("/api/status", api_status),
        Route("/api/repos", api_repos),
        Route("/api/requirement/{req_id:path}", api_requirement),
        Route("/api/node/{node_id:path}", api_node),
        Route("/api/query", api_query),
        Route("/api/scope", api_scope),
        Route("/api/hierarchy/{req_id:path}", api_hierarchy),
        Route("/api/search", api_search),
        Route("/api/test-coverage/{req_id:path}", api_test_coverage),
        Route("/api/code-coverage/{req_id:path}", api_code_coverage),
        Route("/api/refines-coverage/{req_id:path}", api_refines_coverage),
        Route("/api/uat-coverage/{req_id:path}", api_uat_coverage),
        Route("/api/tree-data", api_tree_data),
        Route("/api/file-content", api_file_content),
        Route("/api/spec-files", api_spec_files),
        Route("/api/dirty", api_dirty),
        Route("/api/check-freshness", api_check_freshness),
        # The page's change stream, counted as held for as long as it is
        # open: an object endpoint is served as the ASGI app it is.
        Route("/api/events", tracker.asgi(request_response(api_events)), methods=["GET"]),
        Route("/api/session/attach", api_attach_client, methods=["POST"]),
        # Terms endpoints
        Route("/api/terms", api_terms),
        Route("/api/term/{term_key:path}", api_term),
        # CLI command endpoints
        Route("/api/run/checks", api_run_checks),
        Route("/api/run/summary", api_run_summary),
        Route("/api/run/gaps", api_run_gaps),
        Route("/api/run/analysis", api_run_analysis),
        Route("/api/run/trace", api_run_trace),
        # The same reports, as documents to download
        Route("/api/export/{report}", api_export),
        # Mutation POST endpoints
        Route("/api/mutate/status", api_mutate_status, methods=["POST"]),
        Route("/api/mutate/template", api_mutate_template, methods=["POST"]),
        Route("/api/mutate/title", api_mutate_title, methods=["POST"]),
        Route("/api/mutate/assertion", api_mutate_assertion, methods=["POST"]),
        Route("/api/mutate/assertion/add", api_mutate_assertion_add, methods=["POST"]),
        Route("/api/mutate/assertion/delete", api_mutate_assertion_delete, methods=["POST"]),
        Route("/api/mutate/remainder", api_mutate_remainder, methods=["POST"]),
        Route("/api/mutate/remainder/add", api_mutate_remainder_add, methods=["POST"]),
        Route("/api/mutate/remainder/delete", api_mutate_remainder_delete, methods=["POST"]),
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
        # Comment endpoints (read)
        Route("/api/comments", api_get_comments),
        Route("/api/comments/card", api_get_comments_card),
        Route("/api/comments/orphaned", api_get_comments_orphaned),
        # Comment endpoints (write)
        Route("/api/comment/add", api_comment_add, methods=["POST"]),
        Route("/api/comment/reply", api_comment_reply, methods=["POST"]),
        Route("/api/comment/resolve", api_comment_resolve, methods=["POST"]),
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
        Route("/api/git/pr", api_git_pr, methods=["POST"]),
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

    # Mount MCP sub-app at /mcp. Implements: REQ-o00062-Q
    # Sharing state.graph with the viewer routes is what makes the version
    # guards protect agent and human writers against EACH OTHER — the whole
    # point of the concurrency contract.
    mcp_app = None
    if mount_mcp:
        try:
            from elspais.mcp.server import create_server

            mcp = create_server(
                graph=state.graph,
                working_dir=state.repo_root,
                shared_state=state.shared,
            )
            # The outer Mount supplies the /mcp prefix; FastMCP's internal
            # default path is also "/mcp", which would bury the endpoint at
            # /mcp/mcp while the documented /mcp answered 404.
            mcp.settings.streamable_http_path = "/"
            mcp_app = mcp.streamable_http_app()
            # A client that holds a server-to-client stream open is present
            # in a way the daemon can observe without its cooperation, which
            # is what a client handle has to be.
            routes.append(Mount("/mcp", app=tracker.asgi(mcp_app)))
        except Exception as exc:
            # Tolerated failure (visible, never silent): the server still
            # serves the viewer, but a missing MCP surface must be reported.
            print(f"warning: MCP mount unavailable at /mcp: {exc}", file=sys.stderr)
            mcp_app = None

    # Mount static files if directory exists
    if _STATIC_DIR.exists():
        from starlette.staticfiles import StaticFiles

        routes.append(Mount("/static", app=StaticFiles(directory=str(_STATIC_DIR))))

    # Implements: REQ-d00295-A, REQ-d00295-D
    # One outer Mount carries the whole table — API routes, the /mcp mount
    # and /static alike — so nothing answers at the root. An empty prefix
    # mounts nothing and leaves the table exactly as it was.
    if base_path:
        routes = [Mount(base_path, routes=routes)]

    # REQ-d00010-F: CORS support
    middleware = [
        Middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        ),
        Middleware(NoCacheMiddleware),
        Middleware(APIErrorMiddleware, base_path=base_path),
        Middleware(AutoRefreshMiddleware),
        Middleware(DetachedGuardMiddleware, base_path=base_path),
    ]

    # Starlette does not run mounted sub-apps' lifespans, and FastMCP's
    # StreamableHTTPSessionManager only works inside its lifespan — without
    # this, every MCP session over HTTP is terminated at initialize.
    # Implements: REQ-o00062-Q
    lifespan = None
    if mcp_app is not None:
        _mcp_app = mcp_app

        @contextlib.asynccontextmanager
        async def lifespan(app):  # noqa: ANN001, ANN202
            async with _mcp_app.router.lifespan_context(_mcp_app):
                yield

    app = Starlette(routes=routes, middleware=middleware, lifespan=lifespan)
    app.state.app_state = state
    # The page reads this to build every URL it requests (REQ-d00295-B).
    app.state.url_prefix = base_path

    return app
