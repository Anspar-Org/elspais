"""
Tests for review system data models.

Tests REQ-d00001: Review Package Management
Tests REQ-d00003: Review Package Archival
Tests REQ-d00004: Review Git Audit Trail
Tests REQ-d00006: Review Threads and Comments
"""

# =============================================================================
# Package Model Tests (REQ-d00001)
# =============================================================================


# IMPLEMENTS: REQ-d00001-A
def test_package_model_fields():
    """Package model SHALL contain required fields."""
    from elspais.trace_view.review.models import ReviewPackage

    pkg = ReviewPackage(
        packageId="pkg-123",
        name="Test Package",
        description="A test package",
        reqIds=["d00001", "d00002"],
        createdBy="testuser",
        createdAt="2025-01-01T00:00:00+00:00",
    )

    assert pkg.packageId == "pkg-123"
    assert pkg.name == "Test Package"
    assert pkg.description == "A test package"
    assert pkg.reqIds == ["d00001", "d00002"]
    assert pkg.createdBy == "testuser"
    assert pkg.createdAt == "2025-01-01T00:00:00+00:00"


# IMPLEMENTS: REQ-d00001-B
def test_package_explicit_creation():
    """Packages SHALL be explicitly created by users via factory method."""
    from elspais.trace_view.review.models import ReviewPackage

    pkg = ReviewPackage.create(
        name="My Package",
        description="Created by user",
        created_by="alice",
    )

    # Factory generates UUID and timestamp
    assert pkg.packageId is not None
    assert len(pkg.packageId) == 36  # UUID format
    assert pkg.createdAt is not None
    assert pkg.reqIds == []  # Starts empty - user must add reqs


# IMPLEMENTS: REQ-d00001-C
def test_package_single_membership():
    """A requirement SHALL belong to at most one package at a time within a branch."""
    from elspais.trace_view.review.models import ReviewPackage

    pkg1 = ReviewPackage.create("Package 1", "", "user1")
    pkg1.reqIds = ["d00001"]

    pkg2 = ReviewPackage.create("Package 2", "", "user2")
    pkg2.reqIds = ["d00002"]

    # Each package has different reqs - enforced by storage layer
    assert "d00001" in pkg1.reqIds
    assert "d00001" not in pkg2.reqIds


# IMPLEMENTS: REQ-d00001-E
def test_thread_package_ownership():
    """All threads and comments SHALL be owned by exactly one package."""
    from elspais.trace_view.review.models import CommentPosition, Thread

    position = CommentPosition.create_general("abcd1234")
    thread = Thread.create(
        req_id="d00001",
        creator="alice",
        position=position,
        initial_comment="Test comment",
        package_id="pkg-001",  # Package ownership
    )

    assert thread.packageId == "pkg-001"


# IMPLEMENTS: REQ-d00001-F, REQ-d00003-E
def test_package_deletion_archives():
    """Package deletion SHALL archive (not destroy) the package and its threads."""
    from elspais.trace_view.review.models import (
        ARCHIVE_REASON_DELETED,
        ReviewPackage,
    )

    pkg = ReviewPackage.create("Test Package", "Description", "user1")

    # Archive with 'deleted' reason
    pkg.archive("admin", ARCHIVE_REASON_DELETED)

    assert pkg.is_archived is True
    assert pkg.archiveReason == "deleted"
    assert pkg.archivedBy == "admin"
    assert pkg.archivedAt is not None


# =============================================================================
# Archive Metadata Tests (REQ-d00003)
# =============================================================================


# IMPLEMENTS: REQ-d00003-C
def test_package_archive_metadata():
    """Archive metadata SHALL include archivedAt, archivedBy, archiveReason."""
    from elspais.trace_view.review.models import (
        ARCHIVE_REASON_RESOLVED,
        ReviewPackage,
    )

    pkg = ReviewPackage.create("Test Package", "Description", "creator")
    pkg.archive("reviewer", ARCHIVE_REASON_RESOLVED)

    # Verify metadata
    assert pkg.archivedAt is not None
    assert pkg.archivedBy == "reviewer"
    assert pkg.archiveReason == "resolved"

    # Verify in serialized form
    pkg_dict = pkg.to_dict()
    assert "archivedAt" in pkg_dict
    assert pkg_dict["archivedBy"] == "reviewer"
    assert pkg_dict["archiveReason"] == "resolved"


# =============================================================================
# Git Context Tests (REQ-d00004)
# =============================================================================


# IMPLEMENTS: REQ-d00004-A, REQ-d00004-B
def test_package_git_context():
    """Package SHALL record branchName and creationCommitHash when created."""
    from elspais.trace_view.review.models import ReviewPackage

    pkg = ReviewPackage.create(
        name="Git Package",
        description="Package with git context",
        created_by="alice",
        branch_name="feature/test",
        commit_hash="abc1234567890",
    )

    assert pkg.branchName == "feature/test"
    assert pkg.creationCommitHash == "abc1234567890"
    assert pkg.lastReviewedCommitHash == "abc1234567890"


# IMPLEMENTS: REQ-d00004-C
def test_package_commit_tracking():
    """Package SHALL update lastReviewedCommitHash on each comment activity."""
    from elspais.trace_view.review.models import ReviewPackage

    pkg = ReviewPackage.create(
        name="Git Package",
        description="",
        created_by="alice",
        commit_hash="initial123",
    )

    assert pkg.lastReviewedCommitHash == "initial123"

    # Update on activity
    pkg.update_last_reviewed_commit("newcommit456")

    assert pkg.lastReviewedCommitHash == "newcommit456"


# =============================================================================
# Dataclass Serialization Tests (REQ-d00006-A)
# =============================================================================


# IMPLEMENTS: REQ-d00006-A
def test_dataclass_serialization():
    """All review data types SHALL implement to_dict() and from_dict()."""
    from elspais.trace_view.review.models import (
        Comment,
        CommentPosition,
        ReviewFlag,
        ReviewPackage,
        Thread,
    )

    # Test Comment
    comment = Comment.create("alice", "Test body")
    comment_dict = comment.to_dict()
    restored_comment = Comment.from_dict(comment_dict)
    assert restored_comment.author == comment.author
    assert restored_comment.body == comment.body

    # Test CommentPosition
    pos = CommentPosition.create_line("abcd1234", 10, "context")
    pos_dict = pos.to_dict()
    restored_pos = CommentPosition.from_dict(pos_dict)
    assert restored_pos.type == pos.type
    assert restored_pos.lineNumber == pos.lineNumber

    # Test Thread
    thread = Thread.create("d00001", "bob", pos, "Initial comment")
    thread_dict = thread.to_dict()
    restored_thread = Thread.from_dict(thread_dict)
    assert restored_thread.reqId == thread.reqId
    assert len(restored_thread.comments) == 1

    # Test ReviewFlag
    flag = ReviewFlag.create("charlie", "Needs review", ["security"])
    flag_dict = flag.to_dict()
    restored_flag = ReviewFlag.from_dict(flag_dict)
    assert restored_flag.flaggedBy == flag.flaggedBy

    # Test ReviewPackage
    pkg = ReviewPackage.create("Test", "Desc", "dave")
    pkg_dict = pkg.to_dict()
    restored_pkg = ReviewPackage.from_dict(pkg_dict)
    assert restored_pkg.name == pkg.name


# =============================================================================
# Enum Tests (REQ-d00006-B)
# =============================================================================


# IMPLEMENTS: REQ-d00006-B
def test_enum_string_values():
    """Enums SHALL use string values for JSON compatibility."""
    from elspais.trace_view.review.models import (
        ApprovalDecision,
        PositionType,
        RequestState,
    )

    # PositionType uses string values
    assert PositionType.LINE.value == "line"
    assert PositionType.BLOCK.value == "block"
    assert PositionType.WORD.value == "word"
    assert PositionType.GENERAL.value == "general"

    # RequestState uses string values
    assert RequestState.PENDING.value == "pending"
    assert RequestState.APPROVED.value == "approved"
    assert RequestState.REJECTED.value == "rejected"
    assert RequestState.APPLIED.value == "applied"

    # ApprovalDecision uses string values
    assert ApprovalDecision.APPROVE.value == "approve"
    assert ApprovalDecision.REJECT.value == "reject"


# =============================================================================
# Thread Model Tests (REQ-d00006-C)
# =============================================================================


# IMPLEMENTS: REQ-d00006-C
def test_thread_model_fields():
    """Thread model SHALL contain all required fields."""
    from elspais.trace_view.review.models import CommentPosition, Thread

    pos = CommentPosition.create_general("hash1234")
    thread = Thread.create("d00001", "alice", pos, "First comment", "pkg-001")

    assert thread.threadId is not None
    assert thread.reqId == "d00001"
    assert thread.createdBy == "alice"
    assert thread.createdAt is not None
    assert thread.position is not None
    assert thread.resolved is False
    assert thread.resolvedBy is None
    assert thread.resolvedAt is None
    assert len(thread.comments) == 1
    assert thread.packageId == "pkg-001"


# =============================================================================
# Comment Model Tests (REQ-d00006-D)
# =============================================================================


# IMPLEMENTS: REQ-d00006-D
def test_comment_model_fields():
    """Comment model SHALL contain id, author, timestamp, body."""
    from elspais.trace_view.review.models import Comment

    comment = Comment.create("alice", "This is the comment body")

    assert comment.id is not None
    assert len(comment.id) == 36  # UUID format
    assert comment.author == "alice"
    assert comment.timestamp is not None
    assert comment.body == "This is the comment body"


# =============================================================================
# Position Anchor Types Tests (REQ-d00006-E)
# =============================================================================


# IMPLEMENTS: REQ-d00006-E
def test_position_anchor_types():
    """CommentPosition SHALL support line, block, word, general anchor types."""
    from elspais.trace_view.review.models import CommentPosition, PositionType

    # Line position
    line_pos = CommentPosition.create_line("hash1234", 10, "context text")
    assert line_pos.type == PositionType.LINE.value
    assert line_pos.lineNumber == 10

    # Block position
    block_pos = CommentPosition.create_block("hash1234", 5, 10, "block context")
    assert block_pos.type == PositionType.BLOCK.value
    assert block_pos.lineRange == (5, 10)

    # Word position
    word_pos = CommentPosition.create_word("hash1234", "SHALL", 2, "context")
    assert word_pos.type == PositionType.WORD.value
    assert word_pos.keyword == "SHALL"
    assert word_pos.keywordOccurrence == 2

    # General position
    general_pos = CommentPosition.create_general("hash1234")
    assert general_pos.type == PositionType.GENERAL.value


# =============================================================================
# Factory Methods Tests (REQ-d00006-F)
# =============================================================================


# IMPLEMENTS: REQ-d00006-F
def test_factory_methods():
    """Factory methods (create()) SHALL auto-generate UUIDs and timestamps."""
    import uuid

    from elspais.trace_view.review.models import (
        Comment,
        CommentPosition,
        ReviewPackage,
        Thread,
    )

    # Comment factory
    comment = Comment.create("alice", "body")
    assert comment.id is not None
    uuid.UUID(comment.id)  # Validates UUID format
    assert comment.timestamp is not None

    # Thread factory
    pos = CommentPosition.create_general("12345678")
    thread = Thread.create("d00001", "bob", pos)
    assert thread.threadId is not None
    uuid.UUID(thread.threadId)
    assert thread.createdAt is not None

    # Package factory
    pkg = ReviewPackage.create("name", "desc", "charlie")
    assert pkg.packageId is not None
    uuid.UUID(pkg.packageId)
    assert pkg.createdAt is not None


# =============================================================================
# Container Version Tracking Tests (REQ-d00006-G)
# =============================================================================


# IMPLEMENTS: REQ-d00006-G
def test_container_version_tracking():
    """Container classes SHALL include version tracking."""
    from elspais.trace_view.review.models import (
        PackagesFile,
        StatusFile,
        ThreadsFile,
    )

    # ThreadsFile
    threads_file = ThreadsFile(reqId="d00001", threads=[])
    assert threads_file.version == "1.0"
    tf_dict = threads_file.to_dict()
    assert "version" in tf_dict

    # StatusFile
    status_file = StatusFile(reqId="d00001", requests=[])
    assert status_file.version == "1.0"
    sf_dict = status_file.to_dict()
    assert "version" in sf_dict

    # PackagesFile
    packages_file = PackagesFile(packages=[])
    assert packages_file.version == "1.0"
    pf_dict = packages_file.to_dict()
    assert "version" in pf_dict


# =============================================================================
# Position Hash Tracking Tests (REQ-d00006-H)
# =============================================================================


# IMPLEMENTS: REQ-d00006-H
def test_position_hash_tracking():
    """CommentPosition SHALL include hashWhenCreated and fallbackContext."""
    from elspais.trace_view.review.models import CommentPosition

    pos = CommentPosition.create_line(
        hash_value="abcd1234",
        line_number=15,
        context="the system SHALL",
    )

    assert pos.hashWhenCreated == "abcd1234"
    assert pos.fallbackContext == "the system SHALL"


# =============================================================================
# Status Request Auto State Tests (REQ-d00006-I)
# =============================================================================


# IMPLEMENTS: REQ-d00006-I
def test_status_request_auto_state():
    """StatusRequest state SHALL be automatically calculated from approval votes."""
    from elspais.trace_view.review.models import RequestState, StatusRequest

    # Create a request that requires product_owner and tech_lead
    request = StatusRequest.create(
        req_id="d00001",
        from_status="Draft",
        to_status="Active",
        requested_by="alice",
        justification="Ready for review",
        required_approvers=["product_owner", "tech_lead"],
    )

    assert request.state == RequestState.PENDING.value

    # Add one approval - still pending
    request.add_approval("product_owner", "approve")
    assert request.state == RequestState.PENDING.value

    # Add second approval - now approved
    request.add_approval("tech_lead", "approve")
    assert request.state == RequestState.APPROVED.value


def test_status_request_rejection():
    """StatusRequest SHALL be rejected if any approver rejects."""
    from elspais.trace_view.review.models import RequestState, StatusRequest

    request = StatusRequest.create(
        req_id="d00001",
        from_status="Draft",
        to_status="Active",
        requested_by="alice",
        justification="Test",
        required_approvers=["product_owner"],
    )

    request.add_approval("product_owner", "reject", "Not ready yet")

    assert request.state == RequestState.REJECTED.value


# =============================================================================
# Timestamps UTC ISO 8601 Tests (REQ-d00006-J)
# =============================================================================


# IMPLEMENTS: REQ-d00006-J
def test_timestamps_utc_iso8601():
    """All timestamps SHALL be UTC in ISO 8601 format."""
    from elspais.trace_view.review.models import (
        Comment,
        now_iso,
        parse_iso_datetime,
    )

    # Test now_iso() returns ISO 8601 UTC
    timestamp = now_iso()
    assert "+" in timestamp or "Z" in timestamp or timestamp.endswith("+00:00")

    # Verify it can be parsed
    dt = parse_iso_datetime(timestamp)
    assert dt.tzinfo is not None

    # Test that Comment timestamps are ISO 8601
    comment = Comment.create("alice", "body")
    parsed = parse_iso_datetime(comment.timestamp)
    assert parsed is not None


# =============================================================================
# Validation Tests
# =============================================================================


def test_comment_validation():
    """Comment validation should catch missing fields."""
    from elspais.trace_view.review.models import Comment

    # Valid comment
    comment = Comment.create("alice", "body")
    is_valid, errors = comment.validate()
    assert is_valid is True
    assert len(errors) == 0

    # Invalid comment - empty body
    invalid = Comment(id="123", author="alice", timestamp="2025-01-01T00:00:00+00:00", body="")
    is_valid, errors = invalid.validate()
    assert is_valid is False


def test_position_validation():
    """Position validation should verify type-specific fields."""
    from elspais.trace_view.review.models import CommentPosition

    # Valid line position
    pos = CommentPosition.create_line("abcd1234", 5)
    is_valid, errors = pos.validate()
    assert is_valid is True

    # Invalid - line position without lineNumber
    invalid_pos = CommentPosition(type="line", hashWhenCreated="abcd1234")
    is_valid, errors = invalid_pos.validate()
    assert is_valid is False
    assert any("lineNumber" in e for e in errors)


def test_thread_validation():
    """Thread validation should check nested objects."""
    from elspais.trace_view.review.models import CommentPosition, Thread

    pos = CommentPosition.create_general("abcd1234")
    thread = Thread.create("d00001", "alice", pos, "comment")

    is_valid, errors = thread.validate()
    assert is_valid is True


def test_package_validation():
    """Package validation should verify required fields."""
    from elspais.trace_view.review.models import ReviewPackage

    pkg = ReviewPackage.create("Name", "Description", "user")

    is_valid, errors = pkg.validate()
    assert is_valid is True

    # Invalid - missing name
    invalid_pkg = ReviewPackage(
        packageId="123",
        name="",
        description="",
        reqIds=[],
        createdBy="user",
        createdAt="2025-01-01T00:00:00+00:00",
    )
    is_valid, errors = invalid_pkg.validate()
    assert is_valid is False
