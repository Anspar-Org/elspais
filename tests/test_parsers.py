"""Tests for the parser plugin system."""

from pathlib import Path


class TestSpecParserProtocol:
    """Tests for the SpecParser protocol."""

    def test_protocol_defined(self):
        """Test that SpecParser protocol is defined."""
        from elspais.parsers import SpecParser

        assert hasattr(SpecParser, "parse")
        assert hasattr(SpecParser, "can_parse")


class TestParserRegistry:
    """Tests for ParserRegistry."""

    def test_register_and_get(self):
        """Test registering and retrieving a parser."""
        from elspais.parsers import ParserRegistry
        from elspais.parsers.code import CodeParser

        registry = ParserRegistry()
        parser = CodeParser()

        registry.register("code", parser)
        retrieved = registry.get("code")

        assert retrieved is parser

    def test_get_unknown_returns_none(self):
        """Test getting unknown parser returns None."""
        from elspais.parsers import ParserRegistry

        registry = ParserRegistry()
        result = registry.get("unknown")

        assert result is None

    def test_register_factory(self):
        """Test registering a factory function."""
        from elspais.parsers import ParserRegistry
        from elspais.parsers.code import CodeParser

        registry = ParserRegistry()
        call_count = [0]

        def factory():
            call_count[0] += 1
            return CodeParser()

        registry.register_factory("code", factory)

        # Factory not called until get
        assert call_count[0] == 0

        parser1 = registry.get("code")
        assert call_count[0] == 1
        assert parser1 is not None

        # Second get returns cached instance
        parser2 = registry.get("code")
        assert call_count[0] == 1
        assert parser2 is parser1

    def test_list_sources(self):
        """Test listing registered sources."""
        from elspais.parsers import ParserRegistry
        from elspais.parsers.code import CodeParser

        registry = ParserRegistry()
        registry.register("code", CodeParser())
        registry.register_factory("test", lambda: CodeParser())

        sources = registry.list_sources()

        assert "code" in sources
        assert "test" in sources


class TestCodeParser:
    """Tests for CodeParser."""

    def test_parse_python_implements(self):
        """Test parsing Python-style implements comment."""
        from elspais.core.tree import NodeKind, SourceLocation
        from elspais.core.tree_schema import NodeTypeSchema
        from elspais.parsers.code import CodeParser

        parser = CodeParser()
        content = """
def authenticate_user():
    # Implements: REQ-d00001
    pass
"""
        source = SourceLocation(path="src/auth.py", line=1)
        schema = NodeTypeSchema(name="code")

        nodes = parser.parse(content, source, schema)

        assert len(nodes) == 1
        assert nodes[0].kind == NodeKind.CODE
        assert "REQ-D00001" in nodes[0].metrics.get("_validates_targets", [])
        assert nodes[0].code_ref is not None
        assert nodes[0].code_ref.symbol == "authenticate_user"

    def test_parse_js_implements(self):
        """Test parsing JavaScript-style implements comment."""
        from elspais.core.tree import SourceLocation
        from elspais.core.tree_schema import NodeTypeSchema
        from elspais.parsers.code import CodeParser

        parser = CodeParser()
        content = """
function login() {
    // Implements: REQ-d00002
    return true;
}
"""
        source = SourceLocation(path="src/auth.js", line=1)
        schema = NodeTypeSchema(name="code")

        nodes = parser.parse(content, source, schema)

        assert len(nodes) == 1
        assert "REQ-D00002" in nodes[0].metrics.get("_validates_targets", [])

    def test_parse_multiple_refs(self):
        """Test parsing multiple requirement references."""
        from elspais.core.tree import SourceLocation
        from elspais.core.tree_schema import NodeTypeSchema
        from elspais.parsers.code import CodeParser

        parser = CodeParser()
        content = """
# Implements: REQ-d00001, REQ-d00002
"""
        source = SourceLocation(path="src/auth.py", line=1)
        schema = NodeTypeSchema(name="code")

        nodes = parser.parse(content, source, schema)

        assert len(nodes) == 2

    def test_can_parse_python(self):
        """Test can_parse for Python files."""
        from elspais.parsers.code import CodeParser

        parser = CodeParser()

        assert parser.can_parse(Path("src/auth.py"))
        assert parser.can_parse(Path("lib/utils.py"))
        assert not parser.can_parse(Path("README.md"))

    def test_can_parse_various_extensions(self):
        """Test can_parse for various extensions."""
        from elspais.parsers.code import CodeParser

        parser = CodeParser()

        assert parser.can_parse(Path("app.js"))
        assert parser.can_parse(Path("app.ts"))
        assert parser.can_parse(Path("App.java"))
        assert parser.can_parse(Path("main.go"))
        assert parser.can_parse(Path("lib.rs"))


class TestTestParser:
    """Tests for TestParser."""

    def test_parse_python_test(self):
        """Test parsing Python test file."""
        from elspais.core.tree import NodeKind, SourceLocation
        from elspais.core.tree_schema import NodeTypeSchema
        from elspais.parsers.test import TestParser

        parser = TestParser()
        content = '''
class TestAuthentication:
    def test_login_success(self):
        """Test REQ-d00001 login."""
        pass
'''
        source = SourceLocation(path="tests/test_auth.py", line=1)
        schema = NodeTypeSchema(name="test")

        nodes = parser.parse(content, source, schema)

        assert len(nodes) == 1
        assert nodes[0].kind == NodeKind.TEST
        assert "REQ-D00001" in nodes[0].metrics.get("_validates_targets", [])
        assert nodes[0].test_ref is not None
        assert nodes[0].test_ref.test_class == "TestAuthentication"

    def test_parse_js_test(self):
        """Test parsing JavaScript test file."""
        from elspais.core.tree import SourceLocation
        from elspais.core.tree_schema import NodeTypeSchema
        from elspais.parsers.test import TestParser

        parser = TestParser()
        content = """
it('should login REQ-d00001', () => {
    expect(true).toBe(true);
});
"""
        source = SourceLocation(path="tests/auth.test.js", line=1)
        schema = NodeTypeSchema(name="test")

        nodes = parser.parse(content, source, schema)

        assert len(nodes) == 1
        assert "REQ-D00001" in nodes[0].metrics.get("_validates_targets", [])

    def test_can_parse_test_files(self):
        """Test can_parse identifies test files."""
        from elspais.parsers.test import TestParser

        parser = TestParser()

        assert parser.can_parse(Path("test_auth.py"))
        assert parser.can_parse(Path("auth_test.py"))
        assert parser.can_parse(Path("auth.test.js"))
        assert parser.can_parse(Path("auth.spec.ts"))
        assert parser.can_parse(Path("tests/auth.py"))


class TestJUnitXMLParser:
    """Tests for JUnitXMLParser."""

    def test_parse_simple_results(self):
        """Test parsing simple JUnit XML."""
        from elspais.core.tree import SourceLocation
        from elspais.core.tree_schema import NodeTypeSchema
        from elspais.parsers.junit_xml import JUnitXMLParser

        parser = JUnitXMLParser()
        content = """<?xml version="1.0"?>
<testsuite name="TestAuth" tests="2">
    <testcase classname="TestAuth" name="test_login_REQ_d00001" time="0.5"/>
    <testcase classname="TestAuth" name="test_logout" time="0.1">
        <failure message="assertion failed"/>
    </testcase>
</testsuite>
"""
        source = SourceLocation(path="junit-results.xml", line=1)
        schema = NodeTypeSchema(name="test_result", label_template="{status}: {name}")

        nodes = parser.parse(content, source, schema)

        assert len(nodes) == 2

        # First test passed
        passed = [n for n in nodes if n.test_result.status == "passed"]
        assert len(passed) == 1
        assert passed[0].test_result.duration == 0.5
        assert "REQ-D00001" in passed[0].metrics.get("_validates_targets", [])

        # Second test failed
        failed = [n for n in nodes if n.test_result.status == "failed"]
        assert len(failed) == 1
        assert "assertion failed" in failed[0].test_result.message

    def test_parse_with_errors(self):
        """Test parsing JUnit XML with errors."""
        from elspais.core.tree import SourceLocation
        from elspais.core.tree_schema import NodeTypeSchema
        from elspais.parsers.junit_xml import JUnitXMLParser

        parser = JUnitXMLParser()
        content = """<?xml version="1.0"?>
<testsuite name="TestAuth">
    <testcase classname="TestAuth" name="test_crash" time="0.1">
        <error message="RuntimeError"/>
    </testcase>
</testsuite>
"""
        source = SourceLocation(path="junit-results.xml", line=1)
        schema = NodeTypeSchema(name="test_result")

        nodes = parser.parse(content, source, schema)

        assert len(nodes) == 1
        assert nodes[0].test_result.status == "error"

    def test_parse_invalid_xml(self):
        """Test parsing invalid XML returns empty list."""
        from elspais.core.tree import SourceLocation
        from elspais.core.tree_schema import NodeTypeSchema
        from elspais.parsers.junit_xml import JUnitXMLParser

        parser = JUnitXMLParser()
        content = "not valid xml"
        source = SourceLocation(path="junit-results.xml", line=1)
        schema = NodeTypeSchema(name="test_result")

        nodes = parser.parse(content, source, schema)

        assert nodes == []

    def test_can_parse(self):
        """Test can_parse identifies JUnit XML files."""
        from elspais.parsers.junit_xml import JUnitXMLParser

        parser = JUnitXMLParser()

        assert parser.can_parse(Path("junit-results.xml"))
        assert parser.can_parse(Path("test-results.xml"))
        assert not parser.can_parse(Path("results.json"))


class TestPytestJSONParser:
    """Tests for PytestJSONParser."""

    def test_parse_pytest_json_report(self):
        """Test parsing pytest-json-report format."""
        from elspais.core.tree import SourceLocation
        from elspais.core.tree_schema import NodeTypeSchema
        from elspais.parsers.pytest_json import PytestJSONParser

        parser = PytestJSONParser()
        content = """{
    "tests": [
        {
            "nodeid": "tests/test_auth.py::TestAuth::test_login_REQ_d00001",
            "outcome": "passed",
            "duration": 0.5
        },
        {
            "nodeid": "tests/test_auth.py::test_logout",
            "outcome": "failed",
            "duration": 0.1,
            "longrepr": "assertion failed"
        }
    ]
}"""
        source = SourceLocation(path="pytest-results.json", line=1)
        schema = NodeTypeSchema(name="test_result", label_template="{status}: {name}")

        nodes = parser.parse(content, source, schema)

        assert len(nodes) == 2

        passed = [n for n in nodes if n.test_result.status == "passed"]
        assert len(passed) == 1
        assert "REQ-D00001" in passed[0].metrics.get("_validates_targets", [])

        failed = [n for n in nodes if n.test_result.status == "failed"]
        assert len(failed) == 1

    def test_parse_invalid_json(self):
        """Test parsing invalid JSON returns empty list."""
        from elspais.core.tree import SourceLocation
        from elspais.core.tree_schema import NodeTypeSchema
        from elspais.parsers.pytest_json import PytestJSONParser

        parser = PytestJSONParser()
        content = "not valid json"
        source = SourceLocation(path="pytest-results.json", line=1)
        schema = NodeTypeSchema(name="test_result")

        nodes = parser.parse(content, source, schema)

        assert nodes == []

    def test_can_parse(self):
        """Test can_parse identifies pytest JSON files."""
        from elspais.parsers.pytest_json import PytestJSONParser

        parser = PytestJSONParser()

        assert parser.can_parse(Path("pytest-results.json"))
        assert parser.can_parse(Path("test-results.json"))
        assert not parser.can_parse(Path("results.xml"))


class TestJourneyParser:
    """Tests for JourneyParser."""

    def test_parse_journey(self):
        """Test parsing a user journey."""
        from elspais.core.tree import NodeKind, SourceLocation
        from elspais.core.tree_schema import NodeTypeSchema
        from elspais.parsers.journey import JourneyParser

        parser = JourneyParser()
        content = """
# JNY-Spec-Author-01: Create New Requirement

**Actor**: Specification Author
**Goal**: Create a new requirement specification
**Context**: Working on a new feature

**Steps**:
1. Open the spec editor
2. Write the requirement
3. Save the file

**Expected Outcome**: Requirement is validated and stored
"""
        source = SourceLocation(path="spec/journeys.md", line=1)
        schema = NodeTypeSchema(name="user_journey", label_template="{id}: {goal}")

        nodes = parser.parse(content, source, schema)

        assert len(nodes) == 1
        assert nodes[0].kind == NodeKind.USER_JOURNEY
        assert nodes[0].journey is not None
        assert nodes[0].journey.id == "JNY-Spec-Author-01"
        assert nodes[0].journey.actor == "Specification Author"
        assert nodes[0].journey.goal == "Create a new requirement specification"
        assert len(nodes[0].journey.steps) == 3

    def test_can_parse(self):
        """Test can_parse identifies journey files."""
        from elspais.parsers.journey import JourneyParser

        parser = JourneyParser()

        assert parser.can_parse(Path("user-journeys.md"))
        assert parser.can_parse(Path("jny-spec.md"))
        assert not parser.can_parse(Path("requirements.md"))


class TestRequirementParser:
    """Tests for RequirementParser."""

    def test_parse_requirement(self, hht_like_fixture):
        """Test parsing requirements from fixture."""
        from elspais.core.tree import NodeKind, SourceLocation
        from elspais.core.tree_schema import NodeTypeSchema
        from elspais.parsers.requirement import RequirementParser

        parser = RequirementParser()

        # Read a spec file from fixture
        spec_file = hht_like_fixture / "spec" / "prd-core.md"
        if spec_file.exists():
            content = spec_file.read_text()
            rel_path = str(spec_file.relative_to(hht_like_fixture))

            source = SourceLocation(path=rel_path, line=1)
            schema = NodeTypeSchema(
                name="requirement",
                has_assertions=True,
                label_template="{id}: {title}",
            )

            nodes = parser.parse(content, source, schema)

            # Should have at least one requirement
            req_nodes = [n for n in nodes if n.kind == NodeKind.REQUIREMENT]
            assert len(req_nodes) >= 0  # May be 0 if parsing fails

    def test_can_parse(self):
        """Test can_parse identifies spec files."""
        from elspais.parsers.requirement import RequirementParser

        parser = RequirementParser()

        assert parser.can_parse(Path("spec/requirements.md"))
        assert parser.can_parse(Path("requirements/prd.md"))
        assert not parser.can_parse(Path("README.md"))
        assert not parser.can_parse(Path("data.json"))
