# Verifies: REQ-d00085, REQ-d00241
"""Tests for traceability-focused health checks.

Tests check_structural_orphans(), check_unlinked_tests(), check_unlinked_code(),
check_reference_class(), config backward compatibility for allow_orphans, and
the code.no_traceability wiring in run_code_checks() (REQ-d00241).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from elspais.commands.health import (
    HealthFinding,
    HealthReport,
    check_no_cycles,
    check_reference_class,
    check_structural_orphans,
    check_unlinked_code,
    check_unlinked_tests,
    run_code_checks,
    run_spec_checks,
)
from elspais.config import _merge_configs, config_defaults, get_config
from elspais.graph.builder import TraceGraph
from elspais.graph.federated import FederatedGraph, RepoEntry
from elspais.graph.GraphNode import FileType, GraphNode, NodeKind, make_file_id
from elspais.graph.reference_faults import FaultClass
from elspais.graph.relations import EdgeKind
from tests.federation_repos import make_repo

from ..core.graph_test_helpers import (
    HELPER_NAMESPACE,
    build_graph,
    make_code_ref,
    make_requirement,
    make_test_ref,
)


def _wrap(graph: TraceGraph, config: dict | None = None) -> FederatedGraph:
    """Wrap a bare TraceGraph in a federation-of-one.

    ``from_single`` requires a config with ``[project].name`` populated.
    A test-default name is injected when the caller doesn't supply one,
    or when the supplied config lacks a project name (e.g. raw
    ``config_defaults()``).
    """
    if config is None:
        config = {"project": {"name": "test", "namespace": "REQ"}}
    elif not (config.get("project") or {}).get("name"):
        config = dict(config)
        config.setdefault("project", {})
        config["project"] = dict(config["project"])
        config["project"]["name"] = "test"
    return FederatedGraph.from_single(graph, config, graph.repo_root or Path("/test/repo"))


# =============================================================================
# Structural Orphans
# =============================================================================


class TestCheckStructuralOrphans:
    """Tests for check_structural_orphans()."""

    def test_REQ_d00085_no_orphans_passes(self) -> None:
        """A graph with all nodes under FILE parents passes."""
        graph = build_graph(
            make_requirement("REQ-p00001", title="Parent", level="PRD"),
        )
        check = check_structural_orphans(graph)
        assert check.passed
        assert check.name == "spec.structural_orphans"

    def test_REQ_d00085_orphan_node_fails_with_error_severity(self) -> None:
        """A node without a FILE ancestor is a structural orphan — severity error."""
        graph = build_graph(
            make_requirement("REQ-p00001", title="Parent", level="PRD"),
        )
        # Add an orphan node (no FILE parent)
        orphan = GraphNode(id="REQ-o99999", kind=NodeKind.REQUIREMENT, label="Orphan")
        orphan.set_field("level", "OPS")
        orphan.set_field("status", "Active")
        graph._index["REQ-o99999"] = orphan

        check = check_structural_orphans(graph)
        assert not check.passed
        assert check.severity == "error"
        assert check.name == "spec.structural_orphans"
        assert len(check.findings) >= 1
        orphan_ids = {f.node_id for f in check.findings}
        assert "REQ-o99999" in orphan_ids

    def test_REQ_d00085_allow_structural_orphans_skips(self) -> None:
        """When allow_structural_orphans=True, the check passes even with orphans."""
        graph = build_graph(
            make_requirement("REQ-p00001", title="Parent", level="PRD"),
        )
        orphan = GraphNode(id="REQ-o99999", kind=NodeKind.REQUIREMENT, label="Orphan")
        graph._index["REQ-o99999"] = orphan

        check = check_structural_orphans(graph, allow_structural_orphans=True)
        assert check.passed
        assert "skipped" in check.message.lower() or "allow" in check.message.lower()


# =============================================================================
# Unlinked Tests
# =============================================================================


class TestCheckUnlinkedTests:
    """Tests for check_unlinked_tests() — file-level semantics.

    Unlinked means a TEST-type FILE was scanned and either contains no
    TEST child nodes at all, or contains TEST children none of which
    link to any requirement (REQ-d00241-D). The second condition matters
    because the parser emits a TEST node for every discovered test
    function whether or not it carries a ``Verifies:`` marker, so a
    fully marker-less file still has TEST children.
    """

    def test_REQ_d00085_all_test_files_have_markers_passes(self) -> None:
        """When all test files contain traceability markers, the check passes."""
        graph = build_graph(
            make_requirement("REQ-p00001", title="Feature", level="PRD"),
            make_test_ref(
                verifies=["REQ-p00001"],
                source_path="tests/test_feature.py",
                start_line=1,
                end_line=5,
            ),
        )
        check = check_unlinked_tests(graph)
        assert check.passed
        assert check.name == "tests.unlinked"

    def test_REQ_d00085_unlinked_test_file_has_info_severity(self) -> None:
        """A TEST file with no TEST child nodes is unlinked — severity info."""
        graph = build_graph(
            make_requirement("REQ-p00001", title="Feature", level="PRD"),
            make_test_ref(
                verifies=["REQ-p00001"],
                source_path="tests/test_linked.py",
                start_line=1,
                end_line=5,
            ),
        )
        # Add a TEST-type FILE with no TEST children
        empty_file = GraphNode(
            id="file:tests/test_empty.py", kind=NodeKind.FILE, label="test_empty.py"
        )
        empty_file.set_field("file_type", FileType.TEST)
        empty_file.set_field("relative_path", "tests/test_empty.py")
        graph._index["file:tests/test_empty.py"] = empty_file
        graph._roots.append(empty_file)

        check = check_unlinked_tests(graph)
        assert not check.passed
        assert check.severity == "info"
        assert check.name == "tests.unlinked"
        assert len(check.findings) >= 1
        assert check.details.get("count", 0) >= 1

    def test_REQ_d00085_unlinked_test_findings_have_file_path(self) -> None:
        """Findings for unlinked test files include file_path."""
        graph = TraceGraph()
        empty_file = GraphNode(
            id="file:tests/test_orphan.py", kind=NodeKind.FILE, label="test_orphan.py"
        )
        empty_file.set_field("file_type", FileType.TEST)
        empty_file.set_field("relative_path", "tests/test_orphan.py")
        graph._index["file:tests/test_orphan.py"] = empty_file
        graph._roots.append(empty_file)

        check = check_unlinked_tests(graph)
        assert not check.passed
        assert len(check.findings) >= 1
        finding = check.findings[0]
        assert isinstance(finding, HealthFinding)
        assert finding.file_path is not None

    # Verifies: REQ-d00241-D
    def test_REQ_d00241_D_marker_less_file_with_test_children_flagged(self) -> None:
        """A test FILE whose TEST children all lack requirement links is flagged.

        The parser's third pass emits a TEST node for every discovered
        test function even when it has no ``Verifies:`` marker, so a
        marker-less file is NOT the zero-TEST-children case -- it has
        children, just none linked. Before REQ-d00241-D this file was
        reported by neither tests.unlinked (which only looked for zero
        children) nor code.no_traceability (now code-only): a silent
        detection gap.
        """
        graph = build_graph(
            make_test_ref(
                verifies=[],
                source_path="tests/test_unmarked.py",
                function_name="test_no_marker",
                start_line=1,
                end_line=5,
            ),
        )
        # Sanity: the file really has a TEST child (not the empty-file case).
        file_node = graph._index[make_file_id(HELPER_NAMESPACE, "tests/test_unmarked.py")]
        assert any(
            c.kind == NodeKind.TEST for c in file_node.iter_children(edge_kinds={EdgeKind.CONTAINS})
        )

        check = check_unlinked_tests(graph)
        assert not check.passed
        assert any(f.file_path == "tests/test_unmarked.py" for f in check.findings)

    # Verifies: REQ-d00241-D
    def test_REQ_d00241_D_partially_marked_file_not_flagged(self) -> None:
        """A test FILE with at least one linked TEST child is NOT flagged.

        Partial marking isn't "unlinked" -- one linked test is enough to
        establish file-level traceability.
        """
        graph = build_graph(
            make_requirement("REQ-p00001", title="Feature", level="PRD"),
            make_test_ref(
                verifies=["REQ-p00001"],
                source_path="tests/test_partial.py",
                function_name="test_marked",
                start_line=1,
                end_line=5,
            ),
            make_test_ref(
                verifies=[],
                source_path="tests/test_partial.py",
                function_name="test_unmarked",
                start_line=10,
                end_line=15,
            ),
        )
        check = check_unlinked_tests(graph)
        assert check.passed
        assert not any(f.file_path == "tests/test_partial.py" for f in check.findings)


# =============================================================================
# Unlinked Code
# =============================================================================


class TestCheckUnlinkedCode:
    """Tests for check_unlinked_code() — file-level semantics.

    Unlinked means a CODE-type FILE was scanned but contains no CODE
    child nodes (no traceability markers found).
    """

    def test_REQ_d00085_all_code_files_have_markers_passes(self) -> None:
        """When all code files contain traceability markers, the check passes."""
        graph = build_graph(
            make_requirement("REQ-p00001", title="Feature", level="PRD"),
            make_code_ref(
                implements=["REQ-p00001"],
                source_path="src/feature.py",
                start_line=1,
                end_line=5,
            ),
        )
        check = check_unlinked_code(graph)
        assert check.passed
        assert check.name == "code.unlinked"

    def test_REQ_d00085_unlinked_code_file_has_info_severity(self) -> None:
        """A CODE file with no CODE child nodes is unlinked — severity info."""
        graph = build_graph(
            make_requirement("REQ-p00001", title="Feature", level="PRD"),
            make_code_ref(
                implements=["REQ-p00001"],
                source_path="src/linked.py",
                start_line=1,
                end_line=5,
            ),
        )
        # Add a CODE-type FILE with no CODE children
        empty_file = GraphNode(id="file:src/unlinked.py", kind=NodeKind.FILE, label="unlinked.py")
        empty_file.set_field("file_type", FileType.CODE)
        empty_file.set_field("relative_path", "src/unlinked.py")
        graph._index["file:src/unlinked.py"] = empty_file
        graph._roots.append(empty_file)

        check = check_unlinked_code(graph)
        assert not check.passed
        assert check.severity == "info"
        assert check.name == "code.unlinked"
        assert len(check.findings) >= 1
        assert check.details.get("count", 0) >= 1

    def test_REQ_d00085_unlinked_code_findings_have_file_path(self) -> None:
        """Findings for unlinked code files include file_path."""
        graph = TraceGraph()
        empty_file = GraphNode(id="file:src/orphan.py", kind=NodeKind.FILE, label="orphan.py")
        empty_file.set_field("file_type", FileType.CODE)
        empty_file.set_field("relative_path", "src/orphan.py")
        graph._index["file:src/orphan.py"] = empty_file
        graph._roots.append(empty_file)

        check = check_unlinked_code(graph)
        assert not check.passed
        assert len(check.findings) >= 1
        finding = check.findings[0]
        assert isinstance(finding, HealthFinding)
        assert finding.file_path is not None


# =============================================================================
# code.no_traceability wiring — REQ-d00241 (code-only; tests owned by
# tests.unlinked)
# =============================================================================


class TestRunCodeChecksNoTraceabilityWiring:
    """Tests for the code.no_traceability wiring in run_code_checks().

    REQ-d00241-A/B previously described ``check_no_traceability`` as
    covering "code and test files" / "CODE/TEST nodes", and
    ``run_code_checks()`` fed it unlinked nodes of *both*
    ``NodeKind.CODE`` and ``NodeKind.TEST``. Because the test-file parser
    unconditionally creates a TEST node for every test function found
    (marked or not -- see ``GraphBuilder._add_test_ref``), a test file
    with unmarked functions produced marker-less TEST nodes that were
    *also* separately reported by ``tests.unlinked``
    (``check_unlinked_tests``), double-reporting the same file once
    under each category. REQ-d00241 was reworded to scope
    ``code.no_traceability`` to CODE nodes only; test files are now
    exclusively the responsibility of ``tests.unlinked``.
    """

    # Verifies: REQ-d00241-B, REQ-d00241-E
    def test_REQ_d00241_E_dangling_implements_excluded_owned_by_reference_check(self) -> None:
        """A CODE node unlinked because its ``Implements:`` target failed to
        resolve carries a marker -- it just failed. ``code.no_traceability``
        would call that file unmarked, sending its author to add a marker
        that is already there; the file is excluded here and belongs to
        ``references.unknown_requirement`` instead (REQ-d00241-E).

        Uses a dangling ``implements`` target (rather than an empty list)
        because ``GraphBuilder._add_code_ref`` only creates a CODE node
        per referenced id -- unlike TEST, there's no unconditional
        per-function pass, so a target that fails to resolve is what
        makes the node exist-but-unreachable. Under REQ-d00241-E every path
        that leaves a CODE node exist-but-unreachable also records the
        fault that explains why, so this is also the only way to build one.
        """
        graph = build_graph(
            make_code_ref(
                implements=["REQ-p09999"], source_path="src/orphan.py", start_line=1, end_line=5
            ),
        )
        fed = _wrap(graph)
        checks = run_code_checks(fed)
        check = next(c for c in checks if c.name == "code.no_traceability")
        assert check.passed
        assert not any("orphan.py" in f.message for f in check.findings)

        broken = check_broken_references(fed)
        assert not broken.passed
        assert any("orphan.py" in (f.file_path or "") for f in broken.findings)

    # Verifies: REQ-d00241-A, REQ-d00241-B, REQ-d00241-D
    def test_REQ_d00241_A_marker_less_test_function_excluded(self) -> None:
        """A marker-less test file moves from code.no_traceability to tests.unlinked.

        Regression guard for the double-report defect AND its inverse (the
        detection gap): a test function with no ``Verifies:`` marker still
        produces an unreachable TEST node (per the parser's unconditional
        per-function emission). code.no_traceability must not surface it
        -- that's tests.unlinked's job -- and tests.unlinked MUST surface
        it, otherwise the file silently escapes both checks.
        """
        graph = build_graph(
            make_test_ref(
                verifies=[],
                source_path="tests/test_unmarked.py",
                function_name="test_something",
                start_line=1,
                end_line=5,
            ),
        )
        # Sanity: the TEST node really is unlinked (has a FILE parent,
        # unreachable to any requirement) -- otherwise this test would
        # pass vacuously regardless of the wiring fix.
        assert list(graph.iter_unlinked(NodeKind.TEST))

        checks = run_code_checks(_wrap(graph))
        check = next(c for c in checks if c.name == "code.no_traceability")
        assert check.passed
        assert not any("test_unmarked.py" in f.message for f in check.findings)

        # The file MUST be owned by tests.unlinked instead (REQ-d00241-D).
        tests_check = check_unlinked_tests(_wrap(graph))
        assert not tests_check.passed
        assert any(f.file_path == "tests/test_unmarked.py" for f in tests_check.findings)

    # Verifies: REQ-d00241-A, REQ-d00241-E
    def test_REQ_d00241_A_mixed_code_and_test_neither_appears_in_no_traceability(self) -> None:
        """With both a dangling-``Implements:`` CODE node and a marker-less
        TEST node, ``code.no_traceability`` reports neither -- the CODE
        file is excluded because its marker failed rather than being
        absent (REQ-d00241-E, owned by ``references.unknown_requirement``);
        the TEST file was never code.no_traceability's to report
        (REQ-d00241-A, owned by ``tests.unlinked``).
        """
        graph = build_graph(
            make_code_ref(
                implements=["REQ-p09999"], source_path="src/orphan.py", start_line=1, end_line=5
            ),
            make_test_ref(
                verifies=[],
                source_path="tests/test_unmarked.py",
                function_name="test_something",
                start_line=1,
                end_line=5,
            ),
        )
        checks = run_code_checks(_wrap(graph))
        check = next(c for c in checks if c.name == "code.no_traceability")
        assert check.passed
        messages = [f.message for f in check.findings]
        assert not any("orphan.py" in m for m in messages)
        assert not any("test_unmarked.py" in m for m in messages)


# =============================================================================
# Broken References
# =============================================================================


def check_broken_references(graph: FederatedGraph, config: dict | None = None):
    """A claimed reference naming a requirement that does not exist."""
    return check_reference_class(
        graph,
        config,
        FaultClass.UNKNOWN_REQUIREMENT,
        "references.unknown_requirement",
        "claimed, but no such requirement exists",
    )


def check_unclaimed_references(graph: FederatedGraph, config: dict | None = None):
    """A reference naming a target no configured repository claims."""
    return check_reference_class(
        graph,
        config,
        FaultClass.UNKNOWN_NAMESPACE,
        "references.unknown_namespace",
        "no configured repository claims this identifier",
    )


class TestCheckBrokenReferences:
    """Tests for check_reference_class(..., FaultClass.UNKNOWN_REQUIREMENT, ...)."""

    def test_REQ_d00085_no_broken_refs_passes(self) -> None:
        """A graph with all references resolved passes."""
        graph = build_graph(
            make_requirement("REQ-p00001", title="Parent", level="PRD"),
            make_requirement("REQ-o00001", title="Child", level="OPS", implements=["REQ-p00001"]),
        )
        check = check_broken_references(_wrap(graph))
        assert check.passed
        assert check.name == "references.unknown_requirement"

    def test_REQ_d00085_broken_refs_warning_severity(self) -> None:
        """Broken references produce an error-severity failure by default."""
        from elspais.graph.reference_faults import ReferenceFault

        graph = build_graph(
            make_requirement("REQ-p00001", title="Parent", level="PRD"),
        )
        # Manually inject broken references (fault_class defaults to
        # UNKNOWN_REQUIREMENT, matching the class this check reports).
        graph._broken_references = [
            ReferenceFault(
                source_id="REQ-d00001",
                target_id="REQ-p99999",
                edge_kind="implements",
            ),
            ReferenceFault(
                source_id="REQ-d00002",
                target_id="REQ-p88888",
                edge_kind="refines",
            ),
        ]

        # A claimed target -- a misspelling of an identifier this repository's
        # grammar describes -- is this check's population; the full default
        # config is what makes ``REQ-`` identifiers claimed.
        config = _claimed_config()
        check = check_broken_references(_wrap(graph, config), config)
        assert not check.passed
        assert check.severity == "error"  # REQ-d00204-E: unknown_requirement is an error
        assert check.name == "references.unknown_requirement"
        assert len(check.findings) == 2
        assert check.details.get("count") == 2

    def test_REQ_d00085_broken_ref_findings_have_source_id(self) -> None:
        """Each broken reference finding includes the source node_id."""
        from elspais.graph.reference_faults import ReferenceFault

        graph = TraceGraph()
        graph._broken_references = [
            ReferenceFault(
                source_id="REQ-d00001",
                target_id="REQ-p99999",
                edge_kind="verifies",
            ),
        ]

        config = _claimed_config()
        check = check_broken_references(_wrap(graph, config), config)
        assert not check.passed
        finding = check.findings[0]
        assert isinstance(finding, HealthFinding)
        assert finding.node_id == "REQ-d00001"
        assert "REQ-p99999" in finding.message

    def test_REQ_d00269_F_unclaimed_target_reported_separately(self) -> None:
        """A target no configured repository claims is
        ``references.unknown_namespace``, not ``references.unknown_requirement``
        -- each check reports exactly the class its name promises."""
        from elspais.graph.reference_faults import FaultClass as FC
        from elspais.graph.reference_faults import ReferenceFault

        graph = TraceGraph()
        graph._broken_references = [
            ReferenceFault(
                source_id="REQ-d00001",
                target_id="HHT-p00001",
                edge_kind="implements",
                fault_class=FC.UNKNOWN_NAMESPACE,
            ),
        ]
        config = config_defaults()
        fed = _wrap(graph, config)

        unclaimed = check_unclaimed_references(fed, config)
        assert not unclaimed.passed
        assert any("HHT-p00001" in f.message for f in unclaimed.findings)

        broken = check_broken_references(fed, config)
        assert broken.passed
        assert not any("HHT-p00001" in f.message for f in broken.findings)


# =============================================================================
# Unclaimed References
# =============================================================================


def _claimed_config(**overrides: object) -> dict:
    """A full default config naming this repo, so ``REQ-`` ids are claimed."""
    config = _merge_configs(config_defaults(), dict(overrides))
    config["project"] = {"name": "test", "namespace": "REQ"}
    return config


# Verifies: REQ-d00269-F
class TestCheckUnclaimedReferences:
    """Tests for check_unclaimed_references() — the dedicated check.

    Validates REQ-d00269-F: a reference recognised by position may name
    anything at all, so a
    target no configured repository claims is reported separately from a
    misspelling of an identifier the federation understands, at a
    severity the project chooses.
    """

    def test_REQ_d00269_F_unclaimed_target_in_code_is_reported_once(self, tmp_path) -> None:
        """A real on-disk scan: one finding, naming the unreadable target.

        The reference sits in canonical position, so position recognises
        it; its lowercase namespace is claimed by no configured grammar,
        so only this check may speak for it.
        """
        from elspais.graph.factory import build_graph

        repo = make_repo(tmp_path, "solo", namespace="REQ", req_id="REQ-d00001")
        (repo / "src").mkdir()
        (repo / "src" / "impl.py").write_text(
            "# Implements: widget-42\ndef impl():\n    pass\n", encoding="utf-8"
        )

        federated = build_graph(repo_root=repo)
        unclaimed = check_unclaimed_references(federated)

        assert not unclaimed.passed
        assert unclaimed.name == "references.unknown_namespace"
        assert unclaimed.category == "references"
        assert len(unclaimed.findings) == 1
        assert "widget-42" in unclaimed.findings[0].message

        # The two checks partition the population: neither double-reports.
        broken = check_broken_references(federated)
        assert not any("widget-42" in f.message for f in broken.findings)
        assert broken.passed

    def test_REQ_d00269_F_claimed_target_stays_with_broken_references(self) -> None:
        """A misspelt local identifier is a broken reference, not an unclaimed one."""
        from elspais.graph.reference_faults import ReferenceFault

        graph = TraceGraph()
        graph._broken_references = [
            ReferenceFault(source_id="REQ-d00001", target_id="REQ-p99999", edge_kind="implements"),
        ]
        config = _claimed_config()
        fed = _wrap(graph, config)

        broken = check_broken_references(fed, config)
        unclaimed = check_unclaimed_references(fed, config)

        assert not broken.passed
        assert any("REQ-p99999" in f.message for f in broken.findings)
        assert unclaimed.passed
        assert unclaimed.findings == []

    @pytest.mark.parametrize("configured", ["info", "warning", "error"])
    def test_REQ_d00269_F_severity_follows_configuration(self, configured: str) -> None:
        """Noticing is not the project's decision; how loudly is."""
        from elspais.graph.reference_faults import ReferenceFault

        graph = TraceGraph()
        graph._broken_references = [
            ReferenceFault(
                source_id="REQ-d00001",
                target_id="widget-42",
                edge_kind="implements",
                fault_class=FaultClass.UNKNOWN_NAMESPACE,
            ),
        ]
        config = _claimed_config(rules={"references": {"unknown_namespace": configured}})

        check = check_unclaimed_references(_wrap(graph, config), config)

        assert not check.passed
        assert check.severity == configured

    # Verifies: REQ-d00269-F
    @pytest.mark.parametrize("configured", ["info", "warning", "error"])
    @pytest.mark.parametrize("has_finding", [True, False])
    def test_REQ_d00269_F_severity_is_the_configured_one_in_both_states(
        self, configured: str, has_finding: bool
    ) -> None:
        """The severity a check reports is the project's setting, not a
        property of what the check happened to find.

        A check that reports the configured severity only when it has
        findings answers a different question on a clean estate — and a
        report reader cannot tell the difference between "this project
        treats unclaimed references as errors" and "this check forgot".
        """
        from elspais.graph.reference_faults import ReferenceFault

        graph = TraceGraph()
        if has_finding:
            graph._broken_references = [
                ReferenceFault(
                    source_id="REQ-d00001",
                    target_id="widget-42",
                    edge_kind="implements",
                    fault_class=FaultClass.UNKNOWN_NAMESPACE,
                ),
            ]
        config = _claimed_config(rules={"references": {"unknown_namespace": configured}})

        check = check_unclaimed_references(_wrap(graph, config), config)

        report = HealthReport()
        report.add(check)

        assert bool(check.findings) is has_finding
        assert check.severity == configured
        # The serialized report is what every downstream consumer reads.
        assert report.to_dict()["checks"][0]["severity"] == configured

    # Verifies: REQ-d00269-F
    @pytest.mark.parametrize("has_finding", [True, False])
    def test_REQ_d00269_F_info_severity_never_lands_in_passed(self, has_finding: bool) -> None:
        """The bucket the check is counted under follows its configured
        severity, so it does not migrate between report headings.

        ``HealthReport`` counts every ``info`` check as *skipped* and
        excludes it from *passed*. A check configured informational that
        reported ``error`` when it found nothing was counted as passed on
        a clean run and skipped on a dirty one — the same check under two
        headings from one run to the next.
        """
        from elspais.graph.reference_faults import ReferenceFault

        graph = TraceGraph()
        if has_finding:
            graph._broken_references = [
                ReferenceFault(
                    source_id="REQ-d00001",
                    target_id="widget-42",
                    edge_kind="implements",
                    fault_class=FaultClass.UNKNOWN_NAMESPACE,
                ),
            ]
        config = _claimed_config(rules={"references": {"unknown_namespace": "info"}})

        report = HealthReport()
        report.add(check_unclaimed_references(_wrap(graph, config), config))

        assert report.skipped == 1
        assert report.passed == 0
        assert report.to_dict()["checks"][0]["severity"] == "info"

    # Verifies: REQ-d00269-F
    @pytest.mark.parametrize(
        "configured,has_finding,bucket",
        [
            ("warning", False, "passed"),
            ("warning", True, "warnings"),
            ("error", False, "passed"),
            ("error", True, "failed"),
        ],
    )
    def test_REQ_d00269_F_failing_severities_bucket_by_findings(
        self, configured: str, has_finding: bool, bucket: str
    ) -> None:
        """A check the project asked to hear about loudly is counted as
        passed when clean and against its own severity when not — and is
        never counted as skipped, which is reserved for informational."""
        from elspais.graph.reference_faults import ReferenceFault

        graph = TraceGraph()
        if has_finding:
            graph._broken_references = [
                ReferenceFault(
                    source_id="REQ-d00001",
                    target_id="widget-42",
                    edge_kind="implements",
                    fault_class=FaultClass.UNKNOWN_NAMESPACE,
                ),
            ]
        config = _claimed_config(rules={"references": {"unknown_namespace": configured}})

        report = HealthReport()
        report.add(check_unclaimed_references(_wrap(graph, config), config))

        counts = {"passed": report.passed, "warnings": report.warnings, "failed": report.failed}
        assert counts[bucket] == 1
        assert sum(counts.values()) == 1
        assert report.skipped == 0

    @pytest.mark.parametrize("severity", ["ok", "error"])
    def test_REQ_d00269_F_unknown_namespace_ok_silences_the_finding(self, severity: str) -> None:
        """A project that does not want to hear about references into
        unconfigured repositories sets ``unknown_namespace = "ok"`` --
        the successor to ``allow_unresolved_cross_repo``, which named a
        boolean flag rather than the severity the project actually wanted.
        Any other value keeps reporting it.
        """
        from elspais.graph.reference_faults import ReferenceFault

        host_graph = TraceGraph()
        host_graph._broken_references = [
            ReferenceFault(
                source_id="REQ-d00001",
                target_id="widget-42",
                edge_kind="implements",
                fault_class=FaultClass.UNKNOWN_NAMESPACE,
            ),
        ]
        host_config = _merge_configs(
            config_defaults(),
            {"rules": {"references": {"unknown_namespace": severity}}},
        )
        host_config["project"] = {"name": "host", "namespace": "REQ"}
        lib_config = config_defaults()
        lib_config["project"] = {"name": "lib", "namespace": "HHT"}

        fed = FederatedGraph(
            [
                RepoEntry(
                    name="host",
                    graph=host_graph,
                    config=host_config,
                    repo_root=Path("/repo/host"),
                ),
                RepoEntry(
                    name="lib",
                    graph=TraceGraph(),
                    config=lib_config,
                    repo_root=Path("/repo/lib"),
                ),
            ],
            root_repo="host",
        )

        check = check_unclaimed_references(fed, host_config)

        # Silenced ("ok") still passes and still names the finding -- "ok"
        # is a severity that reports without failing the run, not a filter.
        assert check.passed is (severity == "ok")
        assert any("widget-42" in f.message for f in check.findings)


# =============================================================================
# Requirement Cycles
# =============================================================================


class TestCheckNoCycles:
    """Tests for check_no_cycles() — REQ-d00204-G."""

    # Verifies: REQ-d00204-G
    def test_REQ_d00204_G_acyclic_graph_passes(self) -> None:
        """A normal acyclic requirement graph reports no cycles."""
        graph = build_graph(
            make_requirement("REQ-p00001", title="Parent", level="PRD"),
            make_requirement("REQ-o00001", title="Child", level="OPS", implements=["REQ-p00001"]),
        )
        check = check_no_cycles(_wrap(graph))
        assert check.passed is True
        assert check.name == "spec.no_cycles"

    # Verifies: REQ-d00204-G
    def test_REQ_d00204_G_injected_cycle_fails_and_names_both_ids(self) -> None:
        """A 2-node requirement cycle is detected; the finding names both ids."""
        graph = build_graph(
            make_requirement("REQ-p00001", title="A", level="PRD"),
            make_requirement("REQ-p00002", title="B", level="PRD"),
        )
        reqs = {n.id: n for n in graph.nodes_by_kind(NodeKind.REQUIREMENT)}
        a = reqs["REQ-p00001"]
        b = reqs["REQ-p00002"]
        # Inject a genuine cycle: a -> b -> a through REQUIREMENT children.
        a.link(b, EdgeKind.INTEGRATES)
        b.link(a, EdgeKind.INTEGRATES)

        check = check_no_cycles(_wrap(graph))
        assert check.passed is False
        assert check.name == "spec.no_cycles"
        assert len(check.findings) == 1
        finding = check.findings[0]
        assert isinstance(finding, HealthFinding)
        assert "REQ-p00001" in finding.message
        assert "REQ-p00002" in finding.message


# =============================================================================
# Config backward compatibility: allow_orphans -> allow_structural_orphans
# =============================================================================


class TestConfigBackwardCompat:
    """Test that legacy allow_orphans config key is respected."""

    def test_REQ_d00085_allow_structural_orphans_skips_check(self, tmp_path: Path) -> None:
        """allow_structural_orphans=true skips structural orphan check."""
        config_path = tmp_path / ".elspais.toml"
        config_path.write_text(
            """version = 4

[project]
name = "test-compat"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]

[rules.hierarchy]
allow_structural_orphans = true
"""
        )
        raw = get_config(config_path)
        config = _merge_configs(config_defaults(), raw)

        # Build a graph with an orphan
        graph = build_graph(
            make_requirement("REQ-p00001", title="Parent", level="PRD"),
        )
        orphan = GraphNode(id="REQ-o99999", kind=NodeKind.REQUIREMENT, label="Orphan")
        graph._index["REQ-o99999"] = orphan

        checks = run_spec_checks(_wrap(graph, config), config)
        structural_check = next(c for c in checks if c.name == "spec.structural_orphans")
        assert (
            structural_check.passed
        ), "allow_structural_orphans=true should skip structural orphan check"

    def test_REQ_d00085_allow_structural_orphans_false_runs_check(self, tmp_path: Path) -> None:
        """allow_structural_orphans=false runs the check regardless of allow_orphans."""
        config_path = tmp_path / ".elspais.toml"
        config_path.write_text(
            """version = 4

[project]
name = "test-precedence"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]

[rules.hierarchy]
allow_orphans = true
allow_structural_orphans = false
"""
        )
        raw = get_config(config_path)
        config = _merge_configs(config_defaults(), raw)

        graph = build_graph(
            make_requirement("REQ-p00001", title="Parent", level="PRD"),
        )
        orphan = GraphNode(id="REQ-o99999", kind=NodeKind.REQUIREMENT, label="Orphan")
        graph._index["REQ-o99999"] = orphan

        checks = run_spec_checks(_wrap(graph, config), config)
        structural_check = next(c for c in checks if c.name == "spec.structural_orphans")
        assert (
            not structural_check.passed
        ), "allow_structural_orphans=false should run structural orphan check"
