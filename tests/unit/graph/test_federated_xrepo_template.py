# Verifies: REQ-p00014-H
"""Federated cross-repo Satisfies instantiation (CUR-1353 Phase A).

Phase 3 of CUR-1353: at federation time, a per-repo broken-ref of
``edge_kind == satisfies`` whose target lives in *another* federated
repo causes ``FederatedGraph`` to clone the template REQ subtree
(REQ + directly-attached assertions) into the declaring repo's
``_index`` with composite IDs ``<declaring>::<original>``. The
declaring repo gets intra-graph ``SATISFIES`` + ``STRUCTURES`` +
``DEFINES`` edges, and each clone gets a cross-graph ``INSTANCE``
edge back to its template original.
"""

from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path

from elspais.graph.factory import build_graph
from elspais.graph.federated import FederatedGraph, RepoEntry
from elspais.graph.GraphNode import NodeKind
from elspais.graph.relations import EdgeKind, Stereotype

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _write(repo: Path, rel: str, body: str) -> None:
    """Write ``body`` (dedented, stripped, newline-terminated) to ``repo/rel``."""
    full = repo / rel
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(textwrap.dedent(body).strip() + "\n")


def _git_init(repo: Path) -> None:
    """Initialise a git repo at ``repo`` so capture_git_info doesn't warn."""
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=x@y",
            "-c",
            "user.name=t",
            "commit",
            "-q",
            "-m",
            "init",
        ],
        cwd=repo,
        check=True,
    )


def _make_library(tmp_path: Path) -> Path:
    """Build the ``library`` repo with one **Template** PRD (LIB-p00001)."""
    library = tmp_path / "library"
    library.mkdir()
    _write(
        library,
        ".elspais.toml",
        """
        version = 3
        [project]
        name = "library"
        namespace = "LIB"
        [levels.prd]
        rank = 1
        letter = "p"
        implements = ["prd"]
        [scanning.spec]
        directories = ["spec"]
        [scanning.code]
        directories = []
        [scanning.test]
        enabled = false
        directories = []
        """,
    )
    _write(
        library,
        "spec/prd-library.md",
        """
        # LIB-p00001: Action Dispatch

        **Level**: PRD | **Status**: Approved | **Template**

        ### Assertions

        A. SHALL parse.

        B. SHALL authorize.

        *End* *Action Dispatch*
        """,
    )
    _git_init(library)
    return library


def _make_app(tmp_path: Path) -> Path:
    """Build the ``app`` repo which Satisfies ``LIB-p00001``."""
    app = tmp_path / "app"
    app.mkdir()
    _write(
        app,
        ".elspais.toml",
        """
        version = 3
        [project]
        name = "app"
        namespace = "APP"
        [levels.prd]
        rank = 1
        letter = "p"
        implements = ["prd"]
        [scanning.spec]
        directories = ["spec"]
        [scanning.code]
        directories = []
        [scanning.test]
        enabled = false
        directories = []
        [associates.library]
        path = "../library"
        namespace = "LIB"
        """,
    )
    _write(
        app,
        "spec/prd-app.md",
        """
        # APP-p00001: Concrete Action

        **Level**: PRD | **Status**: Approved
        **Satisfies**: LIB-p00001

        ### Assertions

        A. SHALL be sponsor-specific.

        *End* *Concrete Action*
        """,
    )
    _git_init(app)
    return app


def _build_federation(tmp_path: Path) -> FederatedGraph:
    """Build the canonical two-repo (library + app) federation."""
    _make_library(tmp_path)
    app = _make_app(tmp_path)
    return build_graph(repo_root=app, scan_code=False, scan_tests=False)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCrossRepoCloneShape:
    """The library template REQ is cloned into the app's index with composite IDs."""

    def test_app_index_contains_composite_instance_root(self, tmp_path: Path) -> None:
        fed = _build_federation(tmp_path)
        composite = "APP-p00001::LIB-p00001"
        node = fed.find_by_id(composite)
        if node is None:
            brs = [(br.source_id, br.target_id, br.edge_kind) for br in fed.broken_references()]
            raise AssertionError(
                f"expected cloned REQ {composite} to be present in the app's index; "
                f"got broken refs: {brs}"
            )
        assert node.kind == NodeKind.REQUIREMENT
        assert node.get_field("stereotype") == Stereotype.INSTANCE

    def test_app_index_contains_composite_assertions(self, tmp_path: Path) -> None:
        fed = _build_federation(tmp_path)
        for label in ("A", "B"):
            comp = f"APP-p00001::LIB-p00001-{label}"
            assertion = fed.find_by_id(comp)
            assert assertion is not None, f"expected cloned assertion {comp}"
            assert assertion.kind == NodeKind.ASSERTION
            assert assertion.get_field("stereotype") == Stereotype.INSTANCE

    def test_instance_edges_cross_to_template_originals(self, tmp_path: Path) -> None:
        fed = _build_federation(tmp_path)
        clone = fed.find_by_id("APP-p00001::LIB-p00001")
        assert clone is not None
        instance_edges = [e for e in clone.iter_outgoing_edges() if e.kind == EdgeKind.INSTANCE]
        assert len(instance_edges) == 1
        assert instance_edges[0].target.id == "LIB-p00001"

    def test_satisfies_edge_declaring_to_clone(self, tmp_path: Path) -> None:
        fed = _build_federation(tmp_path)
        declaring = fed.find_by_id("APP-p00001")
        assert declaring is not None
        sat_edges = [e for e in declaring.iter_outgoing_edges() if e.kind == EdgeKind.SATISFIES]
        assert len(sat_edges) == 1
        assert sat_edges[0].target.id == "APP-p00001::LIB-p00001"

    def test_structures_edges_within_clone(self, tmp_path: Path) -> None:
        fed = _build_federation(tmp_path)
        clone = fed.find_by_id("APP-p00001::LIB-p00001")
        assert clone is not None
        structure_edges = [e for e in clone.iter_outgoing_edges() if e.kind == EdgeKind.STRUCTURES]
        assert len(structure_edges) == 2  # one per cloned assertion
        targets = {e.target.id for e in structure_edges}
        assert targets == {
            "APP-p00001::LIB-p00001-A",
            "APP-p00001::LIB-p00001-B",
        }

    def test_defines_edges_from_declaring_file(self, tmp_path: Path) -> None:
        fed = _build_federation(tmp_path)
        declaring = fed.find_by_id("APP-p00001")
        assert declaring is not None
        declaring_file = declaring.file_node()
        assert declaring_file is not None
        defines_targets = {
            e.target.id for e in declaring_file.iter_outgoing_edges() if e.kind == EdgeKind.DEFINES
        }
        expected = {
            "APP-p00001::LIB-p00001",
            "APP-p00001::LIB-p00001-A",
            "APP-p00001::LIB-p00001-B",
        }
        assert expected <= defines_targets

    def test_clone_file_node_is_none(self, tmp_path: Path) -> None:
        """INSTANCE clones have no FILE ancestor — render_save will not visit them."""
        fed = _build_federation(tmp_path)
        clone = fed.find_by_id("APP-p00001::LIB-p00001")
        assert clone is not None
        assert clone.file_node() is None

    def test_clone_records_template_repo_field(self, tmp_path: Path) -> None:
        """Every cross-repo clone (root + assertions) records the template's repo name.

        Phase 5 (CUR-1353, REQ-p00014-K): viewers need provenance --
        "Template defined in `{repo_name}`" -- without re-walking the
        cross-graph INSTANCE edge for every render. The federated
        builder writes ``template_repo`` on each clone at instantiation
        time. This invariant ensures the field is set on both the
        cloned root REQ and each cloned assertion.
        """
        fed = _build_federation(tmp_path)
        for composite in (
            "APP-p00001::LIB-p00001",
            "APP-p00001::LIB-p00001-A",
            "APP-p00001::LIB-p00001-B",
        ):
            node = fed.find_by_id(composite)
            assert node is not None, f"expected clone {composite} to exist"
            assert node.get_field("template_repo") == "library", (
                f"clone {composite} should record template_repo='library', "
                f"got {node.get_field('template_repo')!r}"
            )

    def test_broken_ref_is_resolved(self, tmp_path: Path) -> None:
        """The Satisfies broken-ref against the foreign template is consumed."""
        fed = _build_federation(tmp_path)
        brs = list(fed.broken_references())
        assert not any(
            br.source_id == "APP-p00001" and br.edge_kind == EdgeKind.SATISFIES.value for br in brs
        ), f"expected APP-p00001 satisfies broken-ref to be resolved, got {brs}"

    def test_satisfies_with_non_canonical_id_produces_canonical_composite(
        self, tmp_path: Path
    ) -> None:
        """Author writes ``Satisfies: LIB-p1`` (non-canonical, unpadded).

        The cold-path ``_claim_for`` probe resolves it to canonical
        ``LIB-p00001`` via the library's ``IdResolver``. The resulting clone
        must use the canonical form in the composite ID, not the as-authored
        form -- otherwise two satisfiers writing different non-canonical
        spellings of the same template would produce shadow composites and
        ``_ownership`` would split across forms.
        """
        library = tmp_path / "library"
        app = tmp_path / "app"
        library.mkdir()
        app.mkdir()
        _write(
            library,
            ".elspais.toml",
            """
            version = 3
            [project]
            name = "library"
            namespace = "LIB"
            [levels.prd]
            rank = 1
            letter = "p"
            implements = ["prd"]
            [scanning.spec]
            directories = ["spec"]
            [scanning.code]
            directories = []
            [scanning.test]
            enabled = false
            directories = []
            """,
        )
        _write(
            library,
            "spec/prd-library.md",
            """
            # LIB-p00001: Action Dispatch

            **Level**: PRD | **Status**: Approved | **Template**

            ### Assertions

            A. SHALL parse.

            *End* *Action Dispatch*
            """,
        )
        _write(
            app,
            ".elspais.toml",
            """
            version = 3
            [project]
            name = "app"
            namespace = "APP"
            [levels.prd]
            rank = 1
            letter = "p"
            implements = ["prd"]
            [scanning.spec]
            directories = ["spec"]
            [scanning.code]
            directories = []
            [scanning.test]
            enabled = false
            directories = []
            [associates.library]
            path = "../library"
            namespace = "LIB"
            """,
        )
        # NOTE: non-canonical unpadded `LIB-p1` -- relies on the library's
        # IdResolver to canonicalise to LIB-p00001 (digits=5, leading_zeros).
        _write(
            app,
            "spec/prd-app.md",
            """
            # APP-p00001: Concrete Action

            **Level**: PRD | **Status**: Approved
            **Satisfies**: LIB-p1

            ### Assertions

            A. SHALL be specific.

            *End* *Concrete Action*
            """,
        )
        _git_init(library)
        _git_init(app)

        fed = build_graph(repo_root=app, scan_code=False, scan_tests=False)

        # The composite ID must use the canonical LIB-p00001 form -- never
        # the as-authored LIB-p1.  If this invariant breaks, _claim_for is
        # returning a non-canonical second element or the clone builder is
        # using br.target_id instead of orig.id when constructing clone_id.
        canonical_composite = fed.find_by_id("APP-p00001::LIB-p00001")
        non_canonical_composite = fed.find_by_id("APP-p00001::LIB-p1")
        assert (
            canonical_composite is not None
        ), "expected canonical composite APP-p00001::LIB-p00001 to exist"
        assert non_canonical_composite is None, (
            "non-canonical composite APP-p00001::LIB-p1 must NOT exist "
            "(would indicate a shadow ownership entry)"
        )

        # And the Satisfies broken-ref against the non-canonical target must
        # have been consumed, not left dangling under either spelling.
        brs = list(fed.broken_references())
        assert not any(
            br.source_id == "APP-p00001" and br.edge_kind == EdgeKind.SATISFIES.value for br in brs
        ), f"expected satisfies broken-ref to be resolved, got {brs}"

    def test_two_satisfiers_get_independent_clones(self, tmp_path: Path) -> None:
        """A second downstream repo gets its own composite clones.

        Builds three repos (library, app, tenant), then constructs a single
        FederatedGraph from the three RepoEntry objects directly.  The
        plan's hypothetical ``extra_associates=`` factory parameter does
        not exist; assembling RepoEntry instances by hand is the idiomatic
        way to federate ad-hoc combinations in tests.
        """
        library = _make_library(tmp_path)
        app = _make_app(tmp_path)
        tenant = tmp_path / "tenant"
        tenant.mkdir()
        _write(
            tenant,
            ".elspais.toml",
            """
            version = 3
            [project]
            name = "tenant"
            namespace = "TEN"
            [levels.prd]
            rank = 1
            letter = "p"
            implements = ["prd"]
            [scanning.spec]
            directories = ["spec"]
            [scanning.code]
            directories = []
            [scanning.test]
            enabled = false
            directories = []
            [associates.library]
            path = "../library"
            namespace = "LIB"
            """,
        )
        _write(
            tenant,
            "spec/prd-tenant.md",
            """
            # TEN-p00001: Tenant Action

            **Level**: PRD | **Status**: Approved
            **Satisfies**: LIB-p00001

            ### Assertions

            A. SHALL be tenant-specific.

            *End* *Tenant Action*
            """,
        )
        _git_init(tenant)

        # Build each repo as a federation-of-one (no associates wiring),
        # then stitch them into a single FederatedGraph.  This bypasses the
        # automatic build_graph associate resolution so the same library
        # graph object is shared across both satisfier repos.
        lib_fed = build_graph(
            repo_root=library, scan_code=False, scan_tests=False, _build_associates=False
        )
        app_fed = build_graph(
            repo_root=app, scan_code=False, scan_tests=False, _build_associates=False
        )
        tenant_fed = build_graph(
            repo_root=tenant, scan_code=False, scan_tests=False, _build_associates=False
        )

        lib_entry = next(iter(lib_fed.iter_repos()))
        app_entry = next(iter(app_fed.iter_repos()))
        tenant_entry = next(iter(tenant_fed.iter_repos()))

        fed2 = FederatedGraph(
            repos=[
                RepoEntry(
                    name="app",
                    graph=app_entry.graph,
                    config=app_entry.config,
                    repo_root=app,
                ),
                RepoEntry(
                    name="tenant",
                    graph=tenant_entry.graph,
                    config=tenant_entry.config,
                    repo_root=tenant,
                ),
                RepoEntry(
                    name="library",
                    graph=lib_entry.graph,
                    config=lib_entry.config,
                    repo_root=library,
                ),
            ],
            root_repo="app",
        )

        app_clone = fed2.find_by_id("APP-p00001::LIB-p00001")
        tenant_clone = fed2.find_by_id("TEN-p00001::LIB-p00001")
        assert app_clone is not None, "app's clone should exist"
        assert tenant_clone is not None, "tenant's clone should exist"
        assert app_clone is not tenant_clone, "clones must be independent"

        # Each clone points at the SAME library original via INSTANCE.
        app_instance = next(
            (e for e in app_clone.iter_outgoing_edges() if e.kind == EdgeKind.INSTANCE),
            None,
        )
        tenant_instance = next(
            (e for e in tenant_clone.iter_outgoing_edges() if e.kind == EdgeKind.INSTANCE),
            None,
        )
        assert app_instance is not None
        assert tenant_instance is not None
        assert app_instance.target.id == "LIB-p00001"
        assert tenant_instance.target.id == "LIB-p00001"
        assert app_instance.target is tenant_instance.target


# ---------------------------------------------------------------------------
# _claim_for resolver-probe coverage
# ---------------------------------------------------------------------------


class TestClaimForResolverProbe:
    """``_claim_for`` falls back to per-repo IdResolver lookup when exact-match misses.

    Cold path: a foreign-repo reference written in a *non-canonical* form that
    the foreign repo's ``IdResolver`` parses and renders to a canonical ID
    that DOES exist in that repo's ``_index``. Exact ``_ownership`` lookup
    misses (it stores only canonical IDs); ``_claim_for`` must still succeed.

    The library config uses numeric components with ``leading_zeros=True`` and
    ``digits=5``. ``IdResolver.parse`` zero-pads the component, so ``LIB-p1``
    parses and canonicalises to ``LIB-p00001`` — the actual indexed form.
    """

    def test_claim_for_resolves_unpadded_to_canonical(self, tmp_path: Path) -> None:
        """Unpadded numeric component is the live cold-path scenario.

        ``LIB-p1`` is NOT in ``_ownership`` (only canonical IDs are), but the
        library's resolver parses it and ``render_canonical`` yields
        ``LIB-p00001`` which IS in the library's ``_index``.
        """
        _make_library(tmp_path)
        app = _make_app(tmp_path)
        fed = build_graph(repo_root=app, scan_code=False, scan_tests=False)

        # Pre-condition: the unpadded form is NOT in _ownership.  If this ever
        # changes (e.g. ownership keys gain canonicalisation), the cold path
        # would no longer be exercised here and this test must be rewritten.
        assert "LIB-p1" not in fed._ownership

        claim = fed._claim_for("LIB-p1")
        assert claim == ("library", "LIB-p00001")

    def test_claim_for_resolves_short_padded_to_canonical(self, tmp_path: Path) -> None:
        """Partial zero-padding (``LIB-p001``) is also normalised.

        Belt-and-braces second probe of the zero-pad cold path with a
        differently-truncated component, ensuring the test isn't accidentally
        passing because of a single magic value.
        """
        _make_library(tmp_path)
        app = _make_app(tmp_path)
        fed = build_graph(repo_root=app, scan_code=False, scan_tests=False)

        assert "LIB-p001" not in fed._ownership
        assert fed._claim_for("LIB-p001") == ("library", "LIB-p00001")

    def test_claim_for_returns_none_when_no_repo_claims(self, tmp_path: Path) -> None:
        """``_claim_for`` returns ``None`` when the ID parses for no associated repo.

        Verifies the negative branch — both ``is_local_id`` rejection (foreign
        namespace) and a parseable-but-not-present canonical form.
        """
        _make_library(tmp_path)
        app = _make_app(tmp_path)
        fed = build_graph(repo_root=app, scan_code=False, scan_tests=False)

        # No resolver claims a totally foreign namespace.
        assert fed._claim_for("DOES-NOT-EXIST-99999") is None

        # The library resolver PARSES LIB-p99999, but the canonical form is
        # not in the library's _index, so _claim_for must still return None.
        assert fed._claim_for("LIB-p99999") is None


# ---------------------------------------------------------------------------
# Federated diagnostics: missing associate + Satisfies cycle (Phase 4)
# ---------------------------------------------------------------------------


# Verifies: REQ-p00014-J
class TestFederatedDiagnostics:
    """Phase 4: typed diagnostics for federation-level Satisfies failures.

    Two new failure modes covered here:

    1. Missing-associate: a cross-repo ``Satisfies:`` target's namespace is
       not declared in any ``[associates.*]`` block. The diagnostic must
       point authors at the target ID, the ``[associates.<name>]`` config
       knob, ``.elspais.toml``, and list the currently-available associates
       (or explicitly state none are declared).

    2. Satisfies cycle: two repos' templates satisfy each other (or any
       transitive cycle over SATISFIES + INSTANCE edges). Federated build
       must surface a typed cycle diagnostic via a ``BrokenReference``.
    """

    def test_missing_associate_diagnostic(self, tmp_path: Path) -> None:
        """Single-repo app references a namespace that no associate covers.

        Because ``[associates.*]`` is empty, the diagnostic must include the
        phrase ``No associates declared`` to make the actionable fix obvious
        (authors must add an associate, not switch namespaces).
        """
        app = tmp_path / "app"
        app.mkdir()
        _write(
            app,
            ".elspais.toml",
            """
            version = 3
            [project]
            name = "app"
            namespace = "APP"
            [levels.prd]
            rank = 1
            letter = "p"
            implements = ["prd"]
            [scanning.spec]
            directories = ["spec"]
            [scanning.code]
            directories = []
            [scanning.test]
            enabled = false
            directories = []
            """,
        )
        _write(
            app,
            "spec/prd-app.md",
            """
            # APP-p00001: Orphan Satisfier

            **Level**: PRD | **Status**: Approved
            **Satisfies**: EVS-p00001

            ### Assertions

            A. SHALL satisfy nothing.

            *End* *Orphan Satisfier*
            """,
        )
        _git_init(app)

        fed = build_graph(repo_root=app, scan_code=False, scan_tests=False)
        brs = [
            br
            for br in fed.broken_references()
            if br.source_id == "APP-p00001" and br.edge_kind == EdgeKind.SATISFIES.value
        ]
        assert brs, (
            "expected a broken-ref for APP-p00001 satisfies EVS-p00001; "
            f"got {[(b.source_id, b.target_id, b.edge_kind) for b in fed.broken_references()]}"
        )
        diag = brs[0].diagnostic
        assert "EVS-p00001" in diag, f"target ID missing from diagnostic: {diag!r}"
        assert "[associates" in diag, f"[associates hint missing: {diag!r}"
        assert ".elspais.toml" in diag, f".elspais.toml hint missing: {diag!r}"
        assert (
            "No associates declared" in diag
        ), f"expected 'No associates declared' phrasing when no associates exist: {diag!r}"

    def test_missing_associate_diagnostic_with_other_associates(self, tmp_path: Path) -> None:
        """When other associates exist, diagnostic names them.

        The library is declared as an associate. The app's Satisfies points
        at a DIFFERENT namespace (``EVS``) that no associate covers, so the
        diagnostic must still fire — but now list ``library`` as an
        available associate to clarify what IS declared.
        """
        library = _make_library(tmp_path)
        del library  # only the side-effect (writing the library repo) matters
        app = tmp_path / "app"
        app.mkdir()
        _write(
            app,
            ".elspais.toml",
            """
            version = 3
            [project]
            name = "app"
            namespace = "APP"
            [levels.prd]
            rank = 1
            letter = "p"
            implements = ["prd"]
            [scanning.spec]
            directories = ["spec"]
            [scanning.code]
            directories = []
            [scanning.test]
            enabled = false
            directories = []
            [associates.library]
            path = "../library"
            namespace = "LIB"
            """,
        )
        _write(
            app,
            "spec/prd-app.md",
            """
            # APP-p00001: Wrong Namespace Satisfier

            **Level**: PRD | **Status**: Approved
            **Satisfies**: EVS-p00001

            ### Assertions

            A. SHALL look elsewhere.

            *End* *Wrong Namespace Satisfier*
            """,
        )
        _git_init(app)

        fed = build_graph(repo_root=app, scan_code=False, scan_tests=False)
        brs = [
            br
            for br in fed.broken_references()
            if br.source_id == "APP-p00001" and br.edge_kind == EdgeKind.SATISFIES.value
        ]
        assert brs, (
            "expected a broken-ref for APP-p00001 satisfies EVS-p00001; "
            f"got {[(b.source_id, b.target_id, b.edge_kind) for b in fed.broken_references()]}"
        )
        diag = brs[0].diagnostic
        assert "EVS-p00001" in diag, f"target ID missing from diagnostic: {diag!r}"
        assert "library" in diag, f"available associate name missing: {diag!r}"
        assert "[associates" in diag, f"[associates hint missing: {diag!r}"
        assert ".elspais.toml" in diag, f".elspais.toml hint missing: {diag!r}"

    def test_satisfies_cycle_emits_broken_ref(self, tmp_path: Path) -> None:
        """Two repos whose templates satisfy each other form a cycle.

        Federated build walks SATISFIES then INSTANCE edges; when DFS
        re-enters a node already on the path, a typed BrokenReference with
        ``cycle`` in its diagnostic is emitted (one per build).

        We assemble the federation by hand from per-repo
        federation-of-one builds (``_build_associates=False``), bypassing
        the on-disk transitive-associates guard so we can construct a
        topology that the standard CLI path would refuse to load. This is
        the same pattern as
        ``test_two_satisfiers_get_independent_clones``.
        """
        a = tmp_path / "repo_a"
        b = tmp_path / "repo_b"
        a.mkdir()
        b.mkdir()
        _write(
            a,
            ".elspais.toml",
            """
            version = 3
            [project]
            name = "repo_a"
            namespace = "AAA"
            [levels.prd]
            rank = 1
            letter = "p"
            implements = ["prd"]
            [scanning.spec]
            directories = ["spec"]
            [scanning.code]
            directories = []
            [scanning.test]
            enabled = false
            directories = []
            """,
        )
        _write(
            a,
            "spec/prd.md",
            """
            # AAA-p00001: A Template

            **Level**: PRD | **Status**: Approved | **Template**
            **Satisfies**: BBB-p00001

            ### Assertions

            A. SHALL be A.

            *End* *A Template*
            """,
        )
        _write(
            b,
            ".elspais.toml",
            """
            version = 3
            [project]
            name = "repo_b"
            namespace = "BBB"
            [levels.prd]
            rank = 1
            letter = "p"
            implements = ["prd"]
            [scanning.spec]
            directories = ["spec"]
            [scanning.code]
            directories = []
            [scanning.test]
            enabled = false
            directories = []
            """,
        )
        _write(
            b,
            "spec/prd.md",
            """
            # BBB-p00001: B Template

            **Level**: PRD | **Status**: Approved | **Template**
            **Satisfies**: AAA-p00001

            ### Assertions

            A. SHALL be B.

            *End* *B Template*
            """,
        )
        _git_init(a)
        _git_init(b)

        a_fed = build_graph(repo_root=a, scan_code=False, scan_tests=False, _build_associates=False)
        b_fed = build_graph(repo_root=b, scan_code=False, scan_tests=False, _build_associates=False)
        a_entry = next(iter(a_fed.iter_repos()))
        b_entry = next(iter(b_fed.iter_repos()))

        fed = FederatedGraph(
            repos=[
                RepoEntry(
                    name="repo_a",
                    graph=a_entry.graph,
                    config=a_entry.config,
                    repo_root=a,
                ),
                RepoEntry(
                    name="repo_b",
                    graph=b_entry.graph,
                    config=b_entry.config,
                    repo_root=b,
                ),
            ],
            root_repo="repo_a",
        )

        brs = list(fed.broken_references())
        cycle_brs = [br for br in brs if "cycle" in br.diagnostic.lower()]
        assert cycle_brs, (
            f"expected a cycle diagnostic, got: "
            f"{[(b.source_id, b.target_id, b.diagnostic) for b in brs]}"
        )
