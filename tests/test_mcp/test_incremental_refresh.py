"""Tests for incremental graph refresh.

Tests the partial_refresh() method for incrementally updating the graph
when spec files change, rather than doing a full rebuild.
"""

import time
from pathlib import Path
from textwrap import dedent

import pytest

from elspais.mcp.context import WorkspaceContext


# --- Helper to create spec files ---


def create_spec_file(path: Path, content: str) -> None:
    """Create a spec file with given content."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dedent(content).strip() + "\n")


def create_config_file(path: Path) -> None:
    """Create a minimal .elspais.toml config."""
    path.write_text(
        dedent("""
        [project]
        name = "test-project"

        [directories]
        spec = "spec"

        [patterns]
        prefix = "REQ"
        """).strip()
        + "\n"
    )


# --- Fixtures ---


@pytest.fixture
def workspace_dir(tmp_path: Path) -> Path:
    """Create a workspace directory with config and spec files."""
    # Create config
    create_config_file(tmp_path / ".elspais.toml")

    # Create initial spec files
    spec_dir = tmp_path / "spec"
    spec_dir.mkdir()

    create_spec_file(
        spec_dir / "prd-auth.md",
        """
        # REQ-p00001: User Authentication

        **Level**: PRD | **Status**: Active

        ## Assertions

        A. Users SHALL be able to log in.
        B. Users SHALL be able to log out.

        *End* *User Authentication* | **Hash**: abcd1234
        """,
    )

    create_spec_file(
        spec_dir / "dev-auth.md",
        """
        # REQ-d00001: Password Hashing

        **Level**: Dev | **Status**: Active | **Implements**: REQ-p00001

        ## Assertions

        A. Passwords SHALL be hashed with bcrypt.

        *End* *Password Hashing* | **Hash**: efgh5678
        """,
    )

    return tmp_path


@pytest.fixture
def ctx(workspace_dir: Path) -> WorkspaceContext:
    """Create a WorkspaceContext for the workspace."""
    return WorkspaceContext.from_directory(workspace_dir)


# --- Test: partial_refresh with no existing graph ---


def test_partial_refresh_no_graph_does_full_build(ctx: WorkspaceContext) -> None:
    """partial_refresh() without existing graph does full build."""
    # No graph built yet
    assert ctx._graph_state is None

    # Call partial_refresh
    graph, validation = ctx.partial_refresh()

    # Should have built a full graph
    assert graph is not None
    assert ctx._graph_state is not None
    assert graph.find_by_id("REQ-p00001") is not None
    assert graph.find_by_id("REQ-d00001") is not None


# --- Test: partial_refresh with no changes ---


def test_partial_refresh_no_changes_returns_cached(ctx: WorkspaceContext) -> None:
    """partial_refresh() with no changes returns cached graph."""
    # Build initial graph
    graph1, _ = ctx.get_graph()
    built_at_1 = ctx.get_graph_built_at()

    # Wait a tiny bit to distinguish timestamps
    time.sleep(0.01)

    # Call partial_refresh with no changes
    graph2, _ = ctx.partial_refresh()
    built_at_2 = ctx.get_graph_built_at()

    # Should return same graph without rebuild
    assert graph2 is graph1
    assert built_at_2 == built_at_1


# --- Test: partial_refresh detects modified file ---


def test_partial_refresh_modified_file_is_reparsed(
    ctx: WorkspaceContext, workspace_dir: Path
) -> None:
    """partial_refresh() re-parses modified files."""
    # Build initial graph
    graph1, _ = ctx.get_graph()

    # Verify initial state
    req = graph1.find_by_id("REQ-p00001")
    assert req is not None
    assert req.requirement.title == "User Authentication"

    # Wait to ensure mtime changes
    time.sleep(0.1)

    # Modify the file
    spec_file = workspace_dir / "spec" / "prd-auth.md"
    create_spec_file(
        spec_file,
        """
        # REQ-p00001: User Auth Updated

        **Level**: PRD | **Status**: Active

        ## Assertions

        A. Users SHALL be able to log in.
        B. Users SHALL be able to log out.
        C. Users SHALL be able to reset password.

        *End* *User Auth Updated* | **Hash**: newh1234
        """,
    )

    # Call partial_refresh
    graph2, _ = ctx.partial_refresh()

    # Should have updated requirement
    req = graph2.find_by_id("REQ-p00001")
    assert req is not None
    assert req.requirement.title == "User Auth Updated"

    # Should have new assertion
    assert graph2.find_by_id("REQ-p00001-C") is not None

    # Unchanged requirement should still exist
    assert graph2.find_by_id("REQ-d00001") is not None


# --- Test: partial_refresh handles deleted file ---


def test_partial_refresh_deleted_file_removes_requirements(
    ctx: WorkspaceContext, workspace_dir: Path
) -> None:
    """partial_refresh() removes requirements from deleted files."""
    # Build initial graph
    graph1, _ = ctx.get_graph()

    # Verify initial state
    assert graph1.find_by_id("REQ-d00001") is not None
    initial_count = graph1.node_count()

    # Delete the file
    spec_file = workspace_dir / "spec" / "dev-auth.md"
    spec_file.unlink()

    # Call partial_refresh
    graph2, _ = ctx.partial_refresh()

    # Should have removed requirement
    assert graph2.find_by_id("REQ-d00001") is None
    assert graph2.find_by_id("REQ-d00001-A") is None

    # Other requirements still exist
    assert graph2.find_by_id("REQ-p00001") is not None

    # Node count should be lower
    assert graph2.node_count() < initial_count


# --- Test: partial_refresh handles new file ---


def test_partial_refresh_new_file_adds_requirements(
    ctx: WorkspaceContext, workspace_dir: Path
) -> None:
    """partial_refresh() adds requirements from new files."""
    # Build initial graph
    graph1, _ = ctx.get_graph()

    # Verify initial state
    assert graph1.find_by_id("REQ-o00001") is None

    # Wait to ensure mtime differs
    time.sleep(0.1)

    # Add a new file
    spec_file = workspace_dir / "spec" / "ops-deploy.md"
    create_spec_file(
        spec_file,
        """
        # REQ-o00001: Deployment Process

        **Level**: Ops | **Status**: Active | **Implements**: REQ-p00001

        ## Assertions

        A. Deployment SHALL be automated.

        *End* *Deployment Process* | **Hash**: ijkl9012
        """,
    )

    # Call partial_refresh
    graph2, _ = ctx.partial_refresh()

    # Should have new requirement
    assert graph2.find_by_id("REQ-o00001") is not None
    assert graph2.find_by_id("REQ-o00001-A") is not None

    # Should be linked to parent
    new_req = graph2.find_by_id("REQ-o00001")
    assert len(new_req.parents) > 0
    parent_ids = [p.id for p in new_req.parents]
    assert "REQ-p00001" in parent_ids


# --- Test: partial_refresh with explicit changed_files ---


def test_partial_refresh_explicit_changed_files(
    ctx: WorkspaceContext, workspace_dir: Path
) -> None:
    """partial_refresh() accepts explicit list of changed files."""
    # Build initial graph
    graph1, _ = ctx.get_graph()

    # Wait to ensure mtime differs
    time.sleep(0.1)

    # Modify both files
    create_spec_file(
        workspace_dir / "spec" / "prd-auth.md",
        """
        # REQ-p00001: User Auth Modified

        **Level**: PRD | **Status**: Active

        ## Assertions

        A. Users SHALL authenticate.

        *End* *User Auth Modified* | **Hash**: aaaa1111
        """,
    )

    create_spec_file(
        workspace_dir / "spec" / "dev-auth.md",
        """
        # REQ-d00001: Password Security

        **Level**: Dev | **Status**: Active | **Implements**: REQ-p00001

        ## Assertions

        A. Passwords SHALL be secure.

        *End* *Password Security* | **Hash**: bbbb2222
        """,
    )

    # Call partial_refresh with only one file
    graph2, _ = ctx.partial_refresh(
        changed_files=[workspace_dir / "spec" / "prd-auth.md"]
    )

    # Should have updated only the specified file
    prd_req = graph2.find_by_id("REQ-p00001")
    assert prd_req.requirement.title == "User Auth Modified"

    # The other file should NOT be updated (we didn't include it)
    # Note: This test verifies we only process specified files
    dev_req = graph2.find_by_id("REQ-d00001")
    assert dev_req.requirement.title == "Password Hashing"  # Original title


# --- Test: partial_refresh updates tracked files ---


def test_partial_refresh_updates_tracked_files(
    ctx: WorkspaceContext, workspace_dir: Path
) -> None:
    """partial_refresh() updates TrackedFile entries."""
    # Build initial graph
    ctx.get_graph()

    # Get initial tracked files
    tracked_files_1 = ctx.get_tracked_files()
    prd_file_path = (workspace_dir / "spec" / "prd-auth.md").resolve()
    initial_mtime = tracked_files_1[prd_file_path].mtime
    initial_node_ids = list(tracked_files_1[prd_file_path].node_ids)

    # Wait to ensure mtime differs
    time.sleep(0.1)

    # Modify the file to add an assertion
    create_spec_file(
        workspace_dir / "spec" / "prd-auth.md",
        """
        # REQ-p00001: User Authentication

        **Level**: PRD | **Status**: Active

        ## Assertions

        A. Users SHALL be able to log in.
        B. Users SHALL be able to log out.
        C. New assertion added.

        *End* *User Authentication* | **Hash**: newh1234
        """,
    )

    # Call partial_refresh
    ctx.partial_refresh()

    # Get updated tracked files
    tracked_files_2 = ctx.get_tracked_files()
    new_mtime = tracked_files_2[prd_file_path].mtime
    new_node_ids = tracked_files_2[prd_file_path].node_ids

    # mtime should be updated
    assert new_mtime > initial_mtime

    # Should have new assertion node
    assert "REQ-p00001-C" not in initial_node_ids
    assert "REQ-p00001-C" in new_node_ids


# --- Test: partial_refresh preserves relationships ---


def test_partial_refresh_preserves_cross_file_relationships(
    ctx: WorkspaceContext, workspace_dir: Path
) -> None:
    """partial_refresh() preserves relationships between files."""
    # Build initial graph
    graph1, _ = ctx.get_graph()

    # Verify initial relationship
    dev_req = graph1.find_by_id("REQ-d00001")
    assert len(dev_req.parents) > 0
    assert "REQ-p00001" in [p.id for p in dev_req.parents]

    # Wait to ensure mtime differs
    time.sleep(0.1)

    # Modify the parent file
    create_spec_file(
        workspace_dir / "spec" / "prd-auth.md",
        """
        # REQ-p00001: User Auth Updated

        **Level**: PRD | **Status**: Active

        ## Assertions

        A. Users SHALL authenticate.

        *End* *User Auth Updated* | **Hash**: updh1234
        """,
    )

    # Call partial_refresh
    graph2, _ = ctx.partial_refresh()

    # Relationship should still exist
    dev_req = graph2.find_by_id("REQ-d00001")
    assert len(dev_req.parents) > 0
    assert "REQ-p00001" in [p.id for p in dev_req.parents]

    # Parent should have child
    prd_req = graph2.find_by_id("REQ-p00001")
    child_ids = [c.id for c in prd_req.children if c.id.startswith("REQ-d")]
    assert "REQ-d00001" in child_ids


# --- Test: partial_refresh updates metrics ---


def test_partial_refresh_updates_metrics(
    ctx: WorkspaceContext, workspace_dir: Path
) -> None:
    """partial_refresh() recomputes metrics after changes."""
    # Build initial graph
    graph1, _ = ctx.get_graph()

    # Get initial assertion count for parent
    prd_req = graph1.find_by_id("REQ-p00001")
    initial_assertions = prd_req.metrics.get("total_assertions", 0)

    # Wait to ensure mtime differs
    time.sleep(0.1)

    # Modify to add more assertions
    create_spec_file(
        workspace_dir / "spec" / "prd-auth.md",
        """
        # REQ-p00001: User Authentication

        **Level**: PRD | **Status**: Active

        ## Assertions

        A. Users SHALL be able to log in.
        B. Users SHALL be able to log out.
        C. Users SHALL be able to reset password.
        D. Users SHALL be able to change email.

        *End* *User Authentication* | **Hash**: newh1234
        """,
    )

    # Call partial_refresh
    graph2, _ = ctx.partial_refresh()

    # Metrics should be updated
    prd_req = graph2.find_by_id("REQ-p00001")
    new_assertions = prd_req.metrics.get("total_assertions", 0)
    assert new_assertions > initial_assertions
    assert new_assertions == 4


# --- Test: _is_assertion_id helper ---


def test_is_assertion_id_uppercase_letters(ctx: WorkspaceContext) -> None:
    """_is_assertion_id correctly identifies uppercase letter assertions."""
    assert ctx._is_assertion_id("REQ-p00001-A") is True
    assert ctx._is_assertion_id("REQ-p00001-B") is True
    assert ctx._is_assertion_id("REQ-p00001-Z") is True


def test_is_assertion_id_numeric(ctx: WorkspaceContext) -> None:
    """_is_assertion_id correctly identifies numeric assertions."""
    assert ctx._is_assertion_id("REQ-p00001-1") is True
    assert ctx._is_assertion_id("REQ-p00001-01") is True
    assert ctx._is_assertion_id("REQ-p00001-99") is True


def test_is_assertion_id_requirement_ids(ctx: WorkspaceContext) -> None:
    """_is_assertion_id correctly identifies requirement IDs as non-assertions."""
    assert ctx._is_assertion_id("REQ-p00001") is False
    assert ctx._is_assertion_id("REQ-d00001") is False
    assert ctx._is_assertion_id("REQ-o00001") is False


def test_is_assertion_id_complex_patterns(ctx: WorkspaceContext) -> None:
    """_is_assertion_id handles complex ID patterns."""
    # Longer suffixes are not assertions
    assert ctx._is_assertion_id("REQ-p00001-ABC") is False
    assert ctx._is_assertion_id("REQ-p00001-100") is False

    # Mixed patterns
    assert ctx._is_assertion_id("TTN-REQ-p00001-A") is True
    assert ctx._is_assertion_id("TTN-REQ-p00001") is False


# --- Test: partial_refresh handles edge cases ---


def test_partial_refresh_empty_file(
    ctx: WorkspaceContext, workspace_dir: Path
) -> None:
    """partial_refresh() handles empty files gracefully."""
    # Build initial graph
    graph1, _ = ctx.get_graph()
    assert graph1.find_by_id("REQ-d00001") is not None

    # Wait to ensure mtime differs
    time.sleep(0.1)

    # Make file empty (no requirements)
    spec_file = workspace_dir / "spec" / "dev-auth.md"
    spec_file.write_text("# No Requirements Here\n")

    # Call partial_refresh
    graph2, _ = ctx.partial_refresh()

    # Requirement should be gone
    assert graph2.find_by_id("REQ-d00001") is None


def test_partial_refresh_multiple_changes_at_once(
    ctx: WorkspaceContext, workspace_dir: Path
) -> None:
    """partial_refresh() handles multiple simultaneous changes."""
    # Build initial graph
    ctx.get_graph()

    # Wait to ensure mtime differs
    time.sleep(0.1)

    # Make multiple changes at once:
    # 1. Modify existing file
    create_spec_file(
        workspace_dir / "spec" / "prd-auth.md",
        """
        # REQ-p00001: Updated Auth

        **Level**: PRD | **Status**: Active

        ## Assertions

        A. Updated assertion.

        *End* *Updated Auth* | **Hash**: mod12345
        """,
    )

    # 2. Delete a file
    (workspace_dir / "spec" / "dev-auth.md").unlink()

    # 3. Add a new file (use 'd' prefix for Dev level, which is recognized)
    create_spec_file(
        workspace_dir / "spec" / "new-feature.md",
        """
        # REQ-d00002: New Feature

        **Level**: Dev | **Status**: Active | **Implements**: REQ-p00001

        ## Assertions

        A. Feature SHALL work.

        *End* *New Feature* | **Hash**: new12345
        """,
    )

    # Call partial_refresh
    graph, _ = ctx.partial_refresh()

    # Verify all changes applied
    assert graph.find_by_id("REQ-p00001").requirement.title == "Updated Auth"
    assert graph.find_by_id("REQ-d00001") is None
    assert graph.find_by_id("REQ-d00002") is not None


def test_partial_refresh_requirements_cache_updated(
    ctx: WorkspaceContext, workspace_dir: Path
) -> None:
    """partial_refresh() updates the requirements cache."""
    # Build initial graph
    ctx.get_graph()

    # Get initial requirements cache
    reqs1 = ctx.get_requirements()
    assert "REQ-d00001" in reqs1

    # Wait to ensure mtime differs
    time.sleep(0.1)

    # Delete a file
    (workspace_dir / "spec" / "dev-auth.md").unlink()

    # Call partial_refresh
    ctx.partial_refresh()

    # Requirements cache should be updated
    reqs2 = ctx.get_requirements()
    assert "REQ-d00001" not in reqs2
