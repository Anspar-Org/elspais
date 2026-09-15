"""Gap listing composable sections for traceability coverage gaps."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from elspais.commands._requests import GapsRequest
    from elspais.graph.federated import FederatedGraph

from elspais.graph import NodeKind
from elspais.graph.aggregation import (
    WORK_LIST_MEASURE,
    WorkVerdict,
    measure_total,
    work_verdict,
)
from elspais.graph.metrics import tested_and_passing
from elspais.graph.parsers.directives import counted_assertions
from elspais.graph.relations import EdgeKind


@dataclass
class GapEntry:
    """A single gap: a REQ with optionally listed uncovered assertions.

    ``assertions`` holds ``(assertion_id, label, fraction)`` triples. The label
    is carried rather than re-derived from the id: recovering it would mean
    splitting the id on a boundary character only the owning repository's
    grammar knows. ``fraction`` is the assertion's immediate direct coverage
    fraction in ``[0.0, 1.0)`` (REQ-d00258-M, REQ-d00069-M). A fraction of
    ``0.0`` means no evidence is attached here at all; ``0 < fraction < 1``
    means evidence attached directly to this *Assertion* is itself partial
    (e.g. a journey verified in part, REQ-d00255-C) -- coverage conducted up a
    `Refines:` chain plays no part in this fraction, since a gap list answers
    what still needs citing here, not what a refinement has done elsewhere.
    """

    req_id: str
    title: str
    # empty = whole REQ uncovered
    assertions: list[tuple[str, str, float]] = field(default_factory=list)


@dataclass
class GapData:
    """Collected gap data across all gap types."""

    uncovered: list[GapEntry] = field(default_factory=list)
    untested: list[GapEntry] = field(default_factory=list)
    unvalidated: list[GapEntry] = field(default_factory=list)
    failing: list[tuple[str, str, str]] = field(default_factory=list)  # (req_id, title, source)
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


# Implements: REQ-d00252-F
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


# Implements: REQ-p00084-B
def collect_gaps(
    graph: FederatedGraph,
    exclude_status: set[str],
    config: dict[str, Any] | None = None,
    node_ids: set[str] | frozenset[str] | None = None,
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
        # A requirement a scope does not select is not a gap in this report: the
        # reader asked a question about a set, and work outside it is not an
        # answer to that question.
        if node.status in exclude_status or (node_ids is not None and node.id not in node_ids):
            excluded_ids.add(node.id)

    code_covered = _reqs_with_code_refs(graph, excluded_ids)

    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        if node.id in excluded_ids:
            continue

        req_id = node.id
        title = node.get_label() or ""
        metrics = node.get_metric("rollup_metrics")

        # Collect assertion nodes for this REQ (kept as nodes so coverage
        # lookups can key by assertion *label* while gap entries report IDs).
        # Implements: REQ-p00017-G
        # A retired *Assertion* is not a gap: it states no obligation, so
        # nothing is missing when nothing verifies it.
        assertion_nodes = counted_assertions(node, structural=True)
        labels = [a.get_field("label", "") for a in assertion_nodes]

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
        elif metrics is not None:
            # Measured on the immediate direct measure (REQ-d00258-M): find
            # which assertions no citation names. A requirement fully covered
            # only by whole-requirement evidence, or only by finished
            # refinements below it, still has assertions nobody has written
            # evidence for, and this is the surface that exists to list them.
            uncov = _uncovered_assertions(
                work_verdict(metrics, "implemented", labels), assertion_nodes
            )
            if uncov:
                data.uncovered.append(GapEntry(req_id, title, uncov))

        # Testing gap (untested): an assertion is a testing gap iff it is
        # IMPLEMENTED but not tested to ~100% (relative denominator,
        # REQ-d00258, REQ-d00069-J), both read on the immediate direct
        # measure (REQ-d00258-M). A wholly-UNIMPLEMENTED assertion is NOT a
        # testing gap -- there is nothing built to test yet. Such a REQ still
        # surfaces as an implementation gap in the ``uncovered`` section above,
        # so narrowing here never silently drops an unbuilt requirement.
        if metrics is not None and measure_total(metrics.implemented, WORK_LIST_MEASURE) > 0:
            tested = work_verdict(metrics, "tested", labels, restrict_to_dimension="implemented")
            uncov = _uncovered_assertions(tested, assertion_nodes)
            if uncov:
                # Whole-REQ formatting (empty assertion list = "all") only
                # when NO test evidence is attached to the requirement at all
                # AND every assertion is implemented, so "all" is accurate.
                # When some assertions are tested, or an unimplemented sibling
                # is present, list the specific implemented-untested assertions
                # so no untouched sibling is implied to be a testing gap.
                whole_req = not tested.attached and len(uncov) == len(assertion_nodes)
                if whole_req:
                    data.untested.append(GapEntry(req_id, title))
                else:
                    data.untested.append(GapEntry(req_id, title, uncov))

        # Unvalidated: no UAT coverage. Only levels that expect_validation can
        # be "unvalidated" -- an internal level that never gets a journey is not
        # a gap (REQ-d00258-F). The whole-requirement verdict reads the
        # IMMEDIATE measures: a journey validating the requirement is evidence
        # attached here, whether or not it named an *Assertion*, while coverage
        # conducted from a refining requirement is not and must not rescue an
        # unvalidated requirement. The per-assertion listing reads the immediate
        # DIRECT measure (REQ-d00258-M) -- an assertion no journey names is a
        # gap even under a blanket journey.
        if level_expects_validation(cfg, node.level):
            verdict = work_verdict(metrics, "uat_coverage", labels)
            if not verdict.attached:
                data.unvalidated.append(GapEntry(req_id, title))
            elif verdict.needs_work:
                uncov = _uncovered_assertions(verdict, assertion_nodes)
                if uncov:
                    data.unvalidated.append(GapEntry(req_id, title, uncov))

        # Failing: test or UAT failures. Read through the Passing dimension,
        # so a failure line coverage carries is seen too (REQ-d00277-C).
        if metrics is not None:
            if tested_and_passing(metrics).has_failures:
                data.failing.append((req_id, title, "test"))
            if metrics.uat_verified.has_failures:
                data.failing.append((req_id, title, "uat"))

    return data


def _uncovered_assertions(
    verdict: WorkVerdict,
    assertion_nodes: list[Any],
) -> list[tuple[str, str, float]]:
    """The ``(id, label, fraction)`` triples a gap entry renders.

    The verdict already decided WHICH assertions are uncovered and what
    fraction each reached (``work_verdict``, REQ-d00258-C). All this adds is
    the assertion *ID* beside the label, which the fraction map is not keyed
    by and which gap entries report; deciding coverage a second time here is
    what let this surface and the health checks drift apart.

    Order follows the requirement's own assertions rather than the map, so a
    gap list reads in the order the requirement declares.
    """
    result: list[tuple[str, str, float]] = []
    for node in assertion_nodes:
        label = node.get_field("label", "")
        if label in verdict.uncovered:
            result.append((node.id, label, verdict.uncovered[label]))
    return result


# =============================================================================
# Rendering
# =============================================================================

_LABELS = {
    "uncovered": "UNCOVERED (no code refs)",
    "untested": "UNTESTED (implemented, not tested)",
    "unvalidated": "UNVALIDATED (no UAT coverage)",
    "failing": "FAILING",
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
                # Partial gap: show REQ with uncovered assertions. An
                # *Assertion* with partial evidence attached directly
                # (0 < fraction < 1, REQ-d00069-M, e.g. a journey verified in
                # part) is annotated with its percentage so it reads
                # differently from an *Assertion* with no evidence here at
                # all (fraction 0.0).
                parts = []
                for _aid, label, frac in entry.assertions:
                    if frac > 0:
                        parts.append(f"{label} — {round(frac * 100)}% direct")
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
                    f"{aid} ({round(frac * 100)}% direct)" if frac > 0 else aid
                    for aid, _label, frac in entry.assertions
                ]
                assertions = ", ".join(parts)
            else:
                assertions = "(all)"
            lines.append(f"| {entry.req_id} | {entry.title} | {assertions} |")
    return "\n".join(lines)


# =============================================================================
# Composable section
# =============================================================================

# Implements: REQ-d00282-A
# name: GAP_SECTION_FOR_VALUE
# use:  the ONE map between a coverage dimension and the listing of what falls
#       short of it.
# def:  value key -> the name of the section listing that dimension's shortfall.
#
# Each of these sections reads one dimension and lists what it has not credited:
# `uncovered` reads Implemented, `untested` reads Tested, `unvalidated` reads
# UAT Covered, `failing` reads Passing. So a values selection is not
# inapplicable to a report that lists shortfalls -- it says WHICH shortfalls the
# report lists -- and the shorthand commands are this one report under a fixed
# single-dimension selection rather than five separate reports.
GAP_SECTION_FOR_VALUE: dict[str, str] = {
    "implemented": "uncovered",
    "tested": "untested",
    "uat_coverage": "unvalidated",
    "verified": "failing",
}

# What this report offers a reader to select among (REQ-d00282-A). The four
# dimension keys and nothing beneath them: a section lists the requirements a
# dimension has not credited, so it can be asked for or left out, but it cannot
# be narrowed to `implemented.immediate_direct.count`. `resolve_values` refuses
# a name this does not hold, which is that assertion working rather than a
# special case.
OFFERED_VALUES: tuple[str, ...] = tuple(GAP_SECTION_FOR_VALUE)

# Implements: REQ-d00282-A
# What each command offers. A shorthand offers the one dimension it IS, so
# `uncovered --values tested` names a value `uncovered` does not offer and is
# refused, rather than quietly turning into `untested`.
COMMAND_VALUES: dict[str, tuple[str, ...]] = {
    "gaps": OFFERED_VALUES,
    **{section: (key,) for key, section in GAP_SECTION_FOR_VALUE.items()},
}

_ALL_GAP_TYPES = list(GAP_SECTION_FOR_VALUE.values())


# Implements: REQ-d00282-O
def gap_sections(values: tuple[str, ...] | None, command: str = "gaps") -> list[str]:
    """The sections this request asks for, in the order it named them.

    Takes values already resolved against this command's offer -- by
    ``report_inputs_from_args``/``report_inputs_from_params`` at whichever edge
    was invoked -- so composing a section and asking for it alone choose
    listings the same way (REQ-d00279-C). ``None`` states this command's
    default offer, matching every other report's ``values`` contract.
    """
    offered = COMMAND_VALUES.get(command, OFFERED_VALUES)
    keys = offered if values is None else values
    return [GAP_SECTION_FOR_VALUE[key] for key in keys]


# Implements: REQ-p00084-A+B, REQ-d00282-A
def render_section(
    graph: FederatedGraph,
    config: dict[str, Any] | None,
    args: argparse.Namespace,
    command: str = "gaps",
    gap_types: list[str] | None = None,
) -> tuple[str, int]:
    """Render this report's shortfall sections.

    ``command`` names which shorthand is being composed, so a section asked for
    alone and the same section composed with others offer the same values and
    refuse the same names (REQ-d00279-C). An explicit ``gap_types`` is for a
    caller that has already resolved the selection.

    Returns:
        Tuple of (rendered output string, exit code).
        Exit code is always 0 (gap sections are informational).
    """
    from elspais.commands._edges import report_inputs_from_args
    from elspais.commands.health import _resolve_exclude_status

    # Implements: REQ-p00084-A+D, REQ-d00279-C
    # Derived once here rather than resolved twice for scope and values
    # separately: a section composed with others reaches the same scope and
    # the same listing a standalone invocation would.
    offered = COMMAND_VALUES.get(command, OFFERED_VALUES)
    inputs = report_inputs_from_args(args, config, offered, identity_key="")
    if gap_types is None:
        gap_types = gap_sections(inputs.values, command)

    from elspais.commands._scope import flag_values, scope_disclosure
    from elspais.graph.scope import scoped_requirements

    exclude_status = _resolve_exclude_status(flag_values(args, "treat_active"), config=config or {})

    scope_result = scoped_requirements(graph, inputs.scope, config)
    scope_ids = None if len(scope_result.ids) == scope_result.population else scope_result.ids
    data = collect_gaps(graph, exclude_status, config=config, node_ids=scope_ids)
    scope_lines = scope_disclosure(scope_result)

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
        # Implements: REQ-p00084-D
        if scope_lines:
            result["scope"] = scope_lines
        return json.dumps(result, indent=2), 0

    if fmt == "markdown":
        sections = [f"*{line}*" for line in scope_lines]
        sections += [render_gap_markdown(gt, data) for gt in gap_types]
        if show_integrated:
            seg = render_integrated_markdown(data)
            if seg:
                sections.append(seg)
        return "\n\n".join(sections), 0

    # Default: text
    sections = list(scope_lines)
    sections += [render_gap_text(gt, data) for gt in gap_types]
    text = "\n\n".join(sections)
    if show_integrated:
        text += render_integrated_text(data)
    return text, 0


# =============================================================================
# Standalone run
# =============================================================================


def _gap_entry_to_list(entry: GapEntry) -> list:
    """Serialize GapEntry for JSON.

    Uncovered assertions are serialized as ``{"id": ..., "fraction": ...}``
    dicts so an *Assertion* with partial direct evidence (0 < fraction < 1,
    REQ-d00069-M) is distinguishable from one with no evidence attached here
    at all. ``fraction`` is rounded to 4 places, matching the MCP surface
    (server.py), so the two JSON surfaces agree on precision rather than one
    emitting raw floats.
    """
    result: list = [entry.req_id, entry.title]
    if entry.assertions:
        result.append(
            [
                {"id": aid, "label": label, "fraction": round(frac, 4)}
                for aid, label, frac in entry.assertions
            ]
        )
    return result


def _gap_data_from_dict(data: dict[str, Any]) -> GapData:
    """Reconstruct GapData from a JSON dict returned by the daemon."""
    gd = GapData()
    for gt in ("uncovered", "untested", "unvalidated"):
        for item in data.get(gt, []):
            raw_assertions = item[2] if len(item) > 2 else []
            # A payload that carries no label falls back to the full id
            # rather than to an empty bracket: the id is longer than the
            # label but it still says which assertion is uncovered.
            assertions = [
                (a["id"], a.get("label") or a["id"], a.get("fraction", 0.0)) for a in raw_assertions
            ]
            getattr(gd, gt).append(GapEntry(item[0], item[1], assertions))
    for item in data.get("failing", []):
        gd.failing.append(tuple(item))  # type: ignore[arg-type]
    integrated = data.get("integrated", {})
    if isinstance(integrated, dict):
        gd.integrated = {k: list(v) for k, v in integrated.items()}
    return gd


# Implements: REQ-d00279-C
def compute_gaps(graph: FederatedGraph, config: dict, request: GapsRequest) -> dict:
    """The gap listing this request asks for.

    Resolves nothing: the scope was expanded and the selection resolved at the
    edge that was invoked, which is the only place that could tell a project's
    declaration from a reader's own words (REQ-d00280-D).
    """
    from elspais.commands.health import _resolve_exclude_status

    exclude_status = _resolve_exclude_status(request.treat_active, config=config)
    from elspais.commands._scope import scope_disclosure
    from elspais.graph.scope import scoped_requirements

    scope_result = scoped_requirements(graph, request.scope, config)
    ids = None if len(scope_result.ids) == scope_result.population else scope_result.ids
    data = collect_gaps(graph, exclude_status, config=config, node_ids=ids)
    scope_lines = scope_disclosure(scope_result)

    def _serialize_gap_list(gt: str) -> list:
        items = getattr(data, gt)
        if gt == "failing":
            return [list(item) for item in items]
        return [_gap_entry_to_list(entry) for entry in items]

    integrated = {k: sorted(v) for k, v in data.integrated.items()}

    # Implements: REQ-d00279-C
    # The sections come from the selection the invocation carried here, read by
    # the same function the local paths read it with -- a serving process that
    # decided for itself which sections a report holds is how a daemon-served
    # report starts differing from a locally computed one.
    sections = gap_sections(request.values, request.command)

    result: dict[str, Any] = {}
    for gt in sections:
        result[gt] = _serialize_gap_list(gt)
    if integrated and "uncovered" in sections:
        result["integrated"] = integrated
    # Implements: REQ-p00084-D
    if scope_lines:
        result["scope"] = scope_lines
    return result


# Implements: REQ-d00279-C
def run(args: argparse.Namespace) -> int:
    """Run a standalone gap listing command.

    Tries a running daemon/viewer first for fast results,
    falls back to local graph build.
    """
    from elspais.commands._edges import report_inputs_from_args
    from elspais.commands._engine import call as engine_call
    from elspais.commands._requests import GapsRequest
    from elspais.commands._scope import flag_values
    from elspais.commands._values import UnofferedValues
    from elspais.config import get_config

    command = getattr(args, "command", "gaps")
    config = get_config(getattr(args, "config", None))

    # Implements: REQ-d00282-A+F
    # Resolved before anything is built or asked of a serving process. A name
    # this command does not offer is refused outright rather than dropped, which
    # is what keeps a reader from receiving a narrower report than they asked
    # for while it looks exactly like the one they wanted.
    try:
        inputs = report_inputs_from_args(
            args, config, COMMAND_VALUES.get(command, OFFERED_VALUES), identity_key=""
        )
    except UnofferedValues as exc:
        print(f"Error: {command}: {exc}", file=sys.stderr)
        return 1

    request = GapsRequest(
        scope=inputs.scope,
        values=inputs.values,
        command=command,
        treat_active=flag_values(args, "treat_active"),
    )

    fmt = getattr(args, "format", "text")
    spec_dir = getattr(args, "spec_dir", None)

    data = engine_call(
        "/api/run/gaps",
        request,
        compute_gaps,
        config_path=getattr(args, "config", None),
        skip_daemon=bool(spec_dir),
    )

    # Implements: REQ-d00282-E
    # Resolved again from the request AS RESOLVED here, not re-derived from the
    # payload: rendering states the sections this reader asked for whether the
    # payload was computed locally or by a serving process.
    gap_types: list[str] | None = gap_sections(inputs.values, command)

    scope_lines = data.get("scope") or []
    if fmt == "json":
        output = json.dumps(data, indent=2)
    else:
        gap_data = _gap_data_from_dict(data)
        types_to_render = gap_types or _ALL_GAP_TYPES
        show_integrated = "uncovered" in types_to_render
        if fmt == "markdown":
            sections = [f"*{line}*" for line in scope_lines]
            sections += [render_gap_markdown(gt, gap_data) for gt in types_to_render]
            if show_integrated:
                seg = render_integrated_markdown(gap_data)
                if seg:
                    sections.append(seg)
            output = "\n\n".join(sections)
        else:
            sections = list(scope_lines)
            sections += [render_gap_text(gt, gap_data) for gt in types_to_render]
            output = "\n\n".join(sections)
            if show_integrated:
                output += render_integrated_text(gap_data)

    output_file = getattr(args, "output", None)
    if output_file:
        Path(output_file).write_text(output + "\n")
    else:
        print(output)

    return 0
