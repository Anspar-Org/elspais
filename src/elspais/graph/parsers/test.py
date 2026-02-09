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
    from elspais.utilities.patterns import PatternConfig


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
        pattern_config: PatternConfig | None = None,
        reference_resolver: ReferenceResolver | None = None,
    ) -> None:
        """Initialize TestParser with optional configuration.

        Args:
            pattern_config: Configuration for ID structure. If None, uses defaults.
            reference_resolver: Resolver for file-specific reference config. If None,
                               uses default ReferenceConfig.
        """
        self._pattern_config = pattern_config
        self._reference_resolver = reference_resolver

    def _get_pattern_config(self, context: ParseContext) -> PatternConfig:
        """Get pattern config from context or instance.

        Args:
            context: Parse context that may contain pattern config.

        Returns:
            PatternConfig to use for parsing.
        """
        if self._pattern_config is not None:
            return self._pattern_config

        if "pattern_config" in context.config:
            return context.config["pattern_config"]

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

    def _get_reference_config(
        self, context: ParseContext, pattern_config: PatternConfig
    ) -> ReferenceConfig:
        """Get reference config for the current file.

        Args:
            context: Parse context with file path.
            pattern_config: Pattern config (unused but available for consistency).

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

    def _build_test_name_pattern(
        self, pattern_config: PatternConfig, ref_config: ReferenceConfig
    ) -> re.Pattern[str]:
        """Build pattern for matching REQ references in test function names.

        Test names use underscores: def test_foo_REQ_p00001_A

        Args:
            pattern_config: Configuration for ID structure.
            ref_config: Configuration for reference matching.

        Returns:
            Compiled regex pattern for matching test name references.
        """
        prefix = pattern_config.prefix

        # Get type codes
        type_codes = pattern_config.get_all_type_ids()
        if type_codes:
            type_pattern = f"(?:{'|'.join(re.escape(t) for t in type_codes)})"
        else:
            type_pattern = r"[a-z]"

        # Get ID format
        id_format = pattern_config.id_format
        style = id_format.get("style", "numeric")
        digits = id_format.get("digits", 5)

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
        pattern_config = self._get_pattern_config(context)
        ref_config = self._get_reference_config(context, pattern_config)

        # Build patterns dynamically based on config
        test_name_pattern = self._build_test_name_pattern(pattern_config, ref_config)
        comment_pattern = build_comment_pattern(pattern_config, ref_config, "validates")
        block_header_pattern = build_block_header_pattern(ref_config, "validates")
        block_ref_pattern = build_block_ref_pattern(pattern_config, ref_config)

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

        # File-level default validates (# Tests REQ-xxx before any def/class)
        file_default_validates: list[str] = []

        # Context at each line
        line_context: dict[int, tuple[str | None, str | None, int]] = {}

        for ln, text in lines:
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
                    prefix = pattern_config.prefix
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
                prefix = pattern_config.prefix
                if ref.lower().startswith(prefix.lower() + "-"):
                    ref = prefix + ref[len(prefix) :]
                validates.append(ref)

            # Check for REQ in comment (single-line)
            comment_match = comment_pattern.search(text)
            if comment_match:
                refs_str = comment_match.group("refs")
                # Extract individual REQ IDs from the refs string
                prefix = pattern_config.prefix
                for ref_match in re.finditer(
                    rf"{re.escape(prefix)}[-_][A-Za-z0-9\-_]+", refs_str, re.IGNORECASE
                ):
                    ref = ref_match.group(0).replace("_", "-")
                    # Normalize prefix case (e.g., req-d00001 -> REQ-d00001)
                    if ref.lower().startswith(prefix.lower() + "-"):
                        ref = prefix + ref[len(prefix) :]
                    validates.append(ref)

            if validates:
                yield ParsedContent(
                    content_type="test_ref",
                    start_line=ln,
                    end_line=ln,
                    raw_text=text,
                    parsed_data={
                        "validates": validates,
                        "function_name": func_name,
                        "class_name": class_name,
                        "function_line": func_line,
                        "file_default_validates": file_default_validates,
                    },
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
