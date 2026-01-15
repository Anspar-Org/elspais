# Implements: REQ-int-d00008 (Reformat Command)
"""
Hierarchy traversal logic for requirements.

Uses elspais validate --json to get all requirements and build
a traversable hierarchy based on implements relationships.
"""

import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional


@dataclass
class RequirementNode:
    """Represents a requirement with its metadata and hierarchy info."""
    req_id: str
    title: str
    body: str
    rationale: str
    file_path: str
    line: int
    implements: List[str]  # Parent REQ IDs (without REQ- prefix)
    hash: str
    status: str
    level: str
    children: List[str] = field(default_factory=list)  # Child REQ IDs


def get_repo_root() -> Path:
    """Get the repository root using git."""
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--show-toplevel'],
            capture_output=True,
            text=True,
            check=True
        )
        return Path(result.stdout.strip())
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Not in a git repository: {e}")


def get_all_requirements() -> Dict[str, RequirementNode]:
    """
    Get all requirements via elspais validate --json.

    Returns:
        Dict mapping requirement ID (e.g., 'REQ-d00027') to RequirementNode
    """
    repo_root = get_repo_root()

    try:
        result = subprocess.run(
            ['elspais', 'validate', '--json'],
            capture_output=True,
            text=True,
            cwd=str(repo_root)
        )

        # The JSON starts after the "Found N requirements" line
        output = result.stdout
        json_start = output.find('{')
        if json_start == -1:
            print("Warning: No JSON found in elspais output", file=sys.stderr)
            return {}

        json_str = output[json_start:]
        raw_data = json.loads(json_str)

        requirements = {}
        for req_id, data in raw_data.items():
            requirements[req_id] = RequirementNode(
                req_id=req_id,
                title=data.get('title', ''),
                body=data.get('body', ''),
                rationale=data.get('rationale', ''),
                file_path=data.get('filePath', ''),
                line=data.get('line', 0),
                implements=data.get('implements', []),
                hash=data.get('hash', ''),
                status=data.get('status', 'Draft'),
                level=data.get('level', 'PRD'),
                children=[]
            )

        return requirements

    except subprocess.CalledProcessError as e:
        print(f"Warning: elspais failed: {e}", file=sys.stderr)
        return {}
    except json.JSONDecodeError as e:
        print(f"Warning: Failed to parse elspais JSON: {e}", file=sys.stderr)
        return {}


def build_hierarchy(requirements: Dict[str, RequirementNode]) -> Dict[str, RequirementNode]:
    """
    Compute children for each requirement by inverting implements relationships.

    This modifies the requirements dict in-place, populating each node's
    children list.
    """
    for req_id, node in requirements.items():
        for parent_id in node.implements:
            # Normalize parent ID format
            parent_key = f"REQ-{parent_id}" if not parent_id.startswith('REQ-') else parent_id
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


def normalize_req_id(req_id: str) -> str:
    """
    Normalize requirement ID to full format with REQ- prefix.

    Handles both simple IDs (p00044) and associated IDs (CAL-REQ-p00001).
    The type letter (p, d, o) is lowercased, but associated prefixes are preserved.

    Args:
        req_id: Requirement ID (e.g., "d00027", "REQ-d00027", "CAL-REQ-p00001")

    Returns:
        Normalized ID with prefix (e.g., "REQ-d00027", "CAL-REQ-p00001")
    """
    import re

    # Check for associated prefix pattern: PREFIX-REQ-type##### (e.g., CAL-REQ-p00001)
    # The prefix must NOT be "REQ" itself
    associated_match = re.match(r'^([A-Z]+)-(?:REQ-)?([pdoPDO])(\d+)$', req_id, re.IGNORECASE)
    if associated_match:
        prefix = associated_match.group(1).upper()
        # Skip if the "prefix" is actually "REQ" - that's not an associated prefix
        if prefix != 'REQ':
            type_letter = associated_match.group(2).lower()
            number = associated_match.group(3)
            return f"{prefix}-REQ-{type_letter}{number}"

    # Check for simple REQ- prefix or bare ID: REQ-type##### or type#####
    req_match = re.match(r'^(?:REQ-)?([pdoPDO])(\d+)$', req_id, re.IGNORECASE)
    if req_match:
        type_letter = req_match.group(1).lower()
        number = req_match.group(2)
        return f"REQ-{type_letter}{number}"

    # Fallback: return as-is with REQ- prefix if missing
    if not req_id.upper().startswith('REQ-'):
        return f"REQ-{req_id}"
    return req_id
