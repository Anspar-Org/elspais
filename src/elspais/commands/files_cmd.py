# Implements: REQ-d00335
"""The requirements each named file defines, implements, verifies or validates.

A caller names paths and gets, for each, what the graph holds about the file
at that path: whether the scan read it, the role the scan gave it, and every
requirement and *Assertion* it links to with the kind of each link. The answer
is read from the federated graph every other report reads -- a FILE node's
CONTAINS children and the traceability edges that reach them -- so a citation
is read by the one citation reader and an identifier an associate owns names
what it names everywhere else.

``compute_files`` is the one computation. The command line, the HTTP route a
daemon serves it from and the MCP tool all call it, so the three give one
answer for one tree.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from elspais.graph import NodeKind
from elspais.graph.relations import EdgeKind

if TYPE_CHECKING:
    from elspais.commands._requests import FilesRequest
    from elspais.graph.federated import FederatedGraph, RepoEntry
    from elspais.graph.GraphNode import GraphNode

# The outcome for each path named (REQ-d00335-E+F+G).
SCANNED = "scanned"
NOT_SCANNED = "not_scanned"
NO_FILE = "no_file"

# The kind of each link, in the order an answer lists them (REQ-d00335-D).
DEFINES = "defines"
LINK_KINDS = (DEFINES, "implements", "verifies", "validates")

# The edges by which a requirement or *Assertion* reaches the content of a
# code, test or journey file. Stored inverted: the cited node is the edge's
# source and the citing node its target.
_CITING_EDGES = frozenset({EdgeKind.IMPLEMENTS, EdgeKind.VERIFIES, EdgeKind.VALIDATES})
_CITING_KINDS = frozenset({NodeKind.CODE, NodeKind.TEST, NodeKind.USER_JOURNEY})


# Implements: REQ-d00335-A, REQ-p00015-E
def compute_files(
    graph: FederatedGraph,
    config: dict[str, Any],
    request: FilesRequest,
    *,
    built_at: float,
    changed: Iterable[Path] = (),
) -> dict[str, Any]:
    """Answer for each path in *request*, in the order named.

    *built_at* is when the answering graph was built. A file written after
    it, or gone since, is reported as not current, so the answer never
    presents an older reading as the working tree's. *changed* is what a
    serving process's watch found changed since it built the graph
    (``changed_files()`` in ``server/watch.py``); a file named there is not
    current either, which catches a file put in place with an older
    modification time than the build.

    Reads the graph and the file system only; it changes neither.
    """
    members = _members_by_depth(graph)
    unresolved = _unresolved_by_source(graph)
    moved = frozenset(Path(p).resolve() for p in changed)
    return {
        "files": [
            _answer_for(graph, path, members, unresolved, built_at, moved) for path in request.paths
        ]
    }


def _members_by_depth(graph: FederatedGraph) -> list[tuple[Path, RepoEntry]]:
    """Every member with its resolved root, the deepest root first.

    A member nested inside another's directory claims the files beneath its
    own root, so the deepest root containing a path is the member holding it.
    """
    members = [(Path(entry.repo_root).resolve(), entry) for entry in graph.iter_repos()]
    members.sort(key=lambda pair: len(pair[0].parts), reverse=True)
    return members


def _unresolved_by_source(graph: FederatedGraph) -> dict[str, list[dict[str, str]]]:
    """Each reference that named nothing the federation holds, keyed by its holder."""
    held: dict[str, list[dict[str, str]]] = {}
    for fault in graph.unresolved_references():
        held.setdefault(fault.source_id, []).append(
            {
                "reference": fault.target_id,
                "kind": str(fault.edge_kind).lower(),
                "fault": fault.fault_class.label,
            }
        )
    return held


# Implements: REQ-d00335-B+I
def _locate(
    graph: FederatedGraph, path: str, members: list[tuple[Path, RepoEntry]]
) -> tuple[Path, RepoEntry | None, str | None]:
    """The absolute path named, the member holding it, and its path within that member.

    A relative path is read against the root of the repository the tool runs
    in. An absolute path may lie in any member of the federation.
    """
    named = Path(path)
    absolute = (named if named.is_absolute() else Path(graph.repo_root) / named).resolve()
    for root, entry in members:
        try:
            return absolute, entry, absolute.relative_to(root).as_posix()
        except ValueError:
            continue
    return absolute, None, None


def _answer_for(
    graph: FederatedGraph,
    path: str,
    members: list[tuple[Path, RepoEntry]],
    unresolved: dict[str, list[dict[str, str]]],
    built_at: float,
    changed: frozenset[Path],
) -> dict[str, Any]:
    from elspais.graph.GraphNode import make_file_id
    from elspais.server.watch import changed_since

    absolute, member, relative = _locate(graph, path, members)
    file_node = None
    if member is not None and relative:
        file_node = graph.find_by_id(make_file_id(member.namespace, relative))

    exists = absolute.is_file()
    entry: dict[str, Any] = {
        "path": path,
        "relative_path": relative,
        "namespace": member.namespace if member is not None else None,
        "status": NO_FILE,
        "role": None,
        # Implements: REQ-p00015-E
        # A file the graph holds and the disk no longer does is the graph
        # being behind the disk, as a file written after the build is.
        "current": absolute not in changed
        and ((not changed_since(absolute, built_at)) if exists else file_node is None),
        "links": [],
        "unresolved": [],
        "unbound": [],
        "declined_citations": False,
    }
    if not exists:
        # Implements: REQ-d00335-E
        return entry
    if file_node is None:
        # Implements: REQ-d00335-F
        entry["status"] = NOT_SCANNED
        if member is not None and relative is not None:
            entry["declined_citations"] = any(
                found.path == relative
                for found in graph.unscanned_keyword_files(namespace=member.namespace)
            )
        return entry

    # Implements: REQ-d00335-C+D+G+H
    entry["status"] = SCANNED
    entry["role"] = _role_of(file_node)
    entry["links"] = _links_of(file_node)
    # Implements: REQ-d00241-E
    # A citation that produced no link is still a citation: reported with the
    # file rather than leaving it to read as a file that cites nothing.
    entry["unresolved"] = _unresolved_in(file_node, unresolved)
    entry["unbound"] = _unbound_in(graph, member, relative)
    return entry


# Implements: REQ-d00335-H
def _role_of(file_node: GraphNode) -> str | None:
    """The role the scan gave a file: its file type, or ``journey`` for a journey file.

    The spec scan reads journeys from the same directories as requirements,
    so a journey file carries the spec file type. What it holds tells the two
    apart: a spec-typed file holding journeys and no requirement is a
    journey file.
    """
    from elspais.graph.GraphNode import FileType

    file_type = file_node.get_field("file_type")
    if file_type is None:
        return None
    if file_type == FileType.SPEC:
        kinds = {c.kind for c in file_node.iter_children(edge_kinds={EdgeKind.CONTAINS})}
        if NodeKind.USER_JOURNEY in kinds and NodeKind.REQUIREMENT not in kinds:
            return FileType.JOURNEY.value
    return file_type.value


# Implements: REQ-d00335-C+D
def _links_of(file_node: GraphNode) -> list[dict[str, str]]:
    """Every requirement and *Assertion* a scanned file links to, with the kind of link."""
    links: set[tuple[str, str, str]] = set()
    for child in file_node.iter_children(edge_kinds={EdgeKind.CONTAINS}):
        if child.kind == NodeKind.REQUIREMENT:
            links.add((DEFINES, child.id, child.id))
            for assertion in child.iter_children(edge_kinds={EdgeKind.STRUCTURES}):
                if assertion.kind == NodeKind.ASSERTION:
                    links.add((DEFINES, assertion.id, child.id))
        elif child.kind in _CITING_KINDS:
            for edge in child.iter_incoming_edges():
                if edge.kind in _CITING_EDGES:
                    links.update(_cited(edge.kind.value, edge.source, edge.assertion_targets))
    order = {kind: index for index, kind in enumerate(LINK_KINDS)}
    return [
        {"kind": kind, "id": node_id, "requirement": requirement}
        for kind, node_id, requirement in sorted(links, key=lambda t: (order[t[0]], t[1]))
    ]


def _cited(kind: str, cited: GraphNode, labels: list[str] | None) -> set[tuple[str, str, str]]:
    """The links one citing edge makes: the *Assertions* it names, else the requirement."""
    if cited.kind == NodeKind.ASSERTION:
        owner = next(
            (p for p in cited.iter_parents(edge_kinds={EdgeKind.STRUCTURES})),
            None,
        )
        return {(kind, cited.id, owner.id if owner is not None else cited.id)}
    if cited.kind != NodeKind.REQUIREMENT:
        return set()
    if not labels:
        return {(kind, cited.id, cited.id)}
    named = set(labels)
    return {
        (kind, assertion.id, cited.id)
        for assertion in cited.iter_children(edge_kinds={EdgeKind.STRUCTURES})
        if assertion.kind == NodeKind.ASSERTION and assertion.get_field("label") in named
    }


def _unresolved_in(
    file_node: GraphNode, unresolved: dict[str, list[dict[str, str]]]
) -> list[dict[str, str]]:
    """The references written in this file's citations that named nothing held."""
    holders = [file_node.id] + [
        child.id
        for child in file_node.iter_children(edge_kinds={EdgeKind.CONTAINS})
        if child.kind in _CITING_KINDS
    ]
    found = [fault for holder in holders for fault in unresolved.get(holder, [])]
    return sorted(found, key=lambda f: (f["reference"], f["kind"], f["fault"]))


def _unbound_in(
    graph: FederatedGraph, member: RepoEntry | None, relative: str | None
) -> list[dict[str, Any]]:
    """The references of this test file's citations that bound to no test."""
    if member is None or relative is None:
        return []
    return [
        {"reference": target, "line": citation.line}
        for citation in graph.unbound_citations(namespace=member.namespace)
        if citation.path == relative
        for target in citation.targets
    ]


def run(args: argparse.Namespace) -> int:
    """Run the files command."""
    import time

    from elspais.commands._engine import call as engine_call
    from elspais.commands._requests import FilesRequest

    paths = tuple(getattr(args, "paths", ()) or ())
    if not paths:
        print("Usage: elspais files PATH [PATH ...]", file=sys.stderr)
        return 1

    # A graph this command builds itself is built after this moment, so a
    # file changed since then is one the build may not have read.
    started = time.time()

    def compute_here(graph: Any, config: dict[str, Any], request: Any) -> dict[str, Any]:
        return compute_files(graph, config, request, built_at=started)

    data = engine_call(
        "/api/files",
        FilesRequest(paths=paths),
        compute_here,
        skip_daemon=getattr(args, "no_daemon", False),
        config_path=getattr(args, "config", None),
    )
    answer: dict[str, Any] = {"files": data.get("files", [])}
    predates = (data.get("graph_source") or {}).get("graph_predates")
    if predates:
        answer["graph_predates"] = predates

    if getattr(args, "format", "text") == "json":
        sys.stdout.write(json.dumps(answer, indent=2) + "\n")
    else:
        sys.stdout.write(render_files(answer))
    return 0


_OUTCOME_WORDS = {
    SCANNED: "scanned",
    NOT_SCANNED: "not scanned",
    NO_FILE: "no file at this path",
}


def render_files(answer: dict[str, Any]) -> str:
    """The answer as text, one block per path named."""
    lines: list[str] = []
    for entry in answer.get("files", []):
        heading = entry["path"]
        outcome = _OUTCOME_WORDS[entry["status"]]
        if entry["status"] == SCANNED:
            outcome = f"{outcome}, {entry['role']}"
        lines.append(f"{heading}: {outcome}")
        if not entry["current"]:
            lines.append("  stale: the file changed after the graph answering was built")
        if entry["declined_citations"]:
            lines.append("  carries citations, but the scan does not select it")
        for link in entry["links"]:
            lines.append(f"  {link['kind']:<10}  {link['id']}")
        for fault in entry["unresolved"]:
            lines.append(f"  unresolved  {fault['reference']} ({fault['kind']}, {fault['fault']})")
        for unbound in entry["unbound"]:
            lines.append(
                f"  unbound     {unbound['reference']} (line {unbound['line']} binds to no test)"
            )
        if entry["status"] == SCANNED and not (
            entry["links"] or entry["unresolved"] or entry["unbound"]
        ):
            lines.append("  no link")
    return "\n".join(lines) + ("\n" if lines else "")
