"""JUnit XML parser for test results.

This parser extracts test results from JUnit XML format files
and produces TraceNode instances.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from elspais.core.graph import SourceLocation, TestResult, TraceNode
    from elspais.core.graph_schema import NodeTypeSchema


class JUnitXMLParser:
    """Parser for JUnit XML test result files.

    Parses standard JUnit XML format used by pytest, JUnit, and other
    test frameworks.
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
        """Parse JUnit XML content and return nodes.

        Args:
            content: XML file content.
            source: Source location for the file.
            schema: Schema for this node type.

        Returns:
            List of parsed TraceNodes for test results.
        """
        from elspais.core.graph import NodeKind, SourceLocation, TestResult, TraceNode

        nodes: list[TraceNode] = []

        try:
            root = ET.fromstring(content)
        except ET.ParseError:
            return nodes

        # Handle both <testsuites> and <testsuite> as root
        testsuites = root.findall(".//testsuite")
        if not testsuites and root.tag == "testsuite":
            testsuites = [root]

        for testsuite in testsuites:
            testsuite.get("name", "")

            for testcase in testsuite.findall("testcase"):
                name = testcase.get("name", "")
                classname = testcase.get("classname", "")
                time_str = testcase.get("time", "0")

                try:
                    duration = float(time_str)
                except ValueError:
                    duration = 0.0

                # Determine status
                status = "passed"
                message = None

                failure = testcase.find("failure")
                error = testcase.find("error")
                skipped = testcase.find("skipped")

                if failure is not None:
                    status = "failed"
                    message = failure.get("message", failure.text)
                elif error is not None:
                    status = "error"
                    message = error.get("message", error.text)
                elif skipped is not None:
                    status = "skipped"
                    message = skipped.get("message", skipped.text)

                # Extract requirement references from test name or classname
                req_ids = self.REQ_PATTERN.findall(f"{classname} {name}")

                test_result = TestResult(
                    status=status,
                    duration=duration,
                    message=message[:200] if message else None,
                    result_file=source.path,
                )

                # Create a node for the test result
                node_id = f"{source.path}:{classname}::{name}"
                node = TraceNode(
                    id=node_id,
                    kind=NodeKind.TEST_RESULT,
                    label=self._format_label(test_result, name, schema),
                    source=SourceLocation(
                        path=source.path,
                        line=1,  # XML doesn't have meaningful line numbers
                        repo=source.repo,
                    ),
                    test_result=test_result,
                )

                # Store test reference info for linking
                # Normalize IDs to use hyphens consistently
                node.metrics["test_name"] = name
                node.metrics["test_class"] = classname
                node.metrics["_validates_targets"] = [r.replace("_", "-") for r in req_ids]

                nodes.append(node)

        return nodes

    def can_parse(self, file_path: Path) -> bool:
        """Check if this parser can handle the given file.

        Args:
            file_path: Path to the file.

        Returns:
            True for XML files that look like JUnit results.
        """
        name = file_path.name.lower()
        return file_path.suffix.lower() == ".xml" and (
            "junit" in name or "test" in name or "result" in name
        )

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


def create_parser() -> JUnitXMLParser:
    """Factory function to create a JUnitXMLParser.

    Returns:
        New JUnitXMLParser instance.
    """
    return JUnitXMLParser()
