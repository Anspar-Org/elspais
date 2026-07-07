"""Gap listing composable sections for traceability coverage gaps."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from elspais.graph.federated import FederatedGraph

from elspais.graph import NodeKind
from elspais.graph.relations import EdgeKind


@dataclass
class GapEntry:
    """A single gap: a REQ with optionally listed uncovered assertions.

    ``assertions`` holds ``(assertion_id, fraction)`` pairs, where ``fraction``
    is the assertion's conducted coverage fraction in ``[0.0, 1.0)`` (REQ-d00069-J).
    A fraction of ``0.0`` means no coverage at all; ``0 < fraction < 1`` means
    the assertion is partially covered via REFINES conduction.
    """

    req_id: str
    title: str
    assertions: list[tuple[str, float]] = field(default_factory=list)  # empty = whole REQ uncovered


@dataclass
class GapData:
    """Collected gap data across all gap types."""

    uncovered: list[GapEntry] = field(default_factory=list)
    untested: list[GapEntry] = field(default_factory=list)
    unvalidated: list[GapEntry] = field(default_factory=list)
    failing: list[tuple[str, str, str]] = field(default_factory=list)  # (req_id, title, source)
    no_assertions: list[GapEntry] = field(default_factory=list)
    # REQ-d00252-F: requirements covered via an external associate (INTEGRATES),
    # grouped by owning associate name -> sorted list of consumer requirement IDs.
    integrated: dict[str, list[str]] = field(default_factory=dict)


def _reqs_with_code_refs(graph: FederatedGraph, excluded_ids: set[str]) -> set[str]:
    """Return set of requirement IDs that have at least one CODE reference."""
    covered: set[str] = set()
    for node in graph.nodes_by_kind(NodeKind.CODE):
        for parent in node.iter_parents():
            if parent.kind == NodeKind.REQUIREMENT and parent.id not in excluded_ids:
                covered.add(parent.id)
            elif parent.kind == NodeKind.ASSERTION:
                for grandparent in parent.iter_parents():
                    if (
                        grandparent.kind == NodeKind.REQUIREMENT
                        and grandparent.id not in excluded_ids
                    ):
                        covered.add(grandparent.id)
    return covered


# Implements: REQ-d00252
def _integrates_associates(graph: FederatedGraph, node: Any) -> list[str]:
    """Return sorted owning-associate names for a requirement's INTEGRATES targets.

    Empty if the requirement has no INTEGRATES edges. Guards the ownership lookup
    (``repo_for`` raises KeyError if a target is unowned) so an unresolved target
    does not crash gap collection (REQ-d00252-F).
    """
    owners: set[str] = set()
    for edge in node.iter_outgoing_edges():
        if edge.kind != EdgeKind.INTEGRATES:
            continue
        target = edge.target
        owner: str | None
        try:
            owner = graph.repo_for(target.id).name
        except KeyError:
            owner = None  # node not owned by any repo -> skip
        except AttributeError:
            owner = getattr(graph, "_ownership", {}).get(target.id)
        if owner is not None:
            owners.add(owner)
    return sorted(owners)


def collect_gaps(
    graph: FederatedGraph,
    exclude_status: set[str],
    config: dict[str, Any] | None = None,
) -> GapData:
    """Single-pass collection of coverage gaps from the graph.

    Args:
        graph: The federated traceability graph.
        exclude_status: Set of status values to skip (e.g. {"Retired"}).
        config: Project config dict. Used to resolve per-level
            ``expects_validation`` so only levels that expect UAT validation
            produce ``unvalidated`` gaps (REQ-d00258-F).

    Returns:
        GapData with all gap lists populated.
    """
    from elspais.config import level_expects_validation

    cfg = config or {}
    data = GapData()

    excluded_ids: set[str] = set()
    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        if node.status in exclude_status:
            excluded_ids.add(node.id)

    code_covered = _reqs_with_code_refs(graph, excluded_ids)

    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        if node.status in exclude_status:
            continue

        req_id = node.id
        title = node.get_label() or ""
        metrics = node.get_metric("rollup_metrics")

        # Collect assertion nodes for this REQ (kept as nodes so coverage
        # lookups can key by assertion *label* while gap entries report IDs).
        assertion_nodes = [
            child
            for child in node.iter_children(edge_kinds={EdgeKind.STRUCTURES})
            if child.kind == NodeKind.ASSERTION
        ]

        # REQ-d00252-F: a requirement that delegates implementation to a library
        # via INTEGRATES is covered through that associate -- it must NOT be
        # reported as an uncovered gap. Record it under its owning associate(s).
        integrating = _integrates_associates(graph, node)
        if integrating:
            for assoc in integrating:
                data.integrated.setdefault(assoc, []).append(req_id)
        # Uncovered: no code references
        elif req_id not in code_covered:
            data.uncovered.append(GapEntry(req_id, title))
        elif metrics is not None and metrics.implemented.indirect < metrics.implemented.total:
            # Partially covered: find which assertions lack coverage
            uncov = _uncovered_assertions(metrics, assertion_nodes, "implemented")
            if uncov:
                data.uncovered.append(GapEntry(req_id, title, uncov))

        # Testing gap (untested): an assertion is a testing gap iff it is
        # IMPLEMENTED but not tested to ~100% (relative denominator,
        # REQ-d00258, REQ-d00069-J). A wholly-UNIMPLEMENTED assertion is NOT a
        # testing gap -- there is nothing built to test yet. Such a REQ still
        # surfaces as an implementation gap in the ``uncovered`` section above,
        # so narrowing here never silently drops an unbuilt requirement.
        if metrics is not None and metrics.implemented.indirect > 0:
            uncov = _uncovered_assertions(
                metrics, assertion_nodes, "tested", restrict_to_dimension="implemented"
            )
            if uncov:
                # Whole-REQ formatting (empty assertion list = "all") only when
                # the REQ has NO test coverage at all AND every assertion is
                # implemented, so "all" is accurate. When any test coverage
                # exists (partial conduction, 0 < fraction < 1) or an
                # unimplemented sibling is present, list the specific
                # implemented-untested assertions so per-assertion fractions
                # survive (REQ-d00069-J) and no unimplemented sibling is implied.
                whole_req = metrics.tested.indirect <= 0 and len(uncov) == len(assertion_nodes)
                if whole_req:
                    data.untested.append(GapEntry(req_id, title))
                else:
                    data.untested.append(GapEntry(req_id, title, uncov))

        # Unvalidated: no UAT coverage. Only levels that expect_validation can
        # be "unvalidated" -- an internal level that never gets a journey is not
        # a gap (REQ-d00258-F).
        if level_expects_validation(cfg, node.level):
            if metrics is None or metrics.uat_coverage.indirect <= 0:
                data.unvalidated.append(GapEntry(req_id, title))
            elif metrics.uat_coverage.indirect < metrics.uat_coverage.total:
                uncov = _uncovered_assertions(metrics, assertion_nodes, "uat_coverage")
                if uncov:
                    data.unvalidated.append(GapEntry(req_id, title, uncov))

        # No assertions: not testable
        if not assertion_nodes:
            data.no_assertions.append(GapEntry(req_id, title))

        # Failing: test or UAT failures
        if metrics is not None:
            if metrics.verified.has_failures:
                data.failing.append((req_id, title, "test"))
            if metrics.uat_verified.has_failures:
                data.failing.append((req_id, title, "uat"))

    return data


def _uncovered_assertions(
    metrics: Any,
    assertion_nodes: list[Any],
    dimension: str,
    restrict_to_dimension: str | None = None,
) -> list[tuple[str, float]]:
    """Return (id, fraction) pairs for assertions not ~fully covered for a dimension.

    Reads the dimension's per-assertion fraction map so that coverage conducted
    upward across REFINES edges (REQ-d00069-J) is honored. The fraction map is
    keyed by assertion *label* (e.g. ``A``), so each node is looked up by its
    label while the returned pairs report assertion *IDs* (e.g. ``REQ-100-A``),
    which is what gap entries and their renderers expect. An assertion counts as
    covered only when its fraction reaches ~1.0; a partially covered assertion
    (0 < fraction < 1, e.g. a parent assertion refined by a not-fully-covered
    child) is still reported as a gap, with its fraction carried along so
    renderers can distinguish "no coverage at all" (0.0) from "partially
    conducted" (0 < fraction < 1).

    ``restrict_to_dimension`` implements the RELATIVE denominator (REQ-d00258):
    when given, the candidate set is intersected with assertions that HAVE
    coverage in that dimension (fraction > 0). A *testing* gap passes
    ``restrict_to_dimension="implemented"`` so an unimplemented assertion --
    which has nothing built to test yet -- is not reported as a testing gap.
    """
    dim = getattr(metrics, dimension, None)
    fractions = dim.indirect_pct_by_label if dim is not None else {}

    restrict_labels: set[str] | None = None
    if restrict_to_dimension is not None:
        rdim = getattr(metrics, restrict_to_dimension, None)
        rfractions = rdim.indirect_pct_by_label if rdim is not None else {}
        restrict_labels = {lbl for lbl, frac in rfractions.items() if frac > 0}

    covered = 1.0 - 1e-9
    result: list[tuple[str, float]] = []
    for a in assertion_nodes:
        label = a.get_field("label", "")
        if restrict_labels is not None and label not in restrict_labels:
            continue
        frac = fractions.get(label, 0.0)
        if frac < covered:
            result.append((a.id, frac))
    return result


# =============================================================================
# Rendering
# =============================================================================

_LABELS = {
    "uncovered": "UNCOVERED (no code refs)",
    "untested": "UNTESTED (implemented, not tested)",
    "unvalidated": "UNVALIDATED (no UAT coverage)",
    "failing": "FAILING",
    "no_assertions": "NOT TESTABLE (no assertions)",
}


def render_gap_text(gap_type: str, data: GapData) -> str:
    """Render a single gap section as plain text."""
    label = _LABELS[gap_type]
    gaps = getattr(data, gap_type)
    if not gaps:
        return f"\n{label}: none"
    lines = [f"\n{label} ({len(gaps)}):"]
    if gap_type == "failing":
        for rid, title, source in sorted(gaps):
            lines.append(f"  {rid:20s} [{source}] {title}")
    else:
        for entry in sorted(gaps, key=lambda e: e.req_id):
            if entry.assertions:
                # Partial gap: show REQ with uncovered assertions. A partially
                # conducted assertion (0 < fraction < 1, REQ-d00069-J) is
                # annotated with its percentage so it reads differently from
                # an assertion with no coverage at all (fraction 0.0).
                parts = []
                for aid, frac in entry.assertions:
                    label = aid.rsplit("-", 1)[-1] if "-" in aid else aid
                    if frac > 0:
                        parts.append(f"{label} — {round(frac * 100)}% via refines-conduction")
                    else:
                        parts.append(label)
                labels = ", ".join(parts)
                lines.append(f"  {entry.req_id:20s} {entry.title}  [{labels}]")
            else:
                lines.append(f"  {entry.req_id:20s} {entry.title}")
    return "\n".join(lines)


def render_integrated_text(data: GapData) -> str:
    """Render the 'Covered via external associate' segment as plain text.

    Returns an empty string when no requirement integrates an associate, so the
    segment only appears when relevant (REQ-d00252-F).
    """
    if not data.integrated:
        return ""
    lines = ["\nCovered via external associate:"]
    for assoc in sorted(data.integrated):
        req_ids = ", ".join(sorted(data.integrated[assoc]))
        lines.append(f"  {assoc}:  {req_ids}")
    return "\n".join(lines)


def render_integrated_markdown(data: GapData) -> str:
    """Render the 'Covered via external associate' segment as markdown."""
    if not data.integrated:
        return ""
    lines = ["## Covered via external associate", ""]
    lines.append("| Associate | Requirements |")
    lines.append("|-----------|--------------|")
    for assoc in sorted(data.integrated):
        req_ids = ", ".join(sorted(data.integrated[assoc]))
        lines.append(f"| {assoc} | {req_ids} |")
    return "\n".join(lines)


def render_gap_markdown(gap_type: str, data: GapData) -> str:
    """Render a single gap section as markdown."""
    label = _LABELS[gap_type]
    gaps = getattr(data, gap_type)
    if not gaps:
        return f"## {label}\n\nNo gaps found."
    lines = [f"## {label} ({len(gaps)})", ""]
    if gap_type == "failing":
        lines.append("| Requirement | Source | Title |")
        lines.append("|-------------|--------|-------|")
        for rid, title, source in sorted(gaps):
            lines.append(f"| {rid} | {source} | {title} |")
    else:
        lines.append("| Requirement | Title | Uncovered Assertions |")
        lines.append("|-------------|-------|---------------------|")
        for entry in sorted(gaps, key=lambda e: e.req_id):
            if entry.assertions:
                parts = [
                    f"{aid} ({round(frac * 100)}% via refines-conduction)" if frac > 0 else aid
                    for aid, frac in entry.assertions
                ]
                assertions = ", ".join(parts)
            else:
                assertions = "(all)"
            lines.append(f"| {entry.req_id} | {entry.title} | {assertions} |")
    return "\n".join(lines)


# =============================================================================
# Composable section
# =============================================================================

_ALL_GAP_TYPES = ["uncovered", "untested", "unvalidated", "failing", "no_assertions"]


def render_section(
    graph: FederatedGraph,
    config: dict[str, Any] | None,
    args: argparse.Namespace,
    gap_types: list[str] | None = None,
) -> tuple[str, int]:
    """Render gap sections for the given gap types.

    Returns:
        Tuple of (rendered output string, exit code).
        Exit code is always 0 (gap sections are informational).
    """
    from elspais.commands.health import _resolve_exclude_status

    if gap_types is None:
        gap_types = _ALL_GAP_TYPES

    exclude_status = _resolve_exclude_status(args, config=config or {})
    data = collect_gaps(graph, exclude_status, config=config)

    fmt = getattr(args, "format", "text")

    show_integrated = "uncovered" in gap_types

    if fmt == "json":
        result: dict[str, Any] = {}
        for gt in gap_types:
            items = getattr(data, gt)
            if gt == "failing":
                result[gt] = [list(item) for item in items]
            else:
                result[gt] = [_gap_entry_to_list(entry) for entry in items]
        if show_integrated and data.integrated:
            result["integrated"] = {k: sorted(v) for k, v in data.integrated.items()}
        return json.dumps(result, indent=2), 0

    if fmt == "markdown":
        sections = [render_gap_markdown(gt, data) for gt in gap_types]
        if show_integrated:
            seg = render_integrated_markdown(data)
            if seg:
                sections.append(seg)
        return "\n\n".join(sections), 0

    # Default: text
    sections = [render_gap_text(gt, data) for gt in gap_types]
    text = "\n\n".join(sections)
    if show_integrated:
        text += render_integrated_text(data)
    return text, 0


# =============================================================================
# Standalone run
# =============================================================================

_GAP_TYPE_MAP: dict[str, str | None] = {
    "gaps": None,  # None = all gap types
    "uncovered": "uncovered",
    "untested": "untested",
    "unvalidated": "unvalidated",
    "failing": "failing",
    "no_assertions": "no_assertions",
}


def _gap_entry_to_list(entry: GapEntry) -> list:
    """Serialize GapEntry for JSON.

    Uncovered assertions are serialized as ``{"id": ..., "fraction": ...}``
    dicts so a partially-conducted assertion (0 < fraction < 1, REQ-d00069-J)
    is distinguishable from one with no coverage at all. ``fraction`` is
    rounded to 4 places, matching the MCP surface (server.py), so the two
    JSON surfaces agree on precision rather than one emitting raw floats.
    """
    result: list = [entry.req_id, entry.title]
    if entry.assertions:
        result.append([{"id": aid, "fraction": round(frac, 4)} for aid, frac in entry.assertions])
    return result


def _gap_data_from_dict(data: dict[str, Any]) -> GapData:
    """Reconstruct GapData from a JSON dict returned by the daemon."""
    gd = GapData()
    for gt in ("uncovered", "untested", "unvalidated", "no_assertions"):
        for item in data.get(gt, []):
            raw_assertions = item[2] if len(item) > 2 else []
            assertions = [(a["id"], a.get("fraction", 0.0)) for a in raw_assertions]
            getattr(gd, gt).append(GapEntry(item[0], item[1], assertions))
    for item in data.get("failing", []):
        gd.failing.append(tuple(item))  # type: ignore[arg-type]
    integrated = data.get("integrated", {})
    if isinstance(integrated, dict):
        gd.integrated = {k: list(v) for k, v in integrated.items()}
    return gd


def compute_gaps(graph: FederatedGraph, config: dict, params: dict[str, str]) -> dict:
    """Engine-compatible wrapper around collect_gaps.

    Params:
        type: Optional gap type filter (uncovered, untested, unvalidated, failing).
        status: Optional comma-separated statuses to include.
    """
    import argparse as _argparse

    from elspais.commands.health import _resolve_exclude_status

    fake_args = _argparse.Namespace()
    status_str = params.get("status", None)
    fake_args.status = status_str.split(",") if status_str else None

    exclude_status = _resolve_exclude_status(fake_args, config=config)
    data = collect_gaps(graph, exclude_status, config=config)

    def _serialize_gap_list(gt: str) -> list:
        items = getattr(data, gt)
        if gt == "failing":
            return [list(item) for item in items]
        return [_gap_entry_to_list(entry) for entry in items]

    integrated = {k: sorted(v) for k, v in data.integrated.items()}

    gap_type = params.get("type", None)
    if gap_type and gap_type in (
        "uncovered",
        "untested",
        "unvalidated",
        "failing",
        "no_assertions",
    ):
        out = {gap_type: _serialize_gap_list(gap_type)}
        if gap_type == "uncovered" and integrated:
            out["integrated"] = integrated  # type: ignore[assignment]
        return out

    result: dict[str, Any] = {}
    for gt in ("uncovered", "untested", "unvalidated", "failing", "no_assertions"):
        result[gt] = _serialize_gap_list(gt)
    if integrated:
        result["integrated"] = integrated
    return result


def run(args: argparse.Namespace) -> int:
    """Run a standalone gap listing command.

    Tries a running daemon/viewer first for fast results,
    falls back to local graph build.
    """
    from elspais.commands._engine import call as engine_call

    command = getattr(args, "command", "gaps")
    gap_type = _GAP_TYPE_MAP.get(command)
    gap_types: list[str] | None = [gap_type] if gap_type else None
    fmt = getattr(args, "format", "text")
    spec_dir = getattr(args, "spec_dir", None)

    params: dict[str, str] = {}
    if gap_type:
        params["type"] = gap_type

    data = engine_call(
        "/api/run/gaps",
        params,
        compute_gaps,
        config_path=getattr(args, "config", None),
        skip_daemon=bool(spec_dir),
    )

    if fmt == "json":
        output = json.dumps(data, indent=2)
    else:
        gap_data = _gap_data_from_dict(data)
        types_to_render = gap_types or _ALL_GAP_TYPES
        show_integrated = "uncovered" in types_to_render
        if fmt == "markdown":
            sections = [render_gap_markdown(gt, gap_data) for gt in types_to_render]
            if show_integrated:
                seg = render_integrated_markdown(gap_data)
                if seg:
                    sections.append(seg)
            output = "\n\n".join(sections)
        else:
            sections = [render_gap_text(gt, gap_data) for gt in types_to_render]
            output = "\n\n".join(sections)
            if show_integrated:
                output += render_integrated_text(gap_data)

    output_file = getattr(args, "output", None)
    if output_file:
        Path(output_file).write_text(output + "\n")
    else:
        print(output)

    return 0
