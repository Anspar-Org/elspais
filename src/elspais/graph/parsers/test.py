"""TestParser - Priority 80 parser for test references.

Parses test files for requirement references in test names and comments.
Uses the shared reference_config infrastructure for configurable patterns.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING

from elspais.graph.parsers import ParseContext, ParsedContent
from elspais.graph.parsers.config_helpers import is_empty_comment
from elspais.utilities.reference_config import (
    ReferenceConfig,
    ReferenceResolver,
    build_block_header_pattern,
    build_block_ref_pattern,
    build_comment_pattern,
)

if TYPE_CHECKING:
    from elspais.utilities.patterns import IdResolver

# Pattern for expected-broken-links marker
_EXPECTED_BROKEN_LINKS_RE = re.compile(
    r"(?:#|//|--|/\*|<!--)\s*elspais:\s*expected-broken-links\s+(\d+)",
    re.IGNORECASE,
)
_MARKER_HEADER_LINES = 20


# Implements: REQ-d00082-J
class TestParser:
    """Parser for test references.

    Priority: 80 (after code references)

    Recognizes:
    - Test names with REQ references: test_foo_REQ_p00001
    - Comments with REQ references: # Tests REQ-xxx
    - Multiline block headers: -- TESTS REQUIREMENTS:
    - Multiline block items: --   REQ-xxx: Description

    Uses configurable patterns from ReferenceConfig for:
    - Comment styles (# // -- etc.)
    - Keywords (Tests, Validates, etc.)
    - Separator characters (- _ etc.)
    """

    priority = 80

    def __init__(
        self,
        resolver: IdResolver | None = None,
        reference_resolver: ReferenceResolver | None = None,
    ) -> None:
        """Initialize TestParser with optional configuration.

        Args:
            resolver: IdResolver for ID structure. If None, uses defaults.
            reference_resolver: Resolver for file-specific reference config. If None,
                               uses default ReferenceConfig.
        """
        self._resolver = resolver
        self._reference_resolver = reference_resolver

    def _get_resolver(self, context: ParseContext) -> IdResolver:
        """Get IdResolver from context or instance.

        Args:
            context: Parse context that may contain resolver.

        Returns:
            IdResolver to use for parsing.
        """
        if self._resolver is not None:
            return self._resolver

        if "resolver" in context.config:
            return context.config["resolver"]

        from elspais.utilities.patterns import IdPatternConfig, IdResolver

        config = IdPatternConfig.from_dict(
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
        return IdResolver(config)

    def _get_reference_config(
        self,
        context: ParseContext,
    ) -> ReferenceConfig:
        """Get reference config for the current file.

        Args:
            context: Parse context with file path.

        Returns:
            ReferenceConfig for this file.
        """
        if self._reference_resolver is not None:
            file_path = Path(context.file_path)
            repo_root = Path(context.config.get("repo_root", "."))
            return self._reference_resolver.resolve(file_path, repo_root)

        if "reference_resolver" in context.config:
            resolver: ReferenceResolver = context.config["reference_resolver"]
            file_path = Path(context.file_path)
            repo_root = Path(context.config.get("repo_root", "."))
            return resolver.resolve(file_path, repo_root)

        return ReferenceConfig()

    # Implements: REQ-d00082-J
    def _build_test_name_pattern(
        self, resolver: IdResolver, ref_config: ReferenceConfig
    ) -> re.Pattern[str]:
        """Build pattern for matching REQ references in test function names.

        Test names use underscores: def test_foo_REQ_p00001_A

        Args:
            resolver: IdResolver for ID structure.
            ref_config: Configuration for reference matching.

        Returns:
            Compiled regex pattern for matching test name references.
        """
        prefix = resolver.config.namespace

        # Get type codes
        from elspais.utilities.reference_config import _get_type_codes

        type_codes = _get_type_codes(resolver)
        if type_codes:
            type_pattern = f"(?:{'|'.join(re.escape(t) for t in type_codes)})"
        else:
            type_pattern = r"[a-z]"

        # Get ID format from resolver config component
        component = resolver.config.component
        style = component.style
        digits = component.digits

        if style == "numeric":
            id_number_pattern = rf"\d{{{digits}}}"
        else:
            id_number_pattern = r"[A-Za-z0-9]+"

        # Assertion pattern (uppercase letters, can be multiple like A_B_C)
        # Add negative lookahead to prevent matching lowercase continuation
        assertion_pattern = r"(?:_[A-Z](?![a-z]))+"

        # Test names use underscores, so pattern uses _ for separators
        full_pattern = (
            rf"def\s+test_\w*"
            rf"(?P<ref>{re.escape(prefix)}_{type_pattern}{id_number_pattern}"
            rf"(?:{assertion_pattern})?)"
        )

        flags = 0 if ref_config.case_sensitive else re.IGNORECASE
        return re.compile(full_pattern, flags)

    # Implements: REQ-d00054-A
    def claim_and_parse(
        self,
        lines: list[tuple[int, str]],
        context: ParseContext,
    ) -> Iterator[ParsedContent]:
        """Claim and parse test references.

        Tracks function and class context so the builder can create
        canonical TEST node IDs. Also supports file-level scope:
        a ``# Tests REQ-xxx`` comment at module scope (before any
        function/class) becomes the default for all test functions
        in the file.

        Args:
            lines: List of (line_number, content) tuples.
            context: Parsing context.

        Yields:
            ParsedContent for each test reference.
        """
        resolver = self._get_resolver(context)
        ref_config = self._get_reference_config(context)

        # Build patterns dynamically based on config
        test_name_pattern = self._build_test_name_pattern(resolver, ref_config)
        comment_pattern = build_comment_pattern(resolver, ref_config, "validates")
        block_header_pattern = build_block_header_pattern(ref_config, "validates")
        block_ref_pattern = build_block_ref_pattern(resolver, ref_config)

        # Detect expected-broken-links marker in file header
        expected_broken_count = 0
        for _ln, text in lines[:_MARKER_HEADER_LINES]:
            m = _EXPECTED_BROKEN_LINKS_RE.search(text)
            if m:
                expected_broken_count = int(m.group(1))
                break

        # Patterns for tracking function/class context
        func_pattern = re.compile(r"^(\s*)def\s+(test_\w+)\s*\(")
        class_pattern = re.compile(r"^(\s*)class\s+(Test\w*)\s*[:(]")

        # Pre-scan to build function/class context map
        # Maps line_number -> (function_name, class_name, function_line)
        current_class: str | None = None
        current_class_indent: int = -1
        current_func: str | None = None
        current_func_indent: int = -1
        current_func_line: int = 0
        # Whether we've seen any function or class definition yet
        seen_def = False
        # Track triple-quoted string state to skip indent analysis inside them
        in_triple_quote = False

        # File-level default validates (# Tests REQ-xxx before any def/class)
        file_default_validates: list[str] = []

        # Context at each line
        line_context: dict[int, tuple[str | None, str | None, int]] = {}

        for ln, text in lines:
            # Track triple-quoted strings — toggle on odd occurrences of """ or '''
            triple_count = text.count('"""') + text.count("'''")
            was_in_triple = in_triple_quote
            if triple_count % 2 == 1:
                in_triple_quote = not in_triple_quote

            # Skip indent-based context tracking inside or at boundaries of
            # triple-quoted strings (content at column 0 would falsely clear class)
            if in_triple_quote or was_in_triple:
                line_context[ln] = (current_func, current_class, current_func_line)
                continue

            # Track class definitions
            class_match = class_pattern.match(text)
            if class_match:
                indent = len(class_match.group(1))
                current_class = class_match.group(2)
                current_class_indent = indent
                current_func = None
                current_func_indent = -1
                seen_def = True

            # Track function definitions
            func_match = func_pattern.match(text)
            if func_match:
                indent = len(func_match.group(1))
                # If function indent <= class indent, we've left the class
                if current_class and indent <= current_class_indent:
                    current_class = None
                    current_class_indent = -1
                current_func = func_match.group(2)
                current_func_indent = indent
                current_func_line = ln
                seen_def = True

            # If a non-indented line that's not blank/comment, might exit class
            stripped = text.strip()
            if stripped and not stripped.startswith("#") and not class_match and not func_match:
                actual_indent = len(text) - len(text.lstrip())
                if current_class and actual_indent <= current_class_indent:
                    current_class = None
                    current_class_indent = -1
                if current_func and actual_indent <= current_func_indent:
                    current_func = None
                    current_func_indent = -1

            line_context[ln] = (current_func, current_class, current_func_line)

            # Collect file-level default validates (before any def/class)
            if not seen_def:
                cm = comment_pattern.search(text)
                if cm:
                    refs_str = cm.group("refs")
                    prefix = resolver.config.namespace
                    for ref_match in re.finditer(
                        rf"{re.escape(prefix)}[-_][A-Za-z0-9\-_]+",
                        refs_str,
                        re.IGNORECASE,
                    ):
                        ref = ref_match.group(0).replace("_", "-")
                        if ref.lower().startswith(prefix.lower() + "-"):
                            ref = prefix + ref[len(prefix) :]
                        if ref not in file_default_validates:
                            file_default_validates.append(ref)

        # Second pass: extract references with context
        i = 0
        while i < len(lines):
            ln, text = lines[i]
            validates: list[str] = []
            func_name, class_name, func_line = line_context.get(ln, (None, None, 0))

            # Check for REQ in test function name
            name_match = test_name_pattern.search(text)
            if name_match:
                # Convert REQ_p00001 to REQ-p00001 and normalize prefix case
                ref = name_match.group("ref").replace("_", "-")
                # Ensure prefix is uppercase (e.g., req-d00001 -> REQ-d00001)
                prefix = resolver.config.namespace
                if ref.lower().startswith(prefix.lower() + "-"):
                    ref = prefix + ref[len(prefix) :]
                validates.append(ref)

            # Check for REQ in comment (single-line)
            comment_match = comment_pattern.search(text)
            if comment_match:
                refs_str = comment_match.group("refs")
                # Extract individual REQ IDs from the refs string
                prefix = resolver.config.namespace
                for ref_match in re.finditer(
                    rf"{re.escape(prefix)}[-_][A-Za-z0-9\-_]+", refs_str, re.IGNORECASE
                ):
                    ref = ref_match.group(0).replace("_", "-")
                    # Normalize prefix case (e.g., req-d00001 -> REQ-d00001)
                    if ref.lower().startswith(prefix.lower() + "-"):
                        ref = prefix + ref[len(prefix) :]
                    validates.append(ref)

            if validates:
                parsed_data: dict = {
                    "validates": validates,
                    "function_name": func_name,
                    "class_name": class_name,
                    "function_line": func_line,
                    "file_default_validates": file_default_validates,
                }
                if expected_broken_count > 0:
                    parsed_data["expected_broken_count"] = expected_broken_count
                yield ParsedContent(
                    content_type="test_ref",
                    start_line=ln,
                    end_line=ln,
                    raw_text=text,
                    parsed_data=parsed_data,
                )
                i += 1
                continue

            # Check for multiline block header: -- TESTS REQUIREMENTS:
            if block_header_pattern.search(text):
                refs: list[str] = []
                start_ln = ln
                end_ln = ln
                raw_lines = [text]
                i += 1

                # Collect REQ references from subsequent comment lines
                while i < len(lines):
                    next_ln, next_text = lines[i]
                    ref_match = block_ref_pattern.match(next_text)
                    if ref_match:
                        refs.append(ref_match.group("ref"))
                        end_ln = next_ln
                        raw_lines.append(next_text)
                        i += 1
                    elif is_empty_comment(next_text, ref_config.comment_styles):
                        # Empty comment line, skip
                        i += 1
                    else:
                        # Non-comment line or different content, stop
                        break

                if refs:
                    yield ParsedContent(
                        content_type="test_ref",
                        start_line=start_ln,
                        end_line=end_ln,
                        raw_text="\n".join(raw_lines),
                        parsed_data={
                            "validates": refs,
                            "function_name": func_name,
                            "class_name": class_name,
                            "function_line": func_line,
                            "file_default_validates": file_default_validates,
                        },
                    )
                continue

            i += 1
