"""
Hierarchy scanning and traversal utilities.

Centralized functions for requirement hierarchy operations:
- ID resolution and normalization
- Parent/child discovery
- Cycle detection
- Hierarchy traversal
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from elspais.core.models import Requirement


@dataclass
class CycleInfo:
    """Pure data structure for cycle detection results."""

    cycle_members: Set[str] = field(default_factory=set)
    cycle_paths: List[List[str]] = field(default_factory=list)


# -----------------------------------------------------------------------------
# ID Resolution
# -----------------------------------------------------------------------------


def find_requirement(
    impl_id: str,
    requirements: Dict[str, Requirement],
    normalize: bool = True,
) -> Optional[Requirement]:
    """Find requirement by ID with flexible matching.

    Matching order:
    1. Exact match
    2. With REQ- prefix added
    3. Suffix match (slowest)

    Args:
        impl_id: The requirement ID to find (full or partial)
        requirements: Dict mapping requirement ID to Requirement
        normalize: Whether to try normalized forms (default True)

    Returns:
        The matching Requirement or None if not found
    """
    if not impl_id or not requirements:
        return None

    # 1. Exact match
    if impl_id in requirements:
        return requirements[impl_id]

    if normalize:
        # 2. Try with REQ- prefix
        prefixed_id = f"REQ-{impl_id}" if not impl_id.startswith("REQ-") else impl_id
        if prefixed_id in requirements:
            return requirements[prefixed_id]

    # 3. Suffix match (for partial IDs like "p00001" matching "REQ-p00001")
    for req_id, req in requirements.items():
        if req_id.endswith(impl_id) or req_id.endswith(f"-{impl_id}"):
            return req

    return None


def resolve_id(
    impl_id: str,
    requirements: Dict[str, Requirement],
) -> Optional[str]:
    """Same as find_requirement but returns ID string.

    Args:
        impl_id: The requirement ID to resolve
        requirements: Dict mapping requirement ID to Requirement

    Returns:
        The canonical requirement ID or None if not found
    """
    req = find_requirement(impl_id, requirements)
    return req.id if req else None


def normalize_req_id(req_id: str, prefix: str = "REQ") -> str:
    """Normalize ID to canonical format.

    Examples:
        'd00027' -> 'REQ-d00027'
        'REQ-d00027' -> 'REQ-d00027'
        '001' with prefix='JIRA' -> 'JIRA-001'

    Args:
        req_id: The requirement ID to normalize
        prefix: The prefix to use (default "REQ")

    Returns:
        Normalized ID with prefix
    """
    if req_id.startswith(f"{prefix}-"):
        return req_id
    return f"{prefix}-{req_id}"


# -----------------------------------------------------------------------------
# Child/Parent Discovery
# -----------------------------------------------------------------------------


def find_children(
    req_id: str,
    requirements: Dict[str, Requirement],
) -> List[Requirement]:
    """Find all requirements that implement the given requirement.

    Args:
        req_id: The parent requirement ID
        requirements: Dict mapping requirement ID to Requirement

    Returns:
        Sorted list of Requirement objects that implement req_id
    """
    children = []
    short_id = req_id.split("-")[-1] if "-" in req_id else req_id

    for other_req in requirements.values():
        for impl in other_req.implements:
            if impl == req_id or impl == short_id or impl.endswith(short_id):
                children.append(other_req)
                break

    return sorted(children, key=lambda r: r.id)


def find_children_ids(
    req_id: str,
    requirements: Dict[str, Requirement],
) -> List[str]:
    """Same as find_children but returns list of ID strings.

    Args:
        req_id: The parent requirement ID
        requirements: Dict mapping requirement ID to Requirement

    Returns:
        List of requirement IDs that implement req_id
    """
    return [child.id for child in find_children(req_id, requirements)]


# -----------------------------------------------------------------------------
# Hierarchy Building
# -----------------------------------------------------------------------------


def build_children_index(
    requirements: Dict[str, Requirement],
) -> Dict[str, List[str]]:
    """Build parent_id -> [child_ids] mapping.

    Args:
        requirements: Dict mapping requirement ID to Requirement

    Returns:
        Dict mapping each parent ID to list of child IDs
    """
    index: Dict[str, List[str]] = {}

    for req_id, req in requirements.items():
        for impl in req.implements:
            # Normalize the parent ID for consistent lookup
            parent_id = resolve_id(impl, requirements)
            if parent_id is None:
                # Parent doesn't exist - use the raw impl value
                parent_id = impl

            if parent_id not in index:
                index[parent_id] = []
            index[parent_id].append(req_id)

    # Sort children for consistent ordering
    for parent_id in index:
        index[parent_id].sort()

    return index


# -----------------------------------------------------------------------------
# Cycle Detection
# -----------------------------------------------------------------------------


def detect_cycles(
    requirements: Dict[str, Requirement],
) -> CycleInfo:
    """Detect circular dependencies. PURE - no mutation.

    Uses DFS to find cycles in the implements graph.

    Args:
        requirements: Dict mapping requirement ID to Requirement

    Returns:
        CycleInfo with cycle_members and cycle_paths
    """
    visited: Set[str] = set()
    rec_stack: Set[str] = set()
    cycle_members: Set[str] = set()
    cycle_paths: List[List[str]] = []

    def _normalize_parent_id(parent_id: str) -> Optional[str]:
        """Normalize parent ID for lookup."""
        # Try exact match
        if parent_id in requirements:
            return parent_id

        # Try with REQ- prefix
        if not parent_id.startswith("REQ-"):
            prefixed = f"REQ-{parent_id}"
            if prefixed in requirements:
                return prefixed

        # Try suffix match
        for req_id in requirements:
            if req_id.endswith(parent_id) or req_id.endswith(f"-{parent_id}"):
                return req_id

        return None

    def dfs(req_id: str, path: List[str]) -> None:
        if req_id in rec_stack:
            # Found cycle - extract cycle path
            if req_id in path:
                cycle_start = path.index(req_id)
                cycle_path = path[cycle_start:] + [req_id]
                cycle_paths.append(cycle_path)
                for member in path[cycle_start:]:
                    cycle_members.add(member)
            return

        if req_id in visited:
            return

        visited.add(req_id)
        rec_stack.add(req_id)

        req = requirements.get(req_id)
        if req:
            for parent_id in req.implements:
                # Normalize parent_id for lookup
                normalized = _normalize_parent_id(parent_id)
                if normalized and normalized in requirements:
                    dfs(normalized, path + [req_id])

        rec_stack.remove(req_id)

    # Run DFS from each requirement
    for req_id in requirements:
        if req_id not in visited:
            dfs(req_id, [])

    return CycleInfo(cycle_members=cycle_members, cycle_paths=cycle_paths)


# -----------------------------------------------------------------------------
# Traversal
# -----------------------------------------------------------------------------


def traverse_top_down(
    requirements: Dict[str, Requirement],
    start_id: str,
    children_index: Optional[Dict[str, List[str]]] = None,
) -> List[str]:
    """BFS traversal from start node downward.

    Args:
        requirements: Dict mapping requirement ID to Requirement
        start_id: ID to start traversal from
        children_index: Optional pre-built children index

    Returns:
        List of requirement IDs in BFS order
    """
    if children_index is None:
        children_index = build_children_index(requirements)

    result = []
    visited = set()
    queue = [start_id]

    while queue:
        current = queue.pop(0)
        if current in visited:
            continue

        visited.add(current)
        if current in requirements:
            result.append(current)

        # Add children to queue
        for child_id in children_index.get(current, []):
            if child_id not in visited:
                queue.append(child_id)

    return result


def traverse_bottom_up(
    requirements: Dict[str, Requirement],
    start_id: str,
) -> List[str]:
    """Follow implements chain upward to roots.

    Args:
        requirements: Dict mapping requirement ID to Requirement
        start_id: ID to start traversal from

    Returns:
        List of requirement IDs from start to root(s)
    """
    result = []
    visited = set()
    queue = [start_id]

    while queue:
        current = queue.pop(0)
        if current in visited:
            continue

        visited.add(current)

        req = find_requirement(current, requirements)
        if req:
            result.append(req.id)
            # Add parents to queue
            for impl in req.implements:
                parent = find_requirement(impl, requirements)
                if parent and parent.id not in visited:
                    queue.append(parent.id)

    return result


# -----------------------------------------------------------------------------
# Utilities
# -----------------------------------------------------------------------------


def find_roots(requirements: Dict[str, Requirement]) -> List[str]:
    """Find PRD requirements with no implements.

    Args:
        requirements: Dict mapping requirement ID to Requirement

    Returns:
        List of root requirement IDs
    """
    roots = []
    for req_id, req in requirements.items():
        # PRD level (level 1) or requirements with no implements
        is_prd = req.level.upper() == "PRD" or "p" in req_id.lower().split("-")[-1][:1]
        if is_prd and not req.implements:
            roots.append(req_id)

    return sorted(roots)


def find_orphans(requirements: Dict[str, Requirement]) -> List[str]:
    """Find non-PRD requirements with no valid implements (broken links).

    Args:
        requirements: Dict mapping requirement ID to Requirement

    Returns:
        List of orphaned requirement IDs
    """
    orphans = []
    for req_id, req in requirements.items():
        # Skip PRD level requirements - they're roots, not orphans
        is_prd = req.level.upper() == "PRD" or "p" in req_id.lower().split("-")[-1][:1]
        if is_prd:
            continue

        # Non-PRD with no implements is potentially orphaned
        if not req.implements:
            orphans.append(req_id)
            continue

        # Check if all implements point to non-existent requirements
        has_valid_parent = False
        for impl in req.implements:
            if find_requirement(impl, requirements) is not None:
                has_valid_parent = True
                break

        if not has_valid_parent:
            orphans.append(req_id)

    return sorted(orphans)
