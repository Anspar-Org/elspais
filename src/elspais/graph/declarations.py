"""Named declarations a project makes in its configuration, held as nodes.

A configuration document is graph content (REQ-d00299-A), and the values a
consumer reads are a derivation over it (REQ-d00299-B). Neither makes
anything *inside* a document addressable: a scope a project declares under
a name was a key in a table, reachable only by reading the whole document.
This module gives each such declaration a node of its own, beneath the
document that declares it, so it can be addressed, versioned and -- once
the mutations are written -- changed (REQ-d00299-D).

One convention breaks here, and it is easy to misread. For a spec file the
``CONTAINS`` children in ``render_order`` ARE the file's text: the renderer
walks them and concatenates their output. For a configuration document they
are not. The document is the text, and ``CONFIG``'s renderer dumps it.
These children exist for addressing and versioning, and that renderer
ignores them entirely.

Which tables are held this way is :data:`DECLARED_TABLES`. It is narrow on
purpose, and the narrowness is the rule rather than a stage of work: a
setting becomes changeable when someone has written the means to change it
coherently, so the set grows with those functions and never with the
schema.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import tomlkit

from elspais.graph.GraphNode import (
    FileType,
    GraphNode,
    NodeKind,
    make_declaration_id,
)
from elspais.graph.relations import EdgeKind

# The configuration tables whose named entries are held as nodes. `scopes`
# is the first because a scope declaration shapes nothing: no requirement,
# edge or metric depends on one, so adding, changing, renaming and removing
# one are all coherent (REQ-d00299 Rationale).
DECLARED_TABLES: tuple[str, ...] = ("scopes",)


# Implements: REQ-d00299-D
def build_declaration_nodes(config_node: GraphNode) -> list[GraphNode]:
    """A node for every named declaration the given document makes.

    Each node is linked beneath the document by a ``CONTAINS`` edge and
    carries the declaration itself, so a reader reaches a declaration
    without walking the document for it.

    The edges carry no ``render_order``: for this file type the children are
    not the file's text, so there is no order to render them in, and giving
    them one would read as a claim that there is.

    Args:
        config_node: A FILE node of the ``CONFIG`` type.

    Returns:
        The declaration nodes created, in the order the document declares
        them.
    """
    document = config_node.get_field("config_document")
    if document is None:
        return []

    namespace = _namespace_of(config_node)
    relative_path = str(config_node.get_field("relative_path") or "")
    created: list[GraphNode] = []

    for table in DECLARED_TABLES:
        declared = document.get(table)
        if not hasattr(declared, "keys"):
            continue
        for name in list(declared.keys()):
            node = GraphNode(
                id=make_declaration_id(namespace, relative_path, table, str(name)),
                kind=NodeKind.DECLARATION,
            )
            node.set_field("declares_table", table)
            node.set_field("declared_name", str(name))
            node.set_field("declaration", declared[name])
            config_node.link(node, EdgeKind.CONTAINS)
            created.append(node)

    return created


def _namespace_of(config_node: GraphNode) -> str:
    """The namespace a configuration document's FILE node id names.

    A FILE id is ``file:<namespace>:<repo-relative-path>``, and a
    declaration id names the same repository, so it is read back from the
    node holding the document rather than resolved a second way.
    """
    from elspais.graph.GraphNode import parse_structural_id

    _prefix, namespace, _path, _line = parse_structural_id(config_node.id)
    return namespace


def declaration_text(node: GraphNode) -> str:
    """The text of the declaration a node holds.

    This is what a version is taken from, so it is the document's own
    spelling -- values, key order, comments and all. A comment explaining
    why a scope selects what it does is part of the declaration, and a
    change to it is a change to the declaration.
    """
    declaration = node.get_field("declaration")
    if declaration is None:
        raise ValueError(
            f"{node.id} is a declaration that holds nothing, so its text cannot be produced."
        )
    return tomlkit.dumps(declaration)


def declared_settings(node: GraphNode) -> dict[str, Any]:
    """What a declaration says, as plain values.

    Args:
        node: A DECLARATION node.

    Returns:
        The settings the declaration carries, keyed as the TOML is written.
        For a scope that is both halves of REQ-d00280-C -- the requirements
        a report is about and the values it states.
    """
    declaration = node.get_field("declaration")
    if declaration is None:
        return {}
    unwrapped = declaration.unwrap() if hasattr(declaration, "unwrap") else dict(declaration)
    return dict(unwrapped)


def iter_declarations(graph: Any, table: str | None = None) -> Iterator[GraphNode]:
    """Every named declaration a graph holds, optionally for one table.

    Args:
        graph: A ``TraceGraph``.
        table: Restrict to declarations in this configuration table.

    Yields:
        DECLARATION nodes, in index order.
    """
    for node in graph.iter_by_kind(NodeKind.DECLARATION):
        if table is None or node.get_field("declares_table") == table:
            yield node


# Implements: REQ-d00299-D
def find_declaration(graph: Any, table: str, name: str) -> GraphNode | None:
    """The declaration a graph holds under ``name`` in ``table``.

    Matching ignores case, for the reason ``declared_scope`` ignores it: a
    name a project writes on a command line and reads back out of a report
    is one name however it was capitalized.

    Where both a committed document and a machine-local overlay declare the
    name, the overlay's declaration is returned, because that is the one the
    derived configuration resolves to.

    Args:
        graph: A ``TraceGraph``.
        table: The configuration table the name is declared in.
        name: The name declared.

    Returns:
        The node, or None where the graph holds no such declaration.
    """
    from elspais.graph.held_config import iter_config_nodes

    # Read order puts the committed document first and the overlay last, so
    # the last match is the one a reader's configuration resolves to.
    order = {node.id: position for position, node in enumerate(iter_config_nodes(graph))}
    matches = [
        node
        for node in iter_declarations(graph, table)
        if node.get_field("declared_name", "").lower() == name.lower()
    ]
    if not matches:
        return None

    def _document_position(node: GraphNode) -> int:
        owner = node.file_node()
        return order.get(owner.id, -1) if owner is not None else -1

    return max(matches, key=_document_position)


def is_config_node(node: GraphNode) -> bool:
    """Whether a node is a configuration document."""
    return node.kind == NodeKind.FILE and node.get_field("file_type") is FileType.CONFIG
