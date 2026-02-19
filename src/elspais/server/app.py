# Implements: REQ-p00006-B
# Implements: REQ-d00010-A, REQ-d00010-F, REQ-d00010-G
"""elspais.server.app - Flask app factory and REST API routes.

This is a THIN REST wrapper — all logic delegates to pure functions
in ``elspais.mcp.server``. No graph logic is duplicated here.

State pattern matches the MCP server:
    _state = {"graph": graph, "working_dir": repo_root,
              "config": config, "build_time": time.time()}
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template, request
from flask_cors import CORS

from elspais.graph import NodeKind
from elspais.graph.builder import TraceGraph
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
    _mutate_change_status,
    _mutate_delete_edge,
    _mutate_update_assertion,
    _mutate_update_title,
    _query_nodes,
    _search,
    _undo_last_mutation,
)


def create_app(
    repo_root: Path,
    graph: TraceGraph,
    config: dict[str, Any],
) -> Flask:
    """Create the Flask application with REST API routes.

    REQ-d00010-A: Flask application with factory function.
    REQ-d00010-F: CORS enabled for cross-origin requests.
    REQ-d00010-G: Static file serving from templates/static/.

    Args:
        repo_root: Repository root path.
        graph: Pre-built TraceGraph instance.
        config: elspais configuration dict.

    Returns:
        Configured Flask application.
    """
    # Resolve template and static directories
    templates_dir = Path(__file__).parent.parent / "html" / "templates"
    static_dir = templates_dir / "static"

    app = Flask(
        __name__,
        template_folder=str(templates_dir),
        static_folder=str(static_dir) if static_dir.exists() else None,
    )

    # Always reload templates from disk (editable installs change files in-place)
    app.config["TEMPLATES_AUTO_RELOAD"] = True

    # REQ-d00010-F: CORS support
    CORS(app)

    # Disable browser caching for dev server (ensures fresh content on reload)
    @app.after_request
    def _no_cache(response):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

    # Build whitelist of allowed directories for file serving.
    # Includes repo root + associated repo roots discovered via config.
    repo_resolved = repo_root.resolve()
    allowed_roots: list[Path] = [repo_resolved]
    try:
        from elspais.associates import get_associate_spec_directories

        spec_dirs, _ = get_associate_spec_directories(config, repo_root)
        for spec_dir in spec_dirs:
            # Walk up from spec dir to find .elspais.toml (the repo root)
            candidate = spec_dir.resolve()
            while candidate != candidate.parent:
                if (candidate / ".elspais.toml").exists():
                    if candidate not in allowed_roots:
                        allowed_roots.append(candidate)
                    break
                candidate = candidate.parent
    except Exception:
        pass  # Associates not configured; repo root is the only allowed dir

    # State pattern matching MCP server
    _state: dict[str, Any] = {
        "graph": graph,
        "working_dir": repo_root,
        "config": config,
        "build_time": time.time(),
    }

    # ─────────────────────────────────────────────────────────────────
    # Template route
    # ─────────────────────────────────────────────────────────────────

    @app.route("/")
    def index():
        """Serve the trace-edit UI template with enriched context.

        Reuses HTMLGenerator methods to compute stats, journeys,
        and other view context for the unified template.
        """
        try:
            from elspais.html.generator import HTMLGenerator
            from elspais.html.highlighting import get_pygments_css

            gen = HTMLGenerator(_state["graph"], base_path=str(_state["working_dir"]))
            gen._annotate_git_state()
            gen._annotate_coverage()
            stats = gen._compute_stats()
            journeys = gen._collect_journeys()
            stats.journey_count = len(journeys)
            statuses = sorted(gen._collect_unique_values("status"))
            topics = sorted(gen._collect_unique_values("topic"))

            return render_template(
                "trace_unified.html.j2",
                mode="edit",
                stats=stats,
                journeys=journeys,
                statuses=statuses,
                topics=topics,
                version=gen.version,
                base_path=str(_state["working_dir"]),
                pygments_css=get_pygments_css(),
                pygments_css_dark=get_pygments_css(style="monokai", scope=".dark-theme .highlight"),
                # Empty dicts — edit mode uses live API, not embedded data
                node_index={},
                coverage_index={},
                status_data={},
            )
        except Exception:
            return jsonify({"message": "trace_unified.html.j2 template not yet available"}), 200

    # ─────────────────────────────────────────────────────────────────
    # Read-only GET endpoints
    # ─────────────────────────────────────────────────────────────────

    @app.route("/api/status")
    def api_status():
        """GET /api/status - Graph status with associated repos info."""
        result = _get_graph_status(_state["graph"])
        # Include associated repos metadata for badge display
        try:
            from elspais.associates import load_associates_config

            assoc_config = load_associates_config(_state["config"], _state["working_dir"])
            result["associated_repos"] = [
                {"code": a.code, "name": a.name} for a in assoc_config.associates if a.enabled
            ]
        except Exception:
            result["associated_repos"] = []
        return jsonify(result)

    @app.route("/api/requirement/<req_id>")
    def api_requirement(req_id: str):
        """GET /api/requirement/<req_id> - Full requirement details.

        Thin wrapper: calls _get_node() internally but guards kind==requirement.
        """
        result = _get_requirement(_state["graph"], req_id)
        if "error" in result:
            return jsonify(result), 404
        return jsonify(result)

    @app.route("/api/node/<node_id>")
    def api_node(node_id: str):
        """GET /api/node/<node_id> - Full details for any node kind."""
        result = _get_node(_state["graph"], node_id)
        if "error" in result:
            return jsonify(result), 404
        return jsonify(result)

    @app.route("/api/query")
    def api_query():
        """GET /api/query - Combined property + keyword filter endpoint.

        Query parameters:
            kind: Filter by NodeKind value (requirement, journey, test, etc.)
            keywords: Comma-separated keywords
            match_all: true (default) = AND, false = OR
            level: Property filter (PRD, OPS, DEV)
            status: Property filter (active, draft, passed, failed, etc.)
            actor: Property filter (journey actor)
            limit: Max results (default 50)
        """
        kind = request.args.get("kind")
        keywords_str = request.args.get("keywords", "")
        keywords = (
            [k.strip() for k in keywords_str.split(",") if k.strip()] if keywords_str else None
        )
        match_all = request.args.get("match_all", "true").lower() != "false"
        limit = int(request.args.get("limit", "50"))
        # Collect property filters from known param names
        filters: dict[str, str] = {}
        for prop in ("level", "status", "actor"):
            val = request.args.get(prop)
            if val:
                filters[prop] = val
        return jsonify(
            _query_nodes(_state["graph"], kind, keywords, match_all, filters or None, limit)
        )

    @app.route("/api/hierarchy/<req_id>")
    def api_hierarchy(req_id: str):
        """GET /api/hierarchy/<req_id> - Ancestors and children."""
        result = _get_hierarchy(_state["graph"], req_id)
        if "error" in result:
            return jsonify(result), 404
        return jsonify(result)

    @app.route("/api/search")
    def api_search():
        """GET /api/search?q=<query>&field=<field> - Search requirements."""
        query = request.args.get("q", "")
        field = request.args.get("field", "all")
        if not query:
            return jsonify([])
        return jsonify(_search(_state["graph"], query, field))

    @app.route("/api/test-coverage/<req_id>")
    def api_test_coverage(req_id: str):
        """GET /api/test-coverage/<req_id> - Per-assertion test coverage map."""
        result = _get_assertion_test_map(_state["graph"], req_id)
        if "error" in result:
            return jsonify(result), 404
        return jsonify(result)

    @app.route("/api/code-coverage/<req_id>")
    def api_code_coverage(req_id: str):
        """GET /api/code-coverage/<req_id> - Per-assertion code implementation map."""
        result = _get_assertion_code_map(_state["graph"], req_id)
        if "error" in result:
            return jsonify(result), 404
        return jsonify(result)

    @app.route("/api/tree-data")
    def api_tree_data():
        """GET /api/tree-data - Build tree data for nav panel.

        Produces a flat list of tree nodes with coverage, git state,
        and associated flags to enable filtering in edit mode.
        Tests/results are NOT included — they live in per-assertion
        validation panels instead.
        """
        import re

        from elspais.html.generator import compute_validation_color

        g = _state["graph"]
        rows: list[dict[str, Any]] = []
        visited: set[tuple[str, str]] = set()  # (node_id, parent_id) dedup

        def _is_associated(node) -> bool:
            """Check if a requirement is from an associated/sponsor repo."""
            # Definitive: ID pattern (e.g., REQ-CAL-p00001)
            if re.match(r"^REQ-[A-Z]{2,4}-[a-z]", node.id):
                return True
            # Definitive: repo_prefix metric set by annotator
            rp = node.get_metric("repo_prefix", "")
            if rp and rp != "CORE":
                return True
            # Definitive: source location from a different repo
            if node.source and node.source.repo:
                return True
            # Explicit field marker
            return bool(node.get_field("associated", False))

        def _get_repo_prefix(node) -> str:
            """Get repo prefix for a node."""
            # Check annotated metric (non-CORE values are definitive)
            rp = node.get_metric("repo_prefix", "")
            if rp and rp != "CORE":
                return rp
            # Check source location repo marker
            if node.source and node.source.repo:
                return node.source.repo
            # Extract from ID pattern (e.g., REQ-CAL-d00001 → CAL)
            m = re.match(r"^REQ-([A-Z]{2,4})-[a-z]", node.id)
            if m:
                return m.group(1)
            return rp or "CORE"

        def _walk(node, depth: int, parent_id: str | None) -> None:
            """DFS traversal producing flat row list (requirements only)."""
            if node.kind != NodeKind.REQUIREMENT:
                return

            visit_key = (node.id, parent_id or "__root__")
            if visit_key in visited:
                return
            visited.add(visit_key)

            # Collect assertion letters
            assertions = []
            for child in node.iter_children():
                if child.kind == NodeKind.ASSERTION:
                    label = child.get_field("label", "")
                    if label:
                        assertions.append(label)

            # Check for requirement children only
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

            # Recurse into requirement children only
            for child in node.iter_children():
                if child.kind == NodeKind.REQUIREMENT:
                    _walk(child, depth + 1, node.id)

        # Start from roots
        for root in g.iter_roots():
            if root.kind == NodeKind.REQUIREMENT:
                _walk(root, 0, None)

        # Add USER_JOURNEY nodes as root-level rows
        for node in g.nodes_by_kind(NodeKind.USER_JOURNEY):
            source_file = node.source.path if node.source else ""
            source_line = node.source.line if node.source else 0
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

        return jsonify(rows)

    @app.route("/api/file-content")
    def api_file_content():
        """GET /api/file-content?path=<path> - Read a file from disk.

        The path may be relative (to the repo root) or absolute (for
        associated repo files outside the main repo tree).

        Returns the file content as an array of lines with metadata about
        whether the file has pending in-memory mutations that would change
        it on save.
        """
        import os

        from elspais.graph.mutations import MutationLog
        from elspais.html.highlighting import highlight_file_content

        rel_path = request.args.get("path", "")
        if not rel_path:
            return jsonify({"error": "path parameter required"}), 400

        # Resolve to absolute path; if the path is already absolute
        # (e.g. from an associated repo outside the main repo), use it
        # directly; otherwise join with working_dir.
        p = Path(rel_path)
        abs_path = (p if p.is_absolute() else (_state["working_dir"] / rel_path)).resolve()

        # Security: path must be under repo root or an allowed associate dir
        if not any(abs_path.is_relative_to(root) for root in allowed_roots):
            return jsonify({"error": "path outside repository"}), 403

        if not abs_path.exists():
            return jsonify({"error": f"file not found: {rel_path}"}), 404

        try:
            content = abs_path.read_text(encoding="utf-8")
        except Exception as e:
            return jsonify({"error": f"cannot read file: {e}"}), 500

        lines = content.splitlines()

        # Syntax highlighting via shared module
        highlighted = highlight_file_content(rel_path, content)

        # Check which nodes in the mutation log are sourced from this file
        g = _state["graph"]
        mutation_log: MutationLog = g._mutation_log
        affected_node_ids: set[str] = set()
        for entry in mutation_log.iter_entries():
            # Each entry has node_id in before_state or after_state
            node_id = entry.after_state.get("node_id", "") if entry.after_state else ""
            if not node_id:
                node_id = entry.before_state.get("node_id", "") if entry.before_state else ""
            if not node_id:
                continue
            node = g.find_by_id(node_id)
            if node and node.source and node.source.path:
                source_path = Path(node.source.path)
                node_path = (
                    source_path
                    if source_path.is_absolute()
                    else (_state["working_dir"] / source_path)
                ).resolve()
                if node_path == abs_path:
                    affected_node_ids.add(node_id)

        return jsonify(
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

    @app.route("/api/dirty")
    def api_dirty():
        """GET /api/dirty - Check if graph has unsaved mutations."""
        log = _get_mutation_log(_state["graph"], limit=1)
        count = log.get("count", 0)
        return jsonify({"dirty": count > 0, "mutation_count": count})

    # ─────────────────────────────────────────────────────────────────
    # Mutation POST endpoints
    # ─────────────────────────────────────────────────────────────────

    @app.route("/api/mutate/status", methods=["POST"])
    def api_mutate_status():
        """POST /api/mutate/status - Change requirement status."""
        data = request.get_json(force=True)
        node_id = data.get("node_id", "")
        new_status = data.get("new_status", "")
        if not node_id or not new_status:
            return jsonify({"success": False, "error": "node_id and new_status required"}), 400
        result = _mutate_change_status(_state["graph"], node_id, new_status)
        status_code = 200 if result.get("success") else 400
        return jsonify(result), status_code

    @app.route("/api/mutate/title", methods=["POST"])
    def api_mutate_title():
        """POST /api/mutate/title - Update requirement title."""
        data = request.get_json(force=True)
        node_id = data.get("node_id", "")
        new_title = data.get("new_title", "")
        if not node_id or not new_title:
            return jsonify({"success": False, "error": "node_id and new_title required"}), 400
        result = _mutate_update_title(_state["graph"], node_id, new_title)
        status_code = 200 if result.get("success") else 400
        return jsonify(result), status_code

    @app.route("/api/mutate/assertion", methods=["POST"])
    def api_mutate_assertion():
        """POST /api/mutate/assertion - Update assertion text."""
        data = request.get_json(force=True)
        assertion_id = data.get("assertion_id", "")
        new_text = data.get("new_text", "")
        if not assertion_id or not new_text:
            return jsonify({"success": False, "error": "assertion_id and new_text required"}), 400
        result = _mutate_update_assertion(_state["graph"], assertion_id, new_text)
        status_code = 200 if result.get("success") else 400
        return jsonify(result), status_code

    @app.route("/api/mutate/assertion/add", methods=["POST"])
    def api_mutate_assertion_add():
        """POST /api/mutate/assertion/add - Add assertion to requirement."""
        data = request.get_json(force=True)
        req_id = data.get("req_id", "")
        label = data.get("label", "")
        text = data.get("text", "")
        if not req_id or not label or not text:
            return jsonify({"success": False, "error": "req_id, label, and text required"}), 400
        result = _mutate_add_assertion(_state["graph"], req_id, label, text)
        status_code = 200 if result.get("success") else 400
        return jsonify(result), status_code

    @app.route("/api/mutate/edge", methods=["POST"])
    def api_mutate_edge():
        """POST /api/mutate/edge - Edge mutations (add/change_kind/delete).

        The ``action`` field in the JSON body determines the operation:
        - "add": requires source_id, target_id, edge_kind
        - "change_kind": requires source_id, target_id, new_kind
        - "delete": requires source_id, target_id
        """
        data = request.get_json(force=True)
        action = data.get("action", "")
        source_id = data.get("source_id", "")
        target_id = data.get("target_id", "")

        if not action:
            return jsonify({"success": False, "error": "action required"}), 400
        if not source_id or not target_id:
            return jsonify({"success": False, "error": "source_id and target_id required"}), 400

        if action == "add":
            edge_kind = data.get("edge_kind", "")
            if not edge_kind:
                return jsonify({"success": False, "error": "edge_kind required for add"}), 400
            assertion_targets = data.get("assertion_targets")
            result = _mutate_add_edge(
                _state["graph"], source_id, target_id, edge_kind, assertion_targets
            )
        elif action == "change_kind":
            new_kind = data.get("new_kind", "")
            if not new_kind:
                return (
                    jsonify({"success": False, "error": "new_kind required for change_kind"}),
                    400,
                )
            result = _mutate_change_edge_kind(_state["graph"], source_id, target_id, new_kind)
        elif action == "delete":
            result = _mutate_delete_edge(_state["graph"], source_id, target_id, confirm=True)
        else:
            return jsonify({"success": False, "error": f"Unknown action: {action}"}), 400

        status_code = 200 if result.get("success") else 400
        return jsonify(result), status_code

    @app.route("/api/mutate/undo", methods=["POST"])
    def api_mutate_undo():
        """POST /api/mutate/undo - Undo the most recent mutation."""
        result = _undo_last_mutation(_state["graph"])
        status_code = 200 if result.get("success") else 400
        return jsonify(result), status_code

    # ─────────────────────────────────────────────────────────────────
    # Server lifecycle endpoints
    # ─────────────────────────────────────────────────────────────────

    # Heartbeat tracking: server shuts down if no browser pings within timeout.
    # Only activates after the first heartbeat (so the server survives startup).
    _heartbeat: dict[str, float] = {"last": 0.0, "active": False}
    _HEARTBEAT_TIMEOUT = 30  # seconds without a ping before shutdown

    @app.route("/api/heartbeat", methods=["POST"])
    def api_heartbeat():
        """POST /api/heartbeat - Browser keep-alive ping."""
        import sys

        _heartbeat["last"] = time.time()
        if not _heartbeat["active"]:
            _heartbeat["active"] = True
            print("[heartbeat] Browser connected — auto-shutdown enabled.", file=sys.stderr)
            _start_heartbeat_monitor()
        return jsonify({"ok": True})

    def _start_heartbeat_monitor():
        """Background thread that exits the server when heartbeats stop."""
        import os
        import sys
        import threading

        def _monitor():
            while True:
                time.sleep(5)
                elapsed = time.time() - _heartbeat["last"]
                if elapsed > _HEARTBEAT_TIMEOUT:
                    print(
                        f"\n[heartbeat] No browser ping for {int(elapsed)}s "
                        f"(timeout: {_HEARTBEAT_TIMEOUT}s) — shutting down.",
                        file=sys.stderr,
                    )
                    os._exit(0)
                elif elapsed > _HEARTBEAT_TIMEOUT / 2:
                    print(
                        f"[heartbeat] No browser ping for {int(elapsed)}s "
                        f"(shutdown in {_HEARTBEAT_TIMEOUT - int(elapsed)}s)",
                        file=sys.stderr,
                    )

        t = threading.Thread(target=_monitor, daemon=True)
        t.start()

    @app.route("/api/shutdown", methods=["POST"])
    def api_shutdown():
        """POST /api/shutdown - Gracefully stop the server."""
        import os
        import sys
        import threading

        print("\nShutdown requested via API.", file=sys.stderr)
        # Respond before exiting so the caller gets confirmation
        response = jsonify({"success": True, "message": "Server shutting down"})
        threading.Timer(0.5, lambda: os._exit(0)).start()
        return response

    # ─────────────────────────────────────────────────────────────────
    # Persistence endpoints (REQ-o00063-F)
    # ─────────────────────────────────────────────────────────────────

    @app.route("/api/save", methods=["POST"])
    def api_save():
        """POST /api/save - Persist mutations to spec files on disk."""
        from elspais.server.persistence import replay_mutations_to_disk

        result = replay_mutations_to_disk(
            _state["graph"],
            _state["working_dir"],
            build_time=_state.get("build_time"),
        )
        status_code = 200 if result.get("success") else 409
        # Update build_time after successful save
        if result.get("success"):
            _state["build_time"] = time.time()
        return jsonify(result), status_code

    @app.route("/api/revert", methods=["POST"])
    def api_revert():
        """POST /api/revert - Revert all unsaved mutations by rebuilding from disk."""
        from elspais.graph.factory import build_graph

        try:
            new_graph = build_graph(
                config=_state["config"],
                repo_root=_state["working_dir"],
            )
            _state["graph"] = new_graph
            _state["build_time"] = time.time()
            return jsonify({"success": True, "message": "Graph reverted from disk"})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/reload", methods=["POST"])
    def api_reload():
        """POST /api/reload - Reload graph from disk (same as revert)."""
        from elspais.graph.factory import build_graph

        try:
            new_graph = build_graph(
                config=_state["config"],
                repo_root=_state["working_dir"],
            )
            _state["graph"] = new_graph
            _state["build_time"] = time.time()
            return jsonify({"success": True, "message": "Graph reloaded from disk"})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    return app
