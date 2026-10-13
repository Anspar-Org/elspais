"""Parser for the result lines of an *Evidence Snapshot*'s `results.jsonl`.

Each line is one result as `elspais evidence write` recorded it: the target,
the repo-relative file and line that declare the test, the test name, the
file that executed it where that differs, the outcome, and a skip reason
where one was given. A record reads those fields back in the shape every
results parser emits.

The build hands this parser one target's lines, each carrying an added
``_line``: its 1-based line number in `results.jsonl`. That number is the
record's ordinal and its ``result_line``, so each result is placed in the
snapshot file it came from. A line read without ``_line`` is placed by its
position in the text read.

A snapshot records no duration, so every record carries none.

The same lines, carrying the run that executed each test and why a later run
retained its result, are the *Retained Results* a run writes into its output
area. This parser reads both, and passes those two keys through.
"""

from __future__ import annotations

import json
from typing import Any

from elspais.graph.parsers.results.diagnostics import DiagnosticRecorder
from elspais.utilities.evidence import SnapshotUnreadable, read_result_line, split_lines


# Implements: REQ-d00322-J
class EvidenceSnapshotParser(DiagnosticRecorder):
    def parse(self, content: str, source_path: str = "") -> list[dict[str, Any]]:
        self._start_diagnostics()
        records: list[dict[str, Any]] = []
        for number, text in enumerate(split_lines(content), start=1):
            if not text.strip():
                continue
            try:
                row = json.loads(text)
            except ValueError as exc:
                self._record_diagnostic(source_path, f"not valid JSON: {exc}", number)
                continue
            line = row.pop("_line", number) if isinstance(row, dict) else number
            try:
                result = read_result_line(row, source=source_path, number=number)
            except SnapshotUnreadable as exc:
                self._record_diagnostic(source_path, exc.reason, number)
                continue
            record: dict[str, Any] = {}
            # Implements: REQ-d00323-M
            # A Retained Result names the run that executed its test.
            if result.executed_in is not None:
                record["executed_in"] = result.executed_in
                record["retained_reason"] = result.retained_reason or ""
            records.append(
                record
                | {
                    "ordinal": line,
                    "name": result.name,
                    "classname": "",
                    "status": result.outcome,
                    "duration": 0.0,
                    "message": result.skip_reason,
                    "source_path": result.file,
                    "line": result.line,
                    "root_line": None,
                    "root_path": None,
                    "runner_path": result.runner,
                    "test_id": None,
                    "result_file": source_path or None,
                    "result_line": line,
                }
            )
        return records
