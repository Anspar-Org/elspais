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
            "MCP dependencies not installed. "
            "Install with: pip install elspais[mcp]"
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
        return json.dumps({
            "count": len(requirements),
            "requirements": [
                serialize_requirement_summary(req)
                for req in requirements.values()
            ]
        }, indent=2)

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
        filtered = [
            r for r in requirements.values()
            if r.level.upper() == level.upper()
        ]
        return json.dumps({
            "level": level,
            "count": len(filtered),
            "requirements": [serialize_requirement_summary(r) for r in filtered]
        }, indent=2)

    @mcp.resource("content-rules://list")
    def list_content_rules() -> str:
        """List all configured content rule files."""
        import json
        rules = ctx.get_content_rules()
        return json.dumps({
            "count": len(rules),
            "rules": [
                {
                    "file": str(r.file_path),
                    "title": r.title,
                    "type": r.type,
                    "applies_to": r.applies_to,
                }
                for r in rules
            ]
        }, indent=2)

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
            "summary": f"{len(errors)} errors, {len(warnings)} warnings in {len(requirements)} requirements"
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
                req_id: serialize_requirement(req)
                for req_id, req in requirements.items()
            }
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
            "requirements": [serialize_requirement_summary(r) for r in results]
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
                orphans.append({
                    "id": req.id,
                    "missing_parent": parent_id,
                })

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
