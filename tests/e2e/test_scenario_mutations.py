# Validates REQ-d00134-A, REQ-d00134-B, REQ-d00134-C, REQ-d00134-D
# Validates REQ-d00134-E, REQ-d00134-F
"""Comprehensive mutation round-trip scenario test.

Exercises 70+ mutation operations through the Flask API layer in a single
deterministic run. Builds a realistic requirement hierarchy, applies
mutations in phases, verifies intermediate state, saves to disk, reloads,
and confirms round-trip fidelity. Then performs a second mutation round
to prove the saved state is itself mutable.

REQ-d00134-A: 50+ mutations across all types
REQ-d00134-B: 6+ requirements across PRD/OPS/DEV with assertions
REQ-d00134-C: Intermediate checkpoint verification
REQ-d00134-D: Save -> reload -> verify round-trip
REQ-d00134-E: Second mutation round after reload
REQ-d00134-F: Undo operations properly reverted
"""

from __future__ import annotations

from pathlib import Path

import pytest

from elspais.graph import GraphNode, NodeKind
from elspais.graph.builder import TraceGraph
from elspais.graph.relations import EdgeKind
from elspais.server.app import create_app

# ---------------------------------------------------------------------------
# Fixture builder
# ---------------------------------------------------------------------------


def _build_scenario_graph(tmp_path: Path) -> tuple[TraceGraph, dict[str, Path]]:
    """Build a 6-requirement graph across PRD/OPS/DEV with real spec files.

    Hierarchy:
        PRD-1 (3 assertions: A, B, C)
          +-- OPS-1 implements PRD-1 (2 assertions: A, B)
          |     +-- DEV-1 implements OPS-1 (3 assertions: A, B, C)
          +-- OPS-2 implements PRD-1 (2 assertions: A, B)
                +-- DEV-2 implements OPS-2 (2 assertions: A, B)
        PRD-2 (2 assertions: A, B)
          (no children yet -- will be wired via mutations)

    Returns:
        Tuple of (graph, {filename: path_on_disk}).
    """
    from elspais.graph.GraphNode import FileType

    spec_dir = tmp_path / "spec"
    spec_dir.mkdir()

    graph = TraceGraph(repo_root=tmp_path)

    files: dict[str, Path] = {}
    file_nodes: dict[str, GraphNode] = {}

    def _make_file(name: str) -> GraphNode:
        path = spec_dir / name
        path.write_text("placeholder", encoding="utf-8")
        files[name] = path
        rel = str(path.relative_to(tmp_path))
        fn = GraphNode(id=f"file:{rel}", kind=NodeKind.FILE, label=name)
        fn.set_field("file_type", FileType.SPEC)
        fn.set_field("relative_path", rel)
        fn.set_field("absolute_path", str(path))
        fn.set_field("repo", None)
        file_nodes[name] = fn
        return fn

    def _make_req(
        req_id: str,
        title: str,
        level: str,
        status: str,
        file_node: GraphNode,
        assertions: list[tuple[str, str]],
        order: float = 0.0,
    ) -> GraphNode:
        node = GraphNode(id=req_id, kind=NodeKind.REQUIREMENT, label=title)
        node._content = {
            "level": level,
            "status": status,
            "hash": "00000000",
            "body_text": "",
            "parse_line": 1,
            "parse_end_line": None,
        }
        e = file_node.link(node, EdgeKind.CONTAINS)
        e.metadata = {"render_order": order}
        graph._index[req_id] = node

        for label, text in assertions:
            aid = f"{req_id}-{label}"
            a = GraphNode(id=aid, kind=NodeKind.ASSERTION, label=text)
            a._content = {"label": label, "parse_line": 1, "parse_end_line": None}
            node.link(a, EdgeKind.STRUCTURES)
            graph._index[aid] = a

        return node

    # --- File 1: PRD requirements ---
    f1 = _make_file("prd_reqs.md")

    prd1 = _make_req(
        "REQ-p00001",
        "Platform Security",
        "PRD",
        "Active",
        f1,
        [
            ("A", "The platform SHALL encrypt all data at rest."),
            ("B", "The platform SHALL use TLS 1.3 for data in transit."),
            ("C", "The platform SHALL log all security events."),
        ],
        order=0.0,
    )

    prd2 = _make_req(
        "REQ-p00002",
        "Platform Observability",
        "PRD",
        "Active",
        f1,
        [
            ("A", "The platform SHALL provide real-time metrics."),
            ("B", "The platform SHALL support distributed tracing."),
        ],
        order=1.0,
    )

    # --- File 2: OPS requirements ---
    f2 = _make_file("ops_reqs.md")

    ops1 = _make_req(
        "REQ-o00001",
        "Database Encryption",
        "OPS",
        "Active",
        f2,
        [
            ("A", "The database layer SHALL use AES-256 encryption."),
            ("B", "The encryption keys SHALL be rotated every 90 days."),
        ],
        order=0.0,
    )

    ops2 = _make_req(
        "REQ-o00002",
        "Network Security",
        "OPS",
        "Active",
        f2,
        [
            ("A", "The network layer SHALL enforce mTLS between services."),
            ("B", "The firewall SHALL deny all ingress by default."),
        ],
        order=1.0,
    )

    # --- File 3: DEV requirements ---
    f3 = _make_file("dev_reqs.md")

    dev1 = _make_req(
        "REQ-d00001",
        "Encryption Library",
        "DEV",
        "Draft",
        f3,
        [
            ("A", "The library SHALL expose an encrypt() function."),
            ("B", "The library SHALL expose a decrypt() function."),
            ("C", "The library SHALL validate key lengths."),
        ],
        order=0.0,
    )

    dev2 = _make_req(
        "REQ-d00002",
        "Firewall Rules Module",
        "DEV",
        "Draft",
        f3,
        [
            ("A", "The module SHALL generate iptables rules."),
            ("B", "The module SHALL support IPv6."),
        ],
        order=1.0,
    )

    # --- Wire hierarchy edges ---
    # OPS-1 implements PRD-1
    prd1.link(ops1, EdgeKind.IMPLEMENTS)
    # OPS-2 implements PRD-1
    prd1.link(ops2, EdgeKind.IMPLEMENTS)
    # DEV-1 implements OPS-1
    ops1.link(dev1, EdgeKind.IMPLEMENTS)
    # DEV-2 implements OPS-2
    ops2.link(dev2, EdgeKind.IMPLEMENTS)

    # --- Build graph ---
    graph._roots = [prd1, prd2]
    graph._index.update(
        {
            f"file:{files['prd_reqs.md'].relative_to(tmp_path)}": file_nodes["prd_reqs.md"],
            f"file:{files['ops_reqs.md'].relative_to(tmp_path)}": file_nodes["ops_reqs.md"],
            f"file:{files['dev_reqs.md'].relative_to(tmp_path)}": file_nodes["dev_reqs.md"],
        }
    )

    return graph, files


def _make_app(tmp_path: Path, graph: TraceGraph) -> tuple:
    """Create a Flask app from a graph."""
    config = {
        "spec": {"directories": ["spec"]},
        "hierarchy": {"levels": {"PRD": 1, "OPS": 2, "DEV": 3}},
    }
    app = create_app(tmp_path, graph, config)
    app.config["TESTING"] = True
    return app


# ---------------------------------------------------------------------------
# Helper: post mutation and assert success
# ---------------------------------------------------------------------------


def _post(client, url: str, json_data: dict, expect_success: bool = True) -> dict:
    """POST a mutation and return the JSON response."""
    resp = client.post(url, json=json_data)
    data = resp.get_json()
    if expect_success:
        assert resp.status_code == 200, f"POST {url} failed: {data}"
        assert data.get("success") is True, f"POST {url} not successful: {data}"
    return data


# ---------------------------------------------------------------------------
# The scenario test
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestScenarioMutations:
    """REQ-d00134: Comprehensive mutation round-trip scenario test.

    A single large test that exercises 70+ mutations across all types,
    verifies intermediate state, saves, reloads, and confirms fidelity.
    """

    def test_REQ_d00134_A_full_mutation_scenario(self, tmp_path: Path):
        """REQ-d00134-A+B+C+D+E+F: Full mutation scenario with save-reload-verify."""
        mutation_count = 0

        graph, files = _build_scenario_graph(tmp_path)
        app = _make_app(tmp_path, graph)
        client = app.test_client()

        # =================================================================
        # PHASE 1: Status mutations (5 mutations)
        # =================================================================

        # 1. DEV-1: Draft -> Active
        _post(client, "/api/mutate/status", {"node_id": "REQ-d00001", "new_status": "Active"})
        mutation_count += 1

        # 2. DEV-2: Draft -> Active
        _post(client, "/api/mutate/status", {"node_id": "REQ-d00002", "new_status": "Active"})
        mutation_count += 1

        # 3. OPS-1: Active -> Deprecated (will undo this later)
        _post(client, "/api/mutate/status", {"node_id": "REQ-o00001", "new_status": "Deprecated"})
        mutation_count += 1

        # 4. Undo the deprecation of OPS-1 (REQ-d00134-F)
        _post(client, "/api/mutate/undo", {})
        mutation_count += 1

        # 5. PRD-2: Active -> Draft
        _post(client, "/api/mutate/status", {"node_id": "REQ-p00002", "new_status": "Draft"})
        mutation_count += 1

        # --- Checkpoint 1: verify statuses (REQ-d00134-C) ---
        assert graph.find_by_id("REQ-d00001").status == "Active"
        assert graph.find_by_id("REQ-d00002").status == "Active"
        assert graph.find_by_id("REQ-o00001").status == "Active"  # undo restored it
        assert graph.find_by_id("REQ-p00002").status == "Draft"

        # =================================================================
        # PHASE 2: Title mutations (6 mutations)
        # =================================================================

        # 6. Update PRD-1 title
        _post(
            client,
            "/api/mutate/title",
            {"node_id": "REQ-p00001", "new_title": "Platform Security (Revised)"},
        )
        mutation_count += 1

        # 7. Update OPS-1 title
        _post(
            client,
            "/api/mutate/title",
            {"node_id": "REQ-o00001", "new_title": "Database Encryption v2"},
        )
        mutation_count += 1

        # 8. Update DEV-1 title
        _post(
            client,
            "/api/mutate/title",
            {"node_id": "REQ-d00001", "new_title": "Encryption Library v2"},
        )
        mutation_count += 1

        # 9. Update DEV-2 title (will undo and redo)
        _post(
            client,
            "/api/mutate/title",
            {"node_id": "REQ-d00002", "new_title": "WRONG TITLE"},
        )
        mutation_count += 1

        # 10. Undo wrong title (REQ-d00134-F)
        _post(client, "/api/mutate/undo", {})
        mutation_count += 1

        # 11. Set correct title for DEV-2
        _post(
            client,
            "/api/mutate/title",
            {"node_id": "REQ-d00002", "new_title": "Firewall Rules Module v2"},
        )
        mutation_count += 1

        # --- Checkpoint 2: verify titles (REQ-d00134-C) ---
        assert graph.find_by_id("REQ-p00001").get_label() == "Platform Security (Revised)"
        assert graph.find_by_id("REQ-o00001").get_label() == "Database Encryption v2"
        assert graph.find_by_id("REQ-d00001").get_label() == "Encryption Library v2"
        assert graph.find_by_id("REQ-d00002").get_label() == "Firewall Rules Module v2"

        # =================================================================
        # PHASE 3: Assertion mutations -- add (8 mutations)
        # =================================================================

        # 12. Add assertion D to PRD-1
        _post(
            client,
            "/api/mutate/assertion/add",
            {
                "req_id": "REQ-p00001",
                "label": "D",
                "text": "The platform SHALL support multi-factor authentication.",
            },
        )
        mutation_count += 1

        # 13. Add assertion C to OPS-1
        _post(
            client,
            "/api/mutate/assertion/add",
            {
                "req_id": "REQ-o00001",
                "label": "C",
                "text": "The database layer SHALL support transparent data encryption.",
            },
        )
        mutation_count += 1

        # 14. Add assertion C to OPS-2
        _post(
            client,
            "/api/mutate/assertion/add",
            {
                "req_id": "REQ-o00002",
                "label": "C",
                "text": "The network layer SHALL implement rate limiting.",
            },
        )
        mutation_count += 1

        # 15. Add assertion D to DEV-1
        _post(
            client,
            "/api/mutate/assertion/add",
            {
                "req_id": "REQ-d00001",
                "label": "D",
                "text": "The library SHALL support hardware security modules.",
            },
        )
        mutation_count += 1

        # 16. Add assertion C to DEV-2
        _post(
            client,
            "/api/mutate/assertion/add",
            {
                "req_id": "REQ-d00002",
                "label": "C",
                "text": "The module SHALL log all rule changes.",
            },
        )
        mutation_count += 1

        # 17. Add assertion C to PRD-2
        _post(
            client,
            "/api/mutate/assertion/add",
            {
                "req_id": "REQ-p00002",
                "label": "C",
                "text": "The platform SHALL support alerting on anomalies.",
            },
        )
        mutation_count += 1

        # 18-19. Add two more assertions to PRD-1 (E, F)
        _post(
            client,
            "/api/mutate/assertion/add",
            {
                "req_id": "REQ-p00001",
                "label": "E",
                "text": "The platform SHALL enforce least-privilege access.",
            },
        )
        mutation_count += 1

        _post(
            client,
            "/api/mutate/assertion/add",
            {
                "req_id": "REQ-p00001",
                "label": "F",
                "text": "The platform SHALL provide audit trails.",
            },
        )
        mutation_count += 1

        # --- Checkpoint 3: verify new assertions exist ---
        assert graph.find_by_id("REQ-p00001-D") is not None
        assert graph.find_by_id("REQ-p00001-E") is not None
        assert graph.find_by_id("REQ-p00001-F") is not None
        assert graph.find_by_id("REQ-o00001-C") is not None
        assert graph.find_by_id("REQ-o00002-C") is not None
        assert graph.find_by_id("REQ-d00001-D") is not None
        assert graph.find_by_id("REQ-d00002-C") is not None
        assert graph.find_by_id("REQ-p00002-C") is not None

        # =================================================================
        # PHASE 4: Assertion mutations -- update text (5 mutations)
        # =================================================================

        # 20. Update PRD-1-A text
        _post(
            client,
            "/api/mutate/assertion",
            {
                "assertion_id": "REQ-p00001-A",
                "new_text": "The platform SHALL encrypt all data at rest using AES-256.",
            },
        )
        mutation_count += 1

        # 21. Update OPS-1-A text
        _post(
            client,
            "/api/mutate/assertion",
            {
                "assertion_id": "REQ-o00001-A",
                "new_text": "The database layer SHALL use AES-256-GCM encryption.",
            },
        )
        mutation_count += 1

        # 22. Update DEV-1-A text
        _post(
            client,
            "/api/mutate/assertion",
            {
                "assertion_id": "REQ-d00001-A",
                "new_text": "The library SHALL expose an encrypt(plaintext, key) function.",
            },
        )
        mutation_count += 1

        # 23. Update OPS-2-B text
        _post(
            client,
            "/api/mutate/assertion",
            {
                "assertion_id": "REQ-o00002-B",
                "new_text": "The firewall SHALL deny all ingress except allowlisted ports.",
            },
        )
        mutation_count += 1

        # 24. Update DEV-2-A text
        _post(
            client,
            "/api/mutate/assertion",
            {
                "assertion_id": "REQ-d00002-A",
                "new_text": "The module SHALL generate nftables rules.",
            },
        )
        mutation_count += 1

        # =================================================================
        # PHASE 5: Assertion mutations -- delete (3 mutations)
        # =================================================================

        # 25. Delete PRD-1-F (the one we just added)
        _post(
            client,
            "/api/mutate/assertion/delete",
            {"assertion_id": "REQ-p00001-F", "confirm": True},
        )
        mutation_count += 1

        # 26. Delete OPS-2-C (the one we just added)
        _post(
            client,
            "/api/mutate/assertion/delete",
            {"assertion_id": "REQ-o00002-C", "confirm": True},
        )
        mutation_count += 1

        # 27. Delete DEV-2-C (the one we just added, will undo this)
        _post(
            client,
            "/api/mutate/assertion/delete",
            {"assertion_id": "REQ-d00002-C", "confirm": True},
        )
        mutation_count += 1

        # 28. Undo the deletion of DEV-2-C (REQ-d00134-F)
        _post(client, "/api/mutate/undo", {})
        mutation_count += 1

        # --- Checkpoint 4: verify assertion deletions ---
        assert graph.find_by_id("REQ-p00001-F") is None  # deleted
        assert graph.find_by_id("REQ-o00002-C") is None  # deleted
        assert graph.find_by_id("REQ-d00002-C") is not None  # undo restored it

        # =================================================================
        # PHASE 6: Assertion mutations -- rename label (via graph API
        # since Flask has no rename endpoint) (2 mutations)
        # =================================================================

        # 29. Rename PRD-1-E to PRD-1-Z
        graph.rename_assertion("REQ-p00001-E", "Z")
        mutation_count += 1

        # 30. Rename DEV-1-D to DEV-1-X
        graph.rename_assertion("REQ-d00001-D", "X")
        mutation_count += 1

        # --- Checkpoint 5: verify renames ---
        assert graph.find_by_id("REQ-p00001-Z") is not None
        assert graph.find_by_id("REQ-p00001-E") is None
        assert graph.find_by_id("REQ-d00001-X") is not None
        assert graph.find_by_id("REQ-d00001-D") is None

        # =================================================================
        # PHASE 7: Edge mutations -- add (6 mutations)
        # =================================================================

        # 31. Add OPS-1 also implements PRD-2 (cross-link)
        _post(
            client,
            "/api/mutate/edge",
            {
                "action": "add",
                "source_id": "REQ-o00001",
                "target_id": "REQ-p00002",
                "edge_kind": "IMPLEMENTS",
            },
        )
        mutation_count += 1

        # 32. Add DEV-1 also implements OPS-2 (cross-link)
        _post(
            client,
            "/api/mutate/edge",
            {
                "action": "add",
                "source_id": "REQ-d00001",
                "target_id": "REQ-o00002",
                "edge_kind": "IMPLEMENTS",
            },
        )
        mutation_count += 1

        # 33. Add DEV-2 refines PRD-1 (add a REFINES edge)
        _post(
            client,
            "/api/mutate/edge",
            {
                "action": "add",
                "source_id": "REQ-d00002",
                "target_id": "REQ-p00001",
                "edge_kind": "REFINES",
            },
        )
        mutation_count += 1

        # 34. Add OPS-2 implements PRD-2 with assertion target A
        _post(
            client,
            "/api/mutate/edge",
            {
                "action": "add",
                "source_id": "REQ-o00002",
                "target_id": "REQ-p00002",
                "edge_kind": "IMPLEMENTS",
                "assertion_targets": ["A"],
            },
        )
        mutation_count += 1

        # 35. Add DEV-1 implements PRD-1 with assertion targets A+B
        _post(
            client,
            "/api/mutate/edge",
            {
                "action": "add",
                "source_id": "REQ-d00001",
                "target_id": "REQ-p00001",
                "edge_kind": "IMPLEMENTS",
                "assertion_targets": ["A", "B"],
            },
        )
        mutation_count += 1

        # 36. Add edge that we'll delete later
        _post(
            client,
            "/api/mutate/edge",
            {
                "action": "add",
                "source_id": "REQ-d00002",
                "target_id": "REQ-p00002",
                "edge_kind": "IMPLEMENTS",
            },
        )
        mutation_count += 1

        # =================================================================
        # PHASE 8: Edge mutations -- delete (3 mutations)
        # =================================================================

        # 37. Delete the edge we just added (DEV-2 -> PRD-2)
        _post(
            client,
            "/api/mutate/edge",
            {
                "action": "delete",
                "source_id": "REQ-d00002",
                "target_id": "REQ-p00002",
            },
        )
        mutation_count += 1

        # 38. Delete DEV-1's cross-link to OPS-2 (will undo)
        _post(
            client,
            "/api/mutate/edge",
            {
                "action": "delete",
                "source_id": "REQ-d00001",
                "target_id": "REQ-o00002",
            },
        )
        mutation_count += 1

        # 39. Undo the edge deletion (REQ-d00134-F)
        _post(client, "/api/mutate/undo", {})
        mutation_count += 1

        # =================================================================
        # PHASE 9: Edge mutations -- change kind (3 mutations)
        # =================================================================

        # 40. Change DEV-2's REFINES to PRD-1 -> IMPLEMENTS
        _post(
            client,
            "/api/mutate/edge",
            {
                "action": "change_kind",
                "source_id": "REQ-d00002",
                "target_id": "REQ-p00001",
                "new_kind": "IMPLEMENTS",
            },
        )
        mutation_count += 1

        # 41. Change OPS-1's IMPLEMENTS to PRD-1 -> REFINES
        _post(
            client,
            "/api/mutate/edge",
            {
                "action": "change_kind",
                "source_id": "REQ-o00001",
                "target_id": "REQ-p00001",
                "new_kind": "REFINES",
            },
        )
        mutation_count += 1

        # 42. Change it back to IMPLEMENTS
        _post(
            client,
            "/api/mutate/edge",
            {
                "action": "change_kind",
                "source_id": "REQ-o00001",
                "target_id": "REQ-p00001",
                "new_kind": "IMPLEMENTS",
            },
        )
        mutation_count += 1

        # --- Checkpoint 6: verify edge state ---
        # OPS-1 should implement PRD-1 (changed back) and PRD-2
        ops1_node = graph.find_by_id("REQ-o00001")
        ops1_parent_ids = {p.id for p in ops1_node.iter_parents()}
        assert "REQ-p00001" in ops1_parent_ids
        assert "REQ-p00002" in ops1_parent_ids

        # DEV-1 should implement OPS-1, OPS-2, and PRD-1 (with assertion targets)
        dev1_node = graph.find_by_id("REQ-d00001")
        dev1_parent_ids = {p.id for p in dev1_node.iter_parents()}
        assert "REQ-o00001" in dev1_parent_ids
        assert "REQ-o00002" in dev1_parent_ids  # undo restored this
        assert "REQ-p00001" in dev1_parent_ids

        # =================================================================
        # PHASE 10: Requirement mutations -- add (5 mutations)
        # =================================================================

        # 43. Add a new OPS requirement under PRD-2
        graph.add_requirement(
            "REQ-o00003",
            "Metrics Pipeline",
            "OPS",
            status="Draft",
            parent_id="REQ-p00002",
        )
        mutation_count += 1

        # 44. Add assertion A to the new OPS-3
        _post(
            client,
            "/api/mutate/assertion/add",
            {
                "req_id": "REQ-o00003",
                "label": "A",
                "text": "The pipeline SHALL ingest metrics via OpenTelemetry.",
            },
        )
        mutation_count += 1

        # 45. Add assertion B to OPS-3
        _post(
            client,
            "/api/mutate/assertion/add",
            {
                "req_id": "REQ-o00003",
                "label": "B",
                "text": "The pipeline SHALL store metrics in a time-series database.",
            },
        )
        mutation_count += 1

        # 46. Add a new DEV requirement under OPS-3
        graph.add_requirement(
            "REQ-d00003",
            "OTLP Collector",
            "DEV",
            status="Draft",
            parent_id="REQ-o00003",
        )
        mutation_count += 1

        # 47. Add assertion A to DEV-3
        _post(
            client,
            "/api/mutate/assertion/add",
            {
                "req_id": "REQ-d00003",
                "label": "A",
                "text": "The collector SHALL accept OTLP gRPC connections.",
            },
        )
        mutation_count += 1

        # --- Checkpoint 7: verify new requirements ---
        assert graph.find_by_id("REQ-o00003") is not None
        assert graph.find_by_id("REQ-o00003").get_label() == "Metrics Pipeline"
        assert graph.find_by_id("REQ-o00003").status == "Draft"
        assert graph.find_by_id("REQ-d00003") is not None
        assert graph.find_by_id("REQ-d00003-A") is not None

        # =================================================================
        # PHASE 11: Requirement mutations -- delete (2 mutations)
        # =================================================================

        # 48. Delete DEV-3 (we just added it)
        _post(
            client,
            "/api/mutate/requirement/delete",
            {"node_id": "REQ-d00003", "confirm": True},
        )
        mutation_count += 1

        # 49. Undo the deletion of DEV-3 (REQ-d00134-F)
        _post(client, "/api/mutate/undo", {})
        mutation_count += 1

        # --- Checkpoint 8: DEV-3 should be restored ---
        assert graph.find_by_id("REQ-d00003") is not None

        # =================================================================
        # PHASE 12: More mixed mutations (10 mutations)
        # =================================================================

        # 50. Change OPS-3 status to Active
        _post(client, "/api/mutate/status", {"node_id": "REQ-o00003", "new_status": "Active"})
        mutation_count += 1

        # 51. Change DEV-3 status to Active
        _post(client, "/api/mutate/status", {"node_id": "REQ-d00003", "new_status": "Active"})
        mutation_count += 1

        # 52. Update PRD-2 title
        _post(
            client,
            "/api/mutate/title",
            {"node_id": "REQ-p00002", "new_title": "Platform Observability (Enhanced)"},
        )
        mutation_count += 1

        # 53. Add assertion D to PRD-1
        # (F was deleted, E was renamed to Z; D already exists; use G)
        _post(
            client,
            "/api/mutate/assertion/add",
            {
                "req_id": "REQ-p00001",
                "label": "G",
                "text": "The platform SHALL support data masking for PII.",
            },
        )
        mutation_count += 1

        # 54. Update PRD-2-A text
        _post(
            client,
            "/api/mutate/assertion",
            {
                "assertion_id": "REQ-p00002-A",
                "new_text": "The platform SHALL provide real-time metrics with sub-second latency.",
            },
        )
        mutation_count += 1

        # 55. Add DEV-1 assertion E
        _post(
            client,
            "/api/mutate/assertion/add",
            {
                "req_id": "REQ-d00001",
                "label": "E",
                "text": "The library SHALL use constant-time comparison for keys.",
            },
        )
        mutation_count += 1

        # 56-59. Multiple status changes for comprehensive coverage
        _post(client, "/api/mutate/status", {"node_id": "REQ-p00002", "new_status": "Active"})
        mutation_count += 1

        _post(client, "/api/mutate/status", {"node_id": "REQ-d00001", "new_status": "Deprecated"})
        mutation_count += 1

        # 58. Undo deprecation
        _post(client, "/api/mutate/undo", {})
        mutation_count += 1

        # 59. Add one more edge: DEV-2 implements PRD-2 with target B
        _post(
            client,
            "/api/mutate/edge",
            {
                "action": "add",
                "source_id": "REQ-d00002",
                "target_id": "REQ-p00002",
                "edge_kind": "IMPLEMENTS",
                "assertion_targets": ["B"],
            },
        )
        mutation_count += 1

        # =================================================================
        # PHASE 13: Undo-to operation (multi-undo)
        # =================================================================

        # 60-62. Add three mutations to test undo_to
        r1 = _post(
            client,
            "/api/mutate/title",
            {"node_id": "REQ-o00002", "new_title": "Network Security v2"},
        )
        mutation_count += 1
        undo_target_id = r1["mutation"]["id"]

        _post(
            client,
            "/api/mutate/title",
            {"node_id": "REQ-o00002", "new_title": "Network Security v3"},
        )
        mutation_count += 1

        _post(
            client,
            "/api/mutate/title",
            {"node_id": "REQ-o00002", "new_title": "Network Security v4"},
        )
        mutation_count += 1

        # Verify current state
        assert graph.find_by_id("REQ-o00002").get_label() == "Network Security v4"

        # 63. Undo back to (and including) mutation 60 -- undoes mutations 62, 61, 60
        graph.undo_to(undo_target_id)
        mutation_count += 1

        # OPS-2 should be back to "Network Security" (original title)
        assert graph.find_by_id("REQ-o00002").get_label() == "Network Security"

        # =================================================================
        # PHASE 14: A few more mutations to reach 70+ total
        # =================================================================

        # 64. Rename OPS-2 title
        _post(
            client,
            "/api/mutate/title",
            {"node_id": "REQ-o00002", "new_title": "Network Security Final"},
        )
        mutation_count += 1

        # 65. Add assertion D to OPS-2
        _post(
            client,
            "/api/mutate/assertion/add",
            {
                "req_id": "REQ-o00002",
                "label": "D",
                "text": "The network layer SHALL support service mesh integration.",
            },
        )
        mutation_count += 1

        # 66. Update OPS-2-D text
        _post(
            client,
            "/api/mutate/assertion",
            {
                "assertion_id": "REQ-o00002-D",
                "new_text": "The network layer SHALL integrate with Istio service mesh.",
            },
        )
        mutation_count += 1

        # 67. Add DEV-2 assertion D
        _post(
            client,
            "/api/mutate/assertion/add",
            {
                "req_id": "REQ-d00002",
                "label": "D",
                "text": "The module SHALL support nftables rule rollback.",
            },
        )
        mutation_count += 1

        # 68. Rename DEV-1 via graph API
        graph.rename_node("REQ-d00001", "REQ-d00010")
        mutation_count += 1

        # 69. Update the renamed node's title
        _post(
            client,
            "/api/mutate/title",
            {"node_id": "REQ-d00010", "new_title": "Encryption Library Final"},
        )
        mutation_count += 1

        # 70. Final status change on PRD-1
        _post(client, "/api/mutate/status", {"node_id": "REQ-p00001", "new_status": "Deprecated"})
        mutation_count += 1

        assert mutation_count >= 70, f"Expected 70+ mutations, got {mutation_count}"

        # =================================================================
        # CHECKPOINT: Pre-save state verification (REQ-d00134-C)
        # =================================================================

        # Verify overall graph state before save
        # Requirements that should exist:
        expected_reqs = {
            "REQ-p00001": {
                "title": "Platform Security (Revised)",
                "status": "Deprecated",
                "level": "PRD",
            },
            "REQ-p00002": {
                "title": "Platform Observability (Enhanced)",
                "status": "Active",
                "level": "PRD",
            },
            "REQ-o00001": {
                "title": "Database Encryption v2",
                "status": "Active",
                "level": "OPS",
            },
            "REQ-o00002": {
                "title": "Network Security Final",
                "status": "Active",
                "level": "OPS",
            },
            "REQ-o00003": {
                "title": "Metrics Pipeline",
                "status": "Active",
                "level": "OPS",
            },
            "REQ-d00010": {
                "title": "Encryption Library Final",
                "status": "Active",
                "level": "DEV",
            },
            "REQ-d00002": {
                "title": "Firewall Rules Module v2",
                "status": "Active",
                "level": "DEV",
            },
            "REQ-d00003": {
                "title": "OTLP Collector",
                "status": "Active",
                "level": "DEV",
            },
        }

        for req_id, expected in expected_reqs.items():
            node = graph.find_by_id(req_id)
            assert node is not None, f"{req_id} should exist in graph"
            assert (
                node.get_label() == expected["title"]
            ), f"{req_id} title: got {node.get_label()!r}, expected {expected['title']!r}"
            assert (
                node.status == expected["status"]
            ), f"{req_id} status: got {node.status!r}, expected {expected['status']!r}"
            assert (
                node.level == expected["level"]
            ), f"{req_id} level: got {node.level!r}, expected {expected['level']!r}"

        # REQ-d00001 should NOT exist (renamed to REQ-d00010)
        assert graph.find_by_id("REQ-d00001") is None

        # Verify assertion state
        # PRD-1 should have A, B, C, D, Z, G (F deleted, E renamed to Z)
        for label in ["A", "B", "C", "D", "Z", "G"]:
            assert (
                graph.find_by_id(f"REQ-p00001-{label}") is not None
            ), f"REQ-p00001-{label} should exist"
        assert graph.find_by_id("REQ-p00001-E") is None  # renamed to Z
        assert graph.find_by_id("REQ-p00001-F") is None  # deleted

        # DEV-1 was renamed to DEV-10, so assertions are REQ-d00010-*
        for label in ["A", "B", "C", "X", "E"]:
            assert (
                graph.find_by_id(f"REQ-d00010-{label}") is not None
            ), f"REQ-d00010-{label} should exist"
        assert graph.find_by_id("REQ-d00010-D") is None  # renamed to X

        # =================================================================
        # SAVE (REQ-d00134-D)
        # =================================================================

        resp = client.post("/api/save")
        save_data = resp.get_json()
        assert resp.status_code == 200, f"Save failed: {save_data}"
        assert save_data["success"] is True, f"Save not successful: {save_data}"

        # =================================================================
        # RELOAD: Build fresh graph from saved files (REQ-d00134-D)
        # =================================================================

        from elspais.graph.factory import build_graph

        config = {
            "spec": {"directories": ["spec"]},
            "hierarchy": {"levels": {"PRD": 1, "OPS": 2, "DEV": 3}},
        }

        # build_graph needs a .elspais.toml for _find_repo_root
        elspais_toml = tmp_path / ".elspais.toml"
        if not elspais_toml.exists():
            elspais_toml.write_text(
                '[project]\nname = "scenario-test"\n\n'
                "[spec]\n"
                'directories = ["spec"]\n\n'
                "[hierarchy]\n"
                "[hierarchy.levels]\n"
                "PRD = 1\nOPS = 2\nDEV = 3\n",
                encoding="utf-8",
            )

        reloaded = build_graph(
            config=config,
            repo_root=tmp_path,
            scan_code=False,
            scan_tests=False,
            scan_sponsors=False,
        )

        # =================================================================
        # POST-SAVE VERIFICATION (REQ-d00134-D)
        # =================================================================

        # Verify all surviving requirements
        for req_id, expected in expected_reqs.items():
            node = reloaded.find_by_id(req_id)
            assert node is not None, f"{req_id} should exist in reloaded graph"
            assert (
                node.get_label() == expected["title"]
            ), f"Reloaded {req_id} title: got {node.get_label()!r}, expected {expected['title']!r}"
            assert (
                node.status == expected["status"]
            ), f"Reloaded {req_id} status: got {node.status!r}, expected {expected['status']!r}"

        # REQ-d00001 should NOT exist (renamed to d00010)
        assert reloaded.find_by_id("REQ-d00001") is None

        # Verify assertions survived save-reload
        for label in ["A", "B", "C", "D", "Z", "G"]:
            assert (
                reloaded.find_by_id(f"REQ-p00001-{label}") is not None
            ), f"Reloaded REQ-p00001-{label} should exist"
        assert reloaded.find_by_id("REQ-p00001-E") is None
        assert reloaded.find_by_id("REQ-p00001-F") is None

        # Verify assertion text survived
        prd1_a = reloaded.find_by_id("REQ-p00001-A")
        assert (
            "AES-256" in prd1_a.get_label()
        ), f"PRD-1-A text should contain 'AES-256', got: {prd1_a.get_label()}"

        # Verify DEV-10 assertions
        for label in ["A", "B", "C", "X", "E"]:
            assert (
                reloaded.find_by_id(f"REQ-d00010-{label}") is not None
            ), f"Reloaded REQ-d00010-{label} should exist"

        # Verify new requirements from mutations survived
        assert reloaded.find_by_id("REQ-o00003") is not None
        assert reloaded.find_by_id("REQ-d00003") is not None
        assert reloaded.find_by_id("REQ-o00003-A") is not None
        assert reloaded.find_by_id("REQ-o00003-B") is not None
        assert reloaded.find_by_id("REQ-d00003-A") is not None

        # Verify edges survived -- check that implements/refines are in the files
        # Read the dev_reqs.md to check edge rendering
        dev_content = files["dev_reqs.md"].read_text(encoding="utf-8")
        ops_content = files["ops_reqs.md"].read_text(encoding="utf-8")
        prd_content = files["prd_reqs.md"].read_text(encoding="utf-8")  # noqa: F841

        # DEV-10 (renamed from DEV-1) should implement OPS-1 and OPS-2
        assert "REQ-o00001" in dev_content, "DEV-10 should implement OPS-1"
        assert "REQ-o00002" in dev_content, "DEV-10 should implement OPS-2"

        # DEV-2 should implement OPS-2 and PRD-1 (edge kind changed from REFINES)
        # and PRD-2-B (with assertion target)
        assert "REQ-p00001" in dev_content, "DEV-2 should implement PRD-1"

        # OPS-1 should implement PRD-1 and PRD-2
        assert "REQ-p00001" in ops_content, "OPS-1 should implement PRD-1"
        assert "REQ-p00002" in ops_content, "OPS-1 should implement PRD-2"

        # =================================================================
        # SECOND MUTATION ROUND (REQ-d00134-E)
        # =================================================================

        # Create a new app with the reloaded graph
        app2 = _make_app(tmp_path, reloaded)
        client2 = app2.test_client()

        # A few mutations on the reloaded graph
        _post(
            client2,
            "/api/mutate/title",
            {"node_id": "REQ-p00001", "new_title": "Platform Security (Final)"},
        )

        _post(
            client2,
            "/api/mutate/status",
            {"node_id": "REQ-p00001", "new_status": "Active"},
        )

        _post(
            client2,
            "/api/mutate/assertion/add",
            {
                "req_id": "REQ-o00003",
                "label": "C",
                "text": "The pipeline SHALL support metric aggregation.",
            },
        )

        _post(
            client2,
            "/api/mutate/assertion",
            {
                "assertion_id": "REQ-d00002-B",
                "new_text": "The module SHALL support IPv4 and IPv6 dual-stack.",
            },
        )

        # Second save
        resp2 = client2.post("/api/save")
        save2_data = resp2.get_json()
        assert resp2.status_code == 200, f"Second save failed: {save2_data}"
        assert save2_data["success"] is True

        # Second reload
        reloaded2 = build_graph(
            config=config,
            repo_root=tmp_path,
            scan_code=False,
            scan_tests=False,
            scan_sponsors=False,
        )

        # Verify second-round mutations survived
        prd1_r2 = reloaded2.find_by_id("REQ-p00001")
        assert prd1_r2 is not None
        assert prd1_r2.get_label() == "Platform Security (Final)"
        assert prd1_r2.status == "Active"

        assert reloaded2.find_by_id("REQ-o00003-C") is not None
        dev2_b = reloaded2.find_by_id("REQ-d00002-B")
        assert "dual-stack" in dev2_b.get_label()

        # The scenario is complete. All 70+ mutations exercised across
        # all mutation types, with intermediate checkpoints, undo operations,
        # two save-reload cycles, and comprehensive verification.
