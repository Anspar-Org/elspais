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

from elspais.mcp.annotations import AnnotationStore
from elspais.mcp.context import WorkspaceContext
from elspais.mcp.serializers import (
    serialize_broken_reference,
    serialize_content_rule,
    serialize_mutation_entry,
    serialize_node_full,
    serialize_requirement,
    serialize_requirement_summary,
    serialize_violation,
)


def _build_coverage_breakdown(ctx: "WorkspaceContext", req_id: str) -> Dict[str, Any]:
    """
    Build coverage breakdown for a requirement.

    Shared implementation used by both get_coverage_resource() and
    get_coverage_breakdown(). Returns per-assertion coverage status,
    coverage sources, implementing code, validating tests, and gaps.

    Args:
        ctx: WorkspaceContext for graph access
        req_id: The requirement ID (e.g., "REQ-p00001")

    Returns:
        Dict with coverage breakdown, or error dict if requirement not found
    """
    from elspais.graph import NodeKind

    graph, _ = ctx.get_graph()
    node = graph.find_by_id(req_id)

    if node is None:
        return {"error": f"Requirement {req_id} not found in graph"}

    assertions = []
    gaps = []

    for child in node.iter_children():
        if child.kind == NodeKind.ASSERTION:
            assertion_info = {
                "id": child.id,
                "label": child.get_label(),
                "covered": False,
                "coverage_source": None,
                "implementing_code": [],
                "validating_tests": [],
            }

            # Check for coverage sources
            contributions = child.get_metric("_coverage_contributions", [])
            if contributions:
                assertion_info["covered"] = True
                # Get the source type from the first contribution
                first = contributions[0]
                if hasattr(first, "source_type"):
                    assertion_info["coverage_source"] = (
                        first.source_type.value
                        if hasattr(first.source_type, "value")
                        else str(first.source_type)
                    )
                else:
                    assertion_info["coverage_source"] = "unknown"

            # Get implementing code (direct children of kind CODE)
            for code_child in child.iter_children():
                if code_child.kind == NodeKind.CODE:
                    code_info = {"id": code_child.id, "label": code_child.get_label()}
                    if code_child.source:
                        code_info["file"] = code_child.source.path
                        code_info["line"] = code_child.source.line
                    assertion_info["implementing_code"].append(code_info)

            # Get validating tests
            for test_child in child.iter_children():
                if test_child.kind == NodeKind.TEST:
                    test_info = {
                        "id": test_child.id,
                        "label": test_child.get_label(),
                        "status": None,
                    }
                    if test_child.source:
                        test_info["file"] = test_child.source.path
                        test_info["line"] = test_child.source.line
                    # Check for test results
                    for result_child in test_child.iter_children():
                        if (
                            result_child.kind == NodeKind.TEST_RESULT
                            and result_child.test_result
                        ):
                            test_info["status"] = (
                                result_child.test_result.status.value
                                if result_child.test_result.status
                                else None
                            )
                    assertion_info["validating_tests"].append(test_info)

            assertions.append(assertion_info)
            if not assertion_info["covered"]:
                gaps.append(child.id)

    return {
        "id": req_id,
        "label": node.get_label(),
        "assertions": assertions,
        "gaps": gaps,
        "summary": {
            "total_assertions": len(assertions),
            "covered_assertions": len([a for a in assertions if a["covered"]]),
            "coverage_pct": node.get_metric("coverage_pct", 0.0),
            "direct_covered": node.get_metric("direct_covered", 0),
            "explicit_covered": node.get_metric("explicit_covered", 0),
            "inferred_covered": node.get_metric("inferred_covered", 0),
        },
    }


def _get_server_instructions() -> str:
    """Return server instructions for Tool Search discovery.

    These instructions help AI agents understand when and how to use
    elspais tools for requirements management tasks.
    """
    return """# elspais Requirements Traceability Server

Use these tools when working with requirements, specifications, or traceability.

## When to use elspais:
- Validating requirement format and hierarchy rules
- Analyzing test coverage for requirements
- Searching or navigating requirement hierarchies
- Modifying requirement relationships (Implements/Refines)
- Moving requirements between spec files
- AI-assisted requirement transformation
- In-memory graph mutations with undo support

## Tool Categories:

### Read-Only (safe, no file changes):
- validate() - Check format and hierarchy rules
- search() - Find requirements by pattern
- get_requirement() - Get details for single requirement
- get_hierarchy() - Navigate parent/child relationships
- get_traceability_path() - Full tree from requirement to tests
- get_coverage_breakdown() - Per-assertion coverage details

### File Mutation (modifies spec files):
- change_reference_type() - Switch Implements ↔ Refines
- specialize_reference() - REQ→REQ to REQ→Assertion
- move_requirement() - Move between files
- transform_with_ai() - AI-assisted rewrite

### Graph Mutation (in-memory with undo):
- mutate_rename_node() - Rename requirement ID
- mutate_update_title() - Change requirement title
- mutate_change_status() - Change requirement status
- mutate_add_requirement() - Create new requirement
- mutate_delete_requirement() - Delete requirement (with confirmation)
- mutate_add_assertion() - Add assertion to requirement
- mutate_update_assertion() - Update assertion text
- mutate_delete_assertion() - Delete assertion with compaction
- mutate_rename_assertion() - Change assertion label
- mutate_add_edge() - Add implements/refines relationship
- mutate_change_edge_kind() - Switch edge type
- mutate_delete_edge() - Remove relationship
- mutate_fix_broken_reference() - Redirect broken reference

### Undo Operations:
- undo_last_mutation() - Undo most recent graph mutation
- undo_to_mutation() - Batch undo to specific point
- get_mutation_log() - View mutation history
- get_orphaned_nodes() - List nodes without parents
- get_broken_references() - List unresolved references

## Key Workflows:

1. **Understand a requirement**:
   get_requirement() → get_hierarchy() → get_traceability_path()

2. **Find coverage gaps**:
   list_by_criteria(has_gaps=True) → get_coverage_breakdown()

3. **Safely modify files**:
   get_requirement() → [file mutation tool] → refresh_graph() → validate()

4. **Graph mutations with undo**:
   mutate_*() → [verify changes] → undo_last_mutation() if needed

5. **AI transformation** (always use git safety):
   get_node_as_json() → transform_with_ai(save_branch=True)

## Safety Notes:
- Graph mutations are in-memory only - use undo_last_mutation() to reverse
- File mutations modify spec files - use git safety branches
- Always use prepare_file_deletion() before delete_spec_file()
- Use transform_with_ai() with save_branch=True for AI changes
- Call refresh_graph() after file mutation tools
- restore_from_safety_branch() to undo file changes if needed
"""


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

    # Initialize session-scoped annotation store
    annotation_store = AnnotationStore()

    # Create FastMCP server with instructions for Tool Search discovery
    mcp = FastMCP(
        name="elspais",
        instructions=_get_server_instructions(),
    )

    # Register resources
    _register_resources(mcp, ctx)

    # Register tools
    _register_tools(mcp, ctx, annotation_store)

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

    # Graph-related resources

    @mcp.resource("graph://status")
    def get_graph_status_resource() -> str:
        """
        Get traceability graph status and statistics.

        Returns information about the graph cache state including
        staleness, changed files, node counts by type, and build time.
        """
        import json

        is_stale = ctx.is_graph_stale()
        stale_files = ctx.get_stale_files()
        built_at = ctx.get_graph_built_at()

        node_counts: Dict[str, int] = {}
        total_nodes = 0
        if ctx._graph_state is not None:
            graph = ctx._graph_state.graph
            counts = graph.count_by_kind()
            node_counts = {kind.value: count for kind, count in counts.items()}
            total_nodes = graph.node_count()

        return json.dumps(
            {
                "is_stale": is_stale,
                "stale_files": [str(f) for f in stale_files],
                "has_graph": ctx._graph_state is not None,
                "node_counts": node_counts,
                "total_nodes": total_nodes,
                "last_built": built_at,
            },
            indent=2,
        )

    @mcp.resource("graph://validation")
    def get_graph_validation_resource() -> str:
        """
        Get current graph validation warnings and errors.

        Returns validation results from the last graph build including
        broken links, cycles, and orphan nodes.
        """
        import json

        if ctx._graph_state is None:
            # Build graph if not available
            _, validation = ctx.get_graph()
        else:
            validation = ctx._graph_state.validation

        return json.dumps(
            {
                "is_valid": validation.is_valid,
                "errors": [
                    {
                        "type": e.type if hasattr(e, "type") else "error",
                        "message": str(e),
                    }
                    for e in validation.errors
                ],
                "warnings": [
                    {
                        "type": w.type if hasattr(w, "type") else "warning",
                        "message": str(w),
                    }
                    for w in validation.warnings
                ],
                "summary": {
                    "error_count": len(validation.errors),
                    "warning_count": len(validation.warnings),
                },
            },
            indent=2,
        )

    @mcp.resource("traceability://{req_id}")
    def get_traceability_resource(req_id: str) -> str:
        """
        Get full traceability path from requirement down to tests.

        Returns a tree structure showing the requirement, assertions,
        implementing code, validating tests, and test results.
        """
        import json
        from elspais.graph import NodeKind

        graph, _ = ctx.get_graph()
        node = graph.find_by_id(req_id)

        if node is None:
            return json.dumps({"error": f"Requirement {req_id} not found in graph"})

        def build_tree(n, depth=0, max_depth=99):
            """Recursively build tree structure."""
            if depth > max_depth:
                return {"id": n.id, "truncated": True}

            result = {
                "id": n.id,
                "kind": n.kind.value,
                "label": n.get_label(),
            }

            if n.source:
                result["source"] = {
                    "file": n.source.path,
                    "line": n.source.line,
                }

            coverage = n.get_metric("coverage_pct")
            if coverage is not None:
                result["coverage_pct"] = coverage

            if n.kind == NodeKind.TEST_RESULT and n.test_result:
                result["status"] = (
                    n.test_result.status.value if n.test_result.status else None
                )

            children = list(n.iter_children())
            if children:
                children_by_kind: Dict[str, list] = {}
                for child in children:
                    kind_key = child.kind.value
                    if kind_key not in children_by_kind:
                        children_by_kind[kind_key] = []
                    children_by_kind[kind_key].append(build_tree(child, depth + 1))
                if children_by_kind:
                    result["children"] = children_by_kind

            return result

        tree = build_tree(node)

        total_assertions = sum(1 for c in node.iter_children() if c.kind == NodeKind.ASSERTION)
        covered_assertions = node.get_metric("covered_assertions", 0)
        total_tests = node.get_metric("total_tests", 0)
        passed_tests = node.get_metric("passed_tests", 0)

        return json.dumps(
            {
                "tree": tree,
                "summary": {
                    "total_assertions": total_assertions,
                    "covered_assertions": covered_assertions,
                    "coverage_pct": node.get_metric("coverage_pct", 0.0),
                    "total_tests": total_tests,
                    "passed_tests": passed_tests,
                    "pass_rate_pct": node.get_metric("pass_rate_pct", 0.0),
                },
            },
            indent=2,
        )

    @mcp.resource("coverage://{req_id}")
    def get_coverage_resource(req_id: str) -> str:
        """
        Get detailed coverage breakdown for a requirement.

        Returns per-assertion coverage status, coverage sources,
        implementing code, validating tests, and coverage gaps.
        """
        import json

        return json.dumps(_build_coverage_breakdown(ctx, req_id), indent=2)

    @mcp.resource("hierarchy://{req_id}/ancestors")
    def get_hierarchy_ancestors_resource(req_id: str) -> str:
        """
        Get ancestors (parents up to root) for a requirement.

        Returns the chain of parent requirements from immediate
        parent up to root-level requirements.
        """
        import json
        from elspais.graph import NodeKind

        graph, _ = ctx.get_graph()
        node = graph.find_by_id(req_id)

        if node is None:
            return json.dumps({"error": f"Requirement {req_id} not found in graph"})

        ancestors = []
        for ancestor in node.ancestors():
            ancestor_info = {
                "id": ancestor.id,
                "kind": ancestor.kind.value,
                "label": ancestor.get_label(),
                "depth": ancestor.depth,
            }
            if ancestor.source:
                ancestor_info["source"] = {
                    "file": ancestor.source.path,
                    "line": ancestor.source.line,
                }
            ancestors.append(ancestor_info)

        return json.dumps(
            {
                "id": req_id,
                "depth": node.depth,
                "ancestor_count": len(ancestors),
                "ancestors": ancestors,
            },
            indent=2,
        )

    @mcp.resource("hierarchy://{req_id}/descendants")
    def get_hierarchy_descendants_resource(req_id: str) -> str:
        """
        Get descendants (children down to leaves) for a requirement.

        Returns all child nodes recursively including nested requirements,
        assertions, code references, and tests.
        """
        import json
        from elspais.graph import NodeKind

        graph, _ = ctx.get_graph()
        node = graph.find_by_id(req_id)

        if node is None:
            return json.dumps({"error": f"Requirement {req_id} not found in graph"})

        def collect_descendants(n, depth=0, max_depth=99):
            """Collect all descendants recursively."""
            if depth > max_depth:
                return []
            descendants = []
            for child in n.iter_children():
                child_info = {
                    "id": child.id,
                    "kind": child.kind.value,
                    "label": child.get_label(),
                    "parent": n.id,
                }
                if child.source:
                    child_info["source"] = {
                        "file": child.source.path,
                        "line": child.source.line,
                    }
                descendants.append(child_info)
                descendants.extend(collect_descendants(child, depth + 1, max_depth))
            return descendants

        descendants = collect_descendants(node)

        # Count by kind
        counts_by_kind: Dict[str, int] = {}
        for d in descendants:
            kind = d["kind"]
            counts_by_kind[kind] = counts_by_kind.get(kind, 0) + 1

        return json.dumps(
            {
                "id": req_id,
                "descendant_count": len(descendants),
                "counts_by_kind": counts_by_kind,
                "descendants": descendants,
            },
            indent=2,
        )


def _register_tools(
    mcp: "FastMCP", ctx: WorkspaceContext, annotation_store: AnnotationStore
) -> None:
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
        import fnmatch
        from elspais.mcp.serializers import RuleViolation, Severity

        graph, _ = ctx.get_graph(force_refresh=True)
        requirements = ctx.get_requirements(force_refresh=True)

        # Collect validation issues using graph
        violations = []

        for node in requirements.values():
            # Check for orphan requirements (no parents except roots)
            if node.parent_count() == 0 and (node.level or "").upper() not in ("PRD",):
                violations.append(RuleViolation(
                    rule_name="hierarchy.orphan",
                    requirement_id=node.id,
                    message=f"Requirement {node.id} has no parent (orphan)",
                    severity=Severity.WARNING,
                    location=node.source.path if node.source else None,
                ))

            # Check for hash presence
            if not node.hash:
                violations.append(RuleViolation(
                    rule_name="hash.missing",
                    requirement_id=node.id,
                    message=f"Requirement {node.id} is missing a hash",
                    severity=Severity.WARNING,
                    location=node.source.path if node.source else None,
                ))

        # Filter by skip_rules
        if skip_rules:
            violations = [
                v for v in violations
                if not any(fnmatch.fnmatch(v.rule_name, p) for p in skip_rules)
            ]

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
        from elspais.graph.parsers import ParserRegistry
        from elspais.graph.parsers.requirement import RequirementParser
        from elspais.utilities.patterns import PatternConfig

        pattern_config = PatternConfig.from_dict(ctx.config.get("patterns", {}))
        registry = ParserRegistry()
        registry.register(RequirementParser(pattern_config))

        # Parse text to extract requirements
        source_id = file_path or "<text>"
        parsed_items = list(registry.parse_text(text, source_id))

        requirements = {}
        for item in parsed_items:
            if item.content_type == "requirement":
                req_id = item.parsed_data.get("id", "")
                if req_id:
                    requirements[req_id] = item.parsed_data

        return {
            "count": len(requirements),
            "requirements": requirements,
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
        from elspais.graph import NodeKind

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
        from elspais.graph import NodeKind

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
        from elspais.graph import NodeKind

        graph, _ = ctx.get_graph()
        node = graph.find_by_id(req_id)

        if node is None:
            return {"error": f"Requirement {req_id} not found in graph"}

        # Get ancestors (walk up through parents)
        ancestors = [a.id for a in node.ancestors()]

        # Get children (direct descendants, filtered by kind)
        children_reqs = [c.id for c in node.iter_children() if c.kind == NodeKind.REQUIREMENT]
        children_assertions = [c.id for c in node.iter_children() if c.kind == NodeKind.ASSERTION]

        return {
            "id": req_id,
            "kind": node.kind.value,
            "label": node.get_label(),
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
    def get_traceability_path(req_id: str, max_depth: int = 99) -> Dict[str, Any]:
        """
        Get full traceability path from a requirement down to tests.

        Returns a tree structure showing the requirement, its assertions,
        implementing code, validating tests, and test results.

        This is the primary tool for auditor review, showing the complete
        traceability chain from requirement to evidence.

        Args:
            req_id: The requirement ID (e.g., "REQ-p00001")
            max_depth: Maximum depth to traverse (default 99)

        Returns:
            Tree structure with full traceability path
        """
        from elspais.graph import NodeKind

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
                "label": n.get_label(),
            }

            # Add source location if available
            if n.source:
                result["source"] = {
                    "file": n.source.path,
                    "line": n.source.line,
                }

            # Add metrics if available
            coverage = n.get_metric("coverage_pct")
            if coverage is not None:
                result["coverage_pct"] = coverage

            # Add test status if this is a test result
            if n.kind == NodeKind.TEST_RESULT and n.test_result:
                result["status"] = n.test_result.status.value if n.test_result.status else None

            # Add children organized by kind
            children = list(n.iter_children())
            if children:
                children_by_kind: Dict[str, list] = {}
                for child in children:
                    kind_key = child.kind.value
                    if kind_key not in children_by_kind:
                        children_by_kind[kind_key] = []
                    children_by_kind[kind_key].append(build_tree(child, depth + 1))
                if children_by_kind:
                    result["children"] = children_by_kind

            return result

        tree = build_tree(node)

        # Add summary metrics
        total_assertions = sum(1 for c in node.iter_children() if c.kind == NodeKind.ASSERTION)
        covered_assertions = node.get_metric("covered_assertions", 0)
        total_tests = node.get_metric("total_tests", 0)
        passed_tests = node.get_metric("passed_tests", 0)

        return {
            "tree": tree,
            "summary": {
                "total_assertions": total_assertions,
                "covered_assertions": covered_assertions,
                "coverage_pct": node.get_metric("coverage_pct", 0.0),
                "total_tests": total_tests,
                "passed_tests": passed_tests,
                "pass_rate_pct": node.get_metric("pass_rate_pct", 0.0),
            },
        }

    @mcp.tool()
    def get_coverage_breakdown(req_id: str) -> Dict[str, Any]:
        """
        Get detailed coverage breakdown for a requirement.

        Returns per-assertion coverage status, coverage sources
        (direct/explicit/inferred), implementing code references,
        validating tests with pass/fail status, and coverage gaps.

        This is the primary tool for auditor review of coverage evidence.

        Args:
            req_id: The requirement ID (e.g., "REQ-p00001")

        Returns:
            Detailed coverage breakdown with assertion-level detail
        """
        return _build_coverage_breakdown(ctx, req_id)

    @mcp.tool()
    def list_by_criteria(
        level: Optional[str] = None,
        status: Optional[str] = None,
        coverage_below: Optional[float] = None,
        has_gaps: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """
        List requirements matching specified criteria.

        Useful for auditor review to find requirements by level,
        status, or coverage thresholds.

        Args:
            level: Filter by level (PRD, OPS, DEV)
            status: Filter by status (Active, Draft, Deprecated, etc.)
            coverage_below: Filter requirements with coverage below this percentage
            has_gaps: If True, only return requirements with uncovered assertions

        Returns:
            List of matching requirements with summary info
        """
        from elspais.graph import NodeKind

        graph, _ = ctx.get_graph()
        requirements = ctx.get_requirements()

        results = []

        for req in requirements.values():
            # Apply filters
            if level and req.level.upper() != level.upper():
                continue
            if status and req.status.lower() != status.lower():
                continue

            # Get graph node for metrics
            node = graph.find_by_id(req.id)

            # Coverage filter
            coverage_pct = node.get_metric("coverage_pct", 0.0) if node else 0.0
            if coverage_below is not None and coverage_pct >= coverage_below:
                continue

            # Gaps filter
            if has_gaps is not None:
                total = node.get_metric("total_assertions", 0) if node else 0
                covered = node.get_metric("covered_assertions", 0) if node else 0
                req_has_gaps = total > covered
                if has_gaps and not req_has_gaps:
                    continue
                if not has_gaps and req_has_gaps:
                    continue

            # Build result entry
            entry = {
                "id": req.id,
                "title": req.title,
                "level": req.level,
                "status": req.status,
                "coverage_pct": coverage_pct,
                "total_assertions": node.get_metric("total_assertions", 0) if node else 0,
                "covered_assertions": node.get_metric("covered_assertions", 0) if node else 0,
            }

            if node and node.source:
                entry["source"] = {
                    "file": node.source.path,
                    "line": node.source.line,
                }

            results.append(entry)

        return {
            "count": len(results),
            "filters": {
                "level": level,
                "status": status,
                "coverage_below": coverage_below,
                "has_gaps": has_gaps,
            },
            "requirements": results,
        }

    @mcp.tool()
    def show_requirement_context(
        req_id: str,
        include_assertions: bool = True,
        include_implementers: bool = False,
    ) -> Dict[str, Any]:
        """
        Display requirement with full context for auditor review.

        Returns the complete requirement text, assertions, source location,
        and optionally the implementing requirements (children).

        This tool provides a comprehensive view of a single requirement
        for detailed inspection during compliance review.

        Args:
            req_id: The requirement ID (e.g., "REQ-p00001")
            include_assertions: Include assertion labels and text (default True)
            include_implementers: Include child requirements that implement this one

        Returns:
            Full requirement context including text, assertions, metrics
        """
        from elspais.graph import NodeKind

        req = ctx.get_requirement(req_id)
        if req is None:
            return {"error": f"Requirement {req_id} not found"}

        graph, _ = ctx.get_graph()
        node = graph.find_by_id(req_id)

        result: Dict[str, Any] = {
            "id": req.id,
            "title": req.title,
            "level": req.level,
            "status": req.status,
            "body": req.body,
            "rationale": req.rationale,
            "hash": req.hash,
            "implements": req.implements,
        }

        # Source location
        if req.file_path:
            result["source"] = {
                "file": str(req.file_path),
                "line": req.line_number,
            }

        # Assertions
        if include_assertions and req.assertions:
            result["assertions"] = [
                {
                    "label": a.label,
                    "text": a.text,
                    "is_placeholder": a.is_placeholder,
                }
                for a in req.assertions
            ]

        # Coverage metrics
        if node:
            result["metrics"] = {
                "total_assertions": node.get_metric("total_assertions", 0),
                "covered_assertions": node.get_metric("covered_assertions", 0),
                "coverage_pct": node.get_metric("coverage_pct", 0.0),
                "direct_covered": node.get_metric("direct_covered", 0),
                "explicit_covered": node.get_metric("explicit_covered", 0),
                "inferred_covered": node.get_metric("inferred_covered", 0),
                "total_tests": node.get_metric("total_tests", 0),
                "passed_tests": node.get_metric("passed_tests", 0),
                "pass_rate_pct": node.get_metric("pass_rate_pct", 0.0),
            }

        # Implementing requirements (children)
        if include_implementers and node:
            implementers = []
            for child in node.iter_children():
                if child.kind == NodeKind.REQUIREMENT:
                    implementer = {
                        "id": child.id,
                        "label": child.get_label(),
                    }
                    if child.source:
                        implementer["source"] = {
                            "file": child.source.path,
                            "line": child.source.line,
                        }
                    implementer["coverage_pct"] = child.get_metric("coverage_pct", 0.0)
                    implementers.append(implementer)
            result["implementers"] = implementers

        return result

    @mcp.tool()
    def change_reference_type(
        source_id: str,
        target_id: str,
        new_type: str,
    ) -> Dict[str, Any]:
        """
        Change a reference from Implements to Refines or vice versa.

        This tool modifies the spec file to change the reference type
        for a specific relationship. Use this when a child requirement
        should refine (add detail) rather than implement (claim satisfaction)
        its parent, or vice versa.

        Args:
            source_id: The requirement ID that contains the reference
            target_id: The referenced requirement ID to change
            new_type: The new reference type - "implements" or "refines"

        Returns:
            Result of the change operation including success status
            and the file that was modified
        """
        from elspais.mcp.mutator import SpecFileMutator, ReferenceType

        # Validate new_type
        new_type_lower = new_type.lower()
        if new_type_lower not in ("implements", "refines"):
            return {
                "success": False,
                "error": f"Invalid reference type: {new_type}. Must be 'implements' or 'refines'",
            }

        ref_type = (
            ReferenceType.IMPLEMENTS
            if new_type_lower == "implements"
            else ReferenceType.REFINES
        )

        # Get the source requirement to find its file path
        req = ctx.get_requirement(source_id)
        if req is None:
            return {
                "success": False,
                "error": f"Source requirement {source_id} not found",
            }

        if not req.file_path:
            return {
                "success": False,
                "error": f"Source requirement {source_id} has no file path",
            }

        # Create mutator and perform the change
        mutator = SpecFileMutator(ctx.working_dir)
        result = mutator.change_reference_type(
            source_id=source_id,
            target_id=target_id,
            new_type=ref_type,
            file_path=Path(req.file_path),
        )

        response: Dict[str, Any] = {
            "success": result.success,
            "source_id": result.source_id,
            "target_id": result.target_id,
            "new_type": result.new_type.value,
            "message": result.message,
        }

        if result.old_type:
            response["old_type"] = result.old_type.value
        if result.file_path:
            response["file_path"] = str(result.file_path)

        # If successful, invalidate the requirements cache and graph
        if result.success:
            ctx._requirements_cache = None
            ctx._graph_state = None

        return response

    @mcp.tool()
    def specialize_reference(
        source_id: str,
        target_id: str,
        assertions: List[str],
    ) -> Dict[str, Any]:
        """
        Specialize a requirement reference to specific assertions.

        Converts a REQ→REQ reference to REQ→Assertion using multi-assertion
        syntax. For example:
            Implements: REQ-p00001
        becomes:
            Implements: REQ-p00001-A-B-C

        This allows more precise coverage tracking by linking child
        requirements to specific parent assertions rather than the
        entire parent requirement.

        Args:
            source_id: The requirement ID that contains the reference
            target_id: The referenced requirement ID to specialize
            assertions: List of assertion labels (e.g., ["A", "B", "C"])

        Returns:
            Result of the specialization including old and new reference strings
        """
        from elspais.mcp.mutator import SpecFileMutator

        # Get the source requirement to find its file path
        req = ctx.get_requirement(source_id)
        if req is None:
            return {
                "success": False,
                "error": f"Source requirement {source_id} not found",
            }

        if not req.file_path:
            return {
                "success": False,
                "error": f"Source requirement {source_id} has no file path",
            }

        # Create mutator and perform the specialization
        mutator = SpecFileMutator(ctx.working_dir)
        result = mutator.specialize_reference(
            source_id=source_id,
            target_id=target_id,
            assertions=assertions,
            file_path=Path(req.file_path),
        )

        response: Dict[str, Any] = {
            "success": result.success,
            "source_id": result.source_id,
            "target_id": result.target_id,
            "assertions": result.assertions,
            "message": result.message,
        }

        if result.old_reference:
            response["old_reference"] = result.old_reference
        if result.new_reference:
            response["new_reference"] = result.new_reference
        if result.file_path:
            response["file_path"] = str(result.file_path)

        # If successful, invalidate the requirements cache and graph
        if result.success:
            ctx._requirements_cache = None
            ctx._graph_state = None

        return response

    @mcp.tool()
    def move_requirement(
        req_id: str,
        target_file: str,
        position: str = "end",
        after_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Move a requirement from its current file to a different file.

        This tool extracts a requirement from its source file and inserts
        it into the target file at the specified position. Use this for
        reorganizing requirements across spec files.

        Args:
            req_id: The requirement ID to move (e.g., "REQ-p00001")
            target_file: Path to the destination file (relative to workspace)
            position: Where to insert - "start", "end", or "after"
            after_id: If position="after", the requirement ID to insert after

        Returns:
            Result of the move operation including success status
        """
        from elspais.mcp.mutator import SpecFileMutator

        # Validate position
        if position not in ("start", "end", "after"):
            return {
                "success": False,
                "error": f"Invalid position: {position}. Must be 'start', 'end', or 'after'",
            }

        # Validate after_id if position is "after"
        if position == "after" and not after_id:
            return {
                "success": False,
                "error": "after_id is required when position is 'after'",
            }

        # Get the source requirement to find its file path
        req = ctx.get_requirement(req_id)
        if req is None:
            return {
                "success": False,
                "error": f"Requirement {req_id} not found",
            }

        if not req.file_path:
            return {
                "success": False,
                "error": f"Requirement {req_id} has no file path",
            }

        source_file = Path(req.file_path)
        target_path = Path(target_file)

        # Create mutator and perform the move
        mutator = SpecFileMutator(ctx.working_dir)
        result = mutator.move_requirement(
            req_id=req_id,
            source_file=source_file,
            target_file=target_path,
            position=position,
            after_id=after_id,
        )

        response: Dict[str, Any] = {
            "success": result.success,
            "req_id": result.req_id,
            "position": result.position,
            "message": result.message,
        }

        if result.source_file:
            response["source_file"] = str(result.source_file)
        if result.target_file:
            response["target_file"] = str(result.target_file)
        if result.after_id:
            response["after_id"] = result.after_id

        # If successful, invalidate the requirements cache and graph
        if result.success:
            ctx._requirements_cache = None
            ctx._graph_state = None

        return response

    @mcp.tool()
    def prepare_file_deletion(
        file_path: str,
    ) -> Dict[str, Any]:
        """
        Analyze a spec file to determine if it can be safely deleted.

        This tool checks for remaining requirements and non-requirement content
        that might need to be preserved before deletion. Use this before
        calling delete_spec_file to understand what will be affected.

        Args:
            file_path: Path to the spec file to analyze (relative to workspace)

        Returns:
            Analysis including:
            - can_delete: Whether the file can be safely deleted
            - remaining_requirements: List of requirement IDs still in file
            - has_non_requirement_content: Whether there's content to preserve
            - non_requirement_content: The content that would be lost
        """
        from elspais.mcp.mutator import SpecFileMutator

        mutator = SpecFileMutator(ctx.working_dir)
        result = mutator.analyze_file_for_deletion(Path(file_path))

        return {
            "can_delete": result.can_delete,
            "file_path": str(result.file_path),
            "remaining_requirements": result.remaining_requirements,
            "has_non_requirement_content": result.has_non_requirement_content,
            "non_requirement_content": result.non_requirement_content,
            "message": result.message,
        }

    @mcp.tool()
    def delete_spec_file(
        file_path: str,
        force: bool = False,
        extract_content_to: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Delete a spec file, optionally extracting non-requirement content.

        By default, refuses to delete files with remaining requirements.
        Use force=True to delete anyway (requirements will be lost).

        IMPORTANT: Use prepare_file_deletion first to understand what
        will be affected. Move requirements to other files before deletion
        using move_requirement.

        Args:
            file_path: Path to the spec file to delete (relative to workspace)
            force: If True, delete even if requirements remain (data loss!)
            extract_content_to: If provided, extract non-requirement content
                               to this file before deletion

        Returns:
            Result including success status and what was done
        """
        from elspais.mcp.mutator import SpecFileMutator

        mutator = SpecFileMutator(ctx.working_dir)
        result = mutator.delete_spec_file(
            file_path=Path(file_path),
            force=force,
            extract_content_to=Path(extract_content_to) if extract_content_to else None,
        )

        response: Dict[str, Any] = {
            "success": result.success,
            "file_path": str(result.file_path),
            "content_extracted": result.content_extracted,
            "message": result.message,
        }

        if result.content_target:
            response["content_target"] = str(result.content_target)

        # If successful, invalidate the requirements cache and graph
        if result.success:
            ctx._requirements_cache = None
            ctx._graph_state = None

        return response

    @mcp.tool()
    def get_node_as_json(
        node_id: str,
        include_full_text: bool = True,
    ) -> Dict[str, Any]:
        """
        Get complete JSON representation of a node for AI processing.

        Returns comprehensive node data including:
        - Full requirement text from source file
        - All assertions with coverage info
        - Metrics (coverage, tests, pass rates)
        - Relationships (implements, implemented_by, refines)
        - Source location with line range

        This is the primary input format for AI transformation operations.

        Args:
            node_id: The requirement ID (e.g., "REQ-p00001")
            include_full_text: Include full requirement text from file

        Returns:
            Complete node data suitable for AI processing
        """
        req = ctx.get_requirement(node_id)
        if req is None:
            return {"error": f"Requirement {node_id} not found"}

        return serialize_node_full(req, ctx, include_full_text=include_full_text)

    @mcp.tool()
    def transform_with_ai(
        node_id: str,
        prompt: str,
        output_mode: str = "replace",
        save_branch: bool = True,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """
        Transform a requirement using AI (Claude).

        This tool invokes Claude with a prompt and the node's JSON data,
        then applies the transformation to the spec file.

        Output modes:
        - "replace": Claude returns new requirement markdown (applied to file)
        - "operations": Claude returns JSON list of operations (informational)
        - "patch": Claude returns diff (not yet implemented)

        Safety:
        - If save_branch=True, creates a git branch before changes
        - Use dry_run=True to preview without applying
        - Restore with restore_from_safety_branch if needed

        Args:
            node_id: The requirement ID to transform
            prompt: What transformation to perform
            output_mode: How Claude returns results ("replace", "operations")
            save_branch: Create git safety branch before changes
            dry_run: Preview without applying changes

        Returns:
            TransformResult with before/after text, safety branch, etc.
        """
        from elspais.mcp.transforms import AITransformer

        transformer = AITransformer(ctx.working_dir)
        result = transformer.transform(
            node_id=node_id,
            prompt=prompt,
            output_mode=output_mode,
            save_branch=save_branch,
            dry_run=dry_run,
            context=ctx,
        )

        response: Dict[str, Any] = {
            "success": result.success,
            "node_id": result.node_id,
            "dry_run": result.dry_run,
        }

        if result.safety_branch:
            response["safety_branch"] = result.safety_branch
        if result.before_text:
            response["before_text"] = result.before_text
        if result.after_text:
            response["after_text"] = result.after_text
        if result.operations:
            response["operations"] = result.operations
        if result.error:
            response["error"] = result.error
        if result.file_path:
            response["file_path"] = result.file_path

        return response

    @mcp.tool()
    def restore_from_safety_branch(branch_name: str) -> Dict[str, Any]:
        """
        Restore the repository from a safety branch.

        Use this to undo changes made by transform_with_ai or other
        mutation operations. The branch name is returned by those
        operations when save_branch=True.

        Args:
            branch_name: Name of the safety branch to restore from

        Returns:
            Result of the restore operation
        """
        from elspais.mcp.transforms import restore_from_safety_branch as restore

        success, message = restore(ctx.working_dir, branch_name)

        if success:
            # Invalidate caches after restore
            ctx.invalidate_cache()

        return {
            "success": success,
            "message": message,
            "branch_name": branch_name,
        }

    @mcp.tool()
    def list_safety_branches() -> Dict[str, Any]:
        """
        List all safety branches created by elspais.

        Safety branches are created by mutation operations when
        save_branch=True. They can be used to restore the repository
        to a previous state.

        Returns:
            List of safety branch names
        """
        from elspais.mcp.git_safety import GitSafetyManager

        manager = GitSafetyManager(ctx.working_dir)
        branches = manager.list_safety_branches()

        return {
            "count": len(branches),
            "branches": branches,
        }

    # Annotation tools

    @mcp.tool()
    def add_annotation(
        node_id: str,
        key: str,
        value: Any,
        source: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Add or update an annotation on a node.

        Annotations are session-scoped metadata that don't modify files.
        Useful for tracking review status, marking nodes for attention,
        or adding temporary notes during analysis.

        Args:
            node_id: The ID of the node to annotate
            key: The annotation key (e.g., "review_status", "priority")
            value: The annotation value
            source: Optional source identifier (e.g., "claude", "user")

        Returns:
            The created annotation
        """
        annotation = annotation_store.add_annotation(node_id, key, value, source)
        return {
            "node_id": node_id,
            "key": annotation.key,
            "value": annotation.value,
            "source": annotation.source,
            "created_at": annotation.created_at.isoformat(),
        }

    @mcp.tool()
    def get_annotations(node_id: str) -> Dict[str, Any]:
        """
        Get all annotations for a node.

        Args:
            node_id: The ID of the node

        Returns:
            Dict of annotation keys to values, plus tags
        """
        annotations = annotation_store.get_annotations(node_id)
        tags = list(annotation_store.get_tags(node_id))

        return {
            "node_id": node_id,
            "annotations": annotations,
            "tags": tags,
        }

    @mcp.tool()
    def add_tag(node_id: str, tag: str) -> Dict[str, Any]:
        """
        Add a tag to a node.

        Tags are lightweight markers for categorizing nodes.
        Unlike annotations, tags are simple strings without values.

        Args:
            node_id: The ID of the node to tag
            tag: The tag to add

        Returns:
            Result of the operation
        """
        added = annotation_store.add_tag(node_id, tag)
        return {
            "node_id": node_id,
            "tag": tag,
            "added": added,  # False if already present
            "message": f"Added tag '{tag}'" if added else f"Tag '{tag}' already present",
        }

    @mcp.tool()
    def remove_tag(node_id: str, tag: str) -> Dict[str, Any]:
        """
        Remove a tag from a node.

        Args:
            node_id: The ID of the node
            tag: The tag to remove

        Returns:
            Result of the operation
        """
        removed = annotation_store.remove_tag(node_id, tag)
        return {
            "node_id": node_id,
            "tag": tag,
            "removed": removed,
            "message": f"Removed tag '{tag}'" if removed else f"Tag '{tag}' not found",
        }

    @mcp.tool()
    def list_tagged(tag: str) -> Dict[str, Any]:
        """
        Get all node IDs with a specific tag.

        Args:
            tag: The tag to search for

        Returns:
            List of node IDs with this tag
        """
        node_ids = annotation_store.list_tagged(tag)
        return {
            "tag": tag,
            "count": len(node_ids),
            "node_ids": node_ids,
        }

    @mcp.tool()
    def list_all_tags() -> Dict[str, Any]:
        """
        Get all unique tags in use.

        Returns:
            List of tag names and counts
        """
        tags = annotation_store.list_all_tags()
        tag_counts = {tag: len(annotation_store.list_tagged(tag)) for tag in tags}

        return {
            "count": len(tags),
            "tags": tag_counts,
        }

    @mcp.tool()
    def nodes_with_annotation(
        key: str,
        value: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Find nodes with a specific annotation.

        Args:
            key: The annotation key to search for
            value: Optional value to match (if None, matches any value)

        Returns:
            List of matching node IDs
        """
        node_ids = list(annotation_store.nodes_with_annotation(key, value))
        return {
            "key": key,
            "value": value,
            "count": len(node_ids),
            "node_ids": node_ids,
        }

    @mcp.tool()
    def clear_annotations(node_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Clear annotations and tags.

        If node_id is provided, clears only that node.
        If node_id is None, clears all annotations in the session.

        Args:
            node_id: Optional specific node to clear

        Returns:
            Result of the operation
        """
        if node_id:
            cleared = annotation_store.clear_node(node_id)
            return {
                "node_id": node_id,
                "cleared": cleared,
                "message": f"Cleared annotations for {node_id}" if cleared else f"Node {node_id} had no annotations",
            }
        else:
            count = annotation_store.clear()
            return {
                "cleared_nodes": count,
                "message": f"Cleared all annotations ({count} nodes)",
            }

    @mcp.tool()
    def annotation_stats() -> Dict[str, Any]:
        """
        Get statistics about the annotation store.

        Returns stats about nodes, annotations, and tags in the
        current session.

        Returns:
            Statistics dict
        """
        return annotation_store.stats()

    # ─────────────────────────────────────────────────────────────────────────
    # Graph Mutation Tools
    # ─────────────────────────────────────────────────────────────────────────

    @mcp.tool()
    def mutate_rename_node(
        old_id: str,
        new_id: str,
    ) -> Dict[str, Any]:
        """
        Rename a requirement node (in-memory graph mutation with undo).

        Updates the node's ID, all edges pointing to/from this node,
        and assertion IDs if the node is a requirement.

        Args:
            old_id: Current node ID (e.g., "REQ-p00001")
            new_id: New node ID (e.g., "REQ-p00002")

        Returns:
            MutationEntry with id, operation, before_state, after_state
        """
        graph, _ = ctx.get_graph()

        try:
            entry = graph.rename_node(old_id, new_id)
            return {
                "success": True,
                "mutation": serialize_mutation_entry(entry),
                "message": f"Renamed {old_id} to {new_id}",
            }
        except KeyError as e:
            return {"success": False, "error": str(e)}
        except ValueError as e:
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def mutate_update_title(
        node_id: str,
        new_title: str,
    ) -> Dict[str, Any]:
        """
        Update a requirement's title (in-memory graph mutation with undo).

        Does not affect the requirement hash.

        Args:
            node_id: The requirement ID (e.g., "REQ-p00001")
            new_title: The new title for the requirement

        Returns:
            MutationEntry with id, operation, before_state, after_state
        """
        graph, _ = ctx.get_graph()

        try:
            entry = graph.update_title(node_id, new_title)
            return {
                "success": True,
                "mutation": serialize_mutation_entry(entry),
                "message": f"Updated title for {node_id}",
            }
        except KeyError as e:
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def mutate_change_status(
        node_id: str,
        new_status: str,
    ) -> Dict[str, Any]:
        """
        Change a requirement's status (in-memory graph mutation with undo).

        Args:
            node_id: The requirement ID (e.g., "REQ-p00001")
            new_status: New status value (e.g., "Active", "Draft", "Deprecated")

        Returns:
            MutationEntry with id, operation, before_state, after_state
        """
        graph, _ = ctx.get_graph()

        try:
            entry = graph.change_status(node_id, new_status)
            return {
                "success": True,
                "mutation": serialize_mutation_entry(entry),
                "message": f"Changed status of {node_id} to {new_status}",
            }
        except KeyError as e:
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def mutate_add_requirement(
        req_id: str,
        title: str,
        level: str,
        status: str = "Draft",
        parent_id: Optional[str] = None,
        edge_kind: str = "implements",
    ) -> Dict[str, Any]:
        """
        Add a new requirement node (in-memory graph mutation with undo).

        Creates a node with the specified properties and optionally
        links it to a parent.

        Args:
            req_id: The requirement ID (e.g., "REQ-p00001")
            title: The requirement title
            level: The requirement level ("PRD", "OPS", "DEV")
            status: The requirement status (default "Draft")
            parent_id: Optional parent node ID to link to
            edge_kind: Edge type for parent link ("implements" or "refines")

        Returns:
            MutationEntry with id, operation, before_state, after_state
        """
        from elspais.graph.relations import EdgeKind

        graph, _ = ctx.get_graph()

        # Parse edge kind
        edge_kind_lower = edge_kind.lower()
        if edge_kind_lower not in ("implements", "refines"):
            return {
                "success": False,
                "error": f"Invalid edge_kind: {edge_kind}. Must be 'implements' or 'refines'",
            }
        ek = EdgeKind.IMPLEMENTS if edge_kind_lower == "implements" else EdgeKind.REFINES

        try:
            entry = graph.add_requirement(
                req_id=req_id,
                title=title,
                level=level,
                status=status,
                parent_id=parent_id,
                edge_kind=ek,
            )
            return {
                "success": True,
                "mutation": serialize_mutation_entry(entry),
                "message": f"Created requirement {req_id}",
            }
        except (KeyError, ValueError) as e:
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def mutate_delete_requirement(
        node_id: str,
        confirm: bool = False,
    ) -> Dict[str, Any]:
        """
        Delete a requirement (in-memory graph mutation with undo).

        DESTRUCTIVE: Removes the node from the graph. Children become orphans.
        Assertion children are deleted with the requirement.

        Args:
            node_id: The requirement ID to delete
            confirm: Must be True to actually delete (safety check)

        Returns:
            MutationEntry with id, operation, before_state, after_state
        """
        if not confirm:
            return {
                "success": False,
                "error": "Set confirm=True to delete the requirement. This is a destructive operation.",
                "hint": "Use undo_last_mutation() to reverse if needed after deletion.",
            }

        graph, _ = ctx.get_graph()

        try:
            entry = graph.delete_requirement(node_id)
            return {
                "success": True,
                "mutation": serialize_mutation_entry(entry),
                "message": f"Deleted requirement {node_id}. Use undo_last_mutation() to reverse.",
            }
        except KeyError as e:
            return {"success": False, "error": str(e)}

    # ─────────────────────────────────────────────────────────────────────────
    # Assertion Mutation Tools
    # ─────────────────────────────────────────────────────────────────────────

    @mcp.tool()
    def mutate_add_assertion(
        req_id: str,
        label: str,
        text: str,
    ) -> Dict[str, Any]:
        """
        Add an assertion to a requirement (in-memory graph mutation with undo).

        Creates an assertion node, links it as child of the requirement,
        and recomputes the requirement hash.

        Args:
            req_id: The parent requirement ID (e.g., "REQ-p00001")
            label: The assertion label (e.g., "A", "B", "C")
            text: The assertion text

        Returns:
            MutationEntry with id, operation, before_state, after_state
        """
        graph, _ = ctx.get_graph()

        try:
            entry = graph.add_assertion(req_id, label, text)
            return {
                "success": True,
                "mutation": serialize_mutation_entry(entry),
                "message": f"Added assertion {label} to {req_id}",
            }
        except (KeyError, ValueError) as e:
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def mutate_update_assertion(
        assertion_id: str,
        new_text: str,
    ) -> Dict[str, Any]:
        """
        Update assertion text (in-memory graph mutation with undo).

        Recomputes the parent requirement hash.

        Args:
            assertion_id: The assertion ID (e.g., "REQ-p00001-A")
            new_text: The new assertion text

        Returns:
            MutationEntry with id, operation, before_state, after_state
        """
        graph, _ = ctx.get_graph()

        try:
            entry = graph.update_assertion(assertion_id, new_text)
            return {
                "success": True,
                "mutation": serialize_mutation_entry(entry),
                "message": f"Updated assertion {assertion_id}",
            }
        except (KeyError, ValueError) as e:
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def mutate_delete_assertion(
        assertion_id: str,
        compact: bool = True,
        confirm: bool = False,
    ) -> Dict[str, Any]:
        """
        Delete an assertion with optional compaction (in-memory with undo).

        If compact=True and deleting B from [A, B, C, D]:
        - C becomes B, D becomes C
        - All edge references are updated
        - Parent hash is recomputed

        Args:
            assertion_id: The assertion ID to delete (e.g., "REQ-p00001-B")
            compact: If True, renumber subsequent assertions (default True)
            confirm: Must be True to actually delete (safety check)

        Returns:
            MutationEntry with id, operation, before_state, after_state
        """
        if not confirm:
            return {
                "success": False,
                "error": "Set confirm=True to delete the assertion. This is a destructive operation.",
                "hint": "Use undo_last_mutation() to reverse if needed after deletion.",
            }

        graph, _ = ctx.get_graph()

        try:
            entry = graph.delete_assertion(assertion_id, compact=compact)
            return {
                "success": True,
                "mutation": serialize_mutation_entry(entry),
                "message": f"Deleted assertion {assertion_id}. Use undo_last_mutation() to reverse.",
            }
        except (KeyError, ValueError) as e:
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def mutate_rename_assertion(
        old_id: str,
        new_label: str,
    ) -> Dict[str, Any]:
        """
        Rename an assertion label (in-memory graph mutation with undo).

        Updates the assertion node ID, edges with assertion_targets,
        and recomputes the parent requirement hash.

        Args:
            old_id: Current assertion ID (e.g., "REQ-p00001-A")
            new_label: New assertion label (e.g., "D")

        Returns:
            MutationEntry with id, operation, before_state, after_state
        """
        graph, _ = ctx.get_graph()

        try:
            entry = graph.rename_assertion(old_id, new_label)
            return {
                "success": True,
                "mutation": serialize_mutation_entry(entry),
                "message": f"Renamed assertion {old_id} to label {new_label}",
            }
        except (KeyError, ValueError) as e:
            return {"success": False, "error": str(e)}

    # ─────────────────────────────────────────────────────────────────────────
    # Edge Mutation Tools
    # ─────────────────────────────────────────────────────────────────────────

    @mcp.tool()
    def mutate_add_edge(
        source_id: str,
        target_id: str,
        edge_kind: str,
        assertion_targets: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Add a new edge/relationship (in-memory graph mutation with undo).

        Creates a relationship from source to target. If target doesn't exist,
        adds to broken_references instead of creating an edge.

        Args:
            source_id: The child/source node ID (the one implementing)
            target_id: The parent/target node ID (the one being implemented)
            edge_kind: Relationship type ("implements", "refines", "validates")
            assertion_targets: Optional assertion labels targeted (e.g., ["A", "B"])

        Returns:
            MutationEntry with id, operation, before_state, after_state
        """
        from elspais.graph.relations import EdgeKind

        graph, _ = ctx.get_graph()

        # Parse edge kind
        edge_kind_lower = edge_kind.lower()
        try:
            ek = EdgeKind(edge_kind_lower)
        except ValueError:
            return {
                "success": False,
                "error": f"Invalid edge_kind: {edge_kind}. Must be one of: implements, refines, validates, addresses, contains",
            }

        try:
            entry = graph.add_edge(source_id, target_id, ek, assertion_targets)
            broken = entry.after_state.get("broken", False)
            if broken:
                return {
                    "success": True,
                    "mutation": serialize_mutation_entry(entry),
                    "message": f"Added broken reference: {source_id} -> {target_id} (target not found)",
                    "warning": "Target node not found - added as broken reference",
                }
            return {
                "success": True,
                "mutation": serialize_mutation_entry(entry),
                "message": f"Added edge: {source_id} --[{edge_kind}]--> {target_id}",
            }
        except KeyError as e:
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def mutate_change_edge_kind(
        source_id: str,
        target_id: str,
        new_kind: str,
    ) -> Dict[str, Any]:
        """
        Change edge type (in-memory graph mutation with undo).

        Switches the relationship type between two nodes
        (e.g., IMPLEMENTS -> REFINES).

        Args:
            source_id: The child/source node ID
            target_id: The parent/target node ID
            new_kind: New edge type ("implements", "refines", etc.)

        Returns:
            MutationEntry with id, operation, before_state, after_state
        """
        from elspais.graph.relations import EdgeKind

        graph, _ = ctx.get_graph()

        # Parse edge kind
        new_kind_lower = new_kind.lower()
        try:
            ek = EdgeKind(new_kind_lower)
        except ValueError:
            return {
                "success": False,
                "error": f"Invalid new_kind: {new_kind}. Must be one of: implements, refines, validates, addresses, contains",
            }

        try:
            entry = graph.change_edge_kind(source_id, target_id, ek)
            old_kind = entry.before_state.get("edge_kind", "unknown")
            return {
                "success": True,
                "mutation": serialize_mutation_entry(entry),
                "message": f"Changed edge {source_id} -> {target_id} from {old_kind} to {new_kind}",
            }
        except (KeyError, ValueError) as e:
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def mutate_delete_edge(
        source_id: str,
        target_id: str,
        confirm: bool = False,
    ) -> Dict[str, Any]:
        """
        Remove an edge/relationship (in-memory graph mutation with undo).

        Removes the relationship between two nodes. If source has no
        other parents, it may become an orphan.

        Args:
            source_id: The child/source node ID
            target_id: The parent/target node ID
            confirm: Must be True to actually delete (safety check)

        Returns:
            MutationEntry with id, operation, before_state, after_state
        """
        if not confirm:
            return {
                "success": False,
                "error": "Set confirm=True to delete the edge. This may create orphan nodes.",
                "hint": "Use undo_last_mutation() to reverse if needed after deletion.",
            }

        graph, _ = ctx.get_graph()

        try:
            entry = graph.delete_edge(source_id, target_id)
            became_orphan = entry.after_state.get("became_orphan", False)
            if became_orphan:
                return {
                    "success": True,
                    "mutation": serialize_mutation_entry(entry),
                    "message": f"Deleted edge {source_id} -> {target_id}",
                    "warning": f"Node {source_id} is now orphaned (no parents)",
                }
            return {
                "success": True,
                "mutation": serialize_mutation_entry(entry),
                "message": f"Deleted edge {source_id} -> {target_id}",
            }
        except (KeyError, ValueError) as e:
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def mutate_fix_broken_reference(
        source_id: str,
        old_target_id: str,
        new_target_id: str,
    ) -> Dict[str, Any]:
        """
        Fix a broken reference by redirecting to a new target (with undo).

        Finds a broken reference from source to old_target and redirects
        it to new_target. If new_target also doesn't exist, the reference
        remains broken (but with updated target).

        Args:
            source_id: The source node ID with the broken reference
            old_target_id: The current (broken) target ID
            new_target_id: The new target ID to point to

        Returns:
            MutationEntry with id, operation, before_state, after_state
        """
        graph, _ = ctx.get_graph()

        try:
            entry = graph.fix_broken_reference(source_id, old_target_id, new_target_id)
            fixed = entry.after_state.get("fixed", False)
            still_broken = entry.after_state.get("still_broken", False)

            if fixed:
                return {
                    "success": True,
                    "mutation": serialize_mutation_entry(entry),
                    "message": f"Fixed reference: {source_id} now points to {new_target_id}",
                }
            elif still_broken:
                return {
                    "success": True,
                    "mutation": serialize_mutation_entry(entry),
                    "message": f"Redirected broken reference to {new_target_id}",
                    "warning": f"Reference still broken - target {new_target_id} not found",
                }
            return {
                "success": True,
                "mutation": serialize_mutation_entry(entry),
                "message": f"Updated reference from {old_target_id} to {new_target_id}",
            }
        except (KeyError, ValueError) as e:
            return {"success": False, "error": str(e)}

    # ─────────────────────────────────────────────────────────────────────────
    # Undo and Inspection Tools
    # ─────────────────────────────────────────────────────────────────────────

    @mcp.tool()
    def undo_last_mutation() -> Dict[str, Any]:
        """
        Undo the most recent graph mutation.

        Reverses the last mutation using its before_state and removes
        it from the mutation log.

        Returns:
            The undone MutationEntry, or error if log is empty
        """
        graph, _ = ctx.get_graph()

        entry = graph.undo_last()
        if entry is None:
            return {
                "success": False,
                "error": "No mutations to undo",
            }

        return {
            "success": True,
            "undone": serialize_mutation_entry(entry),
            "message": f"Undone: {entry.operation}({entry.target_id})",
        }

    @mcp.tool()
    def undo_to_mutation(mutation_id: str) -> Dict[str, Any]:
        """
        Undo all mutations back to (and including) a specific mutation.

        Batch undo for reverting multiple operations at once.

        Args:
            mutation_id: The mutation ID to undo back to

        Returns:
            List of undone MutationEntry instances
        """
        graph, _ = ctx.get_graph()

        try:
            entries = graph.undo_to(mutation_id)
            return {
                "success": True,
                "count": len(entries),
                "undone": [serialize_mutation_entry(e) for e in entries],
                "message": f"Undone {len(entries)} mutations",
            }
        except ValueError as e:
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def get_mutation_log(limit: int = 50) -> Dict[str, Any]:
        """
        Get the mutation history for the current graph.

        Args:
            limit: Maximum number of entries to return (default 50)

        Returns:
            List of MutationEntry instances in chronological order
        """
        graph, _ = ctx.get_graph()

        entries = list(graph.mutation_log.iter_entries())
        total = len(entries)

        # Return most recent entries up to limit
        if len(entries) > limit:
            entries = entries[-limit:]

        return {
            "total": total,
            "returned": len(entries),
            "entries": [serialize_mutation_entry(e) for e in entries],
        }

    @mcp.tool()
    def get_orphaned_nodes() -> Dict[str, Any]:
        """
        Get all orphaned nodes in the graph.

        Orphans are nodes without parents that aren't roots.
        These typically indicate broken relationships.

        Returns:
            List of orphaned node IDs with basic info
        """
        graph, _ = ctx.get_graph()

        orphans = []
        for node in graph.orphaned_nodes():
            orphans.append({
                "id": node.id,
                "kind": node.kind.value,
                "label": node.get_label(),
            })

        return {
            "count": len(orphans),
            "orphans": orphans,
        }

    @mcp.tool()
    def get_broken_references() -> Dict[str, Any]:
        """
        Get all broken references in the graph.

        Broken references are links to non-existent targets,
        typically from typos or missing requirements.

        Returns:
            List of BrokenReference instances
        """
        graph, _ = ctx.get_graph()

        refs = graph.broken_references()
        return {
            "count": len(refs),
            "references": [serialize_broken_reference(r) for r in refs],
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
