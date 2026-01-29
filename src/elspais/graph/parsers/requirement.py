"""RequirementParser - Priority 50 parser for requirement blocks.

Parses requirement specifications from markdown, claiming lines from
header through end marker.
"""

from __future__ import annotations

import re
from typing import Any, Iterator

from elspais.graph.parsers import ParseContext, ParsedContent
from elspais.utilities.patterns import PatternConfig, PatternValidator


class RequirementParser:
    """Parser for requirement blocks.

    Priority: 50 (after comments, before remainder)

    Parses requirement blocks in the standard format:
    - Header: ## REQ-xxx: Title
    - Metadata: **Level**: ... | **Status**: ...
    - Body text
    - Optional assertions section
    - End marker: *End* *REQ-xxx*
    """

    priority = 50

    # Regex patterns
    HEADER_PATTERN = re.compile(r"^#*\s*(?P<id>[A-Z]+-[A-Za-z0-9-]+):\s*(?P<title>.+)$")
    LEVEL_STATUS_PATTERN = re.compile(
        r"\*\*Level\*\*:\s*(?P<level>\w+)"
        r"(?:\s*\|\s*\*\*Implements\*\*:\s*(?P<implements>[^|\n]+))?"
        r"(?:\s*\|\s*\*\*Status\*\*:\s*(?P<status>\w+))?"
    )
    ALT_STATUS_PATTERN = re.compile(r"\*\*Status\*\*:\s*(?P<status>\w+)")
    IMPLEMENTS_PATTERN = re.compile(r"\*\*Implements\*\*:\s*(?P<implements>[^|\n]+)")
    REFINES_PATTERN = re.compile(r"\*\*Refines\*\*:\s*(?P<refines>[^|\n]+)")
    END_MARKER_PATTERN = re.compile(
        r"^\*End\*\s+\*[^*]+\*\s*(?:\|\s*\*\*Hash\*\*:\s*(?P<hash>[a-zA-Z0-9]+))?",
        re.MULTILINE,
    )
    ASSERTIONS_HEADER_PATTERN = re.compile(r"^##\s+Assertions\s*$", re.MULTILINE)
    ASSERTION_LINE_PATTERN = re.compile(r"^\s*([A-Z0-9]+)\.\s+(.+)$", re.MULTILINE)

    # Values that mean "no references"
    NO_REFERENCE_VALUES = ["-", "null", "none", "x", "X", "N/A", "n/a"]

    def __init__(self, pattern_config: PatternConfig) -> None:
        """Initialize parser with pattern configuration.

        Args:
            pattern_config: Configuration for ID patterns.
        """
        self.pattern_config = pattern_config
        self.validator = PatternValidator(pattern_config)

    def claim_and_parse(
        self,
        lines: list[tuple[int, str]],
        context: ParseContext,
    ) -> Iterator[ParsedContent]:
        """Claim and parse requirement blocks.

        Args:
            lines: List of (line_number, content) tuples.
            context: Parsing context.

        Yields:
            ParsedContent for each requirement block.
        """
        # Build line map for quick access
        line_map = dict(lines)
        line_numbers = sorted(line_map.keys())

        if not line_numbers:
            return

        claimed: set[int] = set()
        i = 0

        while i < len(line_numbers):
            ln = line_numbers[i]
            if ln in claimed:
                i += 1
                continue

            text = line_map[ln]

            # Check for requirement header
            header_match = self.HEADER_PATTERN.match(text)
            if header_match:
                req_id = header_match.group("id")

                # Validate ID against configured pattern
                if not self.validator.is_valid(req_id):
                    i += 1
                    continue

                title = header_match.group("title").strip()
                start_line = ln

                # Find the end of this requirement
                req_lines = [(ln, text)]
                end_line = ln
                j = i + 1

                while j < len(line_numbers):
                    next_ln = line_numbers[j]
                    next_text = line_map[next_ln]
                    req_lines.append((next_ln, next_text))
                    end_line = next_ln

                    # Check for end marker
                    if self.END_MARKER_PATTERN.match(next_text):
                        j += 1
                        # Include separator if present
                        if j < len(line_numbers):
                            sep_ln = line_numbers[j]
                            if line_map[sep_ln].strip() == "---":
                                req_lines.append((sep_ln, line_map[sep_ln]))
                                end_line = sep_ln
                                j += 1
                        break

                    # Check for next requirement header
                    next_match = self.HEADER_PATTERN.match(next_text)
                    if next_match and self.validator.is_valid(next_match.group("id")):
                        # Hit next requirement - don't include this line
                        req_lines.pop()
                        end_line = line_numbers[j - 1] if j > i + 1 else ln
                        break

                    j += 1

                # Claim all lines in this requirement
                for claim_ln, _ in req_lines:
                    claimed.add(claim_ln)

                # Parse the requirement data
                raw_text = "\n".join(t for _, t in req_lines)
                parsed_data = self._parse_requirement(req_id, title, raw_text)

                yield ParsedContent(
                    content_type="requirement",
                    start_line=start_line,
                    end_line=end_line,
                    raw_text=raw_text,
                    parsed_data=parsed_data,
                )

                # Move index past claimed lines
                while i < len(line_numbers) and line_numbers[i] in claimed:
                    i += 1
            else:
                i += 1

    def _parse_requirement(self, req_id: str, title: str, text: str) -> dict[str, Any]:
        """Parse requirement fields from text block.

        Args:
            req_id: Requirement ID.
            title: Requirement title.
            text: Full requirement text.

        Returns:
            Dictionary of parsed requirement data.
        """
        data: dict[str, Any] = {
            "id": req_id,
            "title": title,
            "level": "Unknown",
            "status": "Unknown",
            "implements": [],
            "refines": [],
            "assertions": [],
            "hash": None,
        }

        # Extract level and status
        level_match = self.LEVEL_STATUS_PATTERN.search(text)
        if level_match:
            data["level"] = level_match.group("level") or "Unknown"
            data["status"] = level_match.group("status") or "Unknown"
            if level_match.group("implements"):
                data["implements"] = self._parse_refs(level_match.group("implements"))

        # Try alternative status pattern
        if data["status"] == "Unknown":
            alt_match = self.ALT_STATUS_PATTERN.search(text)
            if alt_match:
                data["status"] = alt_match.group("status")

        # Try alternative implements pattern
        if not data["implements"]:
            impl_match = self.IMPLEMENTS_PATTERN.search(text)
            if impl_match:
                data["implements"] = self._parse_refs(impl_match.group("implements"))

        # Parse refines
        refines_match = self.REFINES_PATTERN.search(text)
        if refines_match:
            data["refines"] = self._parse_refs(refines_match.group("refines"))

        # Expand multi-assertion references
        data["implements"] = self._expand_multi_assertion(data["implements"])
        data["refines"] = self._expand_multi_assertion(data["refines"])

        # Extract assertions
        data["assertions"] = self._extract_assertions(text)

        # Extract hash
        end_match = self.END_MARKER_PATTERN.search(text)
        if end_match and end_match.group("hash"):
            data["hash"] = end_match.group("hash")

        return data

    def _parse_refs(self, refs_str: str) -> list[str]:
        """Parse comma-separated reference list.

        Handles both full IDs (REQ-p00001) and shorthand (p00001).
        Shorthand references are normalized to full IDs using the configured prefix.
        """
        if not refs_str:
            return []

        stripped = refs_str.strip()
        if stripped in self.NO_REFERENCE_VALUES:
            return []

        prefix = self.pattern_config.prefix
        parts = [p.strip() for p in refs_str.split(",")]
        result = []

        for p in parts:
            if not p or p in self.NO_REFERENCE_VALUES:
                continue
            # Normalize shorthand to full ID (e.g., "o00001" -> "REQ-o00001")
            if not p.startswith(f"{prefix}-"):
                p = f"{prefix}-{p}"
            result.append(p)

        return result

    def _expand_multi_assertion(self, refs: list[str]) -> list[str]:
        """Expand multi-assertion syntax.

        REQ-p00001-A-B-C -> [REQ-p00001-A, REQ-p00001-B, REQ-p00001-C]
        """
        result = []
        multi_pattern = re.compile(r"^([A-Z]+-[A-Za-z0-9-]+?)(-[A-Z](?:-[A-Z])+|-\d+(?:-\d+)+)$")

        for ref in refs:
            match = multi_pattern.match(ref)
            if match:
                base_id = match.group(1)
                labels_str = match.group(2)
                labels = [lbl for lbl in labels_str.split("-") if lbl]
                for label in labels:
                    result.append(f"{base_id}-{label}")
            else:
                result.append(ref)

        return result

    def _extract_assertions(self, text: str) -> list[dict[str, Any]]:
        """Extract assertions from text."""
        assertions = []

        header_match = self.ASSERTIONS_HEADER_PATTERN.search(text)
        if not header_match:
            return assertions

        # Get text after header
        start_pos = header_match.end()
        section_text = text[start_pos:]

        # Find end of assertions section
        end_patterns = [r"^##\s+", r"^\*End\*", r"^---\s*$"]
        end_pos = len(section_text)
        for pattern in end_patterns:
            match = re.search(pattern, section_text, re.MULTILINE)
            if match and match.start() < end_pos:
                end_pos = match.start()

        assertions_text = section_text[:end_pos]

        # Parse assertion lines
        for match in self.ASSERTION_LINE_PATTERN.finditer(assertions_text):
            label = match.group(1)
            assertion_text = match.group(2).strip()
            assertions.append(
                {
                    "label": label,
                    "text": assertion_text,
                }
            )

        return assertions
