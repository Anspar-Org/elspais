"""RequirementParser - Priority 50 parser for requirement blocks.

Parses requirement specifications from markdown, claiming lines from
header through end marker.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any

from elspais.graph.parsers import ParseContext, ParsedContent
from elspais.utilities.hasher import HASH_VALUE_PATTERN
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
        rf"^\*End\*\s+\*[^*]+\*\s*(?:\|\s*\*\*Hash\*\*:\s*(?P<hash>{HASH_VALUE_PATTERN}))?",
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
                parsed_data = self._parse_requirement(req_id, title, raw_text, start_line)

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

    def _parse_requirement(
        self, req_id: str, title: str, text: str, start_line: int = 0
    ) -> dict[str, Any]:
        """Parse requirement fields from text block.

        Args:
            req_id: Requirement ID.
            title: Requirement title.
            text: Full requirement text.
            start_line: Line number where the requirement starts in the file.

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
            "body_text": "",  # Raw text between header and footer for hash computation
        }

        # Extract body_text: everything AFTER header line and BEFORE footer line
        # Per spec: "hash SHALL be calculated from every line AFTER Header, BEFORE Footer"
        data["body_text"] = self._extract_body_text(text)

        # Extract level and status
        level_match = self.LEVEL_STATUS_PATTERN.search(text)
        if level_match:
            raw_level = level_match.group("level") or "Unknown"
            # Normalize level to canonical config type key
            resolved = self.pattern_config.resolve_level(raw_level)
            data["level"] = resolved if resolved is not None else raw_level
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
        data["assertions"] = self._extract_assertions(text, start_line)

        # Extract non-normative sections from body_text (REQ-d00062-B, REQ-d00064-B)
        data["sections"] = self._extract_sections(data["body_text"], start_line, text)

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

    def _extract_assertions(self, text: str, start_line: int = 0) -> list[dict[str, Any]]:
        """Extract assertions from text.

        Args:
            text: Full requirement text.
            start_line: Line number where the requirement starts in the file.

        Returns:
            List of assertion dicts with label, text, and line number.
        """
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
            # Compute absolute line number: use match.start(1) to point to the
            # label character itself (not leading whitespace which may include \n)
            abs_pos = start_pos + match.start(1)
            line = start_line + text[:abs_pos].count("\n")
            assertions.append(
                {
                    "label": label,
                    "text": assertion_text,
                    "line": line,
                }
            )

        return assertions

    def _extract_body_text(self, text: str) -> str:
        """Extract body text for hash computation.

        Per spec/requirements-spec.md:
        > The hash SHALL be calculated from:
        > - every line AFTER the Header line
        > - every line BEFORE the Footer line

        Args:
            text: Full requirement text including header and footer.

        Returns:
            Body text (between header and footer) for hash computation.
        """
        lines = text.split("\n")
        if not lines:
            return ""

        # Header is the first line (## REQ-xxx: Title)
        # Body starts from line 1 (after header)
        body_start = 1

        # Find footer line (*End* *Title* | **Hash**: xxx)
        body_end = len(lines)
        for i, line in enumerate(lines):
            if self.END_MARKER_PATTERN.match(line):
                body_end = i
                break

        # Extract body lines and join
        body_lines = lines[body_start:body_end]

        # Strip leading/trailing empty lines but preserve internal structure
        while body_lines and not body_lines[0].strip():
            body_lines.pop(0)
        while body_lines and not body_lines[-1].strip():
            body_lines.pop()

        return "\n".join(body_lines)

    # Pattern to split on ## headings (captures the heading name)
    _SECTION_HEADER_RE = re.compile(r"^##\s+(.+)$", re.MULTILINE)

    def _extract_sections(
        self, body_text: str, start_line: int = 0, raw_text: str = ""
    ) -> list[dict[str, Any]]:
        """Extract named sections from body text.

        Parses ## headings into separate sections. Content before the first
        heading (minus the metadata line) goes into a "preamble" section.
        The Assertions section is excluded (already parsed as assertion nodes).

        Args:
            body_text: The body text between header and footer.
            start_line: Line number where the requirement starts in the file.
            raw_text: Full raw requirement text (for computing line offsets).

        Returns:
            List of {"heading": str, "content": str, "line": int} dicts.
            Empty sections are omitted.
        """
        if not body_text:
            return []

        # Compute the line offset where body_text begins within raw_text.
        # body_text is extracted from raw_text by stripping header and footer,
        # so we find where the first body line appears.
        body_start_offset = 0
        if raw_text and body_text:
            # The header is line 0 of raw_text, body starts after that
            # Find the body_text content in raw_text to get proper offset
            first_body_line = body_text.split("\n")[0] if body_text else ""
            raw_lines = raw_text.split("\n")
            for i, rl in enumerate(raw_lines):
                if rl == first_body_line and i > 0:
                    body_start_offset = i
                    break
            else:
                # Fallback: body starts on line 1 (after header)
                body_start_offset = 1

        sections: list[dict[str, Any]] = []
        lines = body_text.split("\n")

        current_heading: str | None = None
        current_lines: list[str] = []
        current_line_num = start_line + body_start_offset

        # Track starting line for each section
        section_start_line = current_line_num

        for i, line in enumerate(lines):
            match = self._SECTION_HEADER_RE.match(line)
            if match:
                # Flush previous section
                self._flush_section(sections, current_heading, current_lines, section_start_line)
                current_heading = match.group(1).strip()
                current_lines = []
                section_start_line = start_line + body_start_offset + i
            else:
                current_lines.append(line)

        # Flush final section
        self._flush_section(sections, current_heading, current_lines, section_start_line)

        return sections

    def _flush_section(
        self,
        sections: list[dict[str, Any]],
        heading: str | None,
        lines: list[str],
        line_num: int = 0,
    ) -> None:
        """Flush accumulated lines into a section if non-empty.

        For the preamble (heading=None), strips the metadata line
        (**Level**: ... | **Status**: ...) since it's already parsed
        into structured fields.

        Skips the Assertions section (already parsed as nodes).
        """
        if heading is not None and heading.lower() == "assertions":
            return

        # Strip metadata line from preamble
        if heading is None:
            lines = [
                ln
                for ln in lines
                if not self.LEVEL_STATUS_PATTERN.search(ln)
                and not self.ALT_STATUS_PATTERN.search(ln)
                and not self.IMPLEMENTS_PATTERN.search(ln)
            ]

        content = "\n".join(lines).strip()
        if not content:
            return

        sections.append(
            {
                "heading": heading if heading is not None else "preamble",
                "content": content,
                "line": line_num,
            }
        )
