# Implements: REQ-int-d00008 (Reformat Command)
"""
Hierarchy traversal logic for requirements.

Uses elspais core modules directly to parse requirements and build
a traversable hierarchy based on implements relationships.
"""

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from elspais.core.models import Requirement
    from elspais.core.patterns import PatternValidator


@dataclass
class RequirementNode:
    """Represents a requirement with its metadata and hierarchy info."""
    req_id: str
    title: str
    body: str
    rationale: str
    file_path: str
    line: int
    implements: List[str]  # Parent REQ IDs
    hash: str
    status: str
    level: str
    children: List[str] = field(default_factory=list)  # Child REQ IDs

    @classmethod
    def from_core(cls, req: "Requirement") -> "RequirementNode":
        """
        Create a RequirementNode from a core Requirement object.

        Args:
            req: Core Requirement object from elspais.core.models

        Returns:
            RequirementNode with mapped fields
        """
        return cls(
            req_id=req.id,
            title=req.title,
            body=req.body,
            rationale=req.rationale or "",
            file_path=str(req.file_path) if req.file_path else "",
            line=req.line_number or 0,
            implements=list(req.implements),
            hash=req.hash or "",
            status=req.status,
            level=req.level,
            children=[],
        )


def get_all_requirements(
    config_path: Optional[Path] = None,
    base_path: Optional[Path] = None,
    mode: str = "combined",
) -> Dict[str, RequirementNode]:
    """
    Get all requirements using core parser directly.

    Args:
        config_path: Optional path to .elspais.toml config file
        base_path: Base path for resolving relative directories
        mode: Which repos to include:
            - "combined" (default): Load local + core/associated repo requirements
            - "core-only": Load only core/associated repo requirements
            - "local-only": Load only local requirements

    Returns:
        Dict mapping requirement ID (e.g., 'REQ-d00027') to RequirementNode
    """
    from elspais.config.loader import load_config, find_config_file, get_spec_directories
    from elspais.core.parser import RequirementParser
    from elspais.core.patterns import PatternConfig
    from elspais.commands.validate import load_requirements_from_repo

    # Find and load config
    if config_path is None:
        config_path = find_config_file(base_path or Path.cwd())

    if config_path is None:
        print("Warning: No .elspais.toml found", file=sys.stderr)
        return {}

    try:
        config = load_config(config_path)
    except Exception as e:
        print(f"Warning: Failed to load config: {e}", file=sys.stderr)
        return {}

    requirements = {}

    # Load local requirements (unless core-only mode)
    if mode in ("combined", "local-only"):
        # Create parser with pattern config
        pattern_config = PatternConfig.from_dict(config.get("patterns", {}))
        parser = RequirementParser(pattern_config)

        # Get spec directories
        spec_dirs = get_spec_directories(None, config, base_path or config_path.parent)

        if spec_dirs:
            try:
                parse_result = parser.parse_directories(spec_dirs)
                for req_id, req in parse_result.requirements.items():
                    requirements[req_id] = RequirementNode.from_core(req)
            except Exception as e:
                print(f"Warning: Failed to parse local requirements: {e}", file=sys.stderr)

    # Load core/associated repo requirements (unless local-only mode)
    if mode in ("combined", "core-only"):
        core_path = config.get("core", {}).get("path")
        if core_path:
            core_reqs = load_requirements_from_repo(Path(core_path), config)
            for req_id, req in core_reqs.items():
                # Don't overwrite local requirements with same ID
                if req_id not in requirements:
                    requirements[req_id] = RequirementNode.from_core(req)

    if not requirements:
        print("Warning: No requirements found", file=sys.stderr)

    return requirements


def build_hierarchy(requirements: Dict[str, RequirementNode]) -> Dict[str, RequirementNode]:
    """
    Compute children for each requirement by inverting implements relationships.

    This modifies the requirements dict in-place, populating each node's
    children list.
    """
    for req_id, node in requirements.items():
        for parent_id in node.implements:
            # Normalize parent ID format
            parent_key = parent_id if parent_id.startswith('REQ-') else f"REQ-{parent_id}"
            if parent_key in requirements:
                requirements[parent_key].children.append(req_id)

    # Sort children for deterministic traversal
    for node in requirements.values():
        node.children.sort()

    return requirements


def traverse_top_down(
    requirements: Dict[str, RequirementNode],
    start_req: str,
    max_depth: Optional[int] = None,
    callback: Optional[Callable[[RequirementNode, int], None]] = None
) -> List[str]:
    """
    Traverse hierarchy from start_req downward using BFS.

    Args:
        requirements: All requirements with children computed
        start_req: Starting REQ ID (e.g., 'REQ-p00044')
        max_depth: Maximum depth to traverse (None = unlimited)
        callback: Function to call for each REQ visited (node, depth)

    Returns:
        List of REQ IDs in traversal order
    """
    visited = []
    queue = [(start_req, 0)]  # (req_id, depth)
    seen = set()

    while queue:
        req_id, depth = queue.pop(0)

        if req_id in seen:
            continue

        # Depth limit check (depth 0 is the start node)
        if max_depth is not None and depth > max_depth:
            continue

        seen.add(req_id)

        if req_id not in requirements:
            print(f"Warning: {req_id} not found in requirements", file=sys.stderr)
            continue

        visited.append(req_id)
        node = requirements[req_id]

        if callback:
            callback(node, depth)

        # Add children to queue
        for child_id in node.children:
            if child_id not in seen:
                queue.append((child_id, depth + 1))

    return visited


def normalize_req_id(req_id: str, validator: Optional["PatternValidator"] = None) -> str:
    """
    Normalize requirement ID to canonical format using PatternValidator.

    Args:
        req_id: Requirement ID (e.g., "d00027", "REQ-d00027", "REQ-CAL-p00001")
        validator: PatternValidator instance (created from config if not provided)

    Returns:
        Normalized ID in canonical format from config
    """
    from elspais.config.loader import load_config, find_config_file
    from elspais.core.patterns import PatternValidator, PatternConfig

    # Create validator if not provided
    if validator is None:
        try:
            config_path = find_config_file(Path.cwd())
            config = load_config(config_path) if config_path else {}
        except Exception:
            config = {}
        pattern_config = PatternConfig.from_dict(config.get("patterns", {}))
        validator = PatternValidator(pattern_config)

    # Try parsing the ID as-is
    parsed = validator.parse(req_id)

    # If that fails, try with prefix
    if parsed is None and not req_id.upper().startswith(validator.config.prefix):
        parsed = validator.parse(f"{validator.config.prefix}-{req_id}")

    if parsed:
        # Reconstruct canonical ID from parsed components
        parts = [parsed.prefix]
        if parsed.associated:
            parts.append(parsed.associated)
        parts.append(f"{parsed.type_code}{parsed.number}")
        return "-".join(parts)

    # Return as-is if unparseable
    return req_id
