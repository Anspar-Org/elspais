"""Parser for `flutter test --machine` newline-delimited JSON events.

Builds RESULT records carrying the REAL test-file path (from ``suite.path``)
and per-test identity (name, line) — unlike tojunit's lossy classname.

Record shape mirrors sibling parsers (junit_xml, pytest_json):
``{"id", "name", "classname", "status", "duration", "message", "verifies",
"source_path", "line", "root_path", "root_line", "test_id"}``.

``line`` is the line number from the machine event's ``test.line`` field.
For plain ``test()`` calls this is the user call site.  For
``testWidgets(...)`` calls the framework reports a wrapper line instead
(e.g. inside ``package:flutter_test/src/widget_tester.dart``), which will
*not* match the TEST node built from the source file.  In that case the
real call site lives in ``test.root_line`` / ``test.root_url``.

Both fields are carried through so the graph builder can try the primary
``(source_path, line)`` match first and fall back to
``(root_path, root_line)`` before giving up and doing a file-granular link.

``test_id`` is always ``None``.  Per-test correlation is resolved at
graph-build time by ``(source_path, line)`` — no pre-baked id is used.

Suite-loader pseudo-tests (``hidden: true`` in ``testDone``) are skipped.
"""

from __future__ import annotations

import json
from typing import Any


# Implements: REQ-d00254-E
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
                raw_root_url = t.get("root_url")
                # root_url is a file:///abs/path URL (Dart); strip the scheme prefix to get a path
                if raw_root_url and raw_root_url.startswith("file://"):
                    root_path = raw_root_url[len("file://") :]
                else:
                    root_path = None
                tests[t.get("id")] = {
                    "name": t.get("name", ""),
                    "suiteID": t.get("suiteID"),
                    "line": t.get("line"),
                    "root_line": t.get("root_line"),
                    "root_path": root_path,
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
                        "root_line": meta["root_line"],
                        "root_path": meta["root_path"],
                        "test_id": None,
                        # stdout-stream reporter: there is no results file to
                        # point provenance at.
                        "result_file": None,
                        "result_line": None,
                    }
                )
        return results
