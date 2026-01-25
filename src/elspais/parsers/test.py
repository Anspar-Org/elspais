"""Test file parser for requirement references.

This parser extracts requirement references from test files using context-aware
patterns that ONLY match intentional references:
- Validates: REQ-xxx
- IMPLEMENTS: REQ-xxx
- Test function names containing REQ-xxx

This avoids false positives from fixture data or bare mentions in comments.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from elspais.core.graph import SourceLocation, TestReference, TraceNode
    from elspais.core.graph_schema import NodeTypeSchema


class TestParser:
    """Parser for test files with requirement references.

    Uses context-aware patterns to extract ONLY intentional requirement references:
    - Validates: keyword (docstrings, comments)
    - IMPLEMENTS: keyword (comments)
    - Test function names with REQ in name

    Does NOT match:
    - Bare REQ-xxx mentions in strings/fixture data
    - REQ-xxx in comments without Validates: or IMPLEMENTS: keyword
    """

    # Pattern to detect if a line has Validates: keyword
    VALIDATES_LINE_PATTERN = re.compile(
        r"(?:Validates|VALIDATES|validates)[:\s]",
        re.IGNORECASE,
    )

    # Pattern to detect if a line has IMPLEMENTS: keyword
    IMPLEMENTS_LINE_PATTERN = re.compile(
        r"(?:IMPLEMENTS|Implements|implements)[:\s]",
        re.IGNORECASE,
    )

    # Pattern to extract REQ IDs from a validated context line
    # Matches: REQ-d00001, REQ-p00001-A, REQ_d00002, etc.
    REQ_ID_PATTERN = re.compile(
        r"(?:REQ[-_])([A-Za-z]?\d+(?:-[A-Z])?)",
        re.IGNORECASE,
    )

    # Pattern for REQ in test function names
    # Matches: test_REQ_d00001_login, test_REQ_p00001_A_something, test_d00001, etc.
    TEST_NAME_REQ_PATTERN = re.compile(
        r"test_(?:.*?_)?(?:REQ[-_])?([A-Za-z]?\d{4,}(?:[-_][A-Z])?)(?:_|$)",
        re.IGNORECASE,
    )

    # Pattern for it/test JS names with REQ
    # Matches: it('should validate REQ-d00001', ...) or test('REQ-p00001 login', ...)
    JS_TEST_REQ_PATTERN = re.compile(
        r"(?:REQ[-_])([A-Za-z]?\d+(?:-[A-Z])?)",
        re.IGNORECASE,
    )

    # Pattern for test function/method definitions
    TEST_PATTERNS = [
        # Python: def test_xxx or async def test_xxx
        re.compile(r"^\s*(?:async\s+)?def\s+(test_\w+)"),
        # JavaScript/TypeScript: it('xxx', ...) or test('xxx', ...)
        re.compile(r"^\s*(?:it|test)\s*\(\s*['\"](.+?)['\"]"),
        # Java: @Test public void xxx()
        re.compile(r"^\s*(?:@Test\s+)?(?:public\s+)?void\s+(test\w+)\s*\("),
        # Go: func TestXxx(t *testing.T)
        re.compile(r"^\s*func\s+(Test\w+)\s*\("),
        # Rust: #[test] fn xxx()
        re.compile(r"^\s*fn\s+(test_\w+)"),
    ]

    # Test file patterns
    TEST_FILE_PATTERNS: set[str] = {
        "test_",
        "_test.",
        ".test.",
        ".spec.",
        "_spec.",
    }

    # Marker pattern for expected broken links - multi-language support
    # Matches various comment styles:
    # - # elspais: expected-broken-links N  (Python, Shell, Ruby, YAML)
    # - // elspais: expected-broken-links N (JS, TS, Java, C, C++, Go, Rust)
    # - -- elspais: expected-broken-links N (SQL, Lua, Ada)
    # - /* elspais: expected-broken-links N */ (CSS, C-style block comment)
    # - <!-- elspais: expected-broken-links N --> (HTML, XML)
    _EXPECTED_BROKEN_LINKS_PATTERN = re.compile(
        r"(?:"
        r"#|"  # Python, Shell, Ruby, YAML
        r"//|"  # JS, TS, Java, C, C++, Go, Rust
        r"--|"  # SQL, Lua, Ada
        r"/\*|"  # CSS, C-style block comment start
        r"<!--"  # HTML, XML comment start
        r")\s*elspais:\s*expected-broken-links\s+(\d+)",
        re.IGNORECASE,
    )

    # Number of header lines to scan for marker
    _MARKER_HEADER_LINES = 20

    def parse(
        self,
        content: str,
        source: SourceLocation,
        schema: NodeTypeSchema,
    ) -> list[TraceNode]:
        """Parse test content and return nodes.

        Uses context-aware patterns to only match intentional references:
        - Validates: keyword
        - IMPLEMENTS: keyword
        - REQ in test function names

        Args:
            content: File content to parse.
            source: Source location for the file.
            schema: Schema for this node type.

        Returns:
            List of parsed TraceNodes for test references.
        """
        from elspais.core.graph import NodeKind, SourceLocation, TestReference, TraceNode

        nodes: list[TraceNode] = []
        lines = content.split("\n")

        # Detect expected-broken-links marker in header
        suppress_remaining = self._detect_expected_broken_links_marker(lines)

        # Track current test context
        current_test: str | None = None
        current_test_class: str | None = None

        for line_num, line in enumerate(lines, start=1):
            # Check for class definition
            class_match = re.match(r"^\s*class\s+(\w+)", line)
            if class_match:
                current_test_class = class_match.group(1)

            # Check for test function and extract REQ from name if present
            test_func_req_ids: list[str] = []
            for pattern in self.TEST_PATTERNS:
                test_match = pattern.match(line)
                if test_match:
                    current_test = test_match.group(1)
                    # Check if the test name contains a REQ reference
                    # For Python: test_REQ_d00001_xxx -> extract via TEST_NAME_REQ_PATTERN
                    name_req_match = self.TEST_NAME_REQ_PATTERN.search(current_test)
                    if name_req_match:
                        test_func_req_ids.append(name_req_match.group(1))
                    # For JS/TS: it('should login REQ-d00001', ...) -> extract all REQ from name
                    for js_match in self.REQ_ID_PATTERN.finditer(current_test):
                        test_func_req_ids.append(js_match.group(1))
                    break

            # Find context-aware requirement references in this line
            req_ids_found: list[str] = []

            # Check if line has Validates: or IMPLEMENTS: keyword
            has_validates = self.VALIDATES_LINE_PATTERN.search(line) is not None
            has_implements = self.IMPLEMENTS_LINE_PATTERN.search(line) is not None

            # If line has a keyword, extract all REQ IDs from it
            if has_validates or has_implements:
                for match in self.REQ_ID_PATTERN.finditer(line):
                    req_ids_found.append(match.group(1))

            # Pattern 3: REQ in test function name (only on the def line)
            req_ids_found.extend(test_func_req_ids)

            # Create nodes for each unique reference found on this line
            seen_on_line: set[str] = set()
            for raw_id in req_ids_found:
                # Normalize the requirement ID
                normalized_id = self._normalize_req_id(raw_id)
                if normalized_id in seen_on_line:
                    continue
                seen_on_line.add(normalized_id)

                test_ref = TestReference(
                    file_path=source.path,
                    line=line_num,
                    test_name=current_test or f"line_{line_num}",
                    test_class=current_test_class,
                )

                node_id = f"{source.path}:{line_num}:{normalized_id}"
                node = TraceNode(
                    id=node_id,
                    kind=NodeKind.TEST,
                    label=self._format_label(test_ref, schema.label_template),
                    source=SourceLocation(
                        path=source.path,
                        line=line_num,
                        repo=source.repo,
                    ),
                    test_ref=test_ref,
                )
                # Store the referenced requirement ID for linking
                node.metrics["_validates_targets"] = [normalized_id]

                # Check if this reference should be marked as expected broken
                if suppress_remaining > 0:
                    node.metrics["_expected_broken_targets"] = [normalized_id]
                    suppress_remaining -= 1

                nodes.append(node)

        return nodes

    def _detect_expected_broken_links_marker(self, lines: list[str]) -> int:
        """Detect expected-broken-links marker in file header.

        Scans the first 20 lines of file content for the marker:
        # elspais: expected-broken-links N

        Args:
            lines: Lines of file content.

        Returns:
            The expected count N if marker is found, 0 otherwise.
        """
        # Only scan header area (first N lines)
        for line in lines[: self._MARKER_HEADER_LINES]:
            match = self._EXPECTED_BROKEN_LINKS_PATTERN.search(line)
            if match:
                return int(match.group(1))
        return 0

    def _normalize_req_id(self, raw_id: str) -> str:
        """Normalize a raw requirement ID to standard format.

        Preserves case to match requirement IDs in spec files.

        Args:
            raw_id: Raw ID extracted from pattern (e.g., "d00001", "p00001-A").

        Returns:
            Normalized ID (e.g., "REQ-d00001", "REQ-p00001-A").
        """
        # Replace underscores with dashes
        normalized = raw_id.replace("_", "-")

        # Add REQ- prefix if not present (case-insensitive check)
        if not normalized.upper().startswith("REQ-"):
            normalized = f"REQ-{normalized}"

        return normalized

    def can_parse(self, file_path: Path) -> bool:
        """Check if this parser can handle the given file.

        Args:
            file_path: Path to the file.

        Returns:
            True for files that look like test files.
        """
        name = file_path.name.lower()

        # Check file name patterns
        for pattern in self.TEST_FILE_PATTERNS:
            if pattern in name:
                return True

        # Check directory
        path_str = str(file_path).lower()
        return "test" in path_str or "tests" in path_str

    def _format_label(self, test_ref: TestReference, template: str) -> str:
        """Format a label using the template.

        Args:
            test_ref: TestReference to format.
            template: Label template with {placeholders}.

        Returns:
            Formatted label string.
        """
        try:
            return template.format(
                file_path=test_ref.file_path,
                line=test_ref.line,
                test_name=test_ref.test_name,
                test_class=test_ref.test_class or "",
            )
        except (KeyError, AttributeError):
            if test_ref.test_class:
                return f"{test_ref.test_class}::{test_ref.test_name}"
            return test_ref.test_name


def create_parser() -> TestParser:
    """Factory function to create a TestParser.

    Returns:
        New TestParser instance.
    """
    return TestParser()
