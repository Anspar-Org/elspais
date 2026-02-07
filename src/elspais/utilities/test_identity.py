"""Test identity utilities for canonical TEST node IDs.

Provides functions to convert between test result metadata (classname + function)
and canonical test IDs that match what the test scanner produces.

Canonical TEST ID format:
    test:{relative_path}::{ClassName}::{function_name}
    test:{relative_path}::{function_name}  (no class)
"""

from __future__ import annotations

import re


def classname_to_module_path(classname: str) -> tuple[str, str | None]:
    """Convert a dotted classname to a module file path and optional class name.

    JUnit XML and pytest JSON report test classnames as dotted paths like
    ``tests.core.test_foo.TestBar``. This function splits that into a
    filesystem path and an optional class name.

    The heuristic: segments starting with an uppercase letter are class names,
    not module path components. We strip trailing uppercase-starting segments.

    Args:
        classname: Dotted classname from test results.

    Returns:
        Tuple of (module_path, class_name). module_path uses forward slashes
        and ends with ``.py``. class_name is None if no class was detected.

    Examples:
        >>> classname_to_module_path("tests.core.test_foo.TestBar")
        ('tests/core/test_foo.py', 'TestBar')
        >>> classname_to_module_path("tests.core.test_foo")
        ('tests/core/test_foo.py', None)
        >>> classname_to_module_path("test_simple")
        ('test_simple.py', None)
    """
    if not classname:
        return ("", None)

    parts = classname.split(".")

    # Find where class names start (trailing uppercase-starting segments)
    class_parts: list[str] = []
    while parts and parts[-1] and parts[-1][0].isupper():
        class_parts.insert(0, parts.pop())

    class_name = ".".join(class_parts) if class_parts else None

    # Remaining parts form the module path
    if not parts:
        # All parts were class names — unusual but handle it
        return ("", class_name)

    module_path = "/".join(parts) + ".py"
    return (module_path, class_name)


def strip_parametrize_suffix(test_name: str) -> str:
    """Strip pytest parametrize suffix from test name.

    Parametrized tests have names like ``test_foo[param1-param2]``.
    All parametrized variants should map to the same TEST node.

    Args:
        test_name: Test function name, possibly with parametrize suffix.

    Returns:
        Test name without the ``[...]`` suffix.

    Examples:
        >>> strip_parametrize_suffix("test_foo[1-2]")
        'test_foo'
        >>> strip_parametrize_suffix("test_foo")
        'test_foo'
    """
    return re.sub(r"\[.*\]$", "", test_name)


def build_test_id(
    module_path: str,
    function_name: str,
    class_name: str | None = None,
) -> str:
    """Build a canonical test ID from components.

    The canonical format is::

        test:{module_path}::{ClassName}::{function_name}

    or without a class::

        test:{module_path}::{function_name}

    Args:
        module_path: Relative file path (e.g., ``tests/core/test_foo.py``).
        function_name: Test function name (e.g., ``test_validates_input``).
        class_name: Optional test class name (e.g., ``TestFoo``).

    Returns:
        Canonical test ID string.

    Examples:
        >>> build_test_id("tests/core/test_foo.py", "test_bar", "TestFoo")
        'test:tests/core/test_foo.py::TestFoo::test_bar'
        >>> build_test_id("tests/test_foo.py", "test_bar")
        'test:tests/test_foo.py::test_bar'
    """
    # Strip parametrize suffix from function name
    clean_name = strip_parametrize_suffix(function_name)

    if class_name:
        return f"test:{module_path}::{class_name}::{clean_name}"
    return f"test:{module_path}::{clean_name}"


def build_test_id_from_result(
    classname: str,
    test_name: str,
) -> str:
    """Build a canonical test ID from JUnit XML test result metadata.

    Converts dotted classnames (JUnit XML style) to canonical test IDs.
    Uses ``classname_to_module_path`` to split dotted paths into
    file path + class name components.

    Args:
        classname: Dotted classname from JUnit XML result file.
        test_name: Test function name from result file.

    Returns:
        Canonical test ID string.

    Examples:
        >>> build_test_id_from_result("tests.core.test_foo.TestBar", "test_func")
        'test:tests/core/test_foo.py::TestBar::test_func'
    """
    module_path, class_name = classname_to_module_path(classname)
    return build_test_id(module_path, strip_parametrize_suffix(test_name), class_name)


def build_test_id_from_nodeid(nodeid: str) -> str:
    """Build a canonical test ID from a pytest nodeid.

    Pytest nodeids already contain the file path and use ``::`` separators,
    matching our canonical format. We just need to strip parametrize suffixes
    and add the ``test:`` prefix.

    Args:
        nodeid: Pytest nodeid (e.g., ``tests/test_foo.py::TestBar::test_func``
                or ``tests/test_foo.py::test_func[param]``).

    Returns:
        Canonical test ID string.

    Examples:
        >>> build_test_id_from_nodeid("tests/test_foo.py::TestBar::test_func")
        'test:tests/test_foo.py::TestBar::test_func'
        >>> build_test_id_from_nodeid("tests/test_foo.py::test_func[1-2]")
        'test:tests/test_foo.py::test_func'
    """
    # Strip parametrize suffix from the last component
    parts = nodeid.split("::")
    if parts:
        parts[-1] = strip_parametrize_suffix(parts[-1])
    cleaned = "::".join(parts)
    return f"test:{cleaned}"
