"""Parser for `flutter test --machine` newline-delimited JSON events.

Builds RESULT records carrying the test file's real path (from ``suite.path``)
and each test's identity within it (name, line).

Record shape mirrors sibling parsers (junit_xml, pytest_json):
``{"ordinal", "name", "classname", "status", "duration", "message",
"source_path", "line", "root_path", "root_line", "test_id"}``.

``line`` is the machine event's ``test.line``, counted from one, as the tool
counts source lines. For a plain ``test()`` call it is the user's call site.
For ``testWidgets(...)`` the framework reports a wrapper line instead (inside
``package:flutter_test/src/widget_tester.dart``), which names no line of the
user's file; the call site is then in ``test.root_line`` / ``test.root_url``.
Both are carried so the builder can try ``(source_path, line)`` and fall back
to ``(root_path, root_line)``.

``test_id`` is always ``None``: which test a result belongs to is answered at
graph-build time from the file and line, so nothing needs to be pre-baked.

Suite-loader pseudo-tests (``hidden: true`` in ``testDone``) are skipped. An
``error`` event reaches the result of the test it names, even after that
test's ``testDone``; a test started and never finished is recorded as
failing, and a stream ending before its ``done`` event is reported.
"""

from __future__ import annotations

import json
from typing import Any

from elspais.graph.parsers.results.diagnostics import DiagnosticRecorder


class _Run:
    """What one `flutter test --machine` run has said so far.

    Suite and test identifiers are numbered afresh by every run, so they are
    only ever read against the run that issued them.
    """

    def __init__(self) -> None:
        self.events = 0
        self.suites: dict[Any, str] = {}  # suiteID -> path
        self.tests: dict[Any, dict[str, Any]] = {}  # testID -> {name, suiteID, line}
        # testID -> the record written for it, so an error the runner reports
        # after the test's testDone still reaches that test's own result.
        self.recorded: dict[Any, dict[str, Any]] = {}
        # testID -> error text reported before its testDone arrived.
        self.pending_errors: dict[Any, list[str]] = {}
        self.finished: set[Any] = set()
        self.records: list[dict[str, Any]] = []
        self.success: bool | None = None
        self.saw_done = False


# Implements: REQ-d00254-E
class FlutterMachineParser(DiagnosticRecorder):
    # Implements: REQ-d00254-E+Q, REQ-d00294-A+E, REQ-d00285-G
    def parse(self, content: str, source_path: str = "") -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        self._start_diagnostics()
        events = 0
        # Implements: REQ-d00294-A+E
        # One input may hold several runs -- a target whose command runs
        # `flutter test --machine` once per package writes them one after
        # another -- and every run numbers its suites and tests from the
        # start again. Each `start` event opens a run of its own, so an
        # identifier is only ever read within the run that issued it: an
        # error reported in the second run never reaches a test of the first,
        # and the first run's `done` does not stand for the second's.
        run = _Run()

        for lineno, line in enumerate(content.splitlines(), 1):
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
            if etype == "start":
                if run.events:
                    self._finish_run(run, results, source_path)
                    run = _Run()
            run.events += 1
            if etype == "suite":
                s = ev.get("suite", {})
                run.suites[s.get("id")] = s.get("path", "")
            elif etype == "testStart":
                t = ev.get("test", {})
                raw_root_url = t.get("root_url")
                # root_url is a file:///abs/path URL (Dart); strip the scheme prefix to get a path
                if raw_root_url and raw_root_url.startswith("file://"):
                    root_path = raw_root_url[len("file://") :]
                else:
                    root_path = None
                run.tests[t.get("id")] = {
                    "name": t.get("name", ""),
                    "suiteID": t.get("suiteID"),
                    "line": t.get("line"),
                    "root_line": t.get("root_line"),
                    "root_path": root_path,
                }
            elif etype == "error":
                # Implements: REQ-d00294-E
                # package:test reports a test's errors as events of their own:
                # before its testDone (which then reads error/failure), and --
                # as "This test failed after it had already completed." --
                # after it, for an async error or an unawaited future. The
                # runner counts the late one as a failure of that test, so the
                # test's own result is failing and carries why.
                tid = ev.get("testID")
                text = str(ev.get("error") or "").strip()
                rec = run.recorded.get(tid)
                if rec is not None:
                    rec["status"] = "failed"
                    if text:
                        rec["message"] = f"{rec['message']}\n{text}" if rec["message"] else text
                elif tid in run.tests and text:
                    run.pending_errors.setdefault(tid, []).append(text)
            elif etype == "done":
                run.saw_done = True
                run.success = ev.get("success")
            elif etype == "testDone":
                tid = ev.get("testID")
                run.finished.add(tid)
                if ev.get("hidden"):
                    continue
                meta = run.tests.get(tid)
                if meta is None:
                    continue
                if ev.get("skipped"):
                    status = "skipped"
                elif ev.get("result") == "success":
                    status = "passed"
                else:  # "failure" | "error"
                    status = "failed"
                errors = run.pending_errors.pop(tid, [])
                rec = self._record(
                    meta,
                    run.suites,
                    status,
                    "\n".join(errors) or None,
                    len(results) + 1,
                    source_path,
                    # Implements: REQ-d00294-A
                    # Where the stream was saved to an artifact, the line of
                    # this testDone is where the record sits in it, so a
                    # reader can be pointed at the failing record. A runner's
                    # live output has no artifact and so no line.
                    lineno if source_path else None,
                )
                # Implements: REQ-d00254-G
                # package:test reports a test file that failed to load --
                # a compile error, a throw at top level -- as a record of its
                # own named `loading <suite path>`, with no line. None of the
                # file's tests ran, so the record is marked as the failure of
                # the file's loading, which the builder binds to every test
                # scanned in that file rather than to none of them.
                if (
                    status == "failed"
                    and meta["line"] is None
                    and meta["name"] == f"loading {rec['source_path']}"
                ):
                    rec["suite_load_failure"] = True
                results.append(rec)
                run.recorded[tid] = rec
                run.records.append(rec)

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
        if not events:
            return results
        self._finish_run(run, results, source_path)
        return results

    # Implements: REQ-d00254-Q, REQ-d00285-G, REQ-d00294-E
    def _finish_run(self, run: _Run, results: list[dict[str, Any]], source_path: str) -> None:
        """Close one run: its unfinished tests fail, and an incomplete run is reported.

        A test the runner started and never finished did not pass, and a run
        that ends before its `done` event is not a complete run -- a crashed
        flutter_tester, a killed step, an isolate out of memory. Only the end
        of the run can tell that apart from a test nobody selected, so the
        unfinished test is recorded as failing and the truncation is reported
        rather than the test vanishing.
        """
        read_before = bool(results)
        unfinished = [tid for tid in run.tests if tid not in run.finished]
        for tid in unfinished:
            errors = run.pending_errors.pop(tid, [])
            errors.append("started but never finished (runner output ended before its testDone)")
            rec = self._record(
                run.tests[tid],
                run.suites,
                "failed",
                "\n".join(errors),
                len(results) + 1,
                source_path,
                None,
            )
            results.append(rec)
        if unfinished or not run.saw_done:
            names = ", ".join(repr(run.tests[tid]["name"]) for tid in unfinished)
            if not run.saw_done:
                cause = (
                    "flutter --machine output ended without a 'done' event; "
                    "the run did not complete"
                )
            else:
                cause = "flutter --machine run ended with tests it never finished"
            if unfinished:
                cause += f" ({len(unfinished)} test(s) started and never finished: {names})"
            self._record_diagnostic(source_path, cause, partial=bool(run.finished) or read_before)
        elif run.success is False and not any(r["status"] == "failed" for r in run.records):
            # Implements: REQ-d00285-G
            # The runner judged the run failed and no record says why -- a
            # load error, a failure outside every test. Read as it stands the
            # run would be all-passing, so the condition is reported.
            self._record_diagnostic(
                source_path,
                "flutter --machine run reported success=false but no test result failed",
            )

    @staticmethod
    def _record(
        meta: dict[str, Any],
        suites: dict[int, str],
        status: str,
        message: str | None,
        ordinal: int,
        source_path: str,
        result_line: int | None,
    ) -> dict[str, Any]:
        """One result record for the test *meta* describes."""
        return {
            # Implements: REQ-d00294-B
            # This reporter reads a runner's stream, so there is no artifact
            # to name. The position among the results read from the stream is
            # what separates one run of a test from another.
            "ordinal": ordinal,
            "name": meta["name"],
            "classname": "",
            "status": status,
            "duration": 0.0,
            "message": message,
            "source_path": suites.get(meta["suiteID"], ""),
            "line": meta["line"],
            "root_line": meta["root_line"],
            "root_path": meta["root_path"],
            "test_id": None,
            # This format usually arrives on a runner's output, where there is
            # no artifact to name. It is also saved to files and read back by
            # a pattern, and then the artifact is what separates one run's
            # records from another's: without it every file's records start
            # their count again and collide (REQ-d00294-A).
            "result_file": source_path or None,
            "result_line": result_line,
        }
