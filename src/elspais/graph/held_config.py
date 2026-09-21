"""The configuration a consumer reads, derived from the documents held.

A repository's configuration documents are graph content: one FILE node of
the ``CONFIG`` type per document read, carrying the parsed ``TOMLDocument``.
This module is the read path over them. It derives nothing itself — the
merging, the ``[levels]`` replacement, the refusals and the schema
validation all live in :func:`elspais.config.derive_config`, which is a pure
function of the documents — so a consumer holding a graph and a consumer
holding only a path reach the same values by the same route.

That purity is not an accident of layering. ``get_config`` runs before any
graph exists, because reading the configuration is what tells the builder
where to look, so a derivation that needed a graph could never produce one.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import tomlkit

from elspais.config import derive_config
from elspais.graph.GraphNode import FileType, GraphNode, NodeKind

# A machine-local overlay layers over the committed file, so it is read
# second. The names are the ones `config_document_paths` names; ordering by
# them here is what keeps the two readers' precedence the same.
_LOCAL_DOCUMENT = ".elspais.local.toml"

_CACHED_CONFIG = "_derived_config"
_CACHED_FROM = "_derived_config_documents"


def iter_config_nodes(graph: Any) -> list[GraphNode]:
    """Every configuration document a graph holds, in read order.

    Args:
        graph: A ``TraceGraph``.

    Returns:
        The CONFIG FILE nodes, the committed document first and the
        machine-local overlay after it. Empty where the graph holds none.
    """
    nodes = [
        node
        for node in graph.iter_roots(NodeKind.FILE)
        if node.get_field("file_type") is FileType.CONFIG
    ]

    def _is_overlay(node: GraphNode) -> bool:
        return Path(str(node.get_field("absolute_path"))).name == _LOCAL_DOCUMENT

    return sorted(nodes, key=_is_overlay)


def _document_text(node: GraphNode) -> str:
    """The text of the document a node holds.

    Serves two purposes: it is what the derivation reads, and comparing it
    against the text a cached derivation was taken from is what tells a
    stale dictionary from a current one. A document edited in place changes
    no field on the node, so the node's own identity says nothing about
    whether its content moved.
    """
    document = node.get_field("config_document")
    if document is None:
        raise ValueError(
            f"{node.id} is a configuration document that holds no parsed "
            f"document, so no configuration can be derived from it."
        )
    return tomlkit.dumps(document)


# Implements: REQ-d00299-B
def config_from_nodes(nodes: list[GraphNode]) -> dict[str, Any]:
    """Derive the configuration the given documents assemble to.

    The result is cached on the first node and recomputed whenever any
    document's text differs from the text the cache was taken from, so an
    edit to a held document cannot leave a reader on the values it used to
    have.

    Args:
        nodes: CONFIG FILE nodes in read order, the committed document
            first.

    Returns:
        The configuration dictionary, keyed as the TOML is written.

    Raises:
        ValueError: No document was given, or one holds nothing to derive
            from.
    """
    if not nodes:
        raise ValueError(
            "A configuration is derived from the documents it was read from, "
            "and this graph holds none."
        )

    texts = tuple(_document_text(node) for node in nodes)
    primary = nodes[0]
    if getattr(primary, _CACHED_FROM, None) == texts:
        return getattr(primary, _CACHED_CONFIG)

    derived = derive_config(
        [
            (Path(str(node.get_field("absolute_path"))), node.get_field("config_document"))
            for node in nodes
        ]
    )
    setattr(primary, _CACHED_CONFIG, derived)
    setattr(primary, _CACHED_FROM, texts)
    return derived


# Implements: REQ-d00299-B
def held_config(graph: Any) -> dict[str, Any]:
    """The configuration a consumer reads, derived from what the graph holds.

    Args:
        graph: A ``TraceGraph``.

    Returns:
        The configuration dictionary, identical to what ``load_config``
        produces for the same documents.

    Raises:
        ValueError: The graph holds no configuration document.
    """
    return config_from_nodes(iter_config_nodes(graph))
