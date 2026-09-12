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

# A comment carrying a citation sits above the declaration it describes, and the
# length of that comment block says nothing about what it describes.  The scan
# therefore has no line limit: it walks down from a comment while it meets only
# further comments and blank lines, and binds at the first declaration it
# reaches.  Anything else ends the search, so a file header does not attach
# itself to the first declaration in the file.
#
# These prefixes are DELIBERATELY not the named set of comment patterns, and
# deliberately wider than it.  They answer a different question: "does this
# line keep the downward walk alive?", which is about the layout of a file,
# not about whether a *Traceability* keyword written here would count.  A
# block comment carries no citation (REQ-d00082-H), but a citation may sit
# below one, and narrowing this set to the file's own single pattern would
# stop the walk at the block and cost that citation its declaration.  Which
# marker may introduce a keyword is decided once, elsewhere, by
# ``graph/parsers/patterns.comment_pattern_for_path``; nothing recognised
# here is thereby admitted as a reference.
_COMMENT_PREFIXES: tuple[str, ...] = ("#", "//", "--", "/*", "<!--")


# Implements: REQ-d00254-D
def is_comment_line(text: str) -> bool:
    """Whether a source line's first content looks like a comment opener.

    Eligibility for the downward walk only -- see ``_COMMENT_PREFIXES``.
    """
    stripped = text.strip()
    return any(stripped.startswith(prefix) for prefix in _COMMENT_PREFIXES)


# A decorator, an annotation, an attribute -- whatever the language calls the
# line, it is part of the declaration written below it and not code that does
# work.  Matched by its opener alone: what a decorator NAMES is irrelevant here,
# only that the line cannot itself be the declaration the walk is looking for.
_DECORATOR = re.compile(r"^\s*@")


# Implements: REQ-d00254-D
def opens_a_declaration(text: str, class_patterns) -> bool:
    """Whether a line is a declaration's header rather than work of its own.

    REQ-d00254-D attributes a citation the lines of "the function it is written
    above".  Between a citation and that function the author may write a
    decorator, or a class the function is a method of -- neither of which is
    the function, and neither of which stops the citation being written above
    it.  Reading such a line as the end of the search answers a question the
    author did not ask: the citation then falls to D's second branch and takes
    the lines FOLLOWING it, unbounded by the function it was written for, up to
    the next citation or the end of the file.

    A class is skipped rather than bound to.  D speaks of functions and never
    of classes, so a class is not an extent here; it is passed through, and a
    citation above one binds to the first function inside it, or to nothing
    when the class opens with anything else.
    """
    return bool(_DECORATOR.match(text)) or any(p.match(text) for p in class_patterns)


# Implements: REQ-d00254-D
def bind_unowned_comments(lines, is_owned, target_at, assign, skippable=None) -> None:
    """Bind each unowned comment line to the next declaration below it.

    ``is_owned(line_number)`` says whether a line already has an owner,
    ``target_at(index, line_number, text)`` returns the binding target for a
    line or None if it is not a declaration, ``assign(line_number, target)``
    records the binding, and ``skippable(text)`` -- when given -- says a line
    stands between the citation and its declaration without ending the search.

    The walk stops at the first line that is none of these, because a citation
    is written above a declaration only when nothing that does work separates
    them.
    """
    for idx, (ln, text) in enumerate(lines):
        if is_owned(ln) or not is_comment_line(text):
            continue
        for ahead in range(idx + 1, len(lines)):
            ahead_ln, ahead_text = lines[ahead]
            target = target_at(ahead, ahead_ln, ahead_text)
            if target is not None:
                assign(ln, target)
                break
            if skippable is not None and skippable(ahead_text):
                continue
            if ahead_text.strip() and not is_comment_line(ahead_text):
                break


# Implements: REQ-d00254-D
def the_walk_decides(_line_number: int) -> bool:
    """No comment line's binding is settled by the range that encloses it.

    Passed as ``bind_unowned_comments``' ``is_owned`` where a CODE context is
    being built, so every comment line is offered to the downward walk.

    Under D a citation attributes "the function it is written above", and only
    the walk knows what it is written above.  A comment sitting INSIDE a
    function is enclosed by it, but where the walk reaches a declaration --
    nothing between them but blank lines, comments, decorators or a class
    header -- the citation is written above THAT declaration, which begins
    below the comment and so is the narrower of the two.  Preferring the
    narrower one is what stops a citation written above one nested function
    attributing every nested function of its enclosing one.  Where the walk
    reaches work instead, it binds nothing and the enclosing function stands:
    a citation in the middle of a body still speaks for the body, bounded by
    the function that holds it.

    The three TEST pre-scans deliberately keep the enclosing-range predicate.
    A citation above a test class or inside a test must not reach the first
    method below it: a test's extent is where a runner's verdict is attributed,
    and moving that attribution moves a pass or a failure onto a test that did
    not produce it.
    """
    return False


# Implements: REQ-d00254-D
def python_line_context(
    lines: list[tuple[int, str]],
) -> dict[int, tuple[str | None, str | None, int, int]] | None:
    """Per-line function/class context for a Python file, read from the AST.

    Indentation tracking answers two questions wrongly, and both cost a
    citation the code it speaks for. It cannot see the end of a function, so a
    citation inside one is bounded only by the next citation and claims the
    bodies of functions it says nothing about; and it keeps a function current
    across a comment written after that function ended, so a module-level
    citation is read as belonging to the function above it. The AST knows every
    declaration's real extent and is not fooled by a dedented line inside a
    multi-line string.

    Returns None when the source does not parse, so the caller keeps the
    indentation reading rather than losing context altogether.
    """
    try:
        tree = ast.parse("\n".join(text for _, text in lines))
    except (SyntaxError, ValueError):
        return None

    class_ranges: list[tuple[int, int, str]] = []
    func_ranges: list[tuple[int, int, str, str | None]] = []

    def _collect(node, class_name: str | None) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                class_ranges.append((child.lineno, child.end_lineno or child.lineno, child.name))
                _collect(child, child.name)
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func_ranges.append(
                    (child.lineno, child.end_lineno or child.lineno, child.name, class_name)
                )
                # A nested declaration is the narrower answer for its own lines.
                _collect(child, class_name)

    _collect(tree, None)

    context: dict[int, tuple[str | None, str | None, int, int]] = {}
    for ln, _text in lines:
        name: str | None = None
        class_name: str | None = None
        start = end = 0
        for c_start, c_end, c_name in class_ranges:
            if c_start <= ln <= c_end:
                class_name = c_name
        for f_start, f_end, f_name, f_class in func_ranges:
            if f_start <= ln <= f_end:
                name, class_name, start, end = f_name, f_class or class_name, f_start, f_end
        context[ln] = (name, class_name, start, end)
    return context


# Implements: REQ-d00254-D
def _bind_comments_to_declarations(
    lines: list[tuple[int, str]],
    context: dict[int, tuple[str | None, str | None, int, int]],
    func_patterns: list,
    class_patterns: list,
) -> dict[int, tuple[str | None, str | None, int, int]]:
    """Bind a comment above a declaration to it, carrying that declaration's extent.

    A citation is written above the thing it describes at least as often as
    inside it, and a comment sits outside every declaration's own line range.
    Binding is therefore what gives the canonical placement its function -- and
    with it the bound that stops the citation claiming the code of the next one.

    A comment ALREADY inside a function is offered to the walk too
    (``the_walk_decides``): a nested declaration written directly below it
    begins after it, so the citation is written above that one, and it is the
    narrower answer for the lines it attributes.
    """

    def _declaration_at(_idx, ahead_ln, ahead_text):
        for pattern in func_patterns:
            if pattern.match(ahead_text):
                name, class_name, start, end = context.get(ahead_ln, (None, None, 0, 0))
                if name is not None:
                    return (name, class_name, start, end)
        return None

    def _assign(ln, target):
        name, class_name, start, end = target
        _, own_class, _, _ = context[ln]
        context[ln] = (name, class_name or own_class, start, end)

    bind_unowned_comments(
        lines,
        the_walk_decides,
        _declaration_at,
        _assign,
        skippable=lambda text: opens_a_declaration(text, class_patterns),
    )
    return context


# Language-aware function/class patterns for context tracking
# Python: def name(
_PYTHON_FUNC = re.compile(r"^(\s*)(?:async\s+)?def\s+(\w+)\s*\(")
_PYTHON_CLASS = re.compile(r"^(\s*)class\s+(\w+)\s*[:(]")

# A brace-language STATEMENT has the shape of a declaration.  ``if (x) {``,
# ``for (;;) {`` and ``catch (e) {`` read as "name(args) {", and
# ``return build(x);`` reads as "type name(" -- so a citation written directly
# above one would bind to a block that is not a declaration at all and attribute
# the handful of lines that block holds instead of the function it was written
# in.  Every word that can open a statement is therefore refused, at the type
# position and at the name position alike, the same way ``_DART_NOT_KEYWORD``
# refuses them in Dart.  A declaration these patterns decline to see falls to
# REQ-d00254-D's second branch, which is where it fell before they existed.
_BRACE_STATEMENT_WORDS = (
    r"if|else|for|while|do|switch|case|default|try|catch|finally|return|throw|"
    r"new|delete|typeof|instanceof|await|yield|goto|sizeof|using|break|continue"
)
_NOT_STATEMENT_WORD = rf"(?!(?:{_BRACE_STATEMENT_WORDS})\b)"

# JS/TS: function name(, async function name(, name(, name = function(
_JS_FUNC = re.compile(r"^(\s*)(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(")
_JS_METHOD = re.compile(rf"^(\s*)(?:async\s+)?{_NOT_STATEMENT_WORD}(\w+)\s*\([^)]*\)\s*\{{")
_JS_CLASS = re.compile(r"^(\s*)class\s+(\w+)")

# Go: func name(, func (receiver) name(
_GO_FUNC = re.compile(r"^(\s*)func\s+(?:\([^)]+\)\s+)?(\w+)\s*\(")
_GO_STRUCT = re.compile(r"^(\s*)type\s+(\w+)\s+struct\s*\{")

# Rust: pub? fn name(, pub? async fn name(
_RUST_FUNC = re.compile(r"^(\s*)(?:pub\s+)?(?:async\s+)?fn\s+(\w+)\s*[(<]")
_RUST_IMPL = re.compile(r"^(\s*)impl\s+(?:<[^>]+>\s+)?(\w+)")

# C/Java/C#: return_type name(
_C_FUNC = re.compile(
    rf"^(\s*)(?:(?:static|public|private|protected|virtual|inline)\s+)*"
    rf"{_NOT_STATEMENT_WORD}\w[\w:*&<>, ]*\s+{_NOT_STATEMENT_WORD}(\w+)\s*\("
)
_C_CLASS = re.compile(r"^(\s*)(?:public\s+)?class\s+(\w+)")

# Dart: test('desc', ...), testWidgets('desc', ...), group('desc', ...)
_DART_TEST = re.compile(r"^(\s*)(?:test|testWidgets)\s*\(")
_DART_GROUP = re.compile(r"^(\s*)group\s*\(")

# Dart declarations.  A Dart declaration is written type-first and reads,
# character for character, like an ordinary statement -- ``return build(x);``
# and ``const SizedBox(height: 8),`` have the shape of "word word(".  A false
# positive here is not merely a misnamed function: in brace scoping a matched
# one-liner sets the function's brace floor at the current depth, so the very
# next line closes the REAL enclosing method early and every citation below it
# in that method loses its bound.  These patterns therefore refuse every word
# that can open a statement, at the type position AND at the name position.
_DART_KEYWORDS = (
    r"assert|await|break|case|catch|const|continue|do|dynamic|else|export|extends|"
    r"external|factory|final|finally|for|if|implements|import|in|is|late|library|new|"
    r"on|part|required|rethrow|return|static|super|switch|sync|this|throw|try|typedef|"
    r"var|while|with|yield"
)
_DART_NOT_KEYWORD = rf"(?!(?:{_DART_KEYWORDS})\b)"
# A return type: a (possibly qualified, possibly generic, possibly nullable)
# name.  Inside the generic a brace is admitted only within a parenthesised
# group, so a record type argument -- ``Future<({String? code, DateTime? at})>``
# -- is read while a match still cannot span a block: the outer ``[^;{}]``
# refuses a bare brace exactly as it did before.
_DART_TYPE = r"[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)?(?:<(?:[^;{}]|\([^;()]*\))*>)?\??"
# A record type written as the return type itself: ``({String a, int b}) f(``.
# Parenthesis-free within, so it cannot swallow a call's argument list.
_DART_RECORD_TYPE = r"\([^()]*\)\??"

# String get title => _t;  /  Widget get child { ... }
_DART_GETTER = re.compile(
    rf"^(\s*)(?:(?:static|external|final|const|late)\s+)*(?:{_DART_TYPE}\s+)?"
    rf"get\s+(\w+)\s*(?:=>|\{{)"
)

# ``factory`` opens a constructor declaration and nothing else -- no call, no
# statement, no field may begin with it -- so unlike the unadorned constructor
# below it needs no further evidence and no same-line body.  That matters for
# the formatter-split form, whose parameters and ``) {`` sit on the lines
# beneath, which the evidence lookahead cannot see.
_DART_FACTORY = re.compile(
    r"^(\s*)(?:(?:const|external)\s+)*factory\s+"
    r"([A-Z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)?)\s*\("
)

# A constructor is the one declaration written without a return type, which is
# also the shape of every call statement and of every widget in a Flutter tree.
# It is admitted only on evidence a call cannot carry: a ``this.``/``super.``
# parameter (legal only in a constructor's parameter list), or a parameter list
# holding no parenthesis of its own and closed by a body, an initialiser list or
# an arrow, or a named-parameter brace opening the list.  A parameter list is
# required to be paren-free because ``) {`` and ``) =>`` are NOT by themselves
# evidence against a call: a closure argument carries both, and
# ``Timer(d, () { ... });`` or ``ElevatedButton(onPressed: () {}, ...)`` would
# otherwise read as a declaration.  That costs the rare
# ``Foo(void Function(int) cb) {`` and refuses every closure-argument call,
# which is the pervasive shape.
# Left deliberately unmatched, because nothing tells them from a call:
# ``Foo();``, ``Foo._();``, and a formatter-split ``Foo(`` with its positional
# parameters on the lines below.  Those fall to REQ-d00254-D's second branch,
# which is the same answer Dart got for every declaration before this branch
# existed -- never a worse one.
_DART_CONSTRUCTOR = re.compile(
    r"^(\s*)(?:(?:const|factory|external)\s+)*"
    r"([A-Z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)?)\s*"
    r"\((?=[^)]*(?:this|super)\.|[^();]*\)\s*(?:\{|:|=>)|\s*\{\s*$)"
)

# void build() {  /  Future<void> load() async {  /  Widget build(BuildContext c) {}
_DART_FUNC = re.compile(
    rf"^(\s*)(?:(?:static|external|abstract)\s+)*"
    rf"(?:{_DART_RECORD_TYPE}\s*|{_DART_NOT_KEYWORD}(?:void|{_DART_TYPE})\s+)"
    rf"{_DART_NOT_KEYWORD}(?!Function\b)(\w+)\s*\("
)

# A signature the formatter split across lines leaves the return type on the
# line above, so the declaration line carries the name alone:
# ``getLastEnrollmentDisplay() async {``.  ``name(args) {`` and ``name(args) =>``
# are not statements in Dart -- no call, cascade or literal entry can be spelled
# that way -- so the shape is evidence enough, on the same terms the constructor
# demands: a parameter list holding no parenthesis of its own (which refuses
# every closure-argument call, ``setState(() {``) and closed on this line by a
# body or an arrow, with every statement-opening word refused.
_DART_CONTINUED_SIGNATURE = re.compile(
    rf"^(\s*){_DART_NOT_KEYWORD}([a-z_$][\w$]*)\s*"
    rf"\([^()]*\)\s*(?:(?:async|sync)\*?\s*)?(?:\{{|=>)"
)

# class X extends Y {  /  abstract class X {  /  mixin M on N {  /  enum E { ... }
_DART_CLASS = re.compile(
    r"^(\s*)(?:(?:abstract|base|final|interface|sealed|mixin)\s+)*"
    r"(?:class|mixin|enum|extension)\s+(\w+)"
)


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
    ".dart": "dart",  # test files additionally use dart_prescan()
}


def detect_language(file_path: str) -> str:
    """Detect programming language from file extension.

    Args:
        file_path: Path to the source file.

    Returns:
        Language key: 'python', 'js', 'go', 'rust', 'c', 'dart', or 'unknown'.
    """
    ext = Path(file_path).suffix.lower()
    return _LANG_MAP.get(ext, "unknown")


def _patterns_for(language: str) -> tuple[list, list, str]:
    """The function patterns, class patterns and scope mode for a language.

    ONE selection, read by every pre-scan that needs to recognise a
    declaration by sight: the context builder and ``declaration_starts``.
    """
    if language == "python":
        return [_PYTHON_FUNC], [_PYTHON_CLASS], "indent"
    if language == "js":
        return [_JS_FUNC, _JS_METHOD], [_JS_CLASS], "brace"
    if language == "go":
        return [_GO_FUNC], [_GO_STRUCT], "brace"
    if language == "rust":
        return [_RUST_FUNC], [_RUST_IMPL], "brace"
    if language == "c":
        return [_C_FUNC], [_C_CLASS], "brace"
    if language == "dart":
        # Getter before function: ``String get title`` would otherwise read as
        # a function named ``get``.  Factory and constructor before function: a
        # constructor has no return type, so the typed form cannot see it.  The
        # split signature last: it is the weakest evidence of the five and must
        # not answer for a line a fuller shape accounts for.
        return (
            [
                _DART_GETTER,
                _DART_FACTORY,
                _DART_CONSTRUCTOR,
                _DART_FUNC,
                _DART_CONTINUED_SIGNATURE,
            ],
            [_DART_CLASS],
            "brace",
        )
    # Unknown language: try Python-style patterns as fallback
    return [_PYTHON_FUNC], [_PYTHON_CLASS], "indent"


# Implements: REQ-d00254-D
def declaration_starts(lines: list[tuple[int, str]], language: str) -> list[int]:
    """The line each function declaration in a file BEGINS at, ascending.

    REQ-d00254-D bounds a citation that no function encloses at "the start of
    the next function declaration (its first decorator line, where it has
    decorators)".  A decorator is part of the declaration written below it, so
    the declaration begins at the first decorator and not at the ``def``:
    counting from the ``def`` would leave the decorator lines of a function
    attributed to a citation written about something else.

    Read from the AST where the source parses, because a declaration written
    under an ``if`` or a ``try`` is a declaration like any other and a
    structural walk that only descends into classes and functions would miss
    it -- and a missed declaration is exactly the hole this bound closes.
    Where the source does not parse, or the language has no AST here, the same
    patterns ``build_line_context`` recognises are matched line by line and
    the walk steps back over any decorators above the match.

    Returns an empty list when nothing can be read, so the caller imposes no
    bound rather than a wrong one.
    """
    if language == "python":
        try:
            tree = ast.parse("\n".join(text for _, text in lines))
        except (SyntaxError, ValueError):
            tree = None
        if tree is not None:
            starts: set[int] = set()
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    starts.add(min([d.lineno for d in node.decorator_list] + [node.lineno]))
            return sorted(starts)

    func_patterns, _class_patterns, _scope_mode = _patterns_for(language)
    found: set[int] = set()
    for idx, (ln, text) in enumerate(lines):
        if not any(pattern.match(text) for pattern in func_patterns):
            continue
        start = ln
        back = idx - 1
        while back >= 0:
            prev_ln, prev_text = lines[back]
            if _DECORATOR.match(prev_text):
                start = prev_ln
                back -= 1
                continue
            break
        found.add(start)
    return sorted(found)


# Implements: REQ-d00254-D
def build_line_context(
    lines: list[tuple[int, str]],
    language: str,
) -> dict[int, tuple[str | None, str | None, int, int]]:
    """Build function/class context map for each line.

    Pre-scans lines to determine which function/class each line
    belongs to. Supports Python (indentation-based) and C-family
    languages (brace-based scoping).

    After the initial scan, performs a forward-looking fixup: a comment line
    binds to the next function declaration below it, passing over blank lines,
    further comments, and the declaration headers (decorators, class
    statements) that may stand between the two. This handles the common pattern
    of ``# Implements: <REQ-ID>`` placed above a function. A comment the initial
    scan already placed inside a function is offered to the fixup as well, so a
    citation written directly above a NESTED declaration binds to that one
    rather than to the function that merely contains both; see
    ``the_walk_decides``.

    Args:
        lines: List of (line_number, content) tuples.
        language: Detected language key.

    Returns:
        Dict mapping line_number to (function_name, class_name, function_line, function_end_line).
        function_end_line is 0 (sentinel) for text-based scanning since end lines are unreliable.
    """
    func_patterns, class_patterns, scope_mode = _patterns_for(language)

    # Implements: REQ-d00254-D
    # A citation's enclosing function bounds the lines it attributes, so the
    # precise reading is preferred wherever it is available.
    if language == "python":
        ast_context = python_line_context(lines)
        if ast_context is not None:
            return _bind_comments_to_declarations(lines, ast_context, func_patterns, class_patterns)

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
            # Implements: REQ-d00254-D
            # The floor a declaration on THIS line encloses its body above is
            # the depth the line was reached at, before its own braces are
            # applied.  Deriving it from the depth afterwards by subtracting
            # only the opens mis-states it whenever a ``}`` shares the line --
            # ``Widget build(c) {}``, ``const Foo({super.key});`` -- and sets a
            # floor the depth can never fall back to, so the declaration stays
            # current over every line below it until something else replaces it.
            depth_before = brace_depth
            brace_depth += open_count - close_count

            # Exit function scope when braces close
            if current_func and brace_depth <= func_brace_start:
                current_func = None
                current_func_indent = -1
                current_func_line = 0

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
                    class_brace_start = depth_before
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
                    func_brace_start = depth_before
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
                    current_func_line = 0

        # Suppress match variable leaking (used in loop above)
        class_match = None  # type: ignore[assignment]
        func_match = None  # type: ignore[assignment]

        # func_end_line=0 sentinel: text-based scanning can't reliably determine end lines
        line_context[ln] = (current_func, current_class, current_func_line, 0)

    # Bind "# Implements: <REQ-ID>" and its like to the declaration below it.
    def _declaration_at(_idx, ahead_ln, ahead_text):
        for pattern in func_patterns:
            m = pattern.match(ahead_text)
            if m:
                _, ahead_class, _, _ = line_context.get(ahead_ln, (None, None, 0, 0))
                return (m.group(2), ahead_class, ahead_ln)
        return None

    def _assign(ln, target):
        ahead_func, ahead_class, ahead_ln = target
        _, class_name, _, _ = line_context[ln]
        line_context[ln] = (ahead_func, ahead_class or class_name, ahead_ln, 0)

    bind_unowned_comments(
        lines,
        the_walk_decides,
        _declaration_at,
        _assign,
        skippable=lambda text: opens_a_declaration(text, class_patterns),
    )

    # Implements: REQ-d00254-D
    # The last line a function was current for is the end of its extent. It is
    # read after binding so a comment bound to the declaration below it inherits
    # that declaration's extent rather than a zero.
    end_by_start: dict[int, int] = {}
    for ln, _text in lines:
        start = line_context[ln][2]
        if start and line_context[ln][0] is not None:
            end_by_start[start] = max(end_by_start.get(start, start), ln)
    for ln in line_context:
        name, class_name, start, _ = line_context[ln]
        line_context[ln] = (name, class_name, start, end_by_start.get(start, 0) if start else 0)

    return line_context


# Implements: REQ-d00269-E
def ast_string_literal_lines(source: str) -> set[int]:
    """Every line genuinely interior to a Python string literal.

    A keyword written inside a literal names a keyword rather than invoking
    one, and a line-based scanner cannot tell such a line from a comment.
    Only the parser knows, so the parser is asked.

    A literal spans lines ``lineno..end_lineno``. The opening line
    (``lineno``) is excluded: it may hold real code before the quote
    starts (``def render(label="x"):``), so a line merely *containing* a
    string constant is not, by itself, evidence the line is quoted text.
    Only the lines strictly after the opening line -- ``lineno + 1 ..
    end_lineno`` -- are interior to the literal's content and therefore
    excluded from binding.

    Returns an empty set when the source does not parse: a file the tool
    cannot read is not a file it may make claims about.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            end = node.end_lineno or node.lineno
            lines.update(range(node.lineno + 1, end + 1))
    return lines


# Implements: REQ-d00254-K
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

    # Implements: REQ-d00254-O
    # Where a test starts, in the same terms the runner uses. pytest reports a
    # test at the first line of its decorated definition, so a decorated test
    # is reported at its first decorator, not at `def`. Reading `def` here
    # would disagree with every result pytest writes for a decorated test --
    # which is every parametrized one -- and the result would bind to the file
    # instead of to the test that produced it.
    def _start_line(item) -> int:
        return item.decorator_list[0].lineno if item.decorator_list else item.lineno

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
                            start = _start_line(item)
                            func_ranges.append((start, end, item.name, node.name))
                            all_test_funcs.append((start, item.name, node.name))
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
                func_ranges.append((_start_line(node), end, node.name, None))
                all_test_funcs.append((_start_line(node), node.name, None))

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

    # Comment lines above a function def fall outside the AST range; bind them
    # to the function they describe.
    def _declaration_at(_idx, ahead_ln, _ahead_text):
        entry = line_context.get(ahead_ln, (None, None, 0, 0))
        return entry if entry[0] is not None else None

    bind_unowned_comments(
        lines,
        lambda ln: line_context[ln][0] is not None,
        _declaration_at,
        lambda ln, target: line_context.__setitem__(ln, target),
    )

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

    # Implements: REQ-d00254-D
    # A citation written above a test binds to it here too; without this a file
    # reaching this branch has no forward binding at all.
    def _declaration_at(_idx, ahead_ln, ahead_text):
        m = func_pattern.match(ahead_text)
        if not m:
            return None
        _, ahead_class, _, _ = line_context.get(ahead_ln, (None, None, 0, 0))
        return (m.group(2), ahead_class, ahead_ln)

    bind_unowned_comments(
        lines,
        lambda ln: line_context[ln][0] is not None,
        _declaration_at,
        lambda ln, target: line_context.__setitem__(ln, (target[0], target[1], target[2], 0)),
    )

    return line_context, all_test_funcs, first_def_line


class _DartLineScanner:
    """Cross-line bracket scanner for Dart.

    Tracks multiline strings (''' / \"\"\"), raw strings (r-prefix: backslash
    is literal, applies to both quote styles and to raw triple-quoted
    strings), single-line strings (unterminated ones run to EOL, which is
    intentional -- Dart single-line strings cannot legally span lines), //
    line comments, and /* */ block comments that may span lines. Yields only
    bracket characters that are real code."""

    def __init__(self) -> None:
        self.multiline_quote: str | None = None  # "'''" or '"""' while inside
        self.in_block_comment = False

    def brackets(self, code: str):
        i = 0
        n = len(code)
        while i < n:
            if self.multiline_quote:
                end = code.find(self.multiline_quote, i)
                if end < 0:
                    return  # string continues past EOL
                i = end + 3
                self.multiline_quote = None
                continue
            if self.in_block_comment:
                end = code.find("*/", i)
                if end < 0:
                    return
                i = end + 2
                self.in_block_comment = False
                continue
            c = code[i]
            if c == "/" and i + 1 < n and code[i + 1] == "/":
                return  # line comment: rest of line is not code
            if c == "/" and i + 1 < n and code[i + 1] == "*":
                self.in_block_comment = True
                i += 2
                continue
            # r-prefix applies to both quote styles, including raw triple-
            # quoted strings -- resolve it before the triple-quote check.
            raw = c == "r" and i + 1 < n and code[i + 1] in "'\""
            if raw:
                i += 1
                c = code[i]
            if c == "'" or c == '"':
                if code[i : i + 3] in ("'''", '"""'):
                    self.multiline_quote = code[i : i + 3]
                    i += 3
                    continue
                quote = c
                i += 1
                while i < n:
                    if not raw and code[i] == "\\":
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


# Implements: REQ-d00254-K
def _match_brace_end(
    lines: list[tuple[int, str]],
    start_idx: int,
    stop_line: int | None = None,
) -> tuple[int, bool]:
    """Return (end_line, accurate). `accurate` is False only when the brackets
    did not balance before the bound -- i.e. the span was clamped to `stop_line`
    (the next detected test()/group() start) or ran to EOF without depth<=0.
    A clean close is accurate even if a bracket appeared inside a quoted string
    on the way (a slightly-wrong END is harmless; attachment uses the START line).

    A single `_DartLineScanner` instance is threaded across all lines of the
    span so multiline strings/comments that open on one line and close on a
    later one are tracked correctly."""
    depth = 0
    seen = False
    last = lines[start_idx][0]
    scanner = _DartLineScanner()
    for ln, text in lines[start_idx:]:
        if stop_line is not None and ln >= stop_line:
            # clamped: never balanced before next test. Guard against
            # inversion -- the clamp must never produce an end before the
            # span's own start line.
            return max(lines[start_idx][0], stop_line - 1), False
        for ch in scanner.brackets(text):
            if ch in "([{":
                depth += 1
                seen = True
            elif ch in ")]}":
                depth -= 1
        last = ln
        if seen and depth <= 0:
            return ln, True  # clean close
    return last, False  # ran to EOF without closing


# Implements: REQ-d00254-K
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

    # 3) an unowned comment binds to the declaration below it.  Group starts are
    #    binding targets as well as test starts: a citation describing a whole
    #    group otherwise attaches to nothing however close it is written.
    bindable: dict[int, tuple[int, int]] = {s: (s, e) for s, e in spans}
    for i, (ln, text) in enumerate(arr):
        if _DART_GROUP.match(text) and ln not in bindable:
            nxt = next((s for s in start_lines if s > ln), None)
            end, _accurate = _match_brace_end(arr, i, stop_line=nxt)
            bindable[ln] = (ln, end)

    bind_unowned_comments(
        lines,
        lambda ln: bool(line_context[ln][2]),
        lambda _idx, aln, _atext: bindable.get(aln),
        lambda ln, target: line_context.__setitem__(ln, (None, None, target[0], target[1])),
    )

    all_test_funcs = [(s, None, None) for s, _e in spans]
    return line_context, all_test_funcs, first_def_line


# Implements: REQ-d00254-K
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
