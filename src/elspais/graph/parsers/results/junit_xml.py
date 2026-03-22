"""JUnit XML parser for test results.

This parser extracts test results from JUnit XML format files.
Uses IdResolver.search_regex() for finding requirement IDs in test output.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Any

from elspais.graph.parsers import ParseContext, ParsedContent
from elspais.utilities.test_identity import build_test_id_from_result

# Pattern to extract a named XML attribute value from a raw text line.
_ATTR_RE: dict[str, re.Pattern[str]] = {}


def _attr_value(text: str, attr: str) -> str | None:
    """Extract the value of *attr* from a raw XML element string."""
    pat = _ATTR_RE.get(attr)
    if pat is None:
        pat = re.compile(rf'{attr}="([^"]*)"')
        _ATTR_RE[attr] = pat
    m = pat.search(text)
    return m.group(1) if m else None


if TYPE_CHECKING:
    from elspais.utilities.patterns import IdResolver


# Implements: REQ-d00082-K
class JUnitXMLParser:
    """Parser for JUnit XML test result files.

    Parses standard JUnit XML format used by pytest, JUnit, and other
    test frameworks.

    Uses IdResolver.search_regex() for finding requirement IDs in text.

    Also implements the LineClaimingParser protocol via ``claim_and_parse()``
    so it can be used in the standard ParserRegistry pipeline.
    """

    priority = 90

    def __init__(
        self,
        resolver: IdResolver | None = None,
        base_path: Path | None = None,
    ) -> None:
        """Initialize JUnitXMLParser with optional configuration.

        Args:
            resolver: IdResolver for ID structure. If None, uses defaults.
            base_path: Base path for resolving file-specific configs.
        """
        self._resolver = resolver
        self._base_path = base_path or Path(".")

    def _get_resolver(self) -> IdResolver:
        """Get IdResolver from instance or create default.

        Returns:
            IdResolver to use for parsing.
        """
        if self._resolver is not None:
            return self._resolver

        from elspais.utilities.patterns import build_resolver

        return build_resolver(
            {
                "project": {"namespace": "REQ"},
                "id-patterns": {
                    "canonical": "{namespace}-{type.letter}{component}",
                    "types": {
                        "prd": {"level": 1, "aliases": {"letter": "p"}},
                        "ops": {"level": 2, "aliases": {"letter": "o"}},
                        "dev": {"level": 3, "aliases": {"letter": "d"}},
                    },
                    "component": {"style": "numeric", "digits": 5},
                },
            }
        )

    # Implements: REQ-d00082-K
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
            - verifies: List of requirement IDs this test verifies
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
                verifies = self._extract_req_ids(f"{classname} {name}", source_path)

                # Generate canonical TEST node ID using test_identity utility
                test_id = build_test_id_from_result(classname, name)

                result = {
                    "id": f"{source_path}:{classname}::{name}",
                    "name": name,
                    "classname": classname,
                    "status": status,
                    "duration": duration,
                    "message": message[:200] if message else None,
                    "verifies": verifies,
                    "source_path": source_path,
                    "test_id": test_id,
                }

                results.append(result)

        return results

    # Implements: REQ-d00054-A
    def claim_and_parse(
        self,
        lines: list[tuple[int, str]],
        context: ParseContext,
    ) -> Iterator[ParsedContent]:
        """Claim and parse JUnit XML content via the standard pipeline.

        Reassembles lines into full XML content, delegates to ``parse()``,
        and yields ``ParsedContent`` for each test result.

        When the XML is pretty-printed (one ``<testcase`` per line), each
        result gets the line number of its ``<testcase`` element.  When the
        XML is minified (single line), all results share line 1.

        Args:
            lines: List of (line_number, content) tuples.
            context: Parsing context with file info.

        Yields:
            ParsedContent for each test result found.
        """
        content = "\n".join(text for _, text in lines)
        results = self.parse(content, context.file_path)

        # Build a line-number index: (classname, name) -> file line number.
        # Works when the XML is pretty-printed so each <testcase is on its
        # own line; falls back to first-line when minified.
        tc_lines: dict[tuple[str, str], int] = {}
        base_line = lines[0][0] if lines else 1
        for line_no, text in lines:
            if "<testcase " in text:
                # Extract classname and name from the raw XML line
                cn = _attr_value(text, "classname")
                nm = _attr_value(text, "name")
                if cn is not None and nm is not None:
                    tc_lines[(cn, nm)] = line_no

        for result in results:
            key = (result.get("classname", ""), result.get("name", ""))
            start = tc_lines.get(key, base_line)
            yield ParsedContent(
                content_type="test_result",
                start_line=start,
                end_line=start,
                raw_text="",
                parsed_data=result,
            )

    # Implements: REQ-d00082-K
    def _extract_req_ids(self, text: str, source_file: str | None = None) -> list[str]:
        """Extract requirement IDs from text.

        Args:
            text: Text to search for requirement IDs.
            source_file: Optional source file for file-specific config (unused, kept for API).

        Returns:
            List of normalized requirement IDs (using hyphens).
        """
        resolver = self._get_resolver()
        pattern = resolver.search_regex()

        ids: list[str] = []
        for m in pattern.finditer(text):
            normalized = resolver.normalize_ref(m.group(0))
            if normalized and normalized not in ids:
                ids.append(normalized)

        return ids

    # Implements: REQ-d00054-A
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


def create_parser(
    resolver: IdResolver | None = None,
    base_path: Path | None = None,
) -> JUnitXMLParser:
    """Factory function to create a JUnitXMLParser.

    Args:
        resolver: Optional IdResolver for ID structure.
        base_path: Optional base path for resolving file paths.

    Returns:
        New JUnitXMLParser instance.
    """
    return JUnitXMLParser(resolver, base_path)
