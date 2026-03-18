# Verifies: REQ-d00203-A, REQ-d00203-B, REQ-d00203-C, REQ-d00203-D, REQ-d00203-E
"""Tests for multi-repo federation building in factory.build_graph().

Validates REQ-d00203-A: build_graph() builds separate TraceGraphs per repo
Validates REQ-d00203-B: Transitive associates are rejected with FederationError
Validates REQ-d00203-C: Missing associate path creates error-state RepoEntry (soft fail)
Validates REQ-d00203-D: strict=True raises on missing associate
Validates REQ-d00203-E: FederatedGraph root repo is the invoking repo, not an associate
"""

from __future__ import annotations

from pathlib import Path

import pytest
import tomlkit

from elspais.graph.factory import build_graph
from elspais.graph.federated import FederationError

# ---------------------------------------------------------------------------
# Helper: write a minimal .elspais.toml
# ---------------------------------------------------------------------------

_BASE_CONFIG = {
    "project": {"namespace": "REQ"},
    "spec": {"directories": ["spec"]},
    "id-patterns": {
        "canonical": "{namespace}-{type.letter}{component}",
        "types": {
            "prd": {"level": 1, "aliases": {"letter": "p"}},
            "ops": {"level": 2, "aliases": {"letter": "o"}},
            "dev": {"level": 3, "aliases": {"letter": "d"}},
        },
        "component": {
            "style": "numeric",
            "digits": 5,
            "leading_zeros": True,
        },
    },
}


def _write_config(repo_dir: Path, extra: dict | None = None) -> Path:
    """Write .elspais.toml into *repo_dir* and return its path."""
    repo_dir.mkdir(parents=True, exist_ok=True)
    cfg = dict(_BASE_CONFIG)
    if extra:
        cfg.update(extra)
    config_path = repo_dir / ".elspais.toml"
    config_path.write_text(tomlkit.dumps(cfg), encoding="utf-8")
    return config_path


def _write_spec_file(
    spec_dir: Path,
    filename: str,
    req_id: str,
    title: str,
    level: str,
    implements: str | None = None,
) -> None:
    """Write a minimal spec file with one requirement."""
    spec_dir.mkdir(parents=True, exist_ok=True)
    meta = f"**Level**: {level} | **Status**: Active"
    if implements:
        meta += f" | **Implements**: {implements}"
    (spec_dir / filename).write_text(
        f"""\
## {req_id}: {title}

{meta}

The system shall do things.

*End* *{title}* | **Hash**: abcd1234
---
""",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def two_repos(tmp_path: Path) -> dict[str, Path]:
    """Create root and associate repo directories with configs and specs.

    Layout::

        tmp_path/
            root/
                .elspais.toml   (declares [associates.assoc])
                spec/
                    dev.md      (DEV req implementing assoc PRD)
            assoc/
                .elspais.toml
                spec/
                    prd.md      (PRD req)
    """
    root_dir = tmp_path / "root"
    assoc_dir = tmp_path / "assoc"

    # --- associate repo ---
    _write_config(assoc_dir)
    _write_spec_file(
        assoc_dir / "spec",
        "prd.md",
        req_id="REQ-p00001",
        title="Product Requirement",
        level="PRD",
    )

    # --- root repo (declares associate) ---
    _write_config(
        root_dir,
        extra={"associates": {"assoc": {"path": "../assoc"}}},
    )
    _write_spec_file(
        root_dir / "spec",
        "dev.md",
        req_id="REQ-d00001",
        title="Dev Requirement",
        level="DEV",
        implements="REQ-p00001",
    )

    return {"root": root_dir, "assoc": assoc_dir}


@pytest.fixture()
def missing_assoc_repo(tmp_path: Path) -> Path:
    """Create a root repo whose associate path does not exist.

    Layout::

        tmp_path/
            root/
                .elspais.toml   (declares [associates.ghost] -> ../ghost)
                spec/
                    dev.md
    """
    root_dir = tmp_path / "root"
    _write_config(
        root_dir,
        extra={"associates": {"ghost": {"path": "../ghost"}}},
    )
    _write_spec_file(
        root_dir / "spec",
        "dev.md",
        req_id="REQ-d00001",
        title="Dev Requirement",
        level="DEV",
    )
    return root_dir


@pytest.fixture()
def transitive_repos(tmp_path: Path) -> dict[str, Path]:
    """Create repos where the associate itself declares associates (forbidden).

    Layout::

        tmp_path/
            root/
                .elspais.toml   (declares [associates.middle])
                spec/dev.md
            middle/
                .elspais.toml   (declares [associates.leaf] -- illegal)
                spec/ops.md
            leaf/
                .elspais.toml
                spec/prd.md
    """
    root_dir = tmp_path / "root"
    middle_dir = tmp_path / "middle"
    leaf_dir = tmp_path / "leaf"

    # leaf (clean)
    _write_config(leaf_dir)
    _write_spec_file(
        leaf_dir / "spec",
        "prd.md",
        req_id="REQ-p00001",
        title="Leaf PRD",
        level="PRD",
    )

    # middle (illegally declares its own associate)
    _write_config(
        middle_dir,
        extra={"associates": {"leaf": {"path": "../leaf"}}},
    )
    _write_spec_file(
        middle_dir / "spec",
        "ops.md",
        req_id="REQ-o00001",
        title="Middle OPS",
        level="OPS",
    )

    # root
    _write_config(
        root_dir,
        extra={"associates": {"middle": {"path": "../middle"}}},
    )
    _write_spec_file(
        root_dir / "spec",
        "dev.md",
        req_id="REQ-d00001",
        title="Root DEV",
        level="DEV",
    )

    return {"root": root_dir, "middle": middle_dir, "leaf": leaf_dir}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFederationBuild:
    """Tests for multi-repo federation building via build_graph().

    Validates REQ-d00203-A: Separate graphs per repo
    Validates REQ-d00203-B: Transitive associates rejected
    Validates REQ-d00203-C: Missing associate soft-fails
    Validates REQ-d00203-D: strict raises on missing associate
    Validates REQ-d00203-E: Root repo identity
    """

    def test_REQ_d00203_A_builds_separate_graphs_per_repo(self, two_repos: dict[str, Path]) -> None:
        """Two repos produce a FederatedGraph with 2 RepoEntries,
        each having a non-None graph."""
        root_dir = two_repos["root"]

        fed = build_graph(
            repo_root=root_dir,
            scan_code=False,
            scan_tests=False,
        )

        entries = list(fed.iter_repos())
        # Expect 2 entries: root + assoc
        assert len(entries) == 2, (
            f"Expected 2 repo entries (root + associate), got {len(entries)}: "
            f"{[e.name for e in entries]}"
        )
        for entry in entries:
            assert entry.graph is not None, (
                f"RepoEntry '{entry.name}' has graph=None — "
                "each repo should have a built TraceGraph"
            )

    def test_REQ_d00203_C_missing_associate_soft_fail(self, missing_assoc_repo: Path) -> None:
        """Root declares associate at non-existent path.
        Default (non-strict) mode: FederatedGraph has an error-state
        RepoEntry with graph=None for the missing associate."""
        fed = build_graph(
            repo_root=missing_assoc_repo,
            scan_code=False,
            scan_tests=False,
        )

        entries = list(fed.iter_repos())
        # Expect 2 entries: root (ok) + ghost (error)
        assert len(entries) == 2, (
            f"Expected 2 repo entries (root + error-state ghost), got {len(entries)}: "
            f"{[e.name for e in entries]}"
        )
        error_entries = [e for e in entries if e.graph is None]
        assert len(error_entries) == 1, (
            "Expected exactly one error-state RepoEntry (graph=None) "
            f"for the missing associate, got {len(error_entries)}"
        )
        assert (
            error_entries[0].error is not None
        ), "Error-state RepoEntry should have a human-readable error message"

    def test_REQ_d00203_D_strict_raises_on_missing_associate(
        self, missing_assoc_repo: Path
    ) -> None:
        """Root declares associate at non-existent path with strict=True.
        Should raise FederationError or ValueError."""
        with pytest.raises((FederationError, ValueError)):
            build_graph(
                repo_root=missing_assoc_repo,
                scan_code=False,
                scan_tests=False,
                strict=True,  # type: ignore[call-arg]
            )

    def test_REQ_d00203_E_root_is_root_repo(self, two_repos: dict[str, Path]) -> None:
        """The FederatedGraph's root repo should be the invoking repo,
        not the associate."""
        root_dir = two_repos["root"]

        fed = build_graph(
            repo_root=root_dir,
            scan_code=False,
            scan_tests=False,
        )

        # The root repo entry should match root_dir
        assert fed.repo_root == root_dir, (
            f"FederatedGraph.repo_root should be the root repo ({root_dir}), "
            f"got {fed.repo_root}"
        )

    def test_REQ_d00203_B_transitive_associates_rejected(
        self, transitive_repos: dict[str, Path]
    ) -> None:
        """Associate declares its own [associates] section.
        build_graph() should raise FederationError."""
        root_dir = transitive_repos["root"]

        with pytest.raises(FederationError):
            build_graph(
                repo_root=root_dir,
                scan_code=False,
                scan_tests=False,
            )


# ---------------------------------------------------------------------------
# Cross-Graph Edge Wiring and ID Conflict Tests
# ---------------------------------------------------------------------------


class TestCrossGraphWiring:
    """Tests for cross-graph edge wiring and ID conflict detection.

    Validates REQ-d00203-A: Cross-graph edges wired from broken references
    """

    def test_cross_graph_edge_wired(self, two_repos: dict[str, Path]) -> None:
        """Root DEV implements associate PRD — edge wires across repos."""
        root_dir = two_repos["root"]

        fed = build_graph(
            repo_root=root_dir,
            scan_code=False,
            scan_tests=False,
        )

        # REQ-d00001 should have REQ-p00001 as parent via IMPLEMENTS
        dev_node = fed.find_by_id("REQ-d00001")
        assert dev_node is not None, "DEV requirement not found"

        from elspais.graph.relations import EdgeKind

        parent_ids = {p.id for p in dev_node.iter_parents(edge_kinds={EdgeKind.IMPLEMENTS})}
        assert "REQ-p00001" in parent_ids, (
            f"Expected REQ-d00001 to implement REQ-p00001, " f"but parents are: {parent_ids}"
        )

    def test_cross_graph_broken_ref_resolved(self, two_repos: dict[str, Path]) -> None:
        """After wiring, the broken reference should be resolved."""
        root_dir = two_repos["root"]

        fed = build_graph(
            repo_root=root_dir,
            scan_code=False,
            scan_tests=False,
        )

        # The reference REQ-d00001 -> REQ-p00001 should not be broken
        broken = fed.broken_references()
        broken_targets = {br.target_id for br in broken}
        assert "REQ-p00001" not in broken_targets, (
            f"REQ-p00001 should not be a broken reference, " f"but found: {broken}"
        )

    def test_id_conflict_raises(self, tmp_path: Path) -> None:
        """Two repos defining the same ID raises FederationError."""
        root_dir = tmp_path / "root"
        assoc_dir = tmp_path / "assoc"

        # Both repos define REQ-p00001
        _write_config(assoc_dir)
        _write_spec_file(
            assoc_dir / "spec",
            "prd.md",
            req_id="REQ-p00001",
            title="Assoc PRD",
            level="PRD",
        )

        _write_config(
            root_dir,
            extra={"associates": {"assoc": {"path": "../assoc"}}},
        )
        _write_spec_file(
            root_dir / "spec",
            "prd.md",
            req_id="REQ-p00001",
            title="Root PRD",
            level="PRD",
        )

        with pytest.raises(FederationError, match="ID conflict"):
            build_graph(
                repo_root=root_dir,
                scan_code=False,
                scan_tests=False,
            )

    def test_unresolvable_ref_stays_broken(self, tmp_path: Path) -> None:
        """Reference to ID not in any repo stays as broken reference."""
        root_dir = tmp_path / "root"
        assoc_dir = tmp_path / "assoc"

        _write_config(assoc_dir)
        _write_spec_file(
            assoc_dir / "spec",
            "prd.md",
            req_id="REQ-p00001",
            title="Assoc PRD",
            level="PRD",
        )

        _write_config(
            root_dir,
            extra={"associates": {"assoc": {"path": "../assoc"}}},
        )
        # Root's DEV implements REQ-p99999 which doesn't exist anywhere
        _write_spec_file(
            root_dir / "spec",
            "dev.md",
            req_id="REQ-d00001",
            title="Root DEV",
            level="DEV",
            implements="REQ-p99999",
        )

        fed = build_graph(
            repo_root=root_dir,
            scan_code=False,
            scan_tests=False,
        )

        broken = fed.broken_references()
        broken_targets = {br.target_id for br in broken}
        assert "REQ-p99999" in broken_targets
