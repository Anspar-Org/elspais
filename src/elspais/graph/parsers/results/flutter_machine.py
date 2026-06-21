"""Parser for `flutter test --machine` newline-delimited JSON events.

Builds RESULT records carrying the REAL test-file path (from ``suite.path``)
and per-test identity (name, line) — unlike tojunit's lossy classname.

Record shape mirrors sibling parsers (junit_xml, pytest_json):
``{"id", "name", "classname", "status", "duration", "message", "verifies",
"source_path", "test_id"}``.  ``test_id`` is always ``None`` because Flutter
results correlate to test files by path (Task 5 precise matching), not by a
pytest-style test_id.
"""

from __future__ import annotations

import json
from typing import Any


class FlutterMachineParser:
    def parse(self, content: str, source_path: str = "") -> list[dict[str, Any]]:
        suites: dict[int, str] = {}  # suiteID -> path
        tests: dict[int, dict[str, Any]] = {}  # testID -> {name, suiteID, line}
        results: list[dict[str, Any]] = []

        for line in content.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except (ValueError, json.JSONDecodeError):
                continue
            if not isinstance(ev, dict):
                continue
            etype = ev.get("type")
            if etype == "suite":
                s = ev.get("suite", {})
                suites[s.get("id")] = s.get("path", "")
            elif etype == "testStart":
                t = ev.get("test", {})
                tests[t.get("id")] = {
                    "name": t.get("name", ""),
                    "suiteID": t.get("suiteID"),
                    "line": t.get("line"),
                }
            elif etype == "testDone":
                if ev.get("hidden"):
                    continue
                meta = tests.get(ev.get("testID"))
                if meta is None:
                    continue
                if ev.get("skipped"):
                    status = "skipped"
                elif ev.get("result") == "success":
                    status = "passed"
                else:  # "failure" | "error"
                    status = "failed"
                path = suites.get(meta["suiteID"], "")
                results.append(
                    {
                        "id": f"{path}::{meta['name']}",
                        "name": meta["name"],
                        "classname": "",
                        "status": status,
                        "duration": 0.0,
                        "message": None,
                        "verifies": [],
                        "source_path": path,
                        "line": meta["line"],
                        "test_id": None,
                    }
                )
        return results
