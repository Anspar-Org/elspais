# Verifies: REQ-d00085
"""Tests for check_spec_no_assertions health check.

Verifies that requirements with no assertions are flagged as not testable,
that the check passes when all requirements have assertions, and that
severity is configurable via [rules.format].no_assertions_severity.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from elspais.commands.health import HealthReport, check_spec_no_assertions
from elspais.config import _merge_configs, config_defaults
from elspais.graph.builder import TraceGraph
from elspais.graph.federated import FederatedGraph

from ..core.graph_test_helpers import (
    build_graph,
    make_requirement,
)


def _wrap(graph: TraceGraph, config: dict | None = None) -> FederatedGraph:
    """Wrap a bare TraceGraph in a federation-of-one.

    Injects a test-default ``[project].name`` when the caller doesn't
    supply one — ``from_single`` requires it.
    """
    if config is None:
        config = {"project": {"name": "test", "namespace": "REQ"}}
    elif not (config.get("project") or {}).get("name"):
        config = dict(config)
        config["project"] = {**(config.get("project") or {}), "name": "test"}
    return FederatedGraph.from_single(graph, config, graph.repo_root or Path("/test/repo"))


class TestCheckSpecNoAssertions:
    """Tests for check_spec_no_assertions()."""

    # Verifies: REQ-d00204
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

    # Verifies: REQ-d00204
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

    # Verifies: REQ-d00204
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


def _graph_with(has_finding: bool) -> TraceGraph:
    """A one-requirement graph that either lacks or carries an assertion."""
    assertions = [] if has_finding else [{"label": "A", "text": "Shall do something"}]
    return build_graph(
        make_requirement("REQ-p00001", title="Subject", level="PRD", assertions=assertions),
    )


def _config_with(severity: str) -> dict:
    return _merge_configs(
        config_defaults(),
        {"rules": {"format": {"no_assertions_severity": severity}}},
    )


# Verifies: REQ-p00002-A
class TestNoAssertionsSeverityIsConfiguredInBothStates:
    """The severity `spec.no_assertions` reports is the configured one
    whether or not it found anything.

    Validates REQ-p00002-A: the format rules a project configures — of
    which `[rules.format].no_assertions_severity` is one — govern how the
    tool reports, so the reported severity is a property of the check and
    of the configuration, never of the findings this run produced. A check
    that carries its configured severity only when it has findings claims
    a different policy on a clean estate than on a dirty one, and moves
    between report headings accordingly.

    No assertion governs this setting by name; REQ-p00002-A is the
    obligation it serves.
    """

    # Verifies: REQ-p00002-A
    @pytest.mark.parametrize("configured", ["info", "warning", "error"])
    @pytest.mark.parametrize("has_finding", [True, False])
    def test_REQ_p00002_A_severity_is_the_configured_one_in_both_states(
        self, configured: str, has_finding: bool
    ) -> None:
        """Six combinations: three severities across found and not-found."""
        config = _config_with(configured)
        check = check_spec_no_assertions(_wrap(_graph_with(has_finding), config), config)

        report = HealthReport()
        report.add(check)

        assert bool(check.findings) is has_finding
        assert check.passed is not has_finding
        assert check.severity == configured
        # The serialized report is what every downstream consumer reads.
        assert report.to_dict()["checks"][0]["severity"] == configured

    # Verifies: REQ-p00002-A
    @pytest.mark.parametrize("has_finding", [True, False])
    def test_REQ_p00002_A_info_severity_never_lands_in_passed(self, has_finding: bool) -> None:
        """An informational check is counted as skipped either way.

        ``HealthReport`` reads severity, not findings, to separate
        *skipped* from *passed*: every ``info`` check is skipped and no
        ``info`` check is passed. Losing the configured severity on the
        no-findings return put the same check under *passed* on a clean
        run and under *skipped* on a dirty one.
        """
        config = _config_with("info")
        report = HealthReport()
        report.add(check_spec_no_assertions(_wrap(_graph_with(has_finding), config), config))

        assert report.skipped == 1
        assert report.passed == 0
        assert report.to_dict()["checks"][0]["severity"] == "info"

    # Verifies: REQ-p00002-A
    @pytest.mark.parametrize(
        "configured,has_finding,bucket",
        [
            ("warning", False, "passed"),
            ("warning", True, "warnings"),
            ("error", False, "passed"),
            ("error", True, "failed"),
        ],
    )
    def test_REQ_p00002_A_failing_severities_bucket_by_findings(
        self, configured: str, has_finding: bool, bucket: str
    ) -> None:
        """A warning- or error-configured check counts as passed when
        clean and against its own severity when not — and is never
        counted as skipped, which is reserved for informational."""
        config = _config_with(configured)
        report = HealthReport()
        report.add(check_spec_no_assertions(_wrap(_graph_with(has_finding), config), config))

        counts = {"passed": report.passed, "warnings": report.warnings, "failed": report.failed}
        assert counts[bucket] == 1
        assert sum(counts.values()) == 1
        assert report.skipped == 0
