# Implements: REQ-p00002-A
"""Error listing for spec format violations and missing assertions.

Follows the gaps.py pattern: collect, render, engine-compatible compute,
standalone run with daemon-first execution.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from elspais.graph import NodeKind
from elspais.graph.relations import EdgeKind

if TYPE_CHECKING:
    from elspais.graph.federated import FederatedGraph


# =============================================================================
# Data model
# =============================================================================


@dataclass
class ErrorEntry:
    """A single spec error: a format violation or missing assertions."""

    req_id: str
    title: str
    rule: str
    message: str
    file_path: str | None = None
    line: int | None = None


@dataclass
class ErrorData:
    """Collected error data across all error types."""

    format_errors: list[ErrorEntry] = field(default_factory=list)
    no_assertions: list[ErrorEntry] = field(default_factory=list)


# =============================================================================
# Collection
# =============================================================================


def collect_errors(
    graph: FederatedGraph, config: dict[str, Any], exclude_status: set[str]
) -> ErrorData:
    """Collect spec format errors and missing-assertion warnings from the graph.

    Reuses validation logic from ``validation.format`` and the same
    no-assertions check as ``health.check_spec_no_assertions``.
    """
    from elspais.validation.format import get_format_rules_config, validate_requirement_format

    data = ErrorData()
    rules = get_format_rules_config(config)

    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        if node.status in exclude_status:
            continue

        req_id = node.id
        title = node.get_label() or ""
        fn = node.file_node()
        fp = fn.get_field("relative_path") if fn else None
        ln = node.get_field("parse_line")

        # Format rule violations
        violations = validate_requirement_format(node, rules)
        for v in violations:
            data.format_errors.append(
                ErrorEntry(
                    req_id=req_id,
                    title=title,
                    rule=v.rule,
                    message=v.message,
                    file_path=fp,
                    line=ln,
                )
            )

        # No assertions check
        has_assertion = any(
            child.kind == NodeKind.ASSERTION
            for child in node.iter_children(edge_kinds={EdgeKind.STRUCTURES})
        )
        if not has_assertion:
            data.no_assertions.append(
                ErrorEntry(
                    req_id=req_id,
                    title=title,
                    rule="no_assertions",
                    message="No assertions — not testable",
                    file_path=fp,
                    line=ln,
                )
            )

    return data


# =============================================================================
# Rendering
# =============================================================================

_LABELS = {
    "format_errors": "FORMAT ERRORS",
    "no_assertions": "NO ASSERTIONS",
}

_ALL_ERROR_TYPES = ["format_errors", "no_assertions"]


def render_error_text(error_type: str, data: ErrorData) -> str:
    """Render a single error section as plain text."""
    label = _LABELS[error_type]
    entries: list[ErrorEntry] = getattr(data, error_type)
    if not entries:
        return f"\n{label}: none"
    lines = [f"\n{label} ({len(entries)}):"]
    for entry in sorted(entries, key=lambda e: e.req_id):
        loc = ""
        if entry.file_path:
            loc = f"  {entry.file_path}"
            if entry.line:
                loc += f":{entry.line}"
        lines.append(f"  {entry.req_id:20s} {entry.rule}: {entry.message}{loc}")
    return "\n".join(lines)


def render_error_markdown(error_type: str, data: ErrorData) -> str:
    """Render a single error section as markdown."""
    label = _LABELS[error_type]
    entries: list[ErrorEntry] = getattr(data, error_type)
    if not entries:
        return f"## {label}\n\nNo errors found."
    lines = [f"## {label} ({len(entries)})", ""]
    lines.append("| Requirement | Rule | Message | Location |")
    lines.append("|-------------|------|---------|----------|")
    for entry in sorted(entries, key=lambda e: e.req_id):
        loc = entry.file_path or ""
        if loc and entry.line:
            loc += f":{entry.line}"
        lines.append(f"| {entry.req_id} | {entry.rule} | {entry.message} | {loc} |")
    return "\n".join(lines)


# =============================================================================
# Engine-compatible compute
# =============================================================================


def _error_entry_to_dict(entry: ErrorEntry) -> dict[str, Any]:
    """Serialize ErrorEntry for JSON."""
    d: dict[str, Any] = {
        "req_id": entry.req_id,
        "title": entry.title,
        "rule": entry.rule,
        "message": entry.message,
    }
    if entry.file_path:
        d["file_path"] = entry.file_path
    if entry.line:
        d["line"] = entry.line
    return d


def _error_data_from_dict(data: dict[str, Any]) -> ErrorData:
    """Reconstruct ErrorData from a JSON dict returned by the daemon."""
    ed = ErrorData()
    for et in _ALL_ERROR_TYPES:
        for item in data.get(et, []):
            getattr(ed, et).append(
                ErrorEntry(
                    req_id=item["req_id"],
                    title=item["title"],
                    rule=item["rule"],
                    message=item["message"],
                    file_path=item.get("file_path"),
                    line=item.get("line"),
                )
            )
    return ed


def compute_errors(
    graph: FederatedGraph, config: dict[str, Any], params: dict[str, str]
) -> dict[str, Any]:
    """Engine-compatible wrapper around collect_errors.

    Params:
        status: Optional comma-separated statuses to include.
    """
    from elspais.commands.health import _resolve_exclude_status

    fake_args = argparse.Namespace()
    status_str = params.get("status", None)
    fake_args.status = status_str.split(",") if status_str else None

    exclude_status = _resolve_exclude_status(fake_args, config=config)
    data = collect_errors(graph, config, exclude_status)

    result: dict[str, Any] = {}
    for et in _ALL_ERROR_TYPES:
        entries: list[ErrorEntry] = getattr(data, et)
        result[et] = [_error_entry_to_dict(e) for e in entries]
    return result


# =============================================================================
# Standalone run
# =============================================================================


def run(args: argparse.Namespace) -> int:
    """Run the errors command.

    Tries a running daemon/viewer first for fast results,
    falls back to local graph build.
    """
    from elspais.commands._engine import call as engine_call

    fmt = getattr(args, "format", "text")
    spec_dir = getattr(args, "spec_dir", None)

    params: dict[str, str] = {}
    status = getattr(args, "status", None)
    if status:
        params["status"] = ",".join(status)

    data = engine_call(
        "/api/run/errors",
        params,
        compute_errors,
        config_path=getattr(args, "config", None),
        skip_daemon=bool(spec_dir),
    )

    if fmt == "json":
        output = json.dumps(data, indent=2)
    else:
        error_data = _error_data_from_dict(data)
        if fmt == "markdown":
            sections = [render_error_markdown(et, error_data) for et in _ALL_ERROR_TYPES]
            output = "\n\n".join(sections)
        else:
            sections = [render_error_text(et, error_data) for et in _ALL_ERROR_TYPES]
            output = "\n\n".join(sections)

    output_file = getattr(args, "output", None)
    if output_file:
        Path(output_file).write_text(output + "\n")
    else:
        print(output)

    return 0
