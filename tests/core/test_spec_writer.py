# Validates REQ-o00063-A, REQ-o00063-B, REQ-o00063-D, REQ-p00004-A
"""Tests for elspais.utilities.spec_writer — spec file I/O helpers.

Validates:
- REQ-o00063-A: change_reference_type SHALL modify Implements/Refines relationships
- REQ-o00063-B: move_requirement SHALL relocate a requirement between spec files
- REQ-o00063-D: File mutations SHALL use encoding="utf-8" consistently
- REQ-p00004-A: add_changelog_entry SHALL insert changelog entries into spec files
"""

from pathlib import Path

import pytest

from elspais.utilities.spec_writer import (
    add_assertion_to_file,
    add_changelog_entry,
    add_status_to_file,
    change_reference_type,
    modify_assertion_text,
    modify_implements,
    modify_status,
    move_requirement,
    update_hash_in_file,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

MINIMAL_SPEC = """\
## REQ-t00001: Test Requirement

**Level**: DEV | **Status**: Active | **Implements**: REQ-p00001

**A.** The system SHALL do something.

*End* *Test Requirement* | **Hash**: abcd1234
---
"""

TWO_REQ_SPEC = """\
## REQ-t00001: First Requirement

**Level**: DEV | **Status**: Active | **Implements**: REQ-p00001

**A.** The system SHALL do the first thing.

*End* *First Requirement* | **Hash**: aaaa1111
---

## REQ-t00002: Second Requirement

**Level**: DEV | **Status**: Draft | **Implements**: REQ-p00002

**A.** The system SHALL do the second thing.

*End* *Second Requirement* | **Hash**: bbbb2222
---
"""


@pytest.fixture()
def spec_file(tmp_path: Path) -> Path:
    """Create a minimal spec file for testing."""
    p = tmp_path / "test_spec.md"
    p.write_text(MINIMAL_SPEC, encoding="utf-8")
    return p


@pytest.fixture()
def two_req_file(tmp_path: Path) -> Path:
    """Create a spec file with two requirements."""
    p = tmp_path / "two_reqs.md"
    p.write_text(TWO_REQ_SPEC, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# change_reference_type  (REQ-o00063-A)
# ---------------------------------------------------------------------------


class TestChangeReferenceType:
    """Tests for change_reference_type.

    Validates REQ-o00063-A: change_reference_type SHALL modify
    Implements/Refines relationships in spec files.
    """

    def test_REQ_o00063_A_implements_to_refines(self, spec_file: Path):
        """Changing Implements to Refines updates the spec file."""
        result = change_reference_type(spec_file, "REQ-t00001", "REQ-p00001", "REFINES")
        assert result["success"] is True

        content = spec_file.read_text(encoding="utf-8")
        assert "**Refines**: REQ-p00001" in content
        assert "**Implements**: REQ-p00001" not in content

    def test_REQ_o00063_A_refines_to_implements(self, tmp_path: Path):
        """Changing Refines back to Implements updates the spec file."""
        spec = tmp_path / "refines.md"
        spec.write_text(
            MINIMAL_SPEC.replace("**Implements**: REQ-p00001", "**Refines**: REQ-p00001"),
            encoding="utf-8",
        )

        result = change_reference_type(spec, "REQ-t00001", "REQ-p00001", "IMPLEMENTS")
        assert result["success"] is True

        content = spec.read_text(encoding="utf-8")
        assert "**Implements**: REQ-p00001" in content
        assert "**Refines**: REQ-p00001" not in content

    def test_REQ_o00063_A_invalid_type_rejected(self, spec_file: Path):
        """Invalid reference type returns an error."""
        result = change_reference_type(spec_file, "REQ-t00001", "REQ-p00001", "DEPENDS")
        assert result["success"] is False
        assert "Invalid reference type" in result["error"]

    def test_REQ_o00063_A_missing_target_returns_error(self, spec_file: Path):
        """Reference to a non-existent target returns an error."""
        result = change_reference_type(spec_file, "REQ-t00001", "REQ-p99999", "REFINES")
        assert result["success"] is False
        assert "not found" in result["error"]

    def test_REQ_o00063_A_case_insensitive_type(self, spec_file: Path):
        """Type argument is case-insensitive ('refines', 'REFINES', 'Refines')."""
        result = change_reference_type(spec_file, "REQ-t00001", "REQ-p00001", "refines")
        assert result["success"] is True

        content = spec_file.read_text(encoding="utf-8")
        assert "**Refines**: REQ-p00001" in content


# ---------------------------------------------------------------------------
# modify_implements  (REQ-o00063-A)
# ---------------------------------------------------------------------------


class TestModifyImplements:
    """Tests for modify_implements.

    Validates REQ-o00063-A: modify_implements SHALL change the
    Implements field of a requirement in a spec file.
    """

    def test_REQ_o00063_A_change_implements_target(self, spec_file: Path):
        """Changing implements target updates the file."""
        result = modify_implements(spec_file, "REQ-t00001", ["REQ-p00099"])
        assert result["success"] is True
        assert result["old_implements"] == ["REQ-p00001"]
        assert result["new_implements"] == ["REQ-p00099"]

        content = spec_file.read_text(encoding="utf-8")
        assert "REQ-p00099" in content
        assert "REQ-p00001" not in content

    def test_REQ_o00063_A_clear_implements_to_dash(self, spec_file: Path):
        """Empty list sets implements to '-'."""
        result = modify_implements(spec_file, "REQ-t00001", [])
        assert result["success"] is True

        content = spec_file.read_text(encoding="utf-8")
        assert "**Implements**: -" in content

    def test_REQ_o00063_A_multiple_implements(self, spec_file: Path):
        """Multiple implements targets are comma-separated."""
        result = modify_implements(spec_file, "REQ-t00001", ["REQ-p00001", "REQ-p00002"])
        assert result["success"] is True

        content = spec_file.read_text(encoding="utf-8")
        assert "REQ-p00001, REQ-p00002" in content

    def test_REQ_o00063_A_dry_run_no_file_change(self, spec_file: Path):
        """dry_run=True returns result without modifying the file."""
        result = modify_implements(spec_file, "REQ-t00001", ["REQ-p00099"], dry_run=True)
        assert result["success"] is True
        assert result["dry_run"] is True

        content = spec_file.read_text(encoding="utf-8")
        assert "REQ-p00001" in content  # unchanged
        assert "REQ-p00099" not in content

    def test_REQ_o00063_A_no_change_same_value(self, spec_file: Path):
        """Same value returns no_change=True without rewriting."""
        result = modify_implements(spec_file, "REQ-t00001", ["REQ-p00001"])
        assert result["success"] is True
        assert result.get("no_change") is True

    def test_REQ_o00063_A_missing_req_returns_error(self, spec_file: Path):
        """Non-existent requirement returns error."""
        result = modify_implements(spec_file, "REQ-z99999", ["REQ-p00001"])
        assert result["success"] is False
        assert "not found" in result["error"]


# ---------------------------------------------------------------------------
# modify_status  (REQ-o00063-A)
# ---------------------------------------------------------------------------


class TestModifyStatus:
    """Tests for modify_status.

    Validates REQ-o00063-A: modify_status SHALL change the Status
    field of a requirement in a spec file.
    """

    def test_REQ_o00063_A_change_status(self, spec_file: Path):
        """Changing status from Active to Deprecated updates the file."""
        result = modify_status(spec_file, "REQ-t00001", "Deprecated")
        assert result["success"] is True
        assert result["old_status"] == "Active"
        assert result["new_status"] == "Deprecated"

        content = spec_file.read_text(encoding="utf-8")
        assert "**Status**: Deprecated" in content
        assert "**Status**: Active" not in content

    def test_REQ_o00063_A_dry_run_preserves_file(self, spec_file: Path):
        """dry_run=True returns result without modifying status."""
        result = modify_status(spec_file, "REQ-t00001", "Deprecated", dry_run=True)
        assert result["success"] is True
        assert result["dry_run"] is True

        content = spec_file.read_text(encoding="utf-8")
        assert "**Status**: Active" in content

    def test_REQ_o00063_A_no_change_same_status(self, spec_file: Path):
        """Same status value returns no_change=True."""
        result = modify_status(spec_file, "REQ-t00001", "Active")
        assert result["success"] is True
        assert result.get("no_change") is True

    def test_REQ_o00063_A_missing_req_returns_error(self, spec_file: Path):
        """Non-existent requirement returns error."""
        result = modify_status(spec_file, "REQ-z99999", "Active")
        assert result["success"] is False
        assert "not found" in result["error"]


# ---------------------------------------------------------------------------
# move_requirement  (REQ-o00063-B)
# ---------------------------------------------------------------------------


class TestMoveRequirement:
    """Tests for move_requirement.

    Validates REQ-o00063-B: move_requirement SHALL relocate a
    requirement between spec files.
    """

    def test_REQ_o00063_B_move_to_new_file(self, spec_file: Path, tmp_path: Path):
        """Requirement is removed from source and appended to destination."""
        dest = tmp_path / "dest.md"
        dest.write_text("", encoding="utf-8")

        result = move_requirement(spec_file, dest, "REQ-t00001")
        assert result["success"] is True

        src_content = spec_file.read_text(encoding="utf-8")
        assert "REQ-t00001" not in src_content

        dest_content = dest.read_text(encoding="utf-8")
        assert "REQ-t00001" in dest_content
        assert "**Hash**: abcd1234" in dest_content

    def test_REQ_o00063_B_source_marked_empty(self, spec_file: Path, tmp_path: Path):
        """After moving the only requirement, source_empty is True."""
        dest = tmp_path / "dest.md"
        dest.write_text("", encoding="utf-8")

        result = move_requirement(spec_file, dest, "REQ-t00001")
        assert result["source_empty"] is True

    def test_REQ_o00063_B_move_one_of_two(self, two_req_file: Path, tmp_path: Path):
        """Moving one requirement leaves the other intact."""
        dest = tmp_path / "dest.md"
        dest.write_text("", encoding="utf-8")

        result = move_requirement(two_req_file, dest, "REQ-t00001")
        assert result["success"] is True
        assert result["source_empty"] is False

        src_content = two_req_file.read_text(encoding="utf-8")
        assert "REQ-t00001" not in src_content
        assert "REQ-t00002" in src_content

        dest_content = dest.read_text(encoding="utf-8")
        assert "REQ-t00001" in dest_content

    def test_REQ_o00063_B_dry_run_no_file_changes(self, spec_file: Path, tmp_path: Path):
        """dry_run=True returns result without modifying either file."""
        dest = tmp_path / "dest.md"
        dest.write_text("", encoding="utf-8")

        result = move_requirement(spec_file, dest, "REQ-t00001", dry_run=True)
        assert result["success"] is True
        assert result["dry_run"] is True

        src_content = spec_file.read_text(encoding="utf-8")
        assert "REQ-t00001" in src_content  # unchanged

        dest_content = dest.read_text(encoding="utf-8")
        assert "REQ-t00001" not in dest_content  # still empty

    def test_REQ_o00063_B_missing_req_returns_error(self, spec_file: Path, tmp_path: Path):
        """Non-existent requirement returns error."""
        dest = tmp_path / "dest.md"
        dest.write_text("", encoding="utf-8")

        result = move_requirement(spec_file, dest, "REQ-z99999")
        assert result["success"] is False
        assert "not found" in result["error"]

    def test_REQ_o00063_B_dest_gets_separator(self, spec_file: Path, tmp_path: Path):
        """Moved block ends with --- separator in destination."""
        dest = tmp_path / "dest.md"
        dest.write_text("", encoding="utf-8")

        move_requirement(spec_file, dest, "REQ-t00001")

        dest_content = dest.read_text(encoding="utf-8")
        assert dest_content.rstrip().endswith("---")


# ---------------------------------------------------------------------------
# update_hash_in_file  (REQ-o00063-A)
# ---------------------------------------------------------------------------


class TestUpdateHashInFile:
    """Tests for update_hash_in_file.

    Validates REQ-o00063-A: update_hash_in_file SHALL update the
    hash in the End marker of a spec file.
    """

    def test_REQ_o00063_A_update_hash(self, spec_file: Path):
        """Hash value in the End marker is replaced."""
        err = update_hash_in_file(spec_file, "REQ-t00001", "deadbeef")
        assert err is None

        content = spec_file.read_text(encoding="utf-8")
        assert "**Hash**: deadbeef" in content
        assert "abcd1234" not in content

    def test_REQ_o00063_A_missing_req_returns_error(self, spec_file: Path):
        """Non-existent requirement returns descriptive error."""
        err = update_hash_in_file(spec_file, "REQ-z99999", "deadbeef")
        assert err is not None
        assert "not found" in err

    def test_REQ_o00063_A_preserves_surrounding_content(self, two_req_file: Path):
        """Updating hash for one requirement does not affect another."""
        err = update_hash_in_file(two_req_file, "REQ-t00001", "newh1111")
        assert err is None

        content = two_req_file.read_text(encoding="utf-8")
        assert "**Hash**: newh1111" in content
        assert "**Hash**: bbbb2222" in content  # second req unchanged


# ---------------------------------------------------------------------------
# UTF-8 encoding consistency  (REQ-o00063-D)
# ---------------------------------------------------------------------------


class TestEncodingConsistency:
    """Tests for UTF-8 encoding on all file writes.

    Validates REQ-o00063-D: File mutations SHALL use encoding='utf-8'
    consistently (the encoding bug fix).
    """

    def test_REQ_o00063_D_unicode_survives_modify_implements(self, tmp_path: Path):
        """Non-ASCII content is preserved through modify_implements."""
        spec = tmp_path / "unicode.md"
        unicode_spec = MINIMAL_SPEC.replace("Test Requirement", "Prueba Requisicion")
        spec.write_text(unicode_spec, encoding="utf-8")

        modify_implements(spec, "REQ-t00001", ["REQ-p00099"])

        content = spec.read_text(encoding="utf-8")
        assert "Prueba Requisicion" in content

    def test_REQ_o00063_D_unicode_survives_modify_status(self, tmp_path: Path):
        """Non-ASCII content is preserved through modify_status."""
        spec = tmp_path / "unicode.md"
        unicode_spec = MINIMAL_SPEC.replace("do something", "hacer algo especial")
        spec.write_text(unicode_spec, encoding="utf-8")

        modify_status(spec, "REQ-t00001", "Deprecated")

        content = spec.read_text(encoding="utf-8")
        assert "hacer algo especial" in content

    def test_REQ_o00063_D_unicode_survives_move(self, tmp_path: Path):
        """Non-ASCII content is preserved through move_requirement."""
        src = tmp_path / "src.md"
        dest = tmp_path / "dest.md"
        unicode_spec = MINIMAL_SPEC.replace("do something", "faire quelque chose")
        src.write_text(unicode_spec, encoding="utf-8")
        dest.write_text("", encoding="utf-8")

        move_requirement(src, dest, "REQ-t00001")

        content = dest.read_text(encoding="utf-8")
        assert "faire quelque chose" in content

    def test_REQ_o00063_D_unicode_survives_change_reference_type(self, tmp_path: Path):
        """Non-ASCII content is preserved through change_reference_type."""
        spec = tmp_path / "unicode.md"
        unicode_spec = MINIMAL_SPEC.replace("do something", "etwas tun")
        spec.write_text(unicode_spec, encoding="utf-8")

        change_reference_type(spec, "REQ-t00001", "REQ-p00001", "REFINES")

        content = spec.read_text(encoding="utf-8")
        assert "etwas tun" in content

    def test_REQ_o00063_D_unicode_survives_update_hash(self, tmp_path: Path):
        """Non-ASCII content is preserved through update_hash_in_file."""
        spec = tmp_path / "unicode.md"
        unicode_spec = MINIMAL_SPEC.replace("do something", "hacer algo")
        spec.write_text(unicode_spec, encoding="utf-8")

        update_hash_in_file(spec, "REQ-t00001", "deadbeef")

        content = spec.read_text(encoding="utf-8")
        assert "hacer algo" in content
        assert "**Hash**: deadbeef" in content


# ---------------------------------------------------------------------------
# add_changelog_entry  (REQ-p00004-A)
# ---------------------------------------------------------------------------

SPEC_WITHOUT_CHANGELOG = """\
# REQ-t00001: Test Req

**Level**: DEV | **Status**: Active | **Implements**: -

## Assertions

A. The system SHALL do X.

*End* *Test Req* | **Hash**: abcdef12
---
"""

SPEC_WITH_CHANGELOG = """\
# REQ-t00001: Test Req

**Level**: DEV | **Status**: Active | **Implements**: -

## Assertions

A. The system SHALL do X.

## Changelog

- 2026-02-15 | bf63eda5 | CUR-1200 | Bob (b@b.org) | First version

*End* *Test Req* | **Hash**: abcdef12
---
"""

CHANGELOG_ENTRY = {
    "date": "2026-03-06",
    "hash": "abcdef12",
    "change_order": "CUR-1234",
    "author_name": "Alice",
    "author_id": "a@b.org",
    "reason": "Refined A",
}


class TestAddChangelogEntry:
    """Tests for add_changelog_entry.

    Validates REQ-p00004-A: add_changelog_entry SHALL insert changelog
    entries into spec files.
    """

    def test_REQ_p00004_A_adds_changelog_to_req_without_section(self, tmp_path: Path):
        """A requirement without ## Changelog gets a new section created."""
        spec = tmp_path / "spec.md"
        spec.write_text(SPEC_WITHOUT_CHANGELOG, encoding="utf-8")

        err = add_changelog_entry(spec, "REQ-t00001", CHANGELOG_ENTRY)
        assert err is None

        content = spec.read_text(encoding="utf-8")
        # Section was created
        assert "## Changelog" in content
        # Entry is present with correct format
        assert "- 2026-03-06 | abcdef12 | CUR-1234 | Alice (a@b.org) | Refined A" in content
        # Changelog appears between assertions and End marker
        changelog_pos = content.index("## Changelog")
        assertion_pos = content.index("A. The system SHALL do X.")
        end_pos = content.index("*End*")
        assert assertion_pos < changelog_pos < end_pos

    def test_REQ_p00004_A_prepends_entry_to_existing_changelog(self, tmp_path: Path):
        """A requirement with existing ## Changelog gets the new entry at the top."""
        spec = tmp_path / "spec.md"
        spec.write_text(SPEC_WITH_CHANGELOG, encoding="utf-8")

        err = add_changelog_entry(spec, "REQ-t00001", CHANGELOG_ENTRY)
        assert err is None

        content = spec.read_text(encoding="utf-8")
        # Both entries present
        new_entry = "- 2026-03-06 | abcdef12 | CUR-1234 | Alice (a@b.org) | Refined A"
        old_entry = "- 2026-02-15 | bf63eda5 | CUR-1200 | Bob (b@b.org) | First version"
        assert new_entry in content
        assert old_entry in content
        # New entry appears before old entry
        assert content.index(new_entry) < content.index(old_entry)

    def test_REQ_p00004_A_returns_error_for_missing_req(self, tmp_path: Path):
        """Returns error string when req_id not found in file."""
        spec = tmp_path / "spec.md"
        spec.write_text(SPEC_WITHOUT_CHANGELOG, encoding="utf-8")

        err = add_changelog_entry(spec, "REQ-z99999", CHANGELOG_ENTRY)
        assert err is not None
        assert isinstance(err, str)
        assert "not found" in err


# ---------------------------------------------------------------------------
# Subheading false-positive regression  (CUR-1003)
# ---------------------------------------------------------------------------

# The bug: _find_next_req_header used `^#+ [A-Z]+-` which matched subheadings
# inside a requirement body (e.g., `### OS-Level Notifications`) because "OS-"
# matches [A-Z]+-. This caused the ownership check to believe the End marker
# belonged to a different requirement. The fix narrows the pattern to only
# match the configured requirement prefix (e.g., `^#+ REQ-`).

SPEC_WITH_SUBHEADING = """\
# REQ-t00001: Questionnaire Session Management

**Level**: PRD | **Status**: Draft | **Implements**: -

## Assertions

### Readiness Gate

A. The system SHALL display a readiness screen.

### OS-Level Notifications

B. The system SHALL deliver an OS-level push notification.

### UI-Driven Alerts

C. The system SHALL show in-app expiry messages.

*End* *Questionnaire Session Management* | **Hash**: 00000000
---
"""

SPEC_WITH_SUBHEADING_NO_STATUS = """\
# REQ-t00001: Questionnaire Session Management

**Level**: PRD | **Implements**: -

## Assertions

### Readiness Gate

A. The system SHALL display a readiness screen.

### OS-Level Notifications

B. The system SHALL deliver an OS-level push notification.

*End* *Questionnaire Session Management* | **Hash**: 00000000
---
"""


class TestSubheadingFalsePositiveRegression:
    """Regression tests for CUR-1003: subheadings inside REQ body falsely
    detected as requirement boundaries.

    The old regex `^#+ [A-Z]+-` matched subheadings like `### OS-Level` or
    `### UI-Driven` because they start with uppercase letters followed by a
    hyphen. This caused spec_writer to think the End marker belonged to a
    different requirement.

    Validates REQ-p00004-A: The tool SHALL compute and verify content hashes
    for change detection.
    """

    def test_REQ_p00004_A_update_hash_with_subheadings(self, tmp_path: Path):
        """update_hash_in_file succeeds when the REQ body contains
        subheadings like ### OS-Level Notifications."""
        spec = tmp_path / "spec.md"
        spec.write_text(SPEC_WITH_SUBHEADING, encoding="utf-8")

        err = update_hash_in_file(spec, "REQ-t00001", "deadbeef")
        assert err is None

        content = spec.read_text(encoding="utf-8")
        assert "**Hash**: deadbeef" in content
        # Subheadings preserved
        assert "### OS-Level Notifications" in content
        assert "### UI-Driven Alerts" in content

    def test_REQ_p00004_A_add_status_with_subheadings(self, tmp_path: Path):
        """add_status_to_file works when REQ body has subheadings."""
        spec = tmp_path / "spec.md"
        spec.write_text(SPEC_WITH_SUBHEADING_NO_STATUS, encoding="utf-8")

        err = add_status_to_file(spec, "REQ-t00001", "Active")
        assert err is None

        content = spec.read_text(encoding="utf-8")
        assert "**Status**: Active" in content

    def test_REQ_p00004_A_modify_assertion_with_subheadings(self, tmp_path: Path):
        """modify_assertion_text works when REQ body has subheadings."""
        spec = tmp_path / "spec.md"
        spec.write_text(SPEC_WITH_SUBHEADING, encoding="utf-8")

        result = modify_assertion_text(
            spec, "REQ-t00001", "A", "The system SHALL show a readiness check."
        )
        assert result["success"] is True

        content = spec.read_text(encoding="utf-8")
        assert "show a readiness check" in content

    def test_REQ_p00004_A_add_assertion_with_subheadings(self, tmp_path: Path):
        """add_assertion_to_file works when REQ body has subheadings."""
        spec = tmp_path / "spec.md"
        spec.write_text(SPEC_WITH_SUBHEADING, encoding="utf-8")

        result = add_assertion_to_file(
            spec, "REQ-t00001", "D", "The system SHALL track session state."
        )
        assert result["success"] is True

        content = spec.read_text(encoding="utf-8")
        assert "track session state" in content

        content = spec.read_text(encoding="utf-8")
        assert "track session state" in content
