"""CodeParser - Priority 70 parser for code references.

Parses code comments containing requirement references.
Uses the shared reference_config infrastructure for configurable patterns.
Includes function/class context tracking for TEST→CODE linking.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Any

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

# Language-aware function/class patterns for context tracking
# Python: def name(
_PYTHON_FUNC = re.compile(r"^(\s*)(?:async\s+)?def\s+(\w+)\s*\(")
_PYTHON_CLASS = re.compile(r"^(\s*)class\s+(\w+)\s*[:(]")

# JS/TS: function name(, async function name(, name(, name = function(
_JS_FUNC = re.compile(r"^(\s*)(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(")
_JS_METHOD = re.compile(r"^(\s*)(?:async\s+)?(\w+)\s*\([^)]*\)\s*\{")
_JS_CLASS = re.compile(r"^(\s*)class\s+(\w+)")

# Go: func name(, func (receiver) name(
_GO_FUNC = re.compile(r"^(\s*)func\s+(?:\([^)]+\)\s+)?(\w+)\s*\(")
_GO_STRUCT = re.compile(r"^(\s*)type\s+(\w+)\s+struct\s*\{")

# Rust: pub? fn name(, pub? async fn name(
_RUST_FUNC = re.compile(r"^(\s*)(?:pub\s+)?(?:async\s+)?fn\s+(\w+)\s*[(<]")
_RUST_IMPL = re.compile(r"^(\s*)impl\s+(?:<[^>]+>\s+)?(\w+)")

# C/Java/C#: return_type name(
_C_FUNC = re.compile(
    r"^(\s*)(?:(?:static|public|private|protected|virtual|inline)\s+)*\w[\w:*&<>, ]*\s+(\w+)\s*\("
)
_C_CLASS = re.compile(r"^(\s*)(?:public\s+)?class\s+(\w+)")

# File extension to language mapping
_LANG_MAP: dict[str, str] = {
    ".py": "python",
    ".pyw": "python",
    ".js": "js",
    ".jsx": "js",
    ".ts": "js",
    ".tsx": "js",
    ".mjs": "js",
    ".cjs": "js",
    ".go": "go",
    ".rs": "rust",
    ".c": "c",
    ".cpp": "c",
    ".cc": "c",
    ".cxx": "c",
    ".h": "c",
    ".hpp": "c",
    ".java": "c",
    ".cs": "c",
    ".kt": "c",
}


class CodeParser:
    """Parser for code reference comments.

    Priority: 70 (after requirements and journeys)

    Recognizes comments like:
    - # Implements: REQ-xxx
    - # Validates: REQ-xxx
    - // Implements: REQ-xxx (for JS/TS)
    - // IMPLEMENTS REQUIREMENTS: (multiline block header)
    - //   REQ-xxx: Description (multiline block item)

    Uses configurable patterns from ReferenceConfig for:
    - Comment styles (# // -- etc.)
    - Keywords (Implements, Validates, Tests, etc.)
    - Separator characters (- _ etc.)
    """

    priority = 70

    def __init__(
        self,
        pattern_config: PatternConfig | None = None,
        reference_resolver: ReferenceResolver | None = None,
    ) -> None:
        """Initialize CodeParser with optional configuration.

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
        # Try instance config first
        if self._pattern_config is not None:
            return self._pattern_config

        # Try context config
        if "pattern_config" in context.config:
            return context.config["pattern_config"]

        # Fall back to creating a default
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

        # Try context config
        if "reference_resolver" in context.config:
            resolver: ReferenceResolver = context.config["reference_resolver"]
            file_path = Path(context.file_path)
            repo_root = Path(context.config.get("repo_root", "."))
            return resolver.resolve(file_path, repo_root)

        # Fall back to default config
        return ReferenceConfig()

    @staticmethod
    def _detect_language(file_path: str) -> str:
        """Detect programming language from file extension.

        Args:
            file_path: Path to the source file.

        Returns:
            Language key: 'python', 'js', 'go', 'rust', 'c', or 'unknown'.
        """
        ext = Path(file_path).suffix.lower()
        return _LANG_MAP.get(ext, "unknown")

    @staticmethod
    def _build_line_context(
        lines: list[tuple[int, str]],
        language: str,
    ) -> dict[int, tuple[str | None, str | None, int]]:
        """Build function/class context map for each line.

        Pre-scans lines to determine which function/class each line
        belongs to. Supports Python (indentation-based) and C-family
        languages (brace-based scoping).

        After the initial scan, performs a forward-looking fixup:
        comment lines with no function context look ahead up to 5 lines
        to find a subsequent function definition. This handles the common
        pattern of ``# Implements: REQ-xxx`` placed above a function.

        Args:
            lines: List of (line_number, content) tuples.
            language: Detected language key.

        Returns:
            Dict mapping line_number to (function_name, class_name, function_line).
        """
        # Select patterns for language
        if language == "python":
            func_patterns = [_PYTHON_FUNC]
            class_patterns = [_PYTHON_CLASS]
            scope_mode = "indent"
        elif language == "js":
            func_patterns = [_JS_FUNC, _JS_METHOD]
            class_patterns = [_JS_CLASS]
            scope_mode = "brace"
        elif language == "go":
            func_patterns = [_GO_FUNC]
            class_patterns = [_GO_STRUCT]
            scope_mode = "brace"
        elif language == "rust":
            func_patterns = [_RUST_FUNC]
            class_patterns = [_RUST_IMPL]
            scope_mode = "brace"
        elif language == "c":
            func_patterns = [_C_FUNC]
            class_patterns = [_C_CLASS]
            scope_mode = "brace"
        else:
            # Unknown language: try Python-style patterns as fallback
            func_patterns = [_PYTHON_FUNC]
            class_patterns = [_PYTHON_CLASS]
            scope_mode = "indent"

        current_class: str | None = None
        current_class_indent: int = -1
        current_func: str | None = None
        current_func_indent: int = -1
        current_func_line: int = 0

        # Brace tracking for C-family scope
        brace_depth = 0
        func_brace_start: int = -1
        class_brace_start: int = -1

        line_context: dict[int, tuple[str | None, str | None, int]] = {}

        for ln, text in lines:
            stripped = text.strip()

            # Track braces for C-family languages
            if scope_mode == "brace":
                open_count = text.count("{")
                close_count = text.count("}")
                brace_depth += open_count - close_count

                # Exit function scope when braces close
                if current_func and brace_depth <= func_brace_start:
                    current_func = None
                    current_func_indent = -1

                # Exit class scope when braces close
                if current_class and brace_depth <= class_brace_start:
                    current_class = None
                    current_class_indent = -1

            # Check class patterns
            for pattern in class_patterns:
                class_match = pattern.match(text)
                if class_match:
                    indent = len(class_match.group(1))
                    # For indent-based: check if we've left current class
                    if scope_mode == "indent" and current_class and indent <= current_class_indent:
                        pass  # Will be replaced below
                    current_class = class_match.group(2)
                    current_class_indent = indent
                    current_func = None
                    current_func_indent = -1
                    if scope_mode == "brace":
                        class_brace_start = brace_depth - open_count
                    break

            # Check function patterns
            for pattern in func_patterns:
                func_match = pattern.match(text)
                if func_match:
                    indent = len(func_match.group(1))
                    # For indent-based: check if function exits class scope
                    if scope_mode == "indent":
                        if current_class and indent <= current_class_indent:
                            current_class = None
                            current_class_indent = -1
                    current_func = func_match.group(2)
                    current_func_indent = indent
                    current_func_line = ln
                    if scope_mode == "brace":
                        func_brace_start = brace_depth - open_count
                    break

            # For indent-based: track scope exits via indentation
            if scope_mode == "indent" and stripped and not class_match and not func_match:
                actual_indent = len(text) - len(text.lstrip())
                if current_class and actual_indent <= current_class_indent:
                    if not stripped.startswith("#") and not stripped.startswith("//"):
                        current_class = None
                        current_class_indent = -1
                if current_func and actual_indent <= current_func_indent:
                    if not stripped.startswith("#") and not stripped.startswith("//"):
                        current_func = None
                        current_func_indent = -1

            # Suppress match variable leaking (used in loop above)
            class_match = None  # type: ignore[assignment]
            func_match = None  # type: ignore[assignment]

            line_context[ln] = (current_func, current_class, current_func_line)

        # Forward-looking fixup: if a comment line has no function context,
        # look ahead up to 5 lines for the next function definition.
        # This handles "# Implements: REQ-xxx" placed above a function.
        for idx, (ln, text) in enumerate(lines):
            func_name, class_name, func_line = line_context[ln]
            if func_name is not None:
                continue

            stripped = text.strip()
            # Only fixup comment lines
            is_comment = False
            for prefix in ("#", "//", "--", "/*", "<!--"):
                if stripped.startswith(prefix):
                    is_comment = True
                    break
            if not is_comment:
                continue

            # Look ahead up to 5 lines for a function definition
            for ahead in range(1, min(6, len(lines) - idx)):
                ahead_ln, ahead_text = lines[idx + ahead]
                for pattern in func_patterns:
                    m = pattern.match(ahead_text)
                    if m:
                        ahead_func = m.group(2)
                        # Use the class context from the ahead line if available
                        _, ahead_class, _ = line_context.get(ahead_ln, (None, None, 0))
                        line_context[ln] = (ahead_func, ahead_class or class_name, ahead_ln)
                        break
                else:
                    continue
                break

        return line_context

    def claim_and_parse(
        self,
        lines: list[tuple[int, str]],
        context: ParseContext,
    ) -> Iterator[ParsedContent]:
        """Claim and parse code reference comments.

        Tracks function and class context so the builder can create
        CODE nodes with function metadata for TEST→CODE linking.

        Args:
            lines: List of (line_number, content) tuples.
            context: Parsing context.

        Yields:
            ParsedContent for each code reference.
        """
        # Get configs for this file
        pattern_config = self._get_pattern_config(context)
        ref_config = self._get_reference_config(context, pattern_config)

        # Build function/class context map (pre-scan)
        language = self._detect_language(context.file_path)
        line_context = self._build_line_context(lines, language)

        # Build patterns dynamically based on config
        implements_pattern = build_comment_pattern(pattern_config, ref_config, "implements")
        validates_pattern = build_comment_pattern(pattern_config, ref_config, "validates")
        block_header_pattern = build_block_header_pattern(ref_config, "implements")
        block_ref_pattern = build_block_ref_pattern(pattern_config, ref_config)

        i = 0
        while i < len(lines):
            ln, text = lines[i]
            func_name, class_name, func_line = line_context.get(ln, (None, None, 0))

            # Check for single-line patterns first
            impl_match = implements_pattern.search(text)
            val_match = validates_pattern.search(text)

            if impl_match or val_match:
                parsed_data: dict[str, Any] = {
                    "implements": [],
                    "validates": [],
                    "function_name": func_name,
                    "class_name": class_name,
                    "function_line": func_line,
                }

                if impl_match:
                    refs = [r.strip() for r in impl_match.group("refs").split(",")]
                    parsed_data["implements"] = refs

                if val_match:
                    refs = [r.strip() for r in val_match.group("refs").split(",")]
                    parsed_data["validates"] = refs

                yield ParsedContent(
                    content_type="code_ref",
                    start_line=ln,
                    end_line=ln,
                    raw_text=text,
                    parsed_data=parsed_data,
                )
                i += 1
                continue

            # Check for multiline block header: // IMPLEMENTS REQUIREMENTS:
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
                        content_type="code_ref",
                        start_line=start_ln,
                        end_line=end_ln,
                        raw_text="\n".join(raw_lines),
                        parsed_data={
                            "implements": refs,
                            "validates": [],
                            "function_name": func_name,
                            "class_name": class_name,
                            "function_line": func_line,
                        },
                    )
                continue

            i += 1
