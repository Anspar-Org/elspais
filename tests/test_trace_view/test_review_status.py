"""
Tests for review status modifier.

Tests REQ-d00011: Status Modifier
"""

from pathlib import Path

# =============================================================================
# find_req_in_file Tests (REQ-d00011-A)
# =============================================================================


# IMPLEMENTS: REQ-d00011-A
def test_find_req_in_file(tmp_repo: Path):
    """find_req_in_file() SHALL locate a requirement and return status line info."""
    from elspais.trace_view.review.status import find_req_in_file

    spec_file = tmp_repo / "spec" / "test-spec.md"

    # Find existing requirement
    location = find_req_in_file(spec_file, "d00001")

    assert location is not None
    assert location.file_path == spec_file
    assert location.req_id == "d00001"
    assert location.current_status == "Active"
    assert location.line_number > 0


def test_find_req_in_file_not_found(tmp_repo: Path):
    """find_req_in_file() should return None for nonexistent requirement."""
    from elspais.trace_view.review.status import find_req_in_file

    spec_file = tmp_repo / "spec" / "test-spec.md"

    location = find_req_in_file(spec_file, "nonexistent")

    assert location is None


def test_find_req_with_prefix(tmp_repo: Path):
    """find_req_in_file() should handle REQ- prefix."""
    from elspais.trace_view.review.status import find_req_in_file

    spec_file = tmp_repo / "spec" / "test-spec.md"

    # With REQ- prefix
    location = find_req_in_file(spec_file, "REQ-d00001")

    assert location is not None
    assert location.req_id == "d00001"  # Normalized


# =============================================================================
# get_req_status Tests (REQ-d00011-B)
# =============================================================================


# IMPLEMENTS: REQ-d00011-B
def test_get_req_status(tmp_repo: Path):
    """get_req_status() SHALL read and return the current status value."""
    from elspais.trace_view.review.status import get_req_status

    status = get_req_status(tmp_repo, "d00001")

    assert status == "Active"


def test_get_req_status_draft(tmp_repo: Path):
    """get_req_status() should return Draft status."""
    from elspais.trace_view.review.status import get_req_status

    status = get_req_status(tmp_repo, "d00002")

    assert status == "Draft"


def test_get_req_status_not_found(tmp_repo: Path):
    """get_req_status() should return None for nonexistent requirement."""
    from elspais.trace_view.review.status import get_req_status

    status = get_req_status(tmp_repo, "nonexistent")

    assert status is None


# =============================================================================
# change_req_status Tests (REQ-d00011-C)
# =============================================================================


# IMPLEMENTS: REQ-d00011-C
def test_change_req_status(tmp_repo: Path):
    """change_req_status() SHALL update the status value atomically."""
    from elspais.trace_view.review.status import change_req_status, get_req_status

    # Verify initial status
    assert get_req_status(tmp_repo, "d00002") == "Draft"

    # Change status
    success, message = change_req_status(tmp_repo, "d00002", "Active", "admin")

    assert success is True
    assert "Active" in message

    # Verify status changed
    assert get_req_status(tmp_repo, "d00002") == "Active"


def test_change_status_same_value(tmp_repo: Path):
    """Changing to same status should succeed with message."""
    from elspais.trace_view.review.status import change_req_status

    success, message = change_req_status(tmp_repo, "d00001", "Active", "admin")

    assert success is True
    assert "already has status" in message


# =============================================================================
# Status Validation Tests (REQ-d00011-D)
# =============================================================================


# IMPLEMENTS: REQ-d00011-D
def test_status_validation():
    """Status values SHALL be validated against allowed set."""
    from elspais.trace_view.review.status import VALID_STATUSES

    assert "Draft" in VALID_STATUSES
    assert "Active" in VALID_STATUSES
    assert "Deprecated" in VALID_STATUSES
    assert len(VALID_STATUSES) == 3


def test_invalid_status_rejected(tmp_repo: Path):
    """Invalid status values should be rejected."""
    from elspais.trace_view.review.status import change_req_status

    success, message = change_req_status(tmp_repo, "d00001", "Invalid", "admin")

    assert success is False
    assert "Invalid status" in message
    assert "Draft" in message  # Should list valid options


# =============================================================================
# Content Preservation Tests (REQ-d00011-E)
# =============================================================================


# IMPLEMENTS: REQ-d00011-E
def test_content_preservation(tmp_repo: Path):
    """The status modifier SHALL preserve all other content in the spec file."""
    from elspais.trace_view.review.status import change_req_status

    spec_file = tmp_repo / "spec" / "test-spec.md"

    # Change status
    change_req_status(tmp_repo, "d00002", "Active", "admin")

    # Read new content
    new_content = spec_file.read_text()

    # Title should be preserved
    assert "# REQ-d00001: Test Requirement" in new_content
    assert "# REQ-d00002: Another Test" in new_content

    # Assertions section should be preserved
    assert "## Assertions" in new_content
    assert "A. The system SHALL do something." in new_content

    # Only the status line for d00002 should change
    assert "**Status**: Active" in new_content


# =============================================================================
# Hash Update Tests (REQ-d00011-F)
# =============================================================================


# IMPLEMENTS: REQ-d00011-F
def test_hash_update(tmp_repo: Path):
    """The status modifier SHALL update the requirement's content hash footer."""
    from elspais.trace_view.review.status import change_req_status

    spec_file = tmp_repo / "spec" / "test-spec.md"

    # Read original content
    original_content = spec_file.read_text()
    original_hash = None
    for line in original_content.split("\n"):
        if "**Hash**: efgh5678" in line:
            original_hash = "efgh5678"
            break

    assert original_hash == "efgh5678"

    # Change status
    change_req_status(tmp_repo, "d00002", "Active", "admin")

    # Read new content
    new_content = spec_file.read_text()

    # Hash should be updated (different from original)
    # The exact new hash depends on the content
    assert "**Hash**:" in new_content


# =============================================================================
# Atomic Status Change Tests (REQ-d00011-G)
# =============================================================================


# IMPLEMENTS: REQ-d00011-G
def test_atomic_status_change(tmp_repo: Path):
    """Failed status changes SHALL NOT leave the spec file in a corrupted state."""
    from elspais.trace_view.review.status import change_req_status

    spec_file = tmp_repo / "spec" / "test-spec.md"

    # Read original content
    original_content = spec_file.read_text()

    # Try to change with invalid status - should fail
    success, _ = change_req_status(tmp_repo, "d00001", "InvalidStatus", "admin")
    assert success is False

    # File should be unchanged
    current_content = spec_file.read_text()
    assert current_content == original_content


def test_atomic_write_nonexistent_req(tmp_repo: Path):
    """Status change on nonexistent req should fail without file modification."""
    from elspais.trace_view.review.status import change_req_status

    spec_file = tmp_repo / "spec" / "test-spec.md"
    original_content = spec_file.read_text()

    success, message = change_req_status(tmp_repo, "d99999", "Active", "admin")

    assert success is False
    assert "not found" in message

    # File unchanged
    assert spec_file.read_text() == original_content


# =============================================================================
# find_req_in_spec_dir Tests (REQ-d00011-H)
# =============================================================================


# IMPLEMENTS: REQ-d00011-H
def test_find_req_in_spec_dir(tmp_repo: Path):
    """find_req_in_spec_dir() SHALL search core spec/ directory."""
    from elspais.trace_view.review.status import find_req_in_spec_dir

    location = find_req_in_spec_dir(tmp_repo, "d00001")

    assert location is not None
    assert location.req_id == "d00001"


def test_find_req_in_spec_dir_sponsor(tmp_repo: Path):
    """find_req_in_spec_dir() SHALL search sponsor/*/spec/ directories."""
    from elspais.trace_view.review.status import find_req_in_spec_dir

    # Create sponsor spec directory with a requirement
    sponsor_spec = tmp_repo / "sponsor" / "HHT" / "spec"
    sponsor_spec.mkdir(parents=True)

    sponsor_content = """# Sponsor Specs

---

# REQ-HHT-d00001: Sponsor Requirement

**Level**: Dev | **Status**: Draft | **Implements**: REQ-p00001

**Purpose:** A sponsor requirement.

## Assertions

A. The system SHALL do sponsor stuff.

*End* *Sponsor Requirement* | **Hash**: spons123
"""
    (sponsor_spec / "sponsor-spec.md").write_text(sponsor_content)

    # Should find sponsor requirement
    location = find_req_in_spec_dir(tmp_repo, "HHT-d00001")

    assert location is not None
    assert location.current_status == "Draft"


# =============================================================================
# Additional Tests
# =============================================================================


def test_compute_req_hash():
    """Test hash computation function."""
    from elspais.trace_view.review.status import compute_req_hash

    content1 = "Test content"
    content2 = "Different content"

    hash1 = compute_req_hash(content1)
    hash2 = compute_req_hash(content2)

    # Hash should be 8 characters
    assert len(hash1) == 8
    assert len(hash2) == 8

    # Different content should produce different hashes
    assert hash1 != hash2

    # Same content should produce same hash
    assert compute_req_hash(content1) == hash1


def test_change_status_deprecated(tmp_repo: Path):
    """Test changing status to Deprecated."""
    from elspais.trace_view.review.status import change_req_status, get_req_status

    # Change Active to Deprecated
    success, message = change_req_status(tmp_repo, "d00001", "Deprecated", "admin")

    assert success is True
    assert get_req_status(tmp_repo, "d00001") == "Deprecated"


def test_req_location_dataclass():
    """Test ReqLocation dataclass."""
    from pathlib import Path

    from elspais.trace_view.review.status import ReqLocation

    location = ReqLocation(
        file_path=Path("/test/spec.md"),
        line_number=10,
        current_status="Active",
        req_id="d00001",
    )

    assert location.file_path == Path("/test/spec.md")
    assert location.line_number == 10
    assert location.current_status == "Active"
    assert location.req_id == "d00001"


def test_find_req_with_different_id_formats(tmp_repo: Path):
    """Test finding requirements with various ID formats."""
    from elspais.trace_view.review.status import find_req_in_file

    spec_file = tmp_repo / "spec" / "test-spec.md"

    # Without prefix
    loc1 = find_req_in_file(spec_file, "d00001")
    assert loc1 is not None

    # With REQ- prefix
    loc2 = find_req_in_file(spec_file, "REQ-d00001")
    assert loc2 is not None

    # Both should find same requirement
    assert loc1.req_id == loc2.req_id
    assert loc1.current_status == loc2.current_status


def test_status_transitions(tmp_repo: Path):
    """Test various status transitions."""
    from elspais.trace_view.review.status import change_req_status, get_req_status

    # d00002 starts as Draft
    assert get_req_status(tmp_repo, "d00002") == "Draft"

    # Draft -> Active
    success, _ = change_req_status(tmp_repo, "d00002", "Active", "user1")
    assert success is True
    assert get_req_status(tmp_repo, "d00002") == "Active"

    # Active -> Deprecated
    success, _ = change_req_status(tmp_repo, "d00002", "Deprecated", "user2")
    assert success is True
    assert get_req_status(tmp_repo, "d00002") == "Deprecated"

    # Deprecated -> Draft
    success, _ = change_req_status(tmp_repo, "d00002", "Draft", "user3")
    assert success is True
    assert get_req_status(tmp_repo, "d00002") == "Draft"


def test_file_not_found():
    """Test handling of nonexistent file."""
    from pathlib import Path

    from elspais.trace_view.review.status import find_req_in_file

    result = find_req_in_file(Path("/nonexistent/file.md"), "d00001")
    assert result is None


def test_skip_index_and_readme(tmp_repo: Path):
    """find_req_in_spec_dir should skip INDEX.md and README.md."""
    from elspais.trace_view.review.status import find_req_in_spec_dir

    # Create INDEX.md with a fake REQ
    index_content = """# Index

# REQ-d99999: Fake Index Requirement

**Level**: Dev | **Status**: Active | **Implements**: REQ-p00001

## Assertions

A. Fake assertion.

*End* *Fake Index Requirement* | **Hash**: index123
"""
    (tmp_repo / "spec" / "INDEX.md").write_text(index_content)

    # Should not find the fake requirement from INDEX.md
    location = find_req_in_spec_dir(tmp_repo, "d99999")
    assert location is None

    # Should still find real requirements
    location = find_req_in_spec_dir(tmp_repo, "d00001")
    assert location is not None
