# Verifies: REQ-d00085
"""Tests for traceability-focused health checks.

Tests check_structural_orphans(), check_unlinked_tests(), check_unlinked_code(),
check_broken_references(), and config backward compatibility for allow_orphans.
"""
from __future__ import annotations

from pathlib import Path

from elspais.commands.health import (
    HealthFinding,
    check_broken_references,
    check_structural_orphans,
    check_unlinked_code,
    check_unlinked_tests,
    run_spec_checks,
)
from elspais.config import ConfigLoader, get_config
from elspais.graph.builder import TraceGraph
from elspais.graph.federated import FederatedGraph
from elspais.graph.GraphNode import FileType, GraphNode, NodeKind
from elspais.graph.relations import EdgeKind

from ..core.graph_test_helpers import (
    build_graph,
    make_code_ref,
    make_requirement,
    make_test_ref,
)


def _wrap(graph: TraceGraph, config: ConfigLoader | None = None) -> FederatedGraph:
    """Wrap a bare TraceGraph in a federation-of-one."""
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
    """Tests for check_unlinked_tests()."""

    def test_REQ_d00085_all_tests_linked_passes(self) -> None:
        """When all TEST nodes validate a requirement, the check passes."""
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

    def test_REQ_d00085_unlinked_test_has_info_severity(self) -> None:
        """A TEST with FILE parent but no requirement link is unlinked — severity info."""
        graph = build_graph(
            make_requirement("REQ-p00001", title="Feature", level="PRD"),
            make_test_ref(
                verifies=["REQ-p00001"],
                source_path="tests/test_linked.py",
                start_line=1,
                end_line=5,
            ),
            make_test_ref(
                verifies=[],
                source_path="tests/test_unlinked.py",
                start_line=1,
                end_line=5,
            ),
        )
        check = check_unlinked_tests(graph)
        assert not check.passed
        assert check.severity == "info"
        assert check.name == "tests.unlinked"
        assert len(check.findings) >= 1
        # The count should reflect exactly 1 unlinked test
        assert check.details.get("count", 0) >= 1

    def test_REQ_d00085_unlinked_test_findings_have_file_path(self) -> None:
        """Findings for unlinked tests include file_path and node_id."""
        graph = build_graph(
            make_test_ref(
                verifies=[],
                source_path="tests/test_orphan.py",
                start_line=1,
                end_line=5,
            ),
        )
        check = check_unlinked_tests(graph)
        assert not check.passed
        assert len(check.findings) >= 1
        finding = check.findings[0]
        assert isinstance(finding, HealthFinding)
        assert finding.node_id is not None
        assert finding.file_path is not None


# =============================================================================
# Unlinked Code
# =============================================================================


class TestCheckUnlinkedCode:
    """Tests for check_unlinked_code()."""

    def test_REQ_d00085_all_code_linked_passes(self) -> None:
        """When all CODE nodes implement a requirement, the check passes."""
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

    def test_REQ_d00085_unlinked_code_has_info_severity(self) -> None:
        """A CODE node with FILE parent but no requirement link — severity info."""
        graph = build_graph(
            make_requirement("REQ-p00001", title="Feature", level="PRD"),
            make_code_ref(
                implements=["REQ-p00001"],
                source_path="src/linked.py",
                start_line=1,
                end_line=5,
            ),
        )
        # Manually add an unlinked CODE node under a FILE parent
        file_node = GraphNode(id="file:src/unlinked.py", kind=NodeKind.FILE, label="unlinked.py")
        file_node.set_field("file_type", FileType.CODE)
        file_node.set_field("relative_path", "src/unlinked.py")
        graph._index["file:src/unlinked.py"] = file_node

        code_node = GraphNode(
            id="code:src/unlinked.py:1", kind=NodeKind.CODE, label="Unlinked Code"
        )
        code_node.set_field("parse_line", 1)
        file_node.link(code_node, EdgeKind.CONTAINS)
        graph._index["code:src/unlinked.py:1"] = code_node

        check = check_unlinked_code(graph)
        assert not check.passed
        assert check.severity == "info"
        assert check.name == "code.unlinked"
        assert len(check.findings) >= 1
        assert check.details.get("count", 0) >= 1

    def test_REQ_d00085_unlinked_code_findings_have_file_path(self) -> None:
        """Findings for unlinked code include file_path and node_id."""
        graph = TraceGraph()
        file_node = GraphNode(id="file:src/orphan.py", kind=NodeKind.FILE, label="orphan.py")
        file_node.set_field("file_type", FileType.CODE)
        file_node.set_field("relative_path", "src/orphan.py")
        graph._index["file:src/orphan.py"] = file_node

        code_node = GraphNode(id="code:src/orphan.py:1", kind=NodeKind.CODE, label="Orphan Code")
        code_node.set_field("parse_line", 1)
        file_node.link(code_node, EdgeKind.CONTAINS)
        graph._index["code:src/orphan.py:1"] = code_node

        check = check_unlinked_code(graph)
        assert not check.passed
        assert len(check.findings) >= 1
        finding = check.findings[0]
        assert isinstance(finding, HealthFinding)
        assert finding.node_id is not None
        assert finding.file_path is not None


# =============================================================================
# Broken References
# =============================================================================


class TestCheckBrokenReferences:
    """Tests for check_broken_references()."""

    def test_REQ_d00085_no_broken_refs_passes(self) -> None:
        """A graph with all references resolved passes."""
        graph = build_graph(
            make_requirement("REQ-p00001", title="Parent", level="PRD"),
            make_requirement("REQ-o00001", title="Child", level="OPS", implements=["REQ-p00001"]),
        )
        check = check_broken_references(_wrap(graph))
        assert check.passed
        assert check.name == "spec.broken_references"

    def test_REQ_d00085_broken_refs_warning_severity(self) -> None:
        """Broken references produce a warning-severity failure."""
        from elspais.graph.mutations import BrokenReference

        graph = build_graph(
            make_requirement("REQ-p00001", title="Parent", level="PRD"),
        )
        # Manually inject broken references
        graph._broken_references = [
            BrokenReference(
                source_id="REQ-d00001",
                target_id="REQ-p99999",
                edge_kind="implements",
            ),
            BrokenReference(
                source_id="REQ-d00002",
                target_id="REQ-p88888",
                edge_kind="refines",
            ),
        ]

        check = check_broken_references(_wrap(graph))
        assert not check.passed
        assert check.severity == "error"  # REQ-d00204-E: within-repo broken refs are errors
        assert check.name == "spec.broken_references"
        assert len(check.findings) == 2
        assert check.details.get("count") == 2

    def test_REQ_d00085_broken_ref_findings_have_source_id(self) -> None:
        """Each broken reference finding includes the source node_id."""
        from elspais.graph.mutations import BrokenReference

        graph = TraceGraph()
        graph._broken_references = [
            BrokenReference(
                source_id="REQ-d00001",
                target_id="REQ-p99999",
                edge_kind="verifies",
            ),
        ]

        check = check_broken_references(_wrap(graph))
        assert not check.passed
        finding = check.findings[0]
        assert isinstance(finding, HealthFinding)
        assert finding.node_id == "REQ-d00001"
        assert "REQ-p99999" in finding.message

    def test_REQ_d00085_allow_unresolved_cross_repo_suppresses_foreign_namespace(self) -> None:
        """Foreign-namespace refs are suppressed when allow_unresolved_cross_repo=True."""
        from elspais.graph.mutations import BrokenReference

        graph = TraceGraph()
        # Foreign namespace (HHT-*) — cross-repo; config gives IdResolver the local namespace
        graph._broken_references = [
            BrokenReference(source_id="REQ-d00001", target_id="HHT-p00001", edge_kind="implements"),
        ]
        config = ConfigLoader.from_dict({"validation": {"allow_unresolved_cross_repo": True}})

        # Pass config to _wrap so FederatedGraph annotates presumed_foreign during init
        fed = _wrap(graph, config)
        check = check_broken_references(fed, config)
        assert check.passed
        assert "suppressed" in check.message

    def test_REQ_d00085_allow_unresolved_cross_repo_keeps_local_refs(self) -> None:
        """Same-namespace broken refs are still flagged with allow_unresolved_cross_repo=True."""
        from elspais.graph.mutations import BrokenReference

        graph = TraceGraph()
        graph._broken_references = [
            BrokenReference(source_id="REQ-d00001", target_id="REQ-p99999", edge_kind="implements"),
        ]
        config = ConfigLoader.from_dict({"validation": {"allow_unresolved_cross_repo": True}})

        check = check_broken_references(_wrap(graph, config), config)
        assert not check.passed

    def test_REQ_d00085_allow_unresolved_cross_repo_default_false(self) -> None:
        """Without the config flag, foreign-namespace broken refs are still reported."""
        from elspais.graph.mutations import BrokenReference

        graph = TraceGraph()
        graph._broken_references = [
            BrokenReference(source_id="REQ-d00001", target_id="HHT-p00001", edge_kind="implements"),
        ]
        config = ConfigLoader.from_dict({})

        check = check_broken_references(_wrap(graph, config))
        assert not check.passed


# =============================================================================
# Config backward compatibility: allow_orphans -> allow_structural_orphans
# =============================================================================


class TestConfigBackwardCompat:
    """Test that legacy allow_orphans config key is respected."""

    def test_REQ_d00085_allow_orphans_fallback_in_run_spec_checks(self, tmp_path: Path) -> None:
        """run_spec_checks() falls back to allow_orphans when allow_structural_orphans is absent."""
        config_path = tmp_path / ".elspais.toml"
        config_path.write_text(
            """[project]
name = "test-compat"

[requirements]
spec_dirs = ["spec"]

[requirements.id_pattern]
prefix = "REQ"
separator = "-"
pattern = "REQ-[a-z]\\\\d{5}"

[rules.hierarchy]
allow_orphans = true
"""
        )
        raw = get_config(config_path)
        config = ConfigLoader.from_dict(raw)

        # Build a graph with an orphan
        graph = build_graph(
            make_requirement("REQ-p00001", title="Parent", level="PRD"),
        )
        orphan = GraphNode(id="REQ-o99999", kind=NodeKind.REQUIREMENT, label="Orphan")
        graph._index["REQ-o99999"] = orphan

        checks = run_spec_checks(_wrap(graph, config), config)
        structural_check = next(c for c in checks if c.name == "spec.structural_orphans")
        # The legacy allow_orphans=true should cause the structural orphan check to pass
        assert (
            structural_check.passed
        ), "allow_orphans=true should skip structural orphan check via fallback"

    def test_REQ_d00085_allow_structural_orphans_takes_precedence(self, tmp_path: Path) -> None:
        """allow_structural_orphans takes precedence over allow_orphans."""
        config_path = tmp_path / ".elspais.toml"
        config_path.write_text(
            """[project]
name = "test-precedence"

[requirements]
spec_dirs = ["spec"]

[requirements.id_pattern]
prefix = "REQ"
separator = "-"
pattern = "REQ-[a-z]\\\\d{5}"

[rules.hierarchy]
allow_orphans = true
allow_structural_orphans = false
"""
        )
        raw = get_config(config_path)
        config = ConfigLoader.from_dict(raw)

        graph = build_graph(
            make_requirement("REQ-p00001", title="Parent", level="PRD"),
        )
        orphan = GraphNode(id="REQ-o99999", kind=NodeKind.REQUIREMENT, label="Orphan")
        graph._index["REQ-o99999"] = orphan

        checks = run_spec_checks(_wrap(graph, config), config)
        structural_check = next(c for c in checks if c.name == "spec.structural_orphans")
        # allow_structural_orphans=false should override allow_orphans=true
        assert (
            not structural_check.passed
        ), "allow_structural_orphans=false should override allow_orphans=true"
