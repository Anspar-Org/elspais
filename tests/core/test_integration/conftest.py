"""Fixtures for integration tests."""

import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def integration_spec_dir():
    """Create a complete spec directory for integration testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        spec_dir = Path(tmpdir) / "spec"
        spec_dir.mkdir()

        # Create PRD file
        prd_file = spec_dir / "prd-auth.md"
        prd_file.write_text(
            """\
# Authentication Product Requirements

## REQ-p00001: User Authentication

**Level**: PRD | **Status**: Active

The system SHALL provide user authentication.

## Assertions

A. Users SHALL be able to log in with email and password.
B. Users SHALL be able to log out.
C. Users SHALL be able to reset their password.

*End* *REQ-p00001* | **Hash**: abc12345

---

## REQ-p00002: Session Management

**Level**: PRD | **Status**: Active

The system SHALL manage user sessions.

## Assertions

A. Sessions SHALL expire after inactivity.
B. Users SHALL be able to view active sessions.

*End* *REQ-p00002*
"""
        )

        # Create OPS file
        ops_file = spec_dir / "ops-auth.md"
        ops_file.write_text(
            """\
# Authentication Operations Requirements

## REQ-o00001: Login Form

**Level**: OPS | **Implements**: REQ-p00001-A | **Status**: Active

The system SHALL display a login form with email and password fields.

*End* *REQ-o00001*

---

## REQ-o00002: Logout Button

**Level**: OPS | **Implements**: REQ-p00001-B | **Status**: Active

The system SHALL display a logout button in the navigation.

*End* *REQ-o00002*

---

## REQ-o00003: Password Reset Flow

**Level**: OPS | **Implements**: REQ-p00001-C | **Status**: Active

The system SHALL provide a password reset flow via email.

*End* *REQ-o00003*

---

## REQ-o00004: Session Timeout

**Level**: OPS | **Implements**: REQ-p00002-A | **Status**: Active

The system SHALL timeout sessions after 30 minutes of inactivity.

*End* *REQ-o00004*
"""
        )

        # Create config file
        config_file = Path(tmpdir) / ".elspais.toml"
        config_file.write_text(
            """\
[project]
namespace = "REQ"

[id-patterns]
canonical = "{namespace}-{level.letter}{component}"
aliases = { short = "{level.letter}{component}" }

[id-patterns.component]
style = "numeric"
digits = 5
leading_zeros = true

[levels.prd]
rank = 1
letter = "p"
implements = ["prd"]

[levels.ops]
rank = 2
letter = "o"
implements = ["ops", "prd"]

[levels.dev]
rank = 3
letter = "d"
implements = ["dev", "ops", "prd"]

[scanning.spec]
directories = ["spec"]
"""
        )

        yield Path(tmpdir)


@pytest.fixture
def multi_assertion_spec_dir():
    """Create a spec directory with multi-assertion syntax for integration testing.

    Includes:
    - A PRD with assertions A, B, C
    - An OPS using multi-assertion syntax: Implements: REQ-p00001-A+B+C
    - A code file using: # Implements: REQ-p00001-A+B
    - Config with multi_assertion_separator = "+"
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        spec_dir = Path(tmpdir) / "spec"
        spec_dir.mkdir()

        # Create PRD file with assertions A, B, C
        prd_file = spec_dir / "prd-multi.md"
        prd_file.write_text(
            """\
# Multi-Assertion Product Requirements

## REQ-p00001: Feature Alpha

**Level**: PRD | **Status**: Active

The system SHALL provide feature alpha.

## Assertions

A. The system SHALL support login.
B. The system SHALL support logout.
C. The system SHALL support password reset.

*End* *REQ-p00001* | **Hash**: aaa11111
"""
        )

        # Create OPS file using multi-assertion syntax
        ops_file = spec_dir / "ops-multi.md"
        ops_file.write_text(
            """\
# Multi-Assertion Operations Requirements

## REQ-o00001: Implement All Auth Features

**Level**: OPS | **Implements**: REQ-p00001-A+B+C | **Status**: Active

The system SHALL implement all authentication features.

*End* *REQ-o00001*
"""
        )

        # Create code directory with Python files using assertion references.
        # The code parser extracts individual refs (comma-separated), while
        # the builder's centralized expansion handles multi-assertion syntax.
        src_dir = Path(tmpdir) / "src"
        src_dir.mkdir()
        code_file = src_dir / "auth.py"
        code_file.write_text(
            """\
# Verifies: REQ-p00001-A, REQ-p00001-B
def authenticate():
    pass
"""
        )

        # Create config file with multi_assertion_separator
        config_file = Path(tmpdir) / ".elspais.toml"
        config_file.write_text(
            """\
[project]
namespace = "REQ"

[id-patterns]
canonical = "{namespace}-{level.letter}{component}"
aliases = { short = "{level.letter}{component}" }

[id-patterns.component]
style = "numeric"
digits = 5
leading_zeros = true

[id-patterns.assertions]
multi_separator = "+"

[levels.prd]
rank = 1
letter = "p"
implements = ["prd"]

[levels.ops]
rank = 2
letter = "o"
implements = ["ops", "prd"]

[levels.dev]
rank = 3
letter = "d"
implements = ["dev", "ops", "prd"]

[scanning.spec]
directories = ["spec"]

[scanning.code]
directories = ["src"]
"""
        )

        yield Path(tmpdir)
