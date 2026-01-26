"""JUnit XML parser for test results.

This parser extracts test results from JUnit XML format files.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


class JUnitXMLParser:
    """Parser for JUnit XML test result files.

    Parses standard JUnit XML format used by pytest, JUnit, and other
    test frameworks.
    """

    # Pattern for requirement IDs in test names (handles both hyphens and underscores)
    REQ_PATTERN = re.compile(
        r"REQ[-_]([A-Za-z]?\d+(?:[-_][A-Z])?)|"  # REQ-p00001, REQ_d00001, REQ-p00001-A
        r"REQ[-_]([A-Z]+[-_][a-z]\d+(?:[-_][A-Z])?)",  # REQ-CAL-d00001
        re.IGNORECASE,
    )

    def parse(self, content: str, source_path: str) -> list[dict[str, Any]]:
        """Parse JUnit XML content and return test result dicts.

        Args:
            content: XML file content.
            source_path: Path to the source file.

        Returns:
            List of test result dictionaries with keys:
            - id: Unique test ID
            - name: Test name
            - classname: Test class name
            - status: passed, failed, skipped, or error
            - duration: Test duration in seconds
            - message: Error/failure message (if any)
            - validates: List of requirement IDs this test validates
        """
        results: list[dict[str, Any]] = []

        try:
            root = ET.fromstring(content)
        except ET.ParseError:
            return results

        # Handle both <testsuites> and <testsuite> as root
        testsuites = root.findall(".//testsuite")
        if not testsuites and root.tag == "testsuite":
            testsuites = [root]

        for testsuite in testsuites:
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
                    message = failure.get("message") or failure.text
                elif error is not None:
                    status = "error"
                    message = error.get("message") or error.text
                elif skipped is not None:
                    status = "skipped"
                    message = skipped.get("message") or skipped.text

                # Extract requirement references from test name or classname
                validates = self._extract_req_ids(f"{classname} {name}")

                result = {
                    "id": f"{source_path}:{classname}::{name}",
                    "name": name,
                    "classname": classname,
                    "status": status,
                    "duration": duration,
                    "message": message[:200] if message else None,
                    "validates": validates,
                    "source_path": source_path,
                }

                results.append(result)

        return results

    def _extract_req_ids(self, text: str) -> list[str]:
        """Extract requirement IDs from text.

        Args:
            text: Text to search for requirement IDs.

        Returns:
            List of normalized requirement IDs (using hyphens).
        """
        req_ids = []

        # Find all REQ-xxx patterns
        # Assertion suffix must be a single uppercase letter NOT followed by lowercase
        # This prevents matching REQ_p00001_login as REQ-p00001-l
        for match in re.finditer(
            r"REQ[-_]([A-Za-z]?\d+(?:[-_][A-Z](?![a-z]))?)",
            text,
            re.IGNORECASE,
        ):
            # Normalize: replace underscores with hyphens
            req_id = f"REQ-{match.group(1).replace('_', '-')}"
            if req_id not in req_ids:
                req_ids.append(req_id)

        return req_ids

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


def create_parser() -> JUnitXMLParser:
    """Factory function to create a JUnitXMLParser.

    Returns:
        New JUnitXMLParser instance.
    """
    return JUnitXMLParser()
