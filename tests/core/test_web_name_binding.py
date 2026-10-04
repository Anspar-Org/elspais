"""A Dart test run in a browser binds its result by the test's full name.

A browser run records a line of the compiled JavaScript, which is no line of
the Dart source. The scan reads each test's full name from its literal
descriptions, the flutter-machine reader keeps only the suite file and the
name, and the builder binds the result to the one test carrying that name.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from elspais.graph.GraphNode import NodeKind
from elspais.graph.parsers.prescan import dart_test_names
from elspais.graph.parsers.results.flutter_machine import FlutterMachineParser
from elspais.graph.relations import EdgeKind


def _lines(src: str) -> list[tuple[int, str]]:
    return [(i + 1, t) for i, t in enumerate(src.split("\n"))]


# ---------------------------------------------------------------------------
# Test names from the scan
# ---------------------------------------------------------------------------


# Verifies: REQ-d00284-G+H
@pytest.mark.parametrize(
    "call,name",
    [
        pytest.param("test('plain', () {});", "plain", id="single-quoted"),
        pytest.param('test("double", () {});', "double", id="double-quoted"),
        pytest.param("test('a' \"b\" 'c', () {});", "abc", id="adjacent-literals"),
        pytest.param("test(r'raw $x \\n', () {});", "raw $x \\n", id="raw"),
        pytest.param(
            "test('esc \\' \\u0041 \\u{42} \\x43 \\$ \\t.', () {});",
            "esc ' A B C $ \t.",
            id="escapes",
        ),
        pytest.param("testWidgets('widget', (t) async {});", "widget", id="testWidgets"),
        pytest.param("test('has $count', () {});", None, id="interpolation"),
        pytest.param("test('has ${a.b}', () {});", None, id="braced-interpolation"),
        pytest.param("test(name, () {});", None, id="not-a-literal"),
        pytest.param("test('a' + name, () {});", None, id="concatenated-expression"),
    ],
)
def test_a_test_is_named_by_its_literal_description(call, name):
    names = dart_test_names(_lines(f"void main() {{\n  {call}\n}}\n"))

    assert names.get(2) == name


# Verifies: REQ-d00284-G
def test_adjacent_literals_join_across_lines():
    src = "void main() {\n  test(\n    'first '\n    \"second\",\n    () {},\n  );\n}\n"

    assert dart_test_names(_lines(src)) == {2: "first second"}


# Verifies: REQ-d00284-G
def test_a_triple_quoted_description_drops_its_blank_first_line():
    src = "void main() {\n  test('''\nspans\nlines''', () {});\n}\n"

    assert dart_test_names(_lines(src)) == {2: "spans\nlines"}


_NESTED = """\
void main() {
  group('outer', () {
    test('one', () {});
    group("inner", () {
      testWidgets('two', (t) async {});
    });
    group('of $kind', () {
      test('three', () {});
    });
    test('four', () {});
  });
  test('five', () {});
}
"""


# Verifies: REQ-d00284-G+H
def test_a_full_name_joins_the_enclosing_groups_and_the_test():
    names = dart_test_names(_lines(_NESTED))

    assert names == {
        3: "outer one",
        5: "outer inner two",
        # A group whose description interpolates leaves its tests unnamed.
        10: "outer four",
        12: "five",
    }


# ---------------------------------------------------------------------------
# What the flutter-machine reader keeps of a recorded location
# ---------------------------------------------------------------------------

_SUITE = "/abs/pkg/test/web/store_test.dart"


def _stream(test_fields: dict) -> str:
    test = {"id": 2, "name": "store keeps events", "suiteID": 1, **test_fields}
    return "\n".join(
        [
            json.dumps({"type": "suite", "suite": {"id": 1, "platform": "chrome", "path": _SUITE}}),
            json.dumps({"type": "testStart", "test": test}),
            json.dumps({"type": "testDone", "testID": 2, "result": "success", "hidden": False}),
        ]
    )


# Verifies: REQ-d00284-D
@pytest.mark.parametrize(
    "fields,source_path,line,root_path,root_line",
    [
        pytest.param(
            {
                "line": 4180,
                "url": "file:///abs/pkg/web/store_test.dart.js",
                "root_line": 4190,
                "root_url": "file:///abs/pkg/web/store_test.dart.js",
            },
            _SUITE,
            None,
            None,
            None,
            id="compiled-script",
        ),
        pytest.param(
            {"line": 4, "url": f"file://{_SUITE}"},
            _SUITE,
            4,
            None,
            None,
            id="dart-source",
        ),
        pytest.param(
            {
                "line": 174,
                "url": "package:flutter_test/src/widget_tester.dart",
                "root_line": 4,
                "root_url": f"file://{_SUITE}",
            },
            _SUITE,
            None,
            _SUITE,
            4,
            id="package-frame",
        ),
    ],
)
def test_only_a_dart_source_location_is_read_as_a_declaration(
    fields, source_path, line, root_path, root_line
):
    (record,) = FlutterMachineParser().parse(_stream(fields))

    assert record["source_path"] == source_path
    assert record["line"] == line
    assert record["root_path"] == root_path
    assert record["root_line"] == root_line
    assert record["name"] == "store keeps events"


# ---------------------------------------------------------------------------
# Binding a browser run's results by name
# ---------------------------------------------------------------------------

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
file_patterns = ["*.dart"]

[[scanning.test.targets]]
name = "web"
reporter = "flutter-machine"
results = "machine.jsonl"
match = "source"

[rules.format]
require_hash = false
require_assertions = false
require_status = false
"""

_SPEC = """\
# Requirements

---

### REQ-d00001: Store

**Level**: dev | **Status**: Active

## Assertions

A. The system SHALL keep events.

B. The system SHALL compact twice.

C. The system SHALL count events.

*End* *Store*
---
"""

_TEST_FILE = "test/web/store_test.dart"
_DART = """\
void main() {
  group('store', () {
    // Verifies: REQ-d00001-A
    test('keeps '
        'events', () {
      expect(1, 1);
    });
    // Verifies: REQ-d00001-B
    test('twice', () {
      expect(1, 1);
    });
    test('twice', () {
      expect(1, 1);
    });
    // Verifies: REQ-d00001-C
    test('counts $n', () {
      expect(1, 1);
    });
  });
}
"""
_KEEPS_LINE = 4
_DECOY_LINE = 9  # the first 'twice' test, on the JavaScript line of 'keeps events'


def _browser_run(root: Path) -> str:
    """Machine events of a browser run: every location is the compiled script."""
    script = f"file://{root / 'test/web/store_test.dart.js'}"
    events = [{"type": "suite", "suite": {"id": 1, "platform": "chrome", "path": _TEST_FILE}}]
    for test_id, name, js_line in [
        (2, "store keeps events", _DECOY_LINE),
        (3, "store twice", 20),
        (4, "store counts 3", 30),
    ]:
        events.append(
            {
                "type": "testStart",
                "test": {
                    "id": test_id,
                    "name": name,
                    "suiteID": 1,
                    "line": js_line,
                    "url": script,
                    "root_line": js_line,
                    "root_url": script,
                },
            }
        )
        events.append({"type": "testDone", "testID": test_id, "result": "success", "hidden": False})
    return "\n".join(json.dumps(e) for e in events) + "\n"


@pytest.fixture(scope="module")
def browser_run(tmp_path_factory):
    from elspais.graph.factory import build_graph

    root = tmp_path_factory.mktemp("web") / "proj"
    for rel, text in {
        ".elspais.toml": _CONFIG,
        "spec/requirements.md": _SPEC,
        _TEST_FILE: _DART,
    }.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    out = root / ".results" / "web"
    out.mkdir(parents=True)
    (out / "machine.jsonl").write_text(_browser_run(root), encoding="utf-8")
    graph = build_graph(repo_root=root)
    (entry,) = list(graph.iter_repos())
    return graph, entry.config


def _result_named(graph, name: str):
    (node,) = [r for r in graph.iter_by_kind(NodeKind.RESULT) if r.get_field("name") == name]
    return node


def _tests_yielding(result) -> list:
    return list(result.iter_parents(edge_kinds={EdgeKind.YIELDS}))


def _test_at(graph, line: int):
    (node,) = [
        t
        for t in graph.iter_by_kind(NodeKind.TEST)
        if t.get_field("parse_line") == line
        and t.file_node() is not None
        and t.file_node().get_field("relative_path") == _TEST_FILE
    ]
    return node


# Verifies: REQ-d00284-G+H
def test_each_test_node_carries_its_full_name(browser_run):
    graph, _config = browser_run

    assert _test_at(graph, _KEEPS_LINE).get_field("test_name") == "store keeps events"
    # A test no citation names carries its name too.
    assert _test_at(graph, 12).get_field("test_name") == "store twice"
    assert _test_at(graph, 16).get_field("test_name") is None


# Verifies: REQ-d00284-D+E
def test_a_browser_result_binds_to_the_test_its_full_name_names(browser_run):
    graph, _config = browser_run
    result = _result_named(graph, "store keeps events")

    assert result.get_field("line") is None
    assert result.get_field("source_file") == _TEST_FILE
    assert result.get_field("match_scope") == "test"
    assert [t.get_field("parse_line") for t in _tests_yielding(result)] == [_KEEPS_LINE]


# Verifies: REQ-d00284-D
def test_a_javascript_line_never_binds_to_the_dart_test_on_that_line(browser_run):
    graph, _config = browser_run
    decoy = _test_at(graph, _DECOY_LINE)

    assert _result_named(graph, "store keeps events") not in list(
        decoy.iter_children(edge_kinds={EdgeKind.YIELDS})
    )


# Verifies: REQ-d00284-B+C
@pytest.mark.parametrize(
    "name,match,candidates",
    [
        pytest.param("store twice", "ambiguous", 2, id="duplicate-name"),
        pytest.param("store counts 3", "unmatched", 0, id="interpolated-name"),
    ],
)
def test_a_name_naming_no_single_test_credits_nothing(browser_run, name, match, candidates):
    graph, _config = browser_run
    result = _result_named(graph, name)

    assert result.get_field("match_scope") == "file"
    assert result.get_field("name_match") == match
    assert len(result.get_field("name_candidates")) == candidates


# Verifies: REQ-d00284-C
def test_the_report_says_what_each_name_picked_out(browser_run):
    from elspais.commands.health import check_file_bound_results

    graph, config = browser_run
    check = check_file_bound_results(graph, config)

    assert check.passed is False
    (finding,) = check.findings
    assert "by name, 1 matched no test and 1 matched more than one" in finding.message


def _project(root: Path, dart: str = _DART) -> Path:
    """Write the project with ``dart`` as its test file; return its results folder."""
    for rel, text in {
        ".elspais.toml": _CONFIG,
        "spec/requirements.md": _SPEC,
        _TEST_FILE: dart,
    }.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    out = root / ".results" / "web"
    out.mkdir(parents=True)
    return out


# Verifies: REQ-d00284-C+H
def test_a_name_is_reported_unmatched_where_no_test_in_the_file_has_a_full_name(tmp_path):
    from elspais.commands.health import check_file_bound_results
    from elspais.graph.factory import build_graph

    root = tmp_path / "proj"
    out = _project(
        root,
        "void main() {\n  // Verifies: REQ-d00001-A\n  test('keeps $n', () {});\n}\n",
    )
    script = f"file://{root / 'test/web/store_test.dart.js'}"
    events = [
        {"type": "suite", "suite": {"id": 1, "platform": "chrome", "path": _TEST_FILE}},
        {
            "type": "testStart",
            "test": {"id": 2, "name": "keeps 3", "suiteID": 1, "line": 3, "url": script},
        },
        {"type": "testDone", "testID": 2, "result": "success", "hidden": False},
    ]
    (out / "machine.jsonl").write_text(
        "\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8"
    )
    graph = build_graph(repo_root=root)
    result = _result_named(graph, "keeps 3")

    assert result.get_field("match_scope") == "file"
    assert result.get_field("name_match") == "unmatched"
    (entry,) = list(graph.iter_repos())
    (finding,) = check_file_bound_results(graph, entry.config).findings
    assert "by name, 1 matched no test" in finding.message


# Verifies: REQ-d00284-F
def test_a_recorded_dart_line_binds_by_line_and_not_by_name(tmp_path):
    from elspais.graph.factory import build_graph

    root = tmp_path / "proj"
    out = _project(root)
    events = [
        {"type": "suite", "suite": {"id": 1, "platform": "vm", "path": _TEST_FILE}},
        {
            "type": "testStart",
            "test": {
                "id": 2,
                "name": "store keeps events",
                "suiteID": 1,
                "line": _DECOY_LINE,
                "url": f"file://{root / _TEST_FILE}",
            },
        },
        {"type": "testDone", "testID": 2, "result": "success", "hidden": False},
    ]
    (out / "machine.jsonl").write_text(
        "\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8"
    )
    graph = build_graph(repo_root=root)
    result = _result_named(graph, "store keeps events")

    assert result.get_field("match_scope") == "test"
    assert [t.get_field("parse_line") for t in _tests_yielding(result)] == [_DECOY_LINE]
