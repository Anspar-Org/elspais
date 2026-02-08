"""Tests for CodeParser - Priority 70 code reference parser."""

from elspais.graph.parsers import ParseContext
from elspais.graph.parsers.code import CodeParser


class TestCodeParserPriority:
    """Tests for CodeParser priority."""

    def test_priority_is_70(self):
        parser = CodeParser()
        assert parser.priority == 70


class TestCodeParserBasic:
    """Tests for basic code reference parsing."""

    def test_claims_implements_comment(self):
        parser = CodeParser()
        lines = [
            (1, "def authenticate():"),
            (2, "    # Implements: REQ-p00001-A"),
            (3, "    pass"),
        ]
        ctx = ParseContext(file_path="src/auth.py")

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 1
        assert results[0].content_type == "code_ref"
        assert results[0].start_line == 2
        assert "REQ-p00001-A" in results[0].parsed_data["implements"]

    def test_claims_validates_comment(self):
        parser = CodeParser()
        lines = [
            (1, "def test_auth():"),
            (2, "    # Validates: REQ-p00001"),
            (3, "    assert True"),
        ]
        ctx = ParseContext(file_path="tests/test_auth.py")

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 1
        assert results[0].parsed_data["validates"] == ["REQ-p00001"]

    def test_no_code_refs_returns_empty(self):
        parser = CodeParser()
        lines = [
            (1, "def regular_function():"),
            (2, "    # Just a regular comment"),
            (3, "    pass"),
        ]
        ctx = ParseContext(file_path="src/utils.py")

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 0


class TestCodeParserCustomPatternConfig:
    """Tests for CodeParser with custom PatternConfig.

    REF: REQ-d00100-A - Custom prefix configuration
    """

    def test_REQ_d00100_A_custom_prefix_spec(self):
        """Test that parser uses custom prefix (SPEC instead of REQ)."""
        from elspais.utilities.patterns import PatternConfig

        # Create PatternConfig with "SPEC" prefix
        pattern_config = PatternConfig.from_dict(
            {
                "prefix": "SPEC",
                "types": {
                    "prd": {"id": "p", "name": "PRD"},
                    "ops": {"id": "o", "name": "OPS"},
                    "dev": {"id": "d", "name": "DEV"},
                },
                "id_format": {"style": "numeric", "digits": 5},
            }
        )

        parser = CodeParser(pattern_config=pattern_config)
        lines = [
            (1, "def authenticate():"),
            (2, "    # Implements: SPEC-p00001-A"),
            (3, "    pass"),
        ]
        ctx = ParseContext(file_path="src/auth.py")

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 1
        assert results[0].content_type == "code_ref"
        assert "SPEC-p00001-A" in results[0].parsed_data["implements"]

    def test_REQ_d00100_A_custom_prefix_ignores_default(self):
        """Test that parser with custom prefix ignores REQ-style IDs."""
        from elspais.utilities.patterns import PatternConfig

        pattern_config = PatternConfig.from_dict(
            {
                "prefix": "SPEC",
                "types": {"prd": {"id": "p", "name": "PRD"}},
                "id_format": {"style": "numeric", "digits": 5},
            }
        )

        parser = CodeParser(pattern_config=pattern_config)
        lines = [
            (1, "def authenticate():"),
            (2, "    # Implements: REQ-p00001-A"),  # Should NOT match
            (3, "    pass"),
        ]
        ctx = ParseContext(file_path="src/auth.py")

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 0


class TestCodeParserCustomReferenceResolver:
    """Tests for CodeParser with custom ReferenceResolver.

    REF: REQ-d00100-B - File-specific overrides via ReferenceResolver
    """

    def test_REQ_d00100_B_resolver_applies_file_override(self):
        """Test that ReferenceResolver applies file-specific overrides."""

        from elspais.utilities.reference_config import (
            ReferenceConfig,
            ReferenceOverride,
            ReferenceResolver,
        )

        # Create resolver with override for test files
        defaults = ReferenceConfig(
            comment_styles=["#", "//"],
            keywords={
                "implements": ["Implements"],
                "validates": ["Validates"],
            },
        )
        overrides = [
            ReferenceOverride(
                match="tests/**",
                keywords={"validates": ["TESTS", "Verifies"]},
            ),
        ]
        resolver = ReferenceResolver(defaults, overrides)

        parser = CodeParser(reference_resolver=resolver)
        lines = [
            (1, "def test_auth():"),
            (2, "    # TESTS: REQ-p00001"),
            (3, "    assert True"),
        ]
        ctx = ParseContext(
            file_path="tests/test_auth.py",
            config={"repo_root": "."},
        )

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 1
        assert results[0].parsed_data["validates"] == ["REQ-p00001"]

    def test_REQ_d00100_B_resolver_uses_defaults_for_non_matching(self):
        """Test that ReferenceResolver falls back to defaults for non-matching files."""
        from elspais.utilities.reference_config import (
            ReferenceConfig,
            ReferenceOverride,
            ReferenceResolver,
        )

        defaults = ReferenceConfig(
            comment_styles=["#"],
            keywords={
                "implements": ["Implements"],
                "validates": ["Validates"],
            },
        )
        overrides = [
            ReferenceOverride(
                match="tests/**",
                keywords={"validates": ["TESTS"]},  # Only for tests
            ),
        ]
        resolver = ReferenceResolver(defaults, overrides)

        parser = CodeParser(reference_resolver=resolver)
        lines = [
            (1, "def validate():"),
            (2, "    # Validates: REQ-p00002"),  # Standard keyword for src files
            (3, "    pass"),
        ]
        ctx = ParseContext(
            file_path="src/validator.py",
            config={"repo_root": "."},
        )

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 1
        assert results[0].parsed_data["validates"] == ["REQ-p00002"]


class TestCodeParserCustomKeywords:
    """Tests for CodeParser with custom keywords.

    REF: REQ-d00100-C - Alternate keywords support
    """

    def test_REQ_d00100_C_custom_validates_keyword(self):
        """Test that alternate keywords work (e.g., 'Verifies:' instead of 'Validates:')."""
        from elspais.utilities.reference_config import ReferenceConfig, ReferenceResolver

        ref_config = ReferenceConfig(
            keywords={
                "implements": ["Implements"],
                "validates": ["Verifies", "Checks"],
            },
        )
        resolver = ReferenceResolver(ref_config, [])

        parser = CodeParser(reference_resolver=resolver)
        lines = [
            (1, "def test_feature():"),
            (2, "    # Verifies: REQ-p00001"),
            (3, "    assert True"),
        ]
        ctx = ParseContext(
            file_path="tests/test_feature.py",
            config={"repo_root": "."},
        )

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 1
        assert results[0].parsed_data["validates"] == ["REQ-p00001"]

    def test_REQ_d00100_C_custom_implements_keyword(self):
        """Test alternate implements keywords (e.g., 'Satisfies:')."""
        from elspais.utilities.reference_config import ReferenceConfig, ReferenceResolver

        ref_config = ReferenceConfig(
            keywords={
                "implements": ["Satisfies", "Fulfills"],
                "validates": ["Validates"],
            },
        )
        resolver = ReferenceResolver(ref_config, [])

        parser = CodeParser(reference_resolver=resolver)
        lines = [
            (1, "def create_user():"),
            (2, "    # Satisfies: REQ-d00001"),
            (3, "    pass"),
        ]
        ctx = ParseContext(
            file_path="src/users.py",
            config={"repo_root": "."},
        )

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 1
        assert results[0].parsed_data["implements"] == ["REQ-d00001"]


class TestCodeParserMultilineBlockCustomStyles:
    """Tests for multi-line block parsing with custom comment styles.

    REF: REQ-d00100-D - Multi-line block with different comment markers
    """

    def test_REQ_d00100_D_block_with_slash_slash_comments(self):
        """Test block parsing with // comment style (JavaScript/TypeScript)."""
        from elspais.utilities.reference_config import ReferenceConfig, ReferenceResolver

        ref_config = ReferenceConfig(
            comment_styles=["//"],
            keywords={"implements": ["Implements", "IMPLEMENTS"]},
        )
        resolver = ReferenceResolver(ref_config, [])

        parser = CodeParser(reference_resolver=resolver)
        lines = [
            (1, "// IMPLEMENTS REQUIREMENTS:"),
            (2, "//   REQ-p00001"),
            (3, "//   REQ-p00002"),
            (4, "function authenticate() {"),
        ]
        ctx = ParseContext(
            file_path="src/auth.ts",
            config={"repo_root": "."},
        )

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 1
        assert results[0].content_type == "code_ref"
        assert "REQ-p00001" in results[0].parsed_data["implements"]
        assert "REQ-p00002" in results[0].parsed_data["implements"]
        assert results[0].start_line == 1
        assert results[0].end_line == 3

    def test_REQ_d00100_D_block_with_hash_comments(self):
        """Test block parsing with # comment style (Python/Ruby)."""
        from elspais.utilities.reference_config import ReferenceConfig, ReferenceResolver

        ref_config = ReferenceConfig(
            comment_styles=["#"],
            keywords={"implements": ["Implements", "IMPLEMENTS"]},
        )
        resolver = ReferenceResolver(ref_config, [])

        parser = CodeParser(reference_resolver=resolver)
        lines = [
            (10, "# IMPLEMENTS REQUIREMENTS:"),
            (11, "#   REQ-d00001"),
            (12, "#   REQ-d00002-A"),
            (13, "#"),  # Empty comment
            (14, "#   REQ-d00003"),
            (15, "def main():"),
        ]
        ctx = ParseContext(
            file_path="src/main.py",
            config={"repo_root": "."},
        )

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 1
        assert len(results[0].parsed_data["implements"]) == 3
        assert "REQ-d00001" in results[0].parsed_data["implements"]
        assert "REQ-d00002-A" in results[0].parsed_data["implements"]
        assert "REQ-d00003" in results[0].parsed_data["implements"]

    def test_REQ_d00100_D_block_with_double_dash_comments(self):
        """Test block parsing with -- comment style (SQL/Lua)."""
        from elspais.utilities.reference_config import ReferenceConfig, ReferenceResolver

        ref_config = ReferenceConfig(
            comment_styles=["--"],
            keywords={"implements": ["Implements", "IMPLEMENTS"]},
        )
        resolver = ReferenceResolver(ref_config, [])

        parser = CodeParser(reference_resolver=resolver)
        lines = [
            (1, "-- IMPLEMENTS REQUIREMENTS:"),
            (2, "--   REQ-o00001"),
            (3, "--   REQ-o00002"),
            (4, "SELECT * FROM users;"),
        ]
        ctx = ParseContext(
            file_path="queries/users.sql",
            config={"repo_root": "."},
        )

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 1
        assert "REQ-o00001" in results[0].parsed_data["implements"]
        assert "REQ-o00002" in results[0].parsed_data["implements"]


class TestCodeParserUnderscoreSeparators:
    """Tests for underscore separators in requirement IDs.

    REF: REQ-d00100-E - Underscore separator support
    """

    def test_REQ_d00100_E_underscore_separator_in_id(self):
        """Test that REQ_p00001 works when separators include '_'."""
        from elspais.utilities.reference_config import ReferenceConfig, ReferenceResolver

        ref_config = ReferenceConfig(
            separators=["-", "_"],
            keywords={
                "implements": ["Implements"],
                "validates": ["Validates"],
            },
        )
        resolver = ReferenceResolver(ref_config, [])

        parser = CodeParser(reference_resolver=resolver)
        lines = [
            (1, "def process():"),
            (2, "    # Implements: REQ_p00001"),
            (3, "    pass"),
        ]
        ctx = ParseContext(
            file_path="src/processor.py",
            config={"repo_root": "."},
        )

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 1
        assert "REQ_p00001" in results[0].parsed_data["implements"]

    def test_REQ_d00100_E_mixed_separators(self):
        """Test mixing hyphen and underscore separators in same comment."""
        from elspais.utilities.reference_config import ReferenceConfig, ReferenceResolver

        ref_config = ReferenceConfig(
            separators=["-", "_"],
            keywords={"implements": ["Implements"]},
        )
        resolver = ReferenceResolver(ref_config, [])

        parser = CodeParser(reference_resolver=resolver)
        lines = [
            (1, "def mixed():"),
            (2, "    # Implements: REQ-p00001, REQ_p00002"),
            (3, "    pass"),
        ]
        ctx = ParseContext(
            file_path="src/mixed.py",
            config={"repo_root": "."},
        )

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 1
        impl = results[0].parsed_data["implements"]
        assert "REQ-p00001" in impl
        assert "REQ_p00002" in impl

    def test_REQ_d00100_E_underscore_only_separator(self):
        """Test with only underscore as separator (no hyphen)."""
        from elspais.utilities.reference_config import ReferenceConfig, ReferenceResolver

        ref_config = ReferenceConfig(
            separators=["_"],
            keywords={"implements": ["Implements"]},
        )
        resolver = ReferenceResolver(ref_config, [])

        parser = CodeParser(reference_resolver=resolver)
        lines = [
            (1, "def underscore_only():"),
            (2, "    # Implements: REQ_d00001_A"),
            (3, "    pass"),
        ]
        ctx = ParseContext(
            file_path="src/underscored.py",
            config={"repo_root": "."},
        )

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 1
        assert "REQ_d00001_A" in results[0].parsed_data["implements"]


class TestCodeParserCaseSensitivity:
    """Tests for case-sensitive vs case-insensitive matching.

    REF: REQ-d00100-F - Case sensitivity configuration
    """

    def test_REQ_d00100_F_case_insensitive_default(self):
        """Test that default matching is case-insensitive."""
        from elspais.utilities.reference_config import ReferenceConfig, ReferenceResolver

        ref_config = ReferenceConfig(
            case_sensitive=False,  # Default
            keywords={"implements": ["Implements"]},
        )
        resolver = ReferenceResolver(ref_config, [])

        parser = CodeParser(reference_resolver=resolver)
        lines = [
            (1, "def case_test():"),
            (2, "    # implements: req-p00001"),  # Lowercase keyword and ID
            (3, "    pass"),
        ]
        ctx = ParseContext(
            file_path="src/case.py",
            config={"repo_root": "."},
        )

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 1
        assert "req-p00001" in results[0].parsed_data["implements"]

    def test_REQ_d00100_F_case_sensitive_matches_exact(self):
        """Test that case-sensitive mode matches exact case only."""
        from elspais.utilities.reference_config import ReferenceConfig, ReferenceResolver

        ref_config = ReferenceConfig(
            case_sensitive=True,
            keywords={"implements": ["Implements"]},
        )
        resolver = ReferenceResolver(ref_config, [])

        parser = CodeParser(reference_resolver=resolver)
        lines = [
            (1, "def case_exact():"),
            (2, "    # Implements: REQ-p00001"),  # Exact case
            (3, "    pass"),
        ]
        ctx = ParseContext(
            file_path="src/exact.py",
            config={"repo_root": "."},
        )

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 1
        assert "REQ-p00001" in results[0].parsed_data["implements"]

    def test_REQ_d00100_F_case_sensitive_rejects_wrong_case(self):
        """Test that case-sensitive mode rejects wrong case."""
        from elspais.utilities.reference_config import ReferenceConfig, ReferenceResolver

        ref_config = ReferenceConfig(
            case_sensitive=True,
            keywords={"implements": ["Implements"]},  # Capital I
        )
        resolver = ReferenceResolver(ref_config, [])

        parser = CodeParser(reference_resolver=resolver)
        lines = [
            (1, "def case_mismatch():"),
            (2, "    # implements: REQ-p00001"),  # Lowercase keyword
            (3, "    pass"),
        ]
        ctx = ParseContext(
            file_path="src/mismatch.py",
            config={"repo_root": "."},
        )

        results = list(parser.claim_and_parse(lines, ctx))

        # Should NOT match because keyword case doesn't match
        assert len(results) == 0


class TestCodeParserContextConfig:
    """Tests for configuration passed via ParseContext.

    REF: REQ-d00100-G - Context-based configuration
    """

    def test_REQ_d00100_G_pattern_config_from_context(self):
        """Test that PatternConfig can be passed via context.config."""
        from elspais.utilities.patterns import PatternConfig

        pattern_config = PatternConfig.from_dict(
            {
                "prefix": "TASK",
                "types": {"feature": {"id": "f", "name": "Feature"}},
                "id_format": {"style": "numeric", "digits": 3},
            }
        )

        parser = CodeParser()  # No instance config
        lines = [
            (1, "def task():"),
            (2, "    # Implements: TASK-f001"),
            (3, "    pass"),
        ]
        ctx = ParseContext(
            file_path="src/task.py",
            config={"pattern_config": pattern_config},
        )

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 1
        assert "TASK-f001" in results[0].parsed_data["implements"]

    def test_REQ_d00100_G_reference_resolver_from_context(self):
        """Test that ReferenceResolver can be passed via context.config."""
        from elspais.utilities.reference_config import ReferenceConfig, ReferenceResolver

        ref_config = ReferenceConfig(
            keywords={"validates": ["Checks"]},
        )
        resolver = ReferenceResolver(ref_config, [])

        parser = CodeParser()  # No instance config
        lines = [
            (1, "def check():"),
            (2, "    # Checks: REQ-p00001"),
            (3, "    pass"),
        ]
        ctx = ParseContext(
            file_path="tests/test_check.py",
            config={
                "reference_resolver": resolver,
                "repo_root": ".",
            },
        )

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 1
        assert results[0].parsed_data["validates"] == ["REQ-p00001"]

    def test_REQ_d00100_G_instance_config_takes_precedence(self):
        """Test that instance config takes precedence over context config."""
        from elspais.utilities.patterns import PatternConfig

        instance_config = PatternConfig.from_dict(
            {
                "prefix": "INSTANCE",
                "types": {"prd": {"id": "p", "name": "PRD"}},
                "id_format": {"style": "numeric", "digits": 5},
            }
        )
        context_config = PatternConfig.from_dict(
            {
                "prefix": "CONTEXT",
                "types": {"prd": {"id": "p", "name": "PRD"}},
                "id_format": {"style": "numeric", "digits": 5},
            }
        )

        parser = CodeParser(pattern_config=instance_config)
        lines = [
            (1, "def test():"),
            (2, "    # Implements: INSTANCE-p00001"),
            (3, "    pass"),
        ]
        ctx = ParseContext(
            file_path="src/test.py",
            config={"pattern_config": context_config},
        )

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 1
        assert "INSTANCE-p00001" in results[0].parsed_data["implements"]


class TestCodeParserMultipleRefs:
    """Tests for parsing multiple references in single comment.

    REF: REQ-d00100-H - Multiple reference parsing
    """

    def test_REQ_d00100_H_comma_separated_implements(self):
        """Test parsing comma-separated implements references."""
        parser = CodeParser()
        lines = [
            (1, "def complex_func():"),
            (2, "    # Implements: REQ-p00001, REQ-p00002, REQ-p00003"),
            (3, "    pass"),
        ]
        ctx = ParseContext(file_path="src/complex.py")

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 1
        impl = results[0].parsed_data["implements"]
        assert len(impl) == 3
        assert "REQ-p00001" in impl
        assert "REQ-p00002" in impl
        assert "REQ-p00003" in impl

    def test_REQ_d00100_H_comma_separated_validates(self):
        """Test parsing comma-separated validates references."""
        parser = CodeParser()
        lines = [
            (1, "def test_multiple():"),
            (2, "    # Validates: REQ-d00001-A, REQ-d00001-B"),
            (3, "    assert True"),
        ]
        ctx = ParseContext(file_path="tests/test_multi.py")

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 1
        val = results[0].parsed_data["validates"]
        assert len(val) == 2
        assert "REQ-d00001-A" in val
        assert "REQ-d00001-B" in val


class TestCodeParserFunctionContext:
    """Tests for Python function context tracking in parsed_data."""

    def test_function_context_in_parsed_data(self):
        """Implements comment inside a function gets function_name in parsed_data."""
        parser = CodeParser()
        lines = [
            (1, "def authenticate():"),
            (2, "    # Implements: REQ-p00001"),
            (3, "    pass"),
        ]
        ctx = ParseContext(file_path="src/auth.py")

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 1
        pd = results[0].parsed_data
        assert pd["function_name"] == "authenticate"
        assert pd["function_line"] == 1

    def test_class_context_in_parsed_data(self):
        """Implements comment inside a class method gets both class_name and function_name."""
        parser = CodeParser()
        lines = [
            (1, "class MyClass:"),
            (2, "    def method(self):"),
            (3, "        # Implements: REQ-p00001"),
            (4, "        pass"),
        ]
        ctx = ParseContext(file_path="src/auth.py")

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 1
        pd = results[0].parsed_data
        assert pd["function_name"] == "method"
        assert pd["class_name"] == "MyClass"
        assert pd["function_line"] == 2

    def test_no_function_context_at_module_level(self):
        """Implements comment at module level has function_name None."""
        parser = CodeParser()
        lines = [
            (1, "# Implements: REQ-p00001"),
            (2, ""),
            (3, ""),
            (4, ""),
            (5, ""),
            (6, ""),
            (7, "x = 42"),
        ]
        ctx = ParseContext(file_path="src/module.py")

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 1
        pd = results[0].parsed_data
        assert pd["function_name"] is None

    def test_forward_looking_comment_before_function(self):
        """Implements comment above a function definition gets function_name via lookahead."""
        parser = CodeParser()
        lines = [
            (1, "# Implements: REQ-p00001"),
            (2, "def authenticate():"),
            (3, "    pass"),
        ]
        ctx = ParseContext(file_path="src/auth.py")

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 1
        pd = results[0].parsed_data
        assert pd["function_name"] == "authenticate"
        assert pd["function_line"] == 2

    def test_async_function_context(self):
        """Async def is detected correctly for function context."""
        parser = CodeParser()
        lines = [
            (1, "async def handler(request):"),
            (2, "    # Implements: REQ-p00001"),
            (3, "    return response"),
        ]
        ctx = ParseContext(file_path="src/handlers.py")

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 1
        pd = results[0].parsed_data
        assert pd["function_name"] == "handler"
        assert pd["function_line"] == 1


class TestCodeParserMultiLanguageContext:
    """Tests for non-Python language detection and function context."""

    def test_javascript_function_detection(self):
        """JS file with function keyword detects function context."""
        parser = CodeParser()
        lines = [
            (1, "function authenticate(user) {"),
            (2, "    // Implements: REQ-p00001"),
            (3, "    return true;"),
            (4, "}"),
        ]
        ctx = ParseContext(file_path="src/auth.js")

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 1
        pd = results[0].parsed_data
        assert pd["function_name"] == "authenticate"

    def test_typescript_class_detection(self):
        """TS file with class keyword detects class context."""
        parser = CodeParser()
        lines = [
            (1, "class AuthService {"),
            (2, "    // Implements: REQ-p00001"),
            (3, "}"),
        ]
        ctx = ParseContext(file_path="src/auth.ts")

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 1
        pd = results[0].parsed_data
        assert pd["class_name"] == "AuthService"

    def test_go_function_detection(self):
        """Go file with func keyword detects function context."""
        parser = CodeParser()
        lines = [
            (1, "func ProcessRequest(w http.ResponseWriter, r *http.Request) {"),
            (2, "    // Implements: REQ-p00001"),
            (3, "}"),
        ]
        ctx = ParseContext(file_path="src/handler.go")

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 1
        pd = results[0].parsed_data
        assert pd["function_name"] == "ProcessRequest"

    def test_rust_function_detection(self):
        """Rust file with pub fn detects function context."""
        parser = CodeParser()
        lines = [
            (1, "pub fn validate(input: &str) -> bool {"),
            (2, "    // Implements: REQ-p00001"),
            (3, "    true"),
            (4, "}"),
        ]
        ctx = ParseContext(file_path="src/validator.rs")

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 1
        pd = results[0].parsed_data
        assert pd["function_name"] == "validate"

    def test_unknown_extension_falls_back(self):
        """Unknown file extension falls back to Python-style detection."""
        parser = CodeParser()
        lines = [
            (1, "def fallback_func():"),
            (2, "    # Implements: REQ-p00001"),
            (3, "    pass"),
        ]
        ctx = ParseContext(file_path="src/script.xyz")

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 1
        pd = results[0].parsed_data
        # Unknown falls back to Python-style patterns, so def should be detected
        assert pd["function_name"] == "fallback_func"


class TestCodeParserLanguageDetection:
    """Tests for CodeParser._detect_language static method."""

    def test_python_extensions(self):
        """Python file extensions map to 'python' language."""
        assert CodeParser._detect_language("src/app.py") == "python"
        assert CodeParser._detect_language("src/app.pyw") == "python"

    def test_js_extensions(self):
        """JS/TS file extensions map to 'js' language."""
        assert CodeParser._detect_language("src/app.js") == "js"
        assert CodeParser._detect_language("src/app.ts") == "js"
        assert CodeParser._detect_language("src/app.jsx") == "js"
        assert CodeParser._detect_language("src/app.tsx") == "js"

    def test_go_extension(self):
        """Go file extension maps to 'go' language."""
        assert CodeParser._detect_language("src/main.go") == "go"

    def test_rust_extension(self):
        """Rust file extension maps to 'rust' language."""
        assert CodeParser._detect_language("src/lib.rs") == "rust"

    def test_c_family_extensions(self):
        """C-family file extensions map to 'c' language."""
        assert CodeParser._detect_language("src/main.c") == "c"
        assert CodeParser._detect_language("src/main.cpp") == "c"
        assert CodeParser._detect_language("src/Main.java") == "c"
        assert CodeParser._detect_language("src/Main.cs") == "c"

    def test_unknown_extension(self):
        """Unknown file extensions map to 'unknown' language."""
        assert CodeParser._detect_language("data/config.txt") == "unknown"
        assert CodeParser._detect_language("docs/readme.md") == "unknown"


class TestCodeParserBraceScope:
    """Tests for brace-based scoping in C-family languages."""

    def test_brace_scope_exits_function(self):
        """After closing brace, next comment is outside function scope."""
        parser = CodeParser()
        lines = [
            (1, "function auth() {"),
            (2, "    // Implements: REQ-p00001"),
            (3, "}"),
            (4, "// Implements: REQ-p00002"),
            (5, ""),
        ]
        ctx = ParseContext(file_path="src/auth.js")

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 2
        # First result inside function
        assert results[0].parsed_data["function_name"] == "auth"
        # Second result outside function (after closing brace)
        assert results[1].parsed_data["function_name"] is None

    def test_nested_braces(self):
        """Function with nested non-function blocks still tracks function context."""
        parser = CodeParser()
        lines = [
            (1, "function process() {"),
            (2, "    let x = 1;"),
            (3, "    {"),
            (4, "        // Implements: REQ-p00001"),
            (5, "    }"),
            (6, "}"),
        ]
        ctx = ParseContext(file_path="src/process.js")

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 1
        pd = results[0].parsed_data
        assert pd["function_name"] == "process"


class TestBuilderCodeRefFunctionContext:
    """Tests that the builder stores function metadata on CODE nodes."""

    def test_code_node_stores_function_name(self):
        """Builder stores function_name on CODE node from parsed_data."""
        from elspais.graph.builder import GraphBuilder
        from elspais.graph.parsers import ParsedContent
        from tests.core.graph_test_helpers import MockSourceContext

        builder = GraphBuilder()
        content = ParsedContent(
            content_type="code_ref",
            start_line=10,
            end_line=10,
            raw_text="# Implements: REQ-p00001",
            parsed_data={
                "implements": ["REQ-p00001"],
                "validates": [],
                "function_name": "authenticate",
                "class_name": None,
                "function_line": 8,
            },
        )
        content.source_context = MockSourceContext(source_id="src/auth.py")
        builder.add_parsed_content(content)
        graph = builder.build()
        code_node = graph.find_by_id("code:src/auth.py:10")
        assert code_node is not None
        assert code_node.get_field("function_name") == "authenticate"
        assert code_node.get_field("class_name") is None

    def test_code_node_stores_class_and_function(self):
        """Builder stores both class_name and function_name, and builds descriptive label."""
        from elspais.graph.builder import GraphBuilder
        from elspais.graph.parsers import ParsedContent
        from tests.core.graph_test_helpers import MockSourceContext

        builder = GraphBuilder()
        content = ParsedContent(
            content_type="code_ref",
            start_line=20,
            end_line=20,
            raw_text="# Implements: REQ-p00001",
            parsed_data={
                "implements": ["REQ-p00001"],
                "validates": [],
                "function_name": "validate",
                "class_name": "AuthService",
                "function_line": 15,
            },
        )
        content.source_context = MockSourceContext(source_id="src/auth.py")
        builder.add_parsed_content(content)
        graph = builder.build()
        code_node = graph.find_by_id("code:src/auth.py:20")
        assert code_node is not None
        assert code_node.get_field("function_name") == "validate"
        assert code_node.get_field("class_name") == "AuthService"
        assert "AuthService.validate" in code_node.get_label()

    def test_code_node_label_without_function(self):
        """Builder creates simple label when no function context is present."""
        from elspais.graph.builder import GraphBuilder
        from elspais.graph.parsers import ParsedContent
        from tests.core.graph_test_helpers import MockSourceContext

        builder = GraphBuilder()
        content = ParsedContent(
            content_type="code_ref",
            start_line=1,
            end_line=1,
            raw_text="# Implements: REQ-p00001",
            parsed_data={
                "implements": ["REQ-p00001"],
                "validates": [],
                "function_name": None,
                "class_name": None,
                "function_line": 0,
            },
        )
        content.source_context = MockSourceContext(source_id="src/module.py")
        builder.add_parsed_content(content)
        graph = builder.build()
        code_node = graph.find_by_id("code:src/module.py:1")
        assert code_node is not None
        assert code_node.get_label() == "Code at src/module.py:1"

    def test_code_node_label_function_only(self):
        """Builder creates label with function name when no class context."""
        from elspais.graph.builder import GraphBuilder
        from elspais.graph.parsers import ParsedContent
        from tests.core.graph_test_helpers import MockSourceContext

        builder = GraphBuilder()
        content = ParsedContent(
            content_type="code_ref",
            start_line=5,
            end_line=5,
            raw_text="# Implements: REQ-p00001",
            parsed_data={
                "implements": ["REQ-p00001"],
                "validates": [],
                "function_name": "process",
                "class_name": None,
                "function_line": 3,
            },
        )
        content.source_context = MockSourceContext(source_id="src/process.py")
        builder.add_parsed_content(content)
        graph = builder.build()
        code_node = graph.find_by_id("code:src/process.py:5")
        assert code_node is not None
        assert code_node.get_label() == "Code: process at src/process.py:5"

    def test_code_node_stores_function_line(self):
        """Builder stores function_line field on CODE node."""
        from elspais.graph.builder import GraphBuilder
        from elspais.graph.parsers import ParsedContent
        from tests.core.graph_test_helpers import MockSourceContext

        builder = GraphBuilder()
        content = ParsedContent(
            content_type="code_ref",
            start_line=25,
            end_line=25,
            raw_text="# Implements: REQ-p00001",
            parsed_data={
                "implements": ["REQ-p00001"],
                "validates": [],
                "function_name": "render",
                "class_name": "View",
                "function_line": 20,
            },
        )
        content.source_context = MockSourceContext(source_id="src/view.py")
        builder.add_parsed_content(content)
        graph = builder.build()
        code_node = graph.find_by_id("code:src/view.py:25")
        assert code_node is not None
        assert code_node.get_field("function_line") == 20
