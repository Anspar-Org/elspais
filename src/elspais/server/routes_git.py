# Implements: REQ-p00004-C, REQ-p00004-D, REQ-p00004-E, REQ-p00004-F
# Implements: REQ-p00004-H, REQ-p00004-I
"""Starlette route handlers for /api/git/* endpoints."""
from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse

from elspais.mcp.server import _get_mutation_log


async def api_git_status(request: Request) -> JSONResponse:
    # Implements: REQ-p00004-C
    """GET /api/git/status - Git status summary for the viewer UI."""
    from elspais.utilities.git import git_status_summary

    state = request.app.state.app_state
    spec_dir = state.config.get("scanning", {}).get("spec", {}).get("directories", ["spec"])[0]
    result = git_status_summary(state.repo_root, spec_dir=spec_dir)
    return JSONResponse(result)


async def api_git_branch(request: Request) -> JSONResponse:
    # Implements: REQ-p00004-D
    """POST /api/git/branch - Create and switch to a new branch."""
    from elspais.utilities.git import create_and_switch_branch

    state = request.app.state.app_state
    data = await request.json()
    name = data.get("name", "").strip()
    if not name:
        return JSONResponse({"success": False, "error": "branch name required"}, status_code=400)
    result = create_and_switch_branch(state.repo_root, name)
    status_code = 200 if result.get("success") else 400
    return JSONResponse(result, status_code=status_code)


async def api_git_push(request: Request) -> JSONResponse:
    # Implements: REQ-p00004-E
    """POST /api/git/push - Commit and push spec files."""
    from elspais.utilities.git import commit_and_push_spec_files

    state = request.app.state.app_state
    data = await request.json()
    message = data.get("message", "").strip()
    if not message:
        return JSONResponse({"success": False, "error": "commit message required"}, status_code=400)
    spec_dir = state.config.get("scanning", {}).get("spec", {}).get("directories", ["spec"])[0]
    result = commit_and_push_spec_files(state.repo_root, message, spec_dir=spec_dir)
    return JSONResponse(result, status_code=200)


async def api_git_pull(request: Request) -> JSONResponse:
    # Implements: REQ-p00004-F
    """POST /api/git/pull - Sync branch with remote and main."""
    from elspais.utilities.git import sync_branch

    state = request.app.state.app_state
    result = sync_branch(state.repo_root)
    status_code = 200 if result.get("success") else 400
    return JSONResponse(result, status_code=status_code)


async def api_git_branches(request: Request) -> JSONResponse:
    # Implements: REQ-p00004-H
    """GET /api/git/branches - List local and remote git branches."""
    from elspais.utilities.git import list_branches

    state = request.app.state.app_state
    result = list_branches(state.repo_root)
    return JSONResponse(result)


async def api_git_checkout(request: Request) -> JSONResponse:
    # Implements: REQ-p00004-I
    """POST /api/git/checkout - Switch to an existing git branch."""
    import subprocess

    from elspais.utilities.git import _clean_git_env

    state = request.app.state.app_state
    data = await request.json()
    branch = data.get("branch", "").strip()
    is_remote = data.get("is_remote", False)

    if not branch:
        return JSONResponse({"success": False, "error": "branch name required"}, status_code=400)

    # Refuse if in-memory mutations are pending
    log = _get_mutation_log(state.graph, limit=1)
    if log.get("count", 0) > 0:
        return JSONResponse(
            {
                "success": False,
                "error": "Save or revert changes before switching branches",
            },
            status_code=409,
        )

    env = _clean_git_env()
    repo = state.repo_root

    try:
        if is_remote:
            result = subprocess.run(
                ["git", "checkout", "-b", branch, f"origin/{branch}"],
                cwd=repo,
                env=env,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0 and "already exists" in result.stderr:
                result = subprocess.run(
                    ["git", "checkout", branch],
                    cwd=repo,
                    env=env,
                    capture_output=True,
                    text=True,
                )
        else:
            result = subprocess.run(
                ["git", "checkout", branch],
                cwd=repo,
                env=env,
                capture_output=True,
                text=True,
            )

        if result.returncode != 0:
            return JSONResponse({"success": False, "error": result.stderr.strip()}, status_code=400)

        return JSONResponse({"success": True, "branch": branch})

    except FileNotFoundError:
        return JSONResponse({"success": False, "error": "git not found"}, status_code=500)
