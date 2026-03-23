# Implements: REQ-p00004-C, REQ-p00004-D, REQ-p00004-E, REQ-p00004-F
# Implements: REQ-p00004-H, REQ-p00004-I
"""Starlette route handlers for /api/git/* endpoints."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse

from elspais.mcp.server import _get_mutation_log


# Implements: REQ-d00201-A
def _iter_repo_entries(state: Any) -> list[tuple[str, Path, dict | None]]:
    """Yield (name, repo_root, config) for all repos in the graph.
    Works for both FederatedGraph (iter_repos) and plain TraceGraph (root only).
    """
    if hasattr(state.graph, "iter_repos"):
        return [
            (e.name, e.repo_root, e.config)
            for e in state.graph.iter_repos()
            if e.error is None and e.graph is not None
        ]
    return [("root", state.repo_root, state.config)]


# Implements: REQ-d00201-A
def _resolve_repo_root(state: Any, repo_name: str | None) -> Path:
    """Look up repo root by name. None/'root' returns state.repo_root."""
    if repo_name is None or repo_name == "root":
        return state.repo_root
    for name, root, _ in _iter_repo_entries(state):
        if name == repo_name:
            return root
    raise ValueError(f"Unknown repo: {repo_name!r}")


async def api_git_status(request: Request) -> JSONResponse:
    # Implements: REQ-p00004-C
    """GET /api/git/status - Git status summary for the viewer UI."""
    from elspais.utilities.git import git_status_summary

    state = request.app.state.app_state
    spec_dir = state.config.get("scanning", {}).get("spec", {}).get("directories", ["spec"])[0]
    result = git_status_summary(state.repo_root, spec_dir=spec_dir)

    # Augment with detached HEAD state fields.
    # Detect detached HEAD from git state (branch is None) even if AppState
    # doesn't know about it (e.g. server started on a detached worktree).
    git_detached = result.get("branch") is None
    root_ds = state.get_detached_state("root")
    is_detached = root_ds is not None or git_detached
    result["is_detached"] = is_detached
    result["originating_branch"] = root_ds.originating_branch if root_ds else None
    result["originating_head"] = root_ds.originating_head if root_ds else None
    if is_detached:
        from elspais.utilities.git import get_current_commit

        result["detached_commit"] = get_current_commit(state.repo_root)
        if root_ds and root_ds.originating_head:
            import subprocess

            from elspais.utilities.git import _clean_git_env

            try:
                rv = subprocess.run(
                    ["git", "rev-list", "--count", "HEAD.." + root_ds.originating_head],
                    cwd=state.repo_root,
                    env=_clean_git_env(),
                    capture_output=True,
                    text=True,
                )
                result["commits_behind_head"] = int(rv.stdout.strip()) if rv.returncode == 0 else 0
            except (FileNotFoundError, ValueError):
                result["commits_behind_head"] = 0
        else:
            result["commits_behind_head"] = 0
    else:
        result["detached_commit"] = None
        result["commits_behind_head"] = 0
    result["uncommitted_file_count"] = len(result.get("dirty_spec_files", [])) + len(
        result.get("dirty_other_files", [])
    )

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
    """POST /api/git/push - Push local commits to remote (no commit step)."""
    import subprocess

    from elspais.utilities.git import _clean_git_env, get_current_branch

    state = request.app.state.app_state
    branch = get_current_branch(state.repo_root)
    if not branch:
        return JSONResponse(
            {"success": False, "error": "Cannot push in detached HEAD state"}, status_code=400
        )
    env = _clean_git_env()
    try:
        result = subprocess.run(
            ["git", "push", "-u", "origin", branch],
            cwd=state.repo_root,
            env=env,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return JSONResponse({"success": False, "error": result.stderr.strip()}, status_code=400)
        return JSONResponse({"success": True, "branch": branch})
    except FileNotFoundError:
        return JSONResponse({"success": False, "error": "git not found"}, status_code=500)


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

        state.leave_detached("root")
        return JSONResponse({"success": True, "branch": branch})

    except FileNotFoundError:
        return JSONResponse({"success": False, "error": "git not found"}, status_code=500)


async def api_git_commits(request: Request) -> JSONResponse:
    """GET /api/git/commits - List commits on a branch."""
    from elspais.utilities.git import list_commits

    state = request.app.state.app_state
    branch = request.query_params.get("branch", "HEAD")
    limit = int(request.query_params.get("limit", "20"))
    result = list_commits(state.repo_root, branch=branch, limit=limit)
    return JSONResponse(result)


async def api_git_commit(request: Request) -> JSONResponse:
    """POST /api/git/commit - Commit spec files locally (checkpoint)."""
    from elspais.utilities.git import commit_spec_files

    state = request.app.state.app_state
    data = await request.json()
    message = data.get("message", "").strip()
    if not message:
        return JSONResponse({"success": False, "error": "commit message required"}, status_code=400)
    files = data.get("files")  # explicit file list, or None for auto-discover
    spec_dir = state.config.get("scanning", {}).get("spec", {}).get("directories", ["spec"])[0]
    result = commit_spec_files(state.repo_root, message, spec_dir=spec_dir, files=files)
    status_code = 200 if result.get("success") else 400
    return JSONResponse(result, status_code=status_code)


async def api_git_checkout_commit(request: Request) -> JSONResponse:
    """POST /api/git/checkout-commit - Checkout a specific commit (detached HEAD)."""
    from elspais.utilities.git import checkout_commit, get_current_branch, get_current_commit

    state = request.app.state.app_state
    data = await request.json()
    commit_hash = data.get("hash", "").strip()
    originating_branch = data.get("branch", "").strip()
    if not commit_hash:
        return JSONResponse({"success": False, "error": "commit hash required"}, status_code=400)
    # Refuse if in-memory mutations are pending
    log = _get_mutation_log(state.graph, limit=1)
    if log.get("count", 0) > 0:
        return JSONResponse(
            {"success": False, "error": "Save or revert changes before rewinding"}, status_code=409
        )
    # Capture before checkout
    if not originating_branch:
        originating_branch = get_current_branch(state.repo_root) or ""
    originating_head = get_current_commit(state.repo_root) or ""
    result = checkout_commit(state.repo_root, commit_hash)
    if result.get("success"):
        state.enter_detached("root", branch=originating_branch, head_commit=originating_head)
    status_code = 200 if result.get("success") else 400
    return JSONResponse(result, status_code=status_code)


async def api_git_commit_message(request: Request) -> JSONResponse:
    """GET /api/git/commit-message - Auto-generate checkpoint commit message."""
    from elspais.utilities.git import generate_checkpoint_message

    state = request.app.state.app_state
    spec_dir = state.config.get("scanning", {}).get("spec", {}).get("directories", ["spec"])[0]
    message = generate_checkpoint_message(state.repo_root, spec_dir=spec_dir)
    return JSONResponse({"message": message})


async def api_git_suggest_branch_name(request: Request) -> JSONResponse:
    """GET /api/git/suggest-branch-name - Suggest non-colliding branch name."""
    from elspais.utilities.git import suggest_branch_name

    state = request.app.state.app_state
    base = request.query_params.get("base", "branch")
    name = suggest_branch_name(state.repo_root, base)
    return JSONResponse({"name": name})
