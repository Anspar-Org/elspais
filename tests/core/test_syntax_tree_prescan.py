# tests/core/test_syntax_tree_prescan.py
"""Where a citation in a test file binds, from a tree-sitter syntax tree.

``tree_prescan`` turns a ``syntax_tree`` reading into the line context a
citation binds by, and a result recording no line binds to a JavaScript test
by the full name the reading gives it. Without the ``ast`` extra the reading
is absent, the file falls back to the text pre-scan, and the build says which
extra to install.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from elspais.graph.GraphNode import NodeKind
from elspais.graph.parsers import parse_cache, syntax_tree
from elspais.graph.parsers.lark import FileDispatcher
from elspais.graph.parsers.prescan import tree_prescan
from elspais.graph.relations import EdgeKind
from elspais.utilities.patterns import FederatedIdReader, IdPatternConfig, IdResolver


def _lines(src: str) -> list[tuple[int, str]]:
    return [(i + 1, t) for i, t in enumerate(src.split("\n"))]


def _id_config() -> IdPatternConfig:
    return IdPatternConfig.from_dict(
        {
            "project": {"namespace": "REQ"},
            "levels": {
                "prd": {"rank": 1, "letter": "p", "implements": ["prd"]},
                "dev": {"rank": 2, "letter": "d", "implements": ["dev", "prd"]},
            },
            "id-patterns": {
                "canonical": "{namespace}-{level.letter}{component}",
                "component": {"style": "numeric", "digits": 5, "leading_zeros": True},
                "assertions": {"label_style": "uppercase", "max_count": 26},
            },
        }
    )


@pytest.fixture
def without_extra(monkeypatch):
    """The process as it is where the ``ast`` extra is not installed."""
    real = syntax_tree.reader_identity()

    def _no_grammar(_path):
        raise ImportError("No module named 'tree_sitter'")

    monkeypatch.setattr(syntax_tree, "_PARSERS", {})
    monkeypatch.setattr(syntax_tree, "_parser", _no_grammar)
    monkeypatch.setattr(syntax_tree, "available", lambda: False)
    monkeypatch.setattr(
        syntax_tree, "reader_identity", lambda: tuple((dist, None) for dist, _v in real)
    )


# ---------------------------------------------------------------------------
# Where a citation in a test file binds
# ---------------------------------------------------------------------------

#  1: // Verifies: REQ-p00001-A      above a group holding a test
#  2: describe('Auth', () => {
#  3:   // Verifies: REQ-p00001-B    directly above a test
#  4:   it('logs in', () => {
#  5:     // Verifies: REQ-p00001-C  inside a test
#  6:     expect(1).toBe(1);
#  7:   });
#  8:
#  9:   // Verifies: REQ-p00001-D    separated from the test by a statement
# 10:   const x = 1;
# 11:   it('logs out', () => {});
# 12: });
# 13:
# 14: // Verifies: REQ-p00001-E      above a group holding no test
# 15: describe('Empty', () => {
# 16:   helper();
# 17: });
_JS_BINDING = """\
// Verifies: REQ-p00001-A
describe('Auth', () => {
  // Verifies: REQ-p00001-B
  it('logs in', () => {
    // Verifies: REQ-p00001-C
    expect(1).toBe(1);
  });

  // Verifies: REQ-p00001-D
  const x = 1;
  it('logs out', () => {});
});

// Verifies: REQ-p00001-E
describe('Empty', () => {
  helper();
});
"""

#  1: class FooTest {
#  2:     // Verifies: REQ-p00001-A
#  3:     @Test
#  4:     void a() {}
#  5:     // Verifies: REQ-p00001-B
#  6:     @Test
#  7:     void b() {}
#  8: }
#  9:
# 10: // Verifies: REQ-p00001-C
# 11: @DisplayName("x")
# 12: class BarTest {
# 13:     @Test
# 14:     void c() {}
# 15: }
# 16:
# 17: // Verifies: REQ-p00001-D
# 18: class Helpers {
# 19:     void h() {}
# 20: }
_JAVA_BINDING = """\
class FooTest {
    // Verifies: REQ-p00001-A
    @Test
    void a() {}
    // Verifies: REQ-p00001-B
    @Test
    void b() {}
}

// Verifies: REQ-p00001-C
@DisplayName("x")
class BarTest {
    @Test
    void c() {}
}

// Verifies: REQ-p00001-D
class Helpers {
    void h() {}
}
"""


def _tree_context(path: str, src: str):
    line_context, _tests = tree_prescan(_lines(src), syntax_tree.read(path, src))
    return line_context


# Verifies: REQ-d00332-E+F+G
@pytest.mark.parametrize(
    "path,src,citation,extent",
    [
        pytest.param("t/a.test.ts", _JS_BINDING, 5, (4, 7), id="js-inside-test"),
        pytest.param("t/a.test.ts", _JS_BINDING, 3, (4, 7), id="js-above-test"),
        pytest.param("t/a.test.ts", _JS_BINDING, 1, (2, 12), id="js-above-describe"),
        pytest.param("t/a.test.ts", _JS_BINDING, 9, (0, 0), id="js-statement-between"),
        pytest.param("t/a.test.ts", _JS_BINDING, 14, (0, 0), id="js-group-holding-no-test"),
        pytest.param("FooTest.java", _JAVA_BINDING, 2, (3, 4), id="java-above-annotation"),
        pytest.param("FooTest.java", _JAVA_BINDING, 10, (11, 15), id="java-above-test-class"),
        pytest.param("FooTest.java", _JAVA_BINDING, 17, (0, 0), id="java-class-holding-no-test"),
    ],
)
def test_a_citation_binds_to_the_test_or_group_it_is_in_or_above(path, src, citation, extent):
    _name, _group, start, end = _tree_context(path, src)[citation]

    assert (start, end) == extent


# Verifies: REQ-d00332-F
def test_a_citation_above_a_test_class_names_the_class_as_its_group():
    name, group, _start, _end = _tree_context("FooTest.java", _JAVA_BINDING)[10]

    assert (name, group) == (None, "BarTest")


# Verifies: REQ-d00332-I
@pytest.mark.parametrize(
    "path,src,first_test_end,next_citation,next_test",
    [
        pytest.param("FooTest.java", _JAVA_BINDING, 4, 5, (6, 7), id="java"),
        pytest.param(
            "t/two.test.ts",
            "it('a', () => {\n  run();\n});\n// Verifies: REQ-p00001-A\nit('b', () => {});\n",
            3,
            4,
            (5, 5),
            id="js",
        ),
    ],
)
def test_a_test_ends_before_the_comments_above_the_next(
    path, src, first_test_end, next_citation, next_test
):
    context = _tree_context(path, src)

    assert context[first_test_end][3] == first_test_end
    assert context[next_citation][2:] == next_test


_CONFIG = """\
version = 5

[project]
name = "web"
namespace = "REQ"

[levels.dev]
rank = 1
letter = "d"
implements = ["dev"]

[id-patterns]
canonical = "{namespace}-{level.letter}{component}"

[id-patterns.component]
style = "numeric"
digits = 5
leading_zeros = true

[scanning.spec]
directories = ["spec"]

[scanning.test]
enabled = true
directories = ["test"]
file_patterns = ["*.test.ts"]

[[scanning.test.targets]]
name = "jest"
reporter = "junit"
results = "junit.xml"
match = "source"

[rules.format]
require_hash = false
require_assertions = false
require_status = false
"""

_SPEC = """\
# Requirements

---

### REQ-d00001: Auth

**Level**: dev | **Status**: Active

## Assertions

A. The system SHALL log a user in.

B. The system SHALL log a user out.

*End* *Auth*
---
"""

_TEST_FILE = "test/auth.test.ts"
_TS = """\
describe('Auth', () => {
  // Verifies: REQ-d00001-A
  it('logs in', () => {
    expect(1).toBe(1);
  });
  // Verifies: REQ-d00001-B
  it('logs out', () => {
    expect(1).toBe(1);
  });
});
"""
_LOGS_IN_LINE = 3

_JUNIT = f"""\
<?xml version="1.0" encoding="UTF-8"?>
<testsuites>
  <testsuite name="auth" tests="1">
    <testcase classname="Auth" name="Auth logs in" file="{_TEST_FILE}" time="0.01"/>
  </testsuite>
</testsuites>
"""


def _write_project(root: Path, results: bool) -> None:
    for rel, text in {
        ".elspais.toml": _CONFIG,
        "spec/requirements.md": _SPEC,
        _TEST_FILE: _TS,
    }.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    if results:
        out = root / ".results" / "jest"
        out.mkdir(parents=True)
        (out / "junit.xml").write_text(_JUNIT, encoding="utf-8")


def _tests_in_file(graph) -> list:
    return [
        t
        for t in graph.iter_by_kind(NodeKind.TEST)
        if t.file_node() is not None and t.file_node().get_field("relative_path") == _TEST_FILE
    ]


# Verifies: REQ-d00284-E+G
def test_a_result_recording_no_line_binds_to_the_js_test_its_full_name_names(tmp_path):
    from elspais.graph.factory import build_graph

    root = tmp_path / "proj"
    _write_project(root, results=True)
    graph = build_graph(repo_root=root)
    (result,) = list(graph.iter_by_kind(NodeKind.RESULT))

    assert result.get_field("line") is None
    assert result.get_field("match_scope") == "test"
    yielding = list(result.iter_parents(edge_kinds={EdgeKind.YIELDS}))
    assert [t.get_field("parse_line") for t in yielding] == [_LOGS_IN_LINE]
    assert yielding[0].get_field("test_name") == "Auth logs in"


# ---------------------------------------------------------------------------
# Without the ast extra
# ---------------------------------------------------------------------------


# Verifies: REQ-d00332-A
def test_without_the_extra_there_is_no_reading(without_extra):
    assert syntax_tree.read("test/auth.test.ts", _TS) is None


# Verifies: REQ-d00332-A
def test_without_the_extra_a_js_test_file_falls_back_to_no_test_boundaries(without_extra):
    dispatcher = FileDispatcher(IdResolver(_id_config()))
    refs = [
        p
        for p in dispatcher.dispatch_test(_JS_BINDING, file_path="t/fallback.test.ts")
        if p.content_type == "test_ref"
    ]

    # Every citation is still read, but none is bound to a test, and no test
    # is reported on its own.
    assert sorted(r.start_line for r in refs) == [1, 3, 5, 9, 14]
    assert all(r.parsed_data["function_line"] == 0 for r in refs)
    assert all(r.parsed_data.get("test_name") is None for r in refs)


# Verifies: REQ-d00332-A
def test_without_the_extra_the_build_names_the_extra(tmp_path, without_extra, capsys):
    from elspais.graph.factory import build_graph

    root = tmp_path / "proj"
    _write_project(root, results=False)
    graph = build_graph(repo_root=root)

    err = capsys.readouterr().err
    assert f"elspais[{syntax_tree.EXTRA}]" in err
    assert _TEST_FILE in err
    assert _LOGS_IN_LINE not in {t.get_field("parse_line") for t in _tests_in_file(graph)}


# Verifies: REQ-d00332-A
def test_with_the_extra_the_build_warns_of_nothing(tmp_path, capsys):
    from elspais.graph.factory import build_graph

    root = tmp_path / "proj"
    _write_project(root, results=False)
    build_graph(repo_root=root)

    assert f"elspais[{syntax_tree.EXTRA}]" not in capsys.readouterr().err


_SPEC_FILES = ("test/a.spec.ts", "test/b.spec.ts")

# Reads candidate paths on stdin and reports one test for each path ending in
# a name given on its command line.
_PRESCAN = """\
import json
import sys

reported = sys.argv[1:]
records = [
    {"file": path, "function": "logs in", "class": "Auth", "line": 3}
    for path in sys.stdin.read().splitlines()
    if any(path.endswith(name) for name in reported)
]
print(json.dumps(records))
"""


def _write_prescan_project(root: Path, reported: tuple[str, ...] | None) -> None:
    config = _CONFIG.replace('["*.test.ts"]', '["*.spec.ts"]')
    if reported is not None:
        script = root / "prescan.py"
        script.parent.mkdir(parents=True, exist_ok=True)
        script.write_text(_PRESCAN, encoding="utf-8")
        command = " ".join([f'"{sys.executable}"', f'"{script}"', *reported])
        config = config.replace(
            'file_patterns = ["*.spec.ts"]',
            f'file_patterns = ["*.spec.ts"]\nprescan_command = {json.dumps(command)}',
        )
    for rel, text in {
        ".elspais.toml": config,
        "spec/requirements.md": _SPEC,
        **dict.fromkeys(_SPEC_FILES, _TS),
    }.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


# Verifies: REQ-d00332-D
@pytest.mark.parametrize(
    ("reported", "unread"),
    [
        pytest.param(("a.spec.ts", "b.spec.ts"), (), id="prescan-reads-both"),
        pytest.param(("a.spec.ts",), ("test/b.spec.ts",), id="prescan-reads-one"),
        pytest.param(None, _SPEC_FILES, id="no-prescan-command"),
    ],
)
def test_without_the_extra_the_warning_leaves_out_files_the_prescan_command_reads(
    tmp_path, without_extra, capsys, reported, unread
):
    from elspais.graph.factory import build_graph

    root = tmp_path / "proj"
    _write_prescan_project(root, reported)
    build_graph(repo_root=root)

    warnings = [
        line
        for line in capsys.readouterr().err.splitlines()
        if f"elspais[{syntax_tree.EXTRA}]" in line
    ]
    if not unread:
        assert warnings == []
    else:
        (warning,) = warnings
        assert f"{len(unread)} test file(s), such as {unread[0]}," in warning


# ---------------------------------------------------------------------------
# The parse cache keys a reading by the syntax tree's libraries
# ---------------------------------------------------------------------------


# Verifies: REQ-d00331-A
def test_the_grammar_fingerprint_changes_with_the_reader_identity(monkeypatch):
    reader = FederatedIdReader(IdResolver(_id_config()))
    before = parse_cache.grammar_fingerprint(reader)

    monkeypatch.setattr(syntax_tree, "reader_identity", lambda: (("tree-sitter", "0.0.0-other"),))
    after = parse_cache.grammar_fingerprint(reader)

    assert before is not None and after is not None
    assert before != after
