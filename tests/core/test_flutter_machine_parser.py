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
            174,
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
