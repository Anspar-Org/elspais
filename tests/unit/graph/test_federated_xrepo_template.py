# Verifies: REQ-p00014-H
"""Federated cross-repo Satisfies instantiation.

At federation time, a per-repo broken-ref of ``edge_kind == satisfies``
whose target lives in *another* federated repo causes ``FederatedGraph``
to clone the template subtree rooted at the target — the REQ with its
assertions, plus every template REQ refining a member, recursively —
into the declaring repo's ``_index`` with composite IDs
``<declaring>::<original>``. The declaring repo gets intra-graph
``SATISFIES``, ``STRUCTURES``, ``REFINES`` and ``DEFINES`` edges, and
each clone gets a cross-graph ``INSTANCE`` edge back to its template
original.
"""

from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path

import pytest

from elspais.graph.factory import build_graph
from elspais.graph.federated import FederatedGraph, RepoEntry
from elspais.graph.GraphNode import NodeKind
from elspais.graph.reference_faults import FaultClass
from elspais.graph.relations import EdgeKind, Stereotype

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _write(repo: Path, rel: str, body: str) -> None:
    """Write ``body`` (dedented, stripped, newline-terminated) to ``repo/rel``."""
    full = repo / rel
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(textwrap.dedent(body).strip() + "\n")


def _bare_member(repo: Path) -> RepoEntry:
    """Build one repository's graph held by no federation yet."""
    from elspais.config import get_config
    from elspais.graph.factory import _build_repository

    config = get_config(None, repo)
    graph, _ = _build_repository(config, repo, scan_code=False, scan_tests=False)
    return RepoEntry(name=repo.name, graph=graph, config=config, repo_root=repo)


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
        version = 5
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
        version = 5
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
            brs = [(br.source_id, br.target_id, br.edge_kind) for br in fed.unresolved_references()]
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

    # Verifies: REQ-p00014-O
    def test_clone_records_template_repo_field(self, tmp_path: Path) -> None:
        """Every cross-repo clone (root + assertions) records the template's repo name.

        Viewers show "Template defined in `{repo_name}`" without walking
        the cross-graph INSTANCE edge for every render, so the federated
        builder writes ``template_repo`` on each clone at instantiation
        time -- the cloned root REQ and each cloned assertion alike.
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
        brs = list(fed.unresolved_references())
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
            version = 5
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
            version = 5
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
        assert canonical_composite is not None, (
            "expected canonical composite APP-p00001::LIB-p00001 to exist"
        )
        assert non_canonical_composite is None, (
            "non-canonical composite APP-p00001::LIB-p1 must NOT exist "
            "(would indicate a shadow ownership entry)"
        )

        # And the Satisfies broken-ref against the non-canonical target must
        # have been consumed, not left dangling under either spelling.
        brs = list(fed.unresolved_references())
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
            version = 5
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

        # Build each repo bare (no associates wiring), then stitch them into
        # a single FederatedGraph.  This bypasses the automatic build_graph
        # associate resolution so the same library graph object is shared
        # across both satisfier repos.
        lib_entry = _bare_member(library)
        app_entry = _bare_member(app)
        tenant_entry = _bare_member(tenant)

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
        assert claim == ("LIB", "LIB-p00001")

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
        assert fed._claim_for("LIB-p001") == ("LIB", "LIB-p00001")

    def test_claim_for_caches_resolvers(self, tmp_path: Path) -> None:
        """``_claim_for`` must not rebuild ``IdResolver`` on every call.

        Phase 8 of CUR-1353: cross-repo broken-ref probes are O(repos *
        broken_refs) in the pre-cache implementation because each call
        to ``_claim_for`` invokes ``build_resolver(entry.config)`` once
        per associated repo. Caching resolvers at federation
        construction (lazy, keyed by repo name) turns this into a
        one-time O(repos) cost.

        This test pins the cache invariant: any cold-path probe should
        populate the cache for the matched repo, and subsequent probes
        must reuse the same resolver instance (identity check, not
        equality) — guaranteeing no per-call rebuilds.
        """
        fed = _build_federation(tmp_path)

        # Cache is lazy: nothing built yet until ``_claim_for`` is called
        # against a non-canonical ID that misses ``_ownership``.  Build
        # passes (``_instantiate_cross_repo_satisfies``,
        # ``_annotate_presumed_foreign_refs``) populate the cache during
        # __init__, so we just snapshot what's already there and verify
        # subsequent calls reuse those exact instances.
        pre_call = dict(fed._resolver_cache)
        # The library was probed during cross-repo Satisfies instantiation,
        # so it must already be cached.
        assert "LIB" in pre_call, (
            f"expected the 'LIB' resolver to be cached after build; "
            f"cache keys: {sorted(pre_call.keys())}"
        )

        # Cold-path call — must hit the cache, not rebuild.
        fed._claim_for("LIB-p1")
        post_call = fed._resolver_cache

        # Same set of repos cached, same resolver instances (identity).
        assert set(post_call.keys()) == set(pre_call.keys()), (
            "_claim_for must not change the set of cached repos; "
            f"pre={sorted(pre_call.keys())} post={sorted(post_call.keys())}"
        )
        for name, resolver in pre_call.items():
            assert post_call[name] is resolver, (
                f"_claim_for rebuilt the IdResolver for repo {name!r} — "
                "cache must return the same instance across calls."
            )

        # And a second probe still doesn't rebuild.
        fed._claim_for("LIB-p1")
        for name, resolver in pre_call.items():
            assert fed._resolver_cache[name] is resolver, (
                f"second _claim_for rebuilt the IdResolver for repo {name!r}."
            )

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


def _satisfies_cycle_federation(tmp_path: Path) -> FederatedGraph:
    """Two repos whose templates satisfy each other, federated by hand."""
    a = tmp_path / "repo_a"
    b = tmp_path / "repo_b"
    a.mkdir()
    b.mkdir()
    _write(
        a,
        ".elspais.toml",
        """
        version = 5
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
        version = 5
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

    a_entry = _bare_member(a)
    b_entry = _bare_member(b)

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
    )
    return fed


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
       must surface a typed cycle diagnostic via a ``ReferenceFault``.
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
            version = 5
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
            for br in fed.unresolved_references()
            if br.source_id == "APP-p00001" and br.edge_kind == EdgeKind.SATISFIES.value
        ]
        assert brs, (
            "expected a broken-ref for APP-p00001 satisfies EVS-p00001; "
            f"got {[(b.source_id, b.target_id, b.edge_kind) for b in fed.unresolved_references()]}"
        )
        diag = brs[0].diagnostic
        assert "EVS-p00001" in diag, f"target ID missing from diagnostic: {diag!r}"
        assert "[associates" in diag, f"[associates hint missing: {diag!r}"
        assert ".elspais.toml" in diag, f".elspais.toml hint missing: {diag!r}"
        assert "No associates declared" in diag, (
            f"expected 'No associates declared' phrasing when no associates exist: {diag!r}"
        )

    def test_missing_associate_diagnostic_with_other_associates(self, tmp_path: Path) -> None:
        """When other associates exist, diagnostic names them.

        The library is declared as an associate. The app's Satisfies points
        at a DIFFERENT namespace (``EVS``) that no associate covers, so the
        diagnostic must still fire — but now list the ``LIB`` namespace as
        available to clarify what IS declared. A member is named by its
        namespace (REQ-d00202-G), so that is what the diagnostic offers.
        """
        library = _make_library(tmp_path)
        del library  # only the side-effect (writing the library repo) matters
        app = tmp_path / "app"
        app.mkdir()
        _write(
            app,
            ".elspais.toml",
            """
            version = 5
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
            for br in fed.unresolved_references()
            if br.source_id == "APP-p00001" and br.edge_kind == EdgeKind.SATISFIES.value
        ]
        assert brs, (
            "expected a broken-ref for APP-p00001 satisfies EVS-p00001; "
            f"got {[(b.source_id, b.target_id, b.edge_kind) for b in fed.unresolved_references()]}"
        )
        diag = brs[0].diagnostic
        assert "EVS-p00001" in diag, f"target ID missing from diagnostic: {diag!r}"
        assert "LIB" in diag, f"available associate namespace missing: {diag!r}"
        assert "[associates" in diag, f"[associates hint missing: {diag!r}"
        assert ".elspais.toml" in diag, f".elspais.toml hint missing: {diag!r}"

    def test_satisfies_cycle_emits_broken_ref(self, tmp_path: Path) -> None:
        """Two repos whose templates satisfy each other form a cycle.

        Federated build walks SATISFIES then INSTANCE edges; when DFS
        re-enters a node already on the path, a typed ReferenceFault with
        ``cycle`` in its diagnostic is emitted (one per build).

        ``_satisfies_cycle_federation`` assembles the federation by hand
        from bare per-repo builds, bypassing the on-disk
        transitive-associates guard so we can construct a topology that the
        standard CLI path would refuse to load. This is the same pattern as
        ``test_two_satisfiers_get_independent_clones``.
        """
        fed = _satisfies_cycle_federation(tmp_path)

        brs = list(fed.unresolved_references())
        cycle_brs = [br for br in brs if "cycle" in br.diagnostic.lower()]
        assert cycle_brs, (
            f"expected a cycle diagnostic, got: "
            f"{[(b.source_id, b.target_id, b.diagnostic) for b in brs]}"
        )

    # Verifies: REQ-d00204-K, REQ-d00200-J
    def test_REQ_d00204_K_satisfies_cycle_reported_once_across_check_runs(
        self, tmp_path: Path
    ) -> None:
        """Running the health checks again does not repeat the cycle fault."""
        from elspais.commands.health import run_spec_checks

        fed = _satisfies_cycle_federation(tmp_path)
        config = next(iter(fed.iter_repos())).config

        def cycles() -> list:
            return [br for br in fed.unresolved_references() if "cycle" in br.diagnostic.lower()]

        assert len(cycles()) == 1
        for _ in range(3):
            run_spec_checks(fed, config)
            assert len(cycles()) == 1


# ---------------------------------------------------------------------------
# A template subtree owned by the library (REQ-p00014-H, -M)
# ---------------------------------------------------------------------------


def _make_library_with_subtree(tmp_path: Path) -> Path:
    """Build a ``library`` repo whose template LIB-p00001 is refined by LIB-p00002."""
    library = tmp_path / "library"
    library.mkdir()
    _write(
        library,
        ".elspais.toml",
        """
        version = 5
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

        # LIB-p00002: Dispatch Authorization

        **Level**: PRD | **Status**: Approved | **Template**
        **Refines**: LIB-p00001

        ### Assertions

        A. SHALL authorize.

        *End* *Dispatch Authorization*
        """,
    )
    _git_init(library)
    return library


class TestCrossRepoSubtreeClone:
    """A library template refined by a library template is cloned whole."""

    @staticmethod
    def _federation(tmp_path: Path) -> FederatedGraph:
        _make_library_with_subtree(tmp_path)
        app = _make_app(tmp_path)
        return build_graph(repo_root=app, scan_code=False, scan_tests=False)

    # Verifies: REQ-p00014-H
    def test_library_refiner_is_cloned_with_its_assertions(self, tmp_path: Path) -> None:
        fed = self._federation(tmp_path)
        faults = [(b.source_id, b.target_id, b.edge_kind) for b in fed.unresolved_references()]
        assert not faults, f"got broken refs: {faults}"
        for composite in (
            "APP-p00001::LIB-p00001",
            "APP-p00001::LIB-p00001-A",
            "APP-p00001::LIB-p00002",
            "APP-p00001::LIB-p00002-A",
        ):
            node = fed.find_by_id(composite)
            assert node is not None, f"expected {composite} in the app's index"
            assert node.get_field("stereotype") == Stereotype.INSTANCE
            assert node.get_field("template_repo") == "library"

    # Verifies: REQ-p00014-H, REQ-p00014-M
    def test_intra_subtree_refines_is_recreated_on_the_clones(self, tmp_path: Path) -> None:
        fed = self._federation(tmp_path)
        root_clone = fed.find_by_id("APP-p00001::LIB-p00001")
        assert root_clone is not None
        refines = [
            e.target.id for e in root_clone.iter_outgoing_edges() if e.kind == EdgeKind.REFINES
        ]
        assert refines == ["APP-p00001::LIB-p00002"]
        structures = [
            e.target.id for e in root_clone.iter_outgoing_edges() if e.kind == EdgeKind.STRUCTURES
        ]
        assert structures == ["APP-p00001::LIB-p00001-A"], (
            "one STRUCTURES edge per cloned assertion"
        )

    # Verifies: REQ-p00014-H
    def test_refiner_clone_crosses_to_its_own_original(self, tmp_path: Path) -> None:
        fed = self._federation(tmp_path)
        refiner_clone = fed.find_by_id("APP-p00001::LIB-p00002")
        assert refiner_clone is not None
        assert not refiner_clone.get_field("refines_refs")
        instance = [
            e.target.id for e in refiner_clone.iter_outgoing_edges() if e.kind == EdgeKind.INSTANCE
        ]
        assert instance == ["LIB-p00002"]

    # Verifies: REQ-p00014-H
    def test_defines_reaches_every_clone_of_the_subtree(self, tmp_path: Path) -> None:
        fed = self._federation(tmp_path)
        declaring = fed.find_by_id("APP-p00001")
        assert declaring is not None
        declaring_file = declaring.file_node()
        assert declaring_file is not None
        defines = {
            e.target.id for e in declaring_file.iter_outgoing_edges() if e.kind == EdgeKind.DEFINES
        }
        assert {
            "APP-p00001::LIB-p00001",
            "APP-p00001::LIB-p00001-A",
            "APP-p00001::LIB-p00002",
            "APP-p00001::LIB-p00002-A",
        } <= defines


# ---------------------------------------------------------------------------
# A template subtree spanning repositories (REQ-p00014-G, -O)
# ---------------------------------------------------------------------------

_APP_CONFIG = """
version = 5
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
"""


def _make_app_refining_library(tmp_path: Path, refiner_marker: str, reference: str) -> Path:
    """Build an ``app`` repo where APP-p00001 satisfies LIB-p00001 and APP-p00002 refines it.

    ``refiner_marker`` is the metadata tail of APP-p00002 (``| **Template**``
    or nothing) and ``reference`` the spelling of its ``Refines:`` target.
    """
    app = tmp_path / "app"
    app.mkdir()
    _write(app, ".elspais.toml", _APP_CONFIG)
    _write(
        app,
        "spec/prd-app.md",
        f"""
        # APP-p00001: Concrete Action

        **Level**: PRD | **Status**: Approved
        **Satisfies**: LIB-p00001

        ### Assertions

        A. SHALL be sponsor-specific.

        *End* *Concrete Action*

        # APP-p00002: App Provision

        **Level**: PRD | **Status**: Approved{refiner_marker}
        **Refines**: {reference}

        ### Assertions

        A. SHALL provide.

        *End* *App Provision*
        """,
    )
    _git_init(app)
    return app


class TestCrossRepoRefinesMatrix:
    """The validation matrix judges a target in an associated repository."""

    # Verifies: REQ-p00014-G, REQ-d00269-B
    @pytest.mark.parametrize(
        ("reference", "refused"),
        [
            ("LIB-p00001", ["LIB-p00001"]),
            ("LIB-p00001-A+B", ["LIB-p00001-A", "LIB-p00001-B"]),
        ],
    )
    def test_concrete_refiner_of_foreign_template_is_refused(
        self, tmp_path: Path, reference: str, refused: list[str]
    ) -> None:
        """A refused reference is reported per expanded label, as the in-repo builder does."""
        _make_library(tmp_path)
        app = _make_app_refining_library(tmp_path, "", reference)
        fed = build_graph(repo_root=app, scan_code=False, scan_tests=False)

        faults = list(fed.unresolved_references())
        assert [(b.source_id, b.target_id, b.edge_kind, b.fault_class) for b in faults] == [
            ("APP-p00002", target, "refines", FaultClass.FORBIDDEN) for target in refused
        ]
        for fault in faults:
            assert "Mark APP-p00002 **Template**" in fault.diagnostic
            assert f"Satisfies: {fault.target_id}" in fault.diagnostic

        template = fed.find_by_id("LIB-p00001")
        assert template is not None
        assert not [e for e in template.iter_outgoing_edges() if e.kind == EdgeKind.REFINES], (
            "a refused reference never lands as an edge"
        )

    # Verifies: REQ-p00014-G, REQ-p00014-R
    def test_refused_and_missing_labels_of_one_item_are_each_reported(self, tmp_path: Path) -> None:
        """One item naming a refused label and a missing one keeps both faults.

        Each label reaches its own failure class: the label the library holds
        is refused by the matrix, the label it lacks is unknown -- not a
        class further along than it reached -- and the two are reported in
        the order the grammar expands them.
        """
        _make_library(tmp_path)
        app = _make_app_refining_library(tmp_path, "", "LIB-p00001-A+Z")
        fed = build_graph(repo_root=app, scan_code=False, scan_tests=False)

        faults = list(fed.unresolved_references())
        assert [(b.source_id, b.target_id, b.edge_kind, b.fault_class) for b in faults] == [
            ("APP-p00002", "LIB-p00001-A", "refines", FaultClass.FORBIDDEN),
            ("APP-p00002", "LIB-p00001-Z", "refines", FaultClass.UNKNOWN_ASSERTION),
        ]
        assert "Mark APP-p00002 **Template**" in faults[0].diagnostic
        assert "LIB-p00001-A+Z" in faults[1].diagnostic

        template = fed.find_by_id("LIB-p00001")
        assert template is not None
        assert not [e for e in template.iter_outgoing_edges() if e.kind == EdgeKind.REFINES], (
            "a refused reference never lands as an edge"
        )

    # Verifies: REQ-p00014-G, REQ-p00014-O
    def test_template_refiner_of_foreign_template_joins_its_subtree(self, tmp_path: Path) -> None:
        """A template in one repository refining a template in another forms one subtree.

        The clone of each member records the repository owning that member's
        own original, not the root's.
        """
        _make_library(tmp_path)
        app = _make_app_refining_library(tmp_path, " | **Template**", "LIB-p00001")
        fed = build_graph(repo_root=app, scan_code=False, scan_tests=False)

        assert not list(fed.unresolved_references())
        template = fed.find_by_id("LIB-p00001")
        assert template is not None
        assert [
            e.target.id for e in template.iter_outgoing_edges() if e.kind == EdgeKind.REFINES
        ] == ["APP-p00002"]

        provenance = {
            composite: fed.find_by_id(composite).get_field("template_repo")
            for composite in (
                "APP-p00001::LIB-p00001",
                "APP-p00001::LIB-p00001-A",
                "APP-p00001::APP-p00002",
                "APP-p00001::APP-p00002-A",
            )
        }
        assert provenance == {
            "APP-p00001::LIB-p00001": "library",
            "APP-p00001::LIB-p00001-A": "library",
            "APP-p00001::APP-p00002": "app",
            "APP-p00001::APP-p00002-A": "app",
        }


# ---------------------------------------------------------------------------
# One verdict on a Satisfies: target, wherever the declaring requirement lives
# ---------------------------------------------------------------------------

_LIBRARY_CONFIG = """
version = 5
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
"""

# The declaring requirements each repository holds, by component number,
# with the metadata line naming their target. Both repositories carry the
# same set, so the one-repository builder judges the library's and the
# federation judges the app's.
_DECLARERS = {
    11: "**Satisfies**: LIB-p00002",
    12: "**Satisfies**: LIB-p00001-B",
    13: "**Implements**: LIB-p00001-B",
    14: "**Satisfies**: LIB-p00001",
    15: "**Satisfies**: LIB-p00001-A",
}


def _copy_name_declarers(namespace: str) -> dict[int, str]:
    """Declarers whose item is spelled ``<declaring>::<original>``.

    17 and 20 name the copy ``{namespace}-p00014`` made of LIB-p00001 in its
    own repository; 18 and 19 name nothing the graph holds.
    """
    return {
        17: f"**Satisfies**: {namespace}-p00014::LIB-p00001",
        18: f"**Satisfies**: {namespace}-p00099::LIB-p00001",
        19: "**Satisfies**: foo::bar",
        20: f"**Implements**: {namespace}-p00014::LIB-p00001",
    }


def _declarers(namespace: str, declarers: dict[int, str] = _DECLARERS) -> str:
    """Spell one requirement per ``declarers`` entry in ``namespace``."""
    return "\n".join(
        f"""
        # {namespace}-p000{number}: Declarer {number}

        **Level**: PRD | **Status**: Approved
        {metadata}

        ### Assertions

        A. SHALL declare {number}.

        *End* *Declarer {number}*
        """
        for number, metadata in declarers.items()
    )


@pytest.fixture(scope="module")
def retired_template_federation(tmp_path_factory: pytest.TempPathFactory) -> FederatedGraph:
    """A library holding a template with a retired *Assertion*, and an app.

    LIB-p00001 is a **Template** whose *Assertion* B carries the RETIRED
    directive; LIB-p00002 is concrete. The library and the app each hold the
    declarers of ``_DECLARERS`` and of ``_copy_name_declarers``; the app
    also satisfies (16) and implements (21), by its name, the copy of the
    template LIB-p00014 makes in the library.
    """
    root = tmp_path_factory.mktemp("retired")
    library = root / "library"
    library.mkdir()
    _write(library, ".elspais.toml", _LIBRARY_CONFIG)
    _write(
        library,
        "spec/prd-library.md",
        """
        # LIB-p00001: Action Dispatch

        **Level**: PRD | **Status**: Approved | **Template**

        ### Assertions

        A. SHALL parse.

        B. <RETIRED> SHALL deny duplicate submissions.

        *End* *Action Dispatch*

        # LIB-p00002: Plain Concrete

        **Level**: PRD | **Status**: Approved

        ### Assertions

        A. SHALL hold.

        *End* *Plain Concrete*
        """
        + _declarers("LIB", {**_DECLARERS, **_copy_name_declarers("LIB")}),
    )
    _git_init(library)

    app = root / "app"
    app.mkdir()
    _write(app, ".elspais.toml", _APP_CONFIG)
    _write(
        app,
        "spec/prd-app.md",
        _declarers(
            "APP",
            {
                **_DECLARERS,
                16: "**Satisfies**: LIB-p00014::LIB-p00001",
                **_copy_name_declarers("APP"),
                21: "**Implements**: LIB-p00014::LIB-p00001",
            },
        ),
    )
    _git_init(app)
    return build_graph(repo_root=app, scan_code=False, scan_tests=False)


def _faults_of(fed: FederatedGraph, source_id: str) -> list[tuple[str, str, FaultClass, str]]:
    """The faults ``source_id`` declared, as comparable tuples."""
    return [
        (b.target_id, b.edge_kind, b.fault_class, b.diagnostic)
        for b in fed.unresolved_references()
        if b.source_id == source_id
    ]


# The library's declarers are judged by the one-repository builder, the app's
# by the federation's cross-repository pass.
_WHERE = pytest.mark.parametrize("namespace", ["LIB", "APP"], ids=["local", "cross-repo"])

# A ``Satisfies:`` declarer and an ``Implements:`` declarer spelling the same
# copy's name: a copy held in the declarers' own repository, or one another
# repository holds.
_COPY_NAMES = pytest.mark.parametrize(
    ("satisfier", "implementer", "copy_name"),
    [
        ("LIB-p00017", "LIB-p00020", "LIB-p00014::LIB-p00001"),
        ("APP-p00017", "APP-p00020", "APP-p00014::LIB-p00001"),
        ("APP-p00016", "APP-p00021", "LIB-p00014::LIB-p00001"),
    ],
    ids=["local", "cross-repo", "held-by-another-repository"],
)


def _copy_name_diagnostic(copy_name: str) -> str:
    """The diagnostic a reference spelling ``copy_name`` (a copy of LIB-p00001) carries."""
    return (
        f"{copy_name} is the name the tool gives a copy of LIB-p00001, and a "
        "copy's name is not an identifier a reference can carry. "
        "Name LIB-p00001 instead."
    )


class TestSatisfiesTargetVerdict:
    """Both instantiation paths judge a ``Satisfies:`` target by one rule."""

    # Verifies: REQ-p00014-G+R, REQ-d00272-A
    @_WHERE
    def test_non_template_target_is_forbidden_and_not_cloned(
        self, retired_template_federation: FederatedGraph, namespace: str
    ) -> None:
        declarer = f"{namespace}-p00011"
        assert _faults_of(retired_template_federation, declarer) == [
            (
                "LIB-p00002",
                "satisfies",
                FaultClass.FORBIDDEN,
                "LIB-p00002 is not marked **Template**; mark LIB-p00002 with "
                "**Template** if it's intended to be satisfiable.",
            )
        ]
        assert retired_template_federation.find_by_id(f"{declarer}::LIB-p00002") is None

    # Verifies: REQ-p00017-H, REQ-d00272-S
    @_WHERE
    def test_retired_assertion_target_is_an_unknown_assertion(
        self, retired_template_federation: FederatedGraph, namespace: str
    ) -> None:
        """A retired *Assertion* is not cloned and is reported as absent.

        The class and the diagnostic are those an ``Implements:`` of the same
        *Assertion* from the same repository reaches.
        """
        satisfier = _faults_of(retired_template_federation, f"{namespace}-p00012")
        implementer = _faults_of(retired_template_federation, f"{namespace}-p00013")

        assert [(t, k, c) for t, k, c, _d in satisfier] == [
            ("LIB-p00001-B", "satisfies", FaultClass.UNKNOWN_ASSERTION)
        ]
        assert [(t, k, c) for t, k, c, _d in implementer] == [
            ("LIB-p00001-B", "implements", FaultClass.UNKNOWN_ASSERTION)
        ]
        assert satisfier[0][3] == implementer[0][3]
        assert retired_template_federation.find_by_id(f"{namespace}-p00012::LIB-p00001-B") is None

    # Verifies: REQ-p00014-B+H
    @_WHERE
    @pytest.mark.parametrize(
        ("number", "clones"),
        [
            (14, ["LIB-p00001", "LIB-p00001-A"]),
            (15, ["LIB-p00001-A"]),
        ],
        ids=["template", "live-assertion"],
    )
    def test_live_template_target_is_cloned_without_fault(
        self,
        retired_template_federation: FederatedGraph,
        namespace: str,
        number: int,
        clones: list[str],
    ) -> None:
        declarer = f"{namespace}-p000{number}"
        assert _faults_of(retired_template_federation, declarer) == []
        for original in clones:
            clone = retired_template_federation.find_by_id(f"{declarer}::{original}")
            assert clone is not None, f"expected {declarer}::{original} to be cloned"
            assert clone.get_field("stereotype") == Stereotype.INSTANCE

    # Verifies: REQ-d00272-A+K+T, REQ-d00212-S
    @_COPY_NAMES
    def test_copy_name_is_malformed_and_names_the_original(
        self,
        retired_template_federation: FederatedGraph,
        satisfier: str,
        implementer: str,
        copy_name: str,
    ) -> None:
        """A ``Satisfies:`` spelling a copy's name is malformed and names the original.

        The answer is the same wherever the copy is held: in the declarer's own
        repository (made by the one-repository builder for the library, by the
        federation's cross-repository pass for the app) or in another one.
        """
        assert retired_template_federation.find_by_id(copy_name) is not None
        faults = [
            b
            for b in retired_template_federation.unresolved_references()
            if b.source_id == satisfier
        ]
        assert [(b.target_id, b.edge_kind, b.fault_class) for b in faults] == [
            (copy_name, "satisfies", FaultClass.MALFORMED)
        ]
        assert "E_NOT_AN_IDENTIFIER" in faults[0].codes
        assert faults[0].diagnostic == _copy_name_diagnostic(copy_name)
        assert retired_template_federation.find_by_id(f"{satisfier}::{copy_name}") is None
        assert retired_template_federation.find_by_id(f"{satisfier}::LIB-p00001") is None

    # Verifies: REQ-d00272-T
    @_WHERE
    @pytest.mark.parametrize(
        ("number", "target"),
        [(18, "{namespace}-p00099::LIB-p00001"), (19, "foo::bar")],
        ids=["absent-declarer", "not-an-identifier"],
    )
    def test_composite_naming_no_held_copy_has_no_diagnostic(
        self,
        retired_template_federation: FederatedGraph,
        namespace: str,
        number: int,
        target: str,
    ) -> None:
        """Only a copy the graph holds under exactly that text is answered."""
        faults = [
            b
            for b in retired_template_federation.unresolved_references()
            if b.source_id == f"{namespace}-p000{number}"
        ]
        assert [(b.target_id, b.edge_kind, b.fault_class, b.diagnostic) for b in faults] == [
            (target.format(namespace=namespace), "satisfies", FaultClass.MALFORMED, "")
        ]
        assert "E_NOT_AN_IDENTIFIER" in faults[0].codes

    # Verifies: REQ-d00272-A+K+T, REQ-d00212-S
    @_COPY_NAMES
    def test_implements_of_a_copy_name_names_the_original(
        self,
        retired_template_federation: FederatedGraph,
        satisfier: str,
        implementer: str,
        copy_name: str,
    ) -> None:
        """Every keyword's malformed item naming a held copy gets the same answer.

        The app's own copy is made by the cross-repository pass, after the
        app's own build has already reported the item; the library's copy is
        held by another repository and wires no edge to it.
        """
        faults = [
            b
            for b in retired_template_federation.unresolved_references()
            if b.source_id == implementer
        ]
        assert [(b.target_id, b.edge_kind, b.fault_class) for b in faults] == [
            (copy_name, "implements", FaultClass.MALFORMED)
        ]
        assert "E_NOT_AN_IDENTIFIER" in faults[0].codes
        assert faults[0].diagnostic == _copy_name_diagnostic(copy_name)
        node = retired_template_federation.find_by_id(implementer)
        assert node is not None
        edges = [*node.iter_incoming_edges(), *node.iter_outgoing_edges()]
        assert [e for e in edges if e.kind == EdgeKind.IMPLEMENTS] == []


# ---------------------------------------------------------------------------
# Compaction judges the references another member holds
# ---------------------------------------------------------------------------


def _draft_template_federation(tmp_path: Path, cited_label: str) -> FederatedGraph:
    """Federate a Draft **Template** LIB-p00001 (A/B/C) with an app citing one label.

    APP-p00002 is concrete, so the matrix refuses its ``Refines:`` of the
    library's template: the reference stays unresolved in the app's graph
    and never becomes an edge the library's graph can see.
    """
    library = tmp_path / "library"
    library.mkdir()
    _write(library, ".elspais.toml", _LIBRARY_CONFIG)
    _write(
        library,
        "spec/prd-library.md",
        """
        # LIB-p00001: Action Dispatch

        **Level**: PRD | **Status**: Draft | **Template**

        ### Assertions

        A. SHALL parse.

        B. SHALL authorize.

        C. SHALL log.

        *End* *Action Dispatch*
        """,
    )
    _git_init(library)
    app = tmp_path / "app"
    app.mkdir()
    _write(app, ".elspais.toml", _APP_CONFIG)
    _write(
        app,
        "spec/prd-app.md",
        f"""
        # APP-p00002: App Provision

        **Level**: PRD | **Status**: Approved
        **Refines**: LIB-p00001-{cited_label}

        ### Assertions

        A. SHALL provide.

        *End* *App Provision*
        """,
    )
    _git_init(app)
    return build_graph(repo_root=app, scan_code=False, scan_tests=False)


def _assertion_texts(fed: FederatedGraph) -> dict[str, str]:
    return {
        label: fed.find_by_id(f"LIB-p00001-{label}").get_label()
        for label in "ABC"
        if fed.find_by_id(f"LIB-p00001-{label}") is not None
    }


def _app_faults(fed: FederatedGraph) -> list[tuple[str, str, FaultClass]]:
    return [
        (f.source_id, f.target_id, f.fault_class)
        for f in fed.unresolved_references()
        if f.source_id == "APP-p00002"
    ]


class TestCompactionJudgesForeignReferences:
    """Removing a provisional requirement's *Assertion* renumbers the later
    ones, so a reference another member holds -- even one the federation
    refused to wire -- would come to designate something else."""

    # Verifies: REQ-p00017-M
    @pytest.mark.parametrize("cited", ["A", "B"], ids=["removed", "moved"])
    def test_foreign_unresolved_reference_refuses_compaction(
        self, tmp_path: Path, cited: str
    ) -> None:
        """The refusal names the citing requirement where it is written and
        the identifier it cites, and nothing changes."""
        from elspais.graph.builder import DeletionWouldRepointError

        fed = _draft_template_federation(tmp_path, cited)
        texts_before = _assertion_texts(fed)
        faults_before = _app_faults(fed)
        assert faults_before == [("APP-p00002", f"LIB-p00001-{cited}", FaultClass.FORBIDDEN)]

        with pytest.raises(DeletionWouldRepointError) as excinfo:
            fed.delete_assertion("LIB-p00001-A")

        message = str(excinfo.value)
        assert "APP-p00002 (spec/prd-app.md:1)" in message, message
        assert "location unknown" not in message, message
        assert f"cites LIB-p00001-{cited}" in message, message

        assert (
            _assertion_texts(fed)
            == texts_before
            == {
                "A": "SHALL parse.",
                "B": "SHALL authorize.",
                "C": "SHALL log.",
            }
        )
        assert len(fed.mutation_log) == 0
        assert list(fed.mutation_log.iter_entries()) == []
        assert _app_faults(fed) == faults_before

    # Verifies: REQ-p00017-L, REQ-p00017-M
    def test_foreign_reference_to_an_unmoved_assertion_does_not_refuse(
        self, tmp_path: Path
    ) -> None:
        """Removing the last *Assertion* moves nothing, so a foreign reference
        to an earlier one still designates what it named and the removal
        proceeds."""
        fed = _draft_template_federation(tmp_path, "A")

        entry = fed.delete_assertion("LIB-p00001-C")

        assert entry.before_state.get("disposition") == "removed"
        assert fed.find_by_id("LIB-p00001-C") is None
        assert _assertion_texts(fed) == {"A": "SHALL parse.", "B": "SHALL authorize."}
        assert len(fed.mutation_log) == 1
