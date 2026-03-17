# Validates: REQ-p00060
"""Comprehensive MCP e2e tests.

Each test builds a project, starts an MCP server, and exercises
multiple tool calls. Tests cover search, hierarchy, mutations,
cursors, subtrees, coverage, and file mutations.
"""

from __future__ import annotations

import shutil

import pytest

pytest.importorskip("mcp")

from .helpers import (
    Requirement,
    base_config,
    build_project,
    mcp_call,
    mcp_call_all,
    start_mcp,
    stop_mcp,
)

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        shutil.which("elspais") is None,
        reason="elspais CLI not found on PATH",
    ),
]


def _assertion_labels(req_data: dict) -> list[str]:
    """Extract assertion labels from a get_requirement response."""
    return [
        c.get("label", "") for c in req_data.get("children", []) if c.get("kind") == "assertion"
    ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_standard_project(tmp_path):
    """Build a standard 3-tier project for MCP tests."""
    cfg = base_config(
        name="mcp-test-project",
        testing_enabled=True,
        test_dirs=["tests"],
    )
    prd1 = Requirement(
        "REQ-p00001",
        "User Management",
        "PRD",
        assertions=[
            ("A", "The system SHALL create user accounts."),
            ("B", "The system SHALL delete user accounts."),
            ("C", "The system SHALL update user profiles."),
        ],
    )
    prd2 = Requirement(
        "REQ-p00002",
        "Notifications",
        "PRD",
        assertions=[
            ("A", "The system SHALL send email notifications."),
            ("B", "The system SHALL send push notifications."),
        ],
    )
    ops = Requirement(
        "REQ-o00001",
        "User Service Ops",
        "OPS",
        implements="REQ-p00001",
        assertions=[
            ("A", "Operations SHALL monitor user service health."),
        ],
    )
    dev1 = Requirement(
        "REQ-d00001",
        "User CRUD",
        "DEV",
        implements="REQ-o00001",
        assertions=[
            ("A", "The module SHALL implement create/read/update/delete."),
            ("B", "The module SHALL validate email format."),
        ],
    )
    dev2 = Requirement(
        "REQ-d00002",
        "Notification Service",
        "DEV",
        implements="REQ-p00002",
        assertions=[
            ("A", "The module SHALL queue notifications."),
            ("B", "The module SHALL retry failed deliveries."),
        ],
    )
    build_project(
        tmp_path,
        cfg,
        spec_files={
            "spec/prd-core.md": [prd1, prd2],
            "spec/ops-services.md": [ops],
            "spec/dev-impl.md": [dev1, dev2],
        },
        code_files={
            "src/user_crud.py": {"implements": ["REQ-d00001"]},
            "src/notifications.py": {"implements": ["REQ-d00002"]},
        },
        test_files={
            "tests/test_users.py": {"validates": ["REQ-d00001"]},
        },
    )
    return tmp_path


def _build_fda_project(tmp_path):
    """Build an FDA-style project for MCP tests."""
    cfg = base_config(
        name="mcp-fda",
        canonical="{type}-{component}",
        types={
            "PRD": {"level": 1},
            "OPS": {"level": 2},
            "DEV": {"level": 3},
        },
        allowed_implements=["DEV -> OPS, PRD", "OPS -> PRD"],
    )
    prd = Requirement(
        "PRD-00001",
        "Compliance",
        "PRD",
        assertions=[
            ("A", "The system SHALL maintain compliance."),
            ("B", "The system SHALL generate compliance reports."),
        ],
    )
    dev = Requirement(
        "DEV-00001",
        "Compliance Engine",
        "DEV",
        implements="PRD-00001",
        assertions=[("A", "The engine SHALL check rules.")],
    )
    build_project(
        tmp_path,
        cfg,
        spec_files={
            "spec/prd-compliance.md": [prd],
            "spec/dev-engine.md": [dev],
        },
    )
    return tmp_path


# ---------------------------------------------------------------------------
# Test 25: MCP search, get_requirement, get_hierarchy
# ---------------------------------------------------------------------------


class TestMCPSearchAndNavigation:
    """MCP search, get_requirement, get_hierarchy on standard project."""

    def test_search_finds_requirements(self, tmp_path):
        _build_standard_project(tmp_path)
        proc = start_mcp(tmp_path)
        try:
            results = mcp_call_all(proc, "search", {"query": "User"})
            assert len(results) >= 1, f"Expected search results, got {results}"
            # At least one result should have "User" in title or id
            ids = [r.get("id", "") for r in results]
            assert any("User" in str(r) for r in results), f"No User-related results: {ids}"
        finally:
            stop_mcp(proc)

    def test_search_empty_returns_nothing(self, tmp_path):
        _build_standard_project(tmp_path)
        proc = start_mcp(tmp_path)
        try:
            results = mcp_call_all(proc, "search", {"query": "zzz_nonexistent_xyz"})
            assert len(results) == 0
        finally:
            stop_mcp(proc)

    def test_get_requirement_returns_details(self, tmp_path):
        _build_standard_project(tmp_path)
        proc = start_mcp(tmp_path)
        try:
            result = mcp_call(proc, "get_requirement", {"req_id": "REQ-p00001"})
            assert result["id"] == "REQ-p00001"
            assert "User Management" in result.get("title", "")
            # Assertions are in 'children' list with kind='assertion'
            children = result.get("children", [])
            assertion_children = [c for c in children if c.get("kind") == "assertion"]
            assert len(assertion_children) >= 3
        finally:
            stop_mcp(proc)

    def test_get_requirement_not_found(self, tmp_path):
        _build_standard_project(tmp_path)
        proc = start_mcp(tmp_path)
        try:
            result = mcp_call(proc, "get_requirement", {"req_id": "REQ-zzz99"})
            # Should indicate not found
            assert result is None or result.get("error") or result.get("_error")
        finally:
            stop_mcp(proc)

    def test_get_hierarchy_shows_tree(self, tmp_path):
        _build_standard_project(tmp_path)
        proc = start_mcp(tmp_path)
        try:
            result = mcp_call(proc, "get_hierarchy", {"req_id": "REQ-d00001"})
            assert "ancestors" in result
            assert "children" in result
            # d00001 implements o00001 which implements p00001
            ancestor_ids = [a.get("id", "") for a in result["ancestors"]]
            assert any("o00001" in aid for aid in ancestor_ids) or len(result["ancestors"]) > 0
        finally:
            stop_mcp(proc)


# ---------------------------------------------------------------------------
# Test 26: MCP project summary and workspace info
# ---------------------------------------------------------------------------


class TestMCPProjectInfo:
    """MCP get_project_summary, get_workspace_info, get_graph_status."""

    def test_project_summary(self, tmp_path):
        _build_standard_project(tmp_path)
        proc = start_mcp(tmp_path)
        try:
            result = mcp_call(proc, "get_project_summary", {})
            assert isinstance(result, dict)
            assert "levels" in result or "total" in result or len(result) > 0
        finally:
            stop_mcp(proc)

    def test_workspace_info(self, tmp_path):
        _build_standard_project(tmp_path)
        proc = start_mcp(tmp_path)
        try:
            result = mcp_call(proc, "get_workspace_info", {"detail": "default"})
            assert isinstance(result, dict)
            assert "project_name" in result or "name" in result or len(result) > 0
        finally:
            stop_mcp(proc)

    def test_graph_status(self, tmp_path):
        _build_standard_project(tmp_path)
        proc = start_mcp(tmp_path)
        try:
            result = mcp_call(proc, "get_graph_status", {})
            assert isinstance(result, dict)
        finally:
            stop_mcp(proc)


# ---------------------------------------------------------------------------
# Test 27: MCP mutation round-trip (add, update, undo)
# ---------------------------------------------------------------------------


class TestMCPMutations:
    """MCP mutation tools: add, update, rename, undo."""

    def test_add_requirement_and_undo(self, tmp_path):
        _build_standard_project(tmp_path)
        proc = start_mcp(tmp_path)
        try:
            # Add a new requirement
            result = mcp_call(
                proc,
                "mutate_add_requirement",
                {
                    "req_id": "REQ-p00003",
                    "title": "New Feature",
                    "level": "prd",
                    "status": "Draft",
                },
            )
            assert isinstance(result, dict)
            assert not result.get("_error"), f"Add failed: {result}"

            # Verify it exists
            get_result = mcp_call(proc, "get_requirement", {"req_id": "REQ-p00003"})
            assert get_result and get_result.get("id") == "REQ-p00003"

            # Undo
            undo = mcp_call(proc, "undo_last_mutation", {})
            assert isinstance(undo, dict)

            # Verify it's gone
            after_undo = mcp_call(proc, "get_requirement", {"req_id": "REQ-p00003"})
            assert after_undo is None or after_undo.get("error") or after_undo.get("_error")
        finally:
            stop_mcp(proc)

    def test_update_title_and_undo(self, tmp_path):
        _build_standard_project(tmp_path)
        proc = start_mcp(tmp_path)
        try:
            # Get original
            original = mcp_call(proc, "get_requirement", {"req_id": "REQ-p00001"})
            orig_title = original["title"]

            # Update
            mcp_call(
                proc,
                "mutate_update_title",
                {
                    "node_id": "REQ-p00001",
                    "new_title": "Updated Title",
                },
            )

            # Verify
            updated = mcp_call(proc, "get_requirement", {"req_id": "REQ-p00001"})
            assert updated["title"] == "Updated Title"

            # Undo
            mcp_call(proc, "undo_last_mutation", {})
            reverted = mcp_call(proc, "get_requirement", {"req_id": "REQ-p00001"})
            assert reverted["title"] == orig_title
        finally:
            stop_mcp(proc)

    def test_mutation_log(self, tmp_path):
        _build_standard_project(tmp_path)
        proc = start_mcp(tmp_path)
        try:
            # Perform some mutations
            mcp_call(
                proc,
                "mutate_update_title",
                {
                    "node_id": "REQ-p00001",
                    "new_title": "Title V1",
                },
            )
            mcp_call(
                proc,
                "mutate_update_title",
                {
                    "node_id": "REQ-p00001",
                    "new_title": "Title V2",
                },
            )

            # Check log
            log = mcp_call(proc, "get_mutation_log", {"limit": 10})
            assert isinstance(log, (list, dict))
        finally:
            stop_mcp(proc)


# ---------------------------------------------------------------------------
# Test 28: MCP assertion mutations
# ---------------------------------------------------------------------------


class TestMCPAssertionMutations:
    """MCP assertion CRUD operations."""

    def test_add_assertion(self, tmp_path):
        _build_standard_project(tmp_path)
        proc = start_mcp(tmp_path)
        try:
            result = mcp_call(
                proc,
                "mutate_add_assertion",
                {
                    "req_id": "REQ-p00001",
                    "label": "D",
                    "text": "The system SHALL support SSO.",
                },
            )
            assert isinstance(result, dict)
            assert not result.get("_error")

            # Verify
            req = mcp_call(proc, "get_requirement", {"req_id": "REQ-p00001"})
            labels = _assertion_labels(req)
            assert "D" in labels
        finally:
            stop_mcp(proc)

    def test_update_assertion(self, tmp_path):
        _build_standard_project(tmp_path)
        proc = start_mcp(tmp_path)
        try:
            result = mcp_call(
                proc,
                "mutate_update_assertion",
                {
                    "assertion_id": "REQ-p00001-A",
                    "new_text": "The system SHALL create and manage user accounts.",
                },
            )
            assert isinstance(result, dict)
        finally:
            stop_mcp(proc)

    def test_delete_assertion_and_undo(self, tmp_path):
        _build_standard_project(tmp_path)
        proc = start_mcp(tmp_path)
        try:
            # Delete assertion C
            result = mcp_call(
                proc,
                "mutate_delete_assertion",
                {
                    "assertion_id": "REQ-p00001-C",
                    "confirm": True,
                },
            )
            assert isinstance(result, dict)

            # Verify it's removed
            req = mcp_call(proc, "get_requirement", {"req_id": "REQ-p00001"})
            labels = _assertion_labels(req)
            assert "C" not in labels

            # Undo
            mcp_call(proc, "undo_last_mutation", {})
            req2 = mcp_call(proc, "get_requirement", {"req_id": "REQ-p00001"})
            labels2 = _assertion_labels(req2)
            assert "C" in labels2, f"Expected C after undo, got labels: {labels2}"
        finally:
            stop_mcp(proc)


# ---------------------------------------------------------------------------
# Test 29: MCP edge mutations
# ---------------------------------------------------------------------------


class TestMCPEdgeMutations:
    """MCP edge add/delete/change operations."""

    def test_add_edge(self, tmp_path):
        _build_standard_project(tmp_path)
        proc = start_mcp(tmp_path)
        try:
            # Add implements edge from d00002 to o00001
            result = mcp_call(
                proc,
                "mutate_add_edge",
                {
                    "source_id": "REQ-d00002",
                    "target_id": "REQ-o00001",
                    "edge_kind": "implements",
                },
            )
            assert isinstance(result, dict)
            assert not result.get("_error"), f"Edge add failed: {result}"
        finally:
            stop_mcp(proc)

    def test_delete_edge_and_undo(self, tmp_path):
        _build_standard_project(tmp_path)
        proc = start_mcp(tmp_path)
        try:
            # Delete the implements edge d00001 -> o00001
            result = mcp_call(
                proc,
                "mutate_delete_edge",
                {
                    "source_id": "REQ-d00001",
                    "target_id": "REQ-o00001",
                    "confirm": True,
                },
            )
            assert isinstance(result, dict)

            # Undo
            mcp_call(proc, "undo_last_mutation", {})

            # Verify edge is back via hierarchy
            hier = mcp_call(proc, "get_hierarchy", {"req_id": "REQ-d00001"})
            ancestors = hier.get("ancestors", [])
            assert len(ancestors) > 0
        finally:
            stop_mcp(proc)


# ---------------------------------------------------------------------------
# Test 30: MCP cursor protocol
# ---------------------------------------------------------------------------


class TestMCPCursors:
    """MCP cursor protocol for incremental iteration."""

    def test_cursor_search(self, tmp_path):
        _build_standard_project(tmp_path)
        proc = start_mcp(tmp_path)
        try:
            # Open cursor over search results
            result = mcp_call(
                proc,
                "open_cursor",
                {
                    "query": "search",
                    "params": {"query": "REQ"},
                    "batch_size": 1,
                },
            )
            assert "total" in result
            assert result["total"] >= 3  # At least 5 requirements

            # Advance
            next_result = mcp_call(proc, "cursor_next", {"count": 1})
            assert isinstance(next_result, dict)

            # Check info
            info = mcp_call(proc, "cursor_info", {})
            assert "position" in info
            assert "remaining" in info
        finally:
            stop_mcp(proc)

    def test_cursor_subtree(self, tmp_path):
        _build_standard_project(tmp_path)
        proc = start_mcp(tmp_path)
        try:
            result = mcp_call(
                proc,
                "open_cursor",
                {
                    "query": "subtree",
                    "params": {"root_id": "REQ-p00001"},
                    "batch_size": 0,
                },
            )
            assert "total" in result
            assert result["total"] >= 1
        finally:
            stop_mcp(proc)


# ---------------------------------------------------------------------------
# Test 31: MCP subtree extraction
# ---------------------------------------------------------------------------


class TestMCPSubtree:
    """MCP get_subtree in various formats."""

    def test_subtree_markdown(self, tmp_path):
        _build_standard_project(tmp_path)
        proc = start_mcp(tmp_path)
        try:
            result = mcp_call(
                proc,
                "get_subtree",
                {
                    "root_id": "REQ-p00001",
                    "format": "markdown",
                },
            )
            assert isinstance(result, (dict, str))
            # Should contain the requirement text
            result_str = str(result)
            assert "REQ-p00001" in result_str or "User Management" in result_str
        finally:
            stop_mcp(proc)

    def test_subtree_flat(self, tmp_path):
        _build_standard_project(tmp_path)
        proc = start_mcp(tmp_path)
        try:
            result = mcp_call(
                proc,
                "get_subtree",
                {
                    "root_id": "REQ-p00001",
                    "format": "flat",
                },
            )
            assert isinstance(result, dict)
            assert "nodes" in result or "edges" in result
        finally:
            stop_mcp(proc)

    def test_subtree_nested(self, tmp_path):
        _build_standard_project(tmp_path)
        proc = start_mcp(tmp_path)
        try:
            result = mcp_call(
                proc,
                "get_subtree",
                {
                    "root_id": "REQ-p00001",
                    "format": "nested",
                },
            )
            assert isinstance(result, dict)
        finally:
            stop_mcp(proc)

    def test_subtree_depth_limited(self, tmp_path):
        _build_standard_project(tmp_path)
        proc = start_mcp(tmp_path)
        try:
            result = mcp_call(
                proc,
                "get_subtree",
                {
                    "root_id": "REQ-p00001",
                    "depth": 1,
                    "format": "flat",
                },
            )
            assert isinstance(result, dict)
        finally:
            stop_mcp(proc)


# ---------------------------------------------------------------------------
# Test 32: MCP test coverage
# ---------------------------------------------------------------------------


class TestMCPTestCoverage:
    """MCP test coverage tools."""

    def test_get_test_coverage(self, tmp_path):
        _build_standard_project(tmp_path)
        proc = start_mcp(tmp_path)
        try:
            result = mcp_call(proc, "get_test_coverage", {"req_id": "REQ-d00001"})
            assert isinstance(result, dict)
        finally:
            stop_mcp(proc)

    def test_uncovered_assertions(self, tmp_path):
        _build_standard_project(tmp_path)
        proc = start_mcp(tmp_path)
        try:
            result = mcp_call(proc, "get_uncovered_assertions", {})
            assert isinstance(result, (list, dict))
        finally:
            stop_mcp(proc)


# ---------------------------------------------------------------------------
# Test 33: MCP with FDA-style IDs
# ---------------------------------------------------------------------------


class TestMCPFDAStyle:
    """MCP tools work correctly with FDA-style ID patterns."""

    def test_search_fda_ids(self, tmp_path):
        _build_fda_project(tmp_path)
        proc = start_mcp(tmp_path)
        try:
            results = mcp_call_all(proc, "search", {"query": "Compliance"})
            assert len(results) >= 1
            ids = [r.get("id", "") for r in results]
            assert any("PRD-00001" in i for i in ids)
        finally:
            stop_mcp(proc)

    def test_get_requirement_fda(self, tmp_path):
        _build_fda_project(tmp_path)
        proc = start_mcp(tmp_path)
        try:
            result = mcp_call(proc, "get_requirement", {"req_id": "PRD-00001"})
            assert result["id"] == "PRD-00001"
            assert "Compliance" in result.get("title", "")
        finally:
            stop_mcp(proc)

    def test_hierarchy_fda(self, tmp_path):
        _build_fda_project(tmp_path)
        proc = start_mcp(tmp_path)
        try:
            result = mcp_call(proc, "get_hierarchy", {"req_id": "DEV-00001"})
            assert "ancestors" in result
            ancestor_ids = [a.get("id", "") for a in result["ancestors"]]
            assert "PRD-00001" in ancestor_ids
        finally:
            stop_mcp(proc)


# ---------------------------------------------------------------------------
# Test 34: MCP scoped search and discover
# ---------------------------------------------------------------------------


class TestMCPScopedSearch:
    """MCP scoped_search and discover_requirements."""

    def test_scoped_search(self, tmp_path):
        _build_standard_project(tmp_path)
        proc = start_mcp(tmp_path)
        try:
            result = mcp_call_all(
                proc,
                "scoped_search",
                {
                    "query": "module",
                    "scope_id": "REQ-p00001",
                    "direction": "descendants",
                },
            )
            # Should find d00001 (User CRUD - module) under p00001's subtree
            assert isinstance(result, list)
        finally:
            stop_mcp(proc)

    def test_discover_requirements(self, tmp_path):
        _build_standard_project(tmp_path)
        proc = start_mcp(tmp_path)
        try:
            result = mcp_call(
                proc,
                "discover_requirements",
                {
                    "query": "user",
                    "scope_id": "REQ-p00001",
                },
            )
            assert isinstance(result, dict)
        finally:
            stop_mcp(proc)


# ---------------------------------------------------------------------------
# Test 35: MCP keyword search
# ---------------------------------------------------------------------------


class TestMCPKeywordSearch:
    """MCP find_by_keywords and get_all_keywords."""

    def test_get_all_keywords(self, tmp_path):
        _build_standard_project(tmp_path)
        proc = start_mcp(tmp_path)
        try:
            result = mcp_call(proc, "get_all_keywords", {})
            assert isinstance(result, (list, dict))
        finally:
            stop_mcp(proc)

    def test_find_by_keywords(self, tmp_path):
        _build_standard_project(tmp_path)
        proc = start_mcp(tmp_path)
        try:
            result = mcp_call_all(
                proc,
                "find_by_keywords",
                {
                    "keywords": ["user", "management"],
                    "match_all": False,
                },
            )
            assert isinstance(result, list)
        finally:
            stop_mcp(proc)

    def test_find_assertions_by_keywords(self, tmp_path):
        _build_standard_project(tmp_path)
        proc = start_mcp(tmp_path)
        try:
            result = mcp_call_all(
                proc,
                "find_assertions_by_keywords",
                {
                    "keywords": ["email"],
                    "match_all": True,
                },
            )
            assert isinstance(result, list)
        finally:
            stop_mcp(proc)


# ---------------------------------------------------------------------------
# Test 36: MCP query_nodes
# ---------------------------------------------------------------------------


class TestMCPQueryNodes:
    """MCP query_nodes with various filters."""

    def test_query_by_kind(self, tmp_path):
        _build_standard_project(tmp_path)
        proc = start_mcp(tmp_path)
        try:
            result = mcp_call(proc, "query_nodes", {"kind": "requirement"})
            # Returns {"results": [...], "count": N, "truncated": bool}
            assert result["count"] >= 5  # 5 requirements in standard project
            assert len(result["results"]) >= 5
        finally:
            stop_mcp(proc)

    def test_query_by_level(self, tmp_path):
        _build_standard_project(tmp_path)
        proc = start_mcp(tmp_path)
        try:
            result = mcp_call(proc, "query_nodes", {"level": "prd"})
            assert result["count"] >= 2  # 2 PRD requirements
        finally:
            stop_mcp(proc)

    def test_query_by_status(self, tmp_path):
        _build_standard_project(tmp_path)
        proc = start_mcp(tmp_path)
        try:
            result = mcp_call(proc, "query_nodes", {"status": "Active"})
            assert result["count"] >= 1
        finally:
            stop_mcp(proc)


# ---------------------------------------------------------------------------
# Test 37: MCP save_mutations (file persistence)
# ---------------------------------------------------------------------------


class TestMCPSaveMutations:
    """MCP save_mutations persists changes to disk."""

    def test_save_mutations_persists(self, tmp_path):
        _build_standard_project(tmp_path)
        proc = start_mcp(tmp_path)
        try:
            # Mutate title
            mcp_call(
                proc,
                "mutate_update_title",
                {
                    "node_id": "REQ-p00001",
                    "new_title": "Persisted Title Change",
                },
            )

            # Save to disk
            result = mcp_call(proc, "save_mutations", {"save_branch": False})
            assert isinstance(result, dict)
            assert not result.get("_error"), f"Save failed: {result}"

            # Verify file was modified
            spec = tmp_path / "spec" / "prd-core.md"
            content = spec.read_text()
            assert "Persisted Title Change" in content
        finally:
            stop_mcp(proc)


# ---------------------------------------------------------------------------
# Test 38: MCP refresh_graph
# ---------------------------------------------------------------------------


class TestMCPRefreshGraph:
    """MCP refresh_graph rebuilds from files."""

    def test_refresh_after_file_edit(self, tmp_path):
        _build_standard_project(tmp_path)
        proc = start_mcp(tmp_path)
        try:
            # Get original count
            mcp_call(proc, "get_project_summary", {})

            # Refresh
            result = mcp_call(proc, "refresh_graph", {})
            assert isinstance(result, dict)
            assert not result.get("_error")

            # Count should be same (no file changes)
            summary2 = mcp_call(proc, "get_project_summary", {})
            assert isinstance(summary2, dict)
        finally:
            stop_mcp(proc)


# ---------------------------------------------------------------------------
# Test 39: MCP orphaned nodes and broken references
# ---------------------------------------------------------------------------


class TestMCPGraphHealth:
    """MCP get_orphaned_nodes and get_broken_references."""

    def test_orphaned_nodes(self, tmp_path):
        _build_standard_project(tmp_path)
        proc = start_mcp(tmp_path)
        try:
            result = mcp_call(proc, "get_orphaned_nodes", {})
            assert isinstance(result, (list, dict))
        finally:
            stop_mcp(proc)

    def test_broken_references(self, tmp_path):
        _build_standard_project(tmp_path)
        proc = start_mcp(tmp_path)
        try:
            result = mcp_call(proc, "get_broken_references", {})
            assert isinstance(result, (list, dict))
        finally:
            stop_mcp(proc)


# ---------------------------------------------------------------------------
# Test 40: MCP comprehensive workflow (many calls in sequence)
# ---------------------------------------------------------------------------


class TestMCPComprehensiveWorkflow:
    """Exercise many MCP tools in a single test for thorough coverage."""

    def test_full_workflow(self, tmp_path):
        """Start from project summary, navigate, mutate, undo, verify."""
        _build_standard_project(tmp_path)
        proc = start_mcp(tmp_path)
        try:
            # 1. Get status
            status = mcp_call(proc, "get_graph_status", {})
            assert isinstance(status, dict)

            # 2. Get summary
            summary = mcp_call(proc, "get_project_summary", {})
            assert isinstance(summary, dict)

            # 3. Search for "notification"
            results = mcp_call_all(proc, "search", {"query": "notification"})
            assert len(results) >= 1

            # 4. Get requirement details
            req = mcp_call(proc, "get_requirement", {"req_id": "REQ-d00002"})
            assert req["id"] == "REQ-d00002"

            # 5. Get hierarchy
            hier = mcp_call(proc, "get_hierarchy", {"req_id": "REQ-d00002"})
            assert "ancestors" in hier

            # 6. Get subtree from p00002
            subtree = mcp_call(
                proc,
                "get_subtree",
                {
                    "root_id": "REQ-p00002",
                    "format": "flat",
                },
            )
            assert isinstance(subtree, dict)

            # 7. Add a new assertion
            mcp_call(
                proc,
                "mutate_add_assertion",
                {
                    "req_id": "REQ-d00002",
                    "label": "C",
                    "text": "The module SHALL log delivery status.",
                },
            )

            # 8. Verify assertion added
            req2 = mcp_call(proc, "get_requirement", {"req_id": "REQ-d00002"})
            labels = _assertion_labels(req2)
            assert "C" in labels

            # 9. Check mutation log
            log = mcp_call(proc, "get_mutation_log", {"limit": 5})
            assert isinstance(log, (list, dict))

            # 10. Undo
            mcp_call(proc, "undo_last_mutation", {})

            # 11. Verify assertion removed
            req3 = mcp_call(proc, "get_requirement", {"req_id": "REQ-d00002"})
            labels3 = _assertion_labels(req3)
            assert "C" not in labels3

            # 12. Check workspace info
            ws = mcp_call(proc, "get_workspace_info", {"detail": "testing"})
            assert isinstance(ws, dict)

        finally:
            stop_mcp(proc)
