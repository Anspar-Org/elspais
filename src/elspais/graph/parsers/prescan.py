"""Prescan utilities for code and test file parsing.

Standalone module containing language detection and pre-scan functions
extracted from CodeParser and TestParser. These are pure utility functions
with no dependency on ReferenceConfig.

Used by the Lark FileDispatcher for building line context maps and
detecting test function structure before grammar-based parsing.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

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

# Dart: test('desc', ...), testWidgets('desc', ...), group('desc', ...)
_DART_TEST = re.compile(r"^(\s*)(?:test|testWidgets)\s*\(")
_DART_GROUP = re.compile(r"^(\s*)group\s*\(")


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
    ".dart": "dart",  # Dart: use dart_prescan() for test files
}


def detect_language(file_path: str) -> str:
    """Detect programming language from file extension.

    Args:
        file_path: Path to the source file.

    Returns:
        Language key: 'python', 'js', 'go', 'rust', 'c', or 'unknown'.
    """
    ext = Path(file_path).suffix.lower()
    return _LANG_MAP.get(ext, "unknown")


def build_line_context(
    lines: list[tuple[int, str]],
    language: str,
) -> dict[int, tuple[str | None, str | None, int, int]]:
    """Build function/class context map for each line.

    Pre-scans lines to determine which function/class each line
    belongs to. Supports Python (indentation-based) and C-family
    languages (brace-based scoping).

    After the initial scan, performs a forward-looking fixup:
    comment lines with no function context look ahead up to 5 lines
    to find a subsequent function definition. This handles the common
    pattern of ``# Implements: <REQ-ID>`` placed above a function.

    Args:
        lines: List of (line_number, content) tuples.
        language: Detected language key.

    Returns:
        Dict mapping line_number to (function_name, class_name, function_line, function_end_line).
        function_end_line is 0 (sentinel) for text-based scanning since end lines are unreliable.
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

    line_context: dict[int, tuple[str | None, str | None, int, int]] = {}

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

        # func_end_line=0 sentinel: text-based scanning can't reliably determine end lines
        line_context[ln] = (current_func, current_class, current_func_line, 0)

    # Forward-looking fixup: if a comment line has no function context,
    # look ahead up to 5 lines for the next function definition.
    # This handles "# Implements: <REQ-ID>" placed above a function.
    for idx, (ln, text) in enumerate(lines):
        func_name, class_name, func_line, _func_end = line_context[ln]
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
                    _, ahead_class, _, _ = line_context.get(ahead_ln, (None, None, 0, 0))
                    line_context[ln] = (ahead_func, ahead_class or class_name, ahead_ln, 0)
                    break
            else:
                continue
            break

    return line_context


def ast_prescan(
    source: str,
    lines: list[tuple[int, str]],
) -> tuple[
    dict[int, tuple[str | None, str | None, int, int]],
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
        - line_context: Maps line_number -> (func_name, class_name, func_line, func_end_line)
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
    line_context: dict[int, tuple[str | None, str | None, int, int]] = {}
    for ln, _text in lines:
        func_name = None
        class_name = None
        func_line = 0
        func_end_line = 0
        for start, end, fname, cname in func_ranges:
            if start <= ln <= end:
                func_name = fname
                class_name = cname
                func_line = start
                func_end_line = end
                break
        line_context[ln] = (func_name, class_name, func_line, func_end_line)

    # Forward-looking fixup: comment lines above a function def fall outside
    # the AST range.  Look ahead up to 5 lines to bind them to the next
    # function — same logic that text_prescan already applies.
    for idx, (ln, text) in enumerate(lines):
        func_name, _class_name, _func_line, _func_end = line_context[ln]
        if func_name is not None:
            continue

        stripped = text.strip()
        is_comment = False
        for prefix in ("#", "//", "--", "/*", "<!--"):
            if stripped.startswith(prefix):
                is_comment = True
                break
        if not is_comment:
            continue

        for ahead in range(1, min(6, len(lines) - idx)):
            ahead_ln, _ahead_text = lines[idx + ahead]
            ahead_func, ahead_class, ahead_fline, ahead_fend = line_context.get(
                ahead_ln, (None, None, 0, 0)
            )
            if ahead_func is not None:
                line_context[ln] = (ahead_func, ahead_class, ahead_fline, ahead_fend)
                break

    return line_context, all_test_funcs, first_def_line


def text_prescan(
    lines: list[tuple[int, str]],
) -> tuple[
    dict[int, tuple[str | None, str | None, int, int]],
    list[tuple[int, str, str | None]],
    int,
]:
    """Pre-scan source using text-based indent tracking.

    Fallback for non-Python files or when AST parsing fails.

    Args:
        lines: List of (line_number, content) tuples.

    Returns:
        Same tuple format as ast_prescan.
    """
    func_pattern = re.compile(r"^(\s*)def\s+(test_\w+)\s*\(")
    class_pattern = re.compile(r"^(\s*)class\s+(Test\w*)\s*[:(]")

    current_class: str | None = None
    current_class_indent: int = -1
    current_func: str | None = None
    current_func_indent: int = -1
    current_func_line: int = 0
    first_def_line = 0

    line_context: dict[int, tuple[str | None, str | None, int, int]] = {}
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

        # func_end_line=0 sentinel: text-based scanning can't reliably determine end lines
        line_context[ln] = (current_func, current_class, current_func_line, 0)

    return line_context, all_test_funcs, first_def_line


def _iter_code_brackets(code: str):
    """Yield bracket chars in ONE line of source, skipping string literals
    ('...'/"...", honoring \\ escapes) and a `//` line-comment -- but only when
    the `//` is NOT inside a string (so a URL like 'http://x' is not mistaken
    for a comment). Triple-quoted/raw strings and /* */ blocks are not special-
    cased; a residual miscount there warns honestly rather than wrongly."""
    i = 0
    n = len(code)
    while i < n:
        c = code[i]
        if c == "/" and i + 1 < n and code[i + 1] == "/":
            return  # real line comment: rest of line is not code
        if c == "'" or c == '"':
            quote = c
            i += 1
            while i < n:
                if code[i] == "\\":
                    i += 2
                    continue
                if code[i] == quote:
                    i += 1
                    break
                i += 1
            continue
        if c in "([{)]}":
            yield c
        i += 1


def _match_brace_end(
    lines: list[tuple[int, str]],
    start_idx: int,
    stop_line: int | None = None,
) -> tuple[int, bool]:
    """Return (end_line, accurate). `accurate` is False only when the brackets
    did not balance before the bound -- i.e. the span was clamped to `stop_line`
    (the next detected test()/group() start) or ran to EOF without depth<=0.
    A clean close is accurate even if a bracket appeared inside a quoted string
    on the way (a slightly-wrong END is harmless; attachment uses the START line)."""
    depth = 0
    seen = False
    last = lines[start_idx][0]
    for ln, text in lines[start_idx:]:
        if stop_line is not None and ln >= stop_line:
            return stop_line - 1, False  # clamped: never balanced before next test
        # (no more //-prestrip; _iter_code_brackets handles comments + strings)
        for ch in _iter_code_brackets(text):
            if ch in "([{":
                depth += 1
                seen = True
            elif ch in ")]}":
                depth -= 1
        last = ln
        if seen and depth <= 0:
            return ln, True  # clean close
    return last, False  # ran to EOF without closing


def dart_prescan(
    lines: list[tuple[int, str]],
) -> tuple[
    dict[int, tuple[str | None, str | None, int, int]],
    list[tuple[int, str | None, str | None]],
    int,
]:
    """Pre-scan Dart source: anchor each line to the test() that encloses it.

    Regex-detects test()/testWidgets() call sites and brace-matches each to its
    end line. func_name/class_name stay None (Dart test ids are line-based, not
    identifier-based); only func_line (the call-site line) and func_end_line are
    populated. A comment line above a test() that is not itself inside another
    test binds forward to it via the forward-look pass below.

    Args:
        lines: List of (line_number, content) tuples.

    Returns:
        Tuple of (line_context, all_test_funcs, first_def_line):
        - line_context: Maps line_number -> (None, None, func_line, func_end_line)
        - all_test_funcs: List of (test_line, None, None) for each test()/testWidgets()
        - first_def_line: Line of first detected test()/group() call (0 if none)
    """
    arr = lines
    # 0) collect ALL detected start lines (test + group) -- used to bound any
    #    runaway brace match: a span may never cross the next start line.
    start_lines = sorted(
        ln for ln, text in arr if _DART_TEST.match(text) or _DART_GROUP.match(text)
    )

    # 1) find each test() start and its brace-matched end (bounded)
    spans: list[tuple[int, int]] = []  # (start_line, end_line)
    first_def_line = start_lines[0] if start_lines else 0
    inaccurate = False
    for i, (ln, text) in enumerate(arr):
        if not _DART_TEST.match(text):
            continue
        # next detected start strictly after this one (cap for the span)
        nxt = next((s for s in start_lines if s > ln), None)
        end, accurate = _match_brace_end(arr, i, stop_line=nxt)
        inaccurate = inaccurate or (not accurate)
        spans.append((ln, end))

    if inaccurate:
        print(
            "Warning: dart_prescan could not balance a test() body before the "
            "next test or end-of-file; comment-inside-test span boundaries may "
            "be inaccurate.",
            file=sys.stderr,
        )

    # 2) line_context: each line inside a span -> that test (innermost wins)
    line_context: dict[int, tuple[str | None, str | None, int, int]] = {}
    for ln, _t in lines:
        owner_start = 0
        owner_end = 0
        best = -1
        for s, e in spans:
            if s <= ln <= e and s > best:  # innermost (largest start) wins
                best, owner_start, owner_end = s, s, e
        line_context[ln] = (None, None, owner_start, owner_end)

    # 3) forward-look: a comment with no owner binds to the next test() within 5 lines
    span_starts = {s for s, _e in spans}
    span_by_start = dict(spans)
    for idx, (ln, text) in enumerate(lines):
        if line_context[ln][2]:
            continue
        stripped = text.strip()
        if not any(stripped.startswith(p) for p in ("//", "/*")):
            continue
        for ahead in range(1, min(6, len(lines) - idx)):
            aln = lines[idx + ahead][0]
            if aln in span_starts:
                line_context[ln] = (None, None, aln, span_by_start[aln])
                break

    all_test_funcs = [(s, None, None) for s, _e in spans]
    return line_context, all_test_funcs, first_def_line


def external_prescan(
    file_entries: list[dict],
    lines: list[tuple[int, str]],
) -> tuple[
    dict[int, tuple[str | None, str | None, int, int]],
    list[tuple[int, str, str | None]],
    int,
]:
    """Build prescan data from externally-provided test structure.

    Args:
        file_entries: List of dicts with keys: function, class, line.
        lines: List of (line_number, content) tuples.

    Returns:
        Same tuple format as ast_prescan.
    """
    all_test_funcs: list[tuple[int, str, str | None]] = []
    # Build ranges: each function spans from its line to the next function's line - 1
    # (or end of file).  If an explicit end_line is provided, use it.
    sorted_entries = sorted(file_entries, key=lambda e: e["line"])
    # (start, end, fname, cname, explicit_end_line)
    func_ranges: list[tuple[int, int, str, str | None, int]] = []

    for i, entry in enumerate(sorted_entries):
        start = entry["line"]
        fname = entry["function"]
        cname = entry.get("class")
        explicit_end = entry.get("end_line", 0)
        if fname.startswith("test_"):
            all_test_funcs.append((start, fname, cname))
        # End is either next function's line - 1, or last source line
        if i + 1 < len(sorted_entries):
            heuristic_end = sorted_entries[i + 1]["line"] - 1
        else:
            heuristic_end = lines[-1][0] if lines else start
        # Use explicit end_line for func_end_line; heuristic for range matching
        end = heuristic_end
        func_end_line = explicit_end if explicit_end else heuristic_end
        func_ranges.append((start, end, fname, cname, func_end_line))

    first_def_line = sorted_entries[0]["line"] if sorted_entries else 0

    line_context: dict[int, tuple[str | None, str | None, int, int]] = {}
    for ln, _text in lines:
        func_name = None
        class_name = None
        func_line = 0
        func_end = 0
        for start, end, fname, cname, fend in func_ranges:
            if start <= ln <= end:
                func_name = fname
                class_name = cname
                func_line = start
                func_end = fend
                break
        line_context[ln] = (func_name, class_name, func_line, func_end)

    return line_context, all_test_funcs, first_def_line
