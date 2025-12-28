"""
Tests for elspais.core.models module.
"""

import pytest
from pathlib import Path


class TestRequirement:
    """Tests for Requirement dataclass."""

    def test_requirement_creation(self):
        """Test creating a Requirement with all fields."""
        from elspais.core.models import Requirement

        req = Requirement(
            id="REQ-p00001",
            title="User Authentication",
            level="PRD",
            status="Active",
            body="The system SHALL authenticate users.",
            implements=["p00002"],
            acceptance_criteria=["Criterion 1", "Criterion 2"],
            rationale="Security requirement",
            hash="a1b2c3d4",
            file_path=Path("spec/prd-core.md"),
            line_number=10,
        )

        assert req.id == "REQ-p00001"
        assert req.title == "User Authentication"
        assert req.level == "PRD"
        assert req.status == "Active"
        assert len(req.implements) == 1
        assert len(req.acceptance_criteria) == 2
        assert req.hash == "a1b2c3d4"

    def test_requirement_minimal(self):
        """Test creating a Requirement with minimal fields."""
        from elspais.core.models import Requirement

        req = Requirement(
            id="REQ-d00001",
            title="Simple Req",
            level="DEV",
            status="Active",
            body="Body text",
        )

        assert req.id == "REQ-d00001"
        assert req.implements == []
        assert req.acceptance_criteria == []
        assert req.rationale is None
        assert req.hash is None

    def test_requirement_type_property(self):
        """Test extracting type from requirement ID."""
        from elspais.core.models import Requirement

        prd = Requirement(id="REQ-p00001", title="PRD", level="PRD", status="Active", body="")
        ops = Requirement(id="REQ-o00001", title="OPS", level="OPS", status="Active", body="")
        dev = Requirement(id="REQ-d00001", title="DEV", level="DEV", status="Active", body="")

        assert prd.type_code == "p"
        assert ops.type_code == "o"
        assert dev.type_code == "d"

    def test_requirement_number_property(self):
        """Test extracting number from requirement ID."""
        from elspais.core.models import Requirement

        req = Requirement(id="REQ-p00042", title="Test", level="PRD", status="Active", body="")
        assert req.number == 42


class TestParsedRequirement:
    """Tests for ParsedRequirement dataclass."""

    def test_parsed_requirement_creation(self):
        """Test creating a ParsedRequirement."""
        from elspais.core.models import ParsedRequirement

        parsed = ParsedRequirement(
            full_id="REQ-CAL-p00001",
            prefix="REQ",
            sponsor="CAL",
            type_code="p",
            number="00001",
        )

        assert parsed.full_id == "REQ-CAL-p00001"
        assert parsed.sponsor == "CAL"
        assert parsed.type_code == "p"
        assert parsed.number == "00001"

    def test_parsed_requirement_no_sponsor(self):
        """Test ParsedRequirement without sponsor."""
        from elspais.core.models import ParsedRequirement

        parsed = ParsedRequirement(
            full_id="REQ-p00001",
            prefix="REQ",
            sponsor=None,
            type_code="p",
            number="00001",
        )

        assert parsed.sponsor is None
        assert parsed.full_id == "REQ-p00001"


class TestRequirementType:
    """Tests for RequirementType dataclass."""

    def test_requirement_type_creation(self):
        """Test creating RequirementType."""
        from elspais.core.models import RequirementType

        prd = RequirementType(id="p", name="Product Requirement", level=1)
        dev = RequirementType(id="d", name="Development Requirement", level=3)

        assert prd.id == "p"
        assert prd.level == 1
        assert dev.level == 3

    def test_requirement_type_comparison(self):
        """Test RequirementType level comparison."""
        from elspais.core.models import RequirementType

        prd = RequirementType(id="p", name="PRD", level=1)
        ops = RequirementType(id="o", name="OPS", level=2)
        dev = RequirementType(id="d", name="DEV", level=3)

        # Higher level number = lower in hierarchy (children)
        assert prd.level < ops.level < dev.level
