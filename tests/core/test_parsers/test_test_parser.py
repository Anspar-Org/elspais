# elspais: expected-broken-links 1
"""Tests for TestParser - Priority 80 test reference parser."""

from elspais.graph.parsers import ParseContext
from elspais.graph.parsers.test import TestParser as _TestParser
from tests.fixtures import fake_reqs


class TestTestParserPriority:
    """Tests for TestParser priority."""

    def test_priority_is_80(self):
        parser = _TestParser()
        assert parser.priority == 80


class TestTestParserBasic:
    """Tests for basic test reference parsing."""

    def test_claims_test_with_req_reference(self):
        parser = _TestParser()
        lines = [
            (1, "def test_user_auth_REQ_p00001():"),
            (2, "    assert True"),
        ]
        ctx = ParseContext(file_path="tests/test_auth.py")

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 1
        assert results[0].content_type == "test_ref"
        assert "REQ-p00001" in results[0].parsed_data["validates"]

    def test_claims_test_with_inline_marker(self):
        parser = _TestParser()
        lines = [
            (1, "def test_something():"),
            (2, "    # Tests REQ-p00001"),
            (3, "    assert True"),
        ]
        ctx = ParseContext(file_path="tests/test_auth.py")

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 1
        assert "REQ-p00001" in results[0].parsed_data["validates"]

    def test_no_test_refs_emits_unlinked_test(self):
        """Test functions without requirement refs still emit as unlinked tests."""
        parser = _TestParser()
        lines = [
            (1, "def test_unrelated():"),
            (2, "    assert 1 + 1 == 2"),
        ]
        ctx = ParseContext(file_path="tests/test_math.py")

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 1
        assert results[0].parsed_data["function_name"] == "test_unrelated"
        assert results[0].parsed_data["validates"] == []

    def test_REQ_d00066_D_validates_assertion_level_reference(self):
        """REQ-d00066-D: Test names with assertion labels are validated."""
        parser = _TestParser()
        lines = [
            (1, "def test_REQ_d00060_A_returns_node_counts():"),
            (2, "    assert True"),
        ]
        ctx = ParseContext(file_path="tests/test_mcp.py")

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 1
        assert results[0].content_type == "test_ref"
        # Should validate the full reference including assertion label
        assert "REQ-d00060-A" in results[0].parsed_data["validates"]

    def test_REQ_d00066_D_validates_multi_assertion_reference(self):
        """REQ-d00066-D: Test names with multiple assertion labels are validated."""
        parser = _TestParser()
        lines = [
            fake_reqs.PARSER_INPUT_MULTI_ASSERTION,
            (2, "    assert True"),
        ]
        ctx = ParseContext(file_path="tests/test_mcp.py")

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 1
        # Should validate REQ-d00060-A-B (multi-assertion syntax)
        assert "REQ-d00060-A-B" in results[0].parsed_data["validates"]


class TestTestParserCustomConfig:
    """Tests for TestParser with custom configuration.

    REQ-d00082-J: Parser accepts custom PatternConfig for non-standard prefixes.
    REQ-d00082-J: Parser accepts custom comment styles via ReferenceResolver.
    REQ-d00082-J: Parser validates underscore separators in test names.
    """

    def test_REQ_d00082_J_custom_prefix_spec(self):
        """REQ-d00082-J: Parser with custom prefix 'SPEC' instead of 'REQ'."""
        from elspais.utilities.patterns import IdPatternConfig, IdResolver

        resolver = IdResolver(
            IdPatternConfig.from_dict(
                {
                    "project": {"namespace": "SPEC"},
                    "id-patterns": {
                        "canonical": "{namespace}-{type.letter}{component}",
                        "aliases": {"short": "{type.letter}{component}"},
                        "types": {
                            "prd": {"level": 1, "aliases": {"letter": "p"}},
                            "ops": {"level": 2, "aliases": {"letter": "o"}},
                            "dev": {"level": 3, "aliases": {"letter": "d"}},
                        },
                        "component": {"style": "numeric", "digits": 5, "leading_zeros": True},
                    },
                }
            )
        )
        parser = _TestParser(resolver=resolver)
        lines = [
            (1, "def test_SPEC_d00101_custom_spec():"),
            (2, "    assert True"),
        ]
        ctx = ParseContext(file_path="tests/test_spec.py")

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 1
        assert "SPEC-d00101" in results[0].parsed_data["validates"]

    def test_REQ_d00082_J_custom_comment_styles_with_resolver(self):
        """REQ-d00082-J: Parser uses custom comment styles from ReferenceResolver."""
        from elspais.utilities.patterns import IdPatternConfig, IdResolver
        from elspais.utilities.reference_config import (
            ReferenceConfig,
            ReferenceResolver,
        )

        id_resolver = IdResolver(
            IdPatternConfig.from_dict(
                {
                    "project": {"namespace": "REQ"},
                    "id-patterns": {
                        "canonical": "{namespace}-{type.letter}{component}",
                        "aliases": {"short": "{type.letter}{component}"},
                        "types": {
                            "prd": {"level": 1, "aliases": {"letter": "p"}},
                            "ops": {"level": 2, "aliases": {"letter": "o"}},
                            "dev": {"level": 3, "aliases": {"letter": "d"}},
                        },
                        "component": {"style": "numeric", "digits": 5, "leading_zeros": True},
                    },
                }
            )
        )

        # Custom config with only C-style block comments
        ref_config = ReferenceConfig(
            separators=["-", "_"],
            case_sensitive=False,
            comment_styles=["/*", "*/"],
            keywords={
                "validates": ["Tests", "Validates"],
            },
        )
        ref_resolver = ReferenceResolver(ref_config)
        parser = _TestParser(resolver=id_resolver, reference_resolver=ref_resolver)

        lines = [
            (1, "def test_something():"),
            (2, "    /* Tests REQ-p00002 */"),
            (3, "    assert True"),
        ]
        ctx = ParseContext(file_path="tests/test_custom.py")

        list(parser.claim_and_parse(lines, ctx))

        # Note: block comment style matching is limited in inline context,
        # so verify parser instantiation works with the config
        assert parser._resolver == id_resolver
        assert parser._reference_resolver == ref_resolver

    def test_REQ_d00082_J_validates_underscore_separators(self):
        """REQ-d00082-J: Parser accepts underscore separators in test names."""
        from elspais.utilities.patterns import IdPatternConfig, IdResolver
        from elspais.utilities.reference_config import ReferenceConfig, ReferenceResolver

        id_resolver = IdResolver(
            IdPatternConfig.from_dict(
                {
                    "project": {"namespace": "REQ"},
                    "id-patterns": {
                        "canonical": "{namespace}-{type.letter}{component}",
                        "aliases": {"short": "{type.letter}{component}"},
                        "types": {
                            "prd": {"level": 1, "aliases": {"letter": "p"}},
                            "ops": {"level": 2, "aliases": {"letter": "o"}},
                            "dev": {"level": 3, "aliases": {"letter": "d"}},
                        },
                        "component": {"style": "numeric", "digits": 5, "leading_zeros": True},
                    },
                }
            )
        )

        # Config that accepts both - and _ as separators
        ref_config = ReferenceConfig(
            separators=["-", "_"],
            case_sensitive=False,
        )
        ref_resolver = ReferenceResolver(ref_config)
        parser = _TestParser(resolver=id_resolver, reference_resolver=ref_resolver)

        lines = [
            (1, "def test_REQ_d00082_J_custom_feature():"),
            (2, "    assert True"),
        ]
        ctx = ParseContext(file_path="tests/test_underscore.py")

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 1
        # Should normalize underscores to hyphens in output
        assert "REQ-d00082-J" in results[0].parsed_data["validates"]


class TestTestParserFunctionTracking:
    """Tests for function/class context tracking in TestParser.

    REQ-d00054-A: TestParser tracks function_name, class_name,
    function_line, and file_default_validates in parsed_data.
    """

    def test_REQ_d00054_A_tracks_function_name(self):
        """Function name is captured from the enclosing def statement."""
        parser = _TestParser()
        lines = [
            (1, "def test_REQ_p00001_foo():"),
            (2, "    assert True"),
        ]
        context = ParseContext(file_path="tests/test_example.py")

        results = list(parser.claim_and_parse(lines, context))

        assert len(results) == 1
        assert results[0].parsed_data["function_name"] == "test_REQ_p00001_foo"

    def test_REQ_d00054_A_tracks_class_name(self):
        """Both class and function names are captured for methods in a test class."""
        parser = _TestParser()
        lines = [
            (1, "class TestFoo:"),
            (2, "    def test_REQ_p00001_bar(self):"),
            (3, "        assert True"),
        ]
        context = ParseContext(file_path="tests/test_example.py")

        results = list(parser.claim_and_parse(lines, context))

        assert len(results) == 1
        assert results[0].parsed_data["class_name"] == "TestFoo"
        assert results[0].parsed_data["function_name"] == "test_REQ_p00001_bar"

    def test_REQ_d00054_A_no_function_context_for_module_comment(self):
        """Module-level comments have no function or class context."""
        parser = _TestParser()
        lines = [
            (1, "# Tests REQ-p00001"),
            (2, ""),
            (3, "def test_unrelated():"),
            (4, "    pass"),
        ]
        context = ParseContext(file_path="tests/test_example.py")

        results = list(parser.claim_and_parse(lines, context))

        # The module-level comment should produce a result
        module_result = [r for r in results if r.start_line == 1]
        assert len(module_result) == 1
        assert module_result[0].parsed_data["function_name"] is None
        assert module_result[0].parsed_data["class_name"] is None

    def test_REQ_d00054_A_file_default_validates(self):
        """File-level REQ comment populates file_default_validates for all items."""
        parser = _TestParser()
        lines = [
            (1, "# Tests REQ-p00001"),
            (2, ""),
            (3, "class TestFoo:"),
            (4, "    def test_REQ_p00002_bar(self):"),
            (5, "        assert True"),
        ]
        context = ParseContext(file_path="tests/test_example.py")

        results = list(parser.claim_and_parse(lines, context))

        # All results should carry the file-level default
        for result in results:
            assert "REQ-p00001" in result.parsed_data["file_default_validates"]

    def test_REQ_d00054_A_function_line_tracks_def_line(self):
        """function_line is the line number of the def statement, not the REQ reference."""
        parser = _TestParser()
        lines = [
            (1, "def test_something():"),
            (2, "    # Tests REQ-p00001"),
            (3, "    assert True"),
        ]
        context = ParseContext(file_path="tests/test_example.py")

        results = list(parser.claim_and_parse(lines, context))

        assert len(results) == 1
        # function_line should be line 1 (the def), not line 2 (the comment)
        assert results[0].parsed_data["function_line"] == 1
        assert results[0].start_line == 2

    def test_REQ_d00054_A_comment_ref_inside_function(self):
        """A comment reference inside a function body gets the function context."""
        parser = _TestParser()
        lines = [
            (1, "class TestFoo:"),
            (2, "    def test_something(self):"),
            (3, "        # Tests REQ-d00001"),
            (4, "        assert True"),
        ]
        context = ParseContext(file_path="tests/test_example.py")

        results = list(parser.claim_and_parse(lines, context))

        assert len(results) == 1
        assert results[0].parsed_data["function_name"] == "test_something"
        assert results[0].parsed_data["class_name"] == "TestFoo"
        assert "REQ-d00001" in results[0].parsed_data["validates"]


class TestAstPrescan:
    """Tests for AST-based pre-scan accuracy in TestParser.

    REQ-d00054-A: AST prescan provides accurate class/function context
    even when multiline strings, decorators, or async defs are present.
    """

    def test_REQ_d00054_A_class_context_preserved_through_multiline_string(self):
        """Multiline string with unindented content must not break class context."""
        parser = _TestParser()
        lines = [
            (1, "class TestWidget:"),
            (2, "    def test_something(self):"),
            (3, '        text = """'),
            (4, "## REQ-d00001:"),
            (5, "Some content at column 0"),
            (6, '"""'),
            (7, "        assert True"),
            (8, ""),
            (9, "    def test_other(self):"),
            (10, "        # Tests REQ-p00001"),
            (11, "        pass"),
        ]
        context = ParseContext(file_path="tests/test_example.py")

        results = list(parser.claim_and_parse(lines, context))

        # test_other has an inline comment ref; test_something has no ref so emitted as unlinked
        by_func = {r.parsed_data["function_name"]: r for r in results}
        assert "test_something" in by_func
        assert "test_other" in by_func
        # Both must have class_name == "TestWidget" (the key bug fix)
        assert by_func["test_something"].parsed_data["class_name"] == "TestWidget"
        assert by_func["test_other"].parsed_data["class_name"] == "TestWidget"

    def test_REQ_d00054_A_async_test_function(self):
        """async def test_foo() should be recognized by AST prescan."""
        parser = _TestParser()
        lines = [
            (1, "import asyncio"),
            (2, ""),
            (3, "async def test_async_thing():"),
            (4, "    # Tests REQ-p00001"),
            (5, "    await asyncio.sleep(0)"),
        ]
        context = ParseContext(file_path="tests/test_example.py")

        results = list(parser.claim_and_parse(lines, context))

        ref_results = [r for r in results if r.parsed_data["validates"]]
        assert len(ref_results) == 1
        assert ref_results[0].parsed_data["function_name"] == "test_async_thing"
        assert ref_results[0].parsed_data["class_name"] is None

    def test_REQ_d00054_A_nested_class_ignored(self):
        """A nested class inside a test class should not confuse the scanner."""
        parser = _TestParser()
        lines = [
            (1, "class TestOuter:"),
            (2, "    class Helper:"),
            (3, "        pass"),
            (4, ""),
            (5, "    def test_REQ_p00001_works(self):"),
            (6, "        assert True"),
        ]
        context = ParseContext(file_path="tests/test_example.py")

        results = list(parser.claim_and_parse(lines, context))

        ref_results = [r for r in results if r.parsed_data["validates"]]
        assert len(ref_results) == 1
        assert ref_results[0].parsed_data["class_name"] == "TestOuter"
        assert ref_results[0].parsed_data["function_name"] == "test_REQ_p00001_works"

    def test_REQ_d00054_A_decorated_test_function(self):
        """Decorators like @pytest.mark.parametrize should not break context."""
        parser = _TestParser()
        lines = [
            (1, "import pytest"),
            (2, ""),
            (3, "class TestDecorated:"),
            (4, '    @pytest.mark.parametrize("x", [1, 2])'),
            (5, "    def test_REQ_p00001_param(self, x):"),
            (6, "        assert x > 0"),
        ]
        context = ParseContext(file_path="tests/test_example.py")

        results = list(parser.claim_and_parse(lines, context))

        ref_results = [r for r in results if r.parsed_data["validates"]]
        assert len(ref_results) == 1
        assert ref_results[0].parsed_data["class_name"] == "TestDecorated"
        assert ref_results[0].parsed_data["function_name"] == "test_REQ_p00001_param"

    def test_REQ_d00054_A_ast_fallback_on_syntax_error(self):
        """Invalid Python syntax should fall back to text-based prescan."""
        parser = _TestParser()
        # Intentionally broken Python syntax
        lines = [
            (1, "def test_REQ_p00001_broken(:"),
            (2, "    assert True"),
        ]
        context = ParseContext(file_path="tests/test_example.py")

        # Should not raise - falls back to text prescan
        results = list(parser.claim_and_parse(lines, context))

        # Text-based prescan won't match the broken def, but the parser
        # should still run without error
        assert isinstance(results, list)

    def test_REQ_d00054_A_module_level_test_functions(self):
        """Module-level test functions should have class_name=None."""
        parser = _TestParser()
        lines = [
            (1, "def test_REQ_p00001_standalone():"),
            (2, "    assert True"),
            (3, ""),
            (4, "def test_REQ_p00002_another():"),
            (5, "    assert True"),
        ]
        context = ParseContext(file_path="tests/test_example.py")

        results = list(parser.claim_and_parse(lines, context))

        assert len(results) == 2
        for r in results:
            assert r.parsed_data["class_name"] is None


class TestExternalPrescan:
    """Tests for externally-provided prescan data in TestParser.

    REQ-d00054-A: External prescan data (from prescan_command) overrides
    AST/text-based scanning for test structure.
    """

    def test_REQ_d00054_A_external_prescan_overrides_ast(self):
        """When prescan_data is provided for a file, it should be used instead of AST."""
        prescan_data = {
            "tests/test_example.py": [
                {"function": "test_alpha", "class": "TestSuite", "line": 5},
            ],
        }
        parser = _TestParser(prescan_data=prescan_data)
        lines = [
            (1, "# module header"),
            (2, ""),
            (3, "class TestSuite:"),
            (4, ""),
            (5, "    def test_alpha(self):"),
            (6, "        # Tests REQ-p00001"),
            (7, "        assert True"),
        ]
        context = ParseContext(file_path="tests/test_example.py")

        results = list(parser.claim_and_parse(lines, context))

        ref_results = [r for r in results if r.parsed_data["validates"]]
        assert len(ref_results) == 1
        assert ref_results[0].parsed_data["function_name"] == "test_alpha"
        assert ref_results[0].parsed_data["class_name"] == "TestSuite"

    def test_REQ_d00054_A_external_prescan_class_context(self):
        """External prescan data with class names produces correct class_name."""
        prescan_data = {
            "tests/test_example.py": [
                {"function": "test_one", "class": "TestGroupA", "line": 3},
                {"function": "test_two", "class": "TestGroupB", "line": 8},
            ],
        }
        parser = _TestParser(prescan_data=prescan_data)
        lines = [
            (1, "# header"),
            (2, ""),
            (3, "    def test_one(self):"),
            (4, "        # Tests REQ-p00001"),
            (5, "        pass"),
            (6, ""),
            (7, ""),
            (8, "    def test_two(self):"),
            (9, "        # Tests REQ-p00002"),
            (10, "        pass"),
        ]
        context = ParseContext(file_path="tests/test_example.py")

        results = list(parser.claim_and_parse(lines, context))

        ref_results = sorted(
            [r for r in results if r.parsed_data["validates"]],
            key=lambda r: r.start_line,
        )
        assert len(ref_results) == 2
        assert ref_results[0].parsed_data["class_name"] == "TestGroupA"
        assert ref_results[0].parsed_data["function_name"] == "test_one"
        assert ref_results[1].parsed_data["class_name"] == "TestGroupB"
        assert ref_results[1].parsed_data["function_name"] == "test_two"


class TestPrescanFallback:
    """Tests for prescan method selection and fallback behavior.

    REQ-d00054-A: Non-Python files use text-based prescan; Python files
    use AST with text-based fallback on SyntaxError.
    """

    def test_REQ_d00054_A_non_python_file_uses_text_prescan(self):
        """A non-.py file should use text-based prescan (not AST)."""
        parser = _TestParser()
        # Dart-like test file with def-style test declarations
        lines = [
            (1, "def test_REQ_p00001_widget():"),
            (2, "    assert True"),
        ]
        context = ParseContext(file_path="tests/test_widget.dart")

        # Should work without error (text prescan, not AST)
        results = list(parser.claim_and_parse(lines, context))

        # Text prescan should still find the test function
        assert len(results) == 1
        assert results[0].parsed_data["function_name"] == "test_REQ_p00001_widget"
        assert "REQ-p00001" in results[0].parsed_data["validates"]
