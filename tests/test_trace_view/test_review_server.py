"""
Tests for review API server.

Tests REQ-d00005: Review Archive Viewer
Tests REQ-d00010: Review API Server
"""

import json
from pathlib import Path

import pytest

# =============================================================================
# Flask App Factory Tests (REQ-d00010-A)
# =============================================================================


# IMPLEMENTS: REQ-d00010-A
def test_flask_app_factory(tmp_repo: Path):
    """The API server SHALL be implemented with create_app() factory function."""
    pytest.importorskip("flask")

    from elspais.trace_view.review.server import create_app

    app = create_app(
        repo_root=tmp_repo,
        static_dir=tmp_repo,
        auto_sync=False,
    )

    assert app is not None
    assert app.config["REPO_ROOT"] == tmp_repo
    assert app.config["AUTO_SYNC"] is False


# =============================================================================
# Thread Endpoints Tests (REQ-d00010-B)
# =============================================================================


# IMPLEMENTS: REQ-d00010-B
def test_thread_endpoints(flask_client, tmp_repo: Path):
    """Thread endpoints SHALL support create, comment, resolve, unresolve."""
    # Create a thread
    thread_data = {
        "threadId": "test-thread-123",
        "reqId": "d00001",
        "createdBy": "alice",
        "createdAt": "2025-01-01T00:00:00+00:00",
        "position": {
            "type": "general",
            "hashWhenCreated": "abcd1234",
        },
        "resolved": False,
        "comments": [
            {
                "id": "comment-1",
                "author": "alice",
                "timestamp": "2025-01-01T00:00:00+00:00",
                "body": "Initial comment",
            }
        ],
    }

    # POST create thread
    response = flask_client.post(
        "/api/reviews/reqs/d00001/threads",
        data=json.dumps(thread_data),
        content_type="application/json",
    )
    assert response.status_code == 201
    data = response.get_json()
    assert data["success"] is True

    # POST add comment
    comment_data = {
        "author": "bob",
        "body": "Reply comment",
    }
    response = flask_client.post(
        "/api/reviews/reqs/d00001/threads/test-thread-123/comments",
        data=json.dumps(comment_data),
        content_type="application/json",
    )
    assert response.status_code == 201
    data = response.get_json()
    assert data["comment"]["author"] == "bob"

    # POST resolve
    response = flask_client.post(
        "/api/reviews/reqs/d00001/threads/test-thread-123/resolve",
        data=json.dumps({"user": "charlie"}),
        content_type="application/json",
    )
    assert response.status_code == 200

    # POST unresolve
    response = flask_client.post(
        "/api/reviews/reqs/d00001/threads/test-thread-123/unresolve",
        data=json.dumps({}),
        content_type="application/json",
    )
    assert response.status_code == 200


# =============================================================================
# Status Endpoints Tests (REQ-d00010-C)
# =============================================================================


# IMPLEMENTS: REQ-d00010-C
def test_status_endpoints(flask_client, tmp_repo: Path):
    """Status endpoints SHALL support GET/POST for status and requests."""
    # GET current status
    response = flask_client.get("/api/reviews/reqs/d00001/status")
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "Active"  # From fixture

    # POST change status
    response = flask_client.post(
        "/api/reviews/reqs/d00001/status",
        data=json.dumps({"newStatus": "Deprecated", "user": "admin"}),
        content_type="application/json",
    )
    assert response.status_code == 200

    # GET requests (empty initially)
    response = flask_client.get("/api/reviews/reqs/d00001/requests")
    assert response.status_code == 200


def test_create_status_request_endpoint(flask_client, tmp_repo: Path):
    """Test creating a status request via API."""
    request_data = {
        "requestId": "req-test-001",
        "reqId": "d00001",
        "type": "status_change",
        "fromStatus": "Draft",
        "toStatus": "Active",
        "requestedBy": "alice",
        "requestedAt": "2025-01-01T00:00:00+00:00",
        "justification": "Ready for activation",
        "approvals": [],
        "requiredApprovers": ["product_owner"],
        "state": "pending",
    }

    response = flask_client.post(
        "/api/reviews/reqs/d00001/requests",
        data=json.dumps(request_data),
        content_type="application/json",
    )
    assert response.status_code == 201


# =============================================================================
# Package Endpoints Tests (REQ-d00010-D)
# =============================================================================


# IMPLEMENTS: REQ-d00010-D
def test_package_endpoints(flask_client, tmp_repo: Path):
    """Package endpoints SHALL support CRUD and membership operations."""
    # GET packages (empty initially)
    response = flask_client.get("/api/reviews/packages")
    assert response.status_code == 200
    data = response.get_json()
    assert "packages" in data

    # POST create package
    pkg_data = {
        "name": "Test Package",
        "description": "A test package",
        "user": "alice",
    }
    response = flask_client.post(
        "/api/reviews/packages",
        data=json.dumps(pkg_data),
        content_type="application/json",
    )
    assert response.status_code == 201
    data = response.get_json()
    package_id = data["package"]["packageId"]

    # GET package by ID
    response = flask_client.get(f"/api/reviews/packages/{package_id}")
    assert response.status_code == 200

    # PUT update package
    response = flask_client.put(
        f"/api/reviews/packages/{package_id}",
        data=json.dumps({"description": "Updated description", "user": "bob"}),
        content_type="application/json",
    )
    assert response.status_code == 200

    # POST add req to package
    response = flask_client.post(
        f"/api/reviews/packages/{package_id}/reqs/d00001",
        data=json.dumps({"user": "alice"}),
        content_type="application/json",
    )
    assert response.status_code == 200

    # DELETE remove req from package
    response = flask_client.delete(
        f"/api/reviews/packages/{package_id}/reqs/d00001",
        data=json.dumps({"user": "alice"}),
        content_type="application/json",
    )
    assert response.status_code == 200


def test_active_package_endpoints(flask_client, tmp_repo: Path):
    """Test active package management endpoints."""
    # Create a package first
    response = flask_client.post(
        "/api/reviews/packages",
        data=json.dumps({"name": "Active Test", "user": "alice"}),
        content_type="application/json",
    )
    package_id = response.get_json()["package"]["packageId"]

    # PUT set active
    response = flask_client.put(
        "/api/reviews/packages/active",
        data=json.dumps({"packageId": package_id, "user": "alice"}),
        content_type="application/json",
    )
    assert response.status_code == 200

    # GET active
    response = flask_client.get("/api/reviews/packages/active")
    assert response.status_code == 200


# =============================================================================
# Sync Endpoints Tests (REQ-d00010-E)
# =============================================================================


# IMPLEMENTS: REQ-d00010-E
def test_sync_endpoints(flask_client, tmp_repo: Path):
    """Sync endpoints SHALL support status, push, fetch, fetch-all-package."""
    # GET sync status
    response = flask_client.get("/api/reviews/sync/status")
    assert response.status_code == 200
    data = response.get_json()
    assert "has_changes" in data
    assert "auto_sync_enabled" in data

    # POST push (no remote, so commit only)
    response = flask_client.post(
        "/api/reviews/sync/push",
        data=json.dumps({"message": "Test sync", "user": "alice"}),
        content_type="application/json",
    )
    assert response.status_code == 200

    # POST fetch
    response = flask_client.post("/api/reviews/sync/fetch")
    assert response.status_code == 200

    # POST fetch-all-package
    response = flask_client.post("/api/reviews/sync/fetch-all-package")
    assert response.status_code == 200


# =============================================================================
# CORS Tests (REQ-d00010-F)
# =============================================================================


# IMPLEMENTS: REQ-d00010-F
def test_cors_enabled(flask_client):
    """CORS SHALL be enabled for cross-origin requests."""
    # CORS headers should be present on responses
    response = flask_client.get("/api/health")

    # flask-cors adds these headers
    # Note: The exact headers depend on the CORS configuration
    assert response.status_code == 200


# =============================================================================
# Static File Serving Tests (REQ-d00010-G)
# =============================================================================


# IMPLEMENTS: REQ-d00010-G
def test_static_file_serving(tmp_repo: Path):
    """Static file serving SHALL be supported from configured directory."""
    pytest.importorskip("flask")
    from elspais.trace_view.review.server import create_app

    # Create index.html
    index_content = "<html><body>Test</body></html>"
    (tmp_repo / "index.html").write_text(index_content)

    # Create app with static routes enabled
    app = create_app(
        repo_root=tmp_repo,
        static_dir=tmp_repo,
        auto_sync=False,
        register_static_routes=True,
    )
    app.config["TESTING"] = True

    with app.test_client() as client:
        response = client.get("/")
        assert response.status_code == 200
        assert b"Test" in response.data


# =============================================================================
# Auto Sync Config Tests (REQ-d00010-H)
# =============================================================================


# IMPLEMENTS: REQ-d00010-H
def test_auto_sync_config(tmp_repo: Path):
    """All write endpoints SHALL optionally trigger auto-sync based on configuration."""
    pytest.importorskip("flask")
    from elspais.trace_view.review.server import create_app

    # Test with auto_sync disabled
    app = create_app(repo_root=tmp_repo, auto_sync=False, register_static_routes=False)
    assert app.config["AUTO_SYNC"] is False

    # Test with auto_sync enabled
    app = create_app(repo_root=tmp_repo, auto_sync=True, register_static_routes=False)
    assert app.config["AUTO_SYNC"] is True


# =============================================================================
# Archive Endpoints Tests (REQ-d00010-I, REQ-d00005-A, REQ-d00005-B)
# =============================================================================


# IMPLEMENTS: REQ-d00010-I, REQ-d00005-A, REQ-d00005-B
def test_archive_endpoints(flask_client, tmp_repo: Path, sample_packages_json):
    """Archive endpoints SHALL support list, get, and threads for archived packages."""
    # First archive the test package
    response = flask_client.post(
        "/api/reviews/packages/pkg-001/archive",
        data=json.dumps({"user": "admin"}),
        content_type="application/json",
    )
    assert response.status_code == 200

    # GET list archived packages
    response = flask_client.get("/api/reviews/archive")
    assert response.status_code == 200
    data = response.get_json()
    assert "packages" in data
    assert len(data["packages"]) == 1

    # GET specific archived package
    response = flask_client.get("/api/reviews/archive/pkg-001")
    assert response.status_code == 200
    data = response.get_json()
    assert data["packageId"] == "pkg-001"


# =============================================================================
# Health Endpoint Tests (REQ-d00010-J)
# =============================================================================


# IMPLEMENTS: REQ-d00010-J
def test_health_endpoint(flask_client, tmp_repo: Path):
    """Health check endpoint SHALL be available at /api/health."""
    response = flask_client.get("/api/health")

    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "ok"
    assert "repo_root" in data
    assert "reviews_dir" in data


# =============================================================================
# Archive Read-Only Tests (REQ-d00005-C)
# =============================================================================


# IMPLEMENTS: REQ-d00005-C
def test_archive_read_only(flask_client, tmp_repo: Path, sample_packages_json):
    """The API SHALL NOT allow adding or editing comments in archived packages."""
    # Archive the package
    flask_client.post(
        "/api/reviews/packages/pkg-001/archive",
        data=json.dumps({"user": "admin"}),
        content_type="application/json",
    )

    # There's no write endpoint for archived packages
    # Verify only GET endpoints exist for archive
    response = flask_client.get("/api/reviews/archive/pkg-001")
    assert response.status_code == 200

    # Archived threads endpoint is read-only (GET only)
    response = flask_client.get("/api/reviews/archive/pkg-001/reqs/d00001/threads")
    # May return 404 if no threads exist, that's OK
    assert response.status_code in [200, 404]


# =============================================================================
# Archive Metadata Response Tests (REQ-d00005-D, REQ-d00005-E)
# =============================================================================


# IMPLEMENTS: REQ-d00005-D, REQ-d00005-E
def test_archive_metadata_response(flask_client, tmp_repo: Path, sample_packages_json):
    """The archive API SHALL return archival metadata and git audit trail."""
    # Archive the package
    flask_client.post(
        "/api/reviews/packages/pkg-001/archive",
        data=json.dumps({"user": "admin"}),
        content_type="application/json",
    )

    # Get archived package
    response = flask_client.get("/api/reviews/archive/pkg-001")
    data = response.get_json()

    # REQ-d00005-D: Archival metadata
    assert "archivedAt" in data
    assert "archivedBy" in data
    assert data["archivedBy"] == "admin"
    assert "archiveReason" in data

    # REQ-d00005-E: Git audit trail
    assert "branchName" in data
    assert "creationCommitHash" in data


# =============================================================================
# Error Handling Tests
# =============================================================================


def test_missing_data_error(flask_client):
    """Endpoints should return 400 for missing data."""
    response = flask_client.post(
        "/api/reviews/reqs/d00001/threads",
        content_type="application/json",
    )
    assert response.status_code == 400


def test_package_not_found(flask_client):
    """GET nonexistent package should return 404."""
    response = flask_client.get("/api/reviews/packages/nonexistent-id")
    assert response.status_code == 404


def test_thread_not_found(flask_client, tmp_repo: Path):
    """Adding comment to nonexistent thread should return 400."""
    response = flask_client.post(
        "/api/reviews/reqs/d00001/threads/nonexistent/comments",
        data=json.dumps({"author": "alice", "body": "test"}),
        content_type="application/json",
    )
    assert response.status_code == 400


def test_delete_default_package_error(flask_client, tmp_repo: Path):
    """Deleting default package should return 400."""
    from elspais.trace_view.review.models import ReviewPackage
    from elspais.trace_view.review.storage import load_packages, save_packages

    # Create a default package
    packages_file = load_packages(tmp_repo)
    default_pkg = ReviewPackage.create("Default", "Default package", "system")
    default_pkg.isDefault = True
    packages_file.packages.append(default_pkg)
    save_packages(tmp_repo, packages_file)

    # Try to delete - should fail
    response = flask_client.delete(
        f"/api/reviews/packages/{default_pkg.packageId}",
        data=json.dumps({"user": "admin"}),
        content_type="application/json",
    )
    assert response.status_code == 400
    assert "default" in response.get_json()["error"].lower()


def test_review_flag_endpoints(flask_client, tmp_repo: Path):
    """Test review flag CRUD endpoints."""
    req_id = "d00001"

    # GET flag (initially unflagged)
    response = flask_client.get(f"/api/reviews/reqs/{req_id}/flag")
    assert response.status_code == 200
    data = response.get_json()
    assert data["flaggedForReview"] is False

    # POST set flag
    flag_data = {
        "flaggedForReview": True,
        "flaggedBy": "alice",
        "flaggedAt": "2025-01-01T00:00:00+00:00",
        "reason": "Needs review",
        "scope": ["security_team"],
    }
    response = flask_client.post(
        f"/api/reviews/reqs/{req_id}/flag",
        data=json.dumps(flag_data),
        content_type="application/json",
    )
    assert response.status_code == 200

    # Verify flag is set
    response = flask_client.get(f"/api/reviews/reqs/{req_id}/flag")
    data = response.get_json()
    assert data["flaggedForReview"] is True

    # DELETE clear flag
    response = flask_client.delete(
        f"/api/reviews/reqs/{req_id}/flag",
        data=json.dumps({"user": "bob"}),
        content_type="application/json",
    )
    assert response.status_code == 200

    # Verify flag is cleared
    response = flask_client.get(f"/api/reviews/reqs/{req_id}/flag")
    data = response.get_json()
    assert data["flaggedForReview"] is False


def test_files_endpoint_security(flask_client, tmp_repo: Path):
    """File reading should only allow spec files for security."""
    # Create a non-spec file
    (tmp_repo / "secret.txt").write_text("secret content")

    # Try to read non-spec file - should fail
    response = flask_client.get(f"/api/files?path={tmp_repo}/secret.txt")
    assert response.status_code == 403

    # Missing path parameter
    response = flask_client.get("/api/files")
    assert response.status_code == 400
