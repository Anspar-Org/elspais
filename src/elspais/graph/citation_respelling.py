"""Respelling the citations in code and test files that name a renamed identifier.

A citation in a code or test file is held as the comment its author wrote. When
a mutation gives a requirement or an *Assertion* a new identifier, each such
comment that designates it is respelled in place, so it designates the same
entity under the new identifier (REQ-p00017-B).

A respelling that reads wrong would be silent, so every respelling is checked
before anything changes (REQ-p00017-O). Both the former and the respelled
comment are read by the build's own reading path, and the respelled comment
must read as exactly the references the former one read as, with each renamed
one replaced by its successor. Otherwise the mutation is refused, naming the
file and line.

Where an identifier sits in a comment is found by the authorities that read a
comment: the keyword pattern, the file's own comment marker, the one list
divider and the federation's identifier reader. No pattern for an identifier is
spelled here.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from elspais.graph.GraphNode import NodeKind
from elspais.graph.parsers.patterns import (
    KEYWORD_PATTERN,
    comment_markers_for_path,
    comment_style_fragment,
)
from elspais.graph.relations import EdgeKind
from elspais.graph.render import citation_texts
from elspais.utilities.patterns import REF_LIST_SEPARATOR, split_ref_list

if TYPE_CHECKING:
    from elspais.graph.GraphNode import GraphNode
    from elspais.utilities.patterns import FederatedIdReader

# Successor of a reference that read, or None where the mutation leaves it alone.
Successor = Callable[[str], "str | None"]

_CITING_KINDS = (NodeKind.CODE, NodeKind.TEST)
_CITATION_CONTENT = ("code_ref", "test_ref")


class CitationRespellingRefused(ValueError):
    """A citation could not be respelled so that it reads as intended."""


@dataclass(frozen=True)
class Respelling:
    """One citation comment and what a mutation respells it to.

    Attributes:
        node: The CODE or TEST node holding the comment.
        file_node: The FILE node holding that node.
        line: The line the comment starts on.
        former: The comment as it was.
        respelled: The comment as the mutation leaves it.
        former_refs: The references the former comment reads as.
        respelled_refs: The references the respelled comment reads as.
    """

    node: GraphNode
    file_node: GraphNode
    line: int
    former: str
    respelled: str
    former_refs: tuple[str, ...] = ()
    respelled_refs: tuple[str, ...] = ()


def containing_file(node: GraphNode) -> GraphNode | None:
    """The FILE node holding a CODE or TEST node."""
    for edge in node.iter_incoming_edges():
        if edge.kind == EdgeKind.CONTAINS and edge.source.kind == NodeKind.FILE:
            return edge.source
    return None


def _path_of(file_node: GraphNode) -> str:
    return file_node.get_field("relative_path") or file_node.get_field("absolute_path") or ""


# Implements: REQ-p00017-B
def citers_of(entities: Iterable[tuple[GraphNode, set[str] | None]]) -> list[GraphNode]:
    """The CODE and TEST nodes a relationship joins to any of *entities*.

    Each entity is paired with the *Assertion* labels whose citations count,
    or None where every citation of it counts: a citation of an *Assertion*
    is an edge out of its requirement carrying the label. Storage inverts
    every relationship, so the cited entity is the source of the edge and
    the citing node its target. Edges reach across federation members, so a
    citation in another member's file is found too.
    """
    found: dict[int, GraphNode] = {}
    for entity, labels in entities:
        for edge in entity.iter_outgoing_edges():
            if edge.kind in (EdgeKind.STRUCTURES, EdgeKind.CONTAINS, EdgeKind.INSTANCE):
                continue
            if edge.target.kind not in _CITING_KINDS:
                continue
            if labels is not None and not labels.intersection(edge.assertion_targets or ()):
                continue
            found[id(edge.target)] = edge.target
    return list(found.values())


def _list_regions(text: str, path: str) -> list[tuple[int, int, str]] | None:
    """Where each line of a citation comment holds reference-list text.

    The opener's list is what its keyword introduces; a continuation line's
    list is what follows the file's own comment marker. Each region is
    returned as its line index, its offset in that line, and its text.
    """
    from elspais.graph.parsers.lark.transformers.reference import reference_target

    lines = text.split("\n")
    first = lines[0]
    keyword = KEYWORD_PATTERN.search(first)
    if keyword is None:
        return None
    target = reference_target(first)
    offset = first.find(target, keyword.end()) if target else -1
    if offset < 0:
        return None
    regions = [(0, offset, target)]
    marker = re.compile(comment_style_fragment(comment_markers_for_path(path)))
    for index, line in enumerate(lines[1:], start=1):
        stripped = line.lstrip(" \t")
        opened = marker.match(stripped)
        if opened is None:
            return None
        body = stripped[opened.end() :].strip()
        start = line.find(body, len(line) - len(stripped) + opened.end())
        if not body or start < 0:
            return None
        regions.append((index, start, body))
    return regions


def _respell_text(
    text: str,
    path: str,
    successor: Successor,
    reader: FederatedIdReader,
) -> tuple[str, list[str], list[str]] | None:
    """*text* with every identifier the mutation renames respelled.

    Returns the respelled text, the references the former text reads as and
    the references the respelled text must read as, or None where nothing
    in *text* designates a renamed identifier.

    Raises:
        CitationRespellingRefused: The comment could not be divided the way
            the reader divides it.
    """
    from elspais.graph.parsers.lark.transformers.reference import read_reference_list

    regions = _list_regions(text, path)
    if regions is None:
        raise CitationRespellingRefused("its reference list could not be located")

    # Every part of the list, with the line and offset it starts at. A line
    # that a following line continues ends with the separator, which leaves
    # an empty last part the joined list does not have.
    parts: list[tuple[int, int, str]] = []
    for position, (line_index, offset, region) in enumerate(regions):
        pieces = split_ref_list(region)
        if position < len(regions) - 1 and region.rstrip().endswith(REF_LIST_SEPARATOR):
            pieces = pieces[:-1]
        cursor = offset
        for piece in pieces:
            parts.append((line_index, cursor, piece))
            cursor += len(piece) + len(REF_LIST_SEPARATOR)

    lines = text.split("\n")
    # The joined text is what the reader is given, exactly as continuation
    # joins it (REQ-d00269-H).
    joined = lines[0].rstrip() + "".join(f" {region}" for _i, _o, region in regions[1:])
    items = read_reference_list(reader, joined)

    replacements: list[tuple[int, int, int, str]] = []
    expected_before: list[str] = []
    expected_after: list[str] = []
    for item in items:
        if item.residue or item.placeholder:
            continue
        if item.raw:
            expected_before.append(item.resolved or item.raw)
        if item.resolved is None or item.fault_class is not None:
            if item.raw:
                expected_after.append(item.raw)
            continue
        new = successor(item.resolved)
        expected_after.append(new or item.resolved)
        if new is None or new == item.resolved:
            continue
        if item.index >= len(parts):
            raise CitationRespellingRefused("its items could not be matched to its text")
        line_index, offset, piece = parts[item.index]
        lead = len(piece) - len(piece.lstrip())
        if not piece.lstrip().startswith(item.raw):
            raise CitationRespellingRefused("its items could not be matched to its text")
        start = offset + lead
        replacements.append((line_index, start, start + len(item.raw), new))

    if not replacements:
        return None
    for line_index, start, end, new in sorted(replacements, reverse=True):
        line = lines[line_index]
        lines[line_index] = line[:start] + new + line[end:]
    return "\n".join(lines), expected_before, expected_after


def _read_as_built(text: str, path: str, kind: NodeKind, reader: FederatedIdReader) -> Any:
    """What the build reads *text* as: its references, verdicts and keyword."""
    from elspais.graph.parsers.lark import FileDispatcher

    dispatcher = FileDispatcher(reader.own, reader.resolvers[1:])
    content = text + "\n"
    if kind == NodeKind.TEST:
        parsed = dispatcher.dispatch_test(content, path)
    else:
        parsed = dispatcher.dispatch_code(content, path)
    citations = [pc for pc in parsed if pc.content_type in _CITATION_CONTENT]
    if len(citations) != 1:
        return None
    data = citations[0].parsed_data
    refs = (
        list(data.get("implements") or [])
        + list(data.get("verifies") or [])
        + list(data.get("forbidden") or [])
    )
    return (
        refs,
        data.get("reference_verdicts") or {},
        data.get("forbidden_keyword"),
        citations[0].end_line - citations[0].start_line,
    )


# Implements: REQ-p00017-B, REQ-p00017-O
def plan_respellings(
    citers: Iterable[tuple[GraphNode, bool]],
    successor: Successor,
    reader: FederatedIdReader,
    designated: str,
) -> list[Respelling]:
    """Every citation comment the mutation respells, each checked.

    Args:
        citers: Each CODE or TEST node to consider, with whether a
            relationship joins it to the renamed entity. A node so joined
            must hold text that designates it.
        successor: The successor of a reference that read, or None where the
            mutation leaves the reference alone.
        reader: The federation's identifier reader.
        designated: The renamed identifier, for the refusal's wording.

    Returns:
        The respellings, nothing yet applied.

    Raises:
        CitationRespellingRefused: A citation would not read as the
            references it designated before, each under its new identifier,
            or a joined node holds no text designating the renamed entity.
            The message names the file and line.
    """
    plan: list[Respelling] = []
    seen: set[int] = set()
    for node, joined in citers:
        if id(node) in seen:
            continue
        seen.add(id(node))
        file_node = containing_file(node)
        if file_node is None:
            if joined:
                raise CitationRespellingRefused(
                    f"{node.id} cites {designated}, and no file holds it, so its citation "
                    f"cannot be respelled."
                )
            continue
        path = _path_of(file_node)
        found = False
        for line, text in sorted(citation_texts(node).items()):
            where = f"{path}:{line}"
            before = _read_as_built(text, path, node.kind, reader)
            if before is None or before[2]:
                # Nothing read, or a keyword this kind of file does not admit
                # was refused: the citation designates nothing.
                continue
            if not any(successor(ref) for ref in before[0]):
                continue
            try:
                respelled = _respell_text(text, path, successor, reader)
            except CitationRespellingRefused as refusal:
                raise CitationRespellingRefused(
                    f"{where}: the citation could not be respelled because {refusal}. "
                    f"Nothing was changed."
                ) from None
            if respelled is None:
                continue
            new_text, before_refs, after_refs = respelled
            after = _read_as_built(new_text, path, node.kind, reader)
            if (
                after is None
                or before[0] != before_refs
                or after[0] != after_refs
                or before[1] != after[1]
                or before[2:] != after[2:]
            ):
                raise CitationRespellingRefused(
                    f"{where}: respelling the citation of {designated} would leave text that "
                    f"does not read as the references it designated before under their new "
                    f"identifiers ({text.strip()!r} -> {new_text.strip()!r}). Nothing was "
                    f"changed."
                )
            found = True
            plan.append(
                Respelling(node, file_node, line, text, new_text, tuple(before[0]), tuple(after[0]))
            )
        if joined and not found:
            line = min(citation_texts(node), default=node.get_field("parse_line") or 0)
            raise CitationRespellingRefused(
                f"{path}:{line}: {node.id} cites {designated}, and no citation text it holds "
                f"names it, so the citation cannot be respelled. Nothing was changed."
            )
    return plan


# Implements: REQ-p00017-B
def journey_successor(old_id: str, new_id: str) -> Successor:
    """Map a reference to a renamed journey, or to one of its steps, to its new spelling.

    A journey reference is read verbatim (it belongs to no repository's
    identifier grammar), and a step is its journey's id, a slash and the
    step's number.
    """

    def successor(ref: str) -> str | None:
        if ref == old_id:
            return new_id
        if ref.startswith(old_id + "/"):
            return new_id + ref[len(old_id) :]
        return None

    return successor


def _set_citation_text(node: GraphNode, line: int, text: str) -> None:
    further = node.get_field("further_citations") or {}
    if line in further:
        updated = dict(further)
        updated[line] = text
        node.set_field("further_citations", updated)
    else:
        node.set_field("raw_text", text)


# Implements: REQ-p00017-B
def apply_respellings(plan: list[Respelling]) -> tuple[list[dict], list[dict]]:
    """Apply *plan* and return what a mutation entry records of it.

    Returns the former and the respelled citations, each naming the FILE
    node by its id, which carries its repository's namespace, so an undo
    finds the right file in a federation.
    """
    before: list[dict] = []
    after: list[dict] = []
    for item in plan:
        _set_citation_text(item.node, item.line, item.respelled)
        record = {"file_id": item.file_node.id, "node_id": item.node.id, "line": item.line}
        before.append({**record, "text": item.former, "refs": list(item.former_refs)})
        after.append({**record, "text": item.respelled, "refs": list(item.respelled_refs)})
    return before, after


def holder_in(file_node: GraphNode | None, node_id: str) -> GraphNode | None:
    """The node *file_node* holds under *node_id*."""
    if file_node is None:
        return None
    for edge in file_node.iter_outgoing_edges():
        if edge.kind == EdgeKind.CONTAINS and edge.target.id == node_id:
            return edge.target
    return None


# Implements: REQ-p00017-B, REQ-o00062-G
def restore_respellings(records: Iterable[dict], find_file: Callable[[str], Any]) -> None:
    """Put back the citation text an undone mutation respelled.

    Idempotent, so a member graph and its federation may both apply it.
    """
    for record in records or ():
        holder = holder_in(find_file(record["file_id"]), record["node_id"])
        if holder is not None:
            _set_citation_text(holder, record["line"], record["text"])
