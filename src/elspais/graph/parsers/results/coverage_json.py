"""Python coverage.json parser.

Parses JSON coverage reports produced by ``coverage json`` (from coverage.py)
into per-file line coverage dictionaries.  Supports both aggregate format and
per-context format (``coverage run --context``).  Does **not** create graph
nodes; the factory uses parsed data to annotate existing FILE nodes.
"""

from __future__ import annotations

import json
from pathlib import Path


class CoverageJsonParser:
    """Parser for Python coverage.json format coverage reports.

    Handles both aggregate reports (no contexts) and per-context reports
    produced with ``coverage run --context=<name>``.
    """

    def parse(self, content: str, source_path: str) -> dict[str, dict]:
        """Parse coverage.json into per-file coverage dicts.

        Args:
            content: Raw JSON file content.
            source_path: Path to the coverage file (for diagnostics; unused).

        Returns:
            Dict keyed by source file path, each value containing:

            - ``line_coverage``: ``dict[int, int]`` — line to 1 (executed) or 0 (missing)
            - ``executable_lines``: ``int`` — from summary.num_statements, or computed
            - ``covered_lines``: ``int`` — from summary.covered_lines, or computed
            - ``contexts``: ``dict[int, list[str]] | None`` — per-line test contexts, if available
        """
        try:
            data = json.loads(content)
        except (json.JSONDecodeError, ValueError):
            return {}

        files = data.get("files")
        if not isinstance(files, dict):
            return {}

        results: dict[str, dict] = {}

        for file_path, file_data in files.items():
            executed = file_data.get("executed_lines", [])
            missing = file_data.get("missing_lines", [])

            line_coverage: dict[int, int] = {}
            for line_no in executed:
                line_coverage[line_no] = 1
            for line_no in missing:
                line_coverage[line_no] = 0

            # Extract summary or compute from line lists
            summary = file_data.get("summary", {})
            executable_lines = summary.get(
                "num_statements", len(executed) + len(missing)
            )
            covered_lines = summary.get("covered_lines", len(executed))

            # Parse contexts if present
            raw_contexts = file_data.get("contexts")
            contexts: dict[int, list[str]] | None = None
            if raw_contexts is not None:
                contexts = {int(k): v for k, v in raw_contexts.items()}

            results[file_path] = {
                "line_coverage": line_coverage,
                "executable_lines": executable_lines,
                "covered_lines": covered_lines,
                "contexts": contexts,
            }

        return results

    def can_parse(self, file_path: Path) -> bool:
        """Check if this parser can handle the given file.

        Returns True for ``.json`` files with ``coverage`` in the filename.

        Args:
            file_path: Path to the file.

        Returns:
            True if the file looks like a Python coverage JSON report.
        """
        name = file_path.name.lower()
        return file_path.suffix.lower() == ".json" and "coverage" in name


def create_parser() -> CoverageJsonParser:
    """Factory function to create a CoverageJsonParser.

    Returns:
        New CoverageJsonParser instance.
    """
    return CoverageJsonParser()
