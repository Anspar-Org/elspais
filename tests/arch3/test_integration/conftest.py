"""Fixtures for integration tests."""

import pytest
import tempfile
from pathlib import Path


@pytest.fixture
def integration_spec_dir():
    """Create a complete spec directory for integration testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        spec_dir = Path(tmpdir) / "spec"
        spec_dir.mkdir()

        # Create PRD file
        prd_file = spec_dir / "prd-auth.md"
        prd_file.write_text("""\
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
""")

        # Create OPS file
        ops_file = spec_dir / "ops-auth.md"
        ops_file.write_text("""\
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
""")

        # Create config file
        config_file = Path(tmpdir) / ".elspais.toml"
        config_file.write_text("""\
[patterns]
prefix = "REQ"
id_template = "{prefix}-{type}{id}"

[patterns.types.prd]
id = "p"
name = "PRD"
level = 1

[patterns.types.ops]
id = "o"
name = "OPS"
level = 2

[patterns.types.dev]
id = "d"
name = "DEV"
level = 3

[patterns.id_format]
style = "numeric"
digits = 5
leading_zeros = true

[spec]
directories = ["spec"]
""")

        yield Path(tmpdir)
