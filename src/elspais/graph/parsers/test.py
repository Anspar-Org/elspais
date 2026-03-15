"""TestParser - Priority 80 parser for test references.

Parses test files for requirement references in test names and comments.
Uses the shared reference_config infrastructure for configurable patterns.

Pre-scan strategies:
- Python files (.py): AST-based scanning via ast.parse() for 100% accurate
  class/function context (immune to multiline strings, decorators, etc.)
- Other files: text-based indent tracking (fallback)
- External command: configurable via [testing].prescan_command for any language
"""

from __future__ import annotations

import ast
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
        prescan_data: dict[str, list[dict]] | None = None,
    ) -> None:
        """Initialize TestParser with optional configuration.

        Args:
            resolver: IdResolver for ID structure. If None, uses defaults.
            reference_resolver: Resolver for file-specific reference config. If None,
                               uses default ReferenceConfig.
            prescan_data: Optional externally-provided test structure data.
                Maps file path -> list of dicts with keys: function, class, line.
                Produced by [testing].prescan_command or injected for testing.
        """
        self._resolver = resolver
        self._reference_resolver = reference_resolver
        self._prescan_data = prescan_data

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
        type_codes = resolver.all_type_alias_values()
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

    def _ast_prescan(
        self,
        source: str,
        lines: list[tuple[int, str]],
    ) -> tuple[
        dict[int, tuple[str | None, str | None, int]],
        list[tuple[int, str, str | None]],
        int,
    ]:
        """Pre-scan Python source using AST for accurate class/function context.

        Uses ast.parse() to walk the syntax tree, immune to multiline strings,
        decorators, and other constructs that confuse text-based scanning.

        Args:
            source: Full source text of the file.
            lines: List of (line_number, content) tuples.

        Returns:
            Tuple of (line_context, all_test_funcs, first_def_line):
            - line_context: Maps line_number -> (func_name, class_name, func_line)
            - all_test_funcs: List of (func_line, func_name, class_name)
            - first_def_line: Line number of first class/function def (0 if none)
        """
        tree = ast.parse(source)

        # Collect all test functions with their enclosing class
        # (lineno, end_lineno, func_name, class_name)
        func_ranges: list[tuple[int, int, str, str | None]] = []
        all_test_funcs: list[tuple[int, str, str | None]] = []
        first_def_line = 0

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                if not first_def_line:
                    first_def_line = node.lineno
                # Only process Test* classes
                if node.name.startswith("Test"):
                    for item in ast.walk(node):
                        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            if item.name.startswith("test_"):
                                end = item.end_lineno or item.lineno
                                func_ranges.append((item.lineno, end, item.name, node.name))
                                all_test_funcs.append((item.lineno, item.name, node.name))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not first_def_line:
                    first_def_line = node.lineno
                # Module-level test functions (not inside a class)
                # Check parent is Module (not nested in class)
                # ast.walk doesn't preserve parent, so we check if this
                # function was already collected from a class walk above
                pass

        # Second pass: collect module-level test functions
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not first_def_line or node.lineno <= first_def_line:
                    first_def_line = node.lineno
                if node.name.startswith("test_"):
                    end = node.end_lineno or node.lineno
                    func_ranges.append((node.lineno, end, node.name, None))
                    all_test_funcs.append((node.lineno, node.name, None))

        # Sort by line number for consistent ordering
        func_ranges.sort(key=lambda x: x[0])
        all_test_funcs.sort(key=lambda x: x[0])

        # Build line_context map: for each source line, determine which
        # function (if any) it falls within
        line_context: dict[int, tuple[str | None, str | None, int]] = {}
        for ln, _text in lines:
            func_name = None
            class_name = None
            func_line = 0
            for start, end, fname, cname in func_ranges:
                if start <= ln <= end:
                    func_name = fname
                    class_name = cname
                    func_line = start
                    break
            line_context[ln] = (func_name, class_name, func_line)

        return line_context, all_test_funcs, first_def_line

    def _text_prescan(
        self,
        lines: list[tuple[int, str]],
    ) -> tuple[
        dict[int, tuple[str | None, str | None, int]],
        list[tuple[int, str, str | None]],
        int,
    ]:
        """Pre-scan source using text-based indent tracking.

        Fallback for non-Python files or when AST parsing fails.

        Args:
            lines: List of (line_number, content) tuples.

        Returns:
            Same tuple format as _ast_prescan.
        """
        func_pattern = re.compile(r"^(\s*)def\s+(test_\w+)\s*\(")
        class_pattern = re.compile(r"^(\s*)class\s+(Test\w*)\s*[:(]")

        current_class: str | None = None
        current_class_indent: int = -1
        current_func: str | None = None
        current_func_indent: int = -1
        current_func_line: int = 0
        first_def_line = 0

        line_context: dict[int, tuple[str | None, str | None, int]] = {}
        all_test_funcs: list[tuple[int, str, str | None]] = []

        for ln, text in lines:
            class_match = class_pattern.match(text)
            if class_match:
                indent = len(class_match.group(1))
                current_class = class_match.group(2)
                current_class_indent = indent
                current_func = None
                current_func_indent = -1
                if not first_def_line:
                    first_def_line = ln

            func_match = func_pattern.match(text)
            if func_match:
                indent = len(func_match.group(1))
                if current_class and indent <= current_class_indent:
                    current_class = None
                    current_class_indent = -1
                current_func = func_match.group(2)
                current_func_indent = indent
                current_func_line = ln
                if not first_def_line:
                    first_def_line = ln
                all_test_funcs.append((ln, current_func, current_class))

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

        return line_context, all_test_funcs, first_def_line

    def _external_prescan(
        self,
        file_entries: list[dict],
        lines: list[tuple[int, str]],
    ) -> tuple[
        dict[int, tuple[str | None, str | None, int]],
        list[tuple[int, str, str | None]],
        int,
    ]:
        """Build prescan data from externally-provided test structure.

        Args:
            file_entries: List of dicts with keys: function, class, line.
            lines: List of (line_number, content) tuples.

        Returns:
            Same tuple format as _ast_prescan.
        """
        all_test_funcs: list[tuple[int, str, str | None]] = []
        # Build ranges: each function spans from its line to the next function's line - 1
        # (or end of file)
        sorted_entries = sorted(file_entries, key=lambda e: e["line"])
        func_ranges: list[tuple[int, int, str, str | None]] = []

        for i, entry in enumerate(sorted_entries):
            start = entry["line"]
            fname = entry["function"]
            cname = entry.get("class")
            if fname.startswith("test_"):
                all_test_funcs.append((start, fname, cname))
            # End is either next function's line - 1, or last source line
            if i + 1 < len(sorted_entries):
                end = sorted_entries[i + 1]["line"] - 1
            else:
                end = lines[-1][0] if lines else start
            func_ranges.append((start, end, fname, cname))

        first_def_line = sorted_entries[0]["line"] if sorted_entries else 0

        line_context: dict[int, tuple[str | None, str | None, int]] = {}
        for ln, _text in lines:
            func_name = None
            class_name = None
            func_line = 0
            for start, end, fname, cname in func_ranges:
                if start <= ln <= end:
                    func_name = fname
                    class_name = cname
                    func_line = start
                    break
            line_context[ln] = (func_name, class_name, func_line)

        return line_context, all_test_funcs, first_def_line

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

        # Pre-scan: choose strategy based on file type
        is_python = context.file_path.endswith(".py")

        if self._prescan_data and context.file_path in self._prescan_data:
            # Use externally-provided prescan data (from prescan_command)
            line_context, all_test_funcs, first_def_line = self._external_prescan(
                self._prescan_data[context.file_path], lines
            )
        elif is_python:
            # Use AST for Python files, fall back to text-based on parse error
            source = "\n".join(text for _, text in lines)
            try:
                line_context, all_test_funcs, first_def_line = self._ast_prescan(source, lines)
            except SyntaxError:
                line_context, all_test_funcs, first_def_line = self._text_prescan(lines)
        else:
            line_context, all_test_funcs, first_def_line = self._text_prescan(lines)

        # Collect file-level default validates (# Tests REQ-xxx before first def/class)
        file_default_validates: list[str] = []
        for ln, text in lines:
            if first_def_line and ln >= first_def_line:
                break
            cm = comment_pattern.search(text)
            if cm:
                refs_str = cm.group("refs")
                prefix = resolver.config.namespace
                for ref_match in re.finditer(
                    rf"{re.escape(prefix)}[-_][A-Za-z0-9\-_]+",
                    refs_str,
                    re.IGNORECASE,
                ):
                    ref = resolver.normalize_ref(ref_match.group(0))
                    if ref not in file_default_validates:
                        file_default_validates.append(ref)

        # Second pass: extract references with context
        emitted_func_lines: set[int] = set()  # Track which functions got emitted
        i = 0
        while i < len(lines):
            ln, text = lines[i]
            validates: list[str] = []
            func_name, class_name, func_line = line_context.get(ln, (None, None, 0))

            # Check for REQ in test function name
            name_match = test_name_pattern.search(text)
            if name_match:
                # Convert REQ_p00001 to REQ-p00001 and normalize prefix case
                ref = resolver.normalize_ref(name_match.group("ref"))
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
                    ref = resolver.normalize_ref(ref_match.group(0))
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
                if func_line:
                    emitted_func_lines.add(func_line)
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
                    if func_line:
                        emitted_func_lines.add(func_line)
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

        # Third pass: emit unlinked test functions (no requirement references)
        # so they appear in the graph for result linking and traceability gaps
        for func_line, func_name, class_name in all_test_funcs:
            if func_line not in emitted_func_lines:
                # Inherit file-level validates if present
                validates = list(file_default_validates)
                yield ParsedContent(
                    content_type="test_ref",
                    start_line=func_line,
                    end_line=func_line,
                    raw_text="",
                    parsed_data={
                        "validates": validates,
                        "function_name": func_name,
                        "class_name": class_name,
                        "function_line": func_line,
                        "file_default_validates": file_default_validates,
                    },
                )
