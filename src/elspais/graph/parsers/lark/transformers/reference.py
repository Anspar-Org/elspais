"""ReferenceTransformer - Converts Lark reference parse tree to ParsedContent list.

Handles both code_ref and test_ref content types.  Pre-scan data (function/class
context) is injected from external sources -- AST-based for Python, text-based
for others, or external prescan command.

The grammar pre-classifies lines as single_ref, block_header, block_ref,
test_name_ref, or other_line.  This transformer:
1. Extracts requirement IDs from classified lines
2. Annotates with function/class context from pre-scan
3. Produces ParsedContent matching the old CodeParser/TestParser contracts

Keyword semantics per file type:

- **test files**: Only ``Verifies`` is valid.  ``Implements`` and ``Refines``
  are read and refused: no edge is created, and the TEST node stays
  unlinked, but the declaration is reported as a ``FaultClass.FORBIDDEN``
  broken reference naming the keyword and the file kind (REQ-d00272-J).
- **code files**: ``Implements`` creates IMPLEMENTS edges.  ``Verifies``
  creates VERIFIES edges (for code that produces pass/fail results).
  ``Refines`` and ``Integrates`` are invalid here (``Refines`` is
  requirement-to-requirement only; ``Integrates`` is spec-file only) and are
  read and refused the same way as an invalid keyword in a test file.

A keyword a file's kind does not admit is still recognised because it is
unmistakably a declaration: passing it over as prose would leave the author
of an annotation that did nothing without a report saying so.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from lark import Tree

from elspais.graph.parsers import ParsedContent
from elspais.graph.parsers.patterns import (
    JOURNEY_REF_PATTERN as _JOURNEY_REF_RE,
)
from elspais.graph.parsers.patterns import (
    KEYWORD_PATTERN as _KEYWORD_RE,
)

if TYPE_CHECKING:
    from elspais.graph.reference_faults import RefItem
    from elspais.utilities.patterns import FederatedIdReader, IdResolver

_log = logging.getLogger(__name__)

# Hardcoded comment styles for empty-comment detection
_COMMENT_STYLES = ["#", "//", "--"]


def reference_target(text: str) -> str:
    """The text a reference line names as its target, verbatim.

    Trailing block-comment terminators are not part of what the author
    wrote as a target, so they are dropped; everything else is kept as
    written, since the point of reporting it is to show the author the
    string that could not be resolved.
    """
    match = _KEYWORD_RE.search(text)
    if not match:
        return ""
    tail = text[match.end() :].lstrip(": \t")
    for terminator in ("*/", "-->"):
        if tail.endswith(terminator):
            tail = tail[: -len(terminator)]
    return tail.strip()


# Implements: REQ-d00269-G
def read_reference_list(reader: FederatedIdReader, text: str) -> list[RefItem]:
    """The items a reference line names, each with its verdict.

    One reading for every surface that has a whole annotation line in hand,
    so a file-level default and the annotation above a function admit the
    same targets.  A journey step belongs to its own grammar rather than to
    any repository's identifiers, so it is offered alongside them.
    """
    return reader.parse_ref_list(reference_target(text), extra_items=(_JOURNEY_REF_RE.pattern,))


class ReferenceTransformer:
    """Transform a reference.lark parse tree into ParsedContent objects.

    Args:
        resolver: IdResolver for normalizing requirement IDs.
        content_type: Output content type -- "code_ref" or "test_ref".
        line_context: Pre-scan data mapping line_number -> (func_name, class_name, func_line).
        file_default_verifies: File-level default verifies (for test files).
        all_test_funcs: All test functions from pre-scan (for emitting unlinked tests).
        reader: Reads the identifiers of every repository in this
            federation, normalizing each under the grammar of the member
            that claims it.  Defaults to this repository alone.
        quoted_lines: Line numbers holding quoted text -- the interior of a
            fenced block.  A keyword there is displayed, not invoked, so the
            line is left ordinary text however it lexed.
    """

    def __init__(
        self,
        resolver: IdResolver,
        content_type: str,
        line_context: dict[int, tuple[str | None, str | None, int, int]] | None = None,
        file_default_verifies: list[str] | None = None,
        all_test_funcs: list[tuple[int, str, str | None]] | None = None,
        source_id: str = "",
        reader: FederatedIdReader | None = None,
        quoted_lines: set[int] | None = None,
    ) -> None:
        from elspais.utilities.patterns import FederatedIdReader as _Reader

        self.resolver = resolver
        self.reader = reader if reader is not None else _Reader(resolver)
        self.content_type = content_type
        self.line_context = line_context or {}
        self.file_default_verifies = file_default_verifies or []
        self.all_test_funcs = all_test_funcs or []
        self.source_id = source_id
        self.quoted_lines = quoted_lines or set()
        self.warnings: list[str] = []

    def transform(self, tree: Tree) -> list[ParsedContent]:
        """Transform parse tree into ParsedContent list."""
        results: list[ParsedContent] = []
        emitted_func_lines: set[int] = set()

        # Track other_line ranges for remainder grouping
        other_lines: list[tuple[int, str]] = []

        # First pass: process classified lines
        i = 0
        children = tree.children
        while i < len(children):
            child = children[i]
            if not isinstance(child, Tree):
                i += 1
                continue

            if child.data == "other_line":
                token = child.children[0]
                other_lines.append((token.line, str(token)))  # type: ignore[attr-defined]
                i += 1
                continue

            # A keyword inside quoted text names a keyword rather than
            # invoking one, so the line stays ordinary text (REQ-d00269-E).
            # quoted_lines holds lines genuinely interior to a fenced block
            # or a Python string literal -- for a literal, the line that
            # merely opens it (which may carry real code before the quote,
            # e.g. `def test_REQ_p00001(x="a"):`) is deliberately not
            # included, so no rule kind needs exempting here: every rule,
            # including test_name_ref, is safe to skip on a quoted line.
            if self._token_line(child) in self.quoted_lines:
                other_lines.append((self._token_line(child), self._token_text(child)))
                i += 1
                continue

            if child.data == "single_ref":
                pc = self._handle_single_ref(child)
                if pc:
                    if pc.parsed_data.get("function_line"):
                        emitted_func_lines.add(pc.parsed_data["function_line"])
                    results.append(pc)

            elif child.data == "block_header":
                # Collect subsequent block_ref lines
                refs: list[str] = []
                start_ln = self._token_line(child)
                end_ln = start_ln
                header_text = self._token_text(child)
                raw_lines = [header_text]
                keyword = self._detect_keyword(header_text)
                i += 1
                while i < len(children):
                    next_child = children[i]
                    if isinstance(next_child, Tree) and next_child.data == "block_ref":
                        ref_text = self._token_text(next_child)
                        extracted = self._extract_ids(ref_text)
                        refs.extend(extracted)
                        end_ln = self._token_line(next_child)
                        raw_lines.append(ref_text)
                        i += 1
                    elif isinstance(next_child, Tree) and next_child.data == "other_line":
                        # Could be empty comment line -- skip
                        text = self._token_text(next_child)
                        if self._is_empty_comment(text):
                            i += 1
                            continue
                        break
                    else:
                        break

                if refs:
                    # Implements: REQ-d00272-J
                    # A keyword this file's kind does not admit is read and
                    # refused, not passed over as prose: no edge, but a
                    # FORBIDDEN fault naming the keyword and the file kind.
                    if self._keyword_invalid_for_content(keyword):
                        func_name, class_name, func_line, func_end_line = (
                            self._forbidden_line_context(start_ln)
                        )
                        parsed_data = {
                            "implements": [],
                            "verifies": [],
                            "function_name": func_name,
                            "class_name": class_name,
                            "function_line": func_line,
                            "function_end_line": func_end_line,
                            "forbidden_keyword": keyword,
                            "forbidden": refs,
                        }
                        if self.content_type == "test_ref":
                            parsed_data["file_default_verifies"] = self.file_default_verifies
                        if func_line:
                            emitted_func_lines.add(func_line)
                        results.append(
                            ParsedContent(
                                content_type=self.content_type,
                                start_line=start_ln,
                                end_line=end_ln,
                                raw_text="\n".join(raw_lines),
                                parsed_data=parsed_data,
                            )
                        )
                        continue

                    func_name, class_name, func_line, func_end_line = self.line_context.get(
                        start_ln, (None, None, 0, 0)
                    )

                    if self.content_type == "code_ref":
                        parsed_data = {
                            "implements": refs if keyword == "implements" else [],
                            "verifies": refs if keyword == "verifies" else [],
                            "function_name": func_name,
                            "class_name": class_name,
                            "function_line": func_line,
                            "function_end_line": func_end_line,
                        }
                    else:  # test_ref
                        parsed_data = {
                            "verifies": refs,
                            "function_name": func_name,
                            "class_name": class_name,
                            "function_line": func_line,
                            "function_end_line": func_end_line,
                            "file_default_verifies": self.file_default_verifies,
                        }

                    if func_line:
                        emitted_func_lines.add(func_line)
                    results.append(
                        ParsedContent(
                            content_type=self.content_type,
                            start_line=start_ln,
                            end_line=end_ln,
                            raw_text="\n".join(raw_lines),
                            parsed_data=parsed_data,
                        )
                    )
                continue

            elif child.data == "test_name_ref":
                pc = self._handle_test_name_ref(child)
                if pc:
                    if pc.parsed_data.get("function_line"):
                        emitted_func_lines.add(pc.parsed_data["function_line"])
                    results.append(pc)

            elif child.data == "unresolved_ref":
                token = child.children[0]
                pc = self._handle_unresolved_ref(str(token), token.line)  # type: ignore[attr-defined]
                if pc:
                    results.append(pc)
                else:
                    other_lines.append((token.line, str(token)))  # type: ignore[attr-defined]

            i += 1

        # For test files: emit unlinked test functions (third pass)
        if self.content_type == "test_ref":
            for func_line, func_name, class_name in self.all_test_funcs:
                if func_line not in emitted_func_lines:
                    verifies = list(self.file_default_verifies)
                    results.append(
                        ParsedContent(
                            content_type="test_ref",
                            start_line=func_line,
                            end_line=func_line,
                            raw_text="",
                            parsed_data={
                                "verifies": verifies,
                                "function_name": func_name,
                                "class_name": class_name,
                                "function_line": func_line,
                                "file_default_verifies": self.file_default_verifies,
                            },
                        )
                    )

        # Emit remainder blocks for unclaimed lines.
        # Fine-grained grouping ensures each remainder is contiguous, which
        # keeps line numbers accurate for term reference scanning.
        self._flush_remainder(other_lines, results)

        return results

    def _flush_remainder(
        self,
        lines: list[tuple[int, str]],
        results: list[ParsedContent],
        *,
        coarse: bool = False,
    ) -> None:
        """Group other_lines into remainder ParsedContent blocks.

        Args:
            lines: (line_number, text) pairs for unclaimed lines.
            results: List to append remainder ParsedContent to.
            coarse: If True, emit one remainder per file (all unclaimed lines
                merged). Used for code/test files where line-precise grouping
                isn't needed.
        """
        if not lines:
            return

        if coarse:
            # Single remainder covering all unclaimed lines
            results.append(
                ParsedContent(
                    content_type="remainder",
                    start_line=lines[0][0],
                    end_line=lines[-1][0],
                    raw_text="\n".join(text for _, text in lines),
                    parsed_data={},
                )
            )
            return

        # Fine-grained: group strictly contiguous lines (for spec files)
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
    # Single reference handling
    # ------------------------------------------------------------------

    def _handle_single_ref(self, node: Tree) -> ParsedContent | None:
        """Handle a single-line reference comment.

        A line the grammar opened on a namespace and a line it opened on
        anything else are read alike: what the keyword introduces is a list
        of references, or it is a target that could not be resolved
        (REQ-d00269-G).  So both go through one reader.
        """
        token = node.children[0]
        return self._handle_unresolved_ref(str(token), token.line)  # type: ignore[attr-defined]

    # ------------------------------------------------------------------
    # Unresolvable reference handling
    # ------------------------------------------------------------------

    # Implements: REQ-d00269-D, REQ-d00269-G, REQ-d00272-J
    def _handle_unresolved_ref(self, text: str, line_num: int) -> ParsedContent | None:
        """Read a reference line, resolved or not.

        The line is recognised because of where the keyword sits, so the
        target may be written any way at all.  What it may *mean* is
        narrower: a list of references, each item matched whole.  A target
        that is anything else -- prose around an identifier, a foreign
        identifier that merely contains one -- resolves to nothing and is
        carried through verbatim instead, on the same broken-reference
        channel a misspelled local identifier travels.  Nothing is picked out
        of it: an edge to a requirement the author never named is worse than
        no edge, because a reference that resolved is a reference nothing
        reports.

        A keyword this kind of file may not use is read the same as any
        other, and the relationship it declares is refused rather than
        created -- but the refusal is reported, naming the keyword and the
        file kind, rather than the line being passed over as though it were
        prose (REQ-d00272-J).

        Returns None only when the line names nothing at all: an empty
        declaration, or content no grammar of the federation accounts for.
        """
        keyword = self._detect_keyword(text)
        if self._keyword_invalid_for_content(keyword):
            items = read_reference_list(self.reader, text)
            targets = [i.resolved or i.raw for i in items if i.raw]
            if not targets:
                return None
            func_name, class_name, func_line, func_end_line = self._forbidden_line_context(line_num)
            parsed_data: dict[str, Any] = {
                "implements": [],
                "verifies": [],
                "function_name": func_name,
                "class_name": class_name,
                "function_line": func_line,
                "function_end_line": func_end_line,
                "forbidden_keyword": keyword,
                "forbidden": targets,
            }
            if self.content_type == "test_ref":
                parsed_data["file_default_verifies"] = self.file_default_verifies
            return ParsedContent(
                content_type=self.content_type,
                start_line=line_num,
                end_line=line_num,
                raw_text=text,
                parsed_data=parsed_data,
            )

        items = read_reference_list(self.reader, text)
        if not items:
            return None
        # A faulted item stays in the ref list: the builder records a fault
        # for a ref that does not resolve, so dropping it here would make
        # every malformed item vanish -- the defect this work exists to
        # remove.  Its verdict rides alongside so the builder can stamp the
        # class rather than re-deriving it.
        refs = [i.resolved or i.raw for i in items if i.raw]
        verdicts = {i.raw: (i.fault_class, i.codes) for i in items if i.fault_class is not None}
        if not refs:
            return None

        func_name, class_name, func_line, func_end_line = self.line_context.get(
            line_num, (None, None, 0, 0)
        )
        if self.content_type == "code_ref":
            parsed_data = {
                "implements": refs if keyword == "implements" else [],
                "verifies": refs if keyword == "verifies" else [],
                "function_name": func_name,
                "class_name": class_name,
                "function_line": func_line,
                "function_end_line": func_end_line,
                "reference_verdicts": verdicts,
            }
        else:
            parsed_data = {
                "verifies": refs,
                "function_name": func_name,
                "class_name": class_name,
                "function_line": func_line,
                "file_default_verifies": self.file_default_verifies,
                "reference_verdicts": verdicts,
            }

        return ParsedContent(
            content_type=self.content_type,
            start_line=line_num,
            end_line=line_num,
            raw_text=text,
            parsed_data=parsed_data,
        )

    # ------------------------------------------------------------------
    # Test name reference handling
    # ------------------------------------------------------------------

    def _handle_test_name_ref(self, node: Tree) -> ParsedContent | None:
        """Handle a test function name containing a REQ reference."""
        token = node.children[0]
        text = str(token)
        line_num = token.line  # type: ignore[attr-defined]

        # Extract REQ_xxx from function name (underscored form).
        # Test names use underscores: def test_foo_REQ_p00001_A
        # A test name is a test annotation, so it names an identifier any
        # federation member owns (REQ-d00269-C).
        ref = self.reader.extract_underscored_ref(text)
        if ref is None:
            return None

        func_name, class_name, func_line, _func_end = self.line_context.get(
            line_num, (None, None, 0, 0)
        )

        parsed_data: dict[str, Any] = {
            "verifies": [ref],
            "function_name": func_name,
            "class_name": class_name,
            "function_line": func_line,
            "file_default_verifies": self.file_default_verifies,
        }

        return ParsedContent(
            content_type="test_ref",
            start_line=line_num,
            end_line=line_num,
            raw_text=text,
            parsed_data=parsed_data,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _extract_ids(self, text: str) -> list[str]:
        """Extract requirement IDs from a reference line (including multi-assertion syntax).

        Collects both REQ-style ids (via the namespace pattern) and JNY-style
        ids (whole journeys and addressable steps) so that ``Verifies:``
        annotations may target either kind.  An identifier any federation
        member owns is recognised here and normalized by the member that
        claims it (REQ-d00269-C).
        """
        refs = self.reader.extract_refs(text)
        for jny_id in _JOURNEY_REF_RE.findall(text):
            if jny_id not in refs:
                refs.append(jny_id)
        return refs

    def _detect_keyword(self, text: str) -> str:
        """Detect which reference keyword is used in *text*.

        Returns:
            ``"implements"``, ``"verifies"``, ``"refines"``, or
            ``"integrates"``. Falls back to ``"implements"`` if no keyword
            is found.
        """
        m = _KEYWORD_RE.search(text)
        if m:
            return m.group(0).lower()
        return "implements"

    # Implements: REQ-d00272-J
    def _keyword_invalid_for_content(self, keyword: str) -> bool:
        """Whether *keyword* is one this file's kind may not use.

        ``Integrates`` is spec-file only; ``Refines`` is
        requirement-to-requirement only.  A test file admits only
        ``Verifies``.
        """
        if keyword == "integrates":
            return True
        if self.content_type == "code_ref" and keyword == "refines":
            return True
        if self.content_type == "test_ref" and keyword != "verifies":
            return True
        return False

    def _forbidden_line_context(self, line_num: int) -> tuple[str | None, str | None, int, int]:
        """Function/class context for a refused keyword's fault, by file kind.

        A code file keeps its ordinary context, since a refused code
        reference still anchors to the function it annotates. A test file
        deliberately drops it: attaching ``function_line`` here would mark
        that line "emitted" and suppress the third-pass unlinked-test
        fallback, silently costing the actual test function the
        file-default ``Verifies`` it is owed regardless of this refusal.
        """
        if self.content_type == "code_ref":
            return self.line_context.get(line_num, (None, None, 0, 0))
        return (None, None, 0, 0)

    def _is_empty_comment(self, text: str) -> bool:
        """Check if a line is an empty comment."""
        stripped = text.strip()
        for style in _COMMENT_STYLES:
            if stripped.startswith(style):
                remainder = stripped[len(style) :].strip().rstrip("#/-").strip()
                if not remainder:
                    return True
        return False

    def _token_line(self, node: Tree) -> int:
        """Get line number from a tree node's first token."""
        token = node.children[0]
        return token.line  # type: ignore[attr-defined]

    def _token_text(self, node: Tree) -> str:
        """Get text from a tree node's first token."""
        return str(node.children[0])
