# Verifies: REQ-d00250-A
# Verifies: REQ-d00131-B
"""Behavior tests for shared parser regex patterns.

Phase 2 of the DRY refactor consolidates the regex patterns that today are
inlined across journey.py, the Lark transformers, hasher.py, and other
modules into ``src/elspais/graph/parsers/patterns.py``. These tests pin
down the externally observable behavior of those patterns so future edits
cannot silently broaden, narrow, or break recognition.

The tests deliberately do not import from journey.py / reference.py /
hasher.py -- they exercise only the public symbols of ``patterns.py``.
"""

from __future__ import annotations

import re

import pytest

from elspais.graph.parsers import patterns

# ---------------------------------------------------------------------------
# JNY_ID_PATTERN -- matches a bare JNY-<slug> identifier (case-insensitive)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "JNY-checkout-001",
        "JNY-x-1",
        "JNY-FOO-99",
        "jny-foo-99",  # lowercase
        "Jny-Mixed-Case-7",  # mixed case
        "JNY-multi-part-slug-12",
    ],
)
def test_jny_id_pattern_accepts_valid_ids(text: str) -> None:
    m = patterns.JNY_ID_PATTERN.search(text)
    assert m is not None, f"expected match for {text!r}"
    # The match should cover the whole token (anchored start) -- the pattern
    # may be used as either match() or search(), so check span via fullmatch.
    assert patterns.JNY_ID_PATTERN.fullmatch(text) is not None


@pytest.mark.parametrize(
    "text",
    [
        "REQ-d00001",
        "REQ-p00050",
        "checkout",
        "",
        "JNY",  # no slug
        "JNY-",  # empty slug
    ],
)
def test_jny_id_pattern_rejects_non_journey_tokens(text: str) -> None:
    assert patterns.JNY_ID_PATTERN.fullmatch(text) is None


# ---------------------------------------------------------------------------
# JNY_ID_LINE_PATTERN -- matches a markdown header line ``## JNY-x: Title``
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "line, expected_id, expected_title",
    [
        ("## JNY-checkout-001: Checkout flow", "JNY-checkout-001", "Checkout flow"),
        ("# JNY-x-1: Bare top-level", "JNY-x-1", "Bare top-level"),
        ("### JNY-deep-3: Deeply nested", "JNY-deep-3", "Deeply nested"),
        ("JNY-noheader-1: No hash prefix", "JNY-noheader-1", "No hash prefix"),
    ],
)
def test_jny_id_line_pattern_extracts_id_and_title(
    line: str, expected_id: str, expected_title: str
) -> None:
    m = patterns.JNY_ID_LINE_PATTERN.match(line)
    assert m is not None, f"expected match for {line!r}"
    assert m.group("id") == expected_id
    assert m.group("title").strip() == expected_title


@pytest.mark.parametrize(
    "line",
    [
        "## REQ-d00001: not a journey",
        "Just prose with JNY-foo-1 inside",  # not a header line
        "## Some other heading",
        "",
    ],
)
def test_jny_id_line_pattern_rejects_non_journey_headers(line: str) -> None:
    assert patterns.JNY_ID_LINE_PATTERN.match(line) is None


# ---------------------------------------------------------------------------
# JNY_END_PATTERN -- matches ``*End* *JNY-...*`` footer
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "line",
    [
        "*End* *JNY-checkout-001*",
        "*End* *JNY-x*",
        "*End* *JNY-multi-part-slug-7*",
    ],
)
def test_jny_end_pattern_accepts_journey_footers(line: str) -> None:
    assert patterns.JNY_END_PATTERN.match(line) is not None


@pytest.mark.parametrize(
    "line",
    [
        "*End* *REQ-d00001*",  # requirement footer, not journey
        "*End* *Some Title*",  # title-based footer
        "End JNY-x",  # missing asterisks
        "",
    ],
)
def test_jny_end_pattern_rejects_non_journey_footers(line: str) -> None:
    assert patterns.JNY_END_PATTERN.match(line) is None


# ---------------------------------------------------------------------------
# JNY_DESCRIPTOR_PATTERN -- captures the slug from ``JNY-<slug>-<digits>``
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text, expected_descriptor",
    [
        ("JNY-checkout-001", "checkout"),
        ("JNY-x-y-z-99", "x-y-z"),
        ("JNY-single-1", "single"),
        ("JNY-with-many-parts-42", "with-many-parts"),
    ],
)
def test_jny_descriptor_pattern_captures_slug(text: str, expected_descriptor: str) -> None:
    m = patterns.JNY_DESCRIPTOR_PATTERN.match(text)
    assert m is not None, f"expected match for {text!r}"
    # Whichever group name is used, the first group should be the descriptor.
    assert m.group(1) == expected_descriptor


@pytest.mark.parametrize(
    "text",
    [
        "JNY-no-trailing-digits",  # no trailing -<digits>
        "REQ-d00001-A",  # not a journey
        "JNY-",
        "",
        "JNY-x",  # missing -digits
    ],
)
def test_jny_descriptor_pattern_rejects_invalid(text: str) -> None:
    assert patterns.JNY_DESCRIPTOR_PATTERN.match(text) is None


# ---------------------------------------------------------------------------
# ACTOR_PATTERN / GOAL_PATTERN / VALIDATES_PATTERN -- journey metadata lines
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "pattern_name, line, expected_value",
    [
        ("ACTOR_PATTERN", "**Actor**: shopper", "shopper"),
        ("ACTOR_PATTERN", "**Actor**: admin user with role", "admin user with role"),
        ("GOAL_PATTERN", "**Goal**: complete purchase", "complete purchase"),
        ("VALIDATES_PATTERN", "Validates: REQ-d00001, REQ-d00002", "REQ-d00001, REQ-d00002"),
    ],
)
def test_journey_metadata_patterns_extract_value(
    pattern_name: str, line: str, expected_value: str
) -> None:
    pattern: re.Pattern[str] = getattr(patterns, pattern_name)
    m = pattern.search(line)
    assert m is not None, f"{pattern_name} did not match {line!r}"
    # The single named/anonymous capture group should hold the trailing value.
    captured = m.group(1) if m.lastindex else m.group(0)
    assert expected_value in captured


@pytest.mark.parametrize(
    "pattern_name, line",
    [
        ("ACTOR_PATTERN", "**Goal**: not an actor line"),
        ("ACTOR_PATTERN", "Actor: missing bold markers"),
        ("GOAL_PATTERN", "**Actor**: not a goal line"),
        ("VALIDATES_PATTERN", "**Validates**: bold-form is not the line form"),
        ("VALIDATES_PATTERN", "Implements: REQ-x"),
    ],
)
def test_journey_metadata_patterns_reject_unrelated(pattern_name: str, line: str) -> None:
    pattern: re.Pattern[str] = getattr(patterns, pattern_name)
    assert pattern.search(line) is None


# ---------------------------------------------------------------------------
# KEYWORD_PATTERN -- all FIVE edge keywords, case-insensitive
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "keyword",
    [
        "implements",
        "verifies",
        "refines",
        "validates",  # currently missing from the inlined regex -- documented bug
        "satisfies",  # currently missing from the inlined regex -- documented bug
        "Implements",
        "VERIFIES",
        "ReFiNeS",
        "Validates",
        "Satisfies",
    ],
)
def test_keyword_pattern_accepts_all_five_edge_keywords(keyword: str) -> None:
    assert patterns.KEYWORD_PATTERN.search(keyword) is not None


@pytest.mark.parametrize(
    "text",
    [
        "implies",
        "verifying",  # not exactly one of the five forms
        "satisfaction",
        "validation",  # not "validates"
        "refine",  # singular form
        "",
        "random words",
    ],
)
def test_keyword_pattern_rejects_unrelated_words(text: str) -> None:
    # We use fullmatch to avoid false-positive substring hits from words like
    # "refined" or "implementation" -- the pattern is allowed to match those
    # as substrings (current inline behavior), but it MUST NOT fullmatch them.
    assert patterns.KEYWORD_PATTERN.fullmatch(text) is None


# ---------------------------------------------------------------------------
# CHANGELOG_HEADER_PATTERN -- depth-2 ATX ``## Changelog`` line
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "line",
    [
        "## Changelog",
        "## Changelog   ",  # trailing whitespace
        "## Changelog\t",  # trailing tab
    ],
)
def test_changelog_header_pattern_accepts_depth2(line: str) -> None:
    # Patterns currently use re.MULTILINE + ^...$ anchors -- search is the
    # contract used by hasher.py.
    assert patterns.CHANGELOG_HEADER_PATTERN.search(line) is not None


@pytest.mark.parametrize(
    "line",
    [
        "### Changelog",  # depth 3
        "# Changelog",  # depth 1
        "## changelog",  # case-sensitive (matches current inline behavior)
        "## Changelogs",  # plural / extra suffix
        "## Changelog entries",  # trailing words
        "",
    ],
)
def test_changelog_header_pattern_rejects_other_forms(line: str) -> None:
    assert patterns.CHANGELOG_HEADER_PATTERN.search(line) is None


# ---------------------------------------------------------------------------
# build_multi_assertion_pattern(prefix, multi_sep)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "prefix, multi_sep, text, should_match",
    [
        # ("REQ", "+") -- the default config
        ("REQ", "+", "REQ-d00001-A", True),
        ("REQ", "+", "REQ-d00001-A+B+C", True),
        ("REQ", "+", "REQ-d00001-A+B+C+D+E", True),
        ("REQ", "+", "PRD-001-A", False),  # wrong prefix
        ("REQ", "+", "REQ-d00001-A,B", False),  # wrong separator
        # ("PRD", "+") -- FDA-style prefix
        ("PRD", "+", "PRD-001-A+B", True),
        ("PRD", "+", "REQ-d00001-A+B", False),
        # ("REQ", ",") -- alternate separator
        ("REQ", ",", "REQ-d00001-A,B", True),
        ("REQ", ",", "REQ-d00001-A+B", False),
    ],
)
def test_build_multi_assertion_pattern_matches_per_config(
    prefix: str, multi_sep: str, text: str, should_match: bool
) -> None:
    pattern = patterns.build_multi_assertion_pattern(prefix, multi_sep)
    match = pattern.search(text)
    if should_match:
        assert match is not None, f"expected match for {text!r} with sep={multi_sep!r}"
        # The full token should be captured (not just a prefix).
        assert match.group(0) == text
    else:
        # Either no match at all, or the match must NOT span the full text.
        assert match is None or match.group(0) != text


def test_build_multi_assertion_pattern_treats_separator_as_literal() -> None:
    """The separator must not be interpreted as a regex metacharacter."""
    # "." would mean "any char" if not escaped -- here we want a literal dot.
    pattern = patterns.build_multi_assertion_pattern("REQ", ".")
    # Literal "." separator: REQ-x.A.B is a valid 3-assertion reference.
    m = pattern.search("REQ-x.A.B")
    assert m is not None
    assert m.group(0) == "REQ-x.A.B"
    # The "+" form should NOT match (separator is now ".", not "+").
    m_plus = pattern.search("REQ-x+A.B")
    # The "REQ-x" prefix may still match as a 0-assertion suffix, but the
    # full "REQ-x+A.B" token must not.
    assert m_plus is None or m_plus.group(0) != "REQ-x+A.B"


def test_build_multi_assertion_pattern_is_case_insensitive() -> None:
    """Multi-assertion matching must be case-insensitive (matches inline behavior)."""
    pattern = patterns.build_multi_assertion_pattern("REQ", "+")
    assert pattern.search("req-d00001-a+b") is not None
    assert pattern.search("Req-D00001-A+B") is not None
