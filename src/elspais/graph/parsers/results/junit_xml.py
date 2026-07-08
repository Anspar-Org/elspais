"""JUnit XML parser for test results.

This parser extracts test results from JUnit XML format files.
Uses IdResolver.search_regex() for finding requirement IDs in test output.

Source-file binding
-------------------
Standard pytest/JUnit XML has no per-test source path, so the classname is
used to synthesize a Python ``test:...::...`` ``test_id`` that a scanned
``.py`` test node can match (the YIELDS branch in the builder).

For non-Python producers (e.g. Playwright ``.spec.ts``), a per-``<testcase>``
``file`` attribute names the real source file.  When present, it is preferred
as the result's ``source_path`` (so ``match = "source"`` binds the result to
the scanned test node by path) and the classname-derived ``test_id`` is
dropped (set to ``None``) -- a ``.py`` module id could never match a
``.spec.ts`` node, and a non-None ``test_id`` would route the result to the
doomed YIELDS branch instead of source matching.  An optional ``line``
attribute is exposed as the result's ``line`` field.  Producers whose JUnit
reporter omits ``file`` behave exactly as before (fully backward-compatible).
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Any
from xml.sax.saxutils import unescape

from elspais.graph.parsers import ParseContext, ParsedContent
from elspais.utilities.test_identity import build_test_id_from_result

# Pattern to extract a named XML attribute value from a raw text line.
_ATTR_RE: dict[str, re.Pattern[str]] = {}

# Attribute values pulled from raw XML text still carry entity escapes;
# ElementTree-parsed values do not. Unescape before comparing the two.
_XML_ENTITIES = {"&quot;": '"', "&apos;": "'"}


def _attr_value(text: str, attr: str) -> str | None:
    """Extract the value of *attr* from a raw XML element string."""
    pat = _ATTR_RE.get(attr)
    if pat is None:
        pat = re.compile(rf'\b{attr}="([^"]*)"')
        _ATTR_RE[attr] = pat
    m = pat.search(text)
    return unescape(m.group(1), _XML_ENTITIES) if m else None


def _testcase_line_index(content: str) -> dict[tuple[str, str], int]:
    """Map ``(classname, name)`` to the 1-based line of its ``<testcase``.

    Works when the XML is pretty-printed so each ``<testcase`` open tag sits
    on its own line; a minified (single-line) document maps everything to
    line 1. Only the first occurrence of a duplicate key is kept.
    """
    index: dict[tuple[str, str], int] = {}
    for line_no, text in enumerate(content.splitlines(), start=1):
        if "<testcase" not in text:
            continue
        cn = _attr_value(text, "classname")
        nm = _attr_value(text, "name")
        if cn is not None and nm is not None:
            index.setdefault((cn, nm), line_no)
    return index


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

        # Results-file provenance: each record points back at the artifact
        # that recorded it (`result_file` = the results file itself, distinct
        # from `source_path`, which names the TEST'S source file and is the
        # RESULT->TEST match key). `result_line` is the `<testcase>` line
        # within the results file (None when the XML is minified).
        tc_lines = _testcase_line_index(content)

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

                # A per-testcase `file` attribute (e.g. Playwright JUnit) names
                # the real source file. Prefer it as the result's source path so
                # `match="source"` can bind the result to the scanned test node,
                # and DROP the classname-derived test_id (which assumes a Python
                # `.py` module path and can never match a `.spec.ts`) so the
                # builder takes its source-location matching path instead of a
                # doomed test_id YIELDS.
                file_attr = testcase.get("file")
                result_source = file_attr or source_path
                line_attr = testcase.get("line")
                try:
                    line_no = int(line_attr) if line_attr else None
                except (TypeError, ValueError):
                    line_no = None

                # Extract requirement references from test name or classname
                verifies = self._extract_req_ids(f"{classname} {name}", source_path)

                # Generate canonical TEST node ID using test_identity utility
                test_id = None if file_attr else build_test_id_from_result(classname, name)

                result = {
                    "id": f"{result_source}:{classname}::{name}",
                    "name": name,
                    "classname": classname,
                    "status": status,
                    "duration": duration,
                    "message": message[:200] if message else None,
                    "verifies": verifies,
                    "source_path": result_source,
                    "test_id": test_id,
                    "line": line_no,
                    "result_file": source_path or None,
                    "result_line": tc_lines.get((classname, name)),
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

        # parse() computes result_line relative to the reassembled content
        # (1-based); shift by the first claimed line so start_line matches
        # the real file position.
        base_line = lines[0][0] if lines else 1

        for result in results:
            rl = result.get("result_line")
            start = (rl + base_line - 1) if rl else base_line
            result["result_line"] = start
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
