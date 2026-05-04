# Validates REQ-d00246-B
"""Tests for emphasis-stripping normalization in lark transformers.

These tests pin the post-fix behavior of the lark requirement transformer at
three sites where user-text is captured from emphasis-decorated spec source:

1. Term names extracted from `definition_block` TEXT tokens.
2. Value text on journey `Actor`/`Goal`/`Context` metadata fields.
3. `reference term` / `reference source` definition-block fields.

Each site MUST normalize via the canonical `strip_emphasis()` helper from
`elspais.utilities.markdown` (balanced strip semantics). Ad-hoc per-character
strip calls (e.g., `.strip('*')`, `.strip('_')`) MUST NOT remain in the
transformer modules. A static lint guard at the bottom of this file enforces
the latter.

Tests are expected to FAIL until the transformer is migrated to use
`strip_emphasis()`.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from elspais.graph.parsers.lark import GrammarFactory
from elspais.graph.parsers.lark.transformers.requirement import RequirementTransformer
from elspais.utilities.patterns import IdPatternConfig, IdResolver


@pytest.fixture
def resolver() -> IdResolver:
    """IdResolver for standard HHT-like pattern (matches test_definition_grammar)."""
    config = IdPatternConfig.from_dict(
        {
            "project": {"namespace": "REQ"},
            "id-patterns": {
                "canonical": "{namespace}-{type.letter}{component}",
                "aliases": {"short": "{type.letter}{component}"},
                "types": {
                    "prd": {"level": 1, "aliases": {"letter": "p"}},
                    "ops": {"level": 2, "aliases": {"letter": "o"}},
                    "dev": {"level": 3, "aliases": {"letter": "d"}},
                },
                "component": {"style": "numeric", "digits": 5, "leading_zeros": True},
                "assertions": {"label_style": "uppercase", "max_count": 26},
            },
        }
    )
    return IdResolver(config)


def _parse(content: str, resolver: IdResolver) -> list:
    """Run the real Lark pipeline (parser + transformer) against `content`."""
    factory = GrammarFactory(resolver)
    lark_parser = factory.get_requirement_parser()
    transformer = RequirementTransformer(resolver)
    if not content.endswith("\n"):
        content += "\n"
    tree = lark_parser.parse(content)
    return transformer.transform(tree, source=content)


def _first_definition(results: list) -> dict:
    """Locate the parsed_data of the first definition_block in `results`.

    Mirrors the pattern used in tests/test_definition_grammar.py: definitions
    may surface as standalone ParsedContent or be nested under a requirement's
    parsed_data['definitions'] list.
    """
    for r in results:
        if r.content_type == "definition_block":
            return r.parsed_data
    for r in results:
        if r.content_type == "requirement":
            defs = r.parsed_data.get("definitions") or []
            if defs:
                return defs[0]
    raise AssertionError(
        f"No definition data found. content_types: {[r.content_type for r in results]}"
    )


def _first_journey(results: list) -> dict:
    """Locate the parsed_data of the first journey ParsedContent."""
    for r in results:
        if r.content_type == "journey":
            return r.parsed_data
    raise AssertionError(
        f"No journey content found. content_types: {[r.content_type for r in results]}"
    )


# ---------------------------------------------------------------------------
# A. Term name normalization (definition block TEXT token).
# ---------------------------------------------------------------------------


class TestTermNameEmphasis:
    """Validates REQ-d00246-B: term names are normalized via strip_emphasis()."""

    @pytest.mark.parametrize(
        "decorated,expected",
        [
            ("**Email Address**", "Email Address"),
            ("__Email Address__", "Email Address"),
            ("*Email*", "Email"),
            ("_Email_", "Email"),
            # Corrupted glossary pattern: many-asterisk wrapping must collapse.
            ("********Email Address********", "Email Address"),
            # Plain text must pass through unchanged.
            ("Email Address", "Email Address"),
        ],
    )
    # Implements: REQ-d00246-B
    def test_REQ_d00246_B_term_name_emphasis_stripped(
        self, resolver: IdResolver, decorated: str, expected: str
    ) -> None:
        content = f"""\
# REQ-p00001: Term Wrapper Test
**Level**: prd | **Status**: Active

{decorated}
: A unique identifier for the user.

## Assertions

A. First assertion

*End* *REQ-p00001* **Hash**: abcd1234
"""
        results = _parse(content, resolver)
        def_data = _first_definition(results)
        assert def_data.get("term") == expected, (
            f"Decorated term {decorated!r} should normalize to {expected!r}, "
            f"got {def_data.get('term')!r}"
        )

    # Implements: REQ-d00246-B
    def test_REQ_d00246_B_term_name_unbalanced_left_intact(self, resolver: IdResolver) -> None:
        """Unbalanced wrappers (different markers / unequal widths) are left alone."""
        content = """\
# REQ-p00001: Asymmetric Wrapper Test
**Level**: prd | **Status**: Active

*Foo**
: A unique identifier for the user.

## Assertions

A. First assertion

*End* *REQ-p00001* **Hash**: abcd1234
"""
        results = _parse(content, resolver)
        def_data = _first_definition(results)
        assert def_data.get("term") == "*Foo**", (
            f"Asymmetric wrapper '*Foo**' should pass through unchanged "
            f"(balanced strip semantics), got {def_data.get('term')!r}"
        )


# ---------------------------------------------------------------------------
# B. Journey Actor/Goal/Context value normalization.
# ---------------------------------------------------------------------------


class TestJourneyMetadataEmphasis:
    """Validates REQ-d00246-B: journey metadata values are normalized."""

    # Implements: REQ-d00246-B
    def test_REQ_d00246_B_journey_actor_goal_context_double_asterisk(
        self, resolver: IdResolver
    ) -> None:
        """Wrapped values on Actor/Goal/Context lose their `**...**` wrappers."""
        content = """\
### JNY-001: Decorated Metadata
**Actor**: **Sarah (Site 101)**
**Goal**: **Submit a clean enrollment form**
**Context**: **Pre-screening visit**

## Steps

1. User does the thing.

*End* *JNY-001*
"""
        results = _parse(content, resolver)
        jny = _first_journey(results)
        assert (
            jny.get("actor") == "Sarah (Site 101)"
        ), f"actor wrapped in '**...**' must be unwrapped, got {jny.get('actor')!r}"
        assert (
            jny.get("goal") == "Submit a clean enrollment form"
        ), f"goal wrapped in '**...**' must be unwrapped, got {jny.get('goal')!r}"
        assert (
            jny.get("context") == "Pre-screening visit"
        ), f"context wrapped in '**...**' must be unwrapped, got {jny.get('context')!r}"

    # Implements: REQ-d00246-B
    def test_REQ_d00246_B_journey_actor_plain_value_unchanged(self, resolver: IdResolver) -> None:
        """Plain (undecorated) values pass through unchanged."""
        content = """\
### JNY-001: Plain Actor
**Actor**: Plain Name
**Goal**: A simple goal

*End* *JNY-001*
"""
        results = _parse(content, resolver)
        jny = _first_journey(results)
        assert (
            jny.get("actor") == "Plain Name"
        ), f"Plain value must pass through unchanged, got {jny.get('actor')!r}"
        assert (
            jny.get("goal") == "A simple goal"
        ), f"Plain goal must pass through unchanged, got {jny.get('goal')!r}"

    # Implements: REQ-d00246-B
    def test_REQ_d00246_B_journey_actor_underscore_wrapped(self, resolver: IdResolver) -> None:
        """Underscore emphasis on the value (label is plain) is also stripped."""
        content = """\
### JNY-001: Underscored Value
Actor: __Bold User__
Goal: Plain goal

*End* *JNY-001*
"""
        results = _parse(content, resolver)
        jny = _first_journey(results)
        assert (
            jny.get("actor") == "Bold User"
        ), f"Value wrapped in '__...__' must be unwrapped, got {jny.get('actor')!r}"

    # Implements: REQ-d00246-B
    def test_REQ_d00246_B_journey_actor_unbalanced_value_intact(self, resolver: IdResolver) -> None:
        """Unbalanced wrappers on the value are NOT stripped."""
        content = """\
### JNY-001: Asymmetric Wrapper
**Actor**: *Sarah**

*End* *JNY-001*
"""
        results = _parse(content, resolver)
        jny = _first_journey(results)
        assert jny.get("actor") == "*Sarah**", (
            f"Asymmetric '*Sarah**' value must pass through unchanged "
            f"(balanced strip semantics), got {jny.get('actor')!r}"
        )


# ---------------------------------------------------------------------------
# C. `reference term` / `reference source` field normalization.
# ---------------------------------------------------------------------------


class TestReferenceTermSourceEmphasis:
    """Validates REQ-d00246-B: reference_term/reference_source use strip_emphasis()."""

    @pytest.mark.parametrize(
        "decorated,expected",
        [
            ("**ISO 9001**", "ISO 9001"),
            ("__ISO 9001__", "ISO 9001"),
            ("*ISO 9001*", "ISO 9001"),
            ("ISO 9001", "ISO 9001"),
        ],
    )
    # Implements: REQ-d00246-B
    def test_REQ_d00246_B_reference_term_emphasis_stripped(
        self, resolver: IdResolver, decorated: str, expected: str
    ) -> None:
        content = f"""\
# REQ-p00001: Reference Term Wrapper Test
**Level**: prd | **Status**: Active

ACME Standard
: A widely-used industry standard.
: Reference Term: {decorated}

## Assertions

A. First assertion

*End* *REQ-p00001* **Hash**: abcd1234
"""
        results = _parse(content, resolver)
        def_data = _first_definition(results)
        assert def_data.get("reference_term") == expected, (
            f"Decorated reference_term {decorated!r} should normalize to "
            f"{expected!r}, got {def_data.get('reference_term')!r}"
        )

    @pytest.mark.parametrize(
        "decorated,expected",
        [
            ("**ANSI**", "ANSI"),
            ("__ANSI__", "ANSI"),
            ("*ANSI*", "ANSI"),
        ],
    )
    # Implements: REQ-d00246-B
    def test_REQ_d00246_B_reference_source_emphasis_stripped(
        self, resolver: IdResolver, decorated: str, expected: str
    ) -> None:
        content = f"""\
# REQ-p00001: Reference Source Wrapper Test
**Level**: prd | **Status**: Active

ACME Standard
: A widely-used industry standard.
: Reference Source: {decorated}

## Assertions

A. First assertion

*End* *REQ-p00001* **Hash**: abcd1234
"""
        results = _parse(content, resolver)
        def_data = _first_definition(results)
        assert def_data.get("reference_source") == expected, (
            f"Decorated reference_source {decorated!r} should normalize to "
            f"{expected!r}, got {def_data.get('reference_source')!r}"
        )

    # Implements: REQ-d00246-B
    def test_REQ_d00246_B_reference_term_unbalanced_intact(self, resolver: IdResolver) -> None:
        """Unbalanced `*ISO_9001_` would have been wrongly stripped by the
        old `.strip("_").strip("*")` logic. New behavior: leave it alone."""
        content = """\
# REQ-p00001: Asymmetric Reference Term
**Level**: prd | **Status**: Active

ACME Standard
: A widely-used industry standard.
: Reference Term: *ISO_9001_

## Assertions

A. First assertion

*End* *REQ-p00001* **Hash**: abcd1234
"""
        results = _parse(content, resolver)
        def_data = _first_definition(results)
        assert def_data.get("reference_term") == "*ISO_9001_", (
            f"Unbalanced '*ISO_9001_' must pass through unchanged "
            f"(balanced strip semantics), got {def_data.get('reference_term')!r}"
        )


# ---------------------------------------------------------------------------
# D. Static lint/AST guard against ad-hoc strip("*") / strip("_") calls.
# ---------------------------------------------------------------------------


_TRANSFORMER_DIR = (
    Path(__file__).resolve().parents[3]
    / "src"
    / "elspais"
    / "graph"
    / "parsers"
    / "lark"
    / "transformers"
)


class TestNoAdHocStripCalls:
    """Validates REQ-d00246-B: no per-character strip("*"|"_") in transformers."""

    @pytest.mark.parametrize(
        "transformer_file",
        sorted(_TRANSFORMER_DIR.glob("*.py")),
        ids=lambda p: p.name,
    )
    # Implements: REQ-d00246-B
    def test_REQ_d00246_B_no_ad_hoc_emphasis_strip(self, transformer_file: Path) -> None:
        """`.strip("*")`, `.strip('_')`, and similar variants must not appear.

        Catches any future regression that reintroduces ad-hoc emphasis
        stripping, bypassing the canonical `strip_emphasis()` helper.
        """
        text = transformer_file.read_text(encoding="utf-8")
        # Match .strip("*"), .strip('*'), .strip("_"), .strip('_'),
        # plus combined-character variants like .strip("*_") / .strip("_*").
        pattern = re.compile(r"""\.strip\(\s*['"][*_]+['"]\s*\)""")
        matches = []
        for lineno, line in enumerate(text.splitlines(), start=1):
            if pattern.search(line):
                matches.append((lineno, line.strip()))
        assert not matches, (
            f"Found ad-hoc emphasis strip calls in {transformer_file.name} -- "
            f"use strip_emphasis() from elspais.utilities.markdown instead. "
            f"Offending lines: {matches}"
        )
