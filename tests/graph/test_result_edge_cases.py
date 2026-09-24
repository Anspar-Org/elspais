# Verifies: REQ-d00294-A, REQ-d00294-B, REQ-d00294-C, REQ-d00294-D, REQ-d00294-E
"""Edge cases of holding every result a test recorded, built from files on disk.

Each test here builds a real project -- spec, scanned tests, a target and the
artifact a real producer writes -- and reads what the built graph says. The
producers differ in where they write a test's location, how they number it,
what they do when a run is cut short, and what directory their paths are
relative to, and each of those is a way for a record to reach the wrong test
or no test at all. The rule every case is held to is REQ-d00294-E: a test
reads as failing where one of ITS OWN results failed, and nowhere else.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from elspais.commands.health import check_test_results, check_unmatched_results
from elspais.graph.aggregation import EvidenceResult, _evidence_result
from elspais.graph.GraphNode import NodeKind
from elspais.graph.relations import EdgeKind

_SPEC = """\
### REQ-p00001: Login

**Level**: PRD | **Status**: Active

The system SHALL let a user log in.

#### Assertions

A. The system SHALL accept valid credentials.

B. The system SHALL reject invalid credentials.

*End* *Login* | **Hash**: ________
"""

_CONFIG_HEAD = """\
version = 5

[project]
name = "edges"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]

[scanning.test]
enabled = true
directories = {directories}
file_patterns = {patterns}
"""

# Two tests in one Python file, each naming its own assertion. The second
# `def` sits on line 7 (1-based), the first on line 2.
_PY_TWO_TESTS = """\
# Verifies: REQ-p00001-A
def test_logs_in():
    pass


# Verifies: REQ-p00001-B
def test_rejects():
    pass
"""

# Two Dart tests in two groups; group A's tearDownAll throws. `a1` is declared
# on line 6 and `b1` on line 12.
_DART_TWO_GROUPS = """\
void main() {
  group('A', () {
    setUpAll(() {});
    tearDownAll(() { throw 'boom'; });
    // Verifies: REQ-p00001-A
    test('a1', () {
      expect(1, 1);
    });
  });
  group('B', () {
    // Verifies: REQ-p00001-B
    test('b1', () {
      expect(2, 2);
    });
  });
}
"""

# Two Dart tests with no groups: `a1` is declared on line 3 and `b1` on line 8.
_DART_TWO_TESTS = """\
void main() {
  // Verifies: REQ-p00001-A
  test('a1', () {
    expect(1, 2);
  });

  // Verifies: REQ-p00001-B
  test('b1', () {
    expect(2, 2);
  });
}
"""


def _project(
    tmp_path: Path,
    *,
    files: dict[str, str],
    targets: str,
    directories: tuple[str, ...] = ("tests",),
    patterns: tuple[str, ...] = ("test_*.py",),
) -> Path:
    """An on-disk project: one requirement, the given files, the given targets."""
    project = tmp_path / "project"
    (project / "spec").mkdir(parents=True)
    (project / "spec" / "reqs.md").write_text(_SPEC, encoding="utf-8")
    for relative, text in files.items():
        path = project / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    head = _CONFIG_HEAD.format(
        directories=json.dumps(list(directories)), patterns=json.dumps(list(patterns))
    )
    (project / ".elspais.toml").write_text(head + "\n" + targets, encoding="utf-8")
    return project


def _build(project: Path, **kwargs):
    from elspais.graph.factory import build_graph

    return build_graph(
        config_path=project / ".elspais.toml", repo_root=project, scan_code=False, **kwargs
    )


def _results(graph) -> list:
    return sorted(graph.iter_by_kind(NodeKind.RESULT), key=lambda n: n.id)


def _test(graph, suffix: str):
    """The scanned TEST node whose id ends with *suffix*."""
    found = [n for n in graph.iter_by_kind(NodeKind.TEST) if n.id.endswith(suffix)]
    assert len(found) == 1, f"expected one TEST ending {suffix!r}, got {[n.id for n in found]}"
    return found[0]


def _own_results(test_node) -> list:
    return sorted(
        (c for c in test_node.iter_children() if c.kind is NodeKind.RESULT), key=lambda n: n.id
    )


def _holders(result) -> list[str]:
    return sorted(p.id for p in result.iter_parents(edge_kinds={EdgeKind.YIELDS}))


def _verdict(graph, test_node) -> EvidenceResult:
    return _evidence_result(graph, (test_node.id,))[0]


def _metrics(graph):
    return graph.find_by_id("REQ-p00001").get_metric("rollup_metrics")


# ---------------------------------------------------------------------------
# flutter --machine event streams, spelled as package:test writes them
# ---------------------------------------------------------------------------


def _jsonl(*events: dict) -> str:
    return "".join(json.dumps(e) + "\n" for e in events)


def _suite(path: str) -> dict:
    return {"type": "suite", "suite": {"id": 0, "platform": "vm", "path": path}}


def _start(tid: int, name: str, line: int | None) -> dict:
    return {
        "type": "testStart",
        "test": {
            "id": tid,
            "name": name,
            "suiteID": 0,
            "groupIDs": [],
            "metadata": {"skip": False, "skipReason": None},
            "line": line,
            "column": 5 if line else None,
            "url": None,
        },
    }


def _done(tid: int, result: str = "success", *, hidden: bool = False) -> dict:
    return {
        "type": "testDone",
        "testID": tid,
        "result": result,
        "skipped": False,
        "hidden": hidden,
    }


def _error(tid: int, text: str) -> dict:
    return {"type": "error", "testID": tid, "error": text, "stackTrace": "", "isFailure": False}


def _end(success: bool) -> dict:
    return {"type": "done", "success": success}


_FLUTTER_TARGET = """\
[[scanning.test.targets]]
name = "{name}"
reporter = "flutter-machine"
match = "source"
command = "flutter test --machine"
{extra}"""


def _flutter_project(tmp_path: Path, dart: str, *, results: str | None, stream: str | None):
    extra = f'results = "{results}"\n' if results else ""
    files = {"test/login_test.dart": dart}
    if results and stream is not None:
        files[results] = stream
    return _project(
        tmp_path,
        files=files,
        targets=_FLUTTER_TARGET.format(name="widgets", extra=extra),
        directories=("test",),
        patterns=("*_test.dart",),
    )


# ===========================================================================
# E -- a record that names no one test is held by none of them
# ===========================================================================


_JUNIT_FILE_NO_LINE = """\
<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="e2e" tests="2" failures="1">
    <testcase classname="login" name="logs in" file="tests/test_login.py" time="0.1">
      <failure message="boom"/>
    </testcase>
    <testcase classname="login" name="rejects" file="tests/test_login.py" time="0.1"/>
  </testsuite>
</testsuites>
"""


# Verifies: REQ-d00294-E
def test_a_record_naming_only_its_file_fails_no_test_in_it(tmp_path):
    """A record carrying a file and no line is not a result of every test there.

    `logs in` failed and `rejects` passed, but neither record says which test
    it is. Handing both records to both tests would make `rejects` read as
    failing on the strength of a sibling's failure.
    """
    project = _project(
        tmp_path,
        files={"tests/test_login.py": _PY_TWO_TESTS, "results/junit.xml": _JUNIT_FILE_NO_LINE},
        targets=(
            '[[scanning.test.targets]]\nname = "e2e"\nreporter = "junit"\n'
            'results = "results/junit.xml"\nmatch = "source"\n'
        ),
    )
    graph = _build(project)

    logs_in = _test(graph, "::test_logs_in")
    rejects = _test(graph, "::test_rejects")
    assert _own_results(logs_in) == []
    assert _own_results(rejects) == []
    assert _verdict(graph, rejects) is EvidenceResult.NONE
    assert _verdict(graph, logs_in) is EvidenceResult.NONE
    assert _metrics(graph).verified.failing_labels == set()


# Verifies: REQ-d00294-E
def test_a_record_naming_only_its_file_is_reported_as_unmatched(tmp_path):
    """The record binds nowhere, and the report says why."""
    project = _project(
        tmp_path,
        files={"tests/test_login.py": _PY_TWO_TESTS, "results/junit.xml": _JUNIT_FILE_NO_LINE},
        targets=(
            '[[scanning.test.targets]]\nname = "e2e"\nreporter = "junit"\n'
            'results = "results/junit.xml"\nmatch = "source"\n'
        ),
    )
    graph = _build(project)

    check = check_unmatched_results(graph)

    assert check.passed is False
    assert len(check.findings) == 2
    assert all("recorded no line" in f.message for f in check.findings)
    assert all("2 test(s) in tests/test_login.py" in f.message for f in check.findings)


# Verifies: REQ-d00294-E
@pytest.mark.parametrize(
    "line_attr,holder",
    [('line="1"', "::test_logs_in"), ('line="6"', "::test_rejects")],
    ids=["first-test", "second-test"],
)
def test_a_record_naming_its_line_fails_only_its_own_test(tmp_path, line_attr, holder):
    """With a line, the failing record reaches the one test it names and no other."""
    junit = (
        '<?xml version="1.0" encoding="utf-8"?>\n<testsuites>\n'
        '  <testsuite name="e2e" tests="1" failures="1">\n'
        f'    <testcase classname="login" name="x" file="tests/test_login.py" {line_attr}>'
        '<failure message="boom"/></testcase>\n'
        "  </testsuite>\n</testsuites>\n"
    )
    project = _project(
        tmp_path,
        files={"tests/test_login.py": _PY_TWO_TESTS, "results/junit.xml": junit},
        targets=(
            '[[scanning.test.targets]]\nname = "e2e"\nreporter = "junit"\n'
            'results = "results/junit.xml"\nmatch = "source"\n'
        ),
    )
    graph = _build(project)

    (result,) = _results(graph)
    assert _holders(result) == [_test(graph, holder).id]
    other = "::test_rejects" if holder == "::test_logs_in" else "::test_logs_in"
    assert _verdict(graph, _test(graph, holder)) is EvidenceResult.FAILED
    assert _verdict(graph, _test(graph, other)) is EvidenceResult.NONE


# ===========================================================================
# E -- a package:test hook failure is not a failure of the tests that passed
# ===========================================================================


def _hook_stream(project_dir: Path, hook: str) -> str:
    path = str(project_dir / "test" / "login_test.dart")
    events = [
        {"type": "start", "protocolVersion": "0.1.1"},
        _suite(path),
        _start(1, f"loading {path}", None),
        _done(1, hidden=True),
    ]
    if hook == "tearDownAll":
        events += [
            _start(4, "A a1", 6),
            _done(4),
            _start(5, "A (tearDownAll)", None),
            _error(5, "boom"),
            _done(5, "error"),
        ]
    else:  # setUpAll throws: a1 never runs, the pseudo-test sits at the hook's line
        events += [
            _start(5, "A (setUpAll)", 3),
            _error(5, "boom"),
            _done(5, "error"),
        ]
    events += [_start(7, "B b1", 12), _done(7), _end(False)]
    return _jsonl(*events)


# Verifies: REQ-d00294-E
@pytest.mark.parametrize("hook", ["tearDownAll", "setUpAll"])
def test_a_failing_group_hook_fails_no_test_that_passed(tmp_path, hook):
    """The hook's pseudo-test names no test, so no test holds its failure.

    `b1` passed its own record and reads as passing. Under a throwing
    `setUpAll`, `a1` never ran and has no result of its own, so it is
    awaiting one -- not failing on the strength of the hook's record.
    """
    project = _flutter_project(
        tmp_path, _DART_TWO_GROUPS, results="coverage/machine.jsonl", stream=None
    )
    (project / "coverage").mkdir()
    (project / "coverage" / "machine.jsonl").write_text(
        _hook_stream(project, hook), encoding="utf-8"
    )
    graph = _build(project)

    a1 = _test(graph, ":6")
    b1 = _test(graph, ":12")
    assert _verdict(graph, b1) is EvidenceResult.PASSED
    expected_a1 = EvidenceResult.PASSED if hook == "tearDownAll" else EvidenceResult.NONE
    assert _verdict(graph, a1) is expected_a1
    assert _metrics(graph).verified.failing_labels == set()

    # The hook's failure is still a failed result, reported where results are.
    pseudo = [r for r in _results(graph) if "(" in (r.get_field("name") or "")]
    assert len(pseudo) == 1
    assert pseudo[0].get_field("status") == "failed"
    assert _holders(pseudo[0]) == []
    assert check_test_results(graph, config=None).details["failed"] == 1


_DART_ONE_TEST_WITH_HOOK = """\
void main() {
  tearDownAll(() { throw 'boom'; });
  // Verifies: REQ-p00001-A
  test('a1', () {
    expect(1, 1);
  });
}
"""


# Verifies: REQ-d00284-B, REQ-d00294-E
def test_a_hook_in_a_one_test_file_is_not_that_tests_result(tmp_path):
    """A line-less pseudo-test beside the one test of its file names no test.

    The file holds one scanned test, and its records name two -- the test
    and the runner's `(tearDownAll)`. The line-less one's name is not the
    title the test declares, so it binds nowhere, leaving the test's own
    pass alone.
    """
    project = _flutter_project(
        tmp_path, _DART_ONE_TEST_WITH_HOOK, results="coverage/machine.jsonl", stream=None
    )
    path = str(project / "test" / "login_test.dart")
    stream = _jsonl(
        _suite(path),
        _start(4, "a1", 4),
        _done(4),
        _start(5, "(tearDownAll)", None),
        _error(5, "boom"),
        _done(5, "error"),
        _end(False),
    )
    (project / "coverage").mkdir()
    (project / "coverage" / "machine.jsonl").write_text(stream, encoding="utf-8")
    graph = _build(project)

    a1 = _test(graph, ":4")
    assert _verdict(graph, a1) is EvidenceResult.PASSED
    (pseudo,) = [r for r in _results(graph) if r.get_field("name") == "(tearDownAll)"]
    assert _holders(pseudo) == []
    assert "'(tearDownAll)' does not name" in pseudo.get_field("unbound_reason")


# ===========================================================================
# E -- package:test's own error events decide a test's verdict
# ===========================================================================


# Verifies: REQ-d00294-E
def test_an_error_after_a_test_finished_fails_that_test(tmp_path):
    """A late async error fails the test the runner blames, and says why."""
    project = _flutter_project(tmp_path, _DART_TWO_TESTS, results=None, stream=None)
    path = str(project / "test" / "login_test.dart")
    stream = _jsonl(
        _suite(path),
        _start(4, "a1", 3),
        _done(4),
        _error(4, "This test failed after it had already completed.\nlate"),
        _start(5, "b1", 8),
        _done(5),
        _end(False),
    )
    graph = _build(project, captured_results={"widgets": stream})

    a1 = _test(graph, ":3")
    (own,) = _own_results(a1)
    assert own.get_field("status") == "failed"
    assert "late" in (own.get_field("message") or "")
    assert _verdict(graph, a1) is EvidenceResult.FAILED
    assert _verdict(graph, _test(graph, ":8")) is EvidenceResult.PASSED
    assert _metrics(graph).verified.failing_labels == {"A"}


# Verifies: REQ-d00294-E
def test_an_error_before_a_test_finished_is_its_failure_message(tmp_path):
    """An error reported before testDone becomes the failing record's message."""
    from elspais.graph.parsers.results.flutter_machine import FlutterMachineParser

    stream = _jsonl(
        _suite("test/login_test.dart"),
        _start(4, "a1", 3),
        _error(4, "Expected: <2> Actual: <1>"),
        _done(4, "failure"),
        _end(False),
    )
    parser = FlutterMachineParser()

    (record,) = parser.parse(stream, "")

    assert record["status"] == "failed"
    assert "Expected: <2>" in record["message"]
    assert list(parser.iter_diagnostics()) == []


# Verifies: REQ-d00294-E
def test_a_run_the_runner_failed_with_no_failing_record_is_reported():
    """`done` with success=false and every record passing is not all-passing."""
    from elspais.graph.parsers.results.flutter_machine import FlutterMachineParser

    stream = _jsonl(_suite("test/login_test.dart"), _start(4, "a1", 3), _done(4), _end(False))
    parser = FlutterMachineParser()

    (record,) = parser.parse(stream, "")

    assert record["status"] == "passed"
    (diagnostic,) = list(parser.iter_diagnostics())
    assert "success=false" in diagnostic.cause


# ===========================================================================
# E -- a stream cut short does not lose the test it was running
# ===========================================================================


# Verifies: REQ-d00294-E
@pytest.mark.parametrize("channel", ["artifact", "captured"])
def test_a_test_started_and_never_finished_reads_as_failing(tmp_path, channel):
    """A crashed or killed run leaves a started test failing, and says so.

    Read as it stands the test would vanish, and a crashed run would look
    exactly like a test nobody selected.
    """
    results = "coverage/machine.jsonl" if channel == "artifact" else None
    project = _flutter_project(tmp_path, _DART_TWO_TESTS, results=results, stream=None)
    path = str(project / "test" / "login_test.dart")
    stream = _jsonl(_suite(path), _start(2, "a1", 3), _start(3, "b1", 8), _done(3))
    kwargs = {}
    if channel == "artifact":
        (project / "coverage").mkdir()
        (project / "coverage" / "machine.jsonl").write_text(stream, encoding="utf-8")
    else:
        kwargs["captured_results"] = {"widgets": stream}
    graph = _build(project, **kwargs)

    a1 = _test(graph, ":3")
    (own,) = _own_results(a1)
    assert own.get_field("status") == "failed"
    assert "never finished" in own.get_field("message")
    assert _verdict(graph, a1) is EvidenceResult.FAILED
    assert _verdict(graph, _test(graph, ":8")) is EvidenceResult.PASSED

    faults = graph.ingestion_faults()
    assert len(faults) == 1
    assert "'done'" in faults[0].cause
    assert "'a1'" in faults[0].cause
    assert faults[0].partial is True


# Verifies: REQ-d00294-E
def test_a_stream_with_no_test_finished_is_not_a_partial_read():
    """Nothing finished, so nothing was read in part: the read yielded nothing whole."""
    from elspais.graph.parsers.results.flutter_machine import FlutterMachineParser

    parser = FlutterMachineParser()
    records = parser.parse(_jsonl(_suite("t.dart"), _start(2, "a1", 3)), "")

    assert [r["status"] for r in records] == ["failed"]
    (diagnostic,) = list(parser.iter_diagnostics())
    assert diagnostic.partial is False


# Verifies: REQ-d00294-A, REQ-d00294-E
def test_each_run_in_one_stream_reads_its_own_identifiers():
    """Two runs written one after another number their tests from 1 again.

    An error the second run reports for its test 1 belongs to that run's
    test, never to the first run's test that happened to carry the same
    number, and the first run's `done` does not vouch for the second.
    """
    from elspais.graph.parsers.results.flutter_machine import FlutterMachineParser

    begin = {"type": "start", "protocolVersion": "0.1.1", "runnerVersion": None}
    first = _jsonl(begin, _suite("a_test.dart"), _start(1, "a", 3), _done(1), _end(True))
    second = _jsonl(
        begin,
        _suite("b_test.dart"),
        _start(1, "b", 5),
        {"type": "error", "testID": 1, "error": "boom in b", "stackTrace": "", "isFailure": True},
        _done(1, "failure"),
        _end(False),
    )
    parser = FlutterMachineParser()

    records = parser.parse(first + second, "")

    assert [(r["name"], r["status"], r["message"]) for r in records] == [
        ("a", "passed", None),
        ("b", "failed", "boom in b"),
    ]
    assert [r["source_path"] for r in records] == ["a_test.dart", "b_test.dart"]
    assert list(parser.iter_diagnostics()) == []


# Verifies: REQ-d00294-E
def test_a_later_run_cut_short_is_reported_despite_an_earlier_done():
    from elspais.graph.parsers.results.flutter_machine import FlutterMachineParser

    begin = {"type": "start", "protocolVersion": "0.1.1", "runnerVersion": None}
    stream = _jsonl(begin, _suite("a_test.dart"), _start(1, "a", 3), _done(1), _end(True)) + _jsonl(
        begin, _suite("b_test.dart"), _start(1, "b", 5)
    )
    parser = FlutterMachineParser()

    records = parser.parse(stream, "")

    assert [(r["name"], r["status"]) for r in records] == [("a", "passed"), ("b", "failed")]
    (diagnostic,) = list(parser.iter_diagnostics())
    assert "'done'" in diagnostic.cause
    assert "'b'" in diagnostic.cause
    assert diagnostic.partial is True


# Verifies: REQ-d00294-A
def test_a_complete_stream_reads_as_it_always_has():
    """A stream ending in `done` with every test finished raises nothing."""
    from elspais.graph.parsers.results.flutter_machine import FlutterMachineParser

    parser = FlutterMachineParser()
    records = parser.parse(
        _jsonl(
            _suite("t.dart"),
            _start(1, "loading t.dart", None),
            _done(1, hidden=True),
            _start(2, "a1", 3),
            _done(2),
            _start(3, "b1", 8),
            _done(3, "failure"),
            _end(False),
        ),
        "",
    )

    assert [(r["name"], r["status"]) for r in records] == [("a1", "passed"), ("b1", "failed")]
    assert list(parser.iter_diagnostics()) == []


# ===========================================================================
# A -- a saved stream points a reader at the record that failed
# ===========================================================================


# Verifies: REQ-d00294-A
def test_a_saved_stream_records_the_line_of_each_testdone():
    from elspais.graph.parsers.results.flutter_machine import FlutterMachineParser

    noise = "".join(f"print line {i}\n" for i in range(50))
    stream = (
        _jsonl(_suite("t.dart"), _start(2, "a1", 3))
        + noise
        + _jsonl(_done(2, "failure"), _end(False))
    )
    failing_line = stream.splitlines().index(json.dumps(_done(2, "failure"))) + 1

    (saved,) = FlutterMachineParser().parse(stream, "coverage/machine.jsonl")
    (live,) = FlutterMachineParser().parse(stream, "")

    assert saved["result_line"] == failing_line == 53
    assert live["result_line"] is None


# ===========================================================================
# A+B -- one run names its results by where they were recorded, whichever
# channel this invocation also captured
# ===========================================================================


# Verifies: REQ-d00294-A, REQ-d00294-B
@pytest.mark.parametrize(
    "captured,written,expected_place",
    [
        (True, True, "coverage/machine.jsonl"),
        (False, True, "coverage/machine.jsonl"),
        (True, False, "widgets/"),
    ],
    ids=["both-channels", "artifact-only", "stdout-only"],
)
def test_a_run_places_its_results_by_the_artifact_it_wrote(
    tmp_path, captured, written, expected_place
):
    """The declared artifact is the place of record wherever the run wrote one.

    A run that wrote its report and streamed its output recorded each result
    once. Which channel this invocation happened to read must not change what
    the result is called; only where no artifact exists is the target the place.
    """
    project = _flutter_project(
        tmp_path, _DART_TWO_TESTS, results="coverage/machine.jsonl", stream=None
    )
    path = str(project / "test" / "login_test.dart")
    stream = _jsonl(_suite(path), _start(2, "a1", 3), _done(2, "failure"), _end(False))
    if written:
        (project / "coverage").mkdir()
        (project / "coverage" / "machine.jsonl").write_text(stream, encoding="utf-8")
    # The run began before it wrote its artifact.
    kwargs = (
        {"captured_results": {"widgets": stream}, "run_started_at": time.time() - 60}
        if captured
        else {}
    )

    graph = _build(project, **kwargs)

    (result,) = _results(graph)
    assert result.id == f"result:REQ:{expected_place}:1"
    result_files = [
        n.id for n in graph.iter_by_kind(NodeKind.FILE) if n.id.endswith("machine.jsonl")
    ]
    assert result_files == (["file:REQ:coverage/machine.jsonl"] if written else [])
    assert _holders(result) == [_test(graph, ":3").id]


# Verifies: REQ-d00294-A, REQ-d00294-B, REQ-d00294-E
@pytest.mark.parametrize("run_started", ["after-artifact", "unknown"])
def test_an_artifact_older_than_the_run_does_not_hide_the_runs_failure(tmp_path, run_started):
    """An earlier run's passing report is not this run's verdict.

    A run that died before its file reporter opened -- a failed dependency
    resolution, a tool that was not found -- leaves the last run's report in
    place while its own output says the test failed. The output this run
    captured is its record; the report that predates it, or that nothing
    shows the run wrote, is not.
    """
    project = _flutter_project(
        tmp_path, _DART_TWO_TESTS, results="coverage/machine.jsonl", stream=None
    )
    path = str(project / "test" / "login_test.dart")
    earlier = _jsonl(_suite(path), _start(2, "a1", 3), _done(2), _end(True))
    now = _jsonl(_suite(path), _start(2, "a1", 3), _done(2, "failure"), _end(False))
    (project / "coverage").mkdir()
    artifact = project / "coverage" / "machine.jsonl"
    artifact.write_text(earlier, encoding="utf-8")
    written = time.time() - 3600
    os.utime(artifact, (written, written))
    kwargs = {"captured_results": {"widgets": now}}
    if run_started == "after-artifact":
        kwargs["run_started_at"] = written + 60

    graph = _build(project, **kwargs)

    (result,) = _results(graph)
    assert result.id == "result:REQ:widgets/:1"
    assert result.get_field("status") == "failed"
    assert _verdict(graph, _test(graph, ":3")) is EvidenceResult.FAILED


# Verifies: REQ-d00294-A, REQ-d00294-B, REQ-d00294-E
def test_captured_targets_sharing_an_artifact_each_read_their_own_output(tmp_path):
    """An artifact two captured targets both declare is neither one's record.

    Whichever target ran last left the file, and nothing on it says which.
    Read as each target's record it would hand every target the last one's
    verdicts and discard the rest -- here the first target's failure -- so
    each reads the output it captured itself.
    """
    targets = (
        _FLUTTER_TARGET.format(name="unit", extra='results = "coverage/machine.jsonl"\n')
        + "\n"
        + _FLUTTER_TARGET.format(name="golden", extra='results = "coverage/machine.jsonl"\n')
    )
    project = _project(
        tmp_path,
        files={"test/login_test.dart": _DART_TWO_TESTS},
        targets=targets,
        directories=("test",),
        patterns=("*_test.dart",),
    )
    path = str(project / "test" / "login_test.dart")
    unit = _jsonl(_suite(path), _start(2, "a1", 3), _done(2, "failure"), _end(False))
    golden = _jsonl(_suite(path), _start(2, "b1", 8), _done(2), _end(True))
    # `golden` ran last and overwrote the shared artifact.
    (project / "coverage").mkdir()
    (project / "coverage" / "machine.jsonl").write_text(golden, encoding="utf-8")

    graph = _build(
        project,
        captured_results={"unit": unit, "golden": golden},
        run_started_at=time.time() - 60,
    )

    assert sorted(r.id for r in _results(graph)) == [
        "result:REQ:golden/:1",
        "result:REQ:unit/:1",
    ]
    assert _verdict(graph, _test(graph, ":3")) is EvidenceResult.FAILED
    assert _verdict(graph, _test(graph, ":8")) is EvidenceResult.PASSED


# Verifies: REQ-d00294-A, REQ-d00294-E
@pytest.mark.parametrize("ran", [True, False], ids=["one-ran", "none-ran"])
def test_a_target_that_did_not_run_reads_no_shared_artifact(tmp_path, ran):
    """An artifact another target also declares is not a stale target's record.

    `unit` and `golden` both write `coverage/machine.jsonl`. Where only
    `unit` ran, the file holds `unit`'s fresh failure: it is `unit`'s result,
    and `golden`, which did not run, holds nothing from it. Where neither
    ran, nothing says which wrote it, so neither reads it and each is told why.
    """
    from elspais.commands.health import check_ingestion_faults

    targets = (
        _FLUTTER_TARGET.format(name="unit", extra='results = "coverage/machine.jsonl"\n')
        + "\n"
        + _FLUTTER_TARGET.format(name="golden", extra='results = "coverage/machine.jsonl"\n')
    )
    project = _project(
        tmp_path,
        files={"test/login_test.dart": _DART_TWO_TESTS},
        targets=targets,
        directories=("test",),
        patterns=("*_test.dart",),
    )
    path = str(project / "test" / "login_test.dart")
    unit = _jsonl(_suite(path), _start(2, "a1", 3), _done(2, "failure"), _end(False))
    (project / "coverage").mkdir()
    (project / "coverage" / "machine.jsonl").write_text(unit, encoding="utf-8")
    run = (
        {
            "captured_results": {"unit": unit},
            "fresh_targets": {"unit"},
            "run_started_at": time.time() - 60,
        }
        if ran
        else {}
    )

    graph = _build(project, **run)

    results = _results(graph)
    faults = [f.message for f in check_ingestion_faults(graph).findings]
    if ran:
        (result,) = results
        assert result.get_field("target") == "unit"
        assert result.get_field("carried") is False
        assert _verdict(graph, _test(graph, ":3")) is EvidenceResult.FAILED
        assert len(faults) == 1 and "golden" in faults[0] and "'unit'" in faults[0]
    else:
        assert results == []
        assert len(faults) == 2


# ===========================================================================
# E -- a producer's relative path is read against the directory it ran in
# ===========================================================================


def _pkg_stream(suite_path: str, *, fail: str) -> str:
    return _jsonl(
        _suite(suite_path),
        _start(2, "a1", 3),
        _done(2, "failure" if fail == "a1" else "success"),
        _start(3, "b1", 8),
        _done(3, "failure" if fail == "b1" else "success"),
        _end(False),
    )


# Verifies: REQ-d00294-E
def test_a_package_relative_suite_path_binds_in_the_targets_package(tmp_path):
    """`dart test` writes suite.path relative to its package; each package keeps its own.

    Two packages hold a test file of the same name, and a copy sits at the
    repository root too. Each package's results reach its own tests, and
    the root copy receives none of them.
    """
    targets = "".join(
        f'[[scanning.test.targets]]\nname = "{pkg}"\ncwd = "{pkg}"\n'
        'reporter = "flutter-machine"\nmatch = "source"\n'
        'results = "coverage/machine.jsonl"\n\n'
        for pkg in ("pkg1", "pkg2")
    )
    project = _project(
        tmp_path,
        files={
            "pkg1/test/login_test.dart": _DART_TWO_TESTS,
            "pkg2/test/login_test.dart": _DART_TWO_TESTS,
            "test/login_test.dart": _DART_TWO_TESTS,
            "pkg1/coverage/machine.jsonl": _pkg_stream("test/login_test.dart", fail="a1"),
            "pkg2/coverage/machine.jsonl": _pkg_stream("test/login_test.dart", fail="b1"),
        },
        targets=targets,
        directories=("test", "pkg1/test", "pkg2/test"),
        patterns=("*_test.dart",),
    )
    graph = _build(project)

    def verdict(rel: str, line: int) -> EvidenceResult:
        return _verdict(graph, _test(graph, f"{rel}:{line}"))

    assert verdict("pkg1/test/login_test.dart", 3) is EvidenceResult.FAILED
    assert verdict("pkg1/test/login_test.dart", 8) is EvidenceResult.PASSED
    assert verdict("pkg2/test/login_test.dart", 3) is EvidenceResult.PASSED
    assert verdict("pkg2/test/login_test.dart", 8) is EvidenceResult.FAILED
    root_tests = [
        n
        for n in graph.iter_by_kind(NodeKind.TEST)
        if "/pkg1/" not in n.id and "/pkg2/" not in n.id
    ]
    assert len(root_tests) == 2
    assert all(_own_results(t) == [] for t in root_tests)
    assert check_unmatched_results(graph).passed is True


_PY_PARAM_TEST = """\
# Verifies: REQ-p00001-A
def test_logs_in():
    pass
"""


# Verifies: REQ-d00294-E
@pytest.mark.parametrize(
    "reporter,results,artifact",
    [
        (
            "junit",
            "junit.xml",
            '<?xml version="1.0" encoding="utf-8"?>\n<testsuites><testsuite name="pytest">\n'
            '<testcase classname="tests.test_login" name="test_logs_in" '
            'file="tests/test_login.py" line="1"><failure message="boom"/></testcase>\n'
            "</testsuite></testsuites>\n",
        ),
        (
            "junit",
            "junit.xml",
            '<?xml version="1.0" encoding="utf-8"?>\n<testsuites><testsuite name="pytest">\n'
            '<testcase classname="tests.test_login" name="test_logs_in">'
            '<failure message="boom"/></testcase>\n'
            "</testsuite></testsuites>\n",
        ),
        (
            "pytest-json",
            ".report.json",
            json.dumps(
                {"tests": [{"nodeid": "tests/test_login.py::test_logs_in", "outcome": "failed"}]}
            ),
        ),
    ],
    ids=["junit-xunit1-file", "junit-xunit2-classname", "pytest-json-nodeid"],
)
def test_a_pytest_report_written_in_the_targets_cwd_binds_there(
    tmp_path, reporter, results, artifact
):
    """pytest writes paths relative to its rootdir -- the target's cwd.

    Read as repo-relative they name a file that is not there, the failing
    record binds to nothing, and the test it names never reads as failing.
    """
    project = _project(
        tmp_path,
        files={"pkg/tests/test_login.py": _PY_PARAM_TEST, f"pkg/{results}": artifact},
        targets=(
            f'[[scanning.test.targets]]\nname = "unit"\ncwd = "pkg"\n'
            f'reporter = "{reporter}"\nresults = "{results}"\n'
        ),
        directories=("pkg/tests",),
    )
    graph = _build(project)

    test_node = _test(graph, "pkg/tests/test_login.py::test_logs_in")
    assert len(_own_results(test_node)) == 1
    assert _verdict(graph, test_node) is EvidenceResult.FAILED
    assert check_unmatched_results(graph).passed is True


# Verifies: REQ-d00294-E
def test_a_repo_relative_path_from_a_cwd_target_is_kept(tmp_path):
    """A post-processed report already naming the repo-relative file keeps it."""
    junit = (
        '<?xml version="1.0" encoding="utf-8"?>\n<testsuites><testsuite name="e2e">\n'
        '<testcase classname="x" name="logs in" file="app/tests/test_login.py" line="1">'
        '<failure message="boom"/></testcase>\n</testsuite></testsuites>\n'
    )
    project = _project(
        tmp_path,
        files={"app/tests/test_login.py": _PY_PARAM_TEST, "app/results/junit.xml": junit},
        targets=(
            '[[scanning.test.targets]]\nname = "e2e"\ncwd = "app"\nreporter = "junit"\n'
            'results = "results/junit.xml"\nmatch = "source"\n'
        ),
        directories=("app/tests",),
    )
    graph = _build(project)

    test_node = _test(graph, "app/tests/test_login.py::test_logs_in")
    assert _verdict(graph, test_node) is EvidenceResult.FAILED


# ===========================================================================
# A -- a result is placed by its repo-relative path, even through a symlink
# ===========================================================================


# Verifies: REQ-d00294-A
def test_a_results_directory_linked_from_outside_keeps_its_repo_relative_place(tmp_path):
    """The same run reads the same way in any checkout, cache link or not."""
    junit = (
        '<?xml version="1.0" encoding="utf-8"?>\n<testsuites><testsuite name="pytest">\n'
        '<testcase classname="tests.test_login" name="test_logs_in">'
        '<failure message="boom"/></testcase>\n</testsuite></testsuites>\n'
    )
    project = _project(
        tmp_path,
        files={"tests/test_login.py": _PY_PARAM_TEST},
        targets=(
            '[[scanning.test.targets]]\nname = "grid"\nreporter = "junit"\n'
            'results = "evidence/*/junit.xml"\nenvironment = "results-path"\n'
        ),
    )
    cache = tmp_path / "ci-cache"
    (cache / "pixel").mkdir(parents=True)
    (cache / "pixel" / "junit.xml").write_text(junit, encoding="utf-8")
    try:
        os.symlink(cache, project / "evidence", target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not available here")

    graph = _build(project)

    (result,) = _results(graph)
    assert result.id == "result:REQ:evidence/pixel/junit.xml:1"
    assert result.get_field("result_file") == "evidence/pixel/junit.xml"
    assert result.get_field("environment") == "pixel"
    assert "file:REQ:evidence/pixel/junit.xml" in {n.id for n in graph.iter_by_kind(NodeKind.FILE)}
    assert _verdict(graph, _test(graph, "::test_logs_in")) is EvidenceResult.FAILED


# ===========================================================================
# A+B -- two targets cannot share one name
# ===========================================================================


# Verifies: REQ-d00294-A, REQ-d00294-B
@pytest.mark.parametrize(
    "first,second",
    [("unit", "unit"), ("unit", "Unit"), ("unit", " unit ")],
    ids=["same", "case", "spacing"],
)
def test_two_targets_sharing_a_name_are_refused(first, second):
    """A shared name would give two runs' results one identity; one verdict is lost."""
    from pydantic import ValidationError

    from elspais.config.schema import TestScanningConfig

    with pytest.raises(ValidationError) as excinfo:
        TestScanningConfig(
            enabled=True,
            targets=[
                {"name": first, "reporter": "junit", "cwd": "a", "results": "r.xml"},
                {"name": second, "reporter": "junit", "cwd": "b", "results": "r.xml"},
            ],
        )
    assert "share a name" in str(excinfo.value)


# Verifies: REQ-d00294-A
def test_targets_with_distinct_names_are_accepted():
    from elspais.config.schema import TestScanningConfig

    config = TestScanningConfig(
        enabled=True,
        targets=[
            {"name": "unit-a", "reporter": "junit", "cwd": "a", "results": "r.xml"},
            {"name": "unit-b", "reporter": "junit", "cwd": "b", "results": "r.xml"},
        ],
    )
    assert [t.name for t in config.targets] == ["unit-a", "unit-b"]


# ===========================================================================
# A -- a JUnit record's line is the line of THAT record
# ===========================================================================


_PLAYWRIGHT_GRID = """\
<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="login.spec.ts" hostname="chromium" tests="2">
    <testcase classname="login.spec.ts" name="logs in" file="t.spec.ts" line="2"/>
    <testcase classname="login.spec.ts" name="rejects" file="t.spec.ts" line="7"/>
  </testsuite>
  <testsuite name="login.spec.ts" hostname="firefox" tests="2" failures="1">
    <testcase classname="login.spec.ts" name="logs in" file="t.spec.ts" line="2">
      <failure message="boom"/>
    </testcase>
    <testcase classname="login.spec.ts" name="rejects" file="t.spec.ts" line="7"/>
  </testsuite>
</testsuites>
"""

_PYTEST_TEARDOWN = """\
<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="pytest" errors="1" failures="1" tests="2">
    <testcase classname="tests.test_x" name="test_other" file="tests/test_x.py" line="6">
      <failure message="assert False"/>
    </testcase>
    <testcase classname="tests.test_x" name="test_other" file="tests/test_x.py" line="6">
      <error message="failed on teardown"/>
    </testcase>
  </testsuite>
</testsuites>
"""


def _line_of(content: str, occurrence: int, needle: str) -> int:
    lines = [i for i, text in enumerate(content.splitlines(), 1) if needle in text]
    return lines[occurrence]


# Verifies: REQ-d00294-A
@pytest.mark.parametrize(
    "content,needle,status_by_line",
    [
        (_PLAYWRIGHT_GRID, 'name="logs in"', ["passed", "failed"]),
        (_PYTEST_TEARDOWN, 'name="test_other"', ["failed", "error"]),
    ],
    ids=["playwright-projects", "pytest-teardown-error"],
)
def test_each_repeated_testcase_points_at_its_own_line(content, needle, status_by_line):
    """Records agreeing on class and name each point at their own `<testcase>`."""
    from elspais.graph.parsers.results.junit_xml import JUnitXMLParser

    records = JUnitXMLParser().parse(content, "results/junit.xml")
    matching = [r for r in records if f'name="{r["name"]}"' in needle]

    assert [r["status"] for r in matching] == status_by_line
    assert [r["result_line"] for r in matching] == [
        _line_of(content, 0, needle),
        _line_of(content, 1, needle),
    ]


# Verifies: REQ-d00294-A, REQ-d00294-E
def test_a_root_suite_keeps_its_own_records_beside_nested_suites():
    """A root `<testsuite>` holding its own testcase and a nested suite loses neither."""
    from elspais.graph.parsers.results.junit_xml import JUnitXMLParser

    content = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<testsuite name="root" hostname="firefox">\n'
        '  <testcase classname="c" name="logs in"><failure message="boom"/></testcase>\n'
        '  <testsuite name="nested">\n'
        '    <testcase classname="c" name="logs in"/>\n'
        "  </testsuite>\n"
        "</testsuite>\n"
    )

    records = JUnitXMLParser().parse(content, "r.xml")

    assert sorted((r["status"], r["suite_hostname"]) for r in records) == [
        ("failed", "firefox"),
        ("passed", None),
    ]


# ===========================================================================
# C+D -- the results path names an environment only where its wildcard did
# ===========================================================================


# Verifies: REQ-d00294-C, REQ-d00294-D
@pytest.mark.parametrize(
    "pattern,segment,expected",
    [
        ("dev*", "dev", None),
        ("junit*.xml", "junit.xml", None),
        ("dev*", "devA", "A"),
        ("dev[!x]", "deva", "a"),
        ("dev[!x]", "devx", None),
        ("dev[^x]", "dev^", "^"),
        ("dev[]a]", "dev]", "]"),
        ("dev[a-c]", "devb", "b"),
        ("dev?", "dev7", "7"),
    ],
)
def test_the_wildcard_reads_as_the_glob_that_selected_the_file(pattern, segment, expected):
    """The segment the glob admitted is read the way fnmatch read it.

    An empty match stood for no part of the name, so it names nothing.
    """
    from fnmatch import fnmatchcase

    from elspais.graph.factory import _wildcard_stood_for

    environment, cause = _wildcard_stood_for(pattern, segment)

    assert environment == expected
    assert bool(cause) is (expected is None)
    if expected is not None:
        assert fnmatchcase(segment, pattern), "a named environment came from an admitted file"


# Verifies: REQ-d00294-C
@pytest.mark.parametrize(
    "pattern", ["dev[!x]", "dev[^x]", "dev[]x]", "dev[\\x]", "dev[a-c]", "dev?", "dev*"]
)
def test_every_segment_the_glob_admits_names_an_environment(pattern):
    """No segment fnmatch admits is refused by the environment reading."""
    from fnmatch import fnmatchcase

    from elspais.graph.factory import _wildcard_stood_for

    for tail in ("a", "b", "x", "^", "]", "\\", "!", "7", "ab"):
        segment = "dev" + tail
        if fnmatchcase(segment, pattern):
            environment, cause = _wildcard_stood_for(pattern, segment)
            assert environment, (pattern, segment, cause)


# Verifies: REQ-d00294-C
def test_the_wildcard_folds_case_where_the_glob_did(monkeypatch):
    """On a platform whose glob folds case, a differently cased file still reads."""
    import os.path

    from elspais.graph.factory import _wildcard_stood_for

    monkeypatch.setattr(os.path, "normcase", lambda s: s.lower())

    assert _wildcard_stood_for("junit-*.XML", "junit-Pixel.xml") == ("Pixel", "")


# Verifies: REQ-d00294-D
def test_an_empty_wildcard_match_on_disk_is_reported(tmp_path):
    """A stale unsuffixed report under a suffix glob derives no environment, and says so."""
    junit = (
        '<?xml version="1.0" encoding="utf-8"?>\n<testsuites><testsuite name="pytest">\n'
        '<testcase classname="tests.test_login" name="test_logs_in"/>\n'
        "</testsuite></testsuites>\n"
    )
    project = _project(
        tmp_path,
        files={
            "tests/test_login.py": _PY_PARAM_TEST,
            "ev/junit.xml": junit,
            "ev/junitB.xml": junit,
        },
        targets=(
            '[[scanning.test.targets]]\nname = "grid"\nreporter = "junit"\n'
            'results = "ev/junit*.xml"\nenvironment = "results-path"\n'
        ),
    )
    graph = _build(project)

    environments = {r.id: r.get_field("environment") for r in _results(graph)}
    assert environments == {
        "result:REQ:ev/junit.xml:1": None,
        "result:REQ:ev/junitB.xml:1": "B",
    }
    faults = graph.ingestion_faults()
    assert len(faults) == 1
    assert "matched nothing" in faults[0].cause


# ===========================================================================
# E -- a pytest JSON outcome the reporter cannot read is not a pass
# ===========================================================================


# Verifies: REQ-d00294-E
@pytest.mark.parametrize(
    "report,expected",
    [
        ({"tests": [{"nodeid": "t.py::a", "outcome": "weird-plugin"}]}, []),
        ({"tests": [{"nodeid": "t.py::a"}]}, []),
        ({"tests": [{"nodeid": "t.py::a", "outcome": " Failed "}]}, ["failed"]),
        ([{"name": "a", "status": "FAILURE"}], ["failed"]),
        ([{"name": "a", "status": "Failed "}], ["failed"]),
        ([{"name": "a"}], []),
    ],
    ids=["unknown", "missing", "report-odd-case", "list-synonym", "list-odd-case", "list-missing"],
)
def test_an_outcome_the_reporter_cannot_read_is_never_a_pass(report, expected):
    from elspais.graph.parsers.results.pytest_json import PytestJSONParser

    parser = PytestJSONParser()
    records = parser.parse(json.dumps(report), "report.json")

    assert [r["status"] for r in records] == expected
    diagnostics = list(parser.iter_diagnostics())
    assert len(diagnostics) == (0 if expected else 1)


# Verifies: REQ-d00294-E
def test_a_rerun_attempt_is_not_a_result_and_is_not_reported():
    """A rerun is an attempt the test's own record settles; it is dropped quietly."""
    from elspais.graph.parsers.results.pytest_json import PytestJSONParser

    parser = PytestJSONParser()
    records = parser.parse(
        json.dumps(
            {
                "tests": [
                    {"nodeid": "t.py::a", "outcome": "rerun"},
                    {"nodeid": "t.py::a", "outcome": "passed"},
                ]
            }
        ),
        "report.json",
    )

    assert [r["status"] for r in records] == ["passed"]
    assert list(parser.iter_diagnostics()) == []


# Verifies: REQ-d00294-E
def test_a_partly_unreadable_pytest_report_is_a_partial_read(tmp_path):
    """Declined records beside read ones leave the artifact read in part."""
    report = {
        "tests": [
            {"nodeid": "tests/test_login.py::test_logs_in", "outcome": "failed"},
            {"nodeid": "tests/test_login.py::test_logs_in", "outcome": "mystery"},
        ]
    }
    project = _project(
        tmp_path,
        files={"tests/test_login.py": _PY_PARAM_TEST, "results/r.json": json.dumps(report)},
        targets=(
            '[[scanning.test.targets]]\nname = "py"\nreporter = "pytest-json"\n'
            'results = "results/r.json"\n'
        ),
    )
    graph = _build(project)

    assert [r.get_field("status") for r in _results(graph)] == ["failed"]
    (fault,) = graph.ingestion_faults()
    assert fault.partial is True
    assert "mystery" in fault.cause


# ===========================================================================
# B -- a line-less record binds to a file's one test only where it names it
# ===========================================================================


# An unannotated test beside the annotated one: only `logs in` is scanned.
_TS_ONE_CITED_ONE_NOT = """\
test('other', async () => {
  expect(1).toBe(1);
});

// Verifies: REQ-p00001-A
test('logs in', async () => {
  expect(true).toBe(true);
});
"""

_PW_TARGET = """\
[[scanning.test.targets]]
name = "browser"
reporter = "junit"
results = "test-results/junit.xml"
match = "source"
classname = "source-file"
environment = "suite-hostname"
"""


def _pw_junit(*records: tuple[str, str, bool]) -> str:
    """Playwright's own junit reporter: a file per suite, no line, the project as hostname."""
    failure = '<failure message="x"/>'
    suites = "".join(
        f'  <testsuite name="login.spec.ts" hostname="{host}" tests="1">\n'
        f'    <testcase classname="login.spec.ts" name="{name}" time="0.5">'
        f"{failure if failed else ''}</testcase>\n"
        f"  </testsuite>\n"
        for host, name, failed in records
    )
    return f'<?xml version="1.0"?>\n<testsuites>\n{suites}</testsuites>\n'


def _pw_project(tmp_path: Path, junit: str) -> Path:
    return _project(
        tmp_path,
        files={"tests/e2e/login.spec.ts": _TS_ONE_CITED_ONE_NOT, "test-results/junit.xml": junit},
        targets=_PW_TARGET,
        patterns=("*.spec.ts",),
    )


# Verifies: REQ-d00284-B+C, REQ-d00294-E
def test_a_line_less_record_of_an_unscanned_sibling_is_not_the_scanned_tests(tmp_path):
    """A filtered run that ran only `other` says nothing about `logs in`.

    `--grep`, `--last-failed` or a shard writes records only for the tests it
    ran. Every record names one test and the file holds one scanned test, but
    the name is not that test's, so the failure is reported unmatched rather
    than read as the failure of a test that never ran.
    """
    graph = _build(_pw_project(tmp_path, _pw_junit(("chromium", "other", True))))

    (scanned,) = list(graph.iter_by_kind(NodeKind.TEST))
    assert _own_results(scanned) == []
    assert _verdict(graph, scanned) is EvidenceResult.NONE
    (result,) = _results(graph)
    assert _holders(result) == []
    assert "'other' does not name" in result.get_field("unbound_reason")


# Verifies: REQ-d00284-B, REQ-d00294-A+E
@pytest.mark.parametrize("name", ["logs in", "Login › logs in"])
def test_a_line_less_record_naming_the_scanned_test_binds_in_every_environment(tmp_path, name):
    """The grid's records for the one scanned test bind to it, one per project.

    Playwright prefixes a test's title with its describe blocks, joined by
    ` › `; the title itself is what the declaration line spells.
    """
    junit = _pw_junit(("chromium", name, False), ("firefox", name, True))
    graph = _build(_pw_project(tmp_path, junit))

    (scanned,) = list(graph.iter_by_kind(NodeKind.TEST))
    held = _own_results(scanned)
    assert sorted(r.get_field("environment") for r in held) == ["chromium", "firefox"]
    assert _verdict(graph, scanned) is EvidenceResult.FAILED


# Verifies: REQ-d00284-B
def test_a_line_less_grid_reads_the_tests_source_once(tmp_path, monkeypatch):
    """Binding a grid's line-less records reads the scanned test's file once.

    What a recorded name reads as against the scanned test does not change
    from one record to the next, so the build must not reread the source for
    every record and every name: that cost grows as records times names and
    is paid on every rebuild.
    """
    from elspais.graph import builder

    reads: list[str] = []
    real = builder._source_lines

    def counting(test_node):
        reads.append(test_node.id)
        return real(test_node)

    monkeypatch.setattr(builder, "_source_lines", counting)
    source = "".join(
        f"test('t{i}', async () => {{\n  expect(1).toBe(1);\n}});\n\n" for i in range(8)
    )
    source += _TS_ONE_CITED_ONE_NOT
    hosts = [f"h{e}" for e in range(4)]
    records = [(h, f"t{i}", False) for h in hosts for i in range(8)]
    records += [(h, "logs in", h == "h2") for h in hosts]
    project = _project(
        tmp_path,
        files={"tests/e2e/login.spec.ts": source, "test-results/junit.xml": _pw_junit(*records)},
        targets=_PW_TARGET,
        patterns=("*.spec.ts",),
    )
    graph = _build(project)

    (scanned,) = list(graph.iter_by_kind(NodeKind.TEST))
    assert len(_own_results(scanned)) == len(hosts)
    assert _verdict(graph, scanned) is EvidenceResult.FAILED
    assert len(reads) == 1


# Verifies: REQ-d00294-F
def test_an_unmatched_record_is_reported_beside_its_environment(tmp_path):
    """Two environments' unbound records of one test read apart in the report.

    A grid run of an unscanned sibling leaves one unbound record per
    environment, alike in everything but the suite each sits in. Without the
    environment the two findings would say the same thing.
    """
    junit = _pw_junit(("pixel6", "other", True), ("iphone15", "other", True))
    graph = _build(_pw_project(tmp_path, junit))

    messages = sorted(f.message for f in check_unmatched_results(graph).findings)

    assert len(messages) == 2
    assert "[iphone15]" in messages[0] and "[pixel6]" not in messages[0]
    assert "[pixel6]" in messages[1] and "[iphone15]" not in messages[1]


# ===========================================================================
# G -- a test file that failed to load fails every test in it
# ===========================================================================


# Verifies: REQ-d00254-G, REQ-d00294-E
def test_a_file_that_failed_to_load_fails_every_test_in_it(tmp_path):
    """package:test's `loading <path>` record is each of the file's tests' failure.

    A compile error means none of the file's tests ran. The record names no
    one test and carries no line, but it is not a sibling's verdict: it is
    the outcome of every test in the file, so each reads as failing rather
    than as never run.
    """
    project = _flutter_project(
        tmp_path, _DART_TWO_GROUPS, results="coverage/machine.jsonl", stream=None
    )
    path = str(project / "test" / "login_test.dart")
    stream = _jsonl(
        _suite(path),
        _start(1, f"loading {path}", None),
        _error(1, "Compilation failed"),
        _done(1, "error"),
        _end(False),
    )
    (project / "coverage").mkdir()
    (project / "coverage" / "machine.jsonl").write_text(stream, encoding="utf-8")
    graph = _build(project)

    (loading,) = _results(graph)
    tests = sorted(graph.iter_by_kind(NodeKind.TEST), key=lambda n: n.id)
    assert len(tests) == 2
    assert _holders(loading) == [t.id for t in tests]
    for test_node in tests:
        assert _verdict(graph, test_node) is EvidenceResult.FAILED
    assert _metrics(graph).verified.failing_labels == {"A", "B"}
    assert check_unmatched_results(graph).passed is True


# Verifies: REQ-d00254-G, REQ-d00294-E
def test_a_loading_record_that_passed_is_not_held(tmp_path):
    """A suite that loaded is hidden by the runner and is no test's result."""
    project = _flutter_project(
        tmp_path, _DART_TWO_GROUPS, results="coverage/machine.jsonl", stream=None
    )
    path = str(project / "test" / "login_test.dart")
    stream = _jsonl(
        _suite(path),
        _start(1, f"loading {path}", None),
        _done(1, hidden=True),
        _start(2, "A a1", 6),
        _done(2),
        _end(True),
    )
    (project / "coverage").mkdir()
    (project / "coverage" / "machine.jsonl").write_text(stream, encoding="utf-8")
    graph = _build(project)

    assert [r.get_field("name") for r in _results(graph)] == ["A a1"]
    assert all(r.get_field("match_scope") == "test" for r in _results(graph))


# pytest's record of a module as a whole, as `junit_family=xunit1` writes it:
# no classname, the module's dotted path as its name, its file and no line.
_PYTEST_MODULE_RECORD = """\
<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="pytest" tests="1">
    <testcase classname="" name="tests.test_login" file="tests/test_login.py" time="0.0">
      {outcome}
    </testcase>
  </testsuite>
</testsuites>
"""


# Verifies: REQ-d00294-E, REQ-d00254-G
@pytest.mark.parametrize(
    "outcome,status,verdict",
    [
        ('<error message="collection failure">ImportError</error>', "error", "FAILED"),
        ('<skipped message="collection skipped">importorskip</skipped>', "skipped", None),
    ],
    ids=["import-error", "module-skip"],
)
def test_a_pytest_module_record_is_the_outcome_of_every_test_in_it(
    tmp_path, outcome, status, verdict
):
    """A module that failed to import or skipped at load ran none of its tests.

    pytest writes one record for the module, naming no test. It is not a
    sibling's verdict: it is the outcome of every test in the file, so each
    holds it, and nothing is reported as matching no test.
    """
    project = _project(
        tmp_path,
        files={
            "tests/test_login.py": _PY_TWO_TESTS,
            "results/junit.xml": _PYTEST_MODULE_RECORD.format(outcome=outcome),
        },
        targets=(
            '[[scanning.test.targets]]\nname = "unit"\nreporter = "junit"\n'
            'results = "results/junit.xml"\n'
        ),
    )
    graph = _build(project)

    (record,) = _results(graph)
    tests = sorted(graph.iter_by_kind(NodeKind.TEST), key=lambda n: n.id)
    assert len(tests) == 2
    assert record.get_field("status") == status
    assert _holders(record) == [t.id for t in tests]
    if verdict is not None:
        for test_node in tests:
            assert _verdict(graph, test_node) is EvidenceResult[verdict]
    assert check_unmatched_results(graph).passed is True


# ===========================================================================
# E -- a record reaching its test by another spelling of the same file
# ===========================================================================


# Verifies: REQ-d00294-E, REQ-d00254-G
@pytest.mark.parametrize("absolute", [True, False], ids=["absolute", "relative"])
def test_a_record_naming_its_test_through_a_symlink_binds_to_it(tmp_path, absolute):
    """A symlinked directory inside the repository is one file reached two ways.

    The test is scanned where it lies and the producer writes a path through
    a link to that directory -- absolute, or relative to the root the target
    ran from, as pytest writes a JUnit `file`; both name the one file, so the
    failure is that test's own.
    """
    project = _project(
        tmp_path,
        files={"tests/real/test_login.py": _PY_TWO_TESTS},
        targets=(
            '[[scanning.test.targets]]\nname = "py"\nreporter = "junit"\n'
            'results = "out/junit.xml"\nmatch = "source"\n'
        ),
    )
    try:
        os.symlink("real", project / "tests" / "link", target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not available here")
    recorded = (
        project / "tests" / "link" / "test_login.py" if absolute else "tests/link/test_login.py"
    )
    (project / "out").mkdir()
    (project / "out" / "junit.xml").write_text(
        '<?xml version="1.0"?>\n<testsuites><testsuite name="pytest">\n'
        f'<testcase classname="x" name="test_rejects" file="{recorded}" line="6">'
        '<failure message="boom"/></testcase>\n</testsuite></testsuites>\n',
        encoding="utf-8",
    )
    graph = _build(project)

    (result,) = _results(graph)
    rejects = _test(graph, "::test_rejects")
    assert _holders(result) == [rejects.id]
    assert _verdict(graph, rejects) is EvidenceResult.FAILED
    assert _verdict(graph, _test(graph, "::test_logs_in")) is EvidenceResult.NONE


# ===========================================================================
# B -- a target's own results never share a place with an artifact's
# ===========================================================================


# Verifies: REQ-d00294-A, REQ-d00294-B, REQ-d00294-E
def test_a_target_named_like_another_targets_results_file_keeps_both(tmp_path):
    """A target read from its output, named `out/junit.xml`, beside that artifact.

    The name is free text, so it can be spelled like the file another target
    writes. The two are different places of record, and each record is held
    by its own test: neither verdict replaces the other.
    """
    junit = (
        '<?xml version="1.0"?>\n<testsuites><testsuite name="pytest">\n'
        '<testcase classname="x" name="test_logs_in" file="tests/test_login.py" '
        'line="1"/>\n</testsuite></testsuites>\n'
    )
    project = _project(
        tmp_path,
        files={
            "tests/test_login.py": _PY_TWO_TESTS,
            "test/login_test.dart": _DART_TWO_TESTS,
            "out/junit.xml": junit,
        },
        targets=(
            '[[scanning.test.targets]]\nname = "out/junit.xml"\n'
            'reporter = "flutter-machine"\nmatch = "source"\n'
            'command = "flutter test --machine"\n\n'
            '[[scanning.test.targets]]\nname = "py"\nreporter = "junit"\n'
            'results = "out/junit.xml"\nmatch = "source"\n'
        ),
        directories=("tests", "test"),
        patterns=("test_*.py", "*_test.dart"),
    )
    stream = _jsonl(
        _suite(str(project / "test" / "login_test.dart")),
        _start(2, "a1", 3),
        _done(2, "failure"),
        _end(False),
    )
    graph = _build(project, captured_results={"out/junit.xml": stream})

    results = _results(graph)
    assert [r.id for r in results] == ["result:REQ:out/junit.xml/:1", "result:REQ:out/junit.xml:1"]
    assert _verdict(graph, _test(graph, ":3")) is EvidenceResult.FAILED
    assert _verdict(graph, _test(graph, "::test_logs_in")) is EvidenceResult.PASSED


# ===========================================================================
# C+D -- an environment of nothing but whitespace is none, and is reported
# ===========================================================================


# Verifies: REQ-d00294-C, REQ-d00294-D
def test_a_blank_suite_hostname_is_no_environment(tmp_path):
    """`hostname="  "` names nothing a reader could tell from a blank."""
    graph = _build(_pw_project(tmp_path, _pw_junit(("  ", "logs in", False))))

    (result,) = _results(graph)
    assert result.get_field("environment") is None
    (fault,) = graph.ingestion_faults()
    assert "blank hostname" in fault.cause


# Verifies: REQ-d00294-C, REQ-d00294-D
def test_a_wildcard_matching_only_whitespace_is_no_environment(tmp_path):
    """A results directory named with spaces alone names no environment."""
    junit = (
        '<?xml version="1.0"?>\n<testsuites><testsuite name="pytest">\n'
        '<testcase classname="tests.test_login" name="test_logs_in"/>\n'
        "</testsuite></testsuites>\n"
    )
    project = _project(
        tmp_path,
        files={"tests/test_login.py": _PY_PARAM_TEST, "ev/  /junit.xml": junit},
        targets=(
            '[[scanning.test.targets]]\nname = "grid"\nreporter = "junit"\n'
            'results = "ev/*/junit.xml"\nenvironment = "results-path"\n'
        ),
    )
    graph = _build(project)

    (result,) = _results(graph)
    assert result.get_field("environment") is None
    (fault,) = graph.ingestion_faults()
    assert "only whitespace" in fault.cause


# ===========================================================================
# B -- a line-less record is matched against the title the test declares
# ===========================================================================


# Verifies: REQ-d00284-B, REQ-d00294-E
@pytest.mark.parametrize(
    "declaration,title",
    [
        ("test('login [smoke]', async () => {", "login [smoke]"),
        (
            "test(\n  'logs in with a title a formatter wrapped',\n  async () => {",
            "logs in with a title a formatter wrapped",
        ),
        ('test(\n  // why\n  "it\\\'s wrapped",\n  async () => {', "it's wrapped"),
    ],
    ids=["bracketed-title", "wrapped-title", "wrapped-past-a-comment"],
)
def test_a_line_less_record_names_the_title_its_test_declares(tmp_path, declaration, title):
    """The title is the declaration's first string literal, taken as written.

    A Playwright title ending in `[...]` is that title rather than a pytest
    parametrization, and a formatter that moves the title onto a line of its
    own leaves it the same title.
    """
    spec_ts = f"// Verifies: REQ-p00001-A\n{declaration}\n    expect(true).toBe(true);\n  }},\n);\n"
    project = _project(
        tmp_path,
        files={
            "tests/e2e/login.spec.ts": spec_ts,
            "test-results/junit.xml": _pw_junit(("chromium", f"Login › {title}", True)),
        },
        targets=_PW_TARGET,
        patterns=("*.spec.ts",),
    )
    graph = _build(project)

    (scanned,) = list(graph.iter_by_kind(NodeKind.TEST))
    (result,) = _results(graph)
    assert _holders(result) == [scanned.id]
    assert _verdict(graph, scanned) is EvidenceResult.FAILED


# Verifies: REQ-d00284-B, REQ-d00294-E
@pytest.mark.parametrize("hosts", [("chromium",), ("chromium", "firefox")], ids=["one", "grid"])
def test_a_line_less_record_names_its_test_beside_an_uncited_sibling(tmp_path, hosts):
    """One cited test beside an uncited one that also ran: the usual Playwright file.

    The records name two tests, but only `logs in` is the title the scanned
    test declares, so its records are its own and `other`'s are nobody's.
    The scanned test fails where its own record failed.
    """
    records = [(h, "other", False) for h in hosts]
    records += [(h, "logs in", h == "chromium") for h in hosts]
    graph = _build(_pw_project(tmp_path, _pw_junit(*records)))

    (scanned,) = list(graph.iter_by_kind(NodeKind.TEST))
    held = _own_results(scanned)
    assert sorted(r.get_field("name") for r in held) == ["logs in"] * len(hosts)
    assert _verdict(graph, scanned) is EvidenceResult.FAILED
    others = [r for r in _results(graph) if r.get_field("name") == "other"]
    assert len(others) == len(hosts)
    for other in others:
        assert _holders(other) == []
        assert "'other' does not name" in other.get_field("unbound_reason")


# Verifies: REQ-d00284-B, REQ-d00294-E
def test_line_less_records_under_two_groups_matching_one_title_bind_to_neither(tmp_path):
    """`A › logs in` and `B › logs in` both end in the one scanned title.

    Only one test was scanned, yet two tests of that title ran, so which of
    them is the scanned one cannot be told and neither verdict is its own.
    """
    junit = _pw_junit(("chromium", "A › logs in", False), ("chromium", "B › logs in", True))
    graph = _build(_pw_project(tmp_path, junit))

    (scanned,) = list(graph.iter_by_kind(NodeKind.TEST))
    assert _own_results(scanned) == []
    for result in _results(graph):
        assert _holders(result) == []
        assert "2 different names" in result.get_field("unbound_reason")


# Verifies: REQ-d00284-B, REQ-d00294-E
@pytest.mark.parametrize(
    "declaration",
    ["test(LOGIN_TITLE, loginFlow);", "test(\n  LOGIN_TITLE,\n  loginFlow,\n);"],
    ids=["one-line", "wrapped"],
)
def test_a_title_that_is_no_literal_is_not_read_off_the_next_test(tmp_path, declaration):
    """A test titled by a constant declares no title a record can be matched to.

    The next string literal in the file is the NEXT test's title. A filtered
    run that ran only that unscanned sibling says nothing about the scanned
    test, so its failure is reported unmatched rather than held.
    """
    spec_ts = f"// Verifies: REQ-p00001-A\n{declaration}\ntest('logs out', logoutFlow);\n"
    project = _project(
        tmp_path,
        files={
            "tests/e2e/login.spec.ts": spec_ts,
            "test-results/junit.xml": _pw_junit(("chromium", "logs out", True)),
        },
        targets=_PW_TARGET,
        patterns=("*.spec.ts",),
    )
    graph = _build(project)

    (scanned,) = list(graph.iter_by_kind(NodeKind.TEST))
    (result,) = _results(graph)
    assert _holders(result) == []
    assert _verdict(graph, scanned) is EvidenceResult.NONE


# Verifies: REQ-d00284-B+C, REQ-d00294-E
def test_a_title_declared_twice_in_the_file_is_not_read_off_a_sibling(tmp_path):
    """`test('x')` under `describe('A')` is cited; `describe('B')` holds another.

    A filtered or sharded run that ran only `B › x` writes one record ending
    in the scanned title. The groups the scanned test sits in are not read
    from its source, so that record may be either test, and handing B's
    failure to A -- which did not run -- is refused and reported.
    """
    spec_ts = (
        "test.describe('A', () => {\n"
        "  // Verifies: REQ-p00001-A\n"
        "  test('x', async () => {});\n"
        "});\n"
        "\n"
        "test.describe('B', () => {\n"
        "  test('x', async () => {});\n"
        "});\n"
    )
    project = _project(
        tmp_path,
        files={
            "tests/e2e/login.spec.ts": spec_ts,
            "test-results/junit.xml": _pw_junit(("chromium", "B › x", True)),
        },
        targets=_PW_TARGET,
        patterns=("*.spec.ts",),
    )
    graph = _build(project)

    (scanned,) = list(graph.iter_by_kind(NodeKind.TEST))
    (result,) = _results(graph)
    assert _holders(result) == []
    assert _verdict(graph, scanned) is EvidenceResult.NONE
    assert "declares 2 tests titled 'x'" in result.get_field("unbound_reason")


# Verifies: REQ-d00284-C
def test_line_less_records_naming_no_scanned_test_say_so_by_their_own_names(tmp_path):
    """Records `y` and `z` ran; the cited `x` was deselected.

    Neither name picks out the one scanned test, so each is reported as a
    name that names no test -- not as an ambiguity between tests -- and each
    finding is labelled with the record's own name, not only the file every
    record of the report shares.
    """
    spec_ts = (
        "// Verifies: REQ-p00001-A\n"
        "test('x', async () => {});\n"
        "test('y', async () => {});\n"
        "test('z', async () => {});\n"
    )
    project = _project(
        tmp_path,
        files={
            "tests/e2e/login.spec.ts": spec_ts,
            "test-results/junit.xml": _pw_junit(("chromium", "y", True), ("chromium", "z", True)),
        },
        targets=_PW_TARGET,
        patterns=("*.spec.ts",),
    )
    graph = _build(project)

    for result in _results(graph):
        name = result.get_field("name")
        assert f"its name {name!r} does not name" in result.get_field("unbound_reason")
    messages = sorted(f.message for f in check_unmatched_results(graph).findings)
    assert len(messages) == 2
    assert "result named 'y' in 'login.spec.ts'" in messages[0]
    assert "result named 'z' in 'login.spec.ts'" in messages[1]
    assert all("cannot be told" not in m for m in messages)


# Verifies: REQ-d00284-B, REQ-d00294-E
@pytest.mark.parametrize(
    "literal", ["r'a1'", "'''a1'''", 'r"""a1"""'], ids=["raw", "triple", "raw-triple"]
)
def test_a_dart_title_written_as_a_raw_or_triple_literal_is_its_title(tmp_path, literal):
    """`test(r'a1', ...)` declares the title `a1`, as `test('a1', ...)` does.

    Dart code writes a raw string for a title holding `$`; a record naming
    `a1` with no line is that test's, and its failure is the test's own.
    """
    dart = (
        "void main() {\n"
        "  // Verifies: REQ-p00001-A\n"
        f"  test({literal}, () {{\n"
        "    expect(1, 2);\n"
        "  });\n"
        "}\n"
    )
    stream = _jsonl(
        _suite("test/login_test.dart"), _start(1, "a1", None), _done(1, "failure"), _end(False)
    )
    project = _flutter_project(tmp_path, dart, results="coverage/machine.jsonl", stream=stream)
    graph = _build(project)

    (scanned,) = list(graph.iter_by_kind(NodeKind.TEST))
    (result,) = _results(graph)
    assert _holders(result) == [scanned.id]
    assert _verdict(graph, scanned) is EvidenceResult.FAILED


# Verifies: REQ-d00284-B, REQ-d00294-E
def test_every_parametrization_of_one_pytest_test_is_that_tests(tmp_path):
    """`test_x[1]` and `test_x[2]` both ran as the one scanned `test_x`.

    They are two records of one test, not two tests of that title, so both
    bind to it and the failing one fails it.
    """
    py = (
        "import pytest\n\n"
        "# Verifies: REQ-p00001-A\n"
        "@pytest.mark.parametrize('v', [1, 2])\n"
        "def test_x(v):\n"
        "    assert v\n"
    )
    junit = (
        '<?xml version="1.0"?>\n<testsuites><testsuite name="pytest">\n'
        '<testcase classname="tests.test_p" name="test_x[1]" file="tests/test_p.py"/>\n'
        '<testcase classname="tests.test_p" name="test_x[2]" file="tests/test_p.py">'
        '<failure message="b"/></testcase>\n'
        "</testsuite></testsuites>\n"
    )
    project = _project(
        tmp_path,
        files={"tests/test_p.py": py, "out/j.xml": junit},
        targets=(
            '[[scanning.test.targets]]\nname = "py"\nreporter = "junit"\n'
            'results = "out/j.xml"\nmatch = "source"\n'
        ),
    )
    graph = _build(project)

    scanned = _test(graph, "tests/test_p.py::test_x")
    assert sorted(r.get_field("name") for r in _own_results(scanned)) == [
        "test_x[1]",
        "test_x[2]",
    ]
    assert _verdict(graph, scanned) is EvidenceResult.FAILED
