"""Health checks over a federation: stable findings and keyword-blind classes.

Validates REQ-d00204-F+K: per-member checks judge a member's nodes by its
configuration, resolve references across the whole federation, and report
the same findings however often they run over an unchanged graph.

Validates REQ-d00272-A+C+S, REQ-d00252-E: an unresolved cross-repository
reference is classed by the stage reading reached -- an unknown requirement
or *Assertion* where a member's grammar claims the target, an unknown
namespace where none does -- whichever keyword cited it.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from elspais.commands.health import run_spec_checks
from elspais.config import get_config
from elspais.graph.factory import _build_repository, build_graph
from elspais.graph.reference_faults import FaultClass
from elspais.graph.relations import EdgeKind

FIX = Path(__file__).parents[1] / "fixtures" / "e2e-integrates"

# A library requirement holding a live and a retired *Assertion*.
_LIB_EXTRA = """
# LIB-d00008: Retiring

**Level**: dev | **Status**: Active | **Implements**: -

## Assertions

A. Old events SHALL be kept.

B. <RETIRED> superseded.

*End* *Retiring* | **Hash**: 00000000
"""


def _req(req_id: str, title: str, keyword: str | None = None, target: str | None = None) -> str:
    """One APP requirement, citing ``target`` under ``keyword`` when given."""
    cites = f"\n**{keyword}**: {target}" if keyword else ""
    return (
        f"\n# {req_id}: {title}\n\n"
        f"**Level**: dev | **Status**: Active | **Implements**: -{cites}\n\n"
        f"## Assertions\n\nA. It SHALL hold.\n\n"
        f"*End* *{title}* | **Hash**: 00000000\n"
    )


def _project(tmp_path: Path, app_spec: str = "", app_toml: str = "") -> Path:
    """Copy the app + library fixture, add specs and config; return the app root."""
    dest = tmp_path / "proj"
    shutil.copytree(FIX, dest)
    app, library = dest / "app", dest / "library"
    lib_spec = library / "spec" / "dev-library.md"
    lib_spec.write_text(lib_spec.read_text() + _LIB_EXTRA)
    if app_spec:
        (app / "spec" / "cases.md").write_text(app_spec)
    if app_toml:
        toml = app / ".elspais.toml"
        toml.write_text(toml.read_text() + app_toml)
    for repo in (library, app):
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    return app


def _build(app: Path):
    config = get_config(None, app)
    return build_graph(config=config, repo_root=app, scan_code=False, scan_tests=False), config


def _faults_from(fed, source_id: str) -> list:
    return [br for br in fed.unresolved_references() if br.source_id == source_id]


def _check(checks, name: str):
    return next(c for c in checks if c.name == name)


# ---------------------------------------------------------------------------
# Repeated runs report the same findings
# ---------------------------------------------------------------------------


class TestRepeatedChecksAreStable:
    """Validates REQ-d00204-K: the checks report the same findings every run."""

    # Verifies: REQ-d00204-K, REQ-d00200-J
    def test_REQ_d00204_K_three_runs_report_identical_findings(self, tmp_path):
        """Findings, the federation's faults and each member's own faults
        are unchanged across runs; the resolved Integrates never surfaces."""
        app = _project(
            tmp_path,
            _req("APP-d00002", "Integrates missing", "Integrates", "LIB-d00099")
            + _req("APP-d00003", "Refines missing", "Refines", "LIB-d00099"),
        )
        fed, config = _build(app)

        members_before = {
            e.namespace: list(e.graph._unresolved_references) for e in fed.iter_repos()
        }
        runs = []
        for _ in range(3):
            checks = run_spec_checks(fed, config)
            runs.append(
                (
                    list(fed.unresolved_references()),
                    sorted((c.name, f.message) for c in checks for f in c.findings),
                )
            )
            # The fixture's own APP-d00001 integrates LIB-d00007, which resolves.
            assert not [
                br
                for br in fed.unresolved_references()
                if br.target_id == "LIB-d00007" or br.fault_class is FaultClass.UNKNOWN_NAMESPACE
            ]

        assert runs[0] == runs[1] == runs[2]
        # Sanity: the run has something to be stable about.
        reported = [msg for name, msg in runs[0][1] if name == "references.unknown_requirement"]
        assert len(reported) == 2
        assert all("LIB-d00099" in msg for msg in reported)

        members_after = {
            e.namespace: list(e.graph._unresolved_references) for e in fed.iter_repos()
        }
        assert members_after == members_before


class TestPerMemberChecksResolveAcrossTheFederation:
    """Validates REQ-d00204-F: a member's references resolve where their target lives."""

    # Verifies: REQ-d00204-F
    def test_REQ_d00204_F_resolved_cross_repo_targets_report_nothing(self, tmp_path):
        """A cross-repo Refines and spec Implements that resolve leave no
        finding naming their target, in any check, after a per-member pass."""
        app = _project(
            tmp_path,
            _req("APP-d00004", "Refines resolved", "Refines", "LIB-d00007")
            + _req("APP-d00005", "Implements resolved", "Implements", "LIB-d00007-A"),
        )
        fed, config = _build(app)

        refiner = fed.find_by_id("APP-d00004")
        assert any(
            e.kind is EdgeKind.REFINES and e.source.id == "LIB-d00007"
            for e in refiner.iter_incoming_edges()
        )

        checks = run_spec_checks(fed, config)

        assert not _faults_from(fed, "APP-d00004")
        assert not _faults_from(fed, "APP-d00005")
        naming = [
            (c.name, f.message)
            for c in checks
            for f in c.findings
            if "LIB-d00007" in f.message or "LIB-d00007" in " ".join(f.related or [])
        ]
        assert naming == []


# ---------------------------------------------------------------------------
# The class an item reaches does not depend on its keyword
# ---------------------------------------------------------------------------

_KEYWORDS = ["Implements", "Refines", "Satisfies", "Integrates"]


def _class_for(tmp_path: Path, keyword: str, target: str):
    app = _project(tmp_path, _req("APP-d00100", "Case", keyword, target))
    fed, _config = _build(app)
    faults = [br for br in _faults_from(fed, "APP-d00100") if br.target_id == target]
    assert len(faults) == 1, faults
    return faults[0]


class TestCrossRepoFaultClass:
    """Validates REQ-d00272-A+C+S, REQ-d00252-E."""

    @pytest.mark.parametrize("keyword", _KEYWORDS)
    # Verifies: REQ-d00272-A+S, REQ-d00252-E
    def test_REQ_d00272_S_claimed_but_missing_is_unknown_requirement(self, tmp_path, keyword):
        """LIB's grammar claims LIB-d00099, but LIB holds no such requirement."""
        fault = _class_for(tmp_path, keyword, "LIB-d00099")
        assert fault.fault_class is FaultClass.UNKNOWN_REQUIREMENT
        assert fault.presumed_foreign is False
        assert "LIB" in fault.diagnostic

    @pytest.mark.parametrize("keyword", ["Implements", "Refines"])
    @pytest.mark.parametrize(
        "target", ["LIB-d00008-Z", "LIB-d00008-B"], ids=["label-missing", "label-retired"]
    )
    # Verifies: REQ-d00272-A+S
    def test_REQ_d00272_S_existing_requirement_missing_label_is_unknown_assertion(
        self, tmp_path, keyword, target
    ):
        """LIB-d00008 exists; label Z was never written and label B is retired."""
        fault = _class_for(tmp_path, keyword, target)
        assert fault.fault_class is FaultClass.UNKNOWN_ASSERTION

    @pytest.mark.parametrize("keyword", _KEYWORDS)
    # Verifies: REQ-d00272-C+S, REQ-d00252-E
    def test_REQ_d00272_C_unlinked_namespace_is_unknown_namespace(self, tmp_path, keyword):
        """No member declares the EVS namespace."""
        fault = _class_for(tmp_path, keyword, "EVS-d00001")
        assert fault.fault_class is FaultClass.UNKNOWN_NAMESPACE

    @pytest.mark.parametrize("keyword", ["Implements", "Refines"])
    # Verifies: REQ-d00272-A+C
    def test_REQ_d00272_A_malformed_same_namespace_reference_keeps_its_class(
        self, tmp_path, keyword
    ):
        """An APP reference APP's own reader refused is not re-classed by the
        federation: it ends with the class the member's build gave it."""
        target = "APP-d00001xyz"
        app = _project(tmp_path, _req("APP-d00100", "Case", keyword, target))
        config = get_config(None, app)
        bare, _ = _build_repository(config, app, scan_code=False, scan_tests=False)
        bare_classes = [
            br.fault_class
            for br in bare._unresolved_references
            if br.source_id == "APP-d00100" and br.target_id == target
        ]
        assert len(bare_classes) == 1
        assert bare_classes[0] not in (
            FaultClass.UNKNOWN_NAMESPACE,
            FaultClass.UNKNOWN_REQUIREMENT,
            FaultClass.UNKNOWN_ASSERTION,
        )

        fault = _class_for(tmp_path / "fed", keyword, target)
        assert fault.fault_class is bare_classes[0]

    # Verifies: REQ-d00272-A
    def test_REQ_d00272_A_resolved_cross_repo_refines_produces_no_fault(self, tmp_path):
        app = _project(tmp_path, _req("APP-d00100", "Case", "Refines", "LIB-d00007-A"))
        fed, _config = _build(app)
        assert _faults_from(fed, "APP-d00100") == []


# ---------------------------------------------------------------------------
# Severity is the project's choice
# ---------------------------------------------------------------------------


class TestUnknownRequirementSeverity:
    """Validates REQ-d00269-F, REQ-d00252-E: each class takes its own severity."""

    @pytest.mark.parametrize(
        "setting, passed, severity",
        [(None, False, "error"), ("warning", False, "warning")],
        ids=["default", "warning"],
    )
    # Verifies: REQ-d00269-F, REQ-d00252-E
    def test_REQ_d00269_F_unknown_requirement_lists_the_finding(
        self, tmp_path, setting, passed, severity
    ):
        toml = f'\n[rules.references]\nunknown_requirement = "{setting}"\n' if setting else ""
        app = _project(tmp_path, _req("APP-d00100", "Case", "Refines", "LIB-d00099"), toml)
        fed, config = _build(app)

        check = _check(run_spec_checks(fed, config), "references.unknown_requirement")
        assert check.passed is passed
        assert check.severity == severity
        assert any("LIB-d00099" in f.message for f in check.findings)

    # Verifies: REQ-d00269-F, REQ-d00285-G
    def test_REQ_d00285_G_unknown_requirement_off_is_a_skipped_check(self, tmp_path):
        toml = '\n[rules.references]\nunknown_requirement = "off"\n'
        app = _project(tmp_path, _req("APP-d00100", "Case", "Refines", "LIB-d00099"), toml)
        fed, config = _build(app)

        check = _check(run_spec_checks(fed, config), "references.unknown_requirement")
        assert check.passed is True
        assert check.severity == "info"
        assert check.findings == []
        assert check.details.get("skipped") is True


class TestNamespaceSharingAPrefix:
    """Validates REQ-d00272-A where one namespace extends another."""

    # Verifies: REQ-d00272-A
    def test_REQ_d00272_A_resolved_reference_into_a_longer_namespace(self, tmp_path):
        """Control: REQ-ALP-d00001 resolves from a repository whose own
        namespace is the prefix REQ."""
        from tests.federation_repos import make_repo

        make_repo(tmp_path, "alpha", namespace="REQ-ALP")
        core = make_repo(
            tmp_path,
            "core",
            namespace="REQ",
            associates={"alpha": "../alpha"},
            associate_namespaces={"alpha": "REQ-ALP"},
        )
        (core / "spec" / "reqs.md").write_text(_CORE_REFINES.format(target="REQ-ALP-d00001"))
        fed, _config = _build(core)
        assert _faults_from(fed, "REQ-d00001") == []

    # Verifies: REQ-d00272-A+S
    def test_REQ_d00272_A_missing_id_in_a_longer_namespace_is_unknown_requirement(self, tmp_path):
        from tests.federation_repos import make_repo

        make_repo(tmp_path, "alpha", namespace="REQ-ALP")
        core = make_repo(
            tmp_path,
            "core",
            namespace="REQ",
            associates={"alpha": "../alpha"},
            associate_namespaces={"alpha": "REQ-ALP"},
        )
        (core / "spec" / "reqs.md").write_text(_CORE_REFINES.format(target="REQ-ALP-d00099"))
        fed, _config = _build(core)
        faults = [br for br in _faults_from(fed, "REQ-d00001") if br.target_id == "REQ-ALP-d00099"]
        assert len(faults) == 1
        assert faults[0].fault_class is FaultClass.UNKNOWN_REQUIREMENT


_CORE_REFINES = """# REQ-d00001: Core refines alpha

**Level**: dev | **Status**: Active | **Implements**: -
**Refines**: {target}

## Assertions

A. It SHALL hold.

*End* *Core refines alpha* | **Hash**: 00000000
"""
