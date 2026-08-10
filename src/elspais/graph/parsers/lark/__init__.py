"""Lark-based parser system for elspais spec and reference files.

Replaces the legacy line-claiming parser pipeline with declarative Lark
grammars + transformers.  Two grammars:

- ``requirement.lark`` -- spec files (requirements + journeys + remainder).
  Earley parser.
- ``reference.lark`` -- code/test files (comment-based refs + remainder).
  LALR parser.

Both import shared ID rules from ``common.lark``.

Public API:
    GrammarFactory  -- config -> compiled Lark parser (cached)
    FileDispatcher  -- (file, file_type, config) -> Iterator[ParsedContent]
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import TYPE_CHECKING

from lark import Lark

if TYPE_CHECKING:
    from collections.abc import Sequence

    from elspais.utilities.patterns import IdResolver

# Directory containing .lark grammar files
_GRAMMARS_DIR = Path(__file__).parent / "grammars"


class GrammarFactory:
    """Build parameterized Lark parsers from .lark template files.

    Template tokens (e.g. ``__NAMESPACE__``) are replaced with config-derived
    regex fragments before compilation.  Compiled parsers are cached by the
    hash of the fully-substituted grammar text so identical configs share a
    single parser instance.
    """

    # Class-level cache: grammar_hash -> compiled Lark instance
    _cache: dict[str, Lark] = {}

    def __init__(
        self,
        resolver: IdResolver,
        member_resolvers: Sequence[IdResolver] = (),
    ) -> None:
        from elspais.utilities.patterns import FederatedIdReader

        self._resolver = resolver
        self._reader = FederatedIdReader(resolver, member_resolvers)

    # ------------------------------------------------------------------
    # Token builders (derive regex fragments from IdResolver / config)
    # ------------------------------------------------------------------

    def _build_tokens(self, federated: bool = False) -> dict[str, str]:
        """Build substitution tokens from the resolver's identifier grammar.

        Args:
            federated: Widen the identifier and namespace fragments to every
                federation member's grammar.  Code and test annotations may
                name an identifier any member owns (REQ-d00269-C); a spec
                file declares only identifiers its own repository owns, so
                its grammar stays narrow.
        """
        # Every fragment comes from the one derivation authority (REQ-d00268-C),
        # so the grammar this parser recognises and the identifiers the resolver
        # accepts cannot drift apart.  A federated fragment alternates each
        # member's own derivation rather than merging configurations
        # (REQ-d00268-E).
        g = self._resolver.grammar()

        tokens: dict[str, str] = {
            "__NAMESPACE__": self._reader.namespace_pattern() if federated else g.namespace,
            "__TYPE_PATTERN__": g.level,
            "__DIGITS_PATTERN__": g.component,
            "__ID_PATTERN__": self._reader.identifier_pattern() if federated else g.identifier,
            "__ASSERTION_LABEL__": g.assertion_label,
            "__ASSERTION_SEP__": g.assertion_separator,
            "__MULTI_SEP__": g.multi_separator,
        }

        # Reference grammar tokens (comment styles + keywords)
        tokens["__COMMENT_STYLES__"] = r"\#|\/\/|\-\-"
        impl_kw = ["Implements", "IMPLEMENTS"]
        ver_kw = ["Verifies", "VERIFIES"]
        ref_kw = ["Refines", "REFINES"]
        tokens["__KEYWORDS__"] = "|".join(re.escape(k) for k in impl_kw + ver_kw + ref_kw)
        tokens["__IMPL_KEYWORDS__"] = "|".join(re.escape(k) for k in impl_kw)
        tokens["__VER_KEYWORDS__"] = "|".join(re.escape(k) for k in ver_kw)

        return tokens

    # ------------------------------------------------------------------
    # Grammar compilation
    # ------------------------------------------------------------------

    def _substitute(self, template: str, tokens: dict[str, str]) -> str:
        """Replace all ``__TOKEN__`` placeholders in *template*."""
        result = template
        for token, value in tokens.items():
            result = result.replace(token, value)
        return result

    def _read_grammar(self, name: str) -> str:
        """Read a .lark grammar file from the grammars directory."""
        path = _GRAMMARS_DIR / name
        return path.read_text(encoding="utf-8")

    def _grammar_hash(self, text: str) -> str:
        """SHA-256 hash of the fully-substituted grammar text."""
        return hashlib.sha256(text.encode()).hexdigest()

    def get_requirement_parser(self) -> Lark:
        """Compile (or retrieve cached) requirement grammar parser.

        Uses LALR parser with contextual lexer.  The contextual lexer
        activates terminals only when the parser state can accept them,
        so metadata field terminals are only tried inside a requirement
        preamble -- the same text outside a requirement is lexed as TEXT.
        """
        tokens = self._build_tokens()
        full_grammar = self._substitute(self._read_grammar("requirement.lark"), tokens)

        key = self._grammar_hash(full_grammar)
        if key not in self._cache:
            self._cache[key] = Lark(
                full_grammar,
                parser="lalr",
                propagate_positions=True,
                maybe_placeholders=False,
            )
        return self._cache[key]

    def get_reference_parser(self) -> Lark:
        """Compile (or retrieve cached) reference grammar parser."""
        tokens = self._build_tokens(federated=True)
        full_grammar = self._substitute(self._read_grammar("reference.lark"), tokens)

        key = self._grammar_hash(full_grammar)
        if key not in self._cache:
            self._cache[key] = Lark(
                full_grammar,
                parser="lalr",
                propagate_positions=True,
                maybe_placeholders=False,
            )
        return self._cache[key]


class FileDispatcher:
    """Route files to the correct Lark grammar based on file type.

    Replaces ``ParserRegistry`` -- given a file, its content, its file type,
    and configuration, the dispatcher:
    1. Picks the grammar (requirement.lark for SPEC, reference.lark for CODE/TEST)
    2. Parses the content
    3. Runs the appropriate transformer
    4. Yields ``ParsedContent`` objects

    Result files (JUnit XML, pytest JSON) are NOT handled here -- they use
    their own stdlib-based parsers.

    Args:
        resolver: IdResolver for ID parsing and normalization.
        member_resolvers: The resolvers of the other repositories in this
            federation.  Code and test annotations may name an identifier
            any member owns, and each such reference is normalized by the
            member that claims it (REQ-d00269-C).
    """

    def __init__(
        self,
        resolver: IdResolver,
        member_resolvers: Sequence[IdResolver] = (),
    ) -> None:
        from elspais.utilities.patterns import FederatedIdReader

        self._resolver = resolver
        self._reader = FederatedIdReader(resolver, member_resolvers)
        self._factory = GrammarFactory(resolver, member_resolvers)
        self._req_parser: Lark | None = None
        self._ref_parser: Lark | None = None

    def _get_req_parser(self) -> Lark:
        if self._req_parser is None:
            self._req_parser = self._factory.get_requirement_parser()
        return self._req_parser

    def _get_ref_parser(self) -> Lark:
        if self._ref_parser is None:
            self._ref_parser = self._factory.get_reference_parser()
        return self._ref_parser

    @staticmethod
    def _neutralize_fenced_blocks(content: str) -> str:
        """Replace content inside fenced code blocks with neutral text.

        Fenced code blocks (```...```) may contain example requirement or
        journey syntax that should not be parsed as actual content. This
        replaces each line inside a fence with a neutral comment that the
        grammar will match as TEXT/remainder, preserving line count.
        """
        fenced = FileDispatcher._fenced_line_numbers(content)
        result: list[str] = []
        for number, line in enumerate(content.split("\n"), start=1):
            if number in fenced:
                # Replace with a neutral line that won't match any grammar rule
                result.append("<!-- fenced -->" if line.strip() else "")
            else:
                result.append(line)
        return "\n".join(result)

    @staticmethod
    def _fenced_line_numbers(content: str) -> set[int]:
        """The 1-based line numbers that sit inside a fenced code block.

        The fence markers themselves are excluded -- they delimit the quoted
        region rather than belonging to it. Text inside the region is a
        display of syntax, not an instance of it, so a *Traceability* keyword
        written there names a keyword instead of invoking one.
        """
        fenced: set[int] = set()
        in_fence = False
        for number, line in enumerate(content.split("\n"), start=1):
            if line.strip().startswith("```"):
                in_fence = not in_fence
            elif in_fence:
                fenced.add(number)
        return fenced

    def dispatch_spec(
        self,
        content: str,
        file_path: str = "",
    ) -> list:
        """Parse a spec file (SPEC or JOURNEY type) and return ParsedContent list."""
        from elspais.graph.parsers.lark.transformers.requirement import RequirementTransformer

        if not content.endswith("\n"):
            content += "\n"
        # Implements: REQ-d00247-A
        # Neutralize fenced code blocks for grammar matching only; the
        # neutralized buffer must NOT escape the parser. Pass the original
        # content as `source` so REMAINDER nodes capture the original text.
        original_content = content
        neutralized = self._neutralize_fenced_blocks(content)
        parser = self._get_req_parser()
        tree = parser.parse(neutralized)
        transformer = RequirementTransformer(self._resolver)
        return transformer.transform(tree, source=original_content)

    def dispatch_code(
        self,
        content: str,
        file_path: str = "",
        line_context: dict[int, tuple[str | None, str | None, int, int]] | None = None,
    ) -> list:
        """Parse a code file and return ParsedContent list."""
        from elspais.graph.parsers.lark.transformers.reference import ReferenceTransformer

        if not content.endswith("\n"):
            content += "\n"

        # Build line context if not provided
        if line_context is None:
            from elspais.graph.parsers.prescan import build_line_context, detect_language

            language = detect_language(file_path)
            lines = [(i + 1, line) for i, line in enumerate(content.split("\n"))]
            line_context = build_line_context(lines, language)

        parser = self._get_ref_parser()
        tree = parser.parse(content)
        transformer = ReferenceTransformer(
            self._resolver,
            "code_ref",
            line_context,
            source_id=file_path,
            reader=self._reader,
            quoted_lines=self._fenced_line_numbers(content),
        )
        return transformer.transform(tree)

    def dispatch_test(
        self,
        content: str,
        file_path: str = "",
        prescan_data: dict[str, list[dict]] | None = None,
    ) -> list:
        """Parse a test file and return ParsedContent list."""
        from elspais.graph.parsers.lark.transformers.reference import ReferenceTransformer
        from elspais.graph.parsers.prescan import (
            ast_prescan,
            dart_prescan,
            external_prescan,
            text_prescan,
        )

        if not content.endswith("\n"):
            content += "\n"

        lines = [(i + 1, line) for i, line in enumerate(content.split("\n"))]

        # Pre-scan for function/class context
        # Implements: REQ-d00254-K
        is_python = file_path.endswith(".py")
        is_dart = file_path.endswith(".dart")

        # Implements: REQ-d00254-N
        if prescan_data and file_path in prescan_data:
            line_context, all_test_funcs, first_def_line = external_prescan(
                prescan_data[file_path], lines
            )
        elif is_python:
            source = "\n".join(text for _, text in lines)
            try:
                line_context, all_test_funcs, first_def_line = ast_prescan(source, lines)
            except SyntaxError:
                line_context, all_test_funcs, first_def_line = text_prescan(lines)
        elif is_dart:
            line_context, all_test_funcs, first_def_line = dart_prescan(lines)
        else:
            line_context, all_test_funcs, first_def_line = text_prescan(lines)

        # Extract file-level default verifies and expected-broken-links
        # from control markers in the parse tree
        parser = self._get_ref_parser()
        tree = parser.parse(content)

        from elspais.graph.parsers.patterns import KEYWORD_PATTERN

        file_default_verifies: list[str] = []
        expected_broken_count = 0
        import re as _re

        for child in tree.children:
            if not hasattr(child, "data"):
                continue
            if child.data == "control_marker":
                text = str(child.children[0])
                m = _re.search(r"expected-broken-links\s+(\d+)", text, _re.IGNORECASE)
                if m:
                    expected_broken_count = int(m.group(1))
            elif child.data == "single_ref":
                token = child.children[0]
                ln = token.line  # type: ignore[attr-defined]
                if first_def_line and ln >= first_def_line:
                    continue
                text = str(token)
                # File-level reference comments become default verifies for
                # all test functions in the file.  Only 'Verifies' is valid
                # in test files; 'Implements'/'Refines' are skipped.
                kw_match = KEYWORD_PATTERN.search(text)
                if kw_match:
                    kw = kw_match.group(0).lower()
                    if kw != "verifies":
                        # Silently skip — test fixtures contain cross-type
                        # keywords in string literals
                        continue
                    for ref in self._reader.extract_refs(text):
                        if ref not in file_default_verifies:
                            file_default_verifies.append(ref)

        transformer = ReferenceTransformer(
            self._resolver,
            "test_ref",
            line_context=line_context,
            file_default_verifies=file_default_verifies,
            expected_broken_count=expected_broken_count,
            all_test_funcs=all_test_funcs,
            source_id=file_path,
            reader=self._reader,
            quoted_lines=self._fenced_line_numbers(content),
        )
        return transformer.transform(tree)


__all__ = ["GrammarFactory", "FileDispatcher"]
