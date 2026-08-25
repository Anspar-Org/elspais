"""What a results parser detected in an artifact and could not turn into a record.

A results artifact that will not parse and a test run that never happened
produce the same thing downstream: no results. The two are not the same
condition, and a reader deciding whether a requirement is untested has to be
able to tell them apart. Each parser records what it declined to read and why
here, and the caller reading the artifact lifts those records onto the graph.

The record stays deliberately small -- a path, a cause, and a line where the
format gives one. It says what was withheld, not what the caller should do
about it; the caller knows which target, which repository and which stage of
ingestion it was reading for, and none of that is the parser's to state.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass


# Implements: REQ-d00285-A, REQ-d00285-G
@dataclass(frozen=True)
class ResultsDiagnostic:
    """Content of a results or coverage artifact that produced no record.

    Attributes:
        path: The artifact the parser was reading, as the caller named it.
        cause: Why the content produced nothing, in the terms the format
            reports it -- an unparseable document, a record whose numbers do
            not read as numbers, a document whose shape the format does not
            admit.
        line: The 1-based line the condition sits on, where the format or the
            underlying error reports one; None where it does not.
    """

    path: str
    cause: str
    line: int | None = None


class DiagnosticRecorder:
    """Records, on a parser, the content it declined to read.

    ``parse()`` calls ``_start_diagnostics()`` before it reads anything, so
    the records belong to that one call: a parser instance reused across
    several artifacts never reports the previous one's conditions against
    this one's path.
    """

    def _start_diagnostics(self) -> None:
        """Begin a fresh parse, discarding any previous parse's records."""
        self._diagnostics: list[ResultsDiagnostic] = []

    def _record_diagnostic(self, path: str, cause: str, line: int | None = None) -> None:
        """Record content this parse produced no record for."""
        if not hasattr(self, "_diagnostics"):
            self._diagnostics = []
        self._diagnostics.append(ResultsDiagnostic(path=path, cause=cause, line=line))

    # Implements: REQ-d00285-G
    def iter_diagnostics(self) -> Iterator[ResultsDiagnostic]:
        """Iterate what the most recent parse declined to read."""
        return iter(getattr(self, "_diagnostics", []))


__all__ = ["DiagnosticRecorder", "ResultsDiagnostic"]
