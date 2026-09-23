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
from tomlkit.items import Comment, SingleKey, Whitespace

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


# The mutation operations that edit a configuration document. Named here
# because the one authority for how a declaration is written is also the
# one place that can say which log entries wrote one: `_find_dirty_files`
# asks this to find the document a removed declaration no longer hangs
# beneath.
DECLARATION_OPERATIONS: tuple[str, ...] = (
    "add_declaration",
    "update_declaration",
    "rename_declaration",
    "delete_declaration",
)


def declared_entries(config_node: GraphNode) -> list[tuple[str, str, Any]]:
    """Every named declaration the node's document makes, in document order.

    Args:
        config_node: A FILE node of the ``CONFIG`` type.

    Returns:
        ``(table, name, item)`` for each entry of each held table, where
        ``item`` is the tomlkit value the document holds under that name.
        Empty where the node holds no document.
    """
    return entries_in(config_node.get_field("config_document"))


def entries_in(document: Any) -> list[tuple[str, str, Any]]:
    """Every named declaration a document makes, in the order it makes them.

    Takes the document rather than the node holding it, because a change is
    judged on a document the graph does not hold yet.
    """
    if document is None:
        return []

    entries: list[tuple[str, str, Any]] = []
    for table in DECLARED_TABLES:
        declared = document.get(table)
        if not hasattr(declared, "keys"):
            continue
        entries.extend((table, str(name), declared[name]) for name in list(declared.keys()))
    return entries


def declaration_node_id(config_node: GraphNode, table: str, name: str) -> str:
    """The id the declaration under ``name`` in ``table`` is addressed by."""
    return make_declaration_id(
        _namespace_of(config_node),
        str(config_node.get_field("relative_path") or ""),
        table,
        name,
    )


def build_declaration_node(config_node: GraphNode, table: str, name: str, item: Any) -> GraphNode:
    """A node for one named declaration, linked beneath its document.

    The edge carries no ``render_order``: for this file type the children
    are not the file's text, so there is no order to render them in, and
    giving them one would read as a claim that there is.
    """
    node = GraphNode(id=declaration_node_id(config_node, table, name), kind=NodeKind.DECLARATION)
    node.set_field("declares_table", table)
    node.set_field("declared_name", name)
    node.set_field("declaration", item)
    config_node.link(node, EdgeKind.CONTAINS)
    return node


# Implements: REQ-d00299-D
def build_declaration_nodes(config_node: GraphNode) -> list[GraphNode]:
    """A node for every named declaration the given document makes.

    Each node is linked beneath the document by a ``CONTAINS`` edge and
    carries the declaration itself, so a reader reaches a declaration
    without walking the document for it.

    Args:
        config_node: A FILE node of the ``CONFIG`` type.

    Returns:
        The declaration nodes created, in the order the document declares
        them.
    """
    return [
        build_declaration_node(config_node, table, name, item)
        for table, name, item in declared_entries(config_node)
    ]


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


def document_of(config_node: GraphNode) -> Any:
    """The parsed document a configuration FILE node holds.

    Raises:
        ValueError: The node holds none, so there is nothing to change.
    """
    document = config_node.get_field("config_document")
    if document is None:
        raise ValueError(
            f"{config_node.id} is a configuration document that holds no "
            f"parsed document, so it cannot be changed."
        )
    return document


def document_text(config_node: GraphNode) -> str:
    """The text the document a node holds would be written back as."""
    return tomlkit.dumps(document_of(config_node))


def copy_document(config_node: GraphNode) -> Any:
    """A separate document holding what this node's document holds.

    A change is applied to one of these and judged before it is installed,
    so a change that would leave a configuration the tool cannot load never
    touches the document the graph is serving.
    """
    return tomlkit.parse(document_text(config_node))


def replace_document(config_node: GraphNode, text: str) -> None:
    """Put a document back as it was written, parsing it afresh.

    An undo restores the text rather than reversing the edit, because a
    document carries comments, key order and spacing that no reversal of
    values would restore. The items the old document held are discarded
    with it, so every node holding one must be re-pointed afterwards.
    """
    config_node.set_field("config_document", tomlkit.parse(text))


# Implements: REQ-d00299-D
def colliding_name(
    document: Any, table: str, name: str, *, ignoring: str | None = None
) -> str | None:
    """A name the document already declares that differs from ``name`` only in case.

    Args:
        document: The document to look in.
        table: The configuration table the name would be declared in.
        name: The name wanted.
        ignoring: A name to pass over -- the declaration being renamed,
            which cannot collide with itself, so recasing one is a rename
            and not a collision.

    Returns:
        The name already declared, or None where none collides.
    """
    for declared_table, declared_name, _item in entries_in(document):
        if declared_table != table:
            continue
        if ignoring is not None and declared_name == ignoring:
            continue
        if declared_name.lower() == name.lower():
            return declared_name
    return None


# A table's body runs from its header to the next one, so comments and blank
# lines written between a declaration's last setting and the NEXT header are
# stored INSIDE the first table while belonging, to a reader, with what
# follows. Every edit here therefore lifts that trivia off before it works and
# puts it back where it was written. Left alone it is destroyed by a removal,
# carried away by a replacement, and jumped over by an addition, each of which
# rewrites bytes nobody touched (REQ-d00299-C).


def _trailing_trivia(item: Any) -> list[Any]:
    """Cut the comments and blank lines from the end of a table's body.

    Returns:
        The body entries removed, in order, ready to be put back.
    """
    body = getattr(getattr(item, "value", None), "body", None)
    if not body:
        return []
    cut = len(body)
    while cut > 0 and body[cut - 1][0] is None:
        if not isinstance(body[cut - 1][1], (Whitespace, Comment)):
            break
        cut -= 1
    lifted = body[cut:]
    del body[cut:]
    return lifted


def _restore_trivia(item: Any, lifted: list[Any]) -> None:
    """Put lifted trivia back at the end of a table's body."""
    body = getattr(getattr(item, "value", None), "body", None)
    if body is None:
        return
    body.extend(lifted)


def _last_declared_item(holder: Any) -> Any | None:
    """The last declaration in a table, which is where its region's trivia sits."""
    body = getattr(getattr(holder, "value", None), "body", None)
    if not body:
        return None
    for key, value in reversed(body):
        if key is not None:
            return value
    return None


def _table_of(document: Any, table: str) -> Any:
    """The table ``table``, created in the document where it has none."""
    existing = document.get(table)
    if hasattr(existing, "keys"):
        return existing
    created = tomlkit.table(True)
    document[table] = created
    return document[table]


# Implements: REQ-d00299-D
def set_declaration(document: Any, table: str, name: str, settings: dict[str, Any]) -> Any:
    """Write what a declaration says, adding it where the document has none.

    A declaration is replaced rather than merged: what is written is what
    the declaration then says, so a setting left out is a setting the
    project no longer states.

    A declaration ALREADY there is edited setting by setting rather than
    assigned whole. Assigning it whole would say the same thing about what
    it declares and destroy everything written around it -- the note beside
    a setting nobody touched, the comment explaining why a setting is what
    it is -- which are the bytes REQ-d00299-C exists to keep.

    Returns:
        The item the document now holds under ``name``.
    """
    holder = _table_of(document, table)
    existing = holder[name] if name in holder else None

    if existing is None or not hasattr(existing, "keys"):
        written = tomlkit.table()
        for key, value in settings.items():
            written[key] = value
        # The region's trailing trivia introduces whatever comes AFTER these
        # declarations, so the new one goes in front of it rather than after.
        last = _last_declared_item(holder)
        lifted = _trailing_trivia(last) if last is not None else []
        holder[name] = written
        _restore_trivia(holder[name], lifted)
        return holder[name]

    lifted = _trailing_trivia(existing)
    for key in [key for key in list(existing.keys()) if key not in settings]:
        del existing[key]
    for key, value in settings.items():
        if key in existing and existing[key] == value:
            continue
        existing[key] = value
    _restore_trivia(existing, lifted)
    return existing


# Implements: REQ-d00299-D, REQ-d00299-C
def remove_declaration(document: Any, table: str, name: str) -> None:
    """Take a declaration out of the document that declares it.

    What sits between its last setting and the next header goes back where
    it was written. That text introduces the declaration that FOLLOWS, and
    losing it with the removal would rewrite a declaration nobody touched.
    The comment written ABOVE the removed declaration is a different matter
    and is left alone: it belongs to the item before it, and deciding it
    described the removed declaration would be a guess.
    """
    holder = document.get(table)
    if not hasattr(holder, "keys") or name not in holder:
        return

    lifted = _trailing_trivia(holder[name])
    # The blank line after a declaration's last setting separated THAT
    # declaration from what followed, so it goes with the removal; what
    # survives is the comment introducing the next one and everything after
    # it. Keeping the blank too would leave the document opening a gap where
    # a declaration used to be.
    while lifted and not isinstance(lifted[0][1], Comment):
        lifted.pop(0)
    container = getattr(holder, "value", None)
    slot = container._map.get(SingleKey(name)) if container is not None else None
    if isinstance(slot, tuple):
        slot = slot[-1]

    del holder[name]

    # A removal vacates its body slot rather than closing it up, so the
    # trivia goes back into that slot and every later key keeps its index.
    if lifted and container is not None and slot is not None:
        container.body[slot] = (None, Whitespace("".join(item.as_string() for _k, item in lifted)))


# Implements: REQ-d00299-D
def rename_declaration_key(document: Any, table: str, name: str, new_name: str) -> Any:
    """Respell the name a declaration is declared under, where it stands.

    Taking the entry out and putting it back under the new name would move
    it to the end of its table and leave the comment written above it
    describing whatever followed, so the key is replaced where it is.
    ``tomlkit`` publishes no rename, hence ``_replace``; the table's
    rendered header carries the old name too, so it is respelled first, and
    the blank line ``tomlkit`` adds after a replaced table is taken back
    off where the entry did not end with one -- it would otherwise detach
    the next declaration's comment from the declaration it describes.

    Returns:
        The item the document now holds under ``new_name``.
    """
    holder = _table_of(document, table)
    item = holder[name]
    body = getattr(getattr(item, "value", None), "body", None)
    ended_with_blank = bool(body) and isinstance(body[-1][1], Whitespace)

    display_name = getattr(item, "display_name", None)
    if display_name and "." in display_name:
        item.display_name = f"{display_name.rsplit('.', 1)[0]}.{new_name}"

    holder.value._replace(name, new_name, item)

    body = getattr(getattr(item, "value", None), "body", None)
    if not ended_with_blank and body and isinstance(body[-1][1], Whitespace):
        body.pop()

    # A table keeps a plain-dict shadow of its container's keys, and the
    # replace above reaches the container only. Left behind, the shadow
    # answers for a name the document no longer declares, and removing the
    # renamed declaration later raises for a key that renders correctly.
    if dict.__contains__(holder, name):
        dict.__delitem__(holder, name)
    dict.__setitem__(holder, new_name, item.value)
    return holder[new_name]
