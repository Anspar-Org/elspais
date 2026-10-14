# tests/core/test_syntax_tree_reading.py
"""What a tree-sitter syntax tree reads from a source file.

``syntax_tree.read`` finds each test, group and function, the full name a
JavaScript test framework gives a test, and ``build_line_context`` and
``declaration_starts`` turn its functions into the extents a code citation
binds by.
"""

from __future__ import annotations

import pytest

from elspais.graph.parsers import syntax_tree
from elspais.graph.parsers.prescan import build_line_context, declaration_starts


def _lines(src: str) -> list[tuple[int, str]]:
    return [(i + 1, t) for i, t in enumerate(src.split("\n"))]


# ---------------------------------------------------------------------------
# Each language's tests: start, end, name, group
# ---------------------------------------------------------------------------

_JS = """\
describe('Auth', () => {
  it('logs in', () => {
    expect(1).toBe(1);
  });
  test.each([[1], [2]])('handles %i', (n) => {
    expect(n).toBeTruthy();
  });
});
"""

_GO = """\
package x

func helper() int {
\treturn 1
}

func TestAdd(t *testing.T) {
\thelper()
}
"""

_JAVA = """\
class FooTest {
    @Test
    void adds() {
        assert true;
    }

    void helper() {
    }

    @org.junit.jupiter.api.Test
    void more() {}
}
"""

_KOTLIN = """\
class FooTest {
    @Test
    fun adds() {
        check(true)
    }
}
"""

_RUST = """\
fn helper() {}

#[cfg(test)]
mod tests {
    #[test]
    fn adds() {
        assert!(true);
    }
}
"""

_CSHARP = """\
public class FooTests
{
    [TestMethodAttribute]
    public void Adds()
    {
    }

    public void Helper() {}
}
"""


# Verifies: REQ-d00332-A
@pytest.mark.parametrize(
    "path,src,tests,groups",
    [
        pytest.param(
            "test/auth.test.ts",
            _JS,
            [(2, 4, None, None), (5, 7, None, None)],
            [(1, 8, "Auth")],
            id="typescript-each-is-one-test",
        ),
        pytest.param(
            "test/auth.test.js",
            _JS,
            [(2, 4, None, None), (5, 7, None, None)],
            [(1, 8, "Auth")],
            id="javascript",
        ),
        pytest.param("x_test.go", _GO, [(7, 9, "TestAdd", None)], [], id="go"),
        pytest.param(
            "FooTest.java",
            _JAVA,
            [(2, 5, "adds", "FooTest"), (10, 11, "more", "FooTest")],
            [(1, 12, "FooTest")],
            id="java-annotation-line-and-qualified-annotation",
        ),
        pytest.param(
            "FooTest.kt", _KOTLIN, [(2, 5, "adds", "FooTest")], [(1, 6, "FooTest")], id="kotlin"
        ),
        pytest.param(
            "src/lib.rs", _RUST, [(5, 8, "adds", "tests")], [(3, 9, "tests")], id="rust-cfg-mod"
        ),
        pytest.param(
            "FooTests.cs",
            _CSHARP,
            [(3, 6, "Adds", "FooTests")],
            [(1, 9, "FooTests")],
            id="csharp-attribute-suffix",
        ),
    ],
)
def test_each_language_reads_its_tests_and_groups(path, src, tests, groups):
    reading = syntax_tree.read(path, src)

    assert list(reading.tests) == tests
    assert list(reading.groups) == groups


# Verifies: REQ-d00332-A
@pytest.mark.parametrize(
    "path,src,not_a_test",
    [
        pytest.param("x_test.go", _GO, "helper", id="go-helper"),
        pytest.param("FooTest.java", _JAVA, "helper", id="java-unannotated"),
        pytest.param("FooTests.cs", _CSHARP, "Helper", id="csharp-unattributed"),
        pytest.param("src/lib.rs", _RUST, "helper", id="rust-unattributed"),
    ],
)
def test_a_function_without_the_test_convention_is_not_a_test(path, src, not_a_test):
    reading = syntax_tree.read(path, src)

    assert not_a_test in {name for _s, _e, name, _c in reading.functions}
    assert not_a_test not in {name for _s, _e, name, _g in reading.tests}


# Verifies: REQ-d00332-A
@pytest.mark.parametrize("path", ["notes.md", "script.py", "test/a_test.dart"])
def test_a_language_the_tree_does_not_read_has_no_reading(path):
    assert syntax_tree.read(path, "x = 1\n") is None


# ---------------------------------------------------------------------------
# Code files: the function a citation is written above
# ---------------------------------------------------------------------------

#  1: // Implements: REQ-p00001-A
#  2: @Service
#  3: public class Foo {
#  4:     @Override
#  5:     public void run() {
#  6:         // Implements: REQ-p00001-B
#  7:         int x = 1;
#  8:     }
#  9: }
_JAVA_CODE = """\
// Implements: REQ-p00001-A
@Service
public class Foo {
    @Override
    public void run() {
        // Implements: REQ-p00001-B
        int x = 1;
    }
}
"""

#  1: // Implements: REQ-p00001-A
#  2: impl Foo {
#  3:     #[inline]
#  4:     fn m(&self) {
#  5:         // Implements: REQ-p00001-B
#  6:         let x = 1;
#  7:     }
#  8: }
_RUST_CODE = """\
// Implements: REQ-p00001-A
impl Foo {
    #[inline]
    fn m(&self) {
        // Implements: REQ-p00001-B
        let x = 1;
    }
}
"""

#  1: function outer() {
#  2:   // Implements: REQ-p00001-B
#  3:   const y = 1;
#  4:   // Implements: REQ-p00001-A
#  5:   function inner() {
#  6:     return y;
#  7:   }
#  8: }
_JS_CODE = """\
function outer() {
  // Implements: REQ-p00001-B
  const y = 1;
  // Implements: REQ-p00001-A
  function inner() {
    return y;
  }
}
"""


# Verifies: REQ-d00254-D
@pytest.mark.parametrize(
    "path,language,src,above,inside,method",
    [
        pytest.param("src/Foo.java", "java", _JAVA_CODE, 1, 6, ("run", "Foo", 4, 8), id="java"),
        pytest.param("src/foo.rs", "rust", _RUST_CODE, 1, 5, ("m", "Foo", 3, 7), id="rust-impl"),
    ],
)
def test_a_code_citation_passes_the_class_header_to_the_first_method(
    path, language, src, above, inside, method
):
    context = build_line_context(_lines(src), language, path=path)

    assert context[above] == method
    assert context[inside] == method


# Verifies: REQ-d00254-D
def test_a_citation_above_a_nested_function_binds_to_it_and_one_in_a_body_stays():
    context = build_line_context(_lines(_JS_CODE), "javascript", path="src/outer.js")

    assert context[4][0] == "inner"
    assert context[4][2:] == (5, 7)
    assert context[2][0] == "outer"
    assert context[2][2:] == (1, 8)


# Verifies: REQ-d00254-D
@pytest.mark.parametrize(
    "path,language,src,starts",
    [
        pytest.param("src/Foo.java", "java", _JAVA_CODE, [4], id="java-annotation"),
        pytest.param("src/foo.rs", "rust", _RUST_CODE, [3], id="rust-attribute"),
        pytest.param("src/outer.js", "javascript", _JS_CODE, [1, 5], id="js-nested"),
    ],
)
def test_declaration_starts_include_the_lines_above_a_declaration(path, language, src, starts):
    assert declaration_starts(_lines(src), language, path=path) == starts


# ---------------------------------------------------------------------------
# JavaScript full test names
# ---------------------------------------------------------------------------


# Verifies: REQ-d00284-G+H
@pytest.mark.parametrize(
    "src,line,name",
    [
        pytest.param(
            "describe('Auth', () => {\n  it('logs in', () => {});\n});\n",
            2,
            "Auth logs in",
            id="group-and-test",
        ),
        pytest.param(
            'describe("Auth", () => {\n  describe(`session`, () => {\n'
            "    test('ends', () => {});\n  });\n});\n",
            3,
            "Auth session ends",
            id="nested-and-template-literal",
        ),
        pytest.param("it(`plain`, () => {});\n", 1, "plain", id="template-literal"),
        pytest.param("it(`has ${n}`, () => {});\n", 1, None, id="template-substitution"),
        pytest.param("it(label, () => {});\n", 1, None, id="variable"),
        pytest.param(
            "describe(suite, () => {\n  it('logs in', () => {});\n});\n",
            2,
            None,
            id="variable-group",
        ),
    ],
)
def test_a_js_test_is_named_by_its_literal_descriptions(src, line, name):
    reading = syntax_tree.read("test/a.test.ts", src)

    assert line in {start for start, _e, _n, _g in reading.tests}
    assert reading.names.get(line) == name
