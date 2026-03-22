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
    _get_assertion_uat_map,
    _get_graph_status,
    _get_hierarchy,
    _get_mutation_log,
    _get_node,
    _get_requirement,
    _mutate_add_assertion,
    _mutate_add_edge,
    _mutate_add_journey,
    _mutate_change_edge_kind,
    _mutate_change_edge_targets,
    _mutate_change_status,
    _mutate_delete_assertion,
    _mutate_delete_edge,
    _mutate_delete_journey,
    _mutate_delete_requirement,
    _mutate_journey_section,
    _mutate_move_node_to_file,
    _mutate_rename_file,
    _mutate_update_assertion,
    _mutate_update_journey_field,
    _mutate_update_title,
    _query_nodes,
    _undo_last_mutation,
)


def _st(request: Request) -> Any:
    """Shorthand to get AppState from request."""
    return request.app.state.app_state


def _get_result_status(test_or_jny_node: Any) -> str | None:
    """Get aggregate result status from a TEST or USER_JOURNEY node's RESULT children."""
    statuses: list[str] = []
    for child in test_or_jny_node.iter_children():
        if child.kind == NodeKind.RESULT:
            s = (child.get_field("status", "") or "").lower()
            if s:
                statuses.append(s)
    if not statuses:
        return None
    if any(s in ("failed", "fail", "failure", "error") for s in statuses):
        return "failed"
    if all(s in ("passed", "pass", "success") for s in statuses):
        return "passed"
    return "mixed"


def _compute_link_data(
    node: Any,
) -> tuple[dict[str, dict[str, bool]], dict[str, list[dict[str, str]]]]:
    """Compute per-assertion direct link flags and REQ-level link lists.

    Returns:
        (assertion_links, req_level_links) where:
        - assertion_links: {label: {implemented: bool, tested: bool, verified: bool,
          validated: bool, accepted: bool, refined: bool}}
        - req_level_links: {dimension: [{id, title, kind}...]}
    """
    from elspais.graph.relations import EdgeKind

    # Collect assertion labels
    assertion_labels: list[str] = []
    for child in node.iter_children():
        if child.kind == NodeKind.ASSERTION:
            label = child.get_field("label", "")
            if label:
                assertion_labels.append(label)

    # Per-assertion: track which dimensions have direct assertion-level links
    # Initialize all to False
    a_links: dict[str, dict[str, bool]] = {}
    for label in assertion_labels:
        a_links[label] = {
            "implemented": False,
            "tested": False,
            "validated": False,
            "refined": False,
        }

    # Header-level links: separate lists per header badge dimension.
    # For implemented/refined: only REQ-level (no assertion_targets) links.
    # For tested/verified/validated/accepted: ALL tests/journeys (REQ-level
    # and assertion-targeted) since the header represents the whole REQ.
    r_links: dict[str, list[dict[str, Any]]] = {
        "implemented": [],
        "refined": [],
        "tested": [],
        "verified": [],
        "validated": [],
        "accepted": [],
    }
    r_seen: dict[str, set[str]] = {k: set() for k in r_links}

    def _add_link(dim: str, target: Any, **extra: Any) -> None:
        if target.id in r_seen[dim]:
            return
        r_seen[dim].add(target.id)
        entry: dict[str, Any] = {
            "id": target.id,
            "title": target.get_label() or target.id,
            "kind": target.kind.value,
        }
        entry.update(extra)
        r_links[dim].append(entry)

    def _process_edge(edge: Any, target: Any, tk: Any) -> str | None:
        """Process one outgoing edge, return the assertion_links dim or None."""
        dim = None
        if edge.kind == EdgeKind.IMPLEMENTS and tk == NodeKind.CODE:
            dim = "implemented"
        elif edge.kind == EdgeKind.VERIFIES and tk == NodeKind.TEST:
            dim = "tested"
        elif edge.kind == EdgeKind.VALIDATES and tk == NodeKind.USER_JOURNEY:
            dim = "validated"
        elif edge.kind == EdgeKind.REFINES and tk in (
            NodeKind.REQUIREMENT,
            NodeKind.CODE,
        ):
            dim = "refined"
        elif edge.kind == EdgeKind.IMPLEMENTS and tk == NodeKind.REQUIREMENT:
            dim = "implemented"

        if dim is None:
            return None

        # Assertion-level link flags
        if edge.assertion_targets:
            for label in edge.assertion_targets:
                if label in a_links:
                    a_links[label][dim] = True

        # Header-level links
        if dim in ("implemented", "refined"):
            # Only include REQ-level (no assertion_targets) for these
            if not edge.assertion_targets:
                _add_link(dim, target)
        elif dim == "tested":
            # All tests go into "tested" (test files) and "verified" (results)
            file_node = target.file_node()
            file_path = file_node.get_field("relative_path") if file_node else None
            _add_link("tested", target, file=file_path, line=target.get_field("parse_line", 0))
            result_status = _get_result_status(target)
            if result_status:
                # Find result file info
                result_file = None
                for rc in target.iter_children():
                    if rc.kind == NodeKind.RESULT:
                        rf = rc.file_node()
                        if rf:
                            result_file = rf.get_field("relative_path")
                            break
                _add_link(
                    "verified",
                    target,
                    result_status=result_status,
                    file=result_file,
                    line=0,
                )
        elif dim == "validated":
            # All journeys go into "validated" (journey files) and "accepted" (results)
            _add_link("validated", target)
            result_status = _get_result_status(target)
            if result_status:
                _add_link("accepted", target, result_status=result_status)

        return dim

    # Phase 1: REQ-level outgoing edges
    for edge in node.iter_outgoing_edges():
        target = edge.target
        _process_edge(edge, target, target.kind)

    # Phase 2: assertion-level outgoing edges (also feeds header links)
    for child in node.iter_children():
        if child.kind != NodeKind.ASSERTION:
            continue
        label = child.get_field("label", "")
        if not label or label not in a_links:
            continue
        for edge in child.iter_outgoing_edges():
            target = edge.target
            # Update assertion link flags
            tk = target.kind
            if edge.kind == EdgeKind.IMPLEMENTS and tk == NodeKind.CODE:
                a_links[label]["implemented"] = True
            elif edge.kind == EdgeKind.VERIFIES and tk == NodeKind.TEST:
                a_links[label]["tested"] = True
            elif edge.kind == EdgeKind.VALIDATES and tk == NodeKind.USER_JOURNEY:
                a_links[label]["validated"] = True
            elif edge.kind == EdgeKind.REFINES:
                a_links[label]["refined"] = True
            # Also add to header-level links (for tested/verified/validated/accepted)
            _process_edge(edge, target, tk)

    return a_links, r_links


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
    from elspais.html.generator import DIMENSION_KEYS, DIMENSION_TIPS, compute_coverage_tiers

    state = _st(request)
    node_id = request.path_params["node_id"]
    result = _get_node(state.graph, node_id)
    if "error" in result:
        return JSONResponse(result, status_code=404)

    # Enrich requirement nodes with per-dimension coverage data
    if result.get("kind") == "requirement":
        node = state.graph.find_by_id(node_id)
        if node is not None:
            tiers = compute_coverage_tiers(node, state.config)
            prefix_map = {
                "implemented": "impl",
                "tested": "tested",
                "verified": "verified",
                "uat_coverage": "uat_cov",
                "uat_verified": "uat_ver",
            }
            dims: dict[str, dict[str, str]] = {}
            for dim_key in DIMENSION_KEYS:
                prefix = prefix_map[dim_key]
                dims[dim_key] = {
                    "color": tiers.get(f"{prefix}_color", ""),
                    "tip": DIMENSION_TIPS.get(dim_key, ""),
                    "status_tip": tiers.get(f"{prefix}_tip", ""),
                }
            result["coverage_dimensions"] = dims

            # Per-assertion direct link flags + REQ-level links
            result["assertion_links"], result["req_level_links"] = _compute_link_data(node)

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
    from elspais.commands.search_cmd import compute_search

    state = _st(request)
    params = {
        "q": request.query_params.get("q", ""),
        "field": request.query_params.get("field", "all"),
        "regex": request.query_params.get("regex", "false"),
        "limit": request.query_params.get("limit", "50"),
    }
    return JSONResponse(compute_search(state.graph, state.config, params))


async def api_test_coverage(request: Request) -> JSONResponse:
    """GET /api/test-coverage/{req_id} - Per-assertion test coverage map."""
    state = _st(request)
    req_id = request.path_params["req_id"]
    result = _get_assertion_test_map(state.graph, req_id)
    if "error" in result:
        return JSONResponse(result, status_code=404)
    return JSONResponse(result)


async def api_uat_coverage(request: Request) -> JSONResponse:
    """GET /api/uat-coverage/{req_id} - Per-assertion UAT (journey) coverage map."""
    state = _st(request)
    req_id = request.path_params["req_id"]
    result = _get_assertion_uat_map(state.graph, req_id)
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

    from elspais.html.generator import compute_coverage_tiers

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
        is_changed = bool(node.get_field("is_changed", False))
        is_uncommitted = bool(node.get_field("is_uncommitted", False))
        tiers = compute_coverage_tiers(node, state.config)
        # Derive coverage tier from combined_color for filtering
        _cc = tiers.get("combined_color", "")
        coverage = (
            "full" if _cc == "green" else ("partial" if _cc in ("yellow", "orange") else "none")
        )

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
                "validation_color": tiers.get("combined_color", ""),
                "validation_tip": tiers.get("combined_tip", ""),
                "impl_color": tiers.get("impl_color", ""),
                "impl_tip": tiers.get("impl_tip", ""),
                "tested_color": tiers.get("tested_color", ""),
                "tested_tip": tiers.get("tested_tip", ""),
                "verified_color": tiers.get("verified_color", ""),
                "verified_tip": tiers.get("verified_tip", ""),
                "uat_cov_color": tiers.get("uat_cov_color", ""),
                "uat_cov_tip": tiers.get("uat_cov_tip", ""),
                "uat_ver_color": tiers.get("uat_ver_color", ""),
                "uat_ver_tip": tiers.get("uat_ver_tip", ""),
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


async def api_spec_files(request: Request) -> JSONResponse:
    """GET /api/spec-files - List SPEC-type FILE nodes."""
    from elspais.graph.GraphNode import FileType

    state = _st(request)
    files = []
    for node in state.graph.nodes_by_kind(NodeKind.FILE):
        if node.get_field("file_type") == FileType.SPEC:
            files.append(
                {
                    "id": node.id,
                    "relative_path": node.get_field("relative_path"),
                    "file_type": "SPEC",
                }
            )
    files.sort(key=lambda f: f["relative_path"])
    return JSONResponse({"files": files})


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
    from elspais.commands.health import compute_checks

    state = _st(request)
    params = dict(request.query_params)
    result = compute_checks(state.graph, state.config, params)
    return JSONResponse(result)


async def api_run_summary(request: Request) -> JSONResponse:
    """GET /api/run/summary - Coverage summary data."""
    from elspais.commands.summary import compute_summary

    state = _st(request)
    params = dict(request.query_params)
    return JSONResponse(compute_summary(state.graph, state.config, params))


async def api_run_gaps(request: Request) -> JSONResponse:
    """GET /api/run/gaps - Traceability coverage gaps."""
    from elspais.commands.gaps import compute_gaps

    state = _st(request)
    params = dict(request.query_params)
    return JSONResponse(compute_gaps(state.graph, state.config, params))


async def api_run_unlinked(request: Request) -> JSONResponse:
    """GET /api/run/unlinked - Unlinked test and code nodes."""
    from elspais.commands.unlinked import compute_unlinked

    state = _st(request)
    params = dict(request.query_params)
    return JSONResponse(compute_unlinked(state.graph, state.config, params))


async def api_run_analysis(request: Request) -> JSONResponse:
    """GET /api/run/analysis - Foundation analysis report."""
    from elspais.commands.analysis_cmd import compute_analysis

    state = _st(request)
    params = dict(request.query_params)
    return JSONResponse(compute_analysis(state.graph, state.config, params))


async def api_run_trace(request: Request) -> JSONResponse:
    """GET /api/run/trace - Traceability matrix data as JSON."""
    from elspais.commands.trace import compute_trace

    state = _st(request)
    params = dict(request.query_params)
    return JSONResponse(compute_trace(state.graph, state.config, params))


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
    # For journeys, reconstruct body to keep header line in sync
    if result.get("success"):
        node = state.graph.find_by_id(node_id)
        if node and node.kind == NodeKind.USER_JOURNEY:
            state.graph.reconstruct_journey_body(node_id)
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


async def api_next_req_id(request: Request) -> JSONResponse:
    """GET /api/next-req-id?level=<level> - Generate next available requirement ID."""
    from elspais.utilities.patterns import ParsedId, build_resolver

    state = _st(request)
    level = request.query_params.get("level", "").lower()
    if not level:
        return JSONResponse({"error": "level required"}, status_code=400)

    resolver = build_resolver(state.config)
    type_code = resolver.resolve_level(level)
    if not type_code:
        return JSONResponse({"error": f"Unknown level: {level}"}, status_code=400)

    # Find the letter alias for this type
    tdef = resolver.config.types.get(type_code)
    type_letter = tdef.aliases.get("letter", type_code) if tdef else type_code

    # Find the highest component number among existing IDs of this type
    max_component = 0
    for node in state.graph.nodes_by_kind(NodeKind.REQUIREMENT):
        parsed = resolver.parse(node.id)
        if parsed and parsed.type_code == type_code:
            try:
                num = int(parsed.component)
                if num > max_component:
                    max_component = num
            except ValueError:
                pass  # named/alphanumeric component

    next_num = max_component + 1
    comp_fmt = resolver.config.component
    if comp_fmt.style == "numeric" and comp_fmt.digits > 0 and comp_fmt.leading_zeros:
        component_str = str(next_num).zfill(comp_fmt.digits)
    else:
        component_str = str(next_num)

    # Build the canonical ID
    next_id = resolver.render(
        ParsedId(
            namespace=resolver.config.namespace,
            type_code=type_code,
            component=component_str,
            assertions=[],
            fqn="",
        ),
        form="canonical",
    )

    return JSONResponse(
        {
            "id": next_id,
            "type_code": type_code,
            "type_letter": type_letter,
            "component": component_str,
            "style": comp_fmt.style,
        }
    )


async def api_mutate_requirement_add(request: Request) -> JSONResponse:
    """POST /api/mutate/requirement/add - Create a new requirement."""
    from elspais.mcp.server import _mutate_add_requirement as _add_req
    from elspais.utilities.patterns import build_resolver

    state = _st(request)
    data = await request.json()
    req_id = data.get("req_id", "")
    title = data.get("title", "")
    level = data.get("level", "")
    file_id = data.get("file_id", "")
    if not req_id or not title or not level:
        return JSONResponse(
            {"success": False, "error": "req_id, title, and level required"},
            status_code=400,
        )

    # Validate ID format
    resolver = build_resolver(state.config)
    if not resolver.is_valid(req_id):
        return JSONResponse(
            {"success": False, "error": f"Invalid ID format: {req_id}"},
            status_code=400,
        )

    # Check for conflicts
    if state.graph.find_by_id(req_id) is not None:
        return JSONResponse(
            {"success": False, "error": f"ID already exists: {req_id}"},
            status_code=400,
        )

    result = _add_req(state.graph, req_id, title, level)
    if result.get("success") and file_id:
        # Wire CONTAINS edge directly (not via move_node_to_file which
        # creates a separate undo entry). The add_requirement undo already
        # unlinks all parents, so this is covered.
        try:
            file_node = state.graph.find_by_id(file_id)
            req_node = state.graph.find_by_id(req_id)
            if file_node and req_node:
                from elspais.graph.relations import EdgeKind

                file_node.link(req_node, EdgeKind.CONTAINS)
        except (ValueError, KeyError):
            pass
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

    # For journeys, reconstruct body to keep Validates: lines in sync
    if result.get("success"):
        source_node = state.graph.find_by_id(source_id)
        if source_node and source_node.kind == NodeKind.USER_JOURNEY:
            state.graph.reconstruct_journey_body(source_id)

    status_code = 200 if result.get("success") else 400
    return JSONResponse(result, status_code=status_code)


# ── Journey Mutations ──────────────────────────────────────────────────────


async def api_mutate_journey_field(request: Request) -> JSONResponse:
    """POST /api/mutate/journey/field - Update actor/goal/context/preamble."""
    state = _st(request)
    data = await request.json()
    node_id = data.get("node_id", "")
    field_name = data.get("field", "")
    value = data.get("value", "")
    if not node_id or not field_name:
        return JSONResponse(
            {"success": False, "error": "node_id and field required"},
            status_code=400,
        )
    result = _mutate_update_journey_field(state.graph, node_id, field_name, value)
    status_code = 200 if result.get("success") else 400
    return JSONResponse(result, status_code=status_code)


async def api_mutate_journey_section(request: Request) -> JSONResponse:
    """POST /api/mutate/journey/section - Add/update/delete a section."""
    state = _st(request)
    data = await request.json()
    node_id = data.get("node_id", "")
    action = data.get("action", "")
    name = data.get("name", "")
    if not node_id or not action or not name:
        return JSONResponse(
            {"success": False, "error": "node_id, action, and name required"},
            status_code=400,
        )
    new_name = data.get("new_name")
    content = data.get("content")
    result = _mutate_journey_section(state.graph, node_id, action, name, new_name, content)
    status_code = 200 if result.get("success") else 400
    return JSONResponse(result, status_code=status_code)


async def api_mutate_journey_add(request: Request) -> JSONResponse:
    """POST /api/mutate/journey/add - Create new journey."""
    import re

    state = _st(request)
    data = await request.json()
    journey_id = data.get("journey_id", "")
    title = data.get("title", "")
    file_id = data.get("file_id", "")
    if not journey_id or not title or not file_id:
        return JSONResponse(
            {"success": False, "error": "journey_id, title, and file_id required"},
            status_code=400,
        )

    # Validate JNY ID format (same pattern as parser: JNY-[A-Za-z0-9-]+)
    if not re.match(r"^JNY-[A-Za-z0-9-]+$", journey_id):
        return JSONResponse(
            {
                "success": False,
                "error": f"Invalid journey ID format: {journey_id}. "
                "Expected: JNY-{{Descriptor}}-{{Number}} (e.g., JNY-LOGIN-01)",
            },
            status_code=400,
        )

    # Check for conflicts
    if state.graph.find_by_id(journey_id) is not None:
        return JSONResponse(
            {"success": False, "error": f"ID already exists: {journey_id}"},
            status_code=400,
        )

    result = _mutate_add_journey(state.graph, journey_id, title, file_id)
    status_code = 200 if result.get("success") else 400
    return JSONResponse(result, status_code=status_code)


async def api_mutate_journey_delete(request: Request) -> JSONResponse:
    """POST /api/mutate/journey/delete - Delete a journey."""
    state = _st(request)
    data = await request.json()
    node_id = data.get("node_id", "")
    confirm = data.get("confirm", False)
    if not node_id:
        return JSONResponse(
            {"success": False, "error": "node_id required"},
            status_code=400,
        )
    result = _mutate_delete_journey(state.graph, node_id, confirm=confirm)
    status_code = 200 if result.get("success") else 400
    return JSONResponse(result, status_code=status_code)


async def api_journey_files(request: Request) -> JSONResponse:
    """GET /api/journey-files - List files that contain or can contain journeys."""
    from elspais.graph.relations import EdgeKind

    state = _st(request)
    g = state.graph
    files: list[dict[str, str]] = []
    seen: set[str] = set()

    # Collect all FILE nodes that contain journeys or are in journey/spec dirs
    for node in g.nodes_by_kind(NodeKind.FILE):
        file_id = node.id
        if file_id in seen:
            continue
        # Include if it contains a USER_JOURNEY or is a SPEC/JOURNEY file
        file_type = node.get_field("file_type")
        has_journey = any(
            e.target.kind == NodeKind.USER_JOURNEY
            for e in node.iter_outgoing_edges()
            if e.kind == EdgeKind.CONTAINS
        )
        if has_journey or (file_type and file_type.value in ("SPEC", "JOURNEY")):
            seen.add(file_id)
            files.append(
                {
                    "id": file_id,
                    "path": node.get_field("relative_path", ""),
                    "has_journeys": has_journey,
                }
            )

    files.sort(key=lambda f: f["path"])
    return JSONResponse({"files": files})


async def api_mutate_move_to_file(request: Request) -> JSONResponse:
    """POST /api/mutate/move-to-file - Move node to a different file.

    If the target file does not exist yet, validates the path against scanning
    config, creates the empty file on disk, rebuilds the graph, then performs
    the move mutation.
    """
    state = _st(request)
    data = await request.json()
    node_id = data.get("node_id", "")
    target_file_id = data.get("target_file_id", "")
    if not node_id or not target_file_id:
        return JSONResponse(
            {"success": False, "error": "node_id and target_file_id required"},
            status_code=400,
        )

    # Check if the target file exists on disk; if not, create it
    if target_file_id.startswith("file:"):
        relative_path = target_file_id[5:]  # strip "file:" prefix
    else:
        relative_path = target_file_id

    # Reject path traversal and absolute paths
    if ".." in relative_path.split("/") or relative_path.startswith("/"):
        return JSONResponse(
            {"success": False, "error": "Invalid path: must not contain '..' or be absolute"},
            status_code=400,
        )

    target_path = Path(state.repo_root) / relative_path
    if not target_path.resolve().is_relative_to(Path(state.repo_root).resolve()):
        return JSONResponse(
            {"success": False, "error": "Path escapes repository root"},
            status_code=400,
        )

    if not target_path.exists():
        # Validate path against scanning config
        error = _validate_new_spec_path(relative_path, state.config)
        if error:
            return JSONResponse(
                {"success": False, "error": error},
                status_code=400,
            )
        # Create the empty file and parent directories
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text("", encoding="utf-8")
        # Create a FILE node in the graph (empty files aren't picked up by rebuild)
        _register_new_file_node(state, target_file_id, relative_path, target_path)

    result = _mutate_move_node_to_file(state.graph, node_id, target_file_id)
    status_code = 200 if result.get("success") else 400
    return JSONResponse(result, status_code=status_code)


def _validate_new_spec_path(relative_path: str, config: dict[str, Any]) -> str | None:
    """Validate that a new file path is under a configured spec directory.

    Returns an error message string if invalid, or None if valid.
    """
    import fnmatch as _fnmatch
    from pathlib import PurePosixPath

    from elspais.config import get_ignore_config
    from elspais.config.schema import ElspaisConfig

    typed_config = ElspaisConfig.model_validate(config)
    spec_cfg = typed_config.scanning.spec
    spec_dirs = list(spec_cfg.directories)
    file_patterns = list(spec_cfg.file_patterns)
    skip_dirs = list(spec_cfg.skip_dirs)
    skip_files = list(spec_cfg.skip_files)

    parts = PurePosixPath(relative_path).parts
    if not parts:
        return "Path is empty"

    # Check that path starts with a configured spec directory
    under_spec_dir = False
    for spec_dir in spec_dirs:
        spec_parts = PurePosixPath(spec_dir).parts
        if parts[: len(spec_parts)] == spec_parts:
            under_spec_dir = True
            break
    if not under_spec_dir:
        return f"Path '{relative_path}' is not under any configured spec directory ({spec_dirs})"

    # Check filename matches file_patterns
    filename = parts[-1]
    matches_pattern = any(_fnmatch.fnmatch(filename, pat) for pat in file_patterns)
    if not matches_pattern:
        return f"Filename '{filename}' does not match any spec file pattern ({file_patterns})"

    # Check skip_dirs
    for part in parts[:-1]:
        if any(_fnmatch.fnmatch(part, pat) for pat in skip_dirs):
            return f"Path contains skipped directory '{part}'"

    # Check skip_files
    if any(_fnmatch.fnmatch(filename, pat) for pat in skip_files):
        return f"Filename '{filename}' matches a skip pattern"

    # Check IgnoreConfig
    ignore_cfg = get_ignore_config(config)
    if ignore_cfg.should_ignore(relative_path, scope="spec"):
        return f"Path '{relative_path}' is ignored by ignore configuration"

    return None


def _register_new_file_node(
    state: Any,
    file_id: str,
    relative_path: str,
    absolute_path: Path,
) -> None:
    """Create and register a FILE node for a newly-created empty spec file.

    Inserts the node directly into the graph's index and the federated
    ownership map so that ``move_node_to_file`` can find it without a
    full rebuild (which would skip empty files anyway).
    """
    from elspais.graph import GraphNode
    from elspais.graph.GraphNode import FileType

    node = GraphNode(
        id=file_id,
        kind=NodeKind.FILE,
        label=absolute_path.name,
    )
    node._content = {
        "file_type": FileType.SPEC,
        "absolute_path": str(absolute_path.resolve()),
        "relative_path": relative_path,
        "repo": None,
        "git_branch": None,
        "git_commit": None,
    }

    # Register in the sub-graph that owns the node being moved
    # For a single-repo setup this is the root repo's TraceGraph.
    # We register in the root repo since new spec files belong there.
    from elspais.graph.federated import FederatedGraph

    graph = state.graph
    if isinstance(graph, FederatedGraph):
        root_repo = graph._root_repo
        entry = graph._repos[root_repo]
        if entry.graph is not None:
            entry.graph._index[file_id] = node
            entry.graph._roots.append(node)
        graph._ownership[file_id] = root_repo
    else:
        # Direct TraceGraph (shouldn't happen with current server, but safe)
        graph._index[file_id] = node
        graph._roots.append(node)


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
