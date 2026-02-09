"""JUnit XML parser for test results.

This parser extracts test results from JUnit XML format files.
Uses the shared reference_config infrastructure for configurable patterns.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Any

from elspais.graph.parsers import ParseContext, ParsedContent
from elspais.utilities.reference_config import (
    ReferenceConfig,
    ReferenceResolver,
    extract_ids_from_text,
)
from elspais.utilities.test_identity import build_test_id_from_result

if TYPE_CHECKING:
    from elspais.utilities.patterns import PatternConfig


class JUnitXMLParser:
    """Parser for JUnit XML test result files.

    Parses standard JUnit XML format used by pytest, JUnit, and other
    test frameworks.

    Uses configurable patterns from ReferenceConfig for:
    - Separator characters (- _ etc.)
    - Case sensitivity
    - Prefix requirements

    Also implements the LineClaimingParser protocol via ``claim_and_parse()``
    so it can be used in the standard ParserRegistry pipeline.
    """

    priority = 90

    def __init__(
        self,
        pattern_config: PatternConfig | None = None,
        reference_resolver: ReferenceResolver | None = None,
        base_path: Path | None = None,
    ) -> None:
        """Initialize JUnitXMLParser with optional configuration.

        Args:
            pattern_config: Configuration for ID structure. If None, uses defaults.
            reference_resolver: Resolver for file-specific reference config. If None,
                               uses default ReferenceConfig.
            base_path: Base path for resolving file-specific configs.
        """
        self._pattern_config = pattern_config
        self._reference_resolver = reference_resolver
        self._base_path = base_path or Path(".")

    def _get_pattern_config(self) -> PatternConfig:
        """Get pattern config from instance or create default.

        Returns:
            PatternConfig to use for parsing.
        """
        if self._pattern_config is not None:
            return self._pattern_config

        from elspais.utilities.patterns import PatternConfig

        return PatternConfig.from_dict(
            {
                "prefix": "REQ",
                "types": {
                    "prd": {"id": "p", "name": "PRD"},
                    "ops": {"id": "o", "name": "OPS"},
                    "dev": {"id": "d", "name": "DEV"},
                },
                "id_format": {"style": "numeric", "digits": 5},
            }
        )

    def _get_reference_config(self, source_file: str | None = None) -> ReferenceConfig:
        """Get reference config for the current file.

        Args:
            source_file: Optional source file path for file-specific config.

        Returns:
            ReferenceConfig for parsing.
        """
        if self._reference_resolver is not None and source_file:
            return self._reference_resolver.resolve(Path(source_file), self._base_path)

        if self._reference_resolver is not None:
            return self._reference_resolver.defaults

        return ReferenceConfig()

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
                validates = self._extract_req_ids(f"{classname} {name}", source_path)

                # Generate canonical TEST node ID using test_identity utility
                test_id = build_test_id_from_result(classname, name)

                result = {
                    "id": f"{source_path}:{classname}::{name}",
                    "name": name,
                    "classname": classname,
                    "status": status,
                    "duration": duration,
                    "message": message[:200] if message else None,
                    "validates": validates,
                    "source_path": source_path,
                    "test_id": test_id,
                }

                results.append(result)

        return results

    def claim_and_parse(
        self,
        lines: list[tuple[int, str]],
        context: ParseContext,
    ) -> Iterator[ParsedContent]:
        """Claim and parse JUnit XML content via the standard pipeline.

        Reassembles lines into full XML content, delegates to ``parse()``,
        and yields ``ParsedContent`` for each test result.

        Args:
            lines: List of (line_number, content) tuples.
            context: Parsing context with file info.

        Yields:
            ParsedContent for each test result found.
        """
        content = "\n".join(text for _, text in lines)
        results = self.parse(content, context.file_path)
        for result in results:
            yield ParsedContent(
                content_type="test_result",
                start_line=lines[0][0] if lines else 1,
                end_line=lines[-1][0] if lines else 1,
                raw_text="",
                parsed_data=result,
            )

    def _extract_req_ids(self, text: str, source_file: str | None = None) -> list[str]:
        """Extract requirement IDs from text.

        Args:
            text: Text to search for requirement IDs.
            source_file: Optional source file for file-specific config.

        Returns:
            List of normalized requirement IDs (using hyphens).
        """
        pattern_config = self._get_pattern_config()
        ref_config = self._get_reference_config(source_file)

        # Use shared extraction function
        ids = extract_ids_from_text(text, pattern_config, ref_config)

        # Normalize: replace underscores with hyphens
        normalized = []
        for req_id in ids:
            normalized_id = req_id.replace("_", "-")
            if normalized_id not in normalized:
                normalized.append(normalized_id)

        return normalized

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
    pattern_config: PatternConfig | None = None,
    reference_resolver: ReferenceResolver | None = None,
    base_path: Path | None = None,
) -> JUnitXMLParser:
    """Factory function to create a JUnitXMLParser.

    Args:
        pattern_config: Optional configuration for ID structure.
        reference_resolver: Optional resolver for file-specific configs.
        base_path: Optional base path for resolving file paths.

    Returns:
        New JUnitXMLParser instance.
    """
    return JUnitXMLParser(pattern_config, reference_resolver, base_path)
