# Validates REQ-d00054-A
"""Tests for test_identity.py - Test identity utilities for canonical TEST node IDs."""

from elspais.utilities.test_identity import (
    build_test_id,
    build_test_id_from_nodeid,
    build_test_id_from_result,
    classname_to_module_path,
    strip_parametrize_suffix,
)


class TestClassnameToModulePath:
    """Tests for classname_to_module_path function."""

    def test_REQ_d00054_A_standard_dotted_path_with_class(self):
        """Standard dotted classname with uppercase class segment."""
        module_path, class_name = classname_to_module_path("tests.core.test_foo.TestBar")
        assert module_path == "tests/core/test_foo.py"
        assert class_name == "TestBar"

    def test_REQ_d00054_A_dotted_path_without_class(self):
        """Dotted path with no uppercase-starting segments yields no class."""
        module_path, class_name = classname_to_module_path("tests.core.test_foo")
        assert module_path == "tests/core/test_foo.py"
        assert class_name is None

    def test_REQ_d00054_A_single_module_no_class(self):
        """Single module name (no dots, no class)."""
        module_path, class_name = classname_to_module_path("test_simple")
        assert module_path == "test_simple.py"
        assert class_name is None

    def test_REQ_d00054_A_empty_string(self):
        """Empty string returns empty path and no class."""
        module_path, class_name = classname_to_module_path("")
        assert module_path == ""
        assert class_name is None

    def test_REQ_d00054_A_nested_classes(self):
        """Multiple trailing uppercase segments are joined as class name."""
        module_path, class_name = classname_to_module_path("tests.test_foo.TestOuter.TestInner")
        assert module_path == "tests/test_foo.py"
        assert class_name == "TestOuter.TestInner"

    def test_REQ_d00054_A_module_with_numeric_segments(self):
        """Numeric path segments (lowercase) are treated as module parts."""
        module_path, class_name = classname_to_module_path("tests.v2.test_api")
        assert module_path == "tests/v2/test_api.py"
        assert class_name is None

    def test_REQ_d00054_A_all_uppercase_segments(self):
        """When all segments start uppercase, module path is empty."""
        module_path, class_name = classname_to_module_path("TestFoo.TestBar")
        assert module_path == ""
        assert class_name == "TestFoo.TestBar"

    def test_REQ_d00054_A_single_class_only(self):
        """Single uppercase segment produces empty module path."""
        module_path, class_name = classname_to_module_path("TestFoo")
        assert module_path == ""
        assert class_name == "TestFoo"

    def test_REQ_d00054_A_deep_nesting(self):
        """Deeply nested module path preserves all segments."""
        module_path, class_name = classname_to_module_path(
            "tests.integration.api.v2.test_endpoints.TestCreate"
        )
        assert module_path == "tests/integration/api/v2/test_endpoints.py"
        assert class_name == "TestCreate"

    def test_REQ_d00054_A_mixed_case_not_leading_upper(self):
        """Segments starting lowercase are module parts even if they contain uppercase."""
        module_path, class_name = classname_to_module_path("tests.testUtils.test_foo")
        assert module_path == "tests/testUtils/test_foo.py"
        assert class_name is None


class TestStripParametrizeSuffix:
    """Tests for strip_parametrize_suffix function."""

    def test_REQ_d00054_A_with_suffix(self):
        """Parametrize suffix in brackets is stripped."""
        result = strip_parametrize_suffix("test_foo[1-2]")
        assert result == "test_foo"

    def test_REQ_d00054_A_without_suffix(self):
        """Name without brackets is unchanged."""
        result = strip_parametrize_suffix("test_foo")
        assert result == "test_foo"

    def test_REQ_d00054_A_multiple_brackets(self):
        """Only the trailing bracket pair is stripped."""
        result = strip_parametrize_suffix("test_foo[a][b]")
        # re.sub with [.*] greedy match strips from first [ to last ]
        assert result == "test_foo"

    def test_REQ_d00054_A_empty_brackets(self):
        """Empty brackets are still stripped."""
        result = strip_parametrize_suffix("test_foo[]")
        assert result == "test_foo"

    def test_REQ_d00054_A_brackets_in_middle(self):
        """Brackets not at end are NOT stripped (only trailing)."""
        result = strip_parametrize_suffix("test_foo[a]_bar")
        assert result == "test_foo[a]_bar"

    def test_REQ_d00054_A_complex_params(self):
        """Complex parametrize values with special characters are stripped."""
        result = strip_parametrize_suffix("test_validate[param1-param2-True]")
        assert result == "test_validate"

    def test_REQ_d00054_A_empty_string(self):
        """Empty string remains empty."""
        result = strip_parametrize_suffix("")
        assert result == ""

    def test_REQ_d00054_A_nested_brackets(self):
        """Nested brackets are all stripped by greedy match."""
        result = strip_parametrize_suffix("test_foo[a[b]c]")
        assert result == "test_foo"


class TestBuildTestId:
    """Tests for build_test_id function."""

    def test_REQ_d00054_A_with_class(self):
        """Build ID with class produces three-part format."""
        result = build_test_id("tests/test_foo.py", "test_bar", "TestFoo")
        assert result == "test:tests/test_foo.py::TestFoo::test_bar"

    def test_REQ_d00054_A_without_class(self):
        """Build ID without class produces two-part format."""
        result = build_test_id("tests/test_foo.py", "test_bar")
        assert result == "test:tests/test_foo.py::test_bar"

    def test_REQ_d00054_A_with_class_none_explicit(self):
        """Explicit None class_name produces two-part format."""
        result = build_test_id("tests/test_foo.py", "test_bar", None)
        assert result == "test:tests/test_foo.py::test_bar"

    def test_REQ_d00054_A_strips_parametrize_suffix(self):
        """Parametrize suffix is stripped from function name."""
        result = build_test_id("tests/test_foo.py", "test_bar[1-2]", "TestFoo")
        assert result == "test:tests/test_foo.py::TestFoo::test_bar"

    def test_REQ_d00054_A_strips_parametrize_without_class(self):
        """Parametrize suffix stripped even without class."""
        result = build_test_id("tests/test_foo.py", "test_bar[param]")
        assert result == "test:tests/test_foo.py::test_bar"

    def test_REQ_d00054_A_deep_module_path(self):
        """Deep module paths are preserved in the ID."""
        result = build_test_id(
            "tests/integration/api/test_endpoints.py",
            "test_create",
            "TestEndpoints",
        )
        assert result == "test:tests/integration/api/test_endpoints.py::TestEndpoints::test_create"

    def test_REQ_d00054_A_empty_module_path(self):
        """Empty module path still produces valid format."""
        result = build_test_id("", "test_foo", "TestBar")
        assert result == "test:::TestBar::test_foo"

    def test_REQ_d00054_A_function_name_no_suffix(self):
        """Plain function name without parametrize is unchanged."""
        result = build_test_id("tests/test_foo.py", "test_validates_input")
        assert result == "test:tests/test_foo.py::test_validates_input"


class TestBuildTestIdFromResult:
    """Tests for build_test_id_from_result function."""

    def test_REQ_d00054_A_full_classname_with_class(self):
        """Full dotted classname with class segment."""
        result = build_test_id_from_result("tests.core.test_foo.TestBar", "test_func")
        assert result == "test:tests/core/test_foo.py::TestBar::test_func"

    def test_REQ_d00054_A_classname_without_class(self):
        """Dotted classname without uppercase class segment."""
        result = build_test_id_from_result("tests.test_foo", "test_func")
        assert result == "test:tests/test_foo.py::test_func"

    def test_REQ_d00054_A_with_parametrize(self):
        """Parametrize suffix in test_name is stripped."""
        result = build_test_id_from_result("tests.test_foo.TestBar", "test_func[param]")
        assert result == "test:tests/test_foo.py::TestBar::test_func"

    def test_REQ_d00054_A_complex_parametrize(self):
        """Complex parametrize values are fully stripped."""
        result = build_test_id_from_result(
            "tests.core.test_validate.TestHash", "test_verify[sha256-8-True]"
        )
        assert result == "test:tests/core/test_validate.py::TestHash::test_verify"

    def test_REQ_d00054_A_single_module(self):
        """Single module name with no dots and no class."""
        result = build_test_id_from_result("test_simple", "test_basic")
        assert result == "test:test_simple.py::test_basic"

    def test_REQ_d00054_A_nested_class(self):
        """Nested class names are joined in the ID."""
        result = build_test_id_from_result("tests.test_foo.TestOuter.TestInner", "test_method")
        assert result == "test:tests/test_foo.py::TestOuter.TestInner::test_method"

    def test_REQ_d00054_A_empty_classname(self):
        """Empty classname still produces an ID (with empty module path)."""
        result = build_test_id_from_result("", "test_func")
        assert result == "test:::test_func"

    def test_REQ_d00054_A_matches_build_test_id_components(self):
        """build_test_id_from_result produces same result as manual decomposition."""
        classname = "tests.integration.test_api.TestEndpoint"
        test_name = "test_create[json]"

        # Manual decomposition
        module_path, class_name = classname_to_module_path(classname)
        clean_name = strip_parametrize_suffix(test_name)
        expected = build_test_id(module_path, clean_name, class_name)

        # Convenience function
        actual = build_test_id_from_result(classname, test_name)

        assert actual == expected


class TestBuildTestIdFromNodeid:
    """Tests for build_test_id_from_nodeid function."""

    def test_REQ_d00054_A_standard_nodeid(self):
        """Standard nodeid with class and function produces canonical test ID."""
        result = build_test_id_from_nodeid("tests/test_foo.py::TestBar::test_func")
        assert result == "test:tests/test_foo.py::TestBar::test_func"

    def test_REQ_d00054_A_without_class(self):
        """Nodeid without class (module-level test) produces two-part ID."""
        result = build_test_id_from_nodeid("tests/test_foo.py::test_func")
        assert result == "test:tests/test_foo.py::test_func"

    def test_REQ_d00054_A_with_parametrize(self):
        """Parametrize suffix is stripped from the last component."""
        result = build_test_id_from_nodeid("tests/test_foo.py::test_func[1-2]")
        assert result == "test:tests/test_foo.py::test_func"

    def test_REQ_d00054_A_complex_parametrize(self):
        """Complex parametrize suffix with multiple values is stripped."""
        result = build_test_id_from_nodeid("tests/test_foo.py::TestBar::test_func[a-b-c]")
        assert result == "test:tests/test_foo.py::TestBar::test_func"
