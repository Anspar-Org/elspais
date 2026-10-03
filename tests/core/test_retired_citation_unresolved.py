"""A citation of a retired Assertion is unresolved the moment it is retired.

A build binds nothing to an Assertion carrying the RETIRED directive and
reports every citation of it as an unresolved reference (REQ-p00017-H).
Retiring one in memory -- by deleting it from an active requirement, or by
rewriting its text to the directive -- has to leave the graph in the state a
build of the retired text produces, without a rebuild in between: the
citation edges go, the faults appear, the citing nodes take the standing a
build gives them, and a citing requirement keeps rendering what it wrote.
Undo restores everything, and bringing the Assertion back binds its
citations again.

Each test works on a throwaway copy of an on-disk fixture, because the
property is a comparison with what a build of the same text produces.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from elspais.graph.factory import build_graph
from elspais.graph.reference_faults import FaultClass
from elspais.graph.relations import EdgeKind
from elspais.graph.render import render_node, render_save

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"

# e2e-standard: REQ-d00001-A is cited by a requirement (once dev-refine.md
# names the label), by two code files (one naming A+B) and by a test.
CITED_REQ = "REQ-d00001"
RETIRED = "REQ-d00001-A"
RETIRED_LINE = "A. The module SHALL use bcrypt for hashing."
LIVE_TEXT = "The module SHALL use bcrypt for hashing."
CITING_REQ = "REQ-d00003"

# The citations of RETIRED, as (citing node, keyword), with code ids written
# relative to the project root.
CITATIONS = {
    (CITING_REQ, "refines"),
    ("code:src/auth.py:1", "implements"),
    ("code:src/auth_multi.py:1", "implements"),
    ("test:tests/test_auth.py::test_authenticate", "verifies"),
}

# e2e-associated: alpha's REQ-ALP-d00001 cites core's REQ-p00001-A once its
# Implements line names the label.
FED_CITED_REQ = "REQ-p00001"
FED_RETIRED = "REQ-p00001-A"
FED_RETIRED_LINE = "A. The platform SHALL authenticate users."
FED_LIVE_TEXT = "The platform SHALL authenticate users."
FED_CITING_REQ = "REQ-ALP-d00001"
ALPHA = "REQ-ALP"
CORE = "REQ"


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------


def _replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert text.count(old) == 1, f"fixture premise: {old!r} not once in {path.name}"
    path.write_text(text.replace(old, new), encoding="utf-8")


def _standard_project(tmp_path: Path, name: str = "repo", *, retired: bool = False) -> Path:
    """A copy of e2e-standard whose Refines names REQ-d00001-A."""
    root = tmp_path / name
    shutil.copytree(FIXTURES_DIR / "e2e-standard", root)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    _replace_once(
        root / "spec" / "dev-refine.md",
        f"**Refines**: {CITED_REQ}\n",
        f"**Refines**: {RETIRED}\n",
    )
    if retired:
        _replace_once(root / "spec" / "dev-impl.md", RETIRED_LINE, "A. <RETIRED>")
    return root


def _associated_project(tmp_path: Path, name: str = "fed", *, retired: bool = False) -> Path:
    """A copy of e2e-associated whose alpha requirement cites REQ-p00001-A.

    Returns the directory holding the three repositories; core is the root.
    """
    base = tmp_path / name
    shutil.copytree(FIXTURES_DIR / "e2e-associated", base)
    for repo in ("core", "alpha", "beta"):
        subprocess.run(["git", "init", "-q", str(base / repo)], check=True)
    _replace_once(
        base / "alpha" / "spec" / "dev-alpha.md",
        f"**Implements**: {FED_CITED_REQ}\n",
        f"**Implements**: {FED_RETIRED}\n",
    )
    if retired:
        _replace_once(base / "core" / "spec" / "prd-core.md", FED_RETIRED_LINE, "A. <RETIRED>")
    return base


def _build(root: Path):
    return build_graph(repo_root=root, config_path=root / ".elspais.toml")


def _retire(graph, assertion_id: str, how: str):
    """Retire *assertion_id* the way *how* names; return the mutation entry."""
    if how == "delete":
        return graph.delete_assertion(assertion_id)
    return graph.update_assertion(assertion_id, "<RETIRED>")


RETIREMENTS = pytest.mark.parametrize("how", ["delete", "update"], ids=["deleted", "edited"])


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


def _state(graph, base: Path, cited_id: str, citing_id: str) -> dict:
    """Everything a retirement changes, with *base* stripped from every id.

    Stripping the directory lets a graph built in one copy of a project be
    compared with one built in another.
    """
    prefix = f"{base}/"

    def rel(value):
        return value.replace(prefix, "") if isinstance(value, str) else value

    faults = sorted(
        (
            entry.namespace,
            rel(f.source_id),
            f.target_id,
            f.edge_kind,
            f.fault_class.name,
            rel(f.diagnostic),
        )
        for entry in graph.iter_repos()
        for f in entry.graph.unresolved_references()
    )
    cited = graph.find_by_id(cited_id)
    edges = sorted(
        (edge.kind.value, rel(edge.target.id), tuple(edge.assertion_targets))
        for edge in cited.iter_outgoing_edges()
        if edge.kind != EdgeKind.STRUCTURES
    )
    citing = graph.find_by_id(citing_id)
    return {
        "faults": faults,
        "edges": edges,
        "roots": sorted(rel(node.id) for node in graph.iter_roots()),
        "orphans": sorted(rel(node.id) for node in graph.orphaned_nodes()),
        "implements_refs": list(citing.get_field("implements_refs") or []),
        "refines_refs": list(citing.get_field("refines_refs") or []),
        "rendered": _render(graph, citing_id),
    }


def _render(graph, node_id: str) -> str:
    """*node_id* rendered under the grammar of the member holding it."""
    member = next(e.graph for e in graph.iter_repos() if e.graph.find_by_id(node_id))
    return render_node(member.find_by_id(node_id), resolver=member.resolver)


def _retired_faults(graph, root: Path, target: str) -> set[tuple[str, str, FaultClass]]:
    """The (citing node, keyword, class) of every fault naming *target*."""
    prefix = f"{root}/"
    return {
        (f.source_id.replace(prefix, ""), f.edge_kind, f.fault_class)
        for f in graph.unresolved_references()
        if f.target_id == target
    }


def _cited_by(graph, root: Path, cited_id: str) -> set[tuple[str, str, tuple[str, ...]]]:
    """(keyword, citing node, labels) of every citation edge *cited_id* holds."""
    prefix = f"{root}/"
    return {
        (edge.kind.value, edge.target.id.replace(prefix, ""), tuple(edge.assertion_targets))
        for edge in graph.find_by_id(cited_id).iter_outgoing_edges()
        if edge.kind != EdgeKind.STRUCTURES
    }


# ---------------------------------------------------------------------------
# One repository
# ---------------------------------------------------------------------------


class TestRetirementReportsEachCitation:
    """Validates REQ-p00017-H."""

    @RETIREMENTS
    # Verifies: REQ-p00017-H
    def test_REQ_p00017_H_each_citation_is_unresolved_without_a_rebuild(self, tmp_path, how):
        root = _standard_project(tmp_path)
        graph = _build(root)
        assert _retired_faults(graph, root, RETIRED) == set()

        _retire(graph, RETIRED, how)

        expected = {(citer, keyword, FaultClass.UNKNOWN_ASSERTION) for citer, keyword in CITATIONS}
        assert _retired_faults(graph, root, RETIRED) == expected
        # The citation naming A+B keeps its B; nothing else binds to the
        # requirement, and nothing was widened to the requirement as a whole.
        assert _cited_by(graph, root, CITED_REQ) == {
            ("implements", "code:src/auth_multi.py:1", ("B",))
        }
        # The citing requirement still says what it wrote.
        citing = graph.find_by_id(CITING_REQ)
        assert citing.get_field("refines_refs") == [RETIRED]
        assert f"**Refines**: {RETIRED}" in _render(graph, CITING_REQ)

    @RETIREMENTS
    # Verifies: REQ-p00017-H
    def test_REQ_p00017_H_retired_state_equals_a_rebuild_after_save(self, tmp_path, how):
        root = _standard_project(tmp_path)
        graph = _build(root)

        _retire(graph, RETIRED, how)
        in_memory = _state(graph, root, CITED_REQ, CITING_REQ)
        result = render_save(graph, repo_root=root)
        assert result["success"] is True, result.get("errors")
        rebuilt = _state(_build(root), root, CITED_REQ, CITING_REQ)

        assert in_memory == rebuilt
        assert "A. <RETIRED>" in (root / "spec" / "dev-impl.md").read_text(encoding="utf-8")


class TestUndoOfARetirement:
    """Validates REQ-o00062-G."""

    @RETIREMENTS
    @pytest.mark.parametrize("undo", ["undo_last", "undo_to"])
    # Verifies: REQ-o00062-G
    def test_REQ_o00062_G_undo_withdraws_the_findings_and_restores_the_edges(
        self, tmp_path, how, undo
    ):
        root = _standard_project(tmp_path)
        graph = _build(root)
        before = _state(graph, root, CITED_REQ, CITING_REQ)

        entry = _retire(graph, RETIRED, how)
        assert _state(graph, root, CITED_REQ, CITING_REQ) != before
        if undo == "undo_last":
            graph.undo_last()
        else:
            # A later mutation on top: undo_to unwinds both.
            graph.update_title("REQ-d00002", "Renamed Notification Service")
            graph.undo_to(entry.id)

        assert _state(graph, root, CITED_REQ, CITING_REQ) == before
        assert _retired_faults(graph, root, RETIRED) == set()


class TestBringingARetiredAssertionBack:
    """Validates REQ-p00017-H, REQ-o00062-G."""

    @pytest.mark.parametrize("origin", ["text", "mutation"], ids=["built-retired", "retired-here"])
    # Verifies: REQ-p00017-H
    def test_REQ_p00017_H_restored_text_binds_the_citations_as_a_build_does(self, tmp_path, origin):
        pristine_root = _standard_project(tmp_path, "pristine")
        pristine = _state(_build(pristine_root), pristine_root, CITED_REQ, CITING_REQ)
        if origin == "text":
            root = _standard_project(tmp_path, "repo", retired=True)
            graph = _build(root)
        else:
            root = _standard_project(tmp_path, "repo")
            graph = _build(root)
            graph.delete_assertion(RETIRED)
        assert _retired_faults(graph, root, RETIRED)

        graph.update_assertion(RETIRED, LIVE_TEXT)

        assert _state(graph, root, CITED_REQ, CITING_REQ) == pristine

    # Verifies: REQ-o00062-G
    def test_REQ_o00062_G_undo_of_bringing_back_returns_to_the_retired_state(self, tmp_path):
        root = _standard_project(tmp_path, retired=True)
        graph = _build(root)
        retired = _state(graph, root, CITED_REQ, CITING_REQ)

        graph.update_assertion(RETIRED, LIVE_TEXT)
        assert _state(graph, root, CITED_REQ, CITING_REQ) != retired
        graph.undo_last()

        assert _state(graph, root, CITED_REQ, CITING_REQ) == retired


# ---------------------------------------------------------------------------
# A federation
# ---------------------------------------------------------------------------


def _fed_state(graph, base: Path) -> dict:
    return _state(graph, base, FED_CITED_REQ, FED_CITING_REQ)


def _member_faults(graph, namespace: str) -> list:
    entry = next(e for e in graph.iter_repos() if e.namespace == namespace)
    return [f for f in entry.graph.unresolved_references() if f.target_id == FED_RETIRED]


class TestRetirementAcrossAFederation:
    """Validates REQ-p00017-H, REQ-o00062-G."""

    @RETIREMENTS
    # Verifies: REQ-p00017-H
    def test_REQ_p00017_H_a_citation_in_another_member_is_reported_in_that_member(
        self, tmp_path, how
    ):
        base = _associated_project(tmp_path)
        graph = _build(base / "core")
        assert _member_faults(graph, ALPHA) == []

        _retire(graph, FED_RETIRED, how)

        (fault,) = _member_faults(graph, ALPHA)
        assert fault.source_id == FED_CITING_REQ
        assert fault.fault_class is FaultClass.UNKNOWN_ASSERTION
        assert "holds no such Assertion" in fault.diagnostic
        assert _member_faults(graph, CORE) == []
        assert (
            "implements",
            FED_CITING_REQ,
            ("A",),
        ) not in _cited_by(graph, base, FED_CITED_REQ)

        built_base = _associated_project(tmp_path, "built", retired=True)
        built = _fed_state(_build(built_base / "core"), built_base)
        assert _fed_state(graph, base) == built

    @RETIREMENTS
    # Verifies: REQ-o00062-G
    def test_REQ_o00062_G_undo_restores_the_cross_repository_edge(self, tmp_path, how):
        base = _associated_project(tmp_path)
        graph = _build(base / "core")
        before = _fed_state(graph, base)
        assert ("implements", FED_CITING_REQ, ("A",)) in _cited_by(graph, base, FED_CITED_REQ)

        _retire(graph, FED_RETIRED, how)
        graph.undo_last()

        assert _fed_state(graph, base) == before
        assert _member_faults(graph, ALPHA) == []

    # Verifies: REQ-p00017-H, REQ-o00062-G
    def test_REQ_p00017_H_bringing_back_binds_the_other_members_citation(self, tmp_path):
        pristine_base = _associated_project(tmp_path, "pristine")
        pristine = _fed_state(_build(pristine_base / "core"), pristine_base)
        base = _associated_project(tmp_path, retired=True)
        graph = _build(base / "core")
        retired = _fed_state(graph, base)

        graph.update_assertion(FED_RETIRED, FED_LIVE_TEXT)
        assert _fed_state(graph, base) == pristine
        graph.undo_last()

        assert _fed_state(graph, base) == retired


# ---------------------------------------------------------------------------
# Every surface reports it alike
# ---------------------------------------------------------------------------

# The health check that lists a citation of a retired Assertion.
CHECK = "references.unknown_assertion"

_FINDING_KEYS = ("node_id", "file_path", "line", "message")


def _findings(raw: list[dict]) -> set[tuple]:
    return {tuple(f.get(k) for k in _FINDING_KEYS) for f in raw}


class TestSurfacesReportTheRetiredCitationAlike:
    """Validates REQ-o00062-O, REQ-p00017-H."""

    @RETIREMENTS
    @pytest.mark.parametrize("surface", ["http", "mcp"])
    # Verifies: REQ-o00062-O, REQ-p00017-H
    def test_REQ_o00062_O_health_mcp_and_viewer_list_it_and_undo_withdraws_it(
        self, tmp_path, how, surface
    ):
        pytest.importorskip("mcp")
        from starlette.testclient import TestClient

        from elspais.commands.health import run_checks
        from elspais.graph.render import node_version
        from elspais.mcp.server import create_server
        from elspais.server.app import create_app
        from elspais.server.state import AppState

        root = _standard_project(tmp_path)
        state = AppState.from_config(repo_root=root)
        client = TestClient(create_app(state=state, mount_mcp=False))
        tools = {
            name: tool.fn
            for name, tool in create_server(
                state.graph, working_dir=root
            )._tool_manager._tools.items()
        }

        def reported() -> dict[str, set[tuple]]:
            health = next(c for c in run_checks(state.graph, state.config) if c.name == CHECK)
            response = client.get("/api/run/checks")
            assert response.status_code == 200
            viewer = next(c for c in response.json()["checks"] if c["name"] == CHECK)
            listing = tools["get_unresolved_references"]()["unresolved_references"]
            return {
                "health": _findings([f.to_dict() for f in health.findings]),
                "viewer": _findings(viewer["findings"]),
                "mcp": _findings([f for f in listing if f["check"] == CHECK]),
            }

        assert reported() == {"health": set(), "viewer": set(), "mcp": set()}

        version = node_version(state.graph.find_by_id(CITED_REQ))
        if surface == "http":
            if how == "delete":
                body = {"assertion_id": RETIRED, "confirm": True, "if_version": version}
                response = client.post("/api/mutate/assertion/delete", json=body)
            else:
                body = {"assertion_id": RETIRED, "new_text": "<RETIRED>", "if_version": version}
                response = client.post("/api/mutate/assertion", json=body)
            assert response.status_code == 200, response.json()
            result = response.json()
        elif how == "delete":
            result = tools["mutate_delete_assertion"](RETIRED, if_version=version, confirm=True)
        else:
            result = tools["mutate_update_assertion"](RETIRED, "<RETIRED>", if_version=version)
        assert result["success"] is True, result

        after = reported()
        assert after["health"] == after["viewer"] == after["mcp"]
        assert {node_id.replace(f"{root}/", "") for node_id, *_ in after["health"]} == {
            citer for citer, _keyword in CITATIONS
        }

        tip = result["mutation"]["id"]
        if surface == "http":
            response = client.post("/api/mutate/undo", json={"if_mutation_id": tip})
            assert response.status_code == 200, response.json()
        else:
            assert tools["undo_last_mutation"](if_mutation_id=tip)["success"] is True

        assert reported() == {"health": set(), "viewer": set(), "mcp": set()}
