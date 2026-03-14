# Implements: REQ-d00131-A, REQ-d00131-B, REQ-d00131-C, REQ-d00131-D
# Implements: REQ-d00131-E, REQ-d00131-F, REQ-d00131-G, REQ-d00131-H
# Implements: REQ-d00131-I, REQ-d00131-J
"""Render Protocol - Serialize graph nodes back to text.

Each domain NodeKind has a render function that produces its text
representation. Walking a FILE node's CONTAINS children in render_order
and concatenating their rendered output produces the file's content.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from elspais.graph.GraphNode import GraphNode, NodeKind
from elspais.graph.relations import EdgeKind
from elspais.utilities.hasher import normalize_assertion_text

if TYPE_CHECKING:
    pass


def render_node(node: GraphNode) -> str:
    """Render a graph node back to its text representation.

    Dispatches to the appropriate renderer based on NodeKind.

    Args:
        node: The graph node to render.

    Returns:
        The text representation of the node.

    Raises:
        ValueError: If the node kind cannot be rendered independently
            (ASSERTION, TEST_RESULT).
    """
    # Implements: REQ-d00131-A
    kind = node.kind

    if kind == NodeKind.REQUIREMENT:
        return _render_requirement(node)
    elif kind == NodeKind.ASSERTION:
        # Implements: REQ-d00131-C
        raise ValueError(
            "ASSERTION nodes are rendered by their parent REQUIREMENT, "
            "not independently. Use render_node() on the parent REQUIREMENT."
        )
    elif kind == NodeKind.REMAINDER:
        return _render_remainder(node)
    elif kind == NodeKind.USER_JOURNEY:
        return _render_journey(node)
    elif kind == NodeKind.CODE:
        return _render_code(node)
    elif kind == NodeKind.TEST:
        return _render_test(node)
    elif kind == NodeKind.TEST_RESULT:
        # Implements: REQ-d00131-H
        raise ValueError("TEST_RESULT nodes are read-only and cannot be rendered back to disk.")
    elif kind == NodeKind.FILE:
        return render_file(node)
    else:
        raise ValueError(f"Unknown NodeKind: {kind}")


# Implements: REQ-d00131-B
def _render_requirement(node: GraphNode) -> str:
    """Render a REQUIREMENT node to its full text block.

    Produces:
    - Header line: ## REQ-xxx: Title
    - Metadata line: **Level**: X | **Status**: Y | **Implements**: Z
    - Preamble body text (from STRUCTURES REMAINDER children with heading="preamble")
    - ## Assertions heading + assertion lines (from STRUCTURES ASSERTION children)
    - Non-normative sections (from STRUCTURES REMAINDER children)
    - *End* marker with hash
    - --- separator
    """
    req_id = node.id
    title = node.get_label()
    level = node.get_field("level") or "Unknown"
    status = node.get_field("status") or "Unknown"
    implements_refs = node.get_field("implements_refs") or []

    lines: list[str] = []

    # Header
    lines.append(f"## {req_id}: {title}")
    lines.append("")

    # Metadata line
    meta_parts = [f"**Level**: {level}", f"**Status**: {status}"]
    if implements_refs:
        impl_str = ", ".join(implements_refs)
        meta_parts.append(f"**Implements**: {impl_str}")
    else:
        meta_parts.append("**Implements**: -")
    lines.append(" | ".join(meta_parts))

    # Collect STRUCTURES children: assertions and sections
    assertions: list[tuple[str, str]] = []
    preamble_text: str | None = None
    named_sections: list[tuple[str, str]] = []

    for child in node.iter_children(edge_kinds={EdgeKind.STRUCTURES}):
        if child.kind == NodeKind.ASSERTION:
            label = child.get_field("label") or ""
            text = child.get_label()
            assertions.append((label, text))
        elif child.kind == NodeKind.REMAINDER:
            heading = child.get_field("heading") or "preamble"
            content = child.get_field("text") or ""
            if heading == "preamble":
                preamble_text = content
            else:
                named_sections.append((heading, content))

    # Preamble body text
    if preamble_text:
        lines.append("")
        lines.append(preamble_text)

    # Assertions section
    if assertions:
        lines.append("")
        lines.append("## Assertions")
        lines.append("")
        for label, text in assertions:
            lines.append(f"{label}. {text}")
            lines.append("")

    # Named sections (Rationale, Notes, etc.)
    for heading, content in named_sections:
        lines.append(f"## {heading}")
        lines.append("")
        lines.append(content)
        lines.append("")

    # Compute hash using order-independent assertion hashing
    hash_val = compute_requirement_hash(assertions)

    # End marker
    lines.append(f"*End* *{title}* | **Hash**: {hash_val}")
    lines.append("---")

    return "\n".join(lines)


# Implements: REQ-d00131-D
def _render_remainder(node: GraphNode) -> str:
    """Render a REMAINDER node back to its raw text.

    Returns the stored text verbatim, preserving all whitespace.
    """
    return node.get_field("text") or ""


# Implements: REQ-d00131-E
def _render_journey(node: GraphNode) -> str:
    """Render a USER_JOURNEY node back to its full block.

    Returns the stored body text which contains the complete journey block.
    """
    return node.get_field("body") or ""


# Implements: REQ-d00131-F
def _render_code(node: GraphNode) -> str:
    """Render a CODE node back to its comment line(s).

    Returns the raw text of the # Implements: comment line(s).
    """
    return node.get_field("raw_text") or ""


# Implements: REQ-d00131-G
def _render_test(node: GraphNode) -> str:
    """Render a TEST node back to its comment line(s).

    Returns the raw text of the # Tests: / # Validates: comment line(s).
    """
    return node.get_field("raw_text") or ""


# Implements: REQ-d00131-I
def render_file(node: GraphNode) -> str:
    """Render a FILE node by walking its CONTAINS children.

    Walks CONTAINS children sorted by render_order edge metadata,
    calls render_node on each, and concatenates the results.

    Args:
        node: A FILE node.

    Returns:
        The complete file content as a string.
    """
    if node.kind != NodeKind.FILE:
        raise ValueError(f"render_file() requires a FILE node, got {node.kind}")

    # Collect CONTAINS children with their render_order
    children_with_order: list[tuple[float, GraphNode]] = []

    for edge in node.iter_outgoing_edges():
        if edge.kind == EdgeKind.CONTAINS:
            order = edge.metadata.get("render_order", 0.0)
            children_with_order.append((order, edge.target))

    if not children_with_order:
        return ""

    # Sort by render_order
    children_with_order.sort(key=lambda x: x[0])

    # Render each child and concatenate
    parts: list[str] = []
    for _order, child in children_with_order:
        rendered = render_node(child)
        if rendered:
            parts.append(rendered)

    return "\n".join(parts)


# Implements: REQ-d00131-J
def compute_requirement_hash(
    assertions: list[tuple[str, str]],
    length: int = 8,
    algorithm: str = "sha256",
) -> str:
    """Compute requirement hash using order-independent assertion hashing.

    1. Compute normalized text hash for each assertion individually.
    2. Sort the individual assertion hashes lexicographically.
    3. Hash the sorted collection into the requirement's final hash.

    This ensures assertion reordering does not trigger change-detection
    review, while assertion text edits still do.

    Args:
        assertions: List of (label, text) tuples.
        length: Number of characters in the hash (default 8).
        algorithm: Hash algorithm to use (default "sha256").

    Returns:
        Hexadecimal hash string of specified length.
    """
    if not assertions:
        # Empty assertions: hash empty string
        h = hashlib.sha256(b"")
        return h.hexdigest()[:length]

    # Step 1: Compute individual assertion hashes
    individual_hashes: list[str] = []
    for label, text in assertions:
        normalized = normalize_assertion_text(label, text)
        if algorithm == "sha256":
            h = hashlib.sha256(normalized.encode("utf-8"))
        else:
            raise ValueError(f"Unsupported algorithm: {algorithm}")
        individual_hashes.append(h.hexdigest())

    # Step 2: Sort lexicographically
    individual_hashes.sort()

    # Step 3: Hash the sorted collection
    combined = "\n".join(individual_hashes)
    if algorithm == "sha256":
        final = hashlib.sha256(combined.encode("utf-8"))
    else:
        raise ValueError(f"Unsupported algorithm: {algorithm}")

    return final.hexdigest()[:length]
