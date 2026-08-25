"""LCOV coverage report parser.

Parses LCOV format coverage reports (e.g., from ``flutter test --coverage``)
into per-file line coverage dictionaries.  Does **not** create graph nodes;
the factory uses parsed data to annotate existing FILE nodes.
"""

from __future__ import annotations

from pathlib import Path

from elspais.graph.parsers.results.diagnostics import DiagnosticRecorder


class LcovParser(DiagnosticRecorder):
    """Parser for LCOV format coverage report files.

    Handles the standard LCOV records: SF (source file), DA (line data),
    LF (lines found), LH (lines hit), and end_of_record.  Prefixes carrying
    function and branch data (FN, FNDA, BRDA, BRF, BRH, TN, etc.) are passed
    over deliberately and not recorded as conditions: this tool measures
    lines, so a record describing something else is not content it declined
    to read but content it has no question about.
    """

    def parse(self, content: str, source_path: str) -> dict[str, dict]:
        """Parse LCOV content into per-file coverage dicts.

        Args:
            content: Raw LCOV file content.
            source_path: Path to the LCOV file; names the artifact in any
                diagnostic this parse records.

        Returns:
            Dict keyed by source file path, each value containing:

            - ``line_coverage``: ``dict[int, int]`` — line number to hit count
            - ``executable_lines``: ``int`` — from LF, or count of DA lines
            - ``covered_lines``: ``int`` — from LH, or count of DA with hit > 0
        """
        results: dict[str, dict] = {}
        self._start_diagnostics()
        saw_source_file = False

        current_file: str | None = None
        line_coverage: dict[int, int] = {}
        lf: int | None = None
        lh: int | None = None

        for line_no, raw_line in enumerate(content.splitlines(), start=1):
            line = raw_line.strip()
            if not line:
                continue

            if line.startswith("SF:"):
                saw_source_file = True
                current_file = line[3:]
                line_coverage = {}
                lf = None
                lh = None

            elif line.startswith("DA:"):
                parts = line[3:].split(",", 1)
                # Implements: REQ-d00285-G
                # A DA record the format cannot read leaves its line
                # unmeasured, and an unmeasured line reads as an uncovered
                # one. Record the record rather than dropping it.
                if len(parts) != 2:
                    self._record_diagnostic(
                        source_path,
                        f"LCOV DA record is not 'line,hits': {line!r}",
                        line=line_no,
                    )
                else:
                    try:
                        source_line = int(parts[0])
                        hit_count = int(parts[1])
                    except ValueError:
                        self._record_diagnostic(
                            source_path,
                            f"LCOV DA record does not read as numbers: {line!r}",
                            line=line_no,
                        )
                    else:
                        line_coverage[source_line] = hit_count

            elif line.startswith("LF:"):
                try:
                    lf = int(line[3:])
                except ValueError:
                    # Implements: REQ-d00285-G
                    self._record_diagnostic(
                        source_path,
                        f"LCOV LF record does not read as a number: {line!r}",
                        line=line_no,
                    )

            elif line.startswith("LH:"):
                try:
                    lh = int(line[3:])
                except ValueError:
                    # Implements: REQ-d00285-G
                    self._record_diagnostic(
                        source_path,
                        f"LCOV LH record does not read as a number: {line!r}",
                        line=line_no,
                    )

            elif line == "end_of_record":
                if current_file is not None:
                    executable = lf if lf is not None else len(line_coverage)
                    covered = (
                        lh if lh is not None else sum(1 for v in line_coverage.values() if v > 0)
                    )
                    results[current_file] = {
                        "line_coverage": dict(line_coverage),
                        "executable_lines": executable,
                        "covered_lines": covered,
                    }
                current_file = None
                line_coverage = {}
                lf = None
                lh = None

        # Implements: REQ-d00285-G
        # A file holding no SF record measured nothing, and an unmeasured
        # tree and an unread report are the same empty dict downstream.
        if content.strip() and not saw_source_file:
            self._record_diagnostic(
                source_path,
                "LCOV file holds no SF record, so it names no measured source file",
            )

        return results

    def can_parse(self, file_path: Path) -> bool:
        """Check if this parser can handle the given file.

        Returns True for ``.info`` files or filenames containing ``lcov``.

        Args:
            file_path: Path to the file.

        Returns:
            True if the file looks like an LCOV coverage report.
        """
        name = file_path.name.lower()
        return file_path.suffix.lower() == ".info" or "lcov" in name


def create_parser() -> LcovParser:
    """Factory function to create an LcovParser.

    Returns:
        New LcovParser instance.
    """
    return LcovParser()
