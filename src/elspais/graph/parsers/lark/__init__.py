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

    def __init__(self, resolver: IdResolver) -> None:
        self._resolver = resolver

    # ------------------------------------------------------------------
    # Token builders (derive regex fragments from IdResolver / config)
    # ------------------------------------------------------------------

    def _build_tokens(self) -> dict[str, str]:
        """Build substitution tokens from the resolver."""
        r = self._resolver
        cfg = r.config

        # Namespace: literal string, e.g. "REQ"
        namespace = re.escape(cfg.namespace)

        # Type pattern: alternation of alias values (e.g. "p|o|d")
        type_values = r.all_type_alias_values()
        if type_values:
            type_pattern = "|".join(re.escape(v) for v in type_values)
        else:
            type_pattern = "[a-z]"

        # Component/digits pattern
        comp = cfg.component
        if comp.style == "numeric":
            if comp.digits > 0:
                digits_pattern = rf"\d{{1,{comp.digits}}}"
            else:
                digits_pattern = r"\d+"
        elif comp.style == "named":
            digits_pattern = comp.pattern or r"[A-Za-z][A-Za-z0-9]+"
        elif comp.style == "alphanumeric":
            digits_pattern = comp.pattern or r"[A-Z0-9]+"
        else:
            digits_pattern = r"[A-Za-z0-9]+"

        # Assertion label
        assertion_label = r._assertion_label_regex_str()

        # Multi-assertion separator
        multi_sep = (
            re.escape(cfg.assertions.multi_separator) if cfg.assertions.multi_separator else r"\+"
        )

        # Build __ID_PATTERN__ from canonical template.
        # Strategy: split canonical into literal segments and placeholders,
        # escape the literals, then join with regex fragments.
        canonical = cfg.canonical_template
        placeholders = {
            "{namespace}": re.escape(namespace),
            "{component}": digits_pattern,
            "{level}": f"(?:{type_pattern})",
        }
        # {type} -> alternation of canonical type codes
        all_type_codes = list(r.config.types.keys())
        if all_type_codes:
            placeholders["{type}"] = "(?:" + "|".join(re.escape(t) for t in all_type_codes) + ")"
        # {level.X} or {type.X} -> alternation of alias values
        for m in re.finditer(r"\{(?:type|level)\.(\w+)\}", canonical):
            alias_name = m.group(1)
            alias_vals = r._reverse_aliases.get(alias_name, {})
            if alias_vals:
                val_alt = "|".join(re.escape(v) for v in alias_vals)
                placeholders[m.group(0)] = f"(?:{val_alt})"

        # Split on placeholders, escape literal parts, reassemble
        parts = re.split(r"(\{[^}]+\})", canonical)
        id_pattern = "".join(
            placeholders[p] if p in placeholders else re.escape(p)
            for p in parts
        )

        tokens: dict[str, str] = {
            "__NAMESPACE__": namespace,
            "__TYPE_PATTERN__": type_pattern,
            "__DIGITS_PATTERN__": digits_pattern,
            "__ID_PATTERN__": id_pattern,
            "__ASSERTION_LABEL__": assertion_label,
            "__MULTI_SEP__": multi_sep,
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
        tokens = self._build_tokens()
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
    """

    def __init__(
        self,
        resolver: IdResolver,
    ) -> None:
        self._resolver = resolver
        self._factory = GrammarFactory(resolver)
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
        lines = content.split("\n")
        result: list[str] = []
        in_fence = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("```") and not in_fence:
                in_fence = True
                result.append(line)  # keep the opening fence marker as-is
            elif stripped.startswith("```") and in_fence:
                in_fence = False
                result.append(line)  # keep the closing fence marker as-is
            elif in_fence:
                # Replace with a neutral line that won't match any grammar rule
                result.append("<!-- fenced -->" if line.strip() else "")
            else:
                result.append(line)
        return "\n".join(result)

    def dispatch_spec(
        self,
        content: str,
        file_path: str = "",
    ) -> list:
        """Parse a spec file (SPEC or JOURNEY type) and return ParsedContent list."""
        from elspais.graph.parsers.lark.transformers.requirement import RequirementTransformer

        if not content.endswith("\n"):
            content += "\n"
        # Neutralize fenced code blocks before parsing
        content = self._neutralize_fenced_blocks(content)
        parser = self._get_req_parser()
        tree = parser.parse(content)
        transformer = RequirementTransformer(self._resolver)
        return transformer.transform(tree, source=content)

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
        from elspais.graph.parsers.prescan import ast_prescan, external_prescan, text_prescan

        if not content.endswith("\n"):
            content += "\n"

        lines = [(i + 1, line) for i, line in enumerate(content.split("\n"))]

        # Pre-scan for function/class context
        is_python = file_path.endswith(".py")

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
        else:
            line_context, all_test_funcs, first_def_line = text_prescan(lines)

        # Extract file-level default verifies and expected-broken-links
        # from control markers in the parse tree
        parser = self._get_ref_parser()
        tree = parser.parse(content)

        file_default_verifies: list[str] = []
        expected_broken_count = 0
        import re as _re

        prefix = self._resolver.config.namespace
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
                kw_match = _re.search(r"(?:implements|verifies|refines)", text, _re.IGNORECASE)
                if kw_match:
                    kw = kw_match.group(0).lower()
                    if kw != "verifies":
                        # Silently skip — test fixtures contain cross-type
                        # keywords in string literals
                        continue
                    # Include multi-assertion separator (+) in pattern
                    multi_sep = _re.escape(self._resolver.config.assertions.multi_separator or "+")
                    for ref_match in _re.finditer(
                        rf"{_re.escape(prefix)}[-_][A-Za-z0-9\-_]+(?:{multi_sep}[A-Za-z0-9]+)*",
                        text,
                        _re.IGNORECASE,
                    ):
                        ref = self._resolver.normalize_ref(ref_match.group(0))
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
        )
        return transformer.transform(tree)


__all__ = ["GrammarFactory", "FileDispatcher"]
