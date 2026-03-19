"""ReferenceTransformer - Converts Lark reference parse tree to ParsedContent list.

Handles both code_ref and test_ref content types.  Pre-scan data (function/class
context) is injected from external sources -- AST-based for Python, text-based
for others, or external prescan command.

The grammar pre-classifies lines as single_ref, block_header, block_ref,
test_name_ref, control_marker, or other_line.  This transformer:
1. Extracts requirement IDs from classified lines
2. Annotates with function/class context from pre-scan
3. Produces ParsedContent matching the old CodeParser/TestParser contracts
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from lark import Tree

from elspais.graph.parsers import ParsedContent

if TYPE_CHECKING:
    from elspais.utilities.patterns import IdResolver

# Hardcoded comment styles for empty-comment detection
_COMMENT_STYLES = ["#", "//", "--"]


class ReferenceTransformer:
    """Transform a reference.lark parse tree into ParsedContent objects.

    Args:
        resolver: IdResolver for normalizing requirement IDs.
        content_type: Output content type -- "code_ref" or "test_ref".
        line_context: Pre-scan data mapping line_number -> (func_name, class_name, func_line).
        file_default_verifies: File-level default verifies (for test files).
        expected_broken_count: From elspais control marker (for test files).
        all_test_funcs: All test functions from pre-scan (for emitting unlinked tests).
    """

    def __init__(
        self,
        resolver: IdResolver,
        content_type: str,
        line_context: dict[int, tuple[str | None, str | None, int]] | None = None,
        file_default_verifies: list[str] | None = None,
        expected_broken_count: int = 0,
        all_test_funcs: list[tuple[int, str, str | None]] | None = None,
    ) -> None:
        self.resolver = resolver
        self.content_type = content_type
        self.line_context = line_context or {}
        self.file_default_verifies = file_default_verifies or []
        self.expected_broken_count = expected_broken_count
        self.all_test_funcs = all_test_funcs or []

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
                raw_lines = [self._token_text(child)]
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
                    func_name, class_name, func_line = self.line_context.get(
                        start_ln, (None, None, 0)
                    )
                    key = "implements" if self.content_type == "code_ref" else "verifies"
                    parsed_data: dict[str, Any] = {
                        key: refs,
                        "function_name": func_name,
                        "class_name": class_name,
                        "function_line": func_line,
                    }
                    if self.content_type == "code_ref":
                        parsed_data.setdefault("verifies", [])
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

            elif child.data == "test_name_ref":
                pc = self._handle_test_name_ref(child)
                if pc:
                    if pc.parsed_data.get("function_line"):
                        emitted_func_lines.add(pc.parsed_data["function_line"])
                    results.append(pc)

            elif child.data == "control_marker":
                # Already extracted during pre-processing; skip
                pass

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
        # For code/test files, merge all unclaimed lines into a single remainder
        # (coarse grouping). Spec files need line-precise grouping for round-trip
        # rendering, but code/test files only need remainders preserved for
        # potential future reference rewriting.
        coarse = self.content_type in ("code_ref", "test_ref")
        self._flush_remainder(other_lines, results, coarse=coarse)

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
        """Handle a single-line reference comment."""
        token = node.children[0]
        text = str(token)
        line_num = token.line  # type: ignore[attr-defined]

        refs = self._extract_ids(text)
        if not refs:
            return None

        func_name, class_name, func_line = self.line_context.get(line_num, (None, None, 0))

        # Determine if this is implements or verifies based on keyword
        is_verifies = self._text_has_verify_keyword(text)

        if self.content_type == "code_ref":
            parsed_data: dict[str, Any] = {
                "implements": [] if is_verifies else refs,
                "verifies": refs if is_verifies else [],
                "function_name": func_name,
                "class_name": class_name,
                "function_line": func_line,
            }
        else:  # test_ref
            parsed_data = {
                "verifies": refs,
                "function_name": func_name,
                "class_name": class_name,
                "function_line": func_line,
                "file_default_verifies": self.file_default_verifies,
            }
            if self.expected_broken_count > 0:
                parsed_data["expected_broken_count"] = self.expected_broken_count

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
        # We need to match the ID part (REQ_p00001) and optional assertion
        # suffix (_A) but stop before lowercase continuation (_validates).
        prefix = self.resolver.config.namespace
        type_codes = self.resolver.all_type_alias_values()
        if type_codes:
            type_pattern = f"(?:{'|'.join(re.escape(t) for t in type_codes)})"
        else:
            type_pattern = r"[a-z]"
        comp = self.resolver.config.component
        if comp.style == "numeric":
            id_number = rf"\d{{{comp.digits}}}"
        else:
            id_number = r"[A-Za-z0-9]+"

        # Assertion: uppercase letter NOT followed by lowercase (to avoid
        # matching _validates as assertion V)
        assertion_pat = r"(?:_[A-Z](?![a-z]))+"

        full_pattern = re.compile(
            rf"(?P<ref>{re.escape(prefix)}_{type_pattern}{id_number}" rf"(?:{assertion_pat})?)",
            re.IGNORECASE,
        )
        match = full_pattern.search(text)
        if not match:
            return None

        ref = self.resolver.normalize_ref(match.group("ref"))
        func_name, class_name, func_line = self.line_context.get(line_num, (None, None, 0))

        parsed_data: dict[str, Any] = {
            "verifies": [ref],
            "function_name": func_name,
            "class_name": class_name,
            "function_line": func_line,
            "file_default_verifies": self.file_default_verifies,
        }
        if self.expected_broken_count > 0:
            parsed_data["expected_broken_count"] = self.expected_broken_count

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
        """Extract requirement IDs from a reference line."""
        prefix = self.resolver.config.namespace
        pattern = re.compile(
            rf"{re.escape(prefix)}[-_][A-Za-z0-9\-_]+",
            re.IGNORECASE,
        )
        refs = []
        for m in pattern.finditer(text):
            ref = self.resolver.normalize_ref(m.group(0))
            if ref not in refs:
                refs.append(ref)
        return refs

    def _text_has_verify_keyword(self, text: str) -> bool:
        """Check if text contains a verify-type keyword."""
        return "verifies" in text.lower()

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
