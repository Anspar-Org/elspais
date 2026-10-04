# Verifies: REQ-d00254-E
"""Tests for the flutter-machine JSONL parser.

Covers line-precise record emission: each parsed result must carry the
``test()`` call-site line number so graph-build can correlate by
``(source_path, line)`` rather than a pre-baked id.
"""

from __future__ import annotations

import json

import pytest

from elspais.graph.parsers.results.flutter_machine import FlutterMachineParser

# ---------------------------------------------------------------------------
# Minimal machine.jsonl stream helpers
# ---------------------------------------------------------------------------

_SUITE_PATH = "test/widget_test.dart"

_STREAM = "\n".join(
    [
        json.dumps({"type": "suite", "suite": {"id": 1, "path": _SUITE_PATH, "platform": "vm"}}),
        # Hidden loader pseudo-test — must be skipped
        json.dumps(
            {
                "type": "testStart",
                "test": {
                    "id": 0,
                    "name": "loading test/widget_test.dart",
                    "suiteID": 1,
                    "line": None,
                    "hidden": True,
                },
            }
        ),
        json.dumps({"type": "testDone", "testID": 0, "result": "success", "hidden": True}),
        # Real test at line 85
        json.dumps(
            {
                "type": "testStart",
                "test": {
                    "id": 2,
                    "name": "Counter increments smoke test",
                    "suiteID": 1,
                    "line": 85,
                },
            }
        ),
        json.dumps({"type": "testDone", "testID": 2, "result": "success", "hidden": False}),
    ]
)


class TestFlutterMachineParser:
    def test_skips_hidden_loader_and_emits_one_record(self) -> None:
        records = FlutterMachineParser().parse(_STREAM)
        assert len(records) == 1, f"expected 1 record, got {len(records)}: {records}"

    def test_record_line_is_test_call_site(self) -> None:
        records = FlutterMachineParser().parse(_STREAM)
        assert records[0]["line"] == 85

    def test_record_status_passed(self) -> None:
        records = FlutterMachineParser().parse(_STREAM)
        assert records[0]["status"] == "passed"

    def test_record_source_path(self) -> None:
        records = FlutterMachineParser().parse(_STREAM)
        assert records[0]["source_path"] == _SUITE_PATH

    def test_record_test_id_is_none(self) -> None:
        """test_id stays None; correlation is by (source_path, line) at build time."""
        records = FlutterMachineParser().parse(_STREAM)
        assert records[0]["test_id"] is None


# ---------------------------------------------------------------------------
# Where a test is declared, and which file executed it
# ---------------------------------------------------------------------------

_RUNNER = "/abs/event_sourcing/test/storage/postgres/postgres_x_test.dart"
_SHARED = "/abs/event_sourcing/test/test_support/boot_conformance.dart"
_WIDGET_WRAPPER = "package:flutter_test/src/widget_tester.dart"


def _one_test_stream(test_fields: dict) -> str:
    """A suite at ``_RUNNER`` running one test that carries ``test_fields``."""
    test = {"id": 250, "name": "two stores share one identity", "suiteID": 245, **test_fields}
    return "\n".join(
        [
            json.dumps({"suite": {"id": 245, "platform": "vm", "path": _RUNNER}, "type": "suite"}),
            json.dumps({"test": test, "type": "testStart", "time": 96500}),
            json.dumps(
                {
                    "testID": 250,
                    "result": "success",
                    "skipped": False,
                    "hidden": False,
                    "type": "testDone",
                    "time": 96600,
                }
            ),
        ]
    )


# Verifies: REQ-d00254-E, REQ-d00254-Z, REQ-d00294-G
@pytest.mark.parametrize(
    "test_fields,source_path,line,root_path,root_line",
    [
        pytest.param(
            {
                "line": 296,
                "url": f"file://{_SHARED}",
                "root_line": 192,
                "root_url": f"file://{_RUNNER}",
            },
            _SHARED,
            296,
            None,
            None,
            id="declared-in-a-shared-file",
        ),
        pytest.param(
            {
                "line": 40,
                "url": f"file://{_RUNNER}",
                "root_line": 40,
                "root_url": f"file://{_RUNNER}",
            },
            _RUNNER,
            40,
            None,
            None,
            id="declared-in-the-suite",
        ),
        pytest.param(
            {
                "line": 174,
                "url": _WIDGET_WRAPPER,
                "root_line": 12,
                "root_url": f"file://{_RUNNER}",
            },
            _RUNNER,
            None,
            _RUNNER,
            12,
            id="testWidgets-package-url",
        ),
        pytest.param(
            {"line": 7, "url": "file:///abs/my%20app/test/shared%20steps.dart"},
            "/abs/my app/test/shared steps.dart",
            7,
            None,
            None,
            id="percent-encoded",
        ),
        pytest.param(
            {"line": 9, "root_line": 9, "root_url": f"file://{_RUNNER}"},
            _RUNNER,
            9,
            _RUNNER,
            9,
            id="no-url",
        ),
    ],
)
def test_a_record_names_where_its_test_is_declared_and_what_ran_it(
    test_fields, source_path, line, root_path, root_line
):
    (record,) = FlutterMachineParser().parse(_one_test_stream(test_fields))

    assert record["source_path"] == source_path
    assert record["line"] == line
    assert record["root_path"] == root_path
    assert record["root_line"] == root_line
    # The suite is the file that executed the test, wherever it is declared.
    assert record["runner_path"] == _RUNNER


# ---------------------------------------------------------------------------
# How a file URL becomes a local path
# ---------------------------------------------------------------------------


# Verifies: REQ-d00254-E
def test_a_windows_file_url_keeps_its_drive_letter(monkeypatch):
    """The Windows URL-to-path conversion is put in place of the POSIX one, so
    the Windows behaviour is exercised on any platform."""
    import warnings

    from elspais.graph.parsers.results import flutter_machine

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        import nturl2path

    monkeypatch.setattr(flutter_machine, "url2pathname", nturl2path.url2pathname)

    (record,) = FlutterMachineParser().parse(
        _one_test_stream({"line": 3, "url": "file:///C:/proj/my%20app/test/a_test.dart"})
    )

    assert record["source_path"] == r"C:\proj\my app\test\a_test.dart"
    assert record["line"] == 3


# Verifies: REQ-d00254-E
@pytest.mark.parametrize(
    "url",
    ["package:flutter_test/src/widget_tester.dart", "dart:async/zone.dart"],
    ids=["package", "dart"],
)
def test_a_url_that_is_not_a_file_url_names_no_path(url):
    from elspais.graph.parsers.results.flutter_machine import _file_url_path

    assert _file_url_path(url) is None


# ---------------------------------------------------------------------------
# Durations and printed output
# ---------------------------------------------------------------------------


def _timed_stream(*prints: dict, start: object = 100, done: object = 1600) -> str:
    """One suite running test 1 from ``start`` to ``done``, with ``prints`` between."""
    events = [
        {"type": "suite", "suite": {"id": 0, "platform": "vm", "path": _SUITE_PATH}},
        {
            "type": "testStart",
            "test": {"id": 1, "name": "throughput", "suiteID": 0, "line": 12},
            "time": start,
        },
        *prints,
        {"type": "testDone", "testID": 1, "result": "success", "hidden": False, "time": done},
    ]
    return "\n".join(json.dumps(e) for e in events)


def _print(message: str, test_id: int = 1) -> dict:
    return {"type": "print", "testID": test_id, "message": message, "messageType": "print"}


# Verifies: REQ-d00322-M
def test_a_record_carries_the_seconds_between_its_start_and_done_events():
    (record,) = FlutterMachineParser().parse(_timed_stream())

    assert record["duration"] == 1.5


# Verifies: REQ-d00322-M
@pytest.mark.parametrize(
    "start,done",
    [(None, 1600), (100, None), ("100", 1600)],
    ids=["no-start", "no-done", "not-an-integer"],
)
def test_a_record_without_two_event_times_carries_no_duration(start, done):
    (record,) = FlutterMachineParser().parse(_timed_stream(start=start, done=done))

    assert record["duration"] == 0.0


# Verifies: REQ-d00322-M
@pytest.mark.parametrize(
    "prints,output",
    [
        ([_print("ratio 0.9x")], "ratio 0.9x"),
        ([_print("ratio 0.9x"), _print("pause 12ms")], "ratio 0.9x\npause 12ms"),
        ([], None),
        ([_print("from nowhere", test_id=99)], None),
    ],
    ids=["one-print", "two-prints-joined", "no-print", "print-for-an-unknown-test"],
)
def test_a_record_carries_what_its_test_printed(prints, output):
    (record,) = FlutterMachineParser().parse(_timed_stream(*prints))

    assert record["output"] == output


# Verifies: REQ-d00322-M
def test_a_result_node_carries_its_duration_and_printed_output(tmp_path):
    from elspais.config.schema import TestTargetConfig
    from elspais.graph.builder import GraphBuilder
    from elspais.graph.factory import _ingest_target_results
    from elspais.graph.GraphNode import NodeKind
    from tests.core.graph_test_helpers import grammar_for

    builder = GraphBuilder(repo_root=tmp_path, namespace="REQ", resolver=grammar_for("REQ"))
    target = TestTargetConfig(name="flutter", reporter="flutter-machine", match="source")
    stream = _timed_stream(_print("ratio 0.9x"), _print("pause 12ms"))
    assert _ingest_target_results(builder, target, stream, tmp_path, namespace="REQ") == 1

    (node,) = list(builder.build().iter_by_kind(NodeKind.RESULT))

    assert node.get_field("duration") == 1.5
    assert node.get_field("output") == "ratio 0.9x\npause 12ms"


def _started(test_id: int, name: str) -> str:
    return json.dumps(
        {"type": "testStart", "test": {"id": test_id, "name": name, "suiteID": 1, "line": 9}}
    )


# Verifies: REQ-d00285-G, REQ-d00254-Q
@pytest.mark.parametrize(
    ("stream", "partial"),
    [
        # The stream ends inside the second test, after the first finished.
        (_STREAM + "\n" + _started(3, "cut off"), True),
        # The stream ends inside the only test it started.
        (_STREAM.split("\n")[0] + "\n" + _started(3, "cut off"), False),
    ],
    ids=["after-a-result", "before-any-result"],
)
def test_a_test_that_started_and_reported_no_result_is_recorded(stream, partial):
    parser = FlutterMachineParser()

    parser.parse(stream, "machine.jsonl")

    (diagnostic,) = parser.iter_diagnostics()
    assert diagnostic.path == "machine.jsonl"
    assert "'cut off' started and reported no result" in diagnostic.cause
    assert diagnostic.partial is partial


# Verifies: REQ-d00285-G
def test_a_stream_whose_tests_all_ended_records_nothing():
    parser = FlutterMachineParser()

    parser.parse(_STREAM, "machine.jsonl")

    assert list(parser.iter_diagnostics()) == []
