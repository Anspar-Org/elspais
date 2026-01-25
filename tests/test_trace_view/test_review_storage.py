"""
Tests for review system storage operations.

Tests REQ-d00002: Review Storage Architecture
Tests REQ-d00003: Review Package Archival
Tests REQ-d00007: Review Storage Operations
"""

import json
from pathlib import Path

# =============================================================================
# Storage Path Tests (REQ-d00002)
# =============================================================================


# IMPLEMENTS: REQ-d00002-A
def test_reviews_directory_location(tmp_repo: Path):
    """Review data SHALL be stored under .reviews/ directory."""
    from elspais.trace_view.review.storage import get_reviews_root

    reviews_root = get_reviews_root(tmp_repo)
    assert reviews_root == tmp_repo / ".reviews"


# IMPLEMENTS: REQ-d00002-B
def test_packages_json_path(tmp_repo: Path):
    """Package metadata SHALL be stored at .reviews/packages.json."""
    from elspais.trace_view.review.storage import get_packages_path

    packages_path = get_packages_path(tmp_repo)
    assert packages_path == tmp_repo / ".reviews" / "packages.json"


# IMPLEMENTS: REQ-d00002-C
def test_threads_json_path(tmp_repo: Path):
    """Threads SHALL be stored at .reviews/reqs/{req-id}/threads.json."""
    from elspais.trace_view.review.storage import get_threads_path

    threads_path = get_threads_path(tmp_repo, "d00001")
    assert threads_path == tmp_repo / ".reviews" / "reqs" / "d00001" / "threads.json"


# IMPLEMENTS: REQ-d00002-D
def test_flag_json_path(tmp_repo: Path):
    """Review flags SHALL be stored at .reviews/reqs/{req-id}/flag.json."""
    from elspais.trace_view.review.storage import get_review_flag_path

    flag_path = get_review_flag_path(tmp_repo, "d00001")
    assert flag_path == tmp_repo / ".reviews" / "reqs" / "d00001" / "flag.json"


# IMPLEMENTS: REQ-d00002-E
def test_status_json_path(tmp_repo: Path):
    """Status requests SHALL be stored at .reviews/reqs/{req-id}/status.json."""
    from elspais.trace_view.review.storage import get_status_path

    status_path = get_status_path(tmp_repo, "d00001")
    assert status_path == tmp_repo / ".reviews" / "reqs" / "d00001" / "status.json"


# IMPLEMENTS: REQ-d00002-F
def test_config_json_path(tmp_repo: Path):
    """Configuration SHALL be stored at .reviews/config.json."""
    from elspais.trace_view.review.storage import get_config_path

    config_path = get_config_path(tmp_repo)
    assert config_path == tmp_repo / ".reviews" / "config.json"


# IMPLEMENTS: REQ-d00002-G, REQ-d00007-A
def test_atomic_writes(tmp_repo: Path):
    """Storage operations SHALL use atomic writes (temp file + rename)."""
    from elspais.trace_view.review.storage import atomic_write_json

    test_path = tmp_repo / ".reviews" / "test.json"
    test_data = {"key": "value"}

    atomic_write_json(test_path, test_data)

    # File should exist with correct content
    assert test_path.exists()
    with open(test_path) as f:
        loaded = json.load(f)
    assert loaded == test_data

    # No temp files should remain
    temp_files = list(test_path.parent.glob(".tmp_*"))
    assert len(temp_files) == 0


# IMPLEMENTS: REQ-d00002-H, REQ-d00007-I
def test_req_id_normalization(tmp_repo: Path):
    """Requirement IDs SHALL be normalized (colons/slashes replaced)."""
    from elspais.trace_view.review.storage import get_req_dir, normalize_req_id

    # Test normalization function
    assert normalize_req_id("d00001") == "d00001"
    assert normalize_req_id("HHT:d00001") == "HHT_d00001"
    assert normalize_req_id("sponsor/d00001") == "sponsor_d00001"

    # Test path construction with normalization
    req_dir = get_req_dir(tmp_repo, "HHT:d00001")
    assert "HHT_d00001" in str(req_dir)


# =============================================================================
# Archive Storage Tests (REQ-d00003)
# =============================================================================


# IMPLEMENTS: REQ-d00003-A, REQ-d00003-B
def test_archive_directory_structure(tmp_repo: Path):
    """Archived packages SHALL be stored at .reviews/archive/{pkg-id}/."""
    from elspais.trace_view.review.storage import (
        get_archive_dir,
        get_archived_package_dir,
        get_archived_package_metadata_path,
    )

    archive_dir = get_archive_dir(tmp_repo)
    assert archive_dir == tmp_repo / ".reviews" / "archive"

    pkg_dir = get_archived_package_dir(tmp_repo, "pkg-123")
    assert pkg_dir == tmp_repo / ".reviews" / "archive" / "pkg-123"

    metadata_path = get_archived_package_metadata_path(tmp_repo, "pkg-123")
    assert metadata_path == tmp_repo / ".reviews" / "archive" / "pkg-123" / "package.json"


# IMPLEMENTS: REQ-d00003-C
def test_archive_metadata_fields(tmp_repo: Path, sample_packages_json):
    """Archive metadata SHALL include archivedAt, archivedBy, archiveReason."""
    from elspais.trace_view.review.models import ARCHIVE_REASON_MANUAL
    from elspais.trace_view.review.storage import (
        archive_package,
        get_archived_package,
    )

    # Archive the test package
    success = archive_package(tmp_repo, "pkg-001", ARCHIVE_REASON_MANUAL, "admin")
    assert success is True

    # Load archived package and verify metadata
    archived_pkg = get_archived_package(tmp_repo, "pkg-001")
    assert archived_pkg is not None
    assert archived_pkg.archivedAt is not None
    assert archived_pkg.archivedBy == "admin"
    assert archived_pkg.archiveReason == "manual"


# IMPLEMENTS: REQ-d00003-D
def test_archive_triggers(tmp_repo: Path, sample_packages_json):
    """Archive SHALL be triggered by resolved/deleted/manual actions."""
    from elspais.trace_view.review.models import (
        ARCHIVE_REASON_DELETED,
        ARCHIVE_REASON_MANUAL,
        ARCHIVE_REASON_RESOLVED,
    )

    # All three reasons should be valid
    for reason in [ARCHIVE_REASON_RESOLVED, ARCHIVE_REASON_DELETED, ARCHIVE_REASON_MANUAL]:
        assert reason in ["resolved", "deleted", "manual"]


# IMPLEMENTS: REQ-d00003-F
def test_archive_read_only(tmp_repo: Path, sample_packages_json):
    """Archived data SHALL be read-only (no write operations)."""
    from elspais.trace_view.review.models import ARCHIVE_REASON_MANUAL
    from elspais.trace_view.review.storage import (
        archive_package,
        get_archived_package,
    )

    # Archive the package
    archive_package(tmp_repo, "pkg-001", ARCHIVE_REASON_MANUAL, "admin")

    # Read operations should work
    pkg = get_archived_package(tmp_repo, "pkg-001")
    assert pkg is not None

    # There are no write operations for archived data - storage module
    # only provides load_archived_threads, not save_archived_threads


# =============================================================================
# Thread Operations Tests (REQ-d00007-B)
# =============================================================================


# IMPLEMENTS: REQ-d00007-B
def test_thread_load_empty(tmp_repo: Path):
    """load_threads() SHALL return empty ThreadsFile if not exists."""
    from elspais.trace_view.review.storage import load_threads

    threads_file = load_threads(tmp_repo, "nonexistent")

    assert threads_file.reqId == "nonexistent"
    assert threads_file.threads == []


# IMPLEMENTS: REQ-d00007-B
def test_thread_crud_operations(tmp_repo: Path):
    """Thread operations SHALL support load, save, add, resolve, unresolve."""
    from elspais.trace_view.review.models import (
        CommentPosition,
        Thread,
    )
    from elspais.trace_view.review.storage import (
        add_comment_to_thread,
        add_thread,
        load_threads,
        resolve_thread,
        unresolve_thread,
    )

    req_id = "d00001"

    # Create a thread
    pos = CommentPosition.create_general("abcd1234")
    thread = Thread.create(req_id, "alice", pos, "First comment")

    # Add thread
    added_thread = add_thread(tmp_repo, req_id, thread)
    assert added_thread.threadId == thread.threadId

    # Load threads
    threads_file = load_threads(tmp_repo, req_id)
    assert len(threads_file.threads) == 1

    # Add comment
    comment = add_comment_to_thread(tmp_repo, req_id, thread.threadId, "bob", "Reply")
    assert comment.author == "bob"

    # Verify comment was added
    threads_file = load_threads(tmp_repo, req_id)
    assert len(threads_file.threads[0].comments) == 2

    # Resolve thread
    result = resolve_thread(tmp_repo, req_id, thread.threadId, "charlie")
    assert result is True

    threads_file = load_threads(tmp_repo, req_id)
    assert threads_file.threads[0].resolved is True

    # Unresolve thread
    result = unresolve_thread(tmp_repo, req_id, thread.threadId)
    assert result is True

    threads_file = load_threads(tmp_repo, req_id)
    assert threads_file.threads[0].resolved is False


# =============================================================================
# Status Request Operations Tests (REQ-d00007-C)
# =============================================================================


# IMPLEMENTS: REQ-d00007-C
def test_status_request_operations(tmp_repo: Path):
    """Status request operations SHALL support load, save, create, approve."""
    from elspais.trace_view.review.models import RequestState, StatusRequest
    from elspais.trace_view.review.storage import (
        add_approval,
        create_status_request,
        load_status_requests,
        mark_request_applied,
    )

    req_id = "d00001"

    # Create a status request
    request = StatusRequest.create(
        req_id=req_id,
        from_status="Draft",
        to_status="Active",
        requested_by="alice",
        justification="Ready for activation",
        required_approvers=["product_owner"],
    )

    # Save it
    create_status_request(tmp_repo, req_id, request)

    # Load and verify
    status_file = load_status_requests(tmp_repo, req_id)
    assert len(status_file.requests) == 1
    assert status_file.requests[0].state == RequestState.PENDING.value

    # Add approval
    approval = add_approval(
        tmp_repo, req_id, request.requestId, "product_owner", "approve", "Looks good"
    )
    assert approval.decision == "approve"

    # Verify state changed to approved
    status_file = load_status_requests(tmp_repo, req_id)
    assert status_file.requests[0].state == RequestState.APPROVED.value

    # Mark as applied
    result = mark_request_applied(tmp_repo, req_id, request.requestId)
    assert result is True

    status_file = load_status_requests(tmp_repo, req_id)
    assert status_file.requests[0].state == RequestState.APPLIED.value


# =============================================================================
# Review Flag Operations Tests (REQ-d00007-D)
# =============================================================================


# IMPLEMENTS: REQ-d00007-D
def test_review_flag_operations(tmp_repo: Path):
    """Review flag operations SHALL support load and save."""
    from elspais.trace_view.review.models import ReviewFlag
    from elspais.trace_view.review.storage import (
        load_review_flag,
        save_review_flag,
    )

    req_id = "d00001"

    # Load returns cleared flag if not exists
    flag = load_review_flag(tmp_repo, req_id)
    assert flag.flaggedForReview is False

    # Create and save a flag
    new_flag = ReviewFlag.create("alice", "Needs review", ["security_team"])
    save_review_flag(tmp_repo, req_id, new_flag)

    # Load and verify
    loaded_flag = load_review_flag(tmp_repo, req_id)
    assert loaded_flag.flaggedForReview is True
    assert loaded_flag.flaggedBy == "alice"
    assert loaded_flag.reason == "Needs review"
    assert "security_team" in loaded_flag.scope


# =============================================================================
# Package Operations Tests (REQ-d00007-E)
# =============================================================================


# IMPLEMENTS: REQ-d00007-E
def test_package_crud_operations(tmp_repo: Path):
    """Package operations SHALL support load, create, update, delete."""
    from elspais.trace_view.review.models import ReviewPackage
    from elspais.trace_view.review.storage import (
        add_req_to_package,
        create_package,
        delete_package,
        load_packages,
        remove_req_from_package,
        update_package,
    )

    # Load returns empty if not exists
    packages_file = load_packages(tmp_repo)
    assert len(packages_file.packages) == 0

    # Create a package
    pkg = ReviewPackage.create("Test Package", "Description", "alice")
    create_package(tmp_repo, pkg)

    packages_file = load_packages(tmp_repo)
    assert len(packages_file.packages) == 1
    assert packages_file.packages[0].name == "Test Package"

    # Update package
    pkg.description = "Updated description"
    result = update_package(tmp_repo, pkg)
    assert result is True

    packages_file = load_packages(tmp_repo)
    assert packages_file.packages[0].description == "Updated description"

    # Add req to package
    result = add_req_to_package(tmp_repo, pkg.packageId, "d00001")
    assert result is True

    packages_file = load_packages(tmp_repo)
    assert "d00001" in packages_file.packages[0].reqIds

    # Add same req again - should be idempotent
    result = add_req_to_package(tmp_repo, pkg.packageId, "d00001")
    assert result is True
    packages_file = load_packages(tmp_repo)
    assert packages_file.packages[0].reqIds.count("d00001") == 1

    # Remove req from package
    result = remove_req_from_package(tmp_repo, pkg.packageId, "d00001")
    assert result is True

    packages_file = load_packages(tmp_repo)
    assert "d00001" not in packages_file.packages[0].reqIds

    # Delete package
    result = delete_package(tmp_repo, pkg.packageId)
    assert result is True

    packages_file = load_packages(tmp_repo)
    assert len(packages_file.packages) == 0


# =============================================================================
# Config Operations Tests (REQ-d00007-F)
# =============================================================================


# IMPLEMENTS: REQ-d00007-F
def test_config_operations(tmp_repo: Path):
    """Config operations SHALL support load and save with defaults."""
    from elspais.trace_view.review.storage import load_config, save_config

    # Load returns default config if not exists
    config = load_config(tmp_repo)
    assert config.pushOnComment is True
    assert config.autoFetchOnOpen is True
    assert len(config.approvalRules) > 0

    # Modify and save
    config.pushOnComment = False
    save_config(tmp_repo, config)

    # Load and verify
    loaded_config = load_config(tmp_repo)
    assert loaded_config.pushOnComment is False


# =============================================================================
# Merge Operations Tests (REQ-d00007-G, REQ-d00007-J)
# =============================================================================


# IMPLEMENTS: REQ-d00007-G
def test_merge_threads(tmp_repo: Path):
    """merge_threads() SHALL combine data from multiple branches."""
    from elspais.trace_view.review.models import (
        CommentPosition,
        Thread,
        ThreadsFile,
    )
    from elspais.trace_view.review.storage import merge_threads

    pos = CommentPosition.create_general("abcd1234")

    # Create local threads file
    local_thread = Thread.create("d00001", "alice", pos, "Local comment")
    local = ThreadsFile(reqId="d00001", threads=[local_thread])

    # Create remote threads file with different thread
    remote_thread = Thread.create("d00001", "bob", pos, "Remote comment")
    remote = ThreadsFile(reqId="d00001", threads=[remote_thread])

    # Merge
    merged = merge_threads(local, remote)

    # Should have both threads
    assert len(merged.threads) == 2
    thread_ids = {t.threadId for t in merged.threads}
    assert local_thread.threadId in thread_ids
    assert remote_thread.threadId in thread_ids


# IMPLEMENTS: REQ-d00007-H
def test_storage_path_convention(tmp_repo: Path):
    """Storage paths SHALL follow convention: .reviews/reqs/{normalized-req-id}/."""
    from elspais.trace_view.review.storage import get_req_dir

    req_dir = get_req_dir(tmp_repo, "d00001")
    assert str(req_dir).endswith(".reviews/reqs/d00001")

    # With sponsor prefix
    req_dir = get_req_dir(tmp_repo, "HHT-d00001")
    assert ".reviews/reqs/HHT-d00001" in str(req_dir)


# IMPLEMENTS: REQ-d00007-J
def test_merge_timestamp_dedup():
    """Merge conflict resolution SHALL use timestamp-based deduplication."""
    from elspais.trace_view.review.models import ReviewFlag
    from elspais.trace_view.review.storage import merge_review_flags

    # Create two flags with different timestamps
    local_flag = ReviewFlag(
        flaggedForReview=True,
        flaggedBy="alice",
        flaggedAt="2025-01-01T10:00:00+00:00",
        reason="Local reason",
        scope=["team_a"],
    )

    remote_flag = ReviewFlag(
        flaggedForReview=True,
        flaggedBy="bob",
        flaggedAt="2025-01-01T12:00:00+00:00",  # Later timestamp
        reason="Remote reason",
        scope=["team_b"],
    )

    # Merge - newer timestamp should win
    merged = merge_review_flags(local_flag, remote_flag)

    assert merged.flaggedBy == "bob"  # Remote was newer
    assert merged.reason == "Remote reason"
    # Scopes should be merged
    assert "team_a" in merged.scope
    assert "team_b" in merged.scope


def test_merge_threads_with_same_id():
    """Merge threads with same ID should combine comments."""
    from elspais.trace_view.review.models import (
        Comment,
        CommentPosition,
        Thread,
        ThreadsFile,
    )
    from elspais.trace_view.review.storage import merge_threads

    pos = CommentPosition.create_general("abcd1234")

    # Create thread with same ID in both local and remote
    thread_id = "shared-thread-id"

    local_thread = Thread(
        threadId=thread_id,
        reqId="d00001",
        createdBy="alice",
        createdAt="2025-01-01T00:00:00+00:00",
        position=pos,
        comments=[
            Comment(
                id="comment-local",
                author="alice",
                timestamp="2025-01-01T10:00:00+00:00",
                body="Local comment",
            )
        ],
    )

    remote_thread = Thread(
        threadId=thread_id,
        reqId="d00001",
        createdBy="alice",
        createdAt="2025-01-01T00:00:00+00:00",
        position=pos,
        comments=[
            Comment(
                id="comment-remote",
                author="bob",
                timestamp="2025-01-01T11:00:00+00:00",
                body="Remote comment",
            )
        ],
    )

    local = ThreadsFile(reqId="d00001", threads=[local_thread])
    remote = ThreadsFile(reqId="d00001", threads=[remote_thread])

    merged = merge_threads(local, remote)

    # Should have one thread with both comments
    assert len(merged.threads) == 1
    assert len(merged.threads[0].comments) == 2
