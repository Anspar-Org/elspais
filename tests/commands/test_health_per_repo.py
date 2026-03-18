# Verifies: REQ-d00204-A, REQ-d00204-B, REQ-d00204-C, REQ-d00204-D
# Verifies: REQ-d00204-E, REQ-d00204-F
"""Tests for per-repo health check delegation in federated graphs.

Validates REQ-d00204: Config-sensitive health checks run per-repo with
each repo's own ConfigLoader, while non-config-sensitive checks run once
on the full FederatedGraph.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from elspais.commands.health import (
    HealthFinding,
    check_broken_references,
    run_spec_checks,
)
from elspais.config import _merge_configs, config_defaults
from elspais.graph.federated import FederatedGraph, RepoEntry
from tests.core.graph_test_helpers import build_graph, make_requirement

if TYPE_CHECKING:
    from elspais.graph.builder import TraceGraph


# === Helpers ===


def _make_config(hierarchy_rules: dict | None = None, **overrides) -> dict:
    """Create a config dict with specific settings.

    Args:
        hierarchy_rules: Dict mapping child level -> list of allowed parent levels.
        **overrides: Additional top-level config keys to merge.
    """
    data: dict = {}
    if hierarchy_rules is not None:
        data["rules"] = {"hierarchy": hierarchy_rules}
    for key, value in overrides.items():
        # Support dotted keys like "rules.format"
        parts = key.split(".")
        d = data
        for part in parts[:-1]:
            d = d.setdefault(part, {})
        d[parts[-1]] = value
    return _merge_configs(config_defaults(), data)


def _build_two_repo_federation(
    alpha_graph: TraceGraph,
    alpha_config: dict,
    beta_graph: TraceGraph,
    beta_config: dict,
) -> FederatedGraph:
    """Build a 2-repo federation from two (graph, config) pairs."""
    alpha_entry = RepoEntry(
        name="alpha",
        graph=alpha_graph,
        config=alpha_config,
        repo_root=Path("/repo/alpha"),
    )
    beta_entry = RepoEntry(
        name="beta",
        graph=beta_graph,
        config=beta_config,
        repo_root=Path("/repo/beta"),
    )
    return FederatedGraph([alpha_entry, beta_entry])


# === Tests ===


class TestHealthFindingRepoField:
    """Tests for HealthFinding repo field support.

    Validates REQ-d00204-D: HealthFinding supports optional repo field.
    """

    def test_REQ_d00204_D_health_finding_has_repo_field(self) -> None:
        """HealthFinding dataclass has a `repo` field that defaults to None."""
        finding = HealthFinding(message="test finding")
        # The `repo` field should exist and default to None
        assert hasattr(
            finding, "repo"
        ), "HealthFinding must have a 'repo' field for per-repo attribution"
        assert finding.repo is None

    def test_REQ_d00204_D_health_finding_repo_field_settable(self) -> None:
        """HealthFinding repo field can be set to a repo name."""
        finding = HealthFinding(message="test finding", repo="alpha")
        assert finding.repo == "alpha"

    def test_REQ_d00204_D_health_finding_to_dict_includes_repo(self) -> None:
        """HealthFinding.to_dict() includes the repo field."""
        finding = HealthFinding(message="test", repo="beta")
        d = finding.to_dict()
        assert "repo" in d, "to_dict() must include the 'repo' field"
        assert d["repo"] == "beta"


class TestPerRepoHierarchyCheck:
    """Tests for per-repo hierarchy level checking.

    Validates REQ-d00204-A: Config-sensitive checks run per-repo with
    repo's own ConfigLoader.
    """

    def test_REQ_d00204_A_hierarchy_check_uses_per_repo_config(self) -> None:
        """Hierarchy check uses each repo's own config, not a single global config.

        Alpha allows dev -> ops. Beta allows dev -> prd.
        With per-repo checking, both should pass.
        With single-config, one would fail.
        """
        # Alpha: DEV implements OPS (allowed by alpha's rules: dev -> [ops])
        alpha_graph = build_graph(
            make_requirement(
                "REQ-o00001", title="Alpha OPS", level="OPS", source_path="spec/alpha-ops.md"
            ),
            make_requirement(
                "REQ-d00001",
                title="Alpha DEV",
                level="DEV",
                implements=["REQ-o00001"],
                source_path="spec/alpha-dev.md",
            ),
            repo_root=Path("/repo/alpha"),
        )
        alpha_config = _make_config(
            hierarchy_rules={"dev": ["ops"]},
            **{"validation.strict_hierarchy": True},
        )

        # Beta: DEV implements PRD (allowed by beta's rules: dev -> [prd])
        beta_graph = build_graph(
            make_requirement(
                "REQ-p00002", title="Beta PRD", level="PRD", source_path="spec/beta-prd.md"
            ),
            make_requirement(
                "REQ-d00002",
                title="Beta DEV",
                level="DEV",
                implements=["REQ-p00002"],
                source_path="spec/beta-dev.md",
            ),
            repo_root=Path("/repo/beta"),
        )
        beta_config = _make_config(
            hierarchy_rules={"dev": ["prd"]},
            **{"validation.strict_hierarchy": True},
        )

        fed = _build_two_repo_federation(alpha_graph, alpha_config, beta_graph, beta_config)

        # Per-repo checks: each repo checked with its own config should pass
        # This is the NEW behavior we're testing
        checks = run_spec_checks(fed, alpha_config)

        # Find hierarchy check results
        hierarchy_checks = [c for c in checks if c.name == "spec.hierarchy_levels"]
        assert len(hierarchy_checks) >= 1

        # With per-repo delegation, all hierarchy checks should pass
        for check in hierarchy_checks:
            assert check.passed, (
                f"Hierarchy check failed: {check.message}. "
                "Per-repo delegation should use each repo's own config."
            )


class TestPerRepoFormatRules:
    """Tests for per-repo format rule checking.

    Validates REQ-d00204-A: Config-sensitive checks run per-repo.
    """

    def test_REQ_d00204_A_format_rules_uses_per_repo_config(self) -> None:
        """Format rules use each repo's own config.

        Alpha requires assertions. Beta does not.
        Beta has a requirement without assertions -- should pass with beta's config.
        """
        # Alpha: requirement WITH assertions (satisfies alpha's require_assertions=true)
        alpha_graph = build_graph(
            make_requirement(
                "REQ-p00010",
                title="Alpha Req",
                level="PRD",
                assertions=[{"label": "A", "text": "Must do something"}],
                source_path="spec/alpha.md",
            ),
            repo_root=Path("/repo/alpha"),
        )
        alpha_config = _make_config(
            **{"rules.format.require_assertions": True},
        )

        # Beta: requirement WITHOUT assertions (ok since beta has require_assertions=false)
        beta_graph = build_graph(
            make_requirement(
                "REQ-p00020",
                title="Beta Req",
                level="PRD",
                source_path="spec/beta.md",
            ),
            repo_root=Path("/repo/beta"),
        )
        beta_config = _make_config(
            **{"rules.format.require_assertions": False},
        )

        fed = _build_two_repo_federation(alpha_graph, alpha_config, beta_graph, beta_config)

        # With per-repo delegation, format checks should pass for both repos
        checks = run_spec_checks(fed, alpha_config)
        format_checks = [c for c in checks if c.name == "spec.format_rules"]
        assert len(format_checks) >= 1

        for check in format_checks:
            assert check.passed, (
                f"Format check failed: {check.message}. "
                "Per-repo delegation should use each repo's own config."
            )


class TestNonConfigChecksRunOnFullFederation:
    """Tests for non-config-sensitive checks running on full federation.

    Validates REQ-d00204-B: Non-config-sensitive checks run once on full
    FederatedGraph.
    """

    def test_REQ_d00204_B_non_config_checks_run_on_full_federation(self) -> None:
        """Non-config checks (duplicates, hash integrity) aggregate across all repos.

        With per-repo delegation, config-sensitive checks run N times (once per repo)
        but non-config checks must run exactly once on the full federation.
        This test verifies that hierarchy checks run per-repo (2x) while
        non-config checks run once (1x).
        """
        alpha_graph = build_graph(
            make_requirement("REQ-p00001", title="Alpha", level="PRD", source_path="spec/alpha.md"),
            repo_root=Path("/repo/alpha"),
        )
        beta_graph = build_graph(
            make_requirement("REQ-p00002", title="Beta", level="PRD", source_path="spec/beta.md"),
            repo_root=Path("/repo/beta"),
        )

        alpha_config = _make_config(
            hierarchy_rules={"dev": ["prd"]},
            **{"validation.strict_hierarchy": True},
        )
        beta_config = _make_config(
            hierarchy_rules={"dev": ["ops"]},
            **{"validation.strict_hierarchy": True},
        )

        fed = _build_two_repo_federation(alpha_graph, alpha_config, beta_graph, beta_config)

        checks = run_spec_checks(fed, alpha_config)

        # Non-config checks should run exactly once on full federation
        dup_checks = [c for c in checks if c.name == "spec.no_duplicates"]
        assert len(dup_checks) == 1, "Duplicate check should run exactly once on full federation"

        hash_checks = [c for c in checks if c.name == "spec.hash_integrity"]
        assert len(hash_checks) == 1, "Hash integrity should run exactly once on full federation"

        # Config-sensitive checks should run per-repo (one per repo)
        hierarchy_checks = [c for c in checks if c.name == "spec.hierarchy_levels"]
        assert len(hierarchy_checks) == 2, (
            f"Hierarchy check should run once per repo (2x), got {len(hierarchy_checks)}. "
            "Per-repo delegation must produce separate results per repo."
        )


class TestPerRepoFindingsAttribution:
    """Tests for per-repo finding attribution.

    Validates REQ-d00204-C: Per-repo results merged with repo attribution.
    """

    def test_REQ_d00204_C_per_repo_findings_have_repo_attribution(self) -> None:
        """Findings from per-repo checks include the repo name."""
        # Create a federation where alpha has a hierarchy violation
        # (DEV implements PRD, but alpha only allows dev -> ops)
        alpha_graph = build_graph(
            make_requirement(
                "REQ-p00050", title="Alpha PRD", level="PRD", source_path="spec/alpha-prd.md"
            ),
            make_requirement(
                "REQ-d00050",
                title="Alpha DEV",
                level="DEV",
                implements=["REQ-p00050"],
                source_path="spec/alpha-dev.md",
            ),
            repo_root=Path("/repo/alpha"),
        )
        alpha_config = _make_config(
            hierarchy_rules={"dev": ["ops"]},  # dev -> prd NOT allowed
            **{"validation.strict_hierarchy": True},
        )

        beta_graph = build_graph(
            make_requirement(
                "REQ-p00060", title="Beta PRD", level="PRD", source_path="spec/beta.md"
            ),
            repo_root=Path("/repo/beta"),
        )
        beta_config = _make_config()

        fed = _build_two_repo_federation(alpha_graph, alpha_config, beta_graph, beta_config)

        checks = run_spec_checks(fed, alpha_config)

        hierarchy_checks = [c for c in checks if c.name == "spec.hierarchy_levels"]
        # Should have findings from the alpha repo violation
        all_findings = []
        for check in hierarchy_checks:
            all_findings.extend(check.findings)

        # At least one finding should exist for alpha's violation
        assert len(all_findings) > 0, "Expected hierarchy violation findings"

        # Each finding should have a repo attribution
        for finding in all_findings:
            assert finding.repo is not None, (
                f"Finding '{finding.message}' missing repo attribution. "
                "Per-repo findings must be annotated with repo name."
            )


class TestBrokenReferenceSeverity:
    """Tests for broken reference severity in federation.

    Validates REQ-d00204-E: Broken refs within-repo are errors,
    cross-repo with error-state target are warnings.
    """

    def test_REQ_d00204_E_broken_refs_within_repo_is_error(self) -> None:
        """Broken reference within a single repo should be severity=error."""
        # Create a graph with a broken reference (target doesn't exist)
        alpha_graph = build_graph(
            make_requirement(
                "REQ-d00070",
                title="Broken Dev",
                level="DEV",
                implements=["REQ-p99999"],  # target doesn't exist
                source_path="spec/alpha.md",
            ),
            repo_root=Path("/repo/alpha"),
        )
        alpha_config = _make_config()

        beta_graph = build_graph(
            make_requirement("REQ-p00080", title="Beta", level="PRD", source_path="spec/beta.md"),
            repo_root=Path("/repo/beta"),
        )
        beta_config = _make_config()

        fed = _build_two_repo_federation(alpha_graph, alpha_config, beta_graph, beta_config)

        check = check_broken_references(fed)

        # Within-repo broken reference should be an error, not just a warning
        assert not check.passed, "Within-repo broken reference should fail the check"
        assert check.severity == "error", (
            f"Within-repo broken reference should be severity='error', got '{check.severity}'. "
            "The new behavior distinguishes within-repo (error) from cross-repo (warning)."
        )

    def test_REQ_d00204_E_broken_refs_cross_repo_error_state_is_warning(self) -> None:
        """Cross-repo reference to error-state repo should be severity=warning,
        distinct from within-repo broken refs which should be errors.

        The new check_broken_references must distinguish the two cases by
        inspecting the federation's error-state repos.
        """
        # Alpha has TWO broken refs:
        # 1. REQ-p99000 - would be in beta (error-state) -> warning
        # 2. REQ-p99999 - doesn't exist anywhere -> error
        alpha_graph = build_graph(
            make_requirement(
                "REQ-d00090",
                title="Alpha Dev A",
                level="DEV",
                implements=["REQ-p99000"],  # would be in beta
                source_path="spec/alpha-a.md",
            ),
            make_requirement(
                "REQ-d00091",
                title="Alpha Dev B",
                level="DEV",
                implements=["REQ-p99999"],  # doesn't exist anywhere
                source_path="spec/alpha-b.md",
            ),
            repo_root=Path("/repo/alpha"),
        )
        alpha_config = _make_config()

        # Beta is in error state (graph=None)
        alpha_entry = RepoEntry(
            name="alpha",
            graph=alpha_graph,
            config=alpha_config,
            repo_root=Path("/repo/alpha"),
        )
        beta_entry = RepoEntry(
            name="beta",
            graph=None,
            config=None,
            repo_root=Path("/repo/beta"),
            error="Failed to build graph",
        )
        fed = FederatedGraph([alpha_entry, beta_entry])

        check = check_broken_references(fed)

        assert not check.passed, "Broken references should fail the check"

        # The check should produce findings with different severity annotations
        # Within-repo broken refs -> error findings, cross-repo to error-state -> warning findings
        assert len(check.findings) >= 2, f"Expected at least 2 findings, got {len(check.findings)}"

        # Findings should be distinguishable by their severity or repo annotation
        # The new implementation must annotate findings differently
        finding_messages = [f.message for f in check.findings]
        has_repo_attr = any(hasattr(f, "repo") and f.repo is not None for f in check.findings)
        assert has_repo_attr, (
            "Broken reference findings must have 'repo' attribution to distinguish "
            "within-repo (error) from cross-repo-to-error-state (warning). "
            f"Findings: {finding_messages}"
        )


class TestRunSpecChecksIteratesRepos:
    """Tests for run_spec_checks per-repo iteration.

    Validates REQ-d00204-F: run_spec_checks iterates iter_repos()
    using FederatedGraph.from_single() per repo.
    """

    def test_REQ_d00204_F_run_spec_checks_iterates_repos(self) -> None:
        """run_spec_checks produces per-repo results for config-sensitive checks.

        A 2-repo federation with different hierarchy configs should produce
        correct per-repo results, not results from a single global config.
        """
        # Alpha: dev -> ops only
        alpha_graph = build_graph(
            make_requirement(
                "REQ-o00100", title="Alpha OPS", level="OPS", source_path="spec/alpha-ops.md"
            ),
            make_requirement(
                "REQ-d00100",
                title="Alpha DEV",
                level="DEV",
                implements=["REQ-o00100"],
                source_path="spec/alpha-dev.md",
            ),
            repo_root=Path("/repo/alpha"),
        )
        alpha_config = _make_config(
            hierarchy_rules={"dev": ["ops"]},
            **{"validation.strict_hierarchy": True},
        )

        # Beta: dev -> prd only
        beta_graph = build_graph(
            make_requirement(
                "REQ-p00200", title="Beta PRD", level="PRD", source_path="spec/beta-prd.md"
            ),
            make_requirement(
                "REQ-d00200",
                title="Beta DEV",
                level="DEV",
                implements=["REQ-p00200"],
                source_path="spec/beta-dev.md",
            ),
            repo_root=Path("/repo/beta"),
        )
        beta_config = _make_config(
            hierarchy_rules={"dev": ["prd"]},
            **{"validation.strict_hierarchy": True},
        )

        fed = _build_two_repo_federation(alpha_graph, alpha_config, beta_graph, beta_config)

        # The key test: with a single global config (alpha's), beta's
        # dev->prd would be a violation. With per-repo delegation, it should pass.
        checks = run_spec_checks(fed, alpha_config)

        hierarchy_checks = [c for c in checks if c.name == "spec.hierarchy_levels"]

        # All hierarchy checks should pass with per-repo delegation
        failed_hierarchy = [c for c in hierarchy_checks if not c.passed]
        assert len(failed_hierarchy) == 0, (
            f"Expected no hierarchy failures with per-repo delegation, "
            f"but got {len(failed_hierarchy)} failures. "
            f"Messages: {[c.message for c in failed_hierarchy]}. "
            "run_spec_checks must iterate repos and use each repo's own config."
        )
