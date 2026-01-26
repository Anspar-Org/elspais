"""Tests for elspais.parsers.journey module."""

import pytest
from pathlib import Path


class TestJourneyParser:
    """Tests for JourneyParser class."""

    @pytest.fixture
    def parser(self):
        """Create a JourneyParser instance."""
        from elspais.parsers.journey import JourneyParser

        return JourneyParser()

    @pytest.fixture
    def source(self):
        """Create a mock SourceLocation."""
        from elspais.core.graph import SourceLocation

        return SourceLocation(path="spec/journeys.md", line=1)

    @pytest.fixture
    def schema(self):
        """Create a mock NodeTypeSchema."""
        from elspais.core.graph_schema import NodeTypeSchema

        return NodeTypeSchema(
            name="journey",
            label_template="{id}: {goal}",
        )

    def test_parse_simple_journey(self, parser, source, schema):
        """Test parsing a simple user journey."""
        content = """# JNY-Login-01: User Login Flow

**Actor**: End User
**Goal**: Successfully log into the system
**Context**: User has valid credentials

**Steps**:
1. Navigate to login page
2. Enter credentials
3. Click login button

**Expected Outcome**: User is redirected to dashboard
"""
        nodes = parser.parse(content, source, schema)

        assert len(nodes) == 1
        node = nodes[0]
        assert node.id == "JNY-Login-01"
        assert node.journey.actor == "End User"
        assert node.journey.goal == "Successfully log into the system"
        assert node.journey.context == "User has valid credentials"
        assert len(node.journey.steps) == 3
        assert "Navigate to login page" in node.journey.steps[0]
        assert node.journey.expected_outcome == "User is redirected to dashboard"

    def test_parse_multiple_journeys(self, parser, source, schema):
        """Test parsing multiple journeys in one file."""
        content = """# JNY-Auth-01: Login

**Actor**: User
**Goal**: Login

# JNY-Auth-02: Logout

**Actor**: User
**Goal**: Logout
"""
        nodes = parser.parse(content, source, schema)

        assert len(nodes) == 2
        assert nodes[0].id == "JNY-Auth-01"
        assert nodes[1].id == "JNY-Auth-02"

    def test_parse_journey_with_dashes_in_id(self, parser, source, schema):
        """Test parsing journey with multi-part descriptor."""
        content = """## JNY-Spec-Author-Review-01: Author Reviews Spec

**Actor**: Spec Author
**Goal**: Review and approve specification
"""
        nodes = parser.parse(content, source, schema)

        assert len(nodes) == 1
        assert nodes[0].id == "JNY-Spec-Author-Review-01"
        assert nodes[0].journey.actor == "Spec Author"

    def test_parse_journey_minimal_fields(self, parser, source, schema):
        """Test parsing journey with only required fields."""
        content = """# JNY-Minimal-01: Minimal Journey

Just some content without structured fields.
"""
        nodes = parser.parse(content, source, schema)

        assert len(nodes) == 1
        node = nodes[0]
        assert node.id == "JNY-Minimal-01"
        assert node.journey.actor == "Unknown"  # Default
        assert node.journey.goal == "Minimal Journey"  # Falls back to title

    def test_parse_steps_with_bullets(self, parser, source, schema):
        """Test parsing steps with bullet points."""
        content = """# JNY-Bullets-01: Bullet Steps

**Actor**: User
**Goal**: Test bullets

**Steps**:
- First step
- Second step
- Third step
"""
        nodes = parser.parse(content, source, schema)

        assert len(nodes) == 1
        assert len(nodes[0].journey.steps) == 3
        assert "First step" in nodes[0].journey.steps[0]

    def test_parse_steps_with_asterisks(self, parser, source, schema):
        """Test parsing steps with asterisk bullets."""
        content = """# JNY-Asterisks-01: Asterisk Steps

**Actor**: User
**Goal**: Test asterisks

**Steps**:
* Step one
* Step two
"""
        nodes = parser.parse(content, source, schema)

        assert len(nodes) == 1
        assert len(nodes[0].journey.steps) == 2

    def test_parse_no_journeys(self, parser, source, schema):
        """Test parsing file with no journeys returns empty list."""
        content = """# Regular Requirement

This is not a journey.

## Another Section

More content.
"""
        nodes = parser.parse(content, source, schema)

        assert nodes == []

    def test_parse_line_numbers(self, parser, source, schema):
        """Test that line numbers are correctly calculated."""
        content = """# Some preamble

Some text here.

# JNY-LineTest-01: Journey at Line 5

**Actor**: Tester
"""
        nodes = parser.parse(content, source, schema)

        assert len(nodes) == 1
        assert nodes[0].source.line == 5

    def test_can_parse_journey_files(self, parser):
        """Test can_parse identifies journey files."""
        assert parser.can_parse(Path("user-journeys.md")) is True
        assert parser.can_parse(Path("jny-auth.md")) is True
        assert parser.can_parse(Path("journey.markdown")) is True

    def test_can_parse_rejects_non_journey(self, parser):
        """Test can_parse rejects non-journey files."""
        assert parser.can_parse(Path("requirements.md")) is False
        assert parser.can_parse(Path("readme.md")) is False
        assert parser.can_parse(Path("test.py")) is False
        assert parser.can_parse(Path("journey.txt")) is False

    def test_extract_field_patterns(self, parser):
        """Test field extraction with different patterns."""
        block = """
**Actor**: Developer
**Goal**: Build feature
**Context**: In development environment
**Expected Outcome**: Feature works
"""
        assert parser._extract_field(block, parser.ACTOR_PATTERN) == "Developer"
        assert parser._extract_field(block, parser.GOAL_PATTERN) == "Build feature"
        assert parser._extract_field(block, parser.CONTEXT_PATTERN) == "In development environment"
        assert parser._extract_field(block, parser.OUTCOME_PATTERN) == "Feature works"

    def test_extract_field_missing(self, parser):
        """Test field extraction returns None when not found."""
        block = "No fields here"
        assert parser._extract_field(block, parser.ACTOR_PATTERN) is None

    def test_format_label(self, parser):
        """Test label formatting."""
        from elspais.core.graph import UserJourney

        journey = UserJourney(
            id="JNY-Test-01",
            actor="Tester",
            goal="Test the system",
            context=None,
            steps=[],
            expected_outcome=None,
            file_path="test.md",
            line_number=1,
        )

        label = parser._format_label(journey, "{id}: {goal}")
        assert label == "JNY-Test-01: Test the system"

    def test_format_label_truncates_long_goal(self, parser):
        """Test that long goals are truncated in labels."""
        from elspais.core.graph import UserJourney

        long_goal = "x" * 100
        journey = UserJourney(
            id="JNY-Test-01",
            actor="Tester",
            goal=long_goal,
            context=None,
            steps=[],
            expected_outcome=None,
            file_path="test.md",
            line_number=1,
        )

        label = parser._format_label(journey, "{id}: {goal}")
        # Goal should be truncated to 50 chars
        assert len(label) < len(f"JNY-Test-01: {long_goal}")


class TestCreateParser:
    """Tests for create_parser factory function."""

    def test_create_parser(self):
        """Test that create_parser returns a JourneyParser."""
        from elspais.parsers.journey import JourneyParser, create_parser

        parser = create_parser()
        assert isinstance(parser, JourneyParser)
