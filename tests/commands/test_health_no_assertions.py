# Verifies: REQ-d00085
"""Tests for check_spec_no_assertions health check.

Verifies that requirements with no assertions are flagged as not testable,
that the check passes when all requirements have assertions, and that
severity is configurable via [rules.format].no_assertions_severity.
"""
from __future__ import annotations

from pathlib import Path

from elspais.commands.health import check_spec_no_assertions
from elspais.config import _merge_configs, config_defaults
from elspais.graph.builder import TraceGraph
from elspais.graph.federated import FederatedGraph

from ..core.graph_test_helpers import (
    build_graph,
    make_requirement,
)


def _wrap(graph: TraceGraph, config: dict | None = None) -> FederatedGraph:
    """Wrap a bare TraceGraph in a federation-of-one."""
    return FederatedGraph.from_single(graph, config, graph.repo_root or Path("/test/repo"))


class TestCheckSpecNoAssertions:
    """Tests for check_spec_no_assertions()."""

    # Implements: REQ-d00204
    def test_check_spec_no_assertions_flags_empty_reqs(self) -> None:
        """A requirement with no assertions produces a warning finding."""
        graph = build_graph(
            make_requirement("REQ-p00001", title="No assertions", level="PRD"),
        )
        fg = _wrap(graph)
        check = check_spec_no_assertions(fg, config_defaults())
        assert not check.passed
        assert check.name == "spec.no_assertions"
        assert check.severity == "warning"
        assert len(check.findings) == 1
        assert "REQ-p00001" in check.findings[0].message
        assert check.findings[0].node_id == "REQ-p00001"

    # Implements: REQ-d00204
    def test_check_spec_no_assertions_passes_when_all_have_assertions(self) -> None:
        """When every requirement has at least one assertion, the check passes."""
        graph = build_graph(
            make_requirement(
                "REQ-p00001",
                title="Has assertions",
                level="PRD",
                assertions=[{"label": "A", "text": "Shall do something"}],
            ),
        )
        fg = _wrap(graph)
        check = check_spec_no_assertions(fg, config_defaults())
        assert check.passed
        assert check.name == "spec.no_assertions"
        assert "All requirements" in check.message

    # Implements: REQ-d00204
    def test_check_spec_no_assertions_severity_configurable(self) -> None:
        """Severity can be set to 'info' via config [rules.format].no_assertions_severity."""
        graph = build_graph(
            make_requirement("REQ-p00001", title="No assertions", level="PRD"),
        )
        fg = _wrap(graph)
        config = _merge_configs(
            config_defaults(),
            {"rules": {"format": {"no_assertions_severity": "info"}}},
        )
        check = check_spec_no_assertions(fg, config)
        assert not check.passed
        assert check.severity == "info"
