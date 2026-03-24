"""LCOV coverage report parser.

Parses LCOV format coverage reports (e.g., from ``flutter test --coverage``)
into per-file line coverage dictionaries.  Does **not** create graph nodes;
the factory uses parsed data to annotate existing FILE nodes.
"""

from __future__ import annotations

from pathlib import Path


class LcovParser:
    """Parser for LCOV format coverage report files.

    Handles the standard LCOV records: SF (source file), DA (line data),
    LF (lines found), LH (lines hit), and end_of_record.  Unknown
    prefixes (FN, FNDA, BRDA, BRF, BRH, TN, etc.) are silently ignored.
    """

    def parse(self, content: str, source_path: str) -> dict[str, dict]:
        """Parse LCOV content into per-file coverage dicts.

        Args:
            content: Raw LCOV file content.
            source_path: Path to the LCOV file (for diagnostics; unused).

        Returns:
            Dict keyed by source file path, each value containing:

            - ``line_coverage``: ``dict[int, int]`` — line number to hit count
            - ``executable_lines``: ``int`` — from LF, or count of DA lines
            - ``covered_lines``: ``int`` — from LH, or count of DA with hit > 0
        """
        results: dict[str, dict] = {}

        current_file: str | None = None
        line_coverage: dict[int, int] = {}
        lf: int | None = None
        lh: int | None = None

        for raw_line in content.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            if line.startswith("SF:"):
                current_file = line[3:]
                line_coverage = {}
                lf = None
                lh = None

            elif line.startswith("DA:"):
                parts = line[3:].split(",", 1)
                if len(parts) == 2:
                    try:
                        line_no = int(parts[0])
                        hit_count = int(parts[1])
                        line_coverage[line_no] = hit_count
                    except ValueError:
                        pass

            elif line.startswith("LF:"):
                try:
                    lf = int(line[3:])
                except ValueError:
                    pass

            elif line.startswith("LH:"):
                try:
                    lh = int(line[3:])
                except ValueError:
                    pass

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
