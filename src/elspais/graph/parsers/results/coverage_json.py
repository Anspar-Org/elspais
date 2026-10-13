"""Python coverage.json parser.

Parses JSON coverage reports produced by ``coverage json`` (from coverage.py)
into per-file line coverage dictionaries.  Supports both aggregate format and
per-context format (``coverage run --context``).  Does **not** create graph
nodes; the factory uses parsed data to annotate existing FILE nodes.
"""

from __future__ import annotations

import json
from pathlib import Path

from elspais.graph.parsers.results.diagnostics import DiagnosticRecorder


class CoverageJsonParser(DiagnosticRecorder):
    """Parser for Python coverage.json format coverage reports.

    Handles both aggregate reports (no contexts) and per-context reports
    produced with ``coverage run --context=<name>``.
    """

    # Implements: REQ-d00285-G
    def parse(self, content: str, source_path: str) -> dict[str, dict]:
        """Parse coverage.json into per-file coverage dicts.

        Args:
            content: Raw JSON file content.
            source_path: Path to the coverage file; names the artifact in any
                diagnostic this parse records.

        Returns:
            Dict keyed by source file path, each value containing:

            - ``line_coverage``: ``dict[int, int]`` — line to 1 (executed) or 0 (missing)
            - ``executable_lines``: ``int`` — from summary.num_statements, or computed
            - ``covered_lines``: ``int`` — from summary.covered_lines, or computed
            - ``contexts``: ``dict[int, list[str]] | None`` — per-line test contexts, if available
        """
        self._start_diagnostics()

        try:
            data = json.loads(content)
        except (json.JSONDecodeError, ValueError) as exc:
            # A coverage report that will not parse leaves every file it
            # measured unmeasured, which reads downstream exactly like a run
            # with no coverage at all. Record which one happened.
            self._record_diagnostic(
                source_path,
                f"coverage JSON did not parse: {exc}",
                line=getattr(exc, "lineno", None),
            )
            return {}

        files = data.get("files") if isinstance(data, dict) else None
        if not isinstance(files, dict):
            # Implements: REQ-d00285-G
            self._record_diagnostic(
                source_path,
                "coverage JSON parsed but holds no 'files' mapping",
            )
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
            executable_lines = summary.get("num_statements", len(executed) + len(missing))
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
            # Implements: REQ-d00333-J+L
            # Coverage a run retained records the digest of the file it
            # measured and the runs that measured it.
            provenance = file_data.get("elspais")
            if isinstance(provenance, dict):
                results[file_path]["provenance"] = provenance

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


# Implements: REQ-d00333-J
def render_coverage_json(readings: dict[str, dict]) -> str:
    """Write per-file readings, in the shape :meth:`CoverageJsonParser.parse` returns, as JSON.

    The parser reads the text back to the same readings, provenance included.
    """
    files: dict[str, dict] = {}
    for path in sorted(readings):
        data = readings[path]
        lines = data.get("line_coverage") or {}
        entry: dict = {
            "executed_lines": sorted(int(n) for n, hit in lines.items() if hit),
            "missing_lines": sorted(int(n) for n, hit in lines.items() if not hit),
            "summary": {
                "num_statements": data.get("executable_lines", len(lines)),
                "covered_lines": sum(1 for hit in lines.values() if hit),
            },
        }
        if data.get("contexts"):
            entry["contexts"] = {str(n): list(c) for n, c in sorted(data["contexts"].items())}
        if data.get("provenance"):
            entry["elspais"] = data["provenance"]
        files[path] = entry
    return json.dumps({"files": files}, indent=1, sort_keys=True) + "\n"


# Implements: REQ-d00333-J+L
def merge_readings(a: dict | None, b: dict | None) -> dict:
    """One file's line coverage from two readings of it, keeping both provenances.

    A line counts the most hits either reading gives it, and holds every test
    context either recorded. The executable count is the larger. The runs
    that measured either reading are named once each, in order. Where only
    one reading exists it is returned as it is.
    """
    if not a or not b:
        return dict(a or b or {})
    lines = dict(a.get("line_coverage") or {})
    for line, hit in (b.get("line_coverage") or {}).items():
        lines[line] = max(lines.get(line, 0), hit)
    contexts: dict[int, list[str]] | None = None
    if a.get("contexts") or b.get("contexts"):
        contexts = {}
        for reading in (a, b):
            for line, names in (reading.get("contexts") or {}).items():
                contexts[line] = sorted(set(contexts.get(line, [])) | set(names))
    runs: list[dict] = []
    for reading in (a, b):
        for run in (reading.get("provenance") or {}).get("measured_in", []):
            if run not in runs:
                runs.append(run)
    provenance = dict(a.get("provenance") or b.get("provenance") or {})
    if runs:
        provenance["measured_in"] = runs
    out = {
        **a,
        "line_coverage": lines,
        "executable_lines": max(a.get("executable_lines", 0), b.get("executable_lines", 0)),
        "covered_lines": sum(1 for hit in lines.values() if hit),
        "contexts": contexts,
    }
    if provenance:
        out["provenance"] = provenance
    return out


def create_parser() -> CoverageJsonParser:
    """Factory function to create a CoverageJsonParser.

    Returns:
        New CoverageJsonParser instance.
    """
    return CoverageJsonParser()
