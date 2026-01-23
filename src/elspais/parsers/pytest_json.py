"""Pytest JSON parser for test results.

This parser extracts test results from pytest JSON format files
(generated with pytest-json-report or similar plugins).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from elspais.core.tree import SourceLocation, TestResult, TraceNode
    from elspais.core.tree_schema import NodeTypeSchema


class PytestJSONParser:
    """Parser for pytest JSON test result files.

    Supports output from pytest-json-report and similar plugins.
    """

    # Pattern for requirement IDs in test names (handles both hyphens and underscores)
    REQ_PATTERN = re.compile(
        r"REQ[-_][A-Za-z]?\d+(?:[-_][A-Z])?|"  # REQ-p00001, REQ_d00001, REQ-p00001-A
        r"REQ[-_][A-Z]+[-_][a-z]\d+(?:[-_][A-Z])?|"  # REQ-CAL-d00001
        r"[A-Z]+[-_]\d+",  # PROJ-123, PROJ_123
        re.IGNORECASE,
    )

    def parse(
        self,
        content: str,
        source: SourceLocation,
        schema: NodeTypeSchema,
    ) -> list[TraceNode]:
        """Parse pytest JSON content and return nodes.

        Args:
            content: JSON file content.
            source: Source location for the file.
            schema: Schema for this node type.

        Returns:
            List of parsed TraceNodes for test results.
        """
        from elspais.core.tree import NodeKind, SourceLocation, TestResult, TraceNode

        nodes: list[TraceNode] = []

        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            return nodes

        # Handle different JSON structures
        tests = self._extract_tests(data)

        for test in tests:
            name = test.get("name", test.get("nodeid", "unknown"))
            outcome = test.get("outcome", test.get("status", "unknown"))
            duration = test.get("duration", test.get("time", 0))

            # Normalize outcome
            status = self._normalize_status(outcome)

            # Extract message from call or longrepr
            message = self._extract_message(test)

            # Extract requirement references from test name
            req_ids = self.REQ_PATTERN.findall(name)

            # Extract class and method from nodeid
            classname, testname = self._parse_nodeid(name)

            test_result = TestResult(
                status=status,
                duration=duration,
                message=message[:200] if message else None,
                result_file=source.path,
            )

            node_id = f"{source.path}:{name}"
            node = TraceNode(
                id=node_id,
                kind=NodeKind.TEST_RESULT,
                label=self._format_label(test_result, testname, schema),
                source=SourceLocation(
                    path=source.path,
                    line=test.get("lineno", 1),
                    repo=source.repo,
                ),
                test_result=test_result,
            )

            # Store test reference info for linking
            # Normalize IDs to use hyphens consistently
            node.metrics["test_name"] = testname
            node.metrics["test_class"] = classname
            node.metrics["_validates_targets"] = [r.upper().replace("_", "-") for r in req_ids]

            nodes.append(node)

        return nodes

    def can_parse(self, file_path: Path) -> bool:
        """Check if this parser can handle the given file.

        Args:
            file_path: Path to the file.

        Returns:
            True for JSON files that look like pytest results.
        """
        name = file_path.name.lower()
        return file_path.suffix.lower() == ".json" and (
            "pytest" in name or "test" in name or "result" in name
        )

    def _extract_tests(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract test entries from various JSON structures.

        Args:
            data: Parsed JSON data.

        Returns:
            List of test dictionaries.
        """
        # pytest-json-report structure
        if "tests" in data:
            return data["tests"]

        # pytest-json structure
        if "report" in data and "tests" in data["report"]:
            return data["report"]["tests"]

        # Array of tests
        if isinstance(data, list):
            return data

        # Single test or wrapped structure
        if "nodeid" in data or "name" in data:
            return [data]

        return []

    def _normalize_status(self, outcome: str) -> str:
        """Normalize outcome string to standard status.

        Args:
            outcome: Raw outcome string.

        Returns:
            Normalized status (passed, failed, skipped, error).
        """
        outcome = outcome.lower()
        if outcome in ("passed", "pass", "success"):
            return "passed"
        if outcome in ("failed", "fail", "failure"):
            return "failed"
        if outcome in ("skipped", "skip", "xfail", "xpass"):
            return "skipped"
        if outcome in ("error", "broken"):
            return "error"
        return outcome

    def _extract_message(self, test: dict[str, Any]) -> str | None:
        """Extract failure/error message from test entry.

        Args:
            test: Test dictionary.

        Returns:
            Error message if available.
        """
        # pytest-json-report structure
        if "call" in test and isinstance(test["call"], dict):
            call = test["call"]
            if "longrepr" in call:
                return str(call["longrepr"])
            if "crash" in call:
                return str(call["crash"])

        # Direct longrepr
        if "longrepr" in test:
            return str(test["longrepr"])

        # Message field
        if "message" in test:
            return str(test["message"])

        return None

    def _parse_nodeid(self, nodeid: str) -> tuple[str | None, str]:
        """Parse pytest nodeid into class and method names.

        Args:
            nodeid: Pytest nodeid (e.g., "tests/test_foo.py::TestClass::test_method")

        Returns:
            Tuple of (classname, testname).
        """
        parts = nodeid.split("::")

        if len(parts) >= 3:
            # File::Class::Method
            return parts[-2], parts[-1]
        if len(parts) == 2:
            # File::Method (no class)
            return None, parts[-1]
        return None, nodeid

    def _format_label(self, result: TestResult, name: str, schema: NodeTypeSchema) -> str:
        """Format a label using the schema template.

        Args:
            result: TestResult to format.
            name: Test name.
            schema: Schema for this node type.

        Returns:
            Formatted label string.
        """
        try:
            duration_ms = int(result.duration * 1000) if result.duration else 0
            return schema.label_template.format(
                status=result.status,
                duration=duration_ms,
                name=name,
            )
        except (KeyError, AttributeError):
            return f"{result.status}: {name}"


def create_parser() -> PytestJSONParser:
    """Factory function to create a PytestJSONParser.

    Returns:
        New PytestJSONParser instance.
    """
    return PytestJSONParser()
