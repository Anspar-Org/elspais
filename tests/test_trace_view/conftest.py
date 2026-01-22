"""
Shared fixtures for trace_view review system tests.

Provides common fixtures for:
- Temporary repository directories
- Sample spec files
- Review storage
- Flask test client
- Git repository mocking
"""

import json
import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def tmp_repo(tmp_path: Path) -> Path:
    """
    Create a temporary directory structure simulating a repository.

    Returns:
        Path to the temporary repository root
    """
    # Create spec directory with sample spec file
    spec_dir = tmp_path / "spec"
    spec_dir.mkdir()

    # Create a sample spec file with test requirements
    spec_content = """# Test Spec File

---

# REQ-d00001: Test Requirement

**Level**: Dev | **Status**: Active | **Implements**: REQ-p00001

**Purpose:** A test requirement for unit tests.

## Assertions

A. The system SHALL do something.
B. The system SHALL do something else.

*End* *Test Requirement* | **Hash**: abcd1234

---

# REQ-d00002: Another Test

**Level**: Dev | **Status**: Draft | **Implements**: REQ-p00001

**Purpose:** Another test requirement.

## Assertions

A. The system SHALL provide X.

*End* *Another Test* | **Hash**: efgh5678
"""
    (spec_dir / "test-spec.md").write_text(spec_content)

    # Create .reviews directory
    reviews_dir = tmp_path / ".reviews"
    reviews_dir.mkdir()

    return tmp_path


@pytest.fixture
def tmp_git_repo(tmp_path: Path) -> Path:
    """
    Create a temporary git repository for branch tests.

    Returns:
        Path to the git repository root
    """
    # Initialize git repo
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, check=True)

    # Configure git user (required for commits)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=tmp_path,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"], cwd=tmp_path, capture_output=True, check=True
    )

    # Create spec directory with sample spec file
    spec_dir = tmp_path / "spec"
    spec_dir.mkdir()

    spec_content = """# Test Spec

# REQ-d00001: Git Test

**Level**: Dev | **Status**: Active | **Implements**: REQ-p00001

## Assertions

A. Test assertion.

*End* *Git Test* | **Hash**: git12345
"""
    (spec_dir / "test.md").write_text(spec_content)

    # Create .reviews directory
    reviews_dir = tmp_path / ".reviews"
    reviews_dir.mkdir()

    # Initial commit
    subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"], cwd=tmp_path, capture_output=True, check=True
    )

    return tmp_path


@pytest.fixture
def sample_packages_json(tmp_repo: Path) -> Path:
    """
    Create a sample packages.json file.

    Returns:
        Path to packages.json
    """
    packages_data = {
        "version": "1.0",
        "packages": [
            {
                "packageId": "pkg-001",
                "name": "Test Package",
                "description": "A test package",
                "reqIds": ["d00001"],
                "createdBy": "testuser",
                "createdAt": "2025-01-01T00:00:00+00:00",
                "branchName": "main",
                "creationCommitHash": "abc1234567890",
            }
        ],
        "activePackageId": "pkg-001",
    }

    packages_path = tmp_repo / ".reviews" / "packages.json"
    packages_path.write_text(json.dumps(packages_data, indent=2))

    return packages_path


@pytest.fixture
def sample_threads_json(tmp_repo: Path) -> Path:
    """
    Create a sample threads.json file for d00001.

    Returns:
        Path to threads.json
    """
    threads_data = {
        "version": "1.0",
        "reqId": "d00001",
        "threads": [
            {
                "threadId": "thread-001",
                "reqId": "d00001",
                "createdBy": "alice",
                "createdAt": "2025-01-01T10:00:00+00:00",
                "position": {"type": "line", "hashWhenCreated": "abcd1234", "lineNumber": 5},
                "resolved": False,
                "resolvedBy": None,
                "resolvedAt": None,
                "comments": [
                    {
                        "id": "comment-001",
                        "author": "alice",
                        "timestamp": "2025-01-01T10:00:00+00:00",
                        "body": "This needs clarification.",
                    }
                ],
                "packageId": "pkg-001",
            }
        ],
    }

    req_dir = tmp_repo / ".reviews" / "reqs" / "d00001"
    req_dir.mkdir(parents=True)
    threads_path = req_dir / "threads.json"
    threads_path.write_text(json.dumps(threads_data, indent=2))

    return threads_path


@pytest.fixture
def sample_status_json(tmp_repo: Path) -> Path:
    """
    Create a sample status.json file for d00001.

    Returns:
        Path to status.json
    """
    status_data = {
        "version": "1.0",
        "reqId": "d00001",
        "requests": [
            {
                "requestId": "req-001",
                "reqId": "d00001",
                "type": "status_change",
                "fromStatus": "Draft",
                "toStatus": "Active",
                "requestedBy": "bob",
                "requestedAt": "2025-01-01T12:00:00+00:00",
                "justification": "Ready for activation",
                "approvals": [],
                "requiredApprovers": ["product_owner", "tech_lead"],
                "state": "pending",
            }
        ],
    }

    req_dir = tmp_repo / ".reviews" / "reqs" / "d00001"
    req_dir.mkdir(parents=True, exist_ok=True)
    status_path = req_dir / "status.json"
    status_path.write_text(json.dumps(status_data, indent=2))

    return status_path


@pytest.fixture
def sample_flag_json(tmp_repo: Path) -> Path:
    """
    Create a sample flag.json file for d00001.

    Returns:
        Path to flag.json
    """
    flag_data = {
        "flaggedForReview": True,
        "flaggedBy": "charlie",
        "flaggedAt": "2025-01-01T08:00:00+00:00",
        "reason": "Needs security review",
        "scope": ["security_team", "tech_lead"],
    }

    req_dir = tmp_repo / ".reviews" / "reqs" / "d00001"
    req_dir.mkdir(parents=True, exist_ok=True)
    flag_path = req_dir / "flag.json"
    flag_path.write_text(json.dumps(flag_data, indent=2))

    return flag_path


@pytest.fixture
def flask_client(tmp_repo: Path):
    """
    Create a Flask test client for the review server.

    Requires flask to be installed.
    """
    pytest.importorskip("flask")

    from elspais.trace_view.review.server import create_app

    app = create_app(
        repo_root=tmp_repo,
        static_dir=tmp_repo,
        auto_sync=False,  # Disable auto-sync for tests
        register_static_routes=False,  # Don't register static routes for API tests
    )
    app.config["TESTING"] = True

    with app.test_client() as client:
        yield client


@pytest.fixture
def sample_requirement_content() -> str:
    """
    Return sample requirement content for position resolution tests.
    """
    return """# REQ-d00001: Sample Requirement

**Level**: Dev | **Status**: Active | **Implements**: REQ-p00001

## Assertions

A. The system SHALL authenticate users.
B. The system SHALL validate input.
C. The system SHALL log errors.

## Rationale

This requirement ensures system security.

*End* *Sample Requirement* | **Hash**: test1234
"""


# Pytest markers
def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "review: marks tests as review system tests")
    config.addinivalue_line("markers", "slow: marks tests as slow (requiring git operations)")
