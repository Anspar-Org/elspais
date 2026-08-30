# Implements: REQ-d00241-A, REQ-d00241-D, REQ-d00285-F
"""The uncited-file predicate: scanned code and test files that cite nothing.

No `Implements:`, no `Verifies:`, nothing that reaches a requirement. The file
was read and it said nothing about the estate.

This is deliberately NOT the population the graph API calls *unlinked*.
`TraceGraph.iter_unlinked()` and the MCP `get_unlinked_nodes` tool answer
about NODES -- a single test function or citation block that exists in the
file structure and reaches no requirement through a traceability edge. A file
holding one linked test and nine unlinked ones is full of unlinked nodes and
is not uncited. One name over both answers puts two surfaces in contradiction
about the same repository, which is what REQ-d00285-F forbids.

The predicate lives here once, and this module holds nothing else. The
`code.uncited_file` and `tests.uncited_file` health checks read it from here
rather than walking the graph again, and `elspais uncited` IS those two checks
-- the report narrowed to them (`PRESETS` in `utilities.findings`) rather than
a second listing rendered beside them. A separate renderer over the same facts
has to be handed every field a finding carries a second time, and the field
nobody remembered is the one that goes missing in exactly one place
(REQ-d00285-C).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from elspais.graph import NodeKind
from elspais.graph.GraphNode import FileType
from elspais.graph.relations import EdgeKind

if TYPE_CHECKING:
    from elspais.graph.federated import FederatedGraph


@dataclass
class UncitedEntry:
    """A scanned file that cites nothing."""

    node_id: str
    file: str
    line: int = 0
    label: str = ""


@dataclass
class UncitedData:
    """Collected uncited files grouped by kind."""

    tests: list[UncitedEntry] = field(default_factory=list)
    code: list[UncitedEntry] = field(default_factory=list)


# Implements: REQ-d00241-A, REQ-d00241-D, REQ-d00241-E
def collect_uncited(graph: FederatedGraph) -> UncitedData:
    """Find scanned code and test files that cite nothing.

    A CODE file is uncited when the scan produced no CODE node from it at
    all: a CODE node is what a citation comment becomes, so none means none
    was written.

    A TEST file is uncited when no test in it reaches a requirement. The
    stronger condition is required because the pre-scan emits a TEST node for
    every test function it discovers whether or not the function carries a
    marker, so a wholly marker-less test file still has TEST children. A file
    with at least one linked test is not uncited -- partial marking is a
    different question.

    A test file whose only citation attached to no test DOES carry a marker,
    and saying it carries none would send its author to add what is already
    there (REQ-d00241-E). Those files are excluded here and named by
    `tests.unbound_citation`, which says what is actually wrong with them.
    """
    data = UncitedData()
    cited_but_unbound = {c.path for c in graph.unbound_citations()}

    for file_node in graph.iter_roots(NodeKind.FILE):
        file_type = file_node.get_field("file_type")
        rel_path = file_node.get_field("relative_path") or file_node.id

        if file_type == FileType.TEST:
            has_linked_test = any(
                graph.is_reachable_to_requirement(child)
                for child in file_node.iter_children(edge_kinds={EdgeKind.CONTAINS})
                if child.kind == NodeKind.TEST
            )
            if has_linked_test:
                continue
            if (file_node.get_field("relative_path") or "") in cited_but_unbound:
                continue
            data.tests.append(UncitedEntry(node_id=file_node.id, file=rel_path))

        elif file_type == FileType.CODE:
            has_child = any(
                child.kind == NodeKind.CODE
                for child in file_node.iter_children(edge_kinds={EdgeKind.CONTAINS})
            )
            if not has_child:
                data.code.append(UncitedEntry(node_id=file_node.id, file=rel_path))

    return data
