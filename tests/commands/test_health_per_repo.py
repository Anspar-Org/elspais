# Verifies: REQ-d00204-A, REQ-d00204-B, REQ-d00204-C, REQ-d00204-D
# Verifies: REQ-d00204-E, REQ-d00204-F
# Verifies: REQ-d00275-A, REQ-d00275-D
# Verifies: REQ-d00285-E
"""Tests for per-repo health check delegation in federated graphs.

Validates REQ-d00204: Config-sensitive health checks run per-repo with
each repo's own ConfigLoader, while non-config-sensitive checks run once
on the full FederatedGraph.
"""

from __future__ import annotations

from pathlib import Path

from elspais.commands.health import (
    HealthFinding,
    check_governed_rule_divergence,
    check_reference_class,
    run_spec_checks,
)
from elspais.config import _merge_configs, config_defaults
from elspais.graph.builder import TraceGraph
from elspais.graph.federated import FederatedGraph, RepoEntry
from elspais.graph.reference_faults import FaultClass
from tests.core.graph_test_helpers import build_graph, make_requirement

# === Helpers ===


def _make_config(hierarchy_rules: dict | None = None, **overrides) -> dict:
    """Create a config dict with specific settings.

    Args:
        hierarchy_rules: Dict mapping child level -> list of allowed parent levels.
            In v3, these are stored as levels.<name>.implements.
        **overrides: Additional top-level config keys to merge.
    """
    data: dict = {}
    if hierarchy_rules is not None:
        # v3: implements rules live in levels.<name>.implements
        defaults = config_defaults()
        levels = dict(defaults.get("levels", {}))
        for level_name, allowed_parents in hierarchy_rules.items():
            if level_name in levels:
                levels[level_name] = {**levels[level_name], "implements": allowed_parents}
            else:
                # Create a minimal level entry
                levels[level_name] = {
                    "rank": len(levels) + 1,
                    "letter": level_name[0],
                    "implements": allowed_parents,
                }
        data["levels"] = levels
    for key, value in overrides.items():
        parts = key.split(".")
        d = data
        for part in parts[:-1]:
            d = d.setdefault(part, {})
        d[parts[-1]] = value
    return _merge_configs(config_defaults(), data)


def _with_namespace(config: dict, namespace: str) -> dict:
    """The same config, declaring the namespace that identifies its member.

    A member is identified by the namespace it declares and by nothing else
    (REQ-d00202-G), so two members of one federation declare two namespaces.
    """
    return {**config, "project": {**config.get("project", {}), "namespace": namespace}}


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
        config=_with_namespace(alpha_config, "ALPHA"),
        repo_root=Path("/repo/alpha"),
    )
    beta_entry = RepoEntry(
        name="beta",
        graph=beta_graph,
        config=_with_namespace(beta_config, "BETA"),
        repo_root=Path("/repo/beta"),
    )
    return FederatedGraph([alpha_entry, beta_entry])


# === Tests ===


class TestHealthFindingRepoField:
    """Tests for HealthFinding repo field support.

    Validates REQ-d00204-D: HealthFinding supports optional repo field.
    """

    # Verifies: REQ-d00204-D
    def test_REQ_d00204_D_health_finding_has_repo_field(self) -> None:
        """HealthFinding dataclass has a `repo` field that defaults to None."""
        finding = HealthFinding(message="test finding")
        # The `repo` field should exist and default to None
        assert hasattr(finding, "repo"), (
            "HealthFinding must have a 'repo' field for per-repo attribution"
        )
        assert finding.repo is None

    # Verifies: REQ-d00204-D
    def test_REQ_d00204_D_health_finding_repo_field_settable(self) -> None:
        """HealthFinding repo field can be set to a repo name."""
        finding = HealthFinding(message="test finding", repo="alpha")
        assert finding.repo == "alpha"

    # Verifies: REQ-d00204-D
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

    # Verifies: REQ-d00204-A
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

    # Verifies: REQ-d00204-A
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

    # Verifies: REQ-d00204-B
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

    # Verifies: REQ-d00204-C
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


def _check_unknown_requirement(graph, config=None):
    return check_reference_class(
        graph,
        config,
        FaultClass.UNKNOWN_REQUIREMENT,
        "references.unknown_requirement",
        "claimed, but no such requirement exists",
    )


class TestReferenceFaultSeverity:
    """Tests for reference-fault severity in federation.

    The severity of a reference fault is fixed per class by configuration
    and decided by one authority (REQ-d00285-E). A class answers "how far
    did reading get", so nothing about the federation's own state moves it.
    """

    # Verifies: REQ-d00285-E
    def test_REQ_d00285_E_broken_refs_within_repo_is_error(self) -> None:
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

        check = _check_unknown_requirement(fed, alpha_config)

        assert not check.passed, "Within-repo broken reference should fail the check"
        assert check.severity == "error", (
            f"references.unknown_requirement should be severity='error' by default, "
            f"got '{check.severity}'."
        )


class TestUnreadableDeclarationIsReported:
    """Validates REQ-d00204-E.

    A declaration whose repository cannot be read is a fault of the
    declaration, not of the directory that is not there. What the report
    has to carry is therefore which declaration reached nothing, and the
    chain of declarations that arrived at it -- a reader working in a
    repository three links up the chain has no other way to find the
    configuration to fix.
    """

    # Verifies: REQ-d00204-E
    def test_REQ_d00204_E_unreadable_declaration_is_reported_citing_the_chain(
        self, tmp_path
    ) -> None:
        """The report names the declaration, the chain reaching it, and why."""
        from elspais.commands.health import check_associate_paths
        from elspais.config import get_config
        from tests.federation_repos import make_repo

        hub = make_repo(tmp_path, "hub", associates={"ghost": "../ghost"})

        check = check_associate_paths(get_config(None, hub), hub)

        assert check.passed is False, "a declaration reaching nothing is not a pass"
        messages = [f.message for f in check.findings]
        assert len(messages) == 1, messages
        reported = messages[0]
        assert "ghost" in reported, reported
        assert "hub -> ghost" in reported, (
            f"the report must cite the declaration chain that reached it: {reported}"
        )
        assert str((tmp_path / "ghost").resolve()) in reported, (
            f"the report must name the path that could not be read: {reported}"
        )

    # Verifies: REQ-d00204-E
    def test_REQ_d00204_E_chain_cites_the_repository_that_declared_it(self, tmp_path) -> None:
        """A declaration made by an associate is cited through that associate.

        Nothing in the invoking repository's own configuration names the
        missing repository, so the chain is the only thing that says where
        to go and fix it.
        """
        from elspais.commands.health import check_associate_paths
        from elspais.config import get_config
        from tests.federation_repos import make_repo

        make_repo(tmp_path, "mid", associates={"ghost": "../ghost"})
        root = make_repo(tmp_path, "root", associates={"mid": "../mid"})

        check = check_associate_paths(get_config(None, root), root)

        assert check.passed is False
        reported = [f.message for f in check.findings if "ghost" in f.message]
        assert len(reported) == 1, [f.message for f in check.findings]
        assert "root -> mid -> ghost" in reported[0], reported[0]


class TestRunSpecChecksIteratesRepos:
    """Tests for run_spec_checks per-repo iteration.

    Validates REQ-d00204-F: run_spec_checks iterates iter_repos()
    using FederatedGraph.from_single() per repo.
    """

    # Verifies: REQ-d00204-F
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


def _governed_member(name: str, rules: dict) -> dict:
    """A member config exactly as written -- no schema defaults filled in.

    Real member configs reach ``RepoEntry`` through the config loader, but the
    disclosure compares the settings a repository *declared*, so these tests
    hand it the declared form directly.
    """
    return {
        "project": {"name": name, "namespace": name.upper()},
        "rules": rules,
    }


def _governed_federation(*configs: dict) -> FederatedGraph:
    """A federation of one empty TraceGraph per supplied member config."""
    return FederatedGraph(
        [
            RepoEntry(
                name=cfg["project"]["name"],
                graph=TraceGraph(),
                config=cfg,
                repo_root=Path("/repo") / cfg["project"]["name"],
            )
            for cfg in configs
        ]
    )


class TestGovernedRuleDivergenceDisclosure:
    """Tests for disclosure of governed settings a member configured otherwise.

    Validates REQ-d00275-D: where a member's configuration would have decided
    a governed setting differently from the invoking repository's, the tool
    discloses the difference -- naming the setting, both values and the member
    -- without failing the run. REQ-d00275-A scopes what "governed" covers.
    """

    # Verifies: REQ-d00275-D
    def test_REQ_d00275_D_divergent_severity_names_setting_values_and_member(self) -> None:
        """The disclosure carries all three facts D requires."""
        host = _governed_member("host", {"references": {"retired": "warning"}})
        lib = _governed_member("lib", {"references": {"retired": "error"}})

        check = check_governed_rule_divergence(_governed_federation(host, lib), host)

        assert check.name == "config.governed_rules"
        assert len(check.findings) == 1, [f.message for f in check.findings]
        finding = check.findings[0]
        assert finding.repo == "lib", "the disclosure must attribute the member"
        assert "rules.references.retired" in finding.message, "must name the setting"
        assert "error" in finding.message, "must carry the member's value"
        assert "warning" in finding.message, "must carry the governing value"
        assert "lib" in finding.message

    # Verifies: REQ-d00275-D
    def test_REQ_d00275_D_disclosure_never_fails_the_run(self) -> None:
        """A difference is disclosed, never judged: passed stays True, severity info."""
        host = _governed_member("host", {"coverage": {"uncredited_evidence": "error"}})
        lib = _governed_member("lib", {"coverage": {"uncredited_evidence": "info"}})

        check = check_governed_rule_divergence(_governed_federation(host, lib), host)

        assert check.findings, "this fixture must produce a disclosure to be meaningful"
        assert check.passed is True, "the disclosure must not fail the run"
        assert check.severity == "info"

    # Verifies: REQ-d00275-D
    def test_REQ_d00275_D_agreeing_member_is_not_disclosed(self) -> None:
        """A member that declared the same governed value has nothing to disclose."""
        host = _governed_member("host", {"references": {"retired": "error"}})
        # Declared explicitly and identically -- the value comparison runs, and
        # finds nothing to report.
        lib = _governed_member("lib", {"references": {"retired": "error"}})

        check = check_governed_rule_divergence(_governed_federation(host, lib), host)

        assert check.findings == []
        assert check.passed is True

    # Verifies: REQ-d00275-A
    def test_REQ_d00275_A_authoring_rules_are_the_members_own(self) -> None:
        """Hierarchy and format rules are not governed, so differing is not disclosed.

        REQ-d00204-A leaves the rules a repository's own content is authored by
        with that repository. Only settings deciding how a finding is judged,
        scored or reported are governed by the invoking repository, so a member
        differing on these has nothing to disclose.
        """
        host = _governed_member(
            "host",
            {
                "hierarchy": {"allow_orphans": False},
                "format": {"require_shall": True, "no_assertions_severity": "error"},
            },
        )
        lib = _governed_member(
            "lib",
            {
                "hierarchy": {"allow_orphans": True},
                "format": {"require_shall": False, "no_assertions_severity": "info"},
            },
        )

        check = check_governed_rule_divergence(_governed_federation(host, lib), host)

        assert check.findings == [], [f.message for f in check.findings]

    # Verifies: REQ-d00275-A
    def test_REQ_d00275_A_status_roles_are_governed_despite_living_under_format(self) -> None:
        """How a status is read when reporting is governed, so it is disclosed."""
        host = _governed_member("host", {"format": {"status_roles": {"active": ["Active"]}}})
        lib = _governed_member("lib", {"format": {"status_roles": {"active": ["Active", "Draft"]}}})

        check = check_governed_rule_divergence(_governed_federation(host, lib), host)

        assert len(check.findings) == 1, [f.message for f in check.findings]
        assert "rules.format.status_roles.active" in check.findings[0].message
        assert check.findings[0].repo == "lib"

    # Verifies: REQ-d00275-D
    def test_REQ_d00275_D_setting_a_member_never_declared_is_not_a_difference(self) -> None:
        """Settings are read as written: an undeclared one was not decided otherwise."""
        host = _governed_member(
            "host",
            {"coverage": {"uncredited_evidence": "warning"}, "references": {"retired": "error"}},
        )
        # Declares one governed setting, agreeing; says nothing about coverage.
        lib = _governed_member("lib", {"references": {"retired": "error"}})

        check = check_governed_rule_divergence(_governed_federation(host, lib), host)

        assert check.findings == [], (
            "an undeclared setting must not be reported as a difference; "
            f"got {[f.message for f in check.findings]}"
        )

    # Verifies: REQ-d00275-D
    def test_REQ_d00275_D_disclosure_runs_as_part_of_the_spec_checks(self) -> None:
        """The disclosure reaches the health report, not just its own entry point."""
        host = _governed_member("host", {"references": {"retired": "warning"}})
        lib = _governed_member("lib", {"references": {"retired": "error"}})

        checks = run_spec_checks(_governed_federation(host, lib), host)

        disclosures = [c for c in checks if c.name == "config.governed_rules"]
        assert len(disclosures) == 1, [c.name for c in checks]
        assert [f.repo for f in disclosures[0].findings] == ["lib"]
        assert disclosures[0].passed is True
