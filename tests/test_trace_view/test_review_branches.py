"""
Tests for review git branch management.

Tests REQ-d00009: Git Branch Management
"""

from pathlib import Path

import pytest

# =============================================================================
# Branch Naming Convention Tests (REQ-d00009-A)
# =============================================================================


# IMPLEMENTS: REQ-d00009-A
def test_branch_naming_convention():
    """Review branches SHALL follow naming convention: reviews/{package_id}/{username}."""
    from elspais.trace_view.review.branches import (
        REVIEW_BRANCH_PREFIX,
        get_review_branch_name,
    )

    assert REVIEW_BRANCH_PREFIX == "reviews/"

    branch = get_review_branch_name("default", "alice")
    assert branch.startswith("reviews/")
    assert "default" in branch
    assert "alice" in branch


# =============================================================================
# get_review_branch_name Tests (REQ-d00009-B)
# =============================================================================


# IMPLEMENTS: REQ-d00009-B
def test_get_review_branch_name():
    """get_review_branch_name() SHALL return formatted branch name."""
    from elspais.trace_view.review.branches import get_review_branch_name

    # Basic case
    result = get_review_branch_name("default", "alice")
    assert result == "reviews/default/alice"

    # With special characters - should be sanitized
    result = get_review_branch_name("q1-review", "bob")
    assert result == "reviews/q1-review/bob"

    # Spaces should be replaced with hyphens
    result = get_review_branch_name("my package", "john doe")
    assert "reviews/" in result
    assert " " not in result


# =============================================================================
# parse_review_branch_name Tests (REQ-d00009-C)
# =============================================================================


# IMPLEMENTS: REQ-d00009-C
def test_parse_review_branch_name():
    """parse_review_branch_name() SHALL extract (package_id, username)."""
    from elspais.trace_view.review.branches import parse_review_branch_name

    # Valid review branch
    result = parse_review_branch_name("reviews/default/alice")
    assert result == ("default", "alice")

    result = parse_review_branch_name("reviews/q1-review/bob")
    assert result == ("q1-review", "bob")

    # Invalid branches
    result = parse_review_branch_name("main")
    assert result is None

    result = parse_review_branch_name("feature/something")
    assert result is None

    result = parse_review_branch_name("reviews/default")  # Missing user
    assert result is None


# =============================================================================
# is_review_branch Tests (REQ-d00009-D)
# =============================================================================


# IMPLEMENTS: REQ-d00009-D
def test_is_review_branch():
    """is_review_branch() SHALL return True only for valid review branches."""
    from elspais.trace_view.review.branches import is_review_branch

    # Valid review branches
    assert is_review_branch("reviews/default/alice") is True
    assert is_review_branch("reviews/q1-review/bob") is True

    # Invalid branches
    assert is_review_branch("main") is False
    assert is_review_branch("feature/test") is False
    assert is_review_branch("reviews/default") is False  # Missing user
    assert is_review_branch("reviews/") is False
    assert is_review_branch("") is False


# =============================================================================
# list_package_branches Tests (REQ-d00009-E)
# =============================================================================


# IMPLEMENTS: REQ-d00009-E
@pytest.mark.slow
def test_list_package_branches(tmp_git_repo: Path):
    """list_package_branches() SHALL return all branch names for a package."""
    from elspais.trace_view.review.branches import (
        create_review_branch,
        list_package_branches,
    )

    # Create some review branches
    create_review_branch(tmp_git_repo, "default", "alice")
    create_review_branch(tmp_git_repo, "default", "bob")
    create_review_branch(tmp_git_repo, "other-pkg", "charlie")

    # List default package branches
    branches = list_package_branches(tmp_git_repo, "default")

    assert len(branches) == 2
    assert "reviews/default/alice" in branches
    assert "reviews/default/bob" in branches
    assert "reviews/other-pkg/charlie" not in branches


# =============================================================================
# get_current_package_context Tests (REQ-d00009-F)
# =============================================================================


# IMPLEMENTS: REQ-d00009-F
@pytest.mark.slow
def test_get_current_package_context(tmp_git_repo: Path):
    """get_current_package_context() SHALL return (package_id, username) on review branch."""
    from elspais.trace_view.review.branches import (
        checkout_review_branch,
        create_review_branch,
        get_current_package_context,
    )

    # On main branch - should return (None, None)
    result = get_current_package_context(tmp_git_repo)
    assert result == (None, None)

    # Create and checkout a review branch
    create_review_branch(tmp_git_repo, "default", "alice")
    checkout_review_branch(tmp_git_repo, "default", "alice")

    result = get_current_package_context(tmp_git_repo)
    assert result == ("default", "alice")


# =============================================================================
# commit_and_push_reviews Tests (REQ-d00009-G)
# =============================================================================


# IMPLEMENTS: REQ-d00009-G
@pytest.mark.slow
def test_commit_and_push_reviews(tmp_git_repo: Path):
    """commit_and_push_reviews() SHALL commit all changes in .reviews/."""
    from elspais.trace_view.review.branches import (
        commit_and_push_reviews,
        has_reviews_changes,
    )

    # Create some review data
    reviews_dir = tmp_git_repo / ".reviews"
    (reviews_dir / "test.json").write_text('{"test": true}')

    # Should have changes
    assert has_reviews_changes(tmp_git_repo) is True

    # Commit (no remote, so push will be skipped)
    success, message = commit_and_push_reviews(tmp_git_repo, "Test commit", "testuser")

    assert success is True
    assert "Committed" in message

    # Should no longer have uncommitted changes
    assert has_reviews_changes(tmp_git_repo) is False


# =============================================================================
# Conflict Detection Tests (REQ-d00009-H)
# =============================================================================


# IMPLEMENTS: REQ-d00009-H
@pytest.mark.slow
def test_conflict_detection(tmp_git_repo: Path):
    """Branch operations SHALL detect conflicts via has_conflicts()."""
    from elspais.trace_view.review.branches import (
        has_conflicts,
        has_uncommitted_changes,
    )

    # No uncommitted changes initially
    assert has_uncommitted_changes(tmp_git_repo) is False

    # Create uncommitted changes
    (tmp_git_repo / "new_file.txt").write_text("content")
    assert has_uncommitted_changes(tmp_git_repo) is True

    # No conflicts (no merge in progress)
    assert has_conflicts(tmp_git_repo) is False


# =============================================================================
# fetch_package_branches Tests (REQ-d00009-I)
# =============================================================================


# IMPLEMENTS: REQ-d00009-I
@pytest.mark.slow
def test_fetch_package_branches(tmp_git_repo: Path):
    """fetch_package_branches() SHALL fetch all remote branches for a package."""
    from elspais.trace_view.review.branches import fetch_package_branches

    # No remote configured, so should return empty list
    branches = fetch_package_branches(tmp_git_repo, "default")
    assert branches == []


# =============================================================================
# Branch Cleanup Safety Tests (REQ-d00009-J)
# =============================================================================


# IMPLEMENTS: REQ-d00009-J
@pytest.mark.slow
def test_branch_cleanup_safety(tmp_git_repo: Path):
    """Branch cleanup SHALL never delete current branch."""
    from elspais.trace_view.review.branches import (
        checkout_review_branch,
        create_review_branch,
        delete_review_branch,
        get_current_branch,
    )

    # Create and checkout a review branch
    create_review_branch(tmp_git_repo, "default", "alice")
    checkout_review_branch(tmp_git_repo, "default", "alice")

    current = get_current_branch(tmp_git_repo)
    assert current == "reviews/default/alice"

    # Try to delete current branch - should fail
    success, message = delete_review_branch(tmp_git_repo, "reviews/default/alice")
    assert success is False
    assert "current branch" in message.lower()


# =============================================================================
# Additional Branch Tests
# =============================================================================


@pytest.mark.slow
def test_create_review_branch(tmp_git_repo: Path):
    """Test creating a review branch."""
    from elspais.trace_view.review.branches import (
        branch_exists,
        create_review_branch,
    )

    branch_name = create_review_branch(tmp_git_repo, "test-pkg", "testuser")

    assert branch_name == "reviews/test-pkg/testuser"
    assert branch_exists(tmp_git_repo, branch_name) is True


@pytest.mark.slow
def test_create_duplicate_branch_fails(tmp_git_repo: Path):
    """Creating a duplicate branch should raise ValueError."""
    from elspais.trace_view.review.branches import create_review_branch

    create_review_branch(tmp_git_repo, "default", "alice")

    with pytest.raises(ValueError, match="already exists"):
        create_review_branch(tmp_git_repo, "default", "alice")


@pytest.mark.slow
def test_checkout_nonexistent_branch(tmp_git_repo: Path):
    """Checkout of nonexistent branch should return False."""
    from elspais.trace_view.review.branches import checkout_review_branch

    result = checkout_review_branch(tmp_git_repo, "nonexistent", "user")
    assert result is False


@pytest.mark.slow
def test_get_head_commit_hash(tmp_git_repo: Path):
    """Test getting HEAD commit hash."""
    from elspais.trace_view.review.branches import (
        get_head_commit_hash,
        get_short_commit_hash,
    )

    full_hash = get_head_commit_hash(tmp_git_repo)
    assert full_hash is not None
    assert len(full_hash) == 40

    short_hash = get_short_commit_hash(tmp_git_repo)
    assert short_hash is not None
    assert len(short_hash) == 7
    assert full_hash.startswith(short_hash)


@pytest.mark.slow
def test_get_git_context(tmp_git_repo: Path):
    """Test getting git context for audit trail."""
    from elspais.trace_view.review.branches import get_git_context

    context = get_git_context(tmp_git_repo)

    assert "branchName" in context
    assert "commitHash" in context
    assert context["commitHash"] is not None


@pytest.mark.slow
def test_branch_info(tmp_git_repo: Path):
    """Test getting branch info."""
    from elspais.trace_view.review.branches import (
        create_review_branch,
        get_branch_info,
    )

    create_review_branch(tmp_git_repo, "default", "alice")

    info = get_branch_info(tmp_git_repo, "reviews/default/alice")

    assert info is not None
    assert info.name == "reviews/default/alice"
    assert info.package_id == "default"
    assert info.username == "alice"
    assert info.is_current is False
    assert info.last_commit_date is not None


@pytest.mark.slow
def test_list_local_review_branches(tmp_git_repo: Path):
    """Test listing all local review branches."""
    from elspais.trace_view.review.branches import (
        create_review_branch,
        list_local_review_branches,
    )

    create_review_branch(tmp_git_repo, "pkg1", "alice")
    create_review_branch(tmp_git_repo, "pkg2", "bob")

    all_branches = list_local_review_branches(tmp_git_repo)
    assert len(all_branches) == 2

    # Filter by user
    alice_branches = list_local_review_branches(tmp_git_repo, user="alice")
    assert len(alice_branches) == 1
    assert "alice" in alice_branches[0]


@pytest.mark.slow
def test_commit_reviews_no_changes(tmp_git_repo: Path):
    """Committing with no changes should succeed."""
    from elspais.trace_view.review.branches import commit_reviews

    result = commit_reviews(tmp_git_repo, "No changes", "testuser")
    assert result is True  # No changes to commit is success


def test_sanitize_branch_name():
    """Test branch name sanitization."""
    from elspais.trace_view.review.branches import _sanitize_branch_name

    # Basic sanitization
    assert _sanitize_branch_name("alice") == "alice"
    assert _sanitize_branch_name("Alice") == "alice"

    # Spaces to hyphens
    assert _sanitize_branch_name("john doe") == "john-doe"

    # Remove invalid characters
    assert _sanitize_branch_name("user@email.com") == "useremailcom"

    # Keep valid characters
    assert _sanitize_branch_name("user_123") == "user_123"
    assert _sanitize_branch_name("user-name") == "user-name"
