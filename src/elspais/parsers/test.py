"""Test file parser for requirement references.

This parser extracts requirement references from test files
(e.g., REQ-d00001 in docstrings or comments) and produces TraceNode instances.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from elspais.core.tree import SourceLocation, TestReference, TraceNode
    from elspais.core.tree_schema import NodeTypeSchema


class TestParser:
    """Parser for test files with requirement references.

    Extracts requirement references from:
    - Test docstrings
    - Test comments
    - Test names (e.g., test_REQ_d00001_login)
    """

    # Pattern for requirement IDs (including assertion references)
    REQ_PATTERN = re.compile(
        r"REQ-[A-Za-z]?\d+(?:-[A-Z])?|"  # REQ-p00001, REQ-p00001-A
        r"REQ-[A-Z]+-[a-z]\d+(?:-[A-Z])?|"  # REQ-CAL-d00001
        r"[A-Z]+-\d+",  # PROJ-123 (Jira style)
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

    def parse(
        self,
        content: str,
        source: SourceLocation,
        schema: NodeTypeSchema,
    ) -> list[TraceNode]:
        """Parse test content and return nodes.

        Args:
            content: File content to parse.
            source: Source location for the file.
            schema: Schema for this node type.

        Returns:
            List of parsed TraceNodes for test references.
        """
        from elspais.core.tree import NodeKind, SourceLocation, TestReference, TraceNode

        nodes: list[TraceNode] = []
        lines = content.split("\n")

        # Track current test context
        current_test: str | None = None
        current_test_class: str | None = None

        for line_num, line in enumerate(lines, start=1):
            # Check for class definition
            class_match = re.match(r"^\s*class\s+(\w+)", line)
            if class_match:
                current_test_class = class_match.group(1)

            # Check for test function
            for pattern in self.TEST_PATTERNS:
                test_match = pattern.match(line)
                if test_match:
                    current_test = test_match.group(1)
                    break

            # Find requirement references in this line
            req_matches = self.REQ_PATTERN.findall(line)
            for req_id in req_matches:
                # Normalize the requirement ID
                req_id = req_id.upper()

                test_ref = TestReference(
                    file_path=source.path,
                    line=line_num,
                    test_name=current_test or f"line_{line_num}",
                    test_class=current_test_class,
                )

                node_id = f"{source.path}:{line_num}:{req_id}"
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
                node.metrics["_validates_targets"] = [req_id]
                nodes.append(node)

        return nodes

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
