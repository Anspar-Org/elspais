# Implements: REQ-p00006-B
# Implements: REQ-d00010-A, REQ-d00010-F, REQ-d00010-G
"""Starlette REST API route handlers for /api/* endpoints.

All logic delegates to pure functions in ``elspais.mcp.server``.
State is accessed via ``request.app.state.app_state`` (an AppState instance).
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse

from elspais.graph import NodeKind
from elspais.mcp.server import (
    _get_assertion_code_map,
    _get_assertion_test_map,
    _get_graph_status,
    _get_hierarchy,
    _get_mutation_log,
    _get_node,
    _get_requirement,
    _mutate_add_assertion,
    _mutate_add_edge,
    _mutate_change_edge_kind,
    _mutate_change_edge_targets,
    _mutate_change_status,
    _mutate_delete_assertion,
    _mutate_delete_edge,
    _mutate_delete_requirement,
    _mutate_move_node_to_file,
    _mutate_rename_file,
    _mutate_update_assertion,
    _mutate_update_title,
    _query_nodes,
    _search,
    _undo_last_mutation,
)


def _st(request: Request) -> Any:
    """Shorthand to get AppState from request."""
    return request.app.state.app_state


# ─────────────────────────────────────────────────────────────────
# Read-only GET endpoints
# ─────────────────────────────────────────────────────────────────


async def api_status(request: Request) -> JSONResponse:
    """GET /api/status - Graph status with federation repo info."""
    state = _st(request)
    result = _get_graph_status(state.graph)
    # Implements: REQ-d00206-C
    # Include federation repo metadata from iter_repos()
    graph = state.graph
    if hasattr(graph, "iter_repos"):
        repos_info = []
        for entry in graph.iter_repos():
            repo_info: dict[str, Any] = {
                "name": entry.name,
                "path": str(entry.repo_root),
                "status": "error" if entry.graph is None else "ok",
            }
            if entry.git_origin:
                repo_info["git_origin"] = entry.git_origin
            if entry.error:
                repo_info["error"] = entry.error
            repos_info.append(repo_info)
        result["repos"] = repos_info
    else:
        result["repos"] = []
    return JSONResponse(result)


# Implements: REQ-d00206-A, REQ-d00206-B
async def api_repos(request: Request) -> JSONResponse:
    """GET /api/repos - Federation repo info with optional staleness."""
    state = _st(request)
    graph = state.graph
    repos: list[dict] = []
    if hasattr(graph, "iter_repos"):
        for entry in graph.iter_repos():
            repo_info: dict = {
                "name": entry.name,
                "path": str(entry.repo_root),
                "status": "error" if entry.graph is None else "ok",
            }
            if entry.git_origin:
                repo_info["git_origin"] = entry.git_origin
            if entry.error:
                repo_info["error"] = entry.error

            # REQ-d00206-B: Staleness info for repos with git_origin
            if entry.git_origin and entry.graph is not None:
                try:
                    from elspais.utilities.git import git_status_summary

                    summary = git_status_summary(entry.repo_root)
                    repo_info["staleness"] = {
                        "branch": summary.get("branch"),
                        "remote_diverged": summary.get("remote_diverged", False),
                        "fast_forward_possible": summary.get("fast_forward_possible", False),
                    }
                except Exception:
                    repo_info["staleness"] = None

            repos.append(repo_info)
    return JSONResponse({"repos": repos})


async def api_requirement(request: Request) -> JSONResponse:
    """GET /api/requirement/{req_id} - Full requirement details."""
    state = _st(request)
    req_id = request.path_params["req_id"]
    result = _get_requirement(state.graph, req_id)
    if "error" in result:
        return JSONResponse(result, status_code=404)
    return JSONResponse(result)


async def api_node(request: Request) -> JSONResponse:
    """GET /api/node/{node_id} - Full details for any node kind."""
    state = _st(request)
    node_id = request.path_params["node_id"]
    result = _get_node(state.graph, node_id)
    if "error" in result:
        return JSONResponse(result, status_code=404)
    return JSONResponse(result)


async def api_query(request: Request) -> JSONResponse:
    """GET /api/query - Combined property + keyword filter endpoint."""
    state = _st(request)
    kind = request.query_params.get("kind")
    keywords_str = request.query_params.get("keywords", "")
    keywords = [k.strip() for k in keywords_str.split(",") if k.strip()] if keywords_str else None
    match_all = request.query_params.get("match_all", "true").lower() != "false"
    limit = int(request.query_params.get("limit", "50"))
    filters: dict[str, str] = {}
    for prop in ("level", "status", "actor"):
        val = request.query_params.get(prop)
        if val:
            filters[prop] = val
    return JSONResponse(
        _query_nodes(state.graph, kind, keywords, match_all, filters or None, limit)
    )


async def api_hierarchy(request: Request) -> JSONResponse:
    """GET /api/hierarchy/{req_id} - Ancestors and children."""
    state = _st(request)
    req_id = request.path_params["req_id"]
    result = _get_hierarchy(state.graph, req_id)
    if "error" in result:
        return JSONResponse(result, status_code=404)
    return JSONResponse(result)


async def api_search(request: Request) -> JSONResponse:
    """GET /api/search?q=<query>&field=<field>&limit=<n>&regex=<bool>."""
    state = _st(request)
    query = request.query_params.get("q", "")
    field = request.query_params.get("field", "all")
    regex = request.query_params.get("regex", "false").lower() == "true"
    limit = int(request.query_params.get("limit", "50"))
    if not query:
        return JSONResponse([])
    return JSONResponse(_search(state.graph, query, field, regex=regex, limit=limit))


async def api_test_coverage(request: Request) -> JSONResponse:
    """GET /api/test-coverage/{req_id} - Per-assertion test coverage map."""
    state = _st(request)
    req_id = request.path_params["req_id"]
    result = _get_assertion_test_map(state.graph, req_id)
    if "error" in result:
        return JSONResponse(result, status_code=404)
    return JSONResponse(result)


async def api_code_coverage(request: Request) -> JSONResponse:
    """GET /api/code-coverage/{req_id} - Per-assertion code implementation map."""
    state = _st(request)
    req_id = request.path_params["req_id"]
    result = _get_assertion_code_map(state.graph, req_id)
    if "error" in result:
        return JSONResponse(result, status_code=404)
    return JSONResponse(result)


async def api_tree_data(request: Request) -> JSONResponse:
    """GET /api/tree-data - Build tree data for nav panel."""
    import re

    from elspais.html.generator import compute_validation_color

    state = _st(request)
    g = state.graph
    rows: list[dict[str, Any]] = []
    visited: set[tuple[str, str]] = set()

    def _is_associated(node) -> bool:
        if re.match(r"^REQ-[A-Z]{2,4}-[a-z]", node.id):
            return True
        rp = node.get_metric("repo_prefix", "")
        if rp and rp != "CORE":
            return True
        _fn = node.file_node()
        if _fn and _fn.get_field("repo"):
            return True
        return bool(node.get_field("associated", False))

    def _get_repo_prefix(node) -> str:
        rp = node.get_metric("repo_prefix", "")
        if rp and rp != "CORE":
            return rp
        _fn = node.file_node()
        if _fn and _fn.get_field("repo"):
            return _fn.get_field("repo")
        m = re.match(r"^REQ-([A-Z]{2,4})-[a-z]", node.id)
        if m:
            return m.group(1)
        return rp or "CORE"

    def _walk(node, depth: int, parent_id: str | None) -> None:
        if node.kind != NodeKind.REQUIREMENT:
            return
        visit_key = (node.id, parent_id or "__root__")
        if visit_key in visited:
            return
        visited.add(visit_key)

        assertions = []
        for child in node.iter_children():
            if child.kind == NodeKind.ASSERTION:
                label = child.get_field("label", "")
                if label:
                    assertions.append(label)

        has_children = any(c.kind == NodeKind.REQUIREMENT for c in node.iter_children())
        coverage = node.get_field("coverage", "none")
        is_changed = bool(node.get_field("is_changed", False))
        is_uncommitted = bool(node.get_field("is_uncommitted", False))
        val_color, val_tip = compute_validation_color(node)

        rows.append(
            {
                "id": node.id,
                "kind": "requirement",
                "title": node.get_label() or "",
                "level": (node.get_field("level") or "").upper(),
                "status": (node.get_field("status") or "").upper(),
                "depth": depth,
                "parent_id": parent_id,
                "assertions": sorted(assertions),
                "has_children": has_children,
                "is_leaf": not has_children,
                "coverage": coverage,
                "is_changed": is_changed,
                "is_uncommitted": is_uncommitted,
                "is_associated": _is_associated(node),
                "is_test": False,
                "is_test_result": False,
                "result_status": "",
                "repo_prefix": _get_repo_prefix(node),
                "source_file": node.get_field("source_file", ""),
                "source_line": node.get_field("source_line", 0),
                "validation_color": val_color,
                "validation_tip": val_tip,
            }
        )

        req_children = sorted(
            (c for c in node.iter_children() if c.kind == NodeKind.REQUIREMENT),
            key=lambda n: n.id,
        )
        for child in req_children:
            _walk(child, depth + 1, node.id)

    for root in sorted(g.iter_roots(), key=lambda n: n.id):
        if root.kind == NodeKind.REQUIREMENT:
            _walk(root, 0, None)

    # Add USER_JOURNEY nodes
    for node in sorted(g.nodes_by_kind(NodeKind.USER_JOURNEY), key=lambda n: n.id):
        _fn = node.file_node()
        source_file = _fn.get_field("relative_path") if _fn else ""
        source_line = node.get_field("parse_line") or 0
        rows.append(
            {
                "id": node.id,
                "kind": "journey",
                "title": node.get_label() or "",
                "level": "",
                "status": "",
                "depth": 0,
                "parent_id": None,
                "assertions": [],
                "has_children": False,
                "is_leaf": True,
                "coverage": "none",
                "is_changed": False,
                "is_uncommitted": False,
                "is_associated": False,
                "is_test": False,
                "is_test_result": False,
                "is_journey": True,
                "result_status": "",
                "repo_prefix": "CORE",
                "source_file": source_file,
                "source_line": source_line,
                "actor": node.get_field("actor", ""),
                "goal": node.get_field("goal", ""),
            }
        )

    return JSONResponse(rows)


async def api_file_content(request: Request) -> JSONResponse:
    """GET /api/file-content?path=<path> - Read a file from disk."""
    import os

    from elspais.graph.mutations import MutationLog
    from elspais.html.highlighting import highlight_file_content

    state = _st(request)
    rel_path = request.query_params.get("path", "")
    if not rel_path:
        return JSONResponse({"error": "path parameter required"}, status_code=400)

    p = Path(rel_path)
    abs_path = (p if p.is_absolute() else (state.repo_root / rel_path)).resolve()

    # Security: path must be under repo root or an allowed associate dir
    if not any(abs_path.is_relative_to(root) for root in state.allowed_roots):
        return JSONResponse({"error": "path outside repository"}, status_code=403)

    if not abs_path.exists():
        return JSONResponse({"error": f"file not found: {rel_path}"}, status_code=404)

    try:
        content = abs_path.read_text(encoding="utf-8")
    except Exception as e:
        return JSONResponse({"error": f"cannot read file: {e}"}, status_code=500)

    lines = content.splitlines()
    highlighted = highlight_file_content(rel_path, content)

    g = state.graph
    mutation_log: MutationLog = g.mutation_log
    affected_node_ids: set[str] = set()
    for entry in mutation_log.iter_entries():
        node_id = entry.after_state.get("node_id", "") if entry.after_state else ""
        if not node_id:
            node_id = entry.before_state.get("node_id", "") if entry.before_state else ""
        if not node_id:
            continue
        node = g.find_by_id(node_id)
        if node:
            _fn = node.file_node()
            _rp = _fn.get_field("relative_path") if _fn else None
            if _rp:
                source_path = Path(_rp)
                node_path = (
                    source_path if source_path.is_absolute() else (state.repo_root / source_path)
                ).resolve()
                if node_path == abs_path:
                    affected_node_ids.add(node_id)

    return JSONResponse(
        {
            "lines": lines,
            "highlighted_lines": highlighted["lines"],
            "language": highlighted["language"],
            "line_count": len(lines),
            "has_pending_mutations": len(affected_node_ids) > 0,
            "pending_mutation_count": len(affected_node_ids),
            "affected_nodes": sorted(affected_node_ids),
            "mtime": os.path.getmtime(abs_path),
        }
    )


async def api_dirty(request: Request) -> JSONResponse:
    """GET /api/dirty - Check if graph has unsaved mutations."""
    state = _st(request)
    log = _get_mutation_log(state.graph, limit=1)
    count = log.get("count", 0)
    return JSONResponse({"dirty": count > 0, "mutation_count": count})


async def api_check_freshness(request: Request) -> JSONResponse:
    # Implements: REQ-p00006-A
    """GET /api/check-freshness - Check if spec files changed since last build."""
    import os

    state = _st(request)
    build_time = state.build_time
    spec_dirs = state.config.get("scanning", {}).get("spec", {}).get("directories", ["spec"])
    working_dir = state.repo_root

    stale_files: list[str] = []
    for spec_dir in spec_dirs:
        spec_path = Path(working_dir) / spec_dir
        if not spec_path.is_dir():
            continue
        for md_file in spec_path.rglob("*.md"):
            try:
                if os.path.getmtime(md_file) > build_time:
                    stale_files.append(str(md_file.relative_to(working_dir)))
            except OSError:
                continue

    log = _get_mutation_log(state.graph, limit=1)
    has_pending = log.get("count", 0) > 0

    return JSONResponse(
        {
            "stale": len(stale_files) > 0,
            "has_pending_mutations": has_pending,
            "stale_files": sorted(stale_files),
        }
    )


# ─────────────────────────────────────────────────────────────────
# CLI command endpoints (/api/run/*)
# ─────────────────────────────────────────────────────────────────


async def api_run_checks(request: Request) -> JSONResponse:
    """GET /api/run/checks - Run health checks and return structured report."""
    from elspais.commands.health import (
        HealthReport,
        _resolve_exclude_status,
        run_code_checks,
        run_spec_checks,
        run_test_checks,
        run_uat_checks,
    )

    state = _st(request)
    graph = state.graph
    config = state.config
    repo_root = state.repo_root

    qp = request.query_params
    spec_only = qp.get("spec_only", "false") == "true"
    code_only = qp.get("code_only", "false") == "true"
    tests_only = qp.get("tests_only", "false") == "true"
    lenient = qp.get("lenient", "false") == "true"

    report = HealthReport()

    run_all = not any([spec_only, code_only, tests_only])

    # Build a minimal args namespace for _resolve_exclude_status
    import argparse

    fake_args = argparse.Namespace()
    status_str = qp.get("status", None)
    fake_args.status = status_str.split(",") if status_str else None

    exclude_status = _resolve_exclude_status(fake_args, config=config)

    # Config checks
    if run_all:
        try:
            from elspais.commands.doctor import run_config_checks as _run_config_checks

            config_path = repo_root / ".elspais.toml"
            for check in _run_config_checks(
                config_path if config_path.exists() else None,
                config,
                repo_root,
            ):
                report.add(check)
        except Exception:
            pass

    # Spec checks
    if run_all or spec_only:
        from elspais.config import get_spec_directories

        spec_dirs = get_spec_directories(None, config)
        for check in run_spec_checks(graph, config, spec_dirs=spec_dirs):
            report.add(check)

    # Code checks
    if run_all or code_only:
        for check in run_code_checks(graph, exclude_status=exclude_status):
            report.add(check)

    # Test checks
    if run_all or tests_only:
        for check in run_test_checks(graph, exclude_status=exclude_status, config=config):
            report.add(check)

    # UAT checks
    if run_all or tests_only:
        for check in run_uat_checks(graph, exclude_status=exclude_status, config=config):
            report.add(check)

    return JSONResponse(report.to_dict(lenient=lenient))


async def api_run_summary(request: Request) -> JSONResponse:
    """GET /api/run/summary - Coverage summary data."""
    from elspais.commands.summary import _collect_coverage

    state = _st(request)
    data = _collect_coverage(state.graph, config=state.config)
    return JSONResponse(data)


async def api_run_gaps(request: Request) -> JSONResponse:
    """GET /api/run/gaps - Traceability coverage gaps."""
    import argparse

    from elspais.commands.gaps import collect_gaps
    from elspais.commands.health import _resolve_exclude_status

    state = _st(request)
    qp = request.query_params
    fake_args = argparse.Namespace()
    status_str = qp.get("status", None)
    fake_args.status = status_str.split(",") if status_str else None

    exclude_status = _resolve_exclude_status(fake_args, config=state.config)
    data = collect_gaps(state.graph, exclude_status)

    gap_type = qp.get("type", None)
    if gap_type and gap_type in ("uncovered", "untested", "unvalidated", "failing"):
        # Return single gap type
        items = getattr(data, gap_type)
        return JSONResponse({gap_type: [list(item) for item in items]})

    # Return all gap types
    result: dict[str, Any] = {}
    for gt in ("uncovered", "untested", "unvalidated", "failing"):
        result[gt] = [list(item) for item in getattr(data, gt)]
    return JSONResponse(result)


async def api_run_unlinked(request: Request) -> JSONResponse:
    """GET /api/run/unlinked - Unlinked test and code nodes."""
    from elspais.commands.unlinked import _by_file, collect_unlinked

    state = _st(request)
    data = collect_unlinked(state.graph)

    result: dict[str, Any] = {
        "tests": {
            "count": len(data.tests),
            "by_file": {
                fp: [{"id": e.node_id, "line": e.line, "label": e.label} for e in entries]
                for fp, entries in _by_file(data.tests).items()
            },
        },
        "code": {
            "count": len(data.code),
            "by_file": {
                fp: [{"id": e.node_id, "line": e.line, "label": e.label} for e in entries]
                for fp, entries in _by_file(data.code).items()
            },
        },
    }
    return JSONResponse(result)


async def api_run_analysis(request: Request) -> JSONResponse:
    """GET /api/run/analysis - Foundation analysis report."""
    from dataclasses import asdict

    from elspais.graph.analysis import NodeKind as NK
    from elspais.graph.analysis import analyze_foundations

    state = _st(request)
    qp = request.query_params

    include_kinds = {NK.REQUIREMENT, NK.ASSERTION}
    if qp.get("include_code", "false") == "true":
        include_kinds.add(NK.CODE)

    top_n = int(qp.get("top", "10"))

    weights_str = qp.get("weights", None)
    weights = (0.3, 0.2, 0.2, 0.3)
    if weights_str:
        try:
            parts = [float(x.strip()) for x in weights_str.split(",")]
            if len(parts) in (3, 4):
                weights = tuple(parts)
        except ValueError:
            pass

    report = analyze_foundations(
        state.graph,
        include_kinds=include_kinds,
        weights=weights,
        top_n=top_n,
    )

    level_filter = qp.get("level", None)
    if level_filter:
        level_upper = level_filter.upper()
        report.ranked_nodes = [ns for ns in report.ranked_nodes if ns.level == level_upper]
        report.top_foundations = [ns for ns in report.top_foundations if ns.level == level_upper]
        report.actionable_leaves = [
            ns for ns in report.actionable_leaves if ns.level == level_upper
        ]

    return JSONResponse(asdict(report))


async def api_run_trace(request: Request) -> JSONResponse:
    """GET /api/run/trace - Traceability matrix data as JSON."""
    from elspais.commands.trace import _get_node_data

    state = _st(request)
    graph = state.graph

    nodes: list[dict] = []
    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        data = _get_node_data(node, graph)
        nodes.append(data)

    return JSONResponse(nodes)


# ─────────────────────────────────────────────────────────────────
# Mutation POST endpoints
# ─────────────────────────────────────────────────────────────────


async def api_mutate_status(request: Request) -> JSONResponse:
    """POST /api/mutate/status - Change requirement status."""
    state = _st(request)
    data = await request.json()
    node_id = data.get("node_id", "")
    new_status = data.get("new_status", "")
    if not node_id or not new_status:
        return JSONResponse(
            {"success": False, "error": "node_id and new_status required"}, status_code=400
        )
    result = _mutate_change_status(state.graph, node_id, new_status)
    status_code = 200 if result.get("success") else 400
    return JSONResponse(result, status_code=status_code)


async def api_mutate_title(request: Request) -> JSONResponse:
    """POST /api/mutate/title - Update requirement title."""
    state = _st(request)
    data = await request.json()
    node_id = data.get("node_id", "")
    new_title = data.get("new_title", "")
    if not node_id or not new_title:
        return JSONResponse(
            {"success": False, "error": "node_id and new_title required"}, status_code=400
        )
    result = _mutate_update_title(state.graph, node_id, new_title)
    status_code = 200 if result.get("success") else 400
    return JSONResponse(result, status_code=status_code)


async def api_mutate_assertion(request: Request) -> JSONResponse:
    """POST /api/mutate/assertion - Update assertion text."""
    state = _st(request)
    data = await request.json()
    assertion_id = data.get("assertion_id", "")
    new_text = data.get("new_text", "")
    if not assertion_id or not new_text:
        return JSONResponse(
            {"success": False, "error": "assertion_id and new_text required"}, status_code=400
        )
    result = _mutate_update_assertion(state.graph, assertion_id, new_text)
    status_code = 200 if result.get("success") else 400
    return JSONResponse(result, status_code=status_code)


async def api_mutate_assertion_add(request: Request) -> JSONResponse:
    """POST /api/mutate/assertion/add - Add assertion to requirement."""
    state = _st(request)
    data = await request.json()
    req_id = data.get("req_id", "")
    label = data.get("label", "")
    text = data.get("text", "")
    if not req_id or not label or not text:
        return JSONResponse(
            {"success": False, "error": "req_id, label, and text required"}, status_code=400
        )
    result = _mutate_add_assertion(state.graph, req_id, label, text)
    status_code = 200 if result.get("success") else 400
    return JSONResponse(result, status_code=status_code)


async def api_mutate_assertion_delete(request: Request) -> JSONResponse:
    # Implements: REQ-d00010-A
    """POST /api/mutate/assertion/delete - Delete an assertion."""
    state = _st(request)
    data = await request.json()
    assertion_id = data.get("assertion_id", "")
    confirm = data.get("confirm", False)
    if not assertion_id:
        return JSONResponse({"success": False, "error": "assertion_id required"}, status_code=400)
    if not confirm:
        return JSONResponse({"success": False, "error": "confirm=true required"}, status_code=400)
    result = _mutate_delete_assertion(state.graph, assertion_id, confirm=True)
    status_code = 200 if result.get("success") else 400
    return JSONResponse(result, status_code=status_code)


async def api_mutate_requirement_delete(request: Request) -> JSONResponse:
    # Implements: REQ-d00010-A
    """POST /api/mutate/requirement/delete - Delete a requirement."""
    state = _st(request)
    data = await request.json()
    node_id = data.get("node_id", "")
    confirm = data.get("confirm", False)
    if not node_id:
        return JSONResponse({"success": False, "error": "node_id required"}, status_code=400)
    if not confirm:
        return JSONResponse({"success": False, "error": "confirm=true required"}, status_code=400)
    result = _mutate_delete_requirement(state.graph, node_id, confirm=True)
    status_code = 200 if result.get("success") else 400
    return JSONResponse(result, status_code=status_code)


async def api_mutate_edge(request: Request) -> JSONResponse:
    """POST /api/mutate/edge - Edge mutations (add/change_kind/change_targets/delete)."""
    state = _st(request)
    data = await request.json()
    action = data.get("action", "")
    source_id = data.get("source_id", "")
    target_id = data.get("target_id", "")

    if not action:
        return JSONResponse({"success": False, "error": "action required"}, status_code=400)
    if not source_id or not target_id:
        return JSONResponse(
            {"success": False, "error": "source_id and target_id required"}, status_code=400
        )

    if action == "add":
        edge_kind = data.get("edge_kind", "")
        if not edge_kind:
            return JSONResponse(
                {"success": False, "error": "edge_kind required for add"}, status_code=400
            )
        assertion_targets = data.get("assertion_targets")
        result = _mutate_add_edge(
            state.graph,
            source_id,
            target_id,
            edge_kind,
            assertion_targets,
            config=state.config,
        )
    elif action == "change_kind":
        new_kind = data.get("new_kind", "")
        if not new_kind:
            return JSONResponse(
                {"success": False, "error": "new_kind required for change_kind"},
                status_code=400,
            )
        result = _mutate_change_edge_kind(state.graph, source_id, target_id, new_kind)
    elif action == "change_targets":
        targets = data.get("assertion_targets", [])
        result = _mutate_change_edge_targets(state.graph, source_id, target_id, targets)
    elif action == "delete":
        result = _mutate_delete_edge(state.graph, source_id, target_id, confirm=True)
    else:
        return JSONResponse(
            {"success": False, "error": f"Unknown action: {action}"}, status_code=400
        )

    status_code = 200 if result.get("success") else 400
    return JSONResponse(result, status_code=status_code)


async def api_mutate_move_to_file(request: Request) -> JSONResponse:
    """POST /api/mutate/move-to-file - Move node to a different file."""
    state = _st(request)
    data = await request.json()
    node_id = data.get("node_id", "")
    target_file_id = data.get("target_file_id", "")
    if not node_id or not target_file_id:
        return JSONResponse(
            {"success": False, "error": "node_id and target_file_id required"},
            status_code=400,
        )
    result = _mutate_move_node_to_file(state.graph, node_id, target_file_id)
    status_code = 200 if result.get("success") else 400
    return JSONResponse(result, status_code=status_code)


async def api_mutate_rename_file(request: Request) -> JSONResponse:
    """POST /api/mutate/rename-file - Rename a FILE node."""
    state = _st(request)
    data = await request.json()
    file_id = data.get("file_id", "")
    new_relative_path = data.get("new_relative_path", "")
    if not file_id or not new_relative_path:
        return JSONResponse(
            {"success": False, "error": "file_id and new_relative_path required"},
            status_code=400,
        )
    result = _mutate_rename_file(
        state.graph,
        file_id,
        new_relative_path,
        state.repo_root,
    )
    status_code = 200 if result.get("success") else 400
    return JSONResponse(result, status_code=status_code)


async def api_mutate_undo(request: Request) -> JSONResponse:
    """POST /api/mutate/undo - Undo the most recent mutation."""
    state = _st(request)
    result = _undo_last_mutation(state.graph)
    status_code = 200 if result.get("success") else 400
    return JSONResponse(result, status_code=status_code)


# ─────────────────────────────────────────────────────────────────
# Server lifecycle endpoints
# ─────────────────────────────────────────────────────────────────


async def api_shutdown(request: Request) -> JSONResponse:
    """POST /api/shutdown - Gracefully stop the server."""
    import os
    import sys
    import threading

    print("\nShutdown requested via API.", file=sys.stderr)
    threading.Timer(0.5, lambda: os._exit(0)).start()
    return JSONResponse({"success": True, "message": "Server shutting down"})


# ─────────────────────────────────────────────────────────────────
# Persistence endpoints (REQ-o00063-F)
# ─────────────────────────────────────────────────────────────────


async def api_save(request: Request) -> JSONResponse:
    """POST /api/save - Persist mutations to spec files on disk."""
    # Implements: REQ-d00132-A
    from elspais.graph.render import render_save
    from elspais.utilities.patterns import build_resolver as _build_resolver_for_save

    state = _st(request)
    result = render_save(
        state.graph,
        state.repo_root,
        resolver=_build_resolver_for_save(state.config),
    )
    status_code = 200 if result.get("success") else 409
    if result.get("success"):
        state.build_time = time.time()
    return JSONResponse(result, status_code=status_code)


async def api_revert(request: Request) -> JSONResponse:
    """POST /api/revert - Revert all unsaved mutations by rebuilding from disk."""
    from elspais.graph.factory import build_graph

    state = _st(request)
    try:
        new_graph = build_graph(
            config=state.config,
            repo_root=state.repo_root,
            canonical_root=state.canonical_root,
        )
        state.graph = new_graph
        state.build_time = time.time()
        return JSONResponse({"success": True, "message": "Graph reverted from disk"})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


async def api_reload(request: Request) -> JSONResponse:
    # Implements: REQ-p00004-J
    """POST /api/reload - Reload graph from disk with fresh config."""
    from elspais.config import load_config
    from elspais.graph.factory import build_graph

    state = _st(request)
    try:
        config_path = Path(state.repo_root) / ".elspais.toml"
        if config_path.exists():
            state.config = load_config(config_path)

        new_graph = build_graph(
            config=state.config,
            repo_root=state.repo_root,
            canonical_root=state.canonical_root,
        )
        state.graph = new_graph
        state.build_time = time.time()
        return JSONResponse({"success": True, "message": "Graph reloaded from disk"})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)
