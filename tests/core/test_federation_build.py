# Verifies: REQ-d00203-A, REQ-d00203-B, REQ-d00203-C, REQ-d00203-D, REQ-d00203-E, REQ-d00200-D
"""Tests for multi-repo federation building in factory.build_graph().

Validates REQ-d00203-A: build_graph() builds separate TraceGraphs per repo
Validates REQ-d00203-B: An associate's own declarations join the federation
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
from elspais.graph.GraphNode import REMAINDER_ID_PREFIX, parse_structural_id
from tests.federation_repos import _git, make_repo

# ---------------------------------------------------------------------------
# Helper: write a minimal .elspais.toml
# ---------------------------------------------------------------------------

_BASE_CONFIG = {
    "project": {"name": "test", "namespace": "REQ"},
    "scanning": {"spec": {"directories": ["spec"]}},
    "id-patterns": {
        "canonical": "{namespace}-{level.letter}{component}",
        "component": {
            "style": "numeric",
            "digits": 5,
            "leading_zeros": True,
        },
    },
    "levels": {
        "prd": {"rank": 1, "letter": "p", "implements": ["prd"]},
        "ops": {"rank": 2, "letter": "o", "implements": ["ops", "prd"]},
        "dev": {"rank": 3, "letter": "d", "implements": ["dev", "ops", "prd"]},
    },
}


def _write_config(
    repo_dir: Path,
    extra: dict | None = None,
    namespace: str | None = None,
) -> Path:
    """Write .elspais.toml into *repo_dir* and return its path.

    `namespace` defaults to the directory's own name upper-cased, so two
    repos built for one federation declare different namespaces -- the
    condition on which a federation can say whose identifiers are whose.
    """
    repo_dir.mkdir(parents=True, exist_ok=True)
    cfg = dict(_BASE_CONFIG)
    cfg["project"] = dict(cfg["project"])
    cfg["project"]["namespace"] = namespace or repo_dir.name.upper()
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
        req_id="ASSOC-p00001",
        title="Product Requirement",
        level="PRD",
    )

    # --- root repo (declares associate) ---
    _write_config(
        root_dir,
        extra={"associates": {"assoc": {"path": "../assoc", "namespace": "ASSOC"}}},
    )
    _write_spec_file(
        root_dir / "spec",
        "dev.md",
        req_id="ROOT-d00001",
        title="Dev Requirement",
        level="DEV",
        implements="ASSOC-p00001",
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
        extra={"associates": {"ghost": {"path": "../ghost", "namespace": "GHOST"}}},
    )
    _write_spec_file(
        root_dir / "spec",
        "dev.md",
        req_id="ROOT-d00001",
        title="Dev Requirement",
        level="DEV",
    )
    return root_dir


@pytest.fixture()
def transitive_repos(tmp_path: Path) -> dict[str, Path]:
    """Create a three-deep declaration chain: root -> middle -> leaf.

    Layout::

        tmp_path/
            root/
                .elspais.toml   (declares [associates.middle])
                spec/dev.md
            middle/
                .elspais.toml   (declares [associates.leaf])
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
        req_id="LEAF-p00001",
        title="Leaf PRD",
        level="PRD",
    )

    # middle (declares its own associate)
    _write_config(
        middle_dir,
        extra={"associates": {"leaf": {"path": "../leaf", "namespace": "LEAF"}}},
    )
    _write_spec_file(
        middle_dir / "spec",
        "ops.md",
        req_id="MIDDLE-o00001",
        title="Middle OPS",
        level="OPS",
    )

    # root
    _write_config(
        root_dir,
        extra={"associates": {"middle": {"path": "../middle", "namespace": "MIDDLE"}}},
    )
    _write_spec_file(
        root_dir / "spec",
        "dev.md",
        req_id="ROOT-d00001",
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
    Validates REQ-d00203-B: An associate's own declarations join the federation
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

    # Verifies: REQ-d00203-B, REQ-d00202-D
    def test_REQ_d00203_B_transitive_associates_resolved(
        self, transitive_repos: dict[str, Path]
    ) -> None:
        """A repo reached only through an intermediate joins the federation.

        root declares middle; middle declares leaf. leaf is named nowhere
        in root's config, so a federation that only reads the root's own
        declarations would be missing it entirely.
        """
        fed = build_graph(
            repo_root=transitive_repos["root"],
            scan_code=False,
            scan_tests=False,
        )

        roots = {entry.repo_root for entry in fed.iter_repos()}
        assert roots == {
            transitive_repos["root"],
            transitive_repos["middle"],
            transitive_repos["leaf"],
        }
        # The leaf's requirement resolves from the root's entry point.
        assert fed.find_by_id("LEAF-p00001") is not None


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

        # ROOT-d00001 should have ASSOC-p00001 as parent via IMPLEMENTS
        dev_node = fed.find_by_id("ROOT-d00001")
        assert dev_node is not None, "DEV requirement not found"

        from elspais.graph.relations import EdgeKind

        parent_ids = {p.id for p in dev_node.iter_parents(edge_kinds={EdgeKind.IMPLEMENTS})}
        assert "ASSOC-p00001" in parent_ids, (
            f"Expected ROOT-d00001 to implement ASSOC-p00001, " f"but parents are: {parent_ids}"
        )

    def test_cross_graph_broken_ref_resolved(self, two_repos: dict[str, Path]) -> None:
        """After wiring, the broken reference should be resolved."""
        root_dir = two_repos["root"]

        fed = build_graph(
            repo_root=root_dir,
            scan_code=False,
            scan_tests=False,
        )

        # The reference ROOT-d00001 -> ASSOC-p00001 should not be broken
        broken = fed.broken_references()
        broken_targets = {br.target_id for br in broken}
        assert "ASSOC-p00001" not in broken_targets, (
            f"ASSOC-p00001 should not be a broken reference, " f"but found: {broken}"
        )

    def test_id_conflict_raises(self, tmp_path: Path) -> None:
        """Two repos defining the same ID raises FederationError.

        Both repos spell a fixed literal into their canonical pattern
        rather than their namespace, which is what leaves two distinctly
        namespaced repositories able to claim one identifier at all.
        """
        root_dir = tmp_path / "root"
        assoc_dir = tmp_path / "assoc"

        fixed_prefix = {"id-patterns": dict(_BASE_CONFIG["id-patterns"])}
        fixed_prefix["id-patterns"]["canonical"] = "REQ-{level.letter}{component}"

        # Both repos define REQ-p00001
        _write_config(assoc_dir, extra=dict(fixed_prefix))
        _write_spec_file(
            assoc_dir / "spec",
            "prd.md",
            req_id="REQ-p00001",
            title="Assoc PRD",
            level="PRD",
        )

        _write_config(
            root_dir,
            extra={
                **fixed_prefix,
                "associates": {"assoc": {"path": "../assoc", "namespace": "ASSOC"}},
            },
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
            req_id="ASSOC-p00001",
            title="Assoc PRD",
            level="PRD",
        )

        _write_config(
            root_dir,
            extra={"associates": {"assoc": {"path": "../assoc", "namespace": "ASSOC"}}},
        )
        # Root's DEV implements ROOT-p99999 which doesn't exist anywhere
        _write_spec_file(
            root_dir / "spec",
            "dev.md",
            req_id="ROOT-d00001",
            title="Root DEV",
            level="DEV",
            implements="ROOT-p99999",
        )

        fed = build_graph(
            repo_root=root_dir,
            scan_code=False,
            scan_tests=False,
        )

        broken = fed.broken_references()
        broken_targets = {br.target_id for br in broken}
        assert "ROOT-p99999" in broken_targets

    def test_shared_path_remainder_does_not_conflict(self, tmp_path: Path) -> None:
        """Regression: REMAINDER nodes use `rem:` prefix, not `remainder:`.

        Two repos with a spec file at the same relative path whose content
        produces a REMAINDER node (prose-only file) previously raised a
        FederationError because the ownership-map built in
        FederatedGraph.__init__ skipped `remainder:` but actual IDs are
        `rem:<path>:<line>`. Verifies REQ-d00200-D ownership mapping
        construction correctly skips structural (FILE/REMAINDER) nodes
        that naturally share relative paths across repos.
        """
        root_dir = tmp_path / "root"
        assoc_dir = tmp_path / "assoc"

        # Associate: unique REQ + shared-path prose file
        _write_config(assoc_dir)
        _write_spec_file(
            assoc_dir / "spec",
            "prd.md",
            req_id="ASSOC-p00001",
            title="Assoc PRD",
            level="PRD",
        )
        (assoc_dir / "spec").mkdir(parents=True, exist_ok=True)
        (assoc_dir / "spec" / "shared_notes.md").write_text(
            "Some prose that contains no requirement block.\n",
            encoding="utf-8",
        )

        # Root: unique REQ + same-path prose file
        _write_config(
            root_dir,
            extra={"associates": {"assoc": {"path": "../assoc", "namespace": "ASSOC"}}},
        )
        _write_spec_file(
            root_dir / "spec",
            "dev.md",
            req_id="ROOT-d00001",
            title="Root DEV",
            level="DEV",
        )
        (root_dir / "spec" / "shared_notes.md").write_text(
            "Different prose, also without a requirement block.\n",
            encoding="utf-8",
        )

        # Must NOT raise — REMAINDER nodes for a path both repos hold
        # (`rem:<namespace>:spec/shared_notes.md:1`) must not be read as an
        # ID conflict during ownership detection.
        fed = build_graph(
            repo_root=root_dir,
            scan_code=False,
            scan_tests=False,
        )

        # Both sub-graphs merged: requirements from each repo are findable.
        assert (
            fed.find_by_id("ROOT-d00001") is not None
        ), "Root DEV requirement not found after federated build"
        assert (
            fed.find_by_id("ASSOC-p00001") is not None
        ), "Associate PRD requirement not found after federated build"

        # Confirm the shared-path REMAINDER actually existed in at least
        # one sub-graph (proves the scenario reproduces the pre-fix bug).
        rem_found = False
        for entry in fed.iter_repos():
            if entry.graph is None:
                continue
            for node_id in entry.graph._index:
                if not node_id.startswith(REMAINDER_ID_PREFIX):
                    continue
                _prefix, namespace, relative_path, _line = parse_structural_id(node_id)
                if namespace == entry.graph.namespace and relative_path == "spec/shared_notes.md":
                    rem_found = True
                    break
            if rem_found:
                break
        assert rem_found, (
            "Expected at least one REMAINDER node with id starting "
            "'rem:spec/shared_notes.md' in some sub-graph; "
            "fixture did not reproduce the bug condition"
        )


# ---------------------------------------------------------------------------
# Coverage is annotated in every build shape
# ---------------------------------------------------------------------------


def _coverage_toml(name: str, namespace: str, associates: str = "") -> str:
    """Config for a repo whose own `src/` carries the coverage evidence."""
    return f"""version = 3

[project]
name = "{name}"
namespace = "{namespace}"

[levels.prd]
rank = 1
implements = []

[levels.dev]
rank = 2
implements = ["prd", "dev"]

[scanning.code]
directories = ["src"]
{associates}"""


def _coverage_spec(namespace: str) -> str:
    """One requirement with two labelled assertions, only A implemented."""
    return f"""# Spec for {namespace}

## {namespace}-d00001: A thing

**Status**: active

The system shall do a thing.

### Assertions

A. The system SHALL do the A thing.

B. The system SHALL do the B thing.

*End*
"""


def _coverage_code(namespace: str) -> str:
    return f'''"""Implementation."""


# Implements: {namespace}-d00001-A
def do_a():
    return 1
'''


def _make_coverage_repo(
    base: Path,
    name: str,
    namespace: str,
    associates: str = "",
) -> Path:
    """An on-disk repo holding one requirement and code implementing it."""
    repo = make_repo(
        base,
        name,
        namespace=namespace,
        config_text=_coverage_toml(name, namespace, associates),
    )
    (repo / "spec" / "reqs.md").write_text(_coverage_spec(namespace), encoding="utf-8")
    (repo / "src").mkdir()
    (repo / "src" / "impl.py").write_text(_coverage_code(namespace), encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "code")
    return repo


@pytest.fixture(scope="module")
def coverage_repos(tmp_path_factory) -> dict[str, Path]:
    """One repo of every build shape, each self-evidencing its own assertion A.

    ``app`` hosts a live federation with ``lib``; ``orphan`` declares an
    associate that cannot be loaded at all; ``solo`` declares none.
    """
    base = tmp_path_factory.mktemp("cov_shapes")
    lib = _make_coverage_repo(base, "lib", "LIB")
    app = _make_coverage_repo(
        base,
        "app",
        "APP",
        associates='\n[associates.lib]\npath = "../lib"\nnamespace = "LIB"\n',
    )
    orphan = _make_coverage_repo(
        base,
        "orphan",
        "ORPHAN",
        associates='\n[associates.ghost]\npath = "../ghost"\nnamespace = "GHOST"\n',
    )
    solo = _make_coverage_repo(base, "solo", "SOLO")
    return {"lib": lib, "app": app, "orphan": orphan, "solo": solo}


def _implemented(fed, req_id: str):
    """The implemented dimension of a requirement's rollup metrics."""
    node = fed.find_by_id(req_id)
    assert node is not None, f"{req_id} is not in the graph"
    metrics = node.get_metric("rollup_metrics")
    assert metrics is not None, f"{req_id} carries no rollup_metrics at all"
    assert (
        metrics.total_assertions == 2
    ), f"{req_id} should hold two assertions, got {metrics.total_assertions}"
    return metrics.implemented


def _assert_a_implemented(fed, req_id: str) -> None:
    """Assertion A is fully implemented and B is not.

    Zero here is the signature of coverage never having been annotated for
    this repository -- the failure mode that otherwise reads as a project
    with no evidence at all.
    """
    dim = _implemented(fed, req_id)
    assert dim.direct > 0.0, (
        f"{req_id} reports no implemented coverage; its own code declares "
        f"'Implements: {req_id}-A', so coverage was never annotated for this repo"
    )
    assert dim.direct_pct_by_label["A"] == 1.0
    assert dim.direct_pct_by_label.get("B", 0.0) == 0.0


class TestCoverageAnnotatedInEveryBuildShape:
    """Coverage is present however a build was assembled.

    Validates REQ-d00269-A: no coverage number depends on the order in which
    a federation was assembled -- including the degenerate orders, where the
    federation has one live member or none to recompute over.
    Validates REQ-d00261-E: a member's own coverage is the same number built
    alone as it is inside a federation.
    """

    # Verifies: REQ-d00269-A
    def test_REQ_d00269_A_two_member_federation_carries_coverage(
        self, coverage_repos: dict[str, Path]
    ) -> None:
        """Both members of a live federation carry their own coverage."""
        fed = build_graph(repo_root=coverage_repos["app"])

        live = [e for e in fed.iter_repos() if e.graph is not None]
        assert len(live) == 2, f"expected two live members, got {[e.name for e in live]}"
        _assert_a_implemented(fed, "APP-d00001")
        _assert_a_implemented(fed, "LIB-d00001")

    # Verifies: REQ-d00269-A
    def test_REQ_d00269_A_host_with_no_loadable_associate_carries_coverage(
        self, coverage_repos: dict[str, Path]
    ) -> None:
        """A host whose every associate failed to load still carries coverage.

        No recompute runs over this graph, so the host's own annotation is
        the only one there will ever be.
        """
        fed = build_graph(repo_root=coverage_repos["orphan"])

        entries = list(fed.iter_repos())
        assert [e.name for e in entries if e.graph is None] == [
            "ghost"
        ], "fixture must produce exactly one associate that failed to load"
        _assert_a_implemented(fed, "ORPHAN-d00001")

    # Verifies: REQ-d00269-A
    def test_REQ_d00269_A_lone_repository_carries_coverage(
        self, coverage_repos: dict[str, Path]
    ) -> None:
        """A repository declaring no associates carries coverage."""
        fed = build_graph(repo_root=coverage_repos["solo"])

        assert [e.name for e in fed.iter_repos()] == ["solo"]
        _assert_a_implemented(fed, "SOLO-d00001")

    # Verifies: REQ-d00261-E
    def test_REQ_d00261_E_member_coverage_matches_the_same_repo_built_alone(
        self, coverage_repos: dict[str, Path]
    ) -> None:
        """Joining a federation moves none of a member's own numbers."""
        alone = _implemented(build_graph(repo_root=coverage_repos["lib"]), "LIB-d00001")
        joined = _implemented(build_graph(repo_root=coverage_repos["app"]), "LIB-d00001")

        assert (alone.direct, alone.indirect) == (joined.direct, joined.indirect)
        assert alone.direct_pct_by_label == joined.direct_pct_by_label
        assert alone.direct > 0.0, "the lone build carries no coverage to compare"


class TestRootRepoReportsItsOrigin:
    """Validates REQ-d00206-A: every repo from iter_repos() reports its origin.

    The reporting surfaces read `git_origin` off whatever `iter_repos()`
    yields, so a member that never carries one can never be reported with
    one. These tests go through `build_graph` over real git-backed repos
    rather than constructing a `RepoEntry` with an origin handed to it,
    because the repository being worked in -- the one entry no test built
    by hand -- was the one that went without.
    """

    # Verifies: REQ-d00206-A
    def test_REQ_d00206_A_federated_host_reports_its_origin(self, tmp_path: Path) -> None:
        """The host entry carries an origin, not only its associates."""
        make_repo(tmp_path, "lib", origin="https://example.com/lib.git")
        host = make_repo(
            tmp_path,
            "app",
            associates={"lib": "../lib"},
            origin="https://example.com/app.git",
        )

        fed = build_graph(repo_root=host, scan_code=False, scan_tests=False)
        entries = {e.name: e for e in fed.iter_repos()}
        assert set(entries) == {"app", "lib"}

        # The planner may normalize the URL it detects, so what is asserted
        # is that an origin was detected at all and that it names this repo.
        assert (
            entries["app"].git_origin is not None
        ), "the host repository reported no origin, so no surface can report one for it"
        assert "example.com/app" in entries["app"].git_origin
        assert entries["lib"].git_origin is not None
        assert "example.com/lib" in entries["lib"].git_origin

    # Verifies: REQ-d00206-A
    def test_REQ_d00206_A_lone_repository_reports_its_origin(self, tmp_path: Path) -> None:
        """A project declaring no associates still reports its own origin."""
        solo = make_repo(tmp_path, "solo", origin="https://example.com/solo.git")

        fed = build_graph(repo_root=solo, scan_code=False, scan_tests=False)
        entries = list(fed.iter_repos())

        assert [e.name for e in entries] == ["solo"]
        assert (
            entries[0].git_origin is not None
        ), "a project with no associates reported no origin for its own repository"
        assert "example.com/solo" in entries[0].git_origin

    # Verifies: REQ-d00206-A
    def test_REQ_d00206_A_repository_without_a_remote_reports_none(self, tmp_path: Path) -> None:
        """No remote configured stays distinguishable from an origin.

        Absence is the answer for a repository that has no remote; anything
        invented in its place would be reported as a real origin and would
        draw staleness reporting against a remote that does not exist.
        """
        host = make_repo(tmp_path, "nohost", associates={"norem": "../norem"})
        make_repo(tmp_path, "norem")

        fed = build_graph(repo_root=host, scan_code=False, scan_tests=False)
        entries = {e.name: e for e in fed.iter_repos()}

        assert set(entries) == {"nohost", "norem"}
        assert entries["nohost"].git_origin is None
        assert entries["norem"].git_origin is None
