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
"""

from __future__ import annotations

import json
from typing import Any

from elspais.graph.parsers.results.diagnostics import DiagnosticRecorder
from elspais.utilities.evidence import split_lines


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
            if not isinstance(row, dict):
                self._record_diagnostic(source_path, "not a JSON object", number)
                continue
            missing = [k for k in ("file", "name", "outcome") if k not in row]
            if missing:
                self._record_diagnostic(source_path, f"missing {', '.join(missing)}", number)
                continue
            line = row.get("_line", number)
            records.append(
                {
                    "ordinal": line,
                    "name": row["name"],
                    "classname": "",
                    "status": row["outcome"],
                    "duration": 0.0,
                    "message": row.get("skip_reason"),
                    "source_path": row["file"],
                    "line": row.get("line"),
                    "root_line": None,
                    "root_path": None,
                    "runner_path": row.get("runner"),
                    "test_id": None,
                    "result_file": source_path or None,
                    "result_line": line,
                }
            )
        return records
