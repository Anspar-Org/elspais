"""Pytest fixtures for DomainDeserializer tests."""

import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def temp_spec_dir():
    """Create a temporary spec directory with sample files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        spec_dir = Path(tmpdir) / "spec"
        spec_dir.mkdir()

        # Create a sample spec file
        prd_file = spec_dir / "prd.md"
        prd_file.write_text(
            """\
# Product Requirements

## REQ-p00001: User Authentication

**Level**: PRD | **Status**: Active

Users SHALL be able to authenticate.

## Assertions

A. Users can log in with email/password.
B. Users can reset their password.

*End* *REQ-p00001* | **Hash**: abc12345

---

## REQ-p00002: User Profile

**Level**: PRD | **Status**: Active

Users SHALL have profiles.

*End* *REQ-p00002*
"""
        )

        # Create an ops file
        ops_file = spec_dir / "ops.md"
        ops_file.write_text(
            """\
# Operations Requirements

## REQ-o00001: Login Flow

**Level**: OPS | **Implements**: REQ-p00001-A | **Status**: Active

The system SHALL provide a login form.

*End* *REQ-o00001*
"""
        )

        yield spec_dir
