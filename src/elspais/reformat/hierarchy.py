# Implements: REQ-int-d00008 (Reformat Command)
"""
Hierarchy traversal logic for requirements.

Uses TraceGraphBuilder from core modules to build the requirement hierarchy.
"""

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Dict, List, Optional

if TYPE_CHECKING:
    from elspais.core.models import Requirement


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
    Get all requirements using core parser and build hierarchy using TraceGraphBuilder.

    Args:
        config_path: Optional path to .elspais.toml config file
        base_path: Base path for resolving relative directories
        mode: Which repos to include:
            - "combined" (default): Load local + core/associated repo requirements
            - "core-only": Load only core/associated repo requirements
            - "local-only": Load only local requirements

    Returns:
        Dict mapping requirement ID (e.g., 'REQ-d00027') to RequirementNode
        with children populated via TraceGraphBuilder
    """
    from elspais.config.loader import find_config_file, get_spec_directories, load_config
    from elspais.core.graph import NodeKind
    from elspais.core.graph_builder import TraceGraphBuilder
    from elspais.core.loader import (
        load_requirements_from_directories,
        load_requirements_from_repo,
    )

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

    core_requirements = {}

    # Load local requirements (unless core-only mode)
    if mode in ("combined", "local-only"):
        spec_dirs = get_spec_directories(None, config, base_path or config_path.parent)

        if spec_dirs:
            try:
                local_reqs = load_requirements_from_directories(spec_dirs, config)
                core_requirements.update(local_reqs)
            except Exception as e:
                print(f"Warning: Failed to parse local requirements: {e}", file=sys.stderr)

    # Load core/associated repo requirements (unless local-only mode)
    if mode in ("combined", "core-only"):
        core_path = config.get("core", {}).get("path")
        if core_path:
            repo_reqs = load_requirements_from_repo(Path(core_path), config)
            for req_id, req in repo_reqs.items():
                # Don't overwrite local requirements with same ID
                if req_id not in core_requirements:
                    core_requirements[req_id] = req

    if not core_requirements:
        print("Warning: No requirements found", file=sys.stderr)
        return {}

    # Build graph to get hierarchy
    repo_root = config_path.parent if config_path else Path.cwd()
    builder = TraceGraphBuilder(repo_root=repo_root)
    builder.add_requirements(core_requirements)
    graph = builder.build()

    # Convert to RequirementNode with children from graph
    requirements: Dict[str, RequirementNode] = {}
    for req_id, req in core_requirements.items():
        requirements[req_id] = RequirementNode.from_core(req)

    # Populate children from graph
    for node in graph.all_nodes():
        if node.kind != NodeKind.REQUIREMENT:
            continue
        if node.id not in requirements:
            continue

        # Get children (requirements that implement this one)
        child_ids = [
            c.id for c in node.children
            if c.kind == NodeKind.REQUIREMENT
        ]
        requirements[node.id].children = sorted(child_ids)

    return requirements


def traverse_top_down(
    requirements: Dict[str, RequirementNode],
    start_req: str,
    max_depth: Optional[int] = None,
    callback: Optional[Callable[[RequirementNode, int], None]] = None,
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
