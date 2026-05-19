# Verifies: REQ-d00242-A+B+C
"""Tests for terms API endpoints (/api/terms, /api/term/{key})."""

from __future__ import annotations

from pathlib import Path

from starlette.testclient import TestClient

from elspais.graph import GraphNode, NodeKind
from elspais.graph.builder import TraceGraph
from elspais.graph.federated import FederatedGraph, RepoEntry
from elspais.graph.relations import EdgeKind
from elspais.graph.terms import TermDictionary, TermEntry, TermRef
from elspais.server.app import create_app
from elspais.server.state import AppState

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

LONG_DEFINITION = (
    "This is a very long definition that exceeds one hundred and fifty characters "
    "in order to test that the API correctly truncates the definition_short field "
    "and appends an ellipsis suffix to indicate truncation occurred."
)
assert len(LONG_DEFINITION) > 150  # sanity check


def _make_app(tmp_path: Path) -> TestClient:
    """Create a test app with a graph containing terms."""
    graph = TraceGraph(repo_root=tmp_path)

    # Create a FILE node
    file_node = GraphNode(id="file:spec/glossary.md", kind=NodeKind.FILE)
    file_node.set_field("relative_path", "spec/glossary.md")
    file_node.set_field("absolute_path", str(tmp_path / "spec" / "glossary.md"))

    # Create a requirement node (for node_title resolution)
    req = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT)
    req.set_field("title", "Authentication Module")
    file_node.link(req, EdgeKind.CONTAINS)

    graph._index["file:spec/glossary.md"] = file_node
    graph._index["REQ-p00001"] = req
    graph._roots.append(file_node)

    # Build federated graph
    repos = [RepoEntry(name="root", graph=graph, config={}, repo_root=tmp_path)]
    federated = FederatedGraph(repos)

    # Populate terms dictionary
    terms = TermDictionary()
    terms.add(
        TermEntry(
            term="Bearer Token",
            definition=LONG_DEFINITION,
            collection=True,
            indexed=True,
            defined_in="REQ-p00001",
            namespace="root",
            references=[
                TermRef(node_id="REQ-p00001", namespace="root", marked=True, line=10),
                TermRef(node_id="REQ-p00001", namespace="root", marked=False, line=25),
            ],
        )
    )
    terms.add(
        TermEntry(
            term="API Gateway",
            definition="A server that acts as a single entry point.",
            collection=False,
            indexed=True,
            defined_in="REQ-p00001",
            namespace="root",
            references=[],
        )
    )
    federated._terms = terms

    state = AppState(graph=federated, repo_root=tmp_path, config={})
    app = create_app(state=state, mount_mcp=False)
    return TestClient(app)


# ---------------------------------------------------------------------------
# TestTermsListEndpoint (REQ-d00242-A)
# ---------------------------------------------------------------------------


class TestTermsListEndpoint:
    """Validates REQ-d00242-A: GET /api/terms returns sorted term list with
    summary fields."""

    def test_REQ_d00242_A_returns_sorted_terms(self, tmp_path: Path) -> None:
        """GET /api/terms returns terms sorted alphabetically by term name."""
        client = _make_app(tmp_path)
        resp = client.get("/api/terms")
        assert resp.status_code == 200
        data = resp.json()
        terms = data if isinstance(data, list) else data.get("terms", data)
        assert len(terms) == 2
        # "API Gateway" before "Bearer Token" alphabetically
        assert terms[0]["term"] == "API Gateway"
        assert terms[1]["term"] == "Bearer Token"

    def test_REQ_d00242_A_term_fields(self, tmp_path: Path) -> None:
        """Each term object has all required summary fields."""
        client = _make_app(tmp_path)
        resp = client.get("/api/terms")
        assert resp.status_code == 200
        data = resp.json()
        terms = data if isinstance(data, list) else data.get("terms", data)
        required_fields = {
            "term",
            "key",
            "definition_short",
            "defined_in",
            "namespace",
            "collection",
            "indexed",
            "ref_count",
        }
        for t in terms:
            missing = required_fields - set(t.keys())
            assert not missing, f"Missing fields: {missing}"

    def test_REQ_d00242_A_definition_short_truncated(self, tmp_path: Path) -> None:
        """definition_short is truncated to 150 chars with '...' suffix for long defs."""
        client = _make_app(tmp_path)
        resp = client.get("/api/terms")
        assert resp.status_code == 200
        data = resp.json()
        terms = data if isinstance(data, list) else data.get("terms", data)
        # Find "Bearer Token" which has LONG_DEFINITION
        bearer = next(t for t in terms if t["term"] == "Bearer Token")
        assert len(bearer["definition_short"]) <= 153  # 150 + "..."
        assert bearer["definition_short"].endswith("...")
        # "API Gateway" has a short definition -- not truncated
        api_gw = next(t for t in terms if t["term"] == "API Gateway")
        assert api_gw["definition_short"] == "A server that acts as a single entry point."

    def test_REQ_d00242_A_ref_count(self, tmp_path: Path) -> None:
        """ref_count matches number of references for each term."""
        client = _make_app(tmp_path)
        resp = client.get("/api/terms")
        assert resp.status_code == 200
        data = resp.json()
        terms = data if isinstance(data, list) else data.get("terms", data)
        bearer = next(t for t in terms if t["term"] == "Bearer Token")
        assert bearer["ref_count"] == 2
        api_gw = next(t for t in terms if t["term"] == "API Gateway")
        assert api_gw["ref_count"] == 0

    def test_REQ_d00242_A_empty_dictionary(self, tmp_path: Path) -> None:
        """Empty TermDictionary returns []."""
        graph = TraceGraph(repo_root=tmp_path)
        repos = [RepoEntry(name="root", graph=graph, config={}, repo_root=tmp_path)]
        federated = FederatedGraph(repos)
        federated._terms = TermDictionary()
        state = AppState(graph=federated, repo_root=tmp_path, config={})
        app = create_app(state=state, mount_mcp=False)
        client = TestClient(app)
        resp = client.get("/api/terms")
        assert resp.status_code == 200
        data = resp.json()
        terms = data if isinstance(data, list) else data.get("terms", data)
        assert terms == []


# ---------------------------------------------------------------------------
# TestTermDetailEndpoint (REQ-d00242-B)
# ---------------------------------------------------------------------------


class TestTermDetailEndpoint:
    """Validates REQ-d00242-B: GET /api/term/{term_key} returns full detail
    with definition, references, and resolved node_title."""

    def test_REQ_d00242_B_returns_full_detail(self, tmp_path: Path) -> None:
        """GET /api/term/{key} returns full term with all fields."""
        client = _make_app(tmp_path)
        resp = client.get("/api/term/bearer token")
        assert resp.status_code == 200
        data = resp.json()
        assert data["term"] == "Bearer Token"
        assert data["definition"] == LONG_DEFINITION
        assert data["defined_in"] == "REQ-p00001"
        assert data["namespace"] == "root"
        assert data["collection"] is True
        assert data["indexed"] is True
        assert isinstance(data["references"], list)
        assert len(data["references"]) == 2

    def test_REQ_d00242_B_references_include_node_title(self, tmp_path: Path) -> None:
        """Each reference has node_title resolved from the graph."""
        client = _make_app(tmp_path)
        resp = client.get("/api/term/bearer token")
        assert resp.status_code == 200
        data = resp.json()
        for ref in data["references"]:
            assert "node_title" in ref
            # REQ-p00001 has title "Authentication Module"
            assert ref["node_title"] == "Authentication Module"

    def test_REQ_d00242_B_reference_fields(self, tmp_path: Path) -> None:
        """Each reference has all required fields."""
        client = _make_app(tmp_path)
        resp = client.get("/api/term/bearer token")
        assert resp.status_code == 200
        data = resp.json()
        required_fields = {"node_id", "node_title", "namespace", "marked", "line"}
        for ref in data["references"]:
            missing = required_fields - set(ref.keys())
            assert not missing, f"Missing ref fields: {missing}"


# ---------------------------------------------------------------------------
# TestTermNotFound (REQ-d00242-C)
# ---------------------------------------------------------------------------


class TestTermNotFound:
    """Validates REQ-d00242-C: GET /api/term/{nonexistent} returns 404."""

    def test_REQ_d00242_C_nonexistent_returns_404(self, tmp_path: Path) -> None:
        """GET /api/term/nonexistent returns 404."""
        client = _make_app(tmp_path)
        resp = client.get("/api/term/nonexistent")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# TestTermRepoNameAndPath (REQ-d00242-B / CUR-1357 disambiguation fields)
# ---------------------------------------------------------------------------


def _make_federated_app(tmp_path: Path) -> TestClient:
    """Build a two-repo federation with terms in the associate repo.

    Mirrors ``_make_app`` but with a separate ``assoc`` RepoEntry whose
    graph owns a FILE node (``file:spec/glossary.md``) and a REQUIREMENT
    node (``REQ-a00001``). Both nodes carry term definitions exercising
    the two ``defined_in_path`` resolution branches (FILE vs non-FILE)
    and the ``repo_name`` stamping done by ``_merge_terms``.
    """
    core_root = tmp_path / "core"
    assoc_root = tmp_path / "assoc"
    core_root.mkdir()
    assoc_root.mkdir()

    # --- core repo: empty graph + terms dict (no terms in core) -----------
    core_graph = TraceGraph(repo_root=core_root)

    # --- assoc repo: FILE node + REQUIREMENT node, both with terms -------
    assoc_graph = TraceGraph(repo_root=assoc_root)
    file_node = GraphNode(id="file:spec/glossary.md", kind=NodeKind.FILE)
    file_node.set_field("relative_path", "spec/glossary.md")
    file_node.set_field("absolute_path", str(assoc_root / "spec" / "glossary.md"))

    req_node = GraphNode(id="REQ-a00001", kind=NodeKind.REQUIREMENT)
    req_node.set_field("title", "Assoc Requirement")
    # CONTAINS edge so ``req_node.file_node()`` resolves to the FILE.
    file_node.link(req_node, EdgeKind.CONTAINS)

    assoc_graph._index["file:spec/glossary.md"] = file_node
    assoc_graph._index["REQ-a00001"] = req_node
    assoc_graph._roots.append(file_node)

    # Populate the assoc graph's per-repo term dict; ``_merge_terms`` will
    # stamp ``repo_name`` from the RepoEntry.name and merge into the
    # federated dictionary.
    assoc_graph._terms.add(
        TermEntry(
            term="OAuth2",
            definition="An open standard for access delegation.",
            collection=False,
            indexed=True,
            defined_in="file:spec/glossary.md",  # FILE id branch
            defined_at_line=42,
            namespace="assoc",
        )
    )
    assoc_graph._terms.add(
        TermEntry(
            term="Access Token",
            definition="A credential representing authorization to a resource.",
            collection=False,
            indexed=True,
            defined_in="REQ-a00001",  # non-FILE id → file_node() lookup
            defined_at_line=7,
            namespace="assoc",
        )
    )

    repos = [
        RepoEntry(name="core", graph=core_graph, config={}, repo_root=core_root),
        RepoEntry(name="assoc", graph=assoc_graph, config={}, repo_root=assoc_root),
    ]
    federated = FederatedGraph(repos)

    state = AppState(graph=federated, repo_root=core_root, config={})
    app = create_app(state=state, mount_mcp=False)
    return TestClient(app)


class TestTermRepoNameAndPath:
    """Validates CUR-1357 disambiguation fields on /api/term/{key}.

    The endpoint must surface:
      - ``repo_name`` — the owning federated RepoEntry.name, used by the
        viewer to disambiguate FILE-id collisions across repos.
      - ``defined_in_path`` — the resolved file path of the term's
        ``defined_in`` node (whether that node is a FILE itself or a
        REQUIREMENT whose enclosing FILE we navigate to via
        ``file_node()``).
      - ``defined_in_line`` — the ``defined_at_line`` recorded by the
        term scanner.

    Together these let the term-card open the correct file viewer
    without any node_id-based ambiguity.
    """

    # Verifies: REQ-d00242-B
    def test_api_term_returns_repo_name(self, tmp_path: Path) -> None:
        """repo_name matches the owning RepoEntry.name (stamped by _merge_terms)."""
        client = _make_federated_app(tmp_path)
        resp = client.get("/api/term/oauth2")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        # Stamped automatically by FederatedGraph._merge_terms from
        # RepoEntry(name="assoc").
        assert data["repo_name"] == "assoc"

    # Verifies: REQ-d00242-B
    def test_api_term_returns_defined_in_path_for_file_term(self, tmp_path: Path) -> None:
        """defined_in points at a FILE id → defined_in_path uses its relative_path."""
        client = _make_federated_app(tmp_path)
        resp = client.get("/api/term/oauth2")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["defined_in"] == "file:spec/glossary.md"
        assert data["defined_in_path"] == "spec/glossary.md"
        assert data["defined_in_line"] == 42

    # Verifies: REQ-d00242-B
    def test_api_term_returns_defined_in_path_for_req_term(self, tmp_path: Path) -> None:
        """defined_in is a REQUIREMENT id → defined_in_path follows file_node()."""
        client = _make_federated_app(tmp_path)
        resp = client.get("/api/term/access token")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["defined_in"] == "REQ-a00001"
        # REQ-a00001 is CONTAINS-linked from file:spec/glossary.md, so
        # file_node() resolves to that FILE and yields its relative_path.
        assert data["defined_in_path"] == "spec/glossary.md"
        assert data["defined_in_line"] == 7

    # Verifies: REQ-d00242-A
    def test_api_terms_list_includes_repo_name(self, tmp_path: Path) -> None:
        """/api/terms list endpoint also exposes repo_name on each entry."""
        client = _make_federated_app(tmp_path)
        resp = client.get("/api/terms")
        assert resp.status_code == 200, resp.text
        terms = resp.json()
        # Both terms originate from the assoc repo.
        assert {t["repo_name"] for t in terms} == {"assoc"}

    # Verifies: REQ-d00242-B
    def test_outer_federation_overwrites_stale_repo_name(self, tmp_path: Path) -> None:
        """Outer federation must overwrite repo_name stamped by an inner build.

        Regression for CUR-1357: when ``factory.build_graph`` builds an
        associate via an inner ``FederatedGraph.from_single`` first, the
        inner ``_merge_terms`` stamps every TermEntry with the associate's
        ``[project].name``. The host's outer federation then wraps the
        same TraceGraph under a *different* ``RepoEntry.name`` (the
        associate key, e.g. ``"hht_diary"``). The viewer's file-resolution
        path looks repos up by ``iter_repos()`` name; if ``term.repo_name``
        still holds the inner ``[project].name`` the lookup misses and the
        viewer opens whichever same-pathed file lives under the host root.
        """
        assoc_root = tmp_path / "assoc"
        assoc_root.mkdir()
        assoc_graph = TraceGraph(repo_root=assoc_root)
        file_node = GraphNode(id="file:spec/glossary.md", kind=NodeKind.FILE)
        file_node.set_field("relative_path", "spec/glossary.md")
        assoc_graph._index["file:spec/glossary.md"] = file_node
        assoc_graph._roots.append(file_node)
        # Pre-stamp with the *wrong* repo_name to simulate the associate
        # having been built through an inner FederatedGraph.from_single
        # first (which stamps using config["project"]["name"]).
        assoc_graph._terms.add(
            TermEntry(
                term="OAuth2",
                definition="An open standard for access delegation.",
                defined_in="file:spec/glossary.md",
                defined_at_line=1,
                namespace="assoc",
                repo_name="Inner Project Name",
            )
        )

        core_root = tmp_path / "core"
        core_root.mkdir()
        core_graph = TraceGraph(repo_root=core_root)
        repos = [
            RepoEntry(name="core", graph=core_graph, config={}, repo_root=core_root),
            RepoEntry(name="assoc", graph=assoc_graph, config={}, repo_root=assoc_root),
        ]
        federated = FederatedGraph(repos)

        merged = federated.terms.lookup("OAuth2")
        assert merged is not None
        # The outer RepoEntry.name ("assoc") wins, not the stale stamping.
        assert merged.repo_name == "assoc", (
            "outer _merge_terms must overwrite the stale repo_name "
            "left over from the associate's inner federation"
        )

    # Verifies: REQ-d00239-A
    def test_scan_terms_uses_req_namespace_not_repo_name(self, tmp_path: Path) -> None:
        """TermRef.namespace must be the REQ-prefix, not the host-side RepoEntry.name.

        Regression for CUR-1357: ``_scan_terms`` previously passed
        ``namespace=entry.name`` to ``scan_graph``, which stamped every
        discovered TermRef with the host-side RepoEntry handle (e.g.
        ``"hht_diary"``) instead of the REQ-id prefix
        (``[project].namespace``, e.g. ``"DIARY"``). The terms API
        surfaces ``ref.namespace`` to the viewer, so callers saw the
        wrong namespace label on every cross-repo term reference.
        """
        assoc_root = tmp_path / "assoc"
        assoc_root.mkdir()
        assoc_graph = TraceGraph(repo_root=assoc_root)
        # A REQUIREMENT whose text contains the term — scan_graph will
        # populate its references list.
        file_node = GraphNode(id="file:spec/prd.md", kind=NodeKind.FILE)
        file_node.set_field("relative_path", "spec/prd.md")
        file_node.set_field("file_type", "spec")
        req_node = GraphNode(id="REQ-a00001", kind=NodeKind.REQUIREMENT)
        req_node.set_label("uses *OAuth2* for authentication")
        req_node.set_field("parse_line", 1)
        file_node.link(req_node, EdgeKind.CONTAINS)
        assoc_graph._index["file:spec/prd.md"] = file_node
        assoc_graph._index["REQ-a00001"] = req_node
        assoc_graph._roots.append(file_node)
        assoc_graph._terms.add(
            TermEntry(
                term="OAuth2",
                definition="An open standard for access delegation.",
                defined_in="file:spec/prd.md",
                defined_at_line=1,
                namespace="ASSOC",
            )
        )

        core_root = tmp_path / "core"
        core_root.mkdir()
        repos = [
            RepoEntry(
                name="core",
                graph=TraceGraph(repo_root=core_root),
                config={"project": {"name": "core", "namespace": "CORE"}},
                repo_root=core_root,
            ),
            # RepoEntry.name ("assoc-key") deliberately differs from the
            # REQ-prefix namespace ("ASSOC") so the two cannot be confused.
            RepoEntry(
                name="assoc-key",
                graph=assoc_graph,
                config={"project": {"name": "Assoc Display Name", "namespace": "ASSOC"}},
                repo_root=assoc_root,
            ),
        ]
        federated = FederatedGraph(repos)

        merged = federated.terms.lookup("OAuth2")
        assert merged is not None
        assert len(merged.references) >= 1, "expected scan_graph to find *OAuth2*"
        # Every reference carries the REQ-prefix, not the host-side handle.
        namespaces = {ref.namespace for ref in merged.references}
        assert namespaces == {"ASSOC"}, (
            f"TermRef.namespace should be the REQ-prefix 'ASSOC', " f"got {namespaces!r}"
        )
