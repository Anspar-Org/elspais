"""RequirementTransformer - Converts Lark parse tree to ParsedContent list.

Walks the deep parse tree produced by requirement.lark and produces
ParsedContent objects identical to those from the old RequirementParser,
JourneyParser, and RemainderParser.

The grammar pre-classifies structural elements (metadata fields, assertion
entries, named sections, footer), so the transformer only needs to extract
values from pre-classified tokens -- no regex re-scanning for structure.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from lark import Token, Tree

from elspais.graph.parsers import ParsedContent
from elspais.utilities.hasher import HASH_VALUE_PATTERN

if TYPE_CHECKING:
    from elspais.utilities.patterns import IdResolver


# Footer hash extraction (only regex still needed -- footer structure is complex)
_HASH_RE = re.compile(rf"\*\*Hash\*\*:[ \t]*(?P<hash>{HASH_VALUE_PATTERN})")

# Header parsing
_REQ_HEADER_RE = re.compile(
    r"^(?P<hashes>#+)[ \t]*(?P<id>[A-Z]+-[A-Za-z0-9-]+):[ \t]*(?P<title>.+)$"
)
_JNY_HEADER_RE = re.compile(r"^#*[ \t]*(?P<id>JNY-[A-Za-z0-9-]+):[ \t]*(?P<title>.+)$")

# Metadata field value extraction
_FIELD_VALUE_RE = re.compile(r"\*\*\w+\*\*:[ \t]*(.*)")

# Journey field patterns
_ACTOR_RE = re.compile(r"\*\*Actor\*\*:[ \t]*(?P<actor>.+?)(?:\n|$)")
_GOAL_RE = re.compile(r"\*\*Goal\*\*:[ \t]*(?P<goal>.+?)(?:\n|$)")
_VALIDATES_RE = re.compile(r"^Validates:[ \t]*(?P<validates>.+?)$", re.MULTILINE)

# Changelog entry pattern
_CHANGELOG_ENTRY_RE = re.compile(r"^- (.+?) \| (\S+) \| (.+?) \| (.+?) \(<?(.+?)>?\) \| (.+)$")

# Values that mean "no references"
_NO_REF_VALUES = {"-", "null", "none", "x", "X", "N/A", "n/a"}


class RequirementTransformer:
    """Transform a requirement.lark parse tree into ParsedContent objects.

    Walks the deep parse tree top-down, extracting values from pre-classified
    tokens.  Produces output identical to the old parser pipeline.
    """

    def __init__(self, resolver: IdResolver) -> None:
        self.resolver = resolver

    def transform(self, tree: Tree, source: str = "") -> list[ParsedContent]:
        """Transform the full parse tree into a list of ParsedContent.

        Args:
            tree: Parse tree from requirement.lark.
            source: Original source text (used for faithful raw_text and
                body_text extraction preserving blank lines).
        """
        self._source_lines = source.split("\n") if source else []
        results: list[ParsedContent] = []
        remainder_lines: list[tuple[int, str]] = []

        for child in tree.children:
            if isinstance(child, Tree):
                if child.data == "requirement":
                    self._flush_remainder(remainder_lines, results)
                    remainder_lines = []
                    results.append(self._transform_requirement(child))
                elif child.data == "journey":
                    self._flush_remainder(remainder_lines, results)
                    remainder_lines = []
                    results.append(self._transform_journey(child))
                elif child.data == "definition_block":
                    self._flush_remainder(remainder_lines, results)
                    remainder_lines = []
                    results.append(self._transform_definition_block(child))
                elif child.data == "remainder_line":
                    token = child.children[0]  # TEXT token
                    remainder_lines.append((token.line, str(token)))  # type: ignore[attr-defined]
                elif child.data == "stray_marker":
                    token = child.children[0]
                    remainder_lines.append((token.line, str(token)))  # type: ignore[attr-defined]

        self._flush_remainder(remainder_lines, results)

        # Fill blank-line gaps that the Lark grammar discards as anonymous _NL.
        # Without this, blank lines between content blocks are lost on render.
        if self._source_lines:
            results = self._fill_blank_line_gaps(results)

        return results

    # ------------------------------------------------------------------
    # Requirement transformation
    # ------------------------------------------------------------------

    def _transform_requirement(self, node: Tree) -> ParsedContent:
        """Transform a requirement tree node into ParsedContent."""
        header_token = node.children[0]  # REQ_HEADER
        header_text = str(header_token)
        header_line = header_token.line  # type: ignore[attr-defined]

        header_match = _REQ_HEADER_RE.match(header_text)
        if not header_match:
            return self._make_remainder(header_line, header_line, header_text)

        req_id = header_match.group("id")
        title = header_match.group("title").strip()
        heading_level = len(header_match.group("hashes"))

        # Walk children to extract structured data
        level = "Unknown"
        status = "Unknown"
        implements: list[str] = []
        refines: list[str] = []
        satisfies: list[str] = []
        assertions: list[dict[str, Any]] = []
        sections: list[dict[str, Any]] = []
        changelog: list[dict[str, str]] = []
        definitions: list[dict[str, Any]] = []
        body_lines: list[str] = []
        hash_value: str | None = None
        end_line = header_line
        has_redundant_refs = False

        for child in node.children[1:]:
            if not isinstance(child, Tree):
                continue

            if child.data == "metadata_line":
                meta = self._extract_metadata(child)
                if meta.get("level"):
                    resolved = self.resolver.resolve_level(meta["level"])
                    level = resolved if resolved is not None else meta["level"]
                if meta.get("status"):
                    status = meta["status"]
                if meta.get("implements"):
                    old_len = len(implements)
                    for ref in meta["implements"]:
                        if ref not in implements:
                            implements.append(ref)
                    if len(implements) < old_len + len(meta["implements"]):
                        has_redundant_refs = True
                if meta.get("refines"):
                    old_len = len(refines)
                    for ref in meta["refines"]:
                        if ref not in refines:
                            refines.append(ref)
                    if len(refines) < old_len + len(meta["refines"]):
                        has_redundant_refs = True
                end_line = self._last_line(child)

            elif child.data == "satisfies_line":
                token = child.children[0]  # SATISFIES_FIELD
                sat_text = str(token)
                # Extract value after separator (: or = or space)
                sep_match = re.search(r"[:=\s]", sat_text.replace("*", "").replace("_", ""))
                if sep_match:
                    # Find separator in original text after field name
                    field_name_end = sat_text.lower().index("satisfies") + len("satisfies")
                    # Skip past any closing decoration
                    while field_name_end < len(sat_text) and sat_text[field_name_end] in "*_":
                        field_name_end += 1
                    sat_value = sat_text[field_name_end:].lstrip(":= \t").strip()
                else:
                    sat_value = ""
                satisfies = self._parse_refs(sat_value)
                end_line = token.line  # type: ignore[attr-defined]

            elif child.data == "assertion_block":
                assertions, sub_heading_sections = self._extract_assertions(child, header_line)
                sections.extend(sub_heading_sections)
                end_line = self._last_line(child)

            elif child.data == "changelog_block":
                changelog = self._extract_changelog(child)
                end_line = self._last_line(child)

            elif child.data == "named_block":
                section = self._extract_named_section(child)
                if section:
                    sections.append(section)
                # Extract definition_blocks nested in content_lines
                for sub in child.children[1:]:
                    if isinstance(sub, Tree) and sub.data == "content_line":
                        for subsub in sub.children:
                            if isinstance(subsub, Tree) and subsub.data == "definition_block":
                                def_data = self._extract_definition_block(subsub)
                                if def_data:
                                    definitions.append(def_data)
                end_line = self._last_line(child)

            elif child.data == "definition_block":
                def_data = self._extract_definition_block(child)
                if def_data:
                    definitions.append(def_data)
                end_line = self._last_line(child)

            elif child.data == "body_line":
                line_num, text = self._extract_text_from_body_line(child)
                body_lines.append(text)
                end_line = line_num

            elif child.data == "end_block":
                footer_token = child.children[0]  # END_MARKER
                footer_text = str(footer_token)
                hash_match = _HASH_RE.search(footer_text)
                if hash_match:
                    hash_value = hash_match.group("hash")
                end_line = footer_token.line  # type: ignore[attr-defined]

        # Build raw_text for hash computation
        raw_text = self._reconstruct_raw_text(node)

        # Build preamble section from body_lines (text before first ## section)
        # Preserve internal blank lines (significant for list spacing) but strip
        # leading/trailing blank lines.
        preamble_content = "\n".join(body_lines).strip()
        if preamble_content:
            sections.insert(
                0,
                {
                    "heading": "preamble",
                    "content": preamble_content,
                    "line": header_line + 1,
                },
            )

        parsed_data: dict[str, Any] = {
            "id": req_id,
            "title": title,
            "level": level,
            "status": status,
            "implements": implements,
            "refines": refines,
            "satisfies": satisfies,
            "assertions": assertions,
            "sections": sections,
            "changelog": changelog,
            "definitions": definitions,
            "hash": hash_value,
            "heading_level": heading_level,
        }
        if has_redundant_refs:
            parsed_data["has_redundant_refs"] = True

        return ParsedContent(
            content_type="requirement",
            start_line=header_line,
            end_line=end_line,
            raw_text=raw_text,
            parsed_data=parsed_data,
        )

    # ------------------------------------------------------------------
    # Metadata extraction from pre-classified tokens
    # ------------------------------------------------------------------

    def _extract_metadata(self, node: Tree) -> dict[str, Any]:
        """Extract metadata fields from a metadata_line tree node.

        Field terminals match flexible patterns with optional markdown
        decoration (**, *, _) and various separators (:, =, space).
        The value is everything after the field name and separator.
        """
        result: dict[str, Any] = {}
        for child in node.children:
            if isinstance(child, Token):
                text = str(child).strip()
                val = self._extract_field_value(text)
                if child.type == "LEVEL_FIELD":
                    result["level"] = val
                elif child.type == "STATUS_FIELD":
                    result["status"] = val
                elif child.type == "IMPLEMENTS_FIELD":
                    result["implements"] = self._parse_refs(val)
                elif child.type == "REFINES_FIELD":
                    result["refines"] = self._parse_refs(val)
                # PIPE tokens are ignored
        return result

    @staticmethod
    def _extract_field_value(text: str) -> str:
        """Extract the value portion from a metadata field token.

        Handles all decoration styles:
          **Level**: prd  ->  prd
          *Status*: Active  ->  Active
          _level_= dev  ->  dev
          level: ops  ->  ops
        """
        # Strip markdown decoration (**, *, _) from the start
        stripped = text.lstrip("*_")
        # Find the field name end (first non-alpha character after stripping)
        i = 0
        while i < len(stripped) and stripped[i].isalpha():
            i += 1
        # Skip past closing decoration
        while i < len(stripped) and stripped[i] in "*_":
            i += 1
        # Skip separator and whitespace
        while i < len(stripped) and stripped[i] in ":= \t":
            i += 1
        return stripped[i:].strip()

    # ------------------------------------------------------------------
    # Assertion extraction from pre-classified tokens
    # ------------------------------------------------------------------

    def _extract_assertions(
        self, node: Tree, req_start_line: int
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Extract assertions and sub-heading sections from an assertion block.

        Returns:
            (assertions, sub_heading_sections) where sub_heading_sections are
            inline labels like ``*Core Functionality*`` stored as section dicts
            with ``heading_style`` preserving the original formatting.
        """
        assertions: list[dict[str, Any]] = []
        sub_sections: list[dict[str, Any]] = []
        for child in node.children:
            if isinstance(child, Tree) and child.data == "assertion":
                assertion = self._extract_single_assertion(child)
                if assertion:
                    assertions.append(assertion)
            elif isinstance(child, Tree) and child.data == "assertion_sub_heading":
                token = child.children[0]  # ASSERT_SUB_HDR
                raw_text = str(token).strip()
                line_num = token.line  # type: ignore[attr-defined]
                # Determine style and strip decoration to get heading text
                if raw_text.startswith("**") and raw_text.endswith("**"):
                    heading_style = "**"
                    heading_text = raw_text[2:-2].strip()
                elif raw_text.startswith("*") and raw_text.endswith("*"):
                    heading_style = "*"
                    heading_text = raw_text[1:-1].strip()
                elif raw_text.startswith("_") and raw_text.endswith("_"):
                    heading_style = "_"
                    heading_text = raw_text[1:-1].strip()
                else:
                    heading_style = "*"
                    heading_text = raw_text
                sub_sections.append(
                    {
                        "heading": heading_text,
                        "content": "",
                        "line": line_num,
                        "heading_style": heading_style,
                    }
                )
        return assertions, sub_sections

    def _extract_single_assertion(self, node: Tree) -> dict[str, Any] | None:
        """Extract a single assertion (entry + continuation lines)."""
        entry_token = node.children[0]  # ASSERTION_ENTRY
        entry_text = str(entry_token)
        line_num = entry_token.line  # type: ignore[attr-defined]

        # Parse "A. assertion text"
        dot_idx = entry_text.index(".")
        label = entry_text[:dot_idx].strip()
        text_parts = [entry_text[dot_idx + 1 :].strip()]

        # Collect continuation lines (ASSERT_CONT tokens)
        for child in node.children[1:]:
            if isinstance(child, Token) and child.type == "ASSERT_CONT":
                text_parts.append(str(child))

        # Strip trailing blank parts
        while text_parts and not text_parts[-1].strip():
            text_parts.pop()

        return {
            "label": label,
            "text": "\n".join(text_parts),
            "line": line_num,
        }

    # ------------------------------------------------------------------
    # Named section extraction
    # ------------------------------------------------------------------

    def _extract_named_section(self, node: Tree) -> dict[str, Any] | None:
        """Extract a named section (## Heading + content)."""
        header_token = node.children[0]  # SECTION_HDR
        header_text = str(header_token).strip()
        line_num = header_token.line  # type: ignore[attr-defined]

        # Strip "## " prefix
        heading = header_text.lstrip("#").strip()

        # Skip Assertions and Changelog (parsed separately)
        if heading.lower() in ("assertions", "changelog"):
            return None

        # Collect content lines from content_line nodes
        content_lines: list[str] = []
        first_content_line: int | None = None
        for child in node.children[1:]:
            if isinstance(child, Tree) and child.data == "content_line":
                for token in child.children:
                    if isinstance(token, Token) and token.type == "TEXT":
                        content_lines.append(str(token))
                        if first_content_line is None:
                            first_content_line = token.line  # type: ignore[attr-defined]
                        break
                else:
                    content_lines.append("")  # blank line
            elif isinstance(child, Token) and child.type == "TEXT":
                content_lines.append(str(child))
                if first_content_line is None:
                    first_content_line = child.line  # type: ignore[attr-defined]

        content = "\n".join(content_lines).strip()
        if not content:
            return None

        return {
            "heading": heading,
            "content": content,
            "line": line_num,
            "content_line": first_content_line or line_num + 1,
        }

    # ------------------------------------------------------------------
    # Changelog extraction
    # ------------------------------------------------------------------

    def _extract_changelog(self, node: Tree) -> list[dict[str, str]]:
        """Extract changelog entries from a changelog_block tree node."""
        entries: list[dict[str, str]] = []
        for child in node.children:
            line: str | None = None
            if isinstance(child, Tree) and child.data == "content_line":
                for token in child.children:
                    if isinstance(token, Token) and token.type == "TEXT":
                        line = str(token).strip()
                        break
            elif isinstance(child, Token) and child.type not in ("CHANGELOG_HDR",):
                line = str(child).strip()
            if line:
                m = _CHANGELOG_ENTRY_RE.match(line)
                if m:
                    entries.append(
                        {
                            "date": m.group(1),
                            "hash": m.group(2),
                            "change_order": m.group(3),
                            "author_name": m.group(4),
                            "author_id": m.group(5),
                            "reason": m.group(6),
                        }
                    )
        return entries

    # ------------------------------------------------------------------
    # Journey transformation
    # ------------------------------------------------------------------

    def _transform_journey(self, node: Tree) -> ParsedContent:
        """Transform a journey tree node into ParsedContent.

        Extracts structured fields from the parse tree:
        - actor, goal, context from JNY_*_FIELD terminals
        - validates from JNY_VALIDATES_FIELD
        - sections (## headings) with their content
        - body_lines (preamble text after metadata)
        """
        header_token = node.children[0]  # JNY_HEADER
        header_text = str(header_token)
        header_line = header_token.line  # type: ignore[attr-defined]

        header_match = _JNY_HEADER_RE.match(header_text)
        if not header_match:
            return self._make_remainder(header_line, header_line, header_text)

        journey_id = header_match.group("id")
        title = header_match.group("title").strip()

        raw_text = self._reconstruct_raw_text(node)
        end_line = self._last_line(node)

        parsed_data: dict[str, Any] = {
            "id": journey_id,
            "title": title,
            "actor": None,
            "goal": None,
            "context": None,
            "validates": [],
            "body_lines": [],
            "sections": [],
        }

        # Walk tree children to extract structured fields
        for child in node.children[1:]:
            if not isinstance(child, Tree):
                continue

            if child.data == "jny_meta_line":
                token = child.children[0]
                text = str(token)
                # Extract value after the field name separator
                val = re.sub(
                    r"^(?:\*\*|\*|_)?(?:Actor|Goal|Context)(?:\*\*|\*|_)?[:=\s]\s*",
                    "",
                    text,
                    flags=re.IGNORECASE,
                ).strip()
                token_type = token.type  # type: ignore[attr-defined]
                if token_type == "JNY_ACTOR_FIELD":
                    parsed_data["actor"] = val
                elif token_type == "JNY_GOAL_FIELD":
                    parsed_data["goal"] = val
                elif token_type == "JNY_CONTEXT_FIELD":
                    parsed_data["context"] = val

            elif child.data == "jny_validates_line":
                token = child.children[0]
                text = str(token)
                val = re.sub(r"^[Vv]alidates[:=\s]\s*", "", text).strip()
                parsed_data["validates"] = [ref.strip() for ref in val.split(",") if ref.strip()]

            elif child.data == "jny_body_line":
                # Preamble body text (after metadata, before sections)
                for tok in child.children:
                    if hasattr(tok, "type") and tok.type == "TEXT":  # type: ignore[attr-defined]
                        parsed_data["body_lines"].append(str(tok))

            elif child.data == "jny_block":
                # ## Section with content
                section_hdr = str(child.children[0])
                section_name = re.sub(r"^##\s*", "", section_hdr).strip()
                section_lines: list[str] = []
                for sub in child.children[1:]:
                    if isinstance(sub, Tree) and sub.data == "jny_content_line":
                        for tok in sub.children:
                            if hasattr(tok, "type") and tok.type == "TEXT":  # type: ignore[attr-defined]
                                section_lines.append(str(tok))
                            elif hasattr(tok, "type"):  # type: ignore[attr-defined]
                                section_lines.append("")  # blank line
                parsed_data["sections"].append(
                    {
                        "name": section_name,
                        "content": "\n".join(section_lines).strip(),
                    }
                )

        # Fallback: if tree parsing didn't extract fields, try regex on raw_text
        if not parsed_data["actor"]:
            actor_match = _ACTOR_RE.search(raw_text)
            if actor_match:
                parsed_data["actor"] = actor_match.group("actor").strip()
        if not parsed_data["goal"]:
            goal_match = _GOAL_RE.search(raw_text)
            if goal_match:
                parsed_data["goal"] = goal_match.group("goal").strip()
        if not parsed_data["validates"]:
            validates_match = _VALIDATES_RE.search(raw_text)
            if validates_match:
                refs_str = validates_match.group("validates")
                parsed_data["validates"] = [
                    ref.strip() for ref in refs_str.split(",") if ref.strip()
                ]

        return ParsedContent(
            content_type="journey",
            start_line=header_line,
            end_line=end_line,
            raw_text=raw_text,
            parsed_data=parsed_data,
        )

    # ------------------------------------------------------------------
    # Definition block extraction
    # Implements: REQ-d00221-B
    # ------------------------------------------------------------------

    def _extract_definition_block(self, node: Tree) -> dict[str, Any] | None:
        """Extract term, definition, and metadata from a definition_block node.

        The grammar rule is: definition_block: TEXT _NL (DEF_LINE _NL)+
        DEF_LINE tokens match ": <text>" lines.
        """
        term_name: str | None = None
        def_lines: list[str] = []
        collection = False
        indexed = True
        is_reference = False
        reference_fields: dict[str, str] = {}
        reference_term = ""
        reference_source = ""
        start_line = 0

        for child in node.children:
            if isinstance(child, Token):
                if child.type == "TEXT":
                    term_name = str(child).strip()
                    start_line = child.line  # type: ignore[attr-defined]
                elif child.type == "DEF_LINE":
                    # Strip leading ": " from the definition line
                    line_text = str(child)
                    if line_text.startswith(": "):
                        line_text = line_text[2:]
                    elif line_text.startswith(":"):
                        line_text = line_text[1:].lstrip()

                    # Check for metadata flags
                    stripped = line_text.strip()
                    low = stripped.lower()
                    if low == "collection: true":
                        collection = True
                    elif low == "collection: false":
                        collection = False
                    elif low == "indexed: true":
                        indexed = True
                    elif low == "indexed: false":
                        indexed = False
                    # Reference-type marker
                    elif low == "reference":
                        is_reference = True
                    # Structured citation fields
                    elif low.startswith("title:"):
                        reference_fields["title"] = stripped[6:].strip()
                    elif low.startswith("version:"):
                        reference_fields["version"] = stripped[8:].strip()
                    elif low.startswith("effective date:"):
                        reference_fields["effective_date"] = stripped[15:].strip()
                    elif low.startswith("url:"):
                        url_val = stripped[4:].strip()
                        if url_val.startswith("<") and url_val.endswith(">"):
                            url_val = url_val[1:-1]
                        reference_fields["url"] = url_val
                    # Synonym/alias metadata
                    elif low.startswith("reference term:"):
                        val = stripped[15:].strip()
                        val = val.strip("_").strip("*")
                        reference_term = val
                    elif low.startswith("reference source:"):
                        val = stripped[17:].strip()
                        val = val.strip("_").strip("*")
                        reference_source = val
                    else:
                        def_lines.append(line_text)

        if not term_name:
            return None

        return {
            "term": term_name,
            "definition": "\n".join(def_lines).strip(),
            "collection": collection,
            "indexed": indexed,
            "line": start_line,
            "is_reference": is_reference,
            "reference_fields": reference_fields,
            "reference_term": reference_term,
            "reference_source": reference_source,
        }

    def _transform_definition_block(self, node: Tree) -> ParsedContent:
        """Transform a file-level definition_block into ParsedContent."""
        data = self._extract_definition_block(node)
        raw_text = self._reconstruct_raw_text(node)
        start = self._first_line(node)
        end = self._last_line(node)

        if data is None:
            return self._make_remainder(start, end, raw_text)

        return ParsedContent(
            content_type="definition_block",
            start_line=start,
            end_line=end,
            raw_text=raw_text,
            parsed_data=data,
        )

    # ------------------------------------------------------------------
    # Gap filling
    # ------------------------------------------------------------------

    def _fill_blank_line_gaps(self, results: list[ParsedContent]) -> list[ParsedContent]:
        """Insert REMAINDER blocks for blank lines between parsed content.

        The Lark grammar treats bare newlines (_NL) at file level as
        anonymous tokens, so they are discarded from the parse tree.
        This method reconstructs those blank lines from the original
        source text, creating REMAINDER nodes so that render_file
        can reproduce them faithfully.

        When content is later deleted, its REMAINDER separators are
        removed too, giving automatic compaction.
        """
        if not results:
            return results

        results.sort(key=lambda r: r.start_line)
        total_lines = len(self._source_lines)
        filled: list[ParsedContent] = []
        prev_end = 0

        for item in results:
            if item.start_line > prev_end + 1:
                gap_lines = [
                    (ln, self._source_lines[ln - 1])
                    for ln in range(prev_end + 1, item.start_line)
                    if ln - 1 < total_lines
                ]
                if gap_lines:
                    self._flush_remainder(gap_lines, filled)
            filled.append(item)
            prev_end = max(prev_end, item.end_line)

        # Trailing blank lines
        if prev_end < total_lines:
            gap_lines = [
                (ln, self._source_lines[ln - 1])
                for ln in range(prev_end + 1, total_lines + 1)
                if ln - 1 < total_lines
            ]
            if gap_lines:
                self._flush_remainder(gap_lines, filled)

        return filled

    # ------------------------------------------------------------------
    # Remainder handling
    # ------------------------------------------------------------------

    def _flush_remainder(
        self,
        lines: list[tuple[int, str]],
        results: list[ParsedContent],
    ) -> None:
        """Group contiguous remainder lines into ParsedContent blocks."""
        if not lines:
            return

        groups: list[list[tuple[int, str]]] = []
        current: list[tuple[int, str]] = []

        for ln, text in lines:
            if not current:
                current.append((ln, text))
            elif ln == current[-1][0] + 1:
                current.append((ln, text))
            else:
                groups.append(current)
                current = [(ln, text)]
        if current:
            groups.append(current)

        for group in groups:
            results.append(
                ParsedContent(
                    content_type="remainder",
                    start_line=group[0][0],
                    end_line=group[-1][0],
                    raw_text="\n".join(text for _, text in group),
                    parsed_data={},
                )
            )

    # ------------------------------------------------------------------
    # Reference parsing
    # ------------------------------------------------------------------

    def _parse_refs(self, refs_str: str) -> list[str]:
        """Parse comma-separated reference list, normalizing to canonical form."""
        if not refs_str:
            return []
        stripped = refs_str.strip()
        if stripped in _NO_REF_VALUES:
            return []
        parts = [p.strip() for p in refs_str.split(",")]
        result = []
        for p in parts:
            if not p or p in _NO_REF_VALUES:
                continue
            canonical = self.resolver.to_canonical(p)
            result.append(canonical if canonical else p)
        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _extract_text_from_body_line(self, node: Tree) -> tuple[int, str]:
        """Extract line number and text from a body_line node.

        body_line has either TEXT _NL (text line) or just _NL (blank line).
        """
        for child in node.children:
            if isinstance(child, Token) and child.type == "TEXT":
                return (child.line, str(child))  # type: ignore[attr-defined]
        # Bare newline (blank line) -- use Lark's propagated position metadata.
        meta = getattr(node, "meta", None)
        if meta and hasattr(meta, "line") and meta.line > 0:
            return (meta.line, "")
        return (0, "")

    def _reconstruct_raw_text(self, node: Tree) -> str:
        """Reconstruct raw text from the original source using line range."""
        if self._source_lines:
            start = self._first_line(node)
            end = self._last_line(node)
            if start > 0 and end >= start:
                # Lines are 1-indexed
                return "\n".join(self._source_lines[start - 1 : end])
        # Fallback: join all tokens
        tokens: list[str] = []
        for token in node.scan_values(lambda v: isinstance(v, Token)):
            tokens.append(str(token))
        return "\n".join(tokens)

    def _first_line(self, node: Tree) -> int:
        """Get the first line number from a tree node."""
        first = 999999999
        for token in node.scan_values(lambda v: isinstance(v, Token)):
            if hasattr(token, "line") and token.line < first:  # type: ignore[attr-defined]
                first = token.line  # type: ignore[attr-defined]
        return first if first < 999999999 else 0

    def _last_line(self, node: Tree) -> int:
        """Get the last line number from a tree node."""
        last = 0
        for token in node.scan_values(lambda v: isinstance(v, Token)):
            if hasattr(token, "line") and token.line > last:  # type: ignore[attr-defined]
                last = token.line  # type: ignore[attr-defined]
        return last

    def _make_remainder(self, start: int, end: int, text: str) -> ParsedContent:
        """Create a remainder ParsedContent."""
        return ParsedContent(
            content_type="remainder",
            start_line=start,
            end_line=end,
            raw_text=text,
            parsed_data={},
        )
