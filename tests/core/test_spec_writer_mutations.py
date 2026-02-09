# Implements: REQ-o00063-G, REQ-o00063-H, REQ-o00063-I
# Validates REQ-o00063-G, REQ-o00063-H, REQ-o00063-I
"""Tests for spec_writer title/assertion mutation functions.

Validates:
- REQ-o00063-G: modify_title SHALL replace a requirement's title in the header
- REQ-o00063-H: modify_assertion_text SHALL replace assertion text, handling multi-line
- REQ-o00063-I: add_assertion_to_file SHALL insert a new assertion after the last existing one
"""

from pathlib import Path

import pytest

from elspais.utilities.spec_writer import (
    add_assertion_to_file,
    modify_assertion_text,
    modify_title,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

MINIMAL_SPEC = """\
## REQ-t00001: Test Requirement

**Level**: DEV | **Status**: Active | **Implements**: REQ-p00001

## Assertions

A. The system SHALL do something.
B. The system SHALL do another thing.

## Rationale

This is a test requirement.

*End* *Test Requirement* | **Hash**: abcd1234
---
"""

TWO_REQ_SPEC = """\
## REQ-t00001: First Requirement

**Level**: DEV | **Status**: Active | **Implements**: REQ-p00001

## Assertions

A. The system SHALL do the first thing.
B. The system SHALL do the second thing.

*End* *First Requirement* | **Hash**: aaaa1111
---

## REQ-t00002: Second Requirement

**Level**: DEV | **Status**: Draft | **Implements**: REQ-p00002

## Assertions

A. The system SHALL handle the second requirement.

*End* *Second Requirement* | **Hash**: bbbb2222
---
"""

MULTILINE_ASSERTION_SPEC = """\
## REQ-t00001: Multi-line Test

**Level**: DEV | **Status**: Active | **Implements**: REQ-p00001

## Assertions

A. The system SHALL do something that is described
   across multiple lines for readability.
B. The system SHALL do a simple thing.

*End* *Multi-line Test* | **Hash**: cccc3333
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


@pytest.fixture()
def multiline_file(tmp_path: Path) -> Path:
    """Create a spec file with a multi-line assertion."""
    p = tmp_path / "multiline.md"
    p.write_text(MULTILINE_ASSERTION_SPEC, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# modify_title  (REQ-o00063-G)
# ---------------------------------------------------------------------------


class TestModifyTitle:
    """Tests for modify_title.

    Validates REQ-o00063-G: modify_title SHALL replace a requirement's
    title in the spec file header line.
    """

    def test_REQ_o00063_G_modify_title_happy_path(self, spec_file: Path):
        """Title is replaced in the header line."""
        result = modify_title(spec_file, "REQ-t00001", "Updated Title")
        assert result["success"] is True
        assert result["old_title"] == "Test Requirement"
        assert result["new_title"] == "Updated Title"
        assert result["dry_run"] is False

        content = spec_file.read_text(encoding="utf-8")
        assert "## REQ-t00001: Updated Title" in content
        assert "## REQ-t00001: Test Requirement" not in content

    def test_REQ_o00063_G_modify_title_dry_run(self, spec_file: Path):
        """dry_run=True returns result without modifying the file."""
        result = modify_title(spec_file, "REQ-t00001", "New Title", dry_run=True)
        assert result["success"] is True
        assert result["old_title"] == "Test Requirement"
        assert result["new_title"] == "New Title"
        assert result["dry_run"] is True

        content = spec_file.read_text(encoding="utf-8")
        assert "## REQ-t00001: Test Requirement" in content
        assert "New Title" not in content

    def test_REQ_o00063_G_modify_title_req_not_found(self, spec_file: Path):
        """Non-existent requirement returns error."""
        result = modify_title(spec_file, "REQ-z99999", "New Title")
        assert result["success"] is False
        assert "not found" in result["error"]

    def test_REQ_o00063_G_modify_title_no_change(self, spec_file: Path):
        """Same title returns no_change=True without rewriting."""
        result = modify_title(spec_file, "REQ-t00001", "Test Requirement")
        assert result["success"] is True
        assert result.get("no_change") is True

    def test_REQ_o00063_G_modify_title_preserves_surrounding(self, two_req_file: Path):
        """Modifying title of one requirement does not affect another."""
        result = modify_title(two_req_file, "REQ-t00001", "Changed First")
        assert result["success"] is True

        content = two_req_file.read_text(encoding="utf-8")
        assert "## REQ-t00001: Changed First" in content
        assert "## REQ-t00002: Second Requirement" in content
        # Ensure the second requirement's body is intact
        assert "**Hash**: bbbb2222" in content

    def test_REQ_o00063_G_modify_title_unicode(self, tmp_path: Path):
        """Non-ASCII characters are preserved in the new title."""
        spec = tmp_path / "unicode.md"
        spec.write_text(MINIMAL_SPEC, encoding="utf-8")

        result = modify_title(spec, "REQ-t00001", "Requisito de Prueba")
        assert result["success"] is True

        content = spec.read_text(encoding="utf-8")
        assert "Requisito de Prueba" in content
        # Ensure the rest of the file is intact
        assert "**Hash**: abcd1234" in content


# ---------------------------------------------------------------------------
# modify_assertion_text  (REQ-o00063-H)
# ---------------------------------------------------------------------------


class TestModifyAssertionText:
    """Tests for modify_assertion_text.

    Validates REQ-o00063-H: modify_assertion_text SHALL replace an
    assertion's text within the requirement block, handling multi-line
    assertions.
    """

    def test_REQ_o00063_H_modify_assertion_happy_path(self, spec_file: Path):
        """Assertion text is replaced within the requirement block."""
        result = modify_assertion_text(
            spec_file, "REQ-t00001", "A", "The system SHALL do something new."
        )
        assert result["success"] is True
        assert result["old_text"] == "The system SHALL do something."
        assert result["new_text"] == "The system SHALL do something new."
        assert result["dry_run"] is False

        content = spec_file.read_text(encoding="utf-8")
        assert "A. The system SHALL do something new." in content
        assert "A. The system SHALL do something." not in content

    def test_REQ_o00063_H_modify_assertion_dry_run(self, spec_file: Path):
        """dry_run=True returns result without modifying the file."""
        result = modify_assertion_text(spec_file, "REQ-t00001", "A", "New text.", dry_run=True)
        assert result["success"] is True
        assert result["dry_run"] is True

        content = spec_file.read_text(encoding="utf-8")
        assert "A. The system SHALL do something." in content
        assert "New text." not in content

    def test_REQ_o00063_H_modify_assertion_req_not_found(self, spec_file: Path):
        """Non-existent requirement returns error."""
        result = modify_assertion_text(spec_file, "REQ-z99999", "A", "New text.")
        assert result["success"] is False
        assert "not found" in result["error"]

    def test_REQ_o00063_H_modify_assertion_label_not_found(self, spec_file: Path):
        """Non-existent assertion label returns error."""
        result = modify_assertion_text(spec_file, "REQ-t00001", "Z", "New text.")
        assert result["success"] is False
        assert "Assertion Z not found" in result["error"]

    def test_REQ_o00063_H_modify_assertion_no_change(self, spec_file: Path):
        """Same text returns no_change=True."""
        result = modify_assertion_text(
            spec_file, "REQ-t00001", "A", "The system SHALL do something."
        )
        assert result["success"] is True
        assert result.get("no_change") is True

    def test_REQ_o00063_H_modify_second_assertion(self, spec_file: Path):
        """Modifying assertion B leaves assertion A intact."""
        result = modify_assertion_text(
            spec_file, "REQ-t00001", "B", "The system SHALL do a new thing."
        )
        assert result["success"] is True
        assert result["old_text"] == "The system SHALL do another thing."

        content = spec_file.read_text(encoding="utf-8")
        assert "A. The system SHALL do something." in content
        assert "B. The system SHALL do a new thing." in content

    def test_REQ_o00063_H_modify_multiline_assertion(self, multiline_file: Path):
        """Multi-line assertion text (with continuation lines) is fully replaced."""
        result = modify_assertion_text(
            multiline_file, "REQ-t00001", "A", "The system SHALL do a simple replacement."
        )
        assert result["success"] is True
        # The old text should span both lines
        assert "across multiple lines" in result["old_text"]
        assert "described" in result["old_text"]

        content = multiline_file.read_text(encoding="utf-8")
        assert "A. The system SHALL do a simple replacement." in content
        # Continuation line should be gone
        assert "across multiple lines" not in content
        # Assertion B should be intact
        assert "B. The system SHALL do a simple thing." in content

    def test_REQ_o00063_H_modify_assertion_preserves_other_req(self, two_req_file: Path):
        """Modifying assertion in one requirement does not affect another."""
        result = modify_assertion_text(two_req_file, "REQ-t00001", "A", "Changed first assertion.")
        assert result["success"] is True

        content = two_req_file.read_text(encoding="utf-8")
        assert "A. Changed first assertion." in content
        # Second requirement's assertion A should be untouched
        assert "A. The system SHALL handle the second requirement." in content


# ---------------------------------------------------------------------------
# add_assertion_to_file  (REQ-o00063-I)
# ---------------------------------------------------------------------------


class TestAddAssertionToFile:
    """Tests for add_assertion_to_file.

    Validates REQ-o00063-I: add_assertion_to_file SHALL insert a new
    assertion after the last existing assertion in the Assertions section.
    """

    def test_REQ_o00063_I_add_assertion_happy_path(self, spec_file: Path):
        """New assertion is inserted after the last existing assertion."""
        result = add_assertion_to_file(
            spec_file, "REQ-t00001", "C", "The system SHALL do a third thing."
        )
        assert result["success"] is True
        assert result["label"] == "C"
        assert result["dry_run"] is False

        content = spec_file.read_text(encoding="utf-8")
        assert "C. The system SHALL do a third thing." in content
        # Ensure it appears after B
        b_pos = content.index("B. The system SHALL do another thing.")
        c_pos = content.index("C. The system SHALL do a third thing.")
        assert c_pos > b_pos

    def test_REQ_o00063_I_add_assertion_dry_run(self, spec_file: Path):
        """dry_run=True returns result without modifying the file."""
        result = add_assertion_to_file(spec_file, "REQ-t00001", "C", "New assertion.", dry_run=True)
        assert result["success"] is True
        assert result["dry_run"] is True

        content = spec_file.read_text(encoding="utf-8")
        assert "C. New assertion." not in content

    def test_REQ_o00063_I_add_assertion_req_not_found(self, spec_file: Path):
        """Non-existent requirement returns error."""
        result = add_assertion_to_file(spec_file, "REQ-z99999", "A", "Text.")
        assert result["success"] is False
        assert "not found" in result["error"]

    def test_REQ_o00063_I_add_assertion_no_assertions_section(self, tmp_path: Path):
        """Requirement with no ## Assertions section returns error."""
        spec = tmp_path / "no_assertions.md"
        spec.write_text(
            "## REQ-t00001: No Assertions\n\n"
            "**Level**: DEV | **Status**: Active | **Implements**: -\n\n"
            "*End* *No Assertions* | **Hash**: eeee5555\n---\n",
            encoding="utf-8",
        )

        result = add_assertion_to_file(spec, "REQ-t00001", "A", "New assertion.")
        assert result["success"] is False
        assert "No ## Assertions section" in result["error"]

    def test_REQ_o00063_I_add_assertion_preserves_surrounding(self, two_req_file: Path):
        """Adding assertion to first requirement does not affect second."""
        result = add_assertion_to_file(two_req_file, "REQ-t00001", "C", "A third assertion.")
        assert result["success"] is True

        content = two_req_file.read_text(encoding="utf-8")
        assert "C. A third assertion." in content
        # Second requirement should be unchanged
        assert "## REQ-t00002: Second Requirement" in content
        assert "**Hash**: bbbb2222" in content

    def test_REQ_o00063_I_add_assertion_after_multiline(self, multiline_file: Path):
        """New assertion is inserted after multi-line assertion properly."""
        result = add_assertion_to_file(
            multiline_file, "REQ-t00001", "C", "A new assertion after multiline."
        )
        assert result["success"] is True

        content = multiline_file.read_text(encoding="utf-8")
        assert "C. A new assertion after multiline." in content
        # Ensure it appears after B (not in the middle of A's continuation)
        b_pos = content.index("B. The system SHALL do a simple thing.")
        c_pos = content.index("C. A new assertion after multiline.")
        assert c_pos > b_pos

    def test_REQ_o00063_I_add_assertion_unicode(self, tmp_path: Path):
        """Non-ASCII text in assertion is preserved."""
        spec = tmp_path / "unicode.md"
        spec.write_text(MINIMAL_SPEC, encoding="utf-8")

        result = add_assertion_to_file(
            spec, "REQ-t00001", "C", "El sistema DEBE hacer algo especial."
        )
        assert result["success"] is True

        content = spec.read_text(encoding="utf-8")
        assert "C. El sistema DEBE hacer algo especial." in content
