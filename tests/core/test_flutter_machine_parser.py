# Verifies: REQ-d00254-E
"""Tests for the flutter-machine JSONL parser.

Covers line-precise record emission: each parsed result must carry the
``test()`` call-site line number so graph-build can correlate by
``(source_path, line)`` rather than a pre-baked id.
"""
from __future__ import annotations

import json

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
