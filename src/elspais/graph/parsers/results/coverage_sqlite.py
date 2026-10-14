"""Python coverage.py native `.coverage` SQLite database parser.

Reads coverage.py's own data file (the default ``.coverage``, written by
``coverage run`` / pytest-cov's ``--cov-context=test``) directly via
coverage.py's PUBLIC API -- **not** by querying the SQLite schema by hand.
The statement set of each file comes from coverage.py's own reporter for
Python source, the one ``Coverage.analysis2`` uses, and the executed lines
from the per-line contexts map where that map is read.
Produces the same per-file dict shape as ``CoverageJsonParser`` (see that
module's docstring) so the factory's coverage-annotation loop needs no
format-specific handling beyond ``can_parse()`` detection.

Rationale: the JSON reporter's ``show_contexts`` option expands the
per-line contexts map into the report, which for a large suite makes the
report and the graph build that reads it enormous. The same context data
lives compactly in the ``.coverage`` SQLite database that coverage.py
already writes.

Does **not** create graph nodes; the factory uses parsed data to annotate
existing FILE nodes.
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Callable

from elspais.graph.parsers.results.diagnostics import DiagnosticRecorder

_log = logging.getLogger(__name__)

_INSTALL_HINT = (
    "coverage-sqlite: 'coverage' package not importable in this interpreter -- "
    "per-test line attribution (code_tested.attributed_lines) will stay 0 and "
    "Code Tested renders 'n/a'. Install with: pip install elspais[coverage]"
)


class CoverageSqliteParser(DiagnosticRecorder):
    """Parser for coverage.py's native `.coverage` SQLite data file.

    Unlike the other reporter-kind parsers, this parser does not consume
    the ``content`` string the factory's ingestion loop would otherwise
    pass in -- the file is binary and cannot be usefully text-decoded. The
    ``binary`` class flag tells the factory to skip the text read and pass
    an empty string; this parser instead reopens the database directly
    from ``source_path`` using coverage.py's public API.
    """

    #: Signals to the factory's ingestion loop that this format is binary
    #: and must not be read via `Path.read_text()`.
    binary = True

    # Implements: REQ-d00285-G
    def parse(
        self,
        content: str,
        source_path: str,
        *,
        wanted_files: Callable[[str], bool] | None = None,
    ) -> dict[str, dict]:
        """Parse a `.coverage` SQLite database into per-file coverage dicts.

        Args:
            content: Unused (binary format; see ``binary`` flag above).
            source_path: Path to the `.coverage` file.
            wanted_files: Optional predicate over measured-file paths. When
                provided, per-line context lists are only materialized for
                files it accepts; rejected files still get
                ``line_coverage``/``executable_lines`` but ``contexts`` stays
                ``None`` and ``contexts_by_lineno()`` is never called for
                them. The contexts map is the suite-scaled part of the data
                (every distinct test context string per executed line), so
                the factory passes a FILE-node-resolution predicate here to
                avoid materializing contexts for measured files that have no
                node in the graph (e.g. test files or out-of-tree sources).

        Returns:
            Dict keyed by source file path (as recorded by coverage.py at
            measurement time -- typically absolute), each value containing:

            - ``line_coverage``: ``dict[int, int]`` -- line to 1 (executed) or 0 (missing)
            - ``executable_lines``: ``int`` -- total statements found by re-parsing the source
            - ``covered_lines``: ``int`` -- executable_lines minus missing lines
            - ``contexts``: ``dict[int, list[str]] | None`` -- per-line test contexts, if any

            Returns an empty dict if the ``coverage`` package is not
            importable, or if the data file cannot be read.
        """
        self._start_diagnostics()

        try:
            import coverage
            from coverage.exceptions import CoverageException
            from coverage.python import PythonFileReporter
        except ImportError:
            _log.warning(_INSTALL_HINT)
            self._record_diagnostic(source_path, _INSTALL_HINT)
            return {}

        # config_file=False: don't pick up ambient [tool.coverage.*] config
        # (e.g. omit/include/source rules) -- we only want this one data file.
        cov = coverage.Coverage(data_file=source_path, config_file=False)
        try:
            cov.load()
        except (CoverageException, OSError, sqlite3.Error) as exc:
            # Implements: REQ-d00285-G
            # sqlite3.Error is defensive: coverage.py currently wraps sqlite
            # errors in DataError (a CoverageException), but a future version
            # letting a bare sqlite3 error escape must not crash the build.
            # A data file that will not load measured nothing as far as the
            # rest of the build can see, which is indistinguishable from a
            # suite run without coverage; record which of the two it was.
            _log.debug("coverage-sqlite: failed to load %s", source_path, exc_info=True)
            self._record_diagnostic(source_path, f"coverage data file did not load: {exc}")
            return {}

        cov_data = cov.get_data()
        results: dict[str, dict] = {}

        for file_path in cov_data.measured_files():
            # Every line a test ran is a key of the per-line contexts map, so
            # where the map is read, the executed lines are taken from it. That
            # decodes each test's line data once; a second call to
            # ``lines()`` would decode all of it again.
            contexts = self._contexts_for(cov_data, file_path, wanted_files)
            if contexts is not None:
                executed = set(contexts)
            else:
                executed = set(cov_data.lines(file_path) or [])
            try:
                reporter = PythonFileReporter(file_path, coverage=cov)
                statements = reporter.lines()
                ran = reporter.translate_lines(executed) & statements
            except (CoverageException, OSError, sqlite3.Error) as exc:
                # Implements: REQ-d00254-P+Q, REQ-d00285-G
                # Re-analysing the source is what produces the statement set;
                # without it there is no denominator and no second source for
                # one. The lines the run executed are still known, so they are
                # kept -- that is P. What must not happen is calling their
                # count the total: every line that never ran would leave the
                # denominator and the file would read as fully covered, which
                # no reader could tell from a real result. So the file is
                # marked unanalysed and contributes no ratio -- that is Q.
                self._record_diagnostic(
                    file_path,
                    f"source could not be re-analysed as Python, so its total "
                    f"line count is unknown: {exc}",
                    partial=True,
                )
                results[file_path] = {
                    "line_coverage": dict.fromkeys(executed, 1),
                    "executable_lines": 0,
                    "covered_lines": len(executed),
                    "contexts": contexts,
                    "source_analysed": False,
                }
                continue

            line_coverage = {ln: (1 if ln in ran else 0) for ln in statements}
            results[file_path] = {
                "line_coverage": line_coverage,
                "executable_lines": len(statements),
                "covered_lines": len(ran),
                "contexts": contexts,
                "source_analysed": True,
            }

        return results

    @staticmethod
    def _contexts_for(cov_data, file_path: str, wanted_files) -> dict[int, list[str]] | None:
        """Per-test contexts for one file, or None where there are none."""
        if wanted_files is not None and not wanted_files(file_path):
            return None
        raw = cov_data.contexts_by_lineno(file_path)
        if not raw:
            return None
        contexts = {ln: ctxs for ln, ctxs in raw.items() if ctxs}
        return contexts or None


def create_parser() -> CoverageSqliteParser:
    """Factory function to create a CoverageSqliteParser.

    Returns:
        New CoverageSqliteParser instance.
    """
    return CoverageSqliteParser()
