# Implements: REQ-d00241-A, REQ-d00241-D, REQ-d00285-F
"""Uncited files mini-report -- composable section.

Lists scanned code and test files that cite nothing: no `Implements:`, no
`Verifies:`, nothing that reaches a requirement. The file was read and it
said nothing about the estate.

This is deliberately NOT the population the graph API calls *unlinked*.
`TraceGraph.iter_unlinked()` and the MCP `get_unlinked_nodes` tool answer
about NODES -- a single test function or citation block that exists in the
file structure and reaches no requirement through a traceability edge. A file
holding one linked test and nine unlinked ones is full of unlinked nodes and
is not uncited. One name over both answers puts two surfaces in contradiction
about the same repository, which is what REQ-d00285-F forbids.

The predicate lives here once. The `code.uncited_file` and
`tests.uncited_file` health checks read it from here rather than walking the
graph again, so `elspais uncited` and `elspais checks` cannot report
different sets.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

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


# =============================================================================
# Rendering
# =============================================================================

_LABEL = "UNCITED FILES"


def render_uncited_text(data: UncitedData, *, verbose: bool = False) -> str:
    """Render uncited files as plain text."""
    total = len(data.tests) + len(data.code)
    if total == 0:
        return f"\n{_LABEL}: none"

    lines = [f"\n{_LABEL} ({total}):"]

    if data.tests:
        lines.append(f"\n  Test files ({len(data.tests)}):")
        for entry in sorted(data.tests, key=lambda e: e.file):
            lines.append(f"    {entry.file}")

    if data.code:
        lines.append(f"\n  Code files ({len(data.code)}):")
        for entry in sorted(data.code, key=lambda e: e.file):
            lines.append(f"    {entry.file}")

    return "\n".join(lines)


def render_uncited_markdown(data: UncitedData, *, verbose: bool = False) -> str:
    """Render uncited files as markdown."""
    total = len(data.tests) + len(data.code)
    if total == 0:
        return f"## {_LABEL}\n\nNo uncited files found."

    lines = [f"## {_LABEL} ({total})", ""]

    if data.tests:
        lines.append(f"### Test files ({len(data.tests)})")
        lines.append("")
        lines.append("| File |")
        lines.append("|------|")
        for entry in sorted(data.tests, key=lambda e: e.file):
            lines.append(f"| {entry.file} |")
        lines.append("")

    if data.code:
        lines.append(f"### Code files ({len(data.code)})")
        lines.append("")
        lines.append("| File |")
        lines.append("|------|")
        for entry in sorted(data.code, key=lambda e: e.file):
            lines.append(f"| {entry.file} |")

    return "\n".join(lines)


# =============================================================================
# Composable section
# =============================================================================


def _serialize(data: UncitedData) -> dict[str, Any]:
    """Serialize UncitedData to a JSON-compatible dict.

    Carries each entry's node id alongside its path. A reader cannot
    rebuild the id from the path -- the id names the repository holding
    the file, which a bare path does not say -- so the id travels rather
    than being guessed at the far end.
    """
    return {
        "tests": {
            "count": len(data.tests),
            "files": [e.file for e in sorted(data.tests, key=lambda e: e.file)],
            "nodes": [
                {"node_id": e.node_id, "file": e.file}
                for e in sorted(data.tests, key=lambda e: e.file)
            ],
        },
        "code": {
            "count": len(data.code),
            "files": [e.file for e in sorted(data.code, key=lambda e: e.file)],
            "nodes": [
                {"node_id": e.node_id, "file": e.file}
                for e in sorted(data.code, key=lambda e: e.file)
            ],
        },
    }


def render_section(
    graph: FederatedGraph,
    config: dict[str, Any] | None,
    args: argparse.Namespace,
) -> tuple[str, int]:
    """Render uncited files section.

    Returns:
        Tuple of (rendered output string, exit code).
        Exit code is 0 when no uncited files, non-zero otherwise.
    """
    data = collect_uncited(graph)
    total = len(data.tests) + len(data.code)
    fmt = getattr(args, "format", "text")
    verbose = getattr(args, "verbose", False)

    if fmt == "json":
        return json.dumps(_serialize(data), indent=2), 1 if total else 0

    if fmt == "markdown":
        return render_uncited_markdown(data, verbose=verbose), 1 if total else 0

    return render_uncited_text(data, verbose=verbose), 1 if total else 0


# =============================================================================
# Standalone run
# =============================================================================


def _uncited_data_from_dict(data: dict[str, Any]) -> UncitedData:
    """Reconstruct UncitedData from a JSON dict returned by the daemon.

    Reads the node ids the daemon sent. A daemon that sent only paths
    leaves the id empty rather than having one invented for it: an id
    naming the wrong repository is worse than none, and every reader of
    this data displays the path.
    """
    ud = UncitedData()
    for kind, entries in (("tests", ud.tests), ("code", ud.code)):
        section = data.get(kind, {})
        nodes = section.get("nodes")
        if nodes:
            entries.extend(
                UncitedEntry(node_id=n.get("node_id", ""), file=n.get("file", "")) for n in nodes
            )
            continue
        entries.extend(UncitedEntry(node_id="", file=f) for f in section.get("files", []))
    return ud


def compute_uncited(graph: FederatedGraph, config: dict, params: dict[str, str]) -> dict:
    """Engine-compatible wrapper around collect_uncited."""
    return _serialize(collect_uncited(graph))


def run(args: argparse.Namespace) -> int:
    """Run a standalone uncited-files listing.

    Tries a running daemon/viewer first for fast results,
    falls back to local graph build.
    """
    from elspais.commands._engine import call as engine_call

    fmt = getattr(args, "format", "text")
    verbose = getattr(args, "verbose", False)
    spec_dir = getattr(args, "spec_dir", None)

    data = engine_call(
        "/api/run/uncited",
        {},
        compute_uncited,
        skip_daemon=bool(spec_dir),
        config_path=getattr(args, "config", None),
    )

    if fmt == "json":
        output = json.dumps(data, indent=2)
        total = data.get("tests", {}).get("count", 0) + data.get("code", {}).get("count", 0)
        exit_code = 1 if total else 0
    else:
        uncited_data = _uncited_data_from_dict(data)
        total = len(uncited_data.tests) + len(uncited_data.code)
        if fmt == "markdown":
            output = render_uncited_markdown(uncited_data, verbose=verbose)
        else:
            output = render_uncited_text(uncited_data, verbose=verbose)
        exit_code = 1 if total else 0

    output_file = getattr(args, "output", None)
    if output_file:
        Path(output_file).write_text(output + "\n")
    else:
        print(output)

    return exit_code
