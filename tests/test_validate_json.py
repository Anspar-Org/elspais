"""
Tests for validate command JSON output.
"""

import json
from argparse import Namespace
from pathlib import Path

import pytest

from elspais.commands.validate import format_requirements_json
from elspais.core.models import Requirement, Assertion
from elspais.core.rules import RuleViolation, Severity


class TestFormatRequirementsJson:
    """Tests for the JSON output formatter."""

    def test_basic_requirement_output(self, tmp_path: Path):
        """Test basic requirement is serialized correctly."""
        req = Requirement(
            id="REQ-p00001",
            title="Test Requirement",
            level="PRD",
            status="Active",
            body="The system SHALL do something.",
            implements=["p00000"],
            hash="a1b2c3d4",
            file_path=tmp_path / "test.md",
            line_number=10,
        )

        result = format_requirements_json({"REQ-p00001": req}, [])
        data = json.loads(result)

        assert "REQ-p00001" in data
        assert data["REQ-p00001"]["title"] == "Test Requirement"
        assert data["REQ-p00001"]["status"] == "Active"
        assert data["REQ-p00001"]["level"] == "PRD"
        assert data["REQ-p00001"]["body"] == "The system SHALL do something."
        assert data["REQ-p00001"]["implements"] == ["p00000"]
        assert data["REQ-p00001"]["hash"] == "a1b2c3d4"
        assert data["REQ-p00001"]["line"] == 10
        assert data["REQ-p00001"]["file"] == "test.md"
        assert data["REQ-p00001"]["isConflict"] is False
        assert data["REQ-p00001"]["isCycle"] is False

    def test_requirement_with_rationale(self, tmp_path: Path):
        """Test requirement with rationale field."""
        req = Requirement(
            id="REQ-d00001",
            title="Dev Requirement",
            level="DEV",
            status="Active",
            body="The module SHALL implement X.",
            rationale="This is needed for Y.",
            file_path=tmp_path / "dev.md",
            line_number=5,
        )

        result = format_requirements_json({"REQ-d00001": req}, [])
        data = json.loads(result)

        assert data["REQ-d00001"]["rationale"] == "This is needed for Y."

    def test_requirement_with_assertions(self, tmp_path: Path):
        """Test requirement with assertions is serialized with assertion data."""
        req = Requirement(
            id="REQ-d00002",
            title="Assertion Test",
            level="DEV",
            status="Active",
            body="Main body text.",
            assertions=[
                Assertion(label="A", text="The system SHALL do X."),
                Assertion(label="B", text="The system SHALL do Y."),
                Assertion(label="C", text="Removed", is_placeholder=True),
            ],
            file_path=tmp_path / "test.md",
            line_number=1,
        )

        result = format_requirements_json({"REQ-d00002": req}, [])
        data = json.loads(result)

        assert "assertions" in data["REQ-d00002"]
        assertions = data["REQ-d00002"]["assertions"]
        assert len(assertions) == 3
        assert assertions[0] == {"label": "A", "text": "The system SHALL do X.", "isPlaceholder": False}
        assert assertions[2]["isPlaceholder"] is True

    def test_conflict_detection(self, tmp_path: Path):
        """Test that duplicate/conflict violations are reflected in JSON."""
        req = Requirement(
            id="REQ-p00001",
            title="Conflicting",
            level="PRD",
            status="Active",
            body="Body",
            file_path=tmp_path / "test.md",
            line_number=1,
        )

        violations = [
            RuleViolation(
                rule_name="id.duplicate",
                requirement_id="REQ-p00001",
                message="Duplicate ID found",
                severity=Severity.ERROR,
                location="test.md:1",
            )
        ]

        result = format_requirements_json({"REQ-p00001": req}, violations)
        data = json.loads(result)

        assert data["REQ-p00001"]["isConflict"] is True
        assert data["REQ-p00001"]["conflictWith"] == "Duplicate ID found"

    def test_cycle_detection(self, tmp_path: Path):
        """Test that cycle violations are reflected in JSON."""
        req = Requirement(
            id="REQ-d00001",
            title="Cyclic",
            level="DEV",
            status="Active",
            body="Body",
            implements=["d00002"],
            file_path=tmp_path / "test.md",
            line_number=1,
        )

        violations = [
            RuleViolation(
                rule_name="hierarchy.cycle",
                requirement_id="REQ-d00001",
                message="Cycle: d00001 -> d00002 -> d00001",
                severity=Severity.ERROR,
                location="test.md:1",
            )
        ]

        result = format_requirements_json({"REQ-d00001": req}, violations)
        data = json.loads(result)

        assert data["REQ-d00001"]["isCycle"] is True
        assert data["REQ-d00001"]["cyclePath"] == "Cycle: d00001 -> d00002 -> d00001"

    def test_multiple_requirements(self, tmp_path: Path):
        """Test multiple requirements are all included."""
        reqs = {
            "REQ-p00001": Requirement(
                id="REQ-p00001", title="PRD 1", level="PRD", status="Active",
                body="Body 1", file_path=tmp_path / "prd.md", line_number=1,
            ),
            "REQ-d00001": Requirement(
                id="REQ-d00001", title="DEV 1", level="DEV", status="Active",
                body="Body 2", implements=["p00001"],
                file_path=tmp_path / "dev.md", line_number=1,
            ),
        }

        result = format_requirements_json(reqs, [])
        data = json.loads(result)

        assert len(data) == 2
        assert "REQ-p00001" in data
        assert "REQ-d00001" in data

    def test_empty_optional_fields(self, tmp_path: Path):
        """Test that optional fields default correctly."""
        req = Requirement(
            id="REQ-p00001",
            title="Minimal",
            level="PRD",
            status="Draft",
            body="",
            file_path=tmp_path / "test.md",
            line_number=1,
        )

        result = format_requirements_json({"REQ-p00001": req}, [])
        data = json.loads(result)

        assert data["REQ-p00001"]["body"] == ""
        assert data["REQ-p00001"]["rationale"] == ""
        assert data["REQ-p00001"]["implements"] == []
        assert data["REQ-p00001"]["hash"] == ""
        assert "assertions" not in data["REQ-p00001"]  # Only included when present

    def test_subdir_field_default(self, tmp_path: Path):
        """Test that subdir defaults to empty string for root spec dir."""
        req = Requirement(
            id="REQ-p00001",
            title="Core Requirement",
            level="PRD",
            status="Active",
            body="Body text.",
            file_path=tmp_path / "spec" / "prd-core.md",
            line_number=1,
        )

        result = format_requirements_json({"REQ-p00001": req}, [])
        data = json.loads(result)

        assert data["REQ-p00001"]["subdir"] == ""

    def test_subdir_field_roadmap(self, tmp_path: Path):
        """Test that subdir is set correctly for roadmap requirements."""
        req = Requirement(
            id="REQ-p00002",
            title="Roadmap Feature",
            level="PRD",
            status="Draft",
            body="Future feature.",
            subdir="roadmap",
            file_path=tmp_path / "spec" / "roadmap" / "prd-roadmap.md",
            line_number=1,
        )

        result = format_requirements_json({"REQ-p00002": req}, [])
        data = json.loads(result)

        assert data["REQ-p00002"]["subdir"] == "roadmap"

    def test_subdir_field_custom(self, tmp_path: Path):
        """Test that subdir works with any subdirectory name."""
        req = Requirement(
            id="REQ-p00003",
            title="Archived Feature",
            level="PRD",
            status="Deprecated",
            body="Old feature.",
            subdir="archive",
            file_path=tmp_path / "spec" / "archive" / "prd-old.md",
            line_number=1,
        )

        result = format_requirements_json({"REQ-p00003": req}, [])
        data = json.loads(result)

        assert data["REQ-p00003"]["subdir"] == "archive"
