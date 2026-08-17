"""Broken references mini-report — composable section."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from elspais.graph.federated import FederatedGraph
    from elspais.graph.reference_faults import ReferenceFault


def collect_broken(
    graph: FederatedGraph,
    config: dict[str, Any] | None,
) -> list[ReferenceFault]:
    """Collect every unresolved reference the graph recorded.

    Silencing by class now happens at review time, through
    ``[rules.references]`` severity (``unknown_namespace = "ok"`` for
    expected cross-repository references) -- this listing always shows the
    whole population regardless of *config*, so a project's severity
    choices never hide something from it.
    """
    return list(graph.broken_references())


# =============================================================================
# Rendering
# =============================================================================

# This command lists every reference that resolves to nothing. The five
# reference checks (`references.malformed`, `references.unknown_namespace`,
# `references.unknown_requirement`, `references.unknown_assertion`,
# `references.forbidden`) partition the same set by fault class, so the
# listing uses the union's name and leaves "broken" to mean what a check
# means by it.
_LABEL = "UNRESOLVED REFERENCES"


def _is_foreign(br: ReferenceFault) -> bool:
    """A target no configured repository claims -- the display flag.

    Derived from *fault_class* rather than read off ``presumed_foreign``:
    the field is retained for the clone-assistance path, but what earns the
    "[foreign]" tag here is the class a fault actually reached.
    """
    from elspais.graph.reference_faults import FaultClass

    return br.fault_class is FaultClass.UNKNOWN_NAMESPACE


def render_broken_text(refs: list[ReferenceFault]) -> str:
    """Render broken references as plain text."""
    if not refs:
        return f"\n{_LABEL}: none"
    lines = [f"\n{_LABEL} ({len(refs)}):"]
    for br in sorted(refs, key=lambda r: (r.source_id, r.target_id)):
        foreign = " [foreign]" if _is_foreign(br) else ""
        lines.append(f"  {br.source_id:20s} -> {br.target_id:20s} ({br.edge_kind}){foreign}")
        if br.diagnostic:
            lines.append(f"      {br.diagnostic}")
    return "\n".join(lines)


def render_broken_markdown(refs: list[ReferenceFault]) -> str:
    """Render broken references as markdown."""
    if not refs:
        return f"## {_LABEL}\n\nNo unresolved references found."
    lines = [
        f"## {_LABEL} ({len(refs)})",
        "",
        "| Source | Target | Kind | Diagnostic |",
        "|--------|--------|------|------------|",
    ]
    for br in sorted(refs, key=lambda r: (r.source_id, r.target_id)):
        foreign = " [foreign]" if _is_foreign(br) else ""
        lines.append(
            f"| {br.source_id} | {br.target_id} | {br.edge_kind}{foreign} | {br.diagnostic} |"
        )
    return "\n".join(lines)


# =============================================================================
# Composable section
# =============================================================================


def render_section(
    graph: FederatedGraph,
    config: dict[str, Any] | None,
    args: argparse.Namespace,
) -> tuple[str, int]:
    """Render broken references section.

    Returns:
        Tuple of (rendered output string, exit code).
        Exit code is 0 when no broken refs, non-zero otherwise.
    """
    refs = collect_broken(graph, config)
    fmt = getattr(args, "format", "text")

    if fmt == "json":
        data = [
            {
                "source": br.source_id,
                "target": br.target_id,
                "kind": br.edge_kind,
                "foreign": _is_foreign(br),
                "diagnostic": br.diagnostic,
            }
            for br in sorted(refs, key=lambda r: (r.source_id, r.target_id))
        ]
        return json.dumps({"broken": data}, indent=2), 1 if refs else 0

    if fmt == "markdown":
        return render_broken_markdown(refs), 1 if refs else 0

    return render_broken_text(refs), 1 if refs else 0


# =============================================================================
# Daemon-compatible compute function
# =============================================================================


def compute_broken(
    graph: FederatedGraph,
    config: dict[str, Any],
    params: dict[str, str],
) -> dict[str, Any]:
    """Compute broken references and return a structured dict.

    This is the compute_fn for ``_engine.call()``, matching the
    ``(graph, config, params) -> dict`` signature used by all CLI
    command endpoints.
    """
    refs = collect_broken(graph, config)
    data = [
        {
            "source": br.source_id,
            "target": br.target_id,
            "kind": br.edge_kind,
            "foreign": _is_foreign(br),
            "diagnostic": br.diagnostic,
        }
        for br in sorted(refs, key=lambda r: (r.source_id, r.target_id))
    ]
    return {"broken": data, "count": len(data)}


# =============================================================================
# Standalone run
# =============================================================================


def run(args: argparse.Namespace) -> int:
    """Run a standalone broken-references listing."""
    from elspais.commands import _engine

    spec_dir = getattr(args, "spec_dir", None)
    skip_daemon = bool(spec_dir)

    if skip_daemon:
        from elspais.config import get_config
        from elspais.graph.factory import build_graph

        config_path = getattr(args, "config", None)
        start_path = Path.cwd()

        config = get_config(config_path, start_path=start_path)
        graph = build_graph(
            spec_dirs=[spec_dir] if spec_dir else None,
            config_path=config_path,
        )
        output, exit_code = render_section(graph, config, args)
    else:
        data = _engine.call(
            "/api/run/broken",
            {},
            compute_broken,
            config_path=getattr(args, "config", None),
        )
        # Reconstruct output from the dict
        fmt = getattr(args, "format", "text")
        refs_data = data.get("broken", [])
        if fmt == "json":
            output = json.dumps({"broken": refs_data}, indent=2)
        elif fmt == "markdown":
            output = _render_broken_data_markdown(refs_data)
        else:
            output = _render_broken_data_text(refs_data)
        exit_code = 1 if refs_data else 0

    output_file = getattr(args, "output", None)
    if output_file:
        Path(output_file).write_text(output + "\n")
    else:
        print(output)

    return exit_code


def _render_broken_data_text(refs: list[dict[str, Any]]) -> str:
    """Render broken references from dict data as plain text."""
    if not refs:
        return f"\n{_LABEL}: none"
    lines = [f"\n{_LABEL} ({len(refs)}):"]
    for br in refs:
        foreign = " [foreign]" if br.get("foreign") else ""
        lines.append(f"  {br['source']:20s} -> {br['target']:20s} ({br['kind']}){foreign}")
        if br.get("diagnostic"):
            lines.append(f"      {br['diagnostic']}")
    return "\n".join(lines)


def _render_broken_data_markdown(refs: list[dict[str, Any]]) -> str:
    """Render broken references from dict data as markdown."""
    if not refs:
        return f"## {_LABEL}\n\nNo unresolved references found."
    lines = [
        f"## {_LABEL} ({len(refs)})",
        "",
        "| Source | Target | Kind | Diagnostic |",
        "|--------|--------|------|------------|",
    ]
    for br in refs:
        foreign = " [foreign]" if br.get("foreign") else ""
        diag = br.get("diagnostic", "")
        lines.append(f"| {br['source']} | {br['target']} | {br['kind']}{foreign} | {diag} |")
    return "\n".join(lines)
