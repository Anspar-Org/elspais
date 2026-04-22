"""Unlinked files mini-report -- composable section.

Lists code and test files that were scanned but contain no traceability
markers (no Implements:, Verifies:, or REQ-xxx patterns found).
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from elspais.graph import NodeKind
from elspais.graph.GraphNode import FileType, make_file_id
from elspais.graph.relations import EdgeKind

if TYPE_CHECKING:
    from elspais.graph.federated import FederatedGraph


@dataclass
class UnlinkedEntry:
    """A file with no traceability markers."""

    node_id: str
    file: str
    line: int = 0
    label: str = ""


@dataclass
class UnlinkedData:
    """Collected unlinked files grouped by kind."""

    tests: list[UnlinkedEntry] = field(default_factory=list)
    code: list[UnlinkedEntry] = field(default_factory=list)


def collect_unlinked(graph: FederatedGraph) -> UnlinkedData:
    """Find code and test files with no traceability markers.

    Scans FILE nodes of type CODE/TEST and checks whether they contain
    any CODE/TEST child nodes (which are created when the parser finds
    Implements:/Verifies:/REQ-xxx markers). Files with no such children
    have no traceability coverage.
    """
    data = UnlinkedData()

    for file_node in graph.iter_roots(NodeKind.FILE):
        file_type = file_node.get_field("file_type")
        rel_path = file_node.get_field("relative_path") or file_node.id

        if file_type == FileType.TEST:
            has_child = any(
                child.kind == NodeKind.TEST
                for child in file_node.iter_children(edge_kinds={EdgeKind.CONTAINS})
            )
            if not has_child:
                data.tests.append(UnlinkedEntry(node_id=file_node.id, file=rel_path))

        elif file_type == FileType.CODE:
            has_child = any(
                child.kind == NodeKind.CODE
                for child in file_node.iter_children(edge_kinds={EdgeKind.CONTAINS})
            )
            if not has_child:
                data.code.append(UnlinkedEntry(node_id=file_node.id, file=rel_path))

    return data


# =============================================================================
# Rendering
# =============================================================================

_LABEL = "UNLINKED FILES"


def render_unlinked_text(data: UnlinkedData, *, verbose: bool = False) -> str:
    """Render unlinked files as plain text."""
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


def render_unlinked_markdown(data: UnlinkedData, *, verbose: bool = False) -> str:
    """Render unlinked files as markdown."""
    total = len(data.tests) + len(data.code)
    if total == 0:
        return f"## {_LABEL}\n\nNo unlinked files found."

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


def _serialize(data: UnlinkedData) -> dict[str, Any]:
    """Serialize UnlinkedData to a JSON-compatible dict."""
    return {
        "tests": {
            "count": len(data.tests),
            "files": [e.file for e in sorted(data.tests, key=lambda e: e.file)],
        },
        "code": {
            "count": len(data.code),
            "files": [e.file for e in sorted(data.code, key=lambda e: e.file)],
        },
    }


def render_section(
    graph: FederatedGraph,
    config: dict[str, Any] | None,
    args: argparse.Namespace,
) -> tuple[str, int]:
    """Render unlinked files section.

    Returns:
        Tuple of (rendered output string, exit code).
        Exit code is 0 when no unlinked files, non-zero otherwise.
    """
    data = collect_unlinked(graph)
    total = len(data.tests) + len(data.code)
    fmt = getattr(args, "format", "text")
    verbose = getattr(args, "verbose", False)

    if fmt == "json":
        return json.dumps(_serialize(data), indent=2), 1 if total else 0

    if fmt == "markdown":
        return render_unlinked_markdown(data, verbose=verbose), 1 if total else 0

    return render_unlinked_text(data, verbose=verbose), 1 if total else 0


# =============================================================================
# Standalone run
# =============================================================================


def _unlinked_data_from_dict(data: dict[str, Any]) -> UnlinkedData:
    """Reconstruct UnlinkedData from a JSON dict returned by the daemon."""
    ud = UnlinkedData()
    for f in data.get("tests", {}).get("files", []):
        ud.tests.append(UnlinkedEntry(node_id=make_file_id(f), file=f))
    for f in data.get("code", {}).get("files", []):
        ud.code.append(UnlinkedEntry(node_id=make_file_id(f), file=f))
    return ud


def compute_unlinked(graph: FederatedGraph, config: dict, params: dict[str, str]) -> dict:
    """Engine-compatible wrapper around collect_unlinked."""
    return _serialize(collect_unlinked(graph))


def run(args: argparse.Namespace) -> int:
    """Run a standalone unlinked-nodes listing.

    Tries a running daemon/viewer first for fast results,
    falls back to local graph build.
    """
    from elspais.commands._engine import call as engine_call

    fmt = getattr(args, "format", "text")
    verbose = getattr(args, "verbose", False)
    spec_dir = getattr(args, "spec_dir", None)

    data = engine_call(
        "/api/run/unlinked",
        {},
        compute_unlinked,
        skip_daemon=bool(spec_dir),
        config_path=getattr(args, "config", None),
    )

    if fmt == "json":
        output = json.dumps(data, indent=2)
        total = data.get("tests", {}).get("count", 0) + data.get("code", {}).get("count", 0)
        exit_code = 1 if total else 0
    else:
        unlinked_data = _unlinked_data_from_dict(data)
        total = len(unlinked_data.tests) + len(unlinked_data.code)
        if fmt == "markdown":
            output = render_unlinked_markdown(unlinked_data, verbose=verbose)
        else:
            output = render_unlinked_text(unlinked_data, verbose=verbose)
        exit_code = 1 if total else 0

    output_file = getattr(args, "output", None)
    if output_file:
        Path(output_file).write_text(output + "\n")
    else:
        print(output)

    return exit_code
