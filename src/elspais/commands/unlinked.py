"""Unlinked nodes mini-report -- composable section."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from elspais.graph.federated import FederatedGraph

from elspais.graph import NodeKind


@dataclass
class UnlinkedEntry:
    """A single unlinked node."""

    node_id: str
    file: str
    line: int
    label: str  # human-friendly name (func_name or short id)


@dataclass
class UnlinkedData:
    """Collected unlinked nodes grouped by kind."""

    tests: list[UnlinkedEntry] = field(default_factory=list)
    code: list[UnlinkedEntry] = field(default_factory=list)


def _node_label(node_id: str) -> str:
    """Extract a human-friendly label from a node ID.

    test:path::Class::func -> Class::func
    test:path::func -> func
    code:path::func -> func
    """
    if "::" in node_id:
        return node_id.split("::", 1)[1]
    return node_id


def collect_unlinked(graph: FederatedGraph) -> UnlinkedData:
    """Collect unlinked TEST and CODE nodes from the graph."""
    data = UnlinkedData()

    for node in graph.iter_unlinked(NodeKind.TEST):
        file_node = node.file_node()
        rel_path = file_node.get_field("relative_path") if file_node else "unknown"
        line = node.get_field("parse_line") or 0
        data.tests.append(
            UnlinkedEntry(
                node_id=node.id,
                file=rel_path,
                line=line,
                label=_node_label(node.id),
            )
        )

    for node in graph.iter_unlinked(NodeKind.CODE):
        file_node = node.file_node()
        rel_path = file_node.get_field("relative_path") if file_node else "unknown"
        line = node.get_field("parse_line") or 0
        data.code.append(
            UnlinkedEntry(
                node_id=node.id,
                file=rel_path,
                line=line,
                label=_node_label(node.id),
            )
        )

    return data


# =============================================================================
# Rendering
# =============================================================================

_LABEL = "UNLINKED NODES"


def _by_file(items: list[UnlinkedEntry]) -> dict[str, list[UnlinkedEntry]]:
    """Group entries by file path, sorted by file then line."""
    grouped: dict[str, list[UnlinkedEntry]] = {}
    for entry in sorted(items, key=lambda e: (e.file, e.line, e.node_id)):
        grouped.setdefault(entry.file, []).append(entry)
    return grouped


def render_unlinked_text(data: UnlinkedData, *, verbose: bool = False) -> str:
    """Render unlinked nodes as plain text."""
    total = len(data.tests) + len(data.code)
    if total == 0:
        return f"\n{_LABEL}: none"

    lines = [f"\n{_LABEL} ({total}):"]

    if data.tests:
        lines.append(f"\n  Tests ({len(data.tests)}):")
        for file_path, entries in _by_file(data.tests).items():
            lines.append(f"    {file_path}: {len(entries)}")
            if verbose:
                for e in entries:
                    lines.append(f"      L{e.line}: {e.label}")

    if data.code:
        lines.append(f"\n  Code ({len(data.code)}):")
        for file_path, entries in _by_file(data.code).items():
            lines.append(f"    {file_path}: {len(entries)}")
            if verbose:
                for e in entries:
                    lines.append(f"      L{e.line}: {e.label}")

    return "\n".join(lines)


def render_unlinked_markdown(data: UnlinkedData, *, verbose: bool = False) -> str:
    """Render unlinked nodes as markdown."""
    total = len(data.tests) + len(data.code)
    if total == 0:
        return f"## {_LABEL}\n\nNo unlinked nodes found."

    lines = [f"## {_LABEL} ({total})", ""]

    if data.tests:
        lines.append(f"### Tests ({len(data.tests)})")
        lines.append("")
        if verbose:
            lines.append("| File | Line | Function |")
            lines.append("|------|------|----------|")
            for file_path, entries in _by_file(data.tests).items():
                for e in entries:
                    lines.append(f"| {file_path} | {e.line} | `{e.label}` |")
        else:
            lines.append("| File | Count |")
            lines.append("|------|-------|")
            for file_path, entries in _by_file(data.tests).items():
                lines.append(f"| {file_path} | {len(entries)} |")
        lines.append("")

    if data.code:
        lines.append(f"### Code ({len(data.code)})")
        lines.append("")
        if verbose:
            lines.append("| File | Line | Function |")
            lines.append("|------|------|----------|")
            for file_path, entries in _by_file(data.code).items():
                for e in entries:
                    lines.append(f"| {file_path} | {e.line} | `{e.label}` |")
        else:
            lines.append("| File | Count |")
            lines.append("|------|-------|")
            for file_path, entries in _by_file(data.code).items():
                lines.append(f"| {file_path} | {len(entries)} |")

    return "\n".join(lines)


# =============================================================================
# Composable section
# =============================================================================


def render_section(
    graph: FederatedGraph,
    config: dict[str, Any] | None,
    args: argparse.Namespace,
) -> tuple[str, int]:
    """Render unlinked nodes section.

    Returns:
        Tuple of (rendered output string, exit code).
        Exit code is 0 when no unlinked nodes, non-zero otherwise.
    """
    data = collect_unlinked(graph)
    total = len(data.tests) + len(data.code)
    fmt = getattr(args, "format", "text")
    verbose = getattr(args, "verbose", False)

    if fmt == "json":
        result: dict[str, Any] = {
            "tests": {
                "count": len(data.tests),
                "by_file": {
                    fp: [{"id": e.node_id, "line": e.line, "label": e.label} for e in entries]
                    for fp, entries in _by_file(data.tests).items()
                },
            },
            "code": {
                "count": len(data.code),
                "by_file": {
                    fp: [{"id": e.node_id, "line": e.line, "label": e.label} for e in entries]
                    for fp, entries in _by_file(data.code).items()
                },
            },
        }
        return json.dumps(result, indent=2), 1 if total else 0

    if fmt == "markdown":
        return render_unlinked_markdown(data, verbose=verbose), 1 if total else 0

    return render_unlinked_text(data, verbose=verbose), 1 if total else 0


# =============================================================================
# Standalone run
# =============================================================================


def _unlinked_data_from_dict(data: dict[str, Any]) -> UnlinkedData:
    """Reconstruct UnlinkedData from a JSON dict returned by the daemon."""
    ud = UnlinkedData()
    for fp, entries in data.get("tests", {}).get("by_file", {}).items():
        for e in entries:
            ud.tests.append(
                UnlinkedEntry(
                    node_id=e["id"],
                    file=fp,
                    line=e.get("line", 0),
                    label=e.get("label", ""),
                )
            )
    for fp, entries in data.get("code", {}).get("by_file", {}).items():
        for e in entries:
            ud.code.append(
                UnlinkedEntry(
                    node_id=e["id"],
                    file=fp,
                    line=e.get("line", 0),
                    label=e.get("label", ""),
                )
            )
    return ud


def run(args: argparse.Namespace) -> int:
    """Run a standalone unlinked-nodes listing.

    Tries a running daemon/viewer first for fast results,
    falls back to local graph build.
    """
    fmt = getattr(args, "format", "text")
    verbose = getattr(args, "verbose", False)

    # Daemon-first path
    # Skip daemon when spec_dir is explicitly set (e.g. tests with custom dirs)
    spec_dir = getattr(args, "spec_dir", None)
    daemon_result = None
    if not spec_dir:
        from elspais.commands._daemon_client import try_daemon_or_start

        daemon_result = try_daemon_or_start("/api/run/unlinked")

    if daemon_result is not None:
        if fmt == "json":
            output = json.dumps(daemon_result, indent=2)
            total = daemon_result.get("tests", {}).get("count", 0) + daemon_result.get(
                "code", {}
            ).get("count", 0)
            exit_code = 1 if total else 0
        else:
            data = _unlinked_data_from_dict(daemon_result)
            total = len(data.tests) + len(data.code)
            if fmt == "markdown":
                output = render_unlinked_markdown(data, verbose=verbose)
            else:
                output = render_unlinked_text(data, verbose=verbose)
            exit_code = 1 if total else 0
    else:
        # Fallback: local graph build
        from elspais.config import get_config
        from elspais.graph.factory import build_graph

        spec_dir = getattr(args, "spec_dir", None)
        config_path = getattr(args, "config", None)
        canonical_root = getattr(args, "canonical_root", None)
        start_path = Path.cwd()

        config = get_config(config_path, start_path=start_path)
        graph = build_graph(
            spec_dirs=[spec_dir] if spec_dir else None,
            config_path=config_path,
            canonical_root=canonical_root,
        )
        output, exit_code = render_section(graph, config, args)

    output_file = getattr(args, "output", None)
    if output_file:
        Path(output_file).write_text(output + "\n")
    else:
        print(output)

    return exit_code
