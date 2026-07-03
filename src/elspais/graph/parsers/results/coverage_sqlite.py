"""Python coverage.py native `.coverage` SQLite database parser.

Reads coverage.py's own data file (the default ``.coverage``, written by
``coverage run`` / pytest-cov's ``--cov-context=test``) directly via
coverage.py's PUBLIC API -- **not** by querying the SQLite schema by hand.
Produces the same per-file dict shape as ``CoverageJsonParser`` (see that
module's docstring) so the factory's coverage-annotation loop needs no
format-specific handling beyond ``can_parse()`` detection.

Rationale (CUR-1568): the JSON reporter's ``show_contexts`` option expands
the per-line contexts map into the report, which for elspais's own ~4600-test
suite produced a ~9.4 GB coverage.json and ~22 GB-RSS graph builds. The same
context data lives compactly in the ``.coverage`` SQLite database (~5 MB for
this repo) -- coverage.py already wrote it, we just weren't reading it.

Does **not** create graph nodes; the factory uses parsed data to annotate
existing FILE nodes.
"""

from __future__ import annotations

import logging
from pathlib import Path

_log = logging.getLogger(__name__)

# SQLite database file header (first 16 bytes of every valid SQLite file).
_SQLITE_MAGIC = b"SQLite format 3\x00"

_INSTALL_HINT = (
    "coverage-sqlite: 'coverage' package not importable in this interpreter -- "
    "per-test line attribution (code_tested.direct) will stay 0 and Code "
    "Tested renders 'n/a'. Install with: pip install elspais[coverage]"
)


class CoverageSqliteParser:
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

    def parse(self, content: str, source_path: str) -> dict[str, dict]:
        """Parse a `.coverage` SQLite database into per-file coverage dicts.

        Args:
            content: Unused (binary format; see ``binary`` flag above).
            source_path: Path to the `.coverage` file.

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
        try:
            import coverage
            from coverage.exceptions import CoverageException
        except ImportError:
            _log.warning(_INSTALL_HINT)
            return {}

        # config_file=False: don't pick up ambient [tool.coverage.*] config
        # (e.g. omit/include/source rules) -- we only want this one data file.
        cov = coverage.Coverage(data_file=source_path, config_file=False)
        try:
            cov.load()
        except (CoverageException, OSError):
            _log.debug("coverage-sqlite: failed to load %s", source_path, exc_info=True)
            return {}

        cov_data = cov.get_data()
        results: dict[str, dict] = {}

        for file_path in cov_data.measured_files():
            try:
                _, statements, _excluded, missing, _ = cov.analysis2(file_path)
            except (CoverageException, OSError):
                # Source no longer available/parseable (moved, deleted, etc.)
                # -- fall back to executed-lines-only (no missing-line data).
                executed = cov_data.lines(file_path) or []
                statements = list(executed)
                missing = []

            missing_set = set(missing)
            line_coverage = {ln: (0 if ln in missing_set else 1) for ln in statements}
            executable_lines = len(statements)
            covered_lines = executable_lines - len(missing_set)

            raw_contexts = cov_data.contexts_by_lineno(file_path)
            contexts: dict[int, list[str]] | None = None
            if raw_contexts:
                contexts = {ln: ctxs for ln, ctxs in raw_contexts.items() if ctxs}
                if not contexts:
                    contexts = None

            results[file_path] = {
                "line_coverage": line_coverage,
                "executable_lines": executable_lines,
                "covered_lines": covered_lines,
                "contexts": contexts,
            }

        return results

    def can_parse(self, file_path: Path) -> bool:
        """Check if this parser can handle the given file.

        Sniffs the SQLite magic-byte header rather than relying on filename
        (coverage.py's default data-file name is `.coverage`, with no
        extension, and it may carry a parallel-mode suffix like
        `.coverage.hostname.1234`).

        Args:
            file_path: Path to the file.

        Returns:
            True if the file's first 16 bytes are the SQLite 3 file header.
        """
        try:
            with open(file_path, "rb") as fh:
                magic = fh.read(len(_SQLITE_MAGIC))
        except OSError:
            return False
        return magic == _SQLITE_MAGIC


def create_parser() -> CoverageSqliteParser:
    """Factory function to create a CoverageSqliteParser.

    Returns:
        New CoverageSqliteParser instance.
    """
    return CoverageSqliteParser()
