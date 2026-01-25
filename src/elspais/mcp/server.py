"""
elspais.mcp.server - MCP server implementation.

Creates and runs the MCP server exposing elspais functionality.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from mcp.server.fastmcp import FastMCP

    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    FastMCP = None

from elspais.mcp.context import WorkspaceContext
from elspais.mcp.serializers import (
    serialize_content_rule,
    serialize_requirement,
    serialize_requirement_summary,
    serialize_violation,
)


def create_server(working_dir: Optional[Path] = None) -> "FastMCP":
    """
    Create and configure the MCP server.

    Args:
        working_dir: Working directory for finding .elspais.toml
                    Defaults to current working directory

    Returns:
        Configured FastMCP server instance

    Raises:
        ImportError: If MCP dependencies are not installed
    """
    if not MCP_AVAILABLE:
        raise ImportError(
            "MCP dependencies not installed. " "Install with: pip install elspais[mcp]"
        )

    if working_dir is None:
        working_dir = Path.cwd()

    # Initialize workspace context
    ctx = WorkspaceContext.from_directory(working_dir)

    # Create FastMCP server
    mcp = FastMCP(
        name="elspais",
    )

    # Register resources
    _register_resources(mcp, ctx)

    # Register tools
    _register_tools(mcp, ctx)

    return mcp


def _register_resources(mcp: "FastMCP", ctx: WorkspaceContext) -> None:
    """Register MCP resources."""

    @mcp.resource("requirements://all")
    def list_all_requirements() -> str:
        """
        Get list of all requirements in the workspace.

        Returns summary information for each requirement including
        ID, title, level, status, and assertion count.
        """
        import json

        requirements = ctx.get_requirements()
        return json.dumps(
            {
                "count": len(requirements),
                "requirements": [
                    serialize_requirement_summary(req) for req in requirements.values()
                ],
            },
            indent=2,
        )

    @mcp.resource("requirements://{req_id}")
    def get_requirement_resource(req_id: str) -> str:
        """
        Get detailed information about a specific requirement.

        Returns full requirement data including body, assertions,
        implements references, and location.
        """
        import json

        req = ctx.get_requirement(req_id)
        if req is None:
            return json.dumps({"error": f"Requirement {req_id} not found"})
        return json.dumps(serialize_requirement(req), indent=2)

    @mcp.resource("requirements://level/{level}")
    def get_requirements_by_level(level: str) -> str:
        """Get all requirements of a specific level (PRD, OPS, DEV)."""
        import json

        requirements = ctx.get_requirements()
        filtered = [r for r in requirements.values() if r.level.upper() == level.upper()]
        return json.dumps(
            {
                "level": level,
                "count": len(filtered),
                "requirements": [serialize_requirement_summary(r) for r in filtered],
            },
            indent=2,
        )

    @mcp.resource("content-rules://list")
    def list_content_rules() -> str:
        """List all configured content rule files."""
        import json

        rules = ctx.get_content_rules()
        return json.dumps(
            {
                "count": len(rules),
                "rules": [
                    {
                        "file": str(r.file_path),
                        "title": r.title,
                        "type": r.type,
                        "applies_to": r.applies_to,
                    }
                    for r in rules
                ],
            },
            indent=2,
        )

    @mcp.resource("content-rules://{filename}")
    def get_content_rule(filename: str) -> str:
        """
        Get content of a content rule markdown file.

        Content rules are documentation files that describe
        requirement formats and authoring guidelines.
        """
        import json

        rules = ctx.get_content_rules()
        for rule in rules:
            if rule.file_path.name == filename or str(rule.file_path).endswith(filename):
                return json.dumps(serialize_content_rule(rule), indent=2)
        return json.dumps({"error": f"Content rule not found: {filename}"})

    @mcp.resource("config://current")
    def get_current_config() -> str:
        """Get the current elspais configuration."""
        import json

        return json.dumps(ctx.config, indent=2, default=str)


def _register_tools(mcp: "FastMCP", ctx: WorkspaceContext) -> None:
    """Register MCP tools."""

    @mcp.tool()
    def validate(skip_rules: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Validate all requirements in the workspace.

        Checks format, hierarchy relationships, hashes, and links.
        Returns violations grouped by severity.

        Args:
            skip_rules: Optional list of rule names to skip
        """
        from elspais.core.rules import RuleEngine, RulesConfig, Severity

        requirements = ctx.get_requirements(force_refresh=True)
        rules_config = RulesConfig.from_dict(ctx.config.get("rules", {}))
        engine = RuleEngine(rules_config)

        violations = engine.validate(requirements)

        # Filter by skip_rules
        if skip_rules:
            violations = [v for v in violations if v.rule_name not in skip_rules]

        errors = [v for v in violations if v.severity == Severity.ERROR]
        warnings = [v for v in violations if v.severity == Severity.WARNING]

        return {
            "valid": len(errors) == 0,
            "errors": [serialize_violation(v) for v in errors],
            "warnings": [serialize_violation(v) for v in warnings],
            "summary": (
                f"{len(errors)} errors, {len(warnings)} warnings "
                f"in {len(requirements)} requirements"
            ),
        }

    @mcp.tool()
    def parse_requirement(text: str, file_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Parse requirement text and extract structured data.

        Args:
            text: Markdown text containing one or more requirements
            file_path: Optional source file path for location info
        """
        from elspais.core.parser import RequirementParser
        from elspais.core.patterns import PatternConfig

        pattern_config = PatternConfig.from_dict(ctx.config.get("patterns", {}))
        parser = RequirementParser(pattern_config)
        path = Path(file_path) if file_path else None
        requirements = parser.parse_text(text, file_path=path)

        return {
            "count": len(requirements),
            "requirements": {
                req_id: serialize_requirement(req) for req_id, req in requirements.items()
            },
        }

    @mcp.tool()
    def search(
        query: str,
        field: str = "all",
        regex: bool = False,
    ) -> Dict[str, Any]:
        """
        Search requirements by pattern.

        Args:
            query: Search query string
            field: Field to search - "all", "id", "title", "body", "assertions"
            regex: If true, treat query as regex pattern
        """
        results = ctx.search_requirements(query, field, regex)
        return {
            "count": len(results),
            "query": query,
            "field": field,
            "requirements": [serialize_requirement_summary(r) for r in results],
        }

    @mcp.tool()
    def get_requirement(req_id: str) -> Dict[str, Any]:
        """
        Get complete details for a single requirement.

        Args:
            req_id: The requirement ID (e.g., "REQ-p00001")
        """
        req = ctx.get_requirement(req_id)
        if req is None:
            return {"error": f"Requirement {req_id} not found"}
        return serialize_requirement(req)

    @mcp.tool()
    def analyze(analysis_type: str = "hierarchy") -> Dict[str, Any]:
        """
        Analyze requirement structure.

        Args:
            analysis_type: One of "hierarchy", "orphans", "coverage"
        """
        requirements = ctx.get_requirements()

        if analysis_type == "hierarchy":
            return _analyze_hierarchy(requirements)
        elif analysis_type == "orphans":
            return _analyze_orphans(requirements)
        elif analysis_type == "coverage":
            return _analyze_coverage(requirements)
        else:
            return {"error": f"Unknown analysis type: {analysis_type}"}

    @mcp.tool()
    def get_graph_status() -> Dict[str, Any]:
        """
        Get current traceability graph status and statistics.

        Returns information about the graph cache state, including
        whether it's stale, which files have changed, node counts
        by type, and when the graph was last built.

        This is useful for checking if the graph needs refresh
        and for understanding the graph structure.
        """
        from elspais.core.graph import NodeKind

        is_stale = ctx.is_graph_stale()
        stale_files = ctx.get_stale_files()
        built_at = ctx.get_graph_built_at()

        # Get node counts if graph exists
        node_counts: Dict[str, int] = {}
        total_nodes = 0
        if ctx._graph_state is not None:
            graph = ctx._graph_state.graph
            counts = graph.count_by_kind()
            node_counts = {kind.value: count for kind, count in counts.items()}
            total_nodes = graph.node_count()

        return {
            "is_stale": is_stale,
            "stale_files": [str(f) for f in stale_files],
            "has_graph": ctx._graph_state is not None,
            "node_counts": node_counts,
            "total_nodes": total_nodes,
            "last_built": built_at,
        }

    @mcp.tool()
    def refresh_graph(full: bool = False) -> Dict[str, Any]:
        """
        Refresh the traceability graph.

        Forces a rebuild of the graph from spec files. Use this
        after making changes to requirements if you need immediate
        access to updated graph data.

        Args:
            full: If True, force full rebuild even if not stale.
                  If False, only rebuild if stale files detected.

        Returns:
            Graph status after refresh including node counts.
        """
        from elspais.core.graph import NodeKind

        was_stale = ctx.is_graph_stale()
        stale_before = ctx.get_stale_files()

        # Trigger graph refresh
        graph, validation = ctx.get_graph(force_refresh=full)

        # Get updated stats
        counts = graph.count_by_kind()
        node_counts = {kind.value: count for kind, count in counts.items()}

        return {
            "refreshed": True,
            "was_stale": was_stale,
            "files_refreshed": [str(f) for f in stale_before] if was_stale else [],
            "node_counts": node_counts,
            "total_nodes": graph.node_count(),
            "validation": {
                "is_valid": validation.is_valid,
                "error_count": len(validation.errors),
                "warning_count": len(validation.warnings),
            },
            "last_built": ctx.get_graph_built_at(),
        }

    @mcp.tool()
    def get_hierarchy(req_id: str) -> Dict[str, Any]:
        """
        Get hierarchy information for a requirement.

        Returns the ancestors (parents up to root), children (direct
        descendants), and depth in the graph for the specified requirement.

        This is useful for understanding where a requirement sits in
        the traceability hierarchy.

        Args:
            req_id: The requirement ID (e.g., "REQ-p00001")

        Returns:
            Dict with ancestors, children, depth, and node info
        """
        from elspais.core.graph import NodeKind

        graph, _ = ctx.get_graph()
        node = graph.find_by_id(req_id)

        if node is None:
            return {"error": f"Requirement {req_id} not found in graph"}

        # Get ancestors (walk up through parents)
        ancestors = [a.id for a in node.ancestors()]

        # Get children (direct descendants, filtered by kind)
        children_reqs = [c.id for c in node.children if c.kind == NodeKind.REQUIREMENT]
        children_assertions = [c.id for c in node.children if c.kind == NodeKind.ASSERTION]

        return {
            "id": req_id,
            "kind": node.kind.value,
            "label": node.label,
            "depth": node.depth,
            "ancestors": ancestors,
            "children": {
                "requirements": children_reqs,
                "assertions": children_assertions,
            },
            "source": {
                "file": node.source.path if node.source else None,
                "line": node.source.line if node.source else None,
            },
        }

    @mcp.tool()
    def get_traceability_path(req_id: str, max_depth: int = 10) -> Dict[str, Any]:
        """
        Get full traceability path from a requirement down to tests.

        Returns a tree structure showing the requirement, its assertions,
        implementing code, validating tests, and test results.

        This is the primary tool for auditor review, showing the complete
        traceability chain from requirement to evidence.

        Args:
            req_id: The requirement ID (e.g., "REQ-p00001")
            max_depth: Maximum depth to traverse (default 10)

        Returns:
            Tree structure with full traceability path
        """
        from elspais.core.graph import NodeKind

        graph, _ = ctx.get_graph()
        node = graph.find_by_id(req_id)

        if node is None:
            return {"error": f"Requirement {req_id} not found in graph"}

        def build_tree(n, depth=0):
            """Recursively build tree structure."""
            if depth > max_depth:
                return {"id": n.id, "truncated": True}

            result = {
                "id": n.id,
                "kind": n.kind.value,
                "label": n.label,
            }

            # Add source location if available
            if n.source:
                result["source"] = {
                    "file": n.source.path,
                    "line": n.source.line,
                }

            # Add metrics if available
            if n.metrics:
                # Only include key metrics
                coverage = n.metrics.get("coverage_pct")
                if coverage is not None:
                    result["coverage_pct"] = coverage

            # Add test status if this is a test result
            if n.kind == NodeKind.TEST_RESULT and n.test_result:
                result["status"] = n.test_result.status.value if n.test_result.status else None

            # Add children organized by kind
            if n.children:
                children_by_kind: Dict[str, list] = {}
                for child in n.children:
                    kind_key = child.kind.value
                    if kind_key not in children_by_kind:
                        children_by_kind[kind_key] = []
                    children_by_kind[kind_key].append(build_tree(child, depth + 1))
                if children_by_kind:
                    result["children"] = children_by_kind

            return result

        tree = build_tree(node)

        # Add summary metrics
        total_assertions = len([c for c in node.children if c.kind == NodeKind.ASSERTION])
        covered_assertions = node.metrics.get("covered_assertions", 0) if node.metrics else 0
        total_tests = node.metrics.get("total_tests", 0) if node.metrics else 0
        passed_tests = node.metrics.get("passed_tests", 0) if node.metrics else 0

        return {
            "tree": tree,
            "summary": {
                "total_assertions": total_assertions,
                "covered_assertions": covered_assertions,
                "coverage_pct": node.metrics.get("coverage_pct", 0.0) if node.metrics else 0.0,
                "total_tests": total_tests,
                "passed_tests": passed_tests,
                "pass_rate_pct": node.metrics.get("pass_rate_pct", 0.0) if node.metrics else 0.0,
            },
        }


def _analyze_hierarchy(requirements: Dict[str, Any]) -> Dict[str, Any]:
    """Analyze requirement hierarchy."""
    # Build parent -> children mapping
    children_map: Dict[str, List[str]] = {}
    roots = []

    for req in requirements.values():
        if not req.implements:
            roots.append(req.id)
        else:
            for parent_id in req.implements:
                if parent_id not in children_map:
                    children_map[parent_id] = []
                children_map[parent_id].append(req.id)

    return {
        "total": len(requirements),
        "roots": roots,
        "children_map": children_map,
    }


def _analyze_orphans(requirements: Dict[str, Any]) -> Dict[str, Any]:
    """Find orphaned requirements."""
    all_ids = set(requirements.keys())
    orphans = []

    for req in requirements.values():
        for parent_id in req.implements:
            if parent_id not in all_ids:
                orphans.append(
                    {
                        "id": req.id,
                        "missing_parent": parent_id,
                    }
                )

    return {
        "count": len(orphans),
        "orphans": orphans,
    }


def _analyze_coverage(requirements: Dict[str, Any]) -> Dict[str, Any]:
    """Analyze requirement coverage by level."""
    levels: Dict[str, int] = {}

    for req in requirements.values():
        level = req.level.upper()
        levels[level] = levels.get(level, 0) + 1

    return {
        "total": len(requirements),
        "by_level": levels,
    }


def run_server(
    working_dir: Optional[Path] = None,
    transport: str = "stdio",
) -> None:
    """
    Run the MCP server.

    Args:
        working_dir: Working directory
        transport: Transport type - "stdio", "sse", or "streamable-http"
    """
    mcp = create_server(working_dir)
    mcp.run(transport=transport)
