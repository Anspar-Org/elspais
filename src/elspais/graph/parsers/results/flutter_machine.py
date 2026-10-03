"""Parser for `flutter test --machine` newline-delimited JSON events.

Builds RESULT records carrying where each test is declared (path, line), the
file that executed it, and its name.

Record shape mirrors sibling parsers (junit_xml, pytest_json):
``{"ordinal", "name", "classname", "status", "duration", "message",
"source_path", "line", "root_path", "root_line", "runner_path", "test_id"}``.

``test.url`` and ``test.line`` name the frame that called ``test()``, and
``suite.path`` names the file the runner executed. The two differ for a
scenario declared in a shared file and executed through a runner file. The
test's citations sit at the declaration. Consequently, a ``file:`` URL in
``test.url`` gives ``source_path`` and ``line``, and ``suite.path`` gives
``runner_path`` (REQ-d00254-Z).

For ``testWidgets(...)``, ``test.url`` names a frame inside
``package:flutter_test``, which is no file of the project. The record then
takes ``source_path`` from ``suite.path`` and carries ``test.root_url`` /
``test.root_line``, which name the call site in the suite's file. The builder
tries ``(source_path, line)`` and falls back to ``(root_path, root_line)``. A
record that names its declaration carries no root location. Consequently,
it never falls back to the runner file.

``test_id`` is always ``None``: which test a result belongs to is answered at
graph-build time from the file and line, so nothing needs to be pre-baked.

Suite-loader pseudo-tests (``hidden: true`` in ``testDone``) are skipped.
"""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlparse
from urllib.request import url2pathname

from elspais.graph.parsers.results.diagnostics import DiagnosticRecorder


def _file_url_path(url: Any) -> str | None:
    """The path a ``file:`` URL names, or ``None`` for any other URL.

    Dart writes ``file:///abs/path``, and ``file:///C:/abs/path`` on Windows.
    The platform's own conversion turns the URL path into a local path, so a
    Windows drive letter is kept. A ``package:`` or ``dart:`` URL names no
    file of the project.
    """
    if isinstance(url, str) and url.startswith("file://"):
        return url2pathname(urlparse(url).path)
    return None


# Implements: REQ-d00254-E
class FlutterMachineParser(DiagnosticRecorder):
    def parse(self, content: str, source_path: str = "") -> list[dict[str, Any]]:
        suites: dict[int, str] = {}  # suiteID -> path
        tests: dict[int, dict[str, Any]] = {}  # testID -> {name, suiteID, line}
        results: list[dict[str, Any]] = []
        self._start_diagnostics()
        events = 0

        for line in content.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except (ValueError, json.JSONDecodeError):
                # Suppressed deliberately: this reporter reads a runner's live
                # stdout, where a build banner, a warning, or a plugin's own
                # print sits between events. A line that is not JSON is
                # expected traffic, not a record that failed to read. What
                # would be a real condition -- a stream carrying no events at
                # all -- is recorded once, after the loop.
                continue
            if not isinstance(ev, dict):
                continue
            events += 1
            etype = ev.get("type")
            if etype == "suite":
                s = ev.get("suite", {})
                suites[s.get("id")] = s.get("path", "")
            elif etype == "testStart":
                t = ev.get("test", {})
                # Implements: REQ-d00254-Z
                declared_path = _file_url_path(t.get("url"))
                tests[t.get("id")] = {
                    "name": t.get("name", ""),
                    "suiteID": t.get("suiteID"),
                    "line": t.get("line"),
                    "declared_path": declared_path,
                    "root_line": None if declared_path else t.get("root_line"),
                    "root_path": None if declared_path else _file_url_path(t.get("root_url")),
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
                runner = suites.get(meta["suiteID"], "")
                results.append(
                    {
                        # Implements: REQ-d00294-B
                        # This reporter reads a runner's stream, so there is
                        # no artifact to name. The position among the results
                        # read from the stream is what separates one run of a
                        # test from another.
                        "ordinal": len(results) + 1,
                        "name": meta["name"],
                        "classname": "",
                        "status": status,
                        "duration": 0.0,
                        "message": None,
                        "source_path": meta["declared_path"] or runner,
                        "line": meta["line"],
                        "root_line": meta["root_line"],
                        "root_path": meta["root_path"],
                        # Implements: REQ-d00294-G
                        "runner_path": runner or None,
                        "test_id": None,
                        # This format usually arrives on a runner's output,
                        # where there is no artifact to name. It is also saved
                        # to files and read back by a pattern, and then the
                        # artifact is what separates one run's records from
                        # another's: without it every file's records start
                        # their count again and collide (REQ-d00294-A).
                        "result_file": source_path or None,
                        "result_line": None,
                    }
                )

        # Implements: REQ-d00285-G
        # Output that carried no machine events at all was not a test run this
        # parser read and found empty -- it was output in some other form, and
        # saying so is the difference between "nothing ran" and "the runner
        # was not reporting in the format this target declares".
        if content.strip() and not events:
            self._record_diagnostic(
                source_path,
                "flutter --machine output carried no JSON events",
            )
        return results
