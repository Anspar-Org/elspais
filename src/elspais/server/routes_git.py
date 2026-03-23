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


async def api_git_repo_status(request: Request) -> JSONResponse:
    # Implements: REQ-p00004-I
    """GET /api/git/repo-status - Per-repo branch/status for multi-repo UI."""
    from elspais.utilities.git import _clean_git_env, _count_commits_since, _find_main_branch, get_current_branch

    state = request.app.state.app_state
    entries = _iter_repo_entries(state)
    protected = state.config.get("rules", {}).get("protected_branches", ["main", "master"])
    repos = []

    for name, root, config in entries:
        branch = get_current_branch(root)
        env = _clean_git_env()
        main_ref = _find_main_branch(root, ("main", "master"), env)
        if branch and main_ref and branch != main_ref:
            commit_count = _count_commits_since(root, main_ref, env)
        else:
            commit_count = 0
        ds = state.get_detached_state(name)
        repo_info: dict[str, Any] = {
            "name": name,
            "repo_root": str(root),
            "branch": branch,
            "commit_count": commit_count,
            "is_detached": ds is not None,
        }
        if ds:
            repo_info["originating_branch"] = ds.originating_branch
            repo_info["originating_head"] = ds.originating_head
        repos.append(repo_info)

    return JSONResponse({"repos": repos, "protected_branches": protected})


async def api_git_monorepo_eligible(request: Request) -> JSONResponse:
    # Implements: REQ-p00004-I
    """GET /api/git/monorepo-eligible - Check monorepo mode eligibility."""
    from elspais.utilities.git import check_monorepo_eligible

    state = request.app.state.app_state
    entries = _iter_repo_entries(state)
    repos = [(name, root) for name, root, _ in entries]
    eligible, reasons = check_monorepo_eligible(repos)
    return JSONResponse({"eligible": eligible, "reasons": reasons})


async def api_git_status(request: Request) -> JSONResponse:
    # Implements: REQ-p00004-C
    """GET /api/git/status - Git status summary for the viewer UI."""
    from elspais.utilities.git import git_status_summary

    state = request.app.state.app_state
    repo_name = request.query_params.get("repo")
    root = _resolve_repo_root(state, repo_name)
    spec_dir = state.config.get("scanning", {}).get("spec", {}).get("directories", ["spec"])[0]
    result = git_status_summary(root, spec_dir=spec_dir)

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

        result["detached_commit"] = get_current_commit(root)
        if root_ds and root_ds.originating_head:
            import subprocess

            from elspais.utilities.git import _clean_git_env

            try:
                rv = subprocess.run(
                    ["git", "rev-list", "--count", "HEAD.." + root_ds.originating_head],
                    cwd=root,
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
    from elspais.utilities.git import create_and_switch_branch, invalidate_ancestor_cache

    state = request.app.state.app_state
    data = await request.json()
    name = data.get("name", "").strip()
    monorepo = data.get("monorepo", False)
    if not name:
        return JSONResponse({"success": False, "error": "branch name required"}, status_code=400)

    if monorepo:
        results = []
        for rname, root, _ in _iter_repo_entries(state):
            r = create_and_switch_branch(root, name)
            r["repo"] = rname
            results.append(r)
            if r.get("success"):
                state.leave_detached(rname)
        invalidate_ancestor_cache()
        all_ok = all(r.get("success") for r in results)
        return JSONResponse({"success": all_ok, "results": results})
    else:
        result = create_and_switch_branch(state.repo_root, name)
        invalidate_ancestor_cache()
        status_code = 200 if result.get("success") else 400
        return JSONResponse(result, status_code=status_code)


async def api_git_push(request: Request) -> JSONResponse:
    # Implements: REQ-p00004-E
    """POST /api/git/push - Push local commits to remote."""
    import subprocess

    from elspais.utilities.git import _clean_git_env, get_current_branch

    state = request.app.state.app_state
    try:
        data = await request.json()
    except Exception:
        data = {}
    monorepo = data.get("monorepo", False)
    repo_name = data.get("repo")

    if monorepo:
        results = []
        for name, root, _ in _iter_repo_entries(state):
            branch = get_current_branch(root)
            if not branch:
                results.append({"repo": name, "success": False, "error": "detached HEAD"})
                continue
            env = _clean_git_env()
            rv = subprocess.run(
                ["git", "push", "-u", "origin", branch],
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
            )
            if rv.returncode != 0:
                results.append({"repo": name, "success": False, "error": rv.stderr.strip()})
            else:
                results.append({"repo": name, "success": True, "branch": branch})
        all_ok = all(r["success"] for r in results)
        return JSONResponse({"success": all_ok, "results": results})
    else:
        root = _resolve_repo_root(state, repo_name)
        branch = get_current_branch(root)
        if not branch:
            return JSONResponse(
                {"success": False, "error": "Cannot push in detached HEAD state"}, status_code=400
            )
        env = _clean_git_env()
        try:
            rv = subprocess.run(
                ["git", "push", "-u", "origin", branch],
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
            )
            if rv.returncode != 0:
                return JSONResponse(
                    {"success": False, "error": rv.stderr.strip()}, status_code=400
                )
            return JSONResponse({"success": True, "branch": branch})
        except FileNotFoundError:
            return JSONResponse({"success": False, "error": "git not found"}, status_code=500)


async def api_git_pull(request: Request) -> JSONResponse:
    # Implements: REQ-p00004-F
    """POST /api/git/pull - Sync branch with remote and main."""
    from elspais.utilities.git import invalidate_ancestor_cache, sync_branch

    state = request.app.state.app_state
    try:
        data = await request.json()
    except Exception:
        data = {}
    monorepo = data.get("monorepo", False)
    repo_name = data.get("repo")

    if monorepo:
        results = []
        for name, root, _ in _iter_repo_entries(state):
            r = sync_branch(root)
            r["repo"] = name
            results.append(r)
        invalidate_ancestor_cache()
        all_ok = all(r.get("success") for r in results)
        return JSONResponse({"success": all_ok, "results": results})
    else:
        root = _resolve_repo_root(state, repo_name)
        result = sync_branch(root)
        invalidate_ancestor_cache()
        status_code = 200 if result.get("success") else 400
        return JSONResponse(result, status_code=status_code)


async def api_git_branches(request: Request) -> JSONResponse:
    # Implements: REQ-p00004-H
    """GET /api/git/branches - List local and remote git branches."""
    from elspais.utilities.git import list_branches

    state = request.app.state.app_state
    repo_name = request.query_params.get("repo")
    root = _resolve_repo_root(state, repo_name)
    result = list_branches(root)
    return JSONResponse(result)


def _checkout_single_repo(repo: Path, branch: str, is_remote: bool) -> dict:
    """Checkout a branch in a single repo.

    Tries local checkout first. For remote branches, also tries creating
    a local tracking branch. Catches FileNotFoundError for missing git.
    """
    import subprocess

    from elspais.utilities.git import _clean_git_env

    env = _clean_git_env()
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
            return {"success": False, "error": result.stderr.strip()}
        return {"success": True, "branch": branch}
    except FileNotFoundError:
        return {"success": False, "error": "git not found"}


async def api_git_checkout(request: Request) -> JSONResponse:
    # Implements: REQ-p00004-I
    """POST /api/git/checkout - Switch to an existing git branch (single or multi-repo)."""
    from elspais.utilities.git import check_dirty_repos, invalidate_ancestor_cache

    state = request.app.state.app_state
    data = await request.json()
    branch = data.get("branch", "").strip()
    is_remote = data.get("is_remote", False)
    monorepo = data.get("monorepo", False)
    repo_name = data.get("repo")

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

    if monorepo:
        entries = _iter_repo_entries(state)
        repos = [(name, root) for name, root, _ in entries]
        dirty = check_dirty_repos(repos)
        if dirty:
            return JSONResponse(
                {
                    "success": False,
                    "error": f"Dirty working trees in repos: {', '.join(dirty)}",
                },
                status_code=409,
            )
        results = []
        for rname, root, _ in entries:
            r = _checkout_single_repo(root, branch, is_remote)
            r["repo"] = rname
            results.append(r)
            if r.get("success"):
                state.leave_detached(rname)
        invalidate_ancestor_cache()
        all_ok = all(r.get("success") for r in results)
        return JSONResponse({"success": all_ok, "results": results})
    else:
        root = _resolve_repo_root(state, repo_name)
        result = _checkout_single_repo(root, branch, is_remote)
        if result.get("success"):
            effective_name = repo_name if repo_name else "root"
            state.leave_detached(effective_name)
            invalidate_ancestor_cache()
        status_code = 200 if result.get("success") else 400
        return JSONResponse(result, status_code=status_code)


async def api_git_commits(request: Request) -> JSONResponse:
    """GET /api/git/commits - List commits on a branch."""
    from elspais.utilities.git import list_commits

    state = request.app.state.app_state
    repo_name = request.query_params.get("repo")
    root = _resolve_repo_root(state, repo_name)
    branch = request.query_params.get("branch", "HEAD")
    limit = int(request.query_params.get("limit", "20"))
    result = list_commits(root, branch=branch, limit=limit)
    return JSONResponse(result)


async def api_git_commit(request: Request) -> JSONResponse:
    """POST /api/git/commit - Commit spec files locally (checkpoint)."""
    from elspais.utilities.git import (
        check_dirty_repos,
        commit_spec_files,
        create_sync_commit,
        remove_sync_file,
    )

    state = request.app.state.app_state
    data = await request.json()
    message = data.get("message", "").strip()
    monorepo = data.get("monorepo", False)
    repo_name = data.get("repo")
    if not message:
        return JSONResponse({"success": False, "error": "commit message required"}, status_code=400)

    if monorepo:
        results = []
        changed_repos = []
        unchanged_repos = []
        for name, root, config in _iter_repo_entries(state):
            spec_dir = (config or {}).get("scanning", {}).get("spec", {}).get(
                "directories", ["spec"]
            )[0]
            dirty = check_dirty_repos([(name, root)])
            if dirty:
                changed_repos.append((name, root, spec_dir))
            else:
                unchanged_repos.append((name, root, spec_dir))
        changed_names = [n for n, _, _ in changed_repos]
        for name, root, spec_dir in changed_repos:
            remove_sync_file(root, spec_dir=spec_dir)
            r = commit_spec_files(root, message, spec_dir=spec_dir)
            r["repo"] = name
            r["sync"] = False
            results.append(r)
        aligned_with = ", ".join(changed_names) if changed_names else "federation"
        for name, root, spec_dir in unchanged_repos:
            r = create_sync_commit(
                root, spec_dir=spec_dir, aligned_with=aligned_with, message=message
            )
            r["repo"] = name
            r["sync"] = True
            results.append(r)
        all_ok = all(r["success"] for r in results)
        return JSONResponse({"success": all_ok, "results": results})
    else:
        root = _resolve_repo_root(state, repo_name)
        spec_dir = state.config.get("scanning", {}).get("spec", {}).get("directories", ["spec"])[0]
        files = data.get("files")
        remove_sync_file(root, spec_dir=spec_dir)
        result = commit_spec_files(root, message, spec_dir=spec_dir, files=files)
        status_code = 200 if result.get("success") else 400
        return JSONResponse(result, status_code=status_code)


async def api_git_checkout_commit(request: Request) -> JSONResponse:
    """POST /api/git/checkout-commit - Checkout a specific commit (detached HEAD)."""
    import subprocess

    from elspais.utilities.git import (
        _clean_git_env,
        check_dirty_repos,
        checkout_commit,
        get_current_branch,
        get_current_commit,
        invalidate_ancestor_cache,
    )

    state = request.app.state.app_state
    data = await request.json()
    monorepo = data.get("monorepo", False)
    repo_name = data.get("repo")
    offset = data.get("offset")

    log = _get_mutation_log(state.graph, limit=1)
    if log.get("count", 0) > 0:
        return JSONResponse(
            {"success": False, "error": "Save or revert changes before rewinding"}, status_code=409
        )

    if monorepo and offset is not None:
        entries = _iter_repo_entries(state)
        repos = [(name, root) for name, root, _ in entries]
        dirty = check_dirty_repos(repos)
        if dirty:
            return JSONResponse(
                {"success": False, "error": f"Dirty working trees in: {', '.join(dirty)}"},
                status_code=409,
            )
        results = []
        env = _clean_git_env()
        for name, root in repos:
            branch = get_current_branch(root) or ""
            head = get_current_commit(root) or ""
            rv = subprocess.run(
                ["git", "checkout", f"HEAD~{offset}"],
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
            )
            if rv.returncode == 0:
                state.enter_detached(name, branch=branch, head_commit=head)
                results.append({"repo": name, "success": True})
            else:
                results.append({"repo": name, "success": False, "error": rv.stderr.strip()})
        invalidate_ancestor_cache()
        return JSONResponse(
            {"success": all(r["success"] for r in results), "results": results}
        )
    else:
        commit_hash = data.get("hash", "").strip()
        originating_branch = data.get("branch", "").strip()
        if not commit_hash:
            return JSONResponse(
                {"success": False, "error": "commit hash required"}, status_code=400
            )
        root = _resolve_repo_root(state, repo_name)
        rname = repo_name or "root"
        if not originating_branch:
            originating_branch = get_current_branch(root) or ""
        originating_head = get_current_commit(root) or ""
        result = checkout_commit(root, commit_hash)
        if result.get("success"):
            state.enter_detached(rname, branch=originating_branch, head_commit=originating_head)
            invalidate_ancestor_cache()
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
