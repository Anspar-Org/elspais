"""Term reference scanner — comment extraction and term occurrence detection.

Implements: REQ-d00236
Implements: REQ-d00237
Implements: REQ-d00238
"""

from __future__ import annotations

import io
import os
import re
import tokenize
from fnmatch import fnmatch
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from elspais.graph.terms import TermDictionary
    from elspais.graph.TraceGraph import TraceGraph

from elspais.graph.GraphNode import FileType, NodeKind
from elspais.graph.terms import TermRef

# -- Language extension maps ---------------------------------------------------

# Implements: REQ-d00236-D
_HASH_LANGS: frozenset[str] = frozenset(
    {
        ".rb",
        ".sh",
        ".bash",
        ".yaml",
        ".yml",
    }
)

# Implements: REQ-d00236-C
_SLASH_LANGS: frozenset[str] = frozenset(
    {
        ".js",
        ".ts",
        ".jsx",
        ".tsx",
        ".java",
        ".c",
        ".h",
        ".cpp",
        ".go",
        ".rs",
        ".dart",
    }
)

# Implements: REQ-d00236-E
_DASH_LANGS: frozenset[str] = frozenset({".sql", ".lua"})

# Implements: REQ-d00236-F
_HTML_LANGS: frozenset[str] = frozenset({".html", ".xml", ".svg"})

# Implements: REQ-d00236-C
_BLOCK_LANGS: frozenset[str] = frozenset(
    {
        ".js",
        ".ts",
        ".jsx",
        ".tsx",
        ".java",
        ".c",
        ".h",
        ".cpp",
        ".go",
        ".rs",
        ".dart",
        ".css",
    }
)

_LINE_COMMENT_RE = re.compile(r"//\s?(.*)")
_HASH_COMMENT_RE = re.compile(r"#\s?(.*)")
_DASH_COMMENT_RE = re.compile(r"--\s?(.*)")
_BLOCK_COMMENT_RE = re.compile(r"/\*(.+?)\*/", re.DOTALL)
_HTML_COMMENT_RE = re.compile(r"<!--(.+?)-->", re.DOTALL)


# -- Public API ----------------------------------------------------------------


# Implements: REQ-d00236-A
def extract_comments(source: str, ext: str) -> list[tuple[str, int]]:
    """Extract comment text from *source* based on file extension *ext*.

    Returns a list of ``(comment_text, line_number)`` pairs.  Line numbers
    are 1-based.  For unknown extensions, returns ``[]``.
    """
    if not source or not ext:
        return []

    ext_lower = ext.lower()

    if ext_lower == ".py":
        return _extract_python_comments(source)

    results: list[tuple[str, int]] = []

    if ext_lower in _SLASH_LANGS:
        results.extend(_extract_line_comments(source, _LINE_COMMENT_RE))
        results.extend(_extract_block_comments(source, _BLOCK_COMMENT_RE))
    elif ext_lower in _HASH_LANGS:
        results.extend(_extract_line_comments(source, _HASH_COMMENT_RE))
    elif ext_lower in _DASH_LANGS:
        results.extend(_extract_line_comments(source, _DASH_COMMENT_RE))
    elif ext_lower in _HTML_LANGS:
        results.extend(_extract_block_comments(source, _HTML_COMMENT_RE))
    # Implements: REQ-d00236-G — unknown extensions fall through with []

    results.sort(key=lambda x: x[1])
    return results


# -- Python-specific extraction ------------------------------------------------


# Implements: REQ-d00236-B
def _extract_python_comments(source: str) -> list[tuple[str, int]]:
    """Use *tokenize* to extract ``#`` comments only (not docstrings or strings)."""
    results: list[tuple[str, int]] = []

    try:
        tokens = tokenize.generate_tokens(io.StringIO(source).readline)
        for tok_type, tok_string, start, _end, _line in tokens:
            if tok_type == tokenize.COMMENT:
                # Strip the leading '#' and optional space
                text = tok_string.lstrip("#").strip()
                if text:
                    results.append((text, start[0]))
    except tokenize.TokenError:
        pass

    results.sort(key=lambda x: x[1])
    return results


# -- Generic line-comment extraction -------------------------------------------


def _extract_line_comments(
    source: str,
    pattern: re.Pattern[str],
) -> list[tuple[str, int]]:
    """Extract single-line comments matching *pattern*."""
    results: list[tuple[str, int]] = []
    for lineno, line in enumerate(source.splitlines(), 1):
        m = pattern.search(line)
        if m:
            text = m.group(1).strip()
            if text:
                results.append((text, lineno))
    return results


# -- Generic block-comment extraction ------------------------------------------


def _extract_block_comments(
    source: str,
    pattern: re.Pattern[str],
) -> list[tuple[str, int]]:
    """Extract block comments matching *pattern* (e.g. ``/* */``, ``<!-- -->``)."""
    results: list[tuple[str, int]] = []
    for m in pattern.finditer(source):
        text = m.group(1).strip()
        if text:
            # Line number is the 1-based line of the match start
            lineno = source[: m.start()].count("\n") + 1
            results.append((text, lineno))
    return results


# -- Term reference scanning ---------------------------------------------------

# All four Markdown emphasis delimiters, longest first for greedy matching.
_ALL_EMPHASIS_DELIMITERS: list[str] = ["**", "__", "*", "_"]

_DEFAULT_MARKUP_STYLES: list[str] = ["*", "**"]


def _build_emphasis_pattern(delimiter: str, term: str) -> re.Pattern[str]:
    """Build a regex that matches *term* wrapped in *delimiter*.

    For ``*`` we need negative lookahead/behind for extra ``*`` to avoid
    matching inside ``**term**``.
    """
    esc = re.escape(delimiter)
    esc_term = re.escape(term)
    if delimiter == "*":
        # *term* but NOT **term* or *term**
        return re.compile(
            r"(?<!\*)" + esc + r"(?!\*)" + esc_term + r"(?<!\*)" + esc + r"(?!\*)",
            re.IGNORECASE,
        )
    if delimiter == "_":
        # _term_ but NOT __term_ or _term__
        return re.compile(
            r"(?<!_)" + esc + r"(?!_)" + esc_term + r"(?<!_)" + esc + r"(?!_)",
            re.IGNORECASE,
        )
    # ** or __ — straightforward
    return re.compile(esc + esc_term + esc, re.IGNORECASE)


# Implements: REQ-d00237-A
def scan_text_for_terms(
    text: str,
    td: TermDictionary,
    node_id: str,
    namespace: str,
    line_offset: int = 0,
    markup_styles: list[str] | None = None,
) -> list[TermRef]:
    """Scan *text* for occurrences of defined terms in *td*.

    Returns a list of :class:`TermRef` instances classifying each occurrence
    as marked, wrong-marking, or unmarked.
    """
    if not text:
        return []

    if markup_styles is None:
        markup_styles = _DEFAULT_MARKUP_STYLES

    styles_set = set(markup_styles)
    results: list[TermRef] = []
    # Track character spans already claimed by emphasis matches
    claimed_spans: list[tuple[int, int]] = []

    for entry in td.iter_all():
        term = entry.term

        # --- Phase 1: scan all 4 emphasis delimiters --------------------------
        # Implements: REQ-d00237-B, REQ-d00237-C
        for delim in _ALL_EMPHASIS_DELIMITERS:
            pat = _build_emphasis_pattern(delim, term)
            for m in pat.finditer(text):
                span_start, span_end = m.start(), m.end()
                # Skip if this span overlaps a previously claimed span
                if any(not (span_end <= cs or span_start >= ce) for cs, ce in claimed_spans):
                    continue

                lineno = text[:span_start].count("\n") + 1 + line_offset
                claimed_spans.append((span_start, span_end))

                if delim in styles_set:
                    # Implements: REQ-d00237-B
                    ref = TermRef(
                        node_id=node_id,
                        namespace=namespace,
                        marked=True,
                        wrong_marking="",
                        line=lineno,
                    )
                else:
                    # Implements: REQ-d00237-C
                    ref = TermRef(
                        node_id=node_id,
                        namespace=namespace,
                        marked=False,
                        wrong_marking=delim,
                        line=lineno,
                    )
                results.append(ref)
                entry.references.append(ref)

        # --- Phase 2: unmarked scan (indexed terms only) ----------------------
        # Implements: REQ-d00237-D, REQ-d00237-E
        if not entry.indexed:
            continue

        word_pat = re.compile(r"\b" + re.escape(term) + r"\b", re.IGNORECASE)
        for m in word_pat.finditer(text):
            span_start, span_end = m.start(), m.end()
            # Skip if overlapping any emphasis match
            if any(not (span_end <= cs or span_start >= ce) for cs, ce in claimed_spans):
                continue

            lineno = text[:span_start].count("\n") + 1 + line_offset
            ref = TermRef(
                node_id=node_id,
                namespace=namespace,
                marked=False,
                wrong_marking="",
                line=lineno,
            )
            results.append(ref)
            entry.references.append(ref)

    return results


# -- Graph-wide term scan ------------------------------------------------------


def _get_node_text(node) -> str | None:  # noqa: ANN001
    """Extract scannable text from *node* based on its kind.

    Returns ``None`` when the node should be skipped entirely
    (e.g. definition_block REMAINDER nodes).
    """
    # Implements: REQ-d00238-B
    kind = node.kind
    if kind == NodeKind.REQUIREMENT:
        return node.get_label() or ""
    if kind == NodeKind.ASSERTION:
        return node.get_label() or ""
    if kind == NodeKind.REMAINDER:
        if node.get_field("content_type") == "definition_block":
            return None
        return node.get_field("text") or ""
    if kind == NodeKind.USER_JOURNEY:
        return node.get_field("body") or ""
    return None


def _extract_file_comments(file_node) -> list[tuple[str, int]] | None:  # noqa: ANN001
    """Extract comments from a FILE node's source on disk.

    Reads the full file so that ``tokenize`` receives valid Python
    (or other language) source.  Returns a list of
    ``(comment_text, file_line_number)`` pairs, or ``None``.
    """
    # Implements: REQ-d00238-C
    abs_path = file_node.get_field("absolute_path")
    rel_path = file_node.get_field("relative_path") or ""
    if not abs_path:
        return None
    ext = os.path.splitext(rel_path)[1]
    try:
        with open(abs_path, encoding="utf-8", errors="replace") as f:
            source = f.read()
    except OSError:
        return None
    comments = extract_comments(source, ext)
    return comments or None


def _should_exclude(rel_path: str, patterns: list[str]) -> bool:
    """Check if *rel_path* matches any exclusion glob pattern."""
    # Implements: REQ-d00238-D
    for pat in patterns:
        if fnmatch(rel_path, pat):
            return True
    return False


# Implements: REQ-d00238-A
def scan_graph(
    terms: TermDictionary,
    graph: TraceGraph,
    namespace: str,
    markup_styles: list[str] | None = None,
    exclude_files: list[str] | None = None,
) -> None:
    """Scan graph nodes for term occurrences and populate references.

    Mutates ``TermEntry.references`` in *terms* with discovered
    :class:`TermRef` instances.
    """
    if len(terms) == 0:
        return

    excl = exclude_files or []

    # Code/test file types: scan comments only (not code or string literals)
    _CODE_FILE_TYPES = frozenset({FileType.CODE, FileType.TEST})

    # Spec-like nodes: scan full text with file-relative line offset.
    # Skip REMAINDER nodes from code/test files (handled below per-FILE).
    spec_kinds = [
        NodeKind.REQUIREMENT,
        NodeKind.ASSERTION,
        NodeKind.REMAINDER,
        NodeKind.USER_JOURNEY,
    ]
    for kind in spec_kinds:
        for node in graph.iter_by_kind(kind):
            if _is_excluded(node, excl):
                continue
            # Skip REMAINDER nodes from code/test files
            if kind == NodeKind.REMAINDER:
                file_n = node.file_node()
                if file_n and file_n.get_field("file_type") in _CODE_FILE_TYPES:
                    continue
            text = _get_node_text(node)
            if text:
                # For REMAINDER sections, content_line points to where the
                # text body starts (after heading + blank lines).  For other
                # node kinds, parse_line is correct.
                if kind == NodeKind.REMAINDER:
                    node_start = node.get_field("content_line") or node.get_field("parse_line") or 0
                else:
                    node_start = node.get_field("parse_line") or 0
                offset = max(node_start - 1, 0)
                scan_text_for_terms(
                    text,
                    terms,
                    node.id,
                    namespace,
                    line_offset=offset,
                    markup_styles=markup_styles,
                )

    # Code/test FILE nodes: read the whole file once and scan its comments.
    # This gives tokenize/ast valid source, producing accurate line numbers.
    for file_node in graph.iter_roots(NodeKind.FILE):
        if file_node.get_field("file_type") not in _CODE_FILE_TYPES:
            continue
        if _is_excluded(file_node, excl):
            continue
        comments = _extract_file_comments(file_node)
        if not comments:
            continue
        file_id = file_node.id
        for comment_text, file_lineno in comments:
            scan_text_for_terms(
                comment_text,
                terms,
                file_id,
                namespace,
                line_offset=file_lineno - 1,
                markup_styles=markup_styles,
            )


def _is_excluded(node, excl: list[str]) -> bool:  # noqa: ANN001
    """Check if a node's file matches any exclusion pattern."""
    if not excl:
        return False
    file_n = node.file_node()
    if file_n is None:
        return False
    rel_path = file_n.get_field("relative_path") or ""
    return _should_exclude(rel_path, excl)
