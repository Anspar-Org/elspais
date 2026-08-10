# Verifies: REQ-d00250-A
# Verifies: REQ-d00131-B
# Verifies: REQ-d00081-D
"""Behavior tests for the shared parser regex patterns.

``src/elspais/graph/parsers/patterns.py`` holds the fixed patterns the
parsers share -- journey identifiers, journey metadata lines, edge
keywords, the changelog header. These tests pin the externally observable
behavior of those patterns so an edit cannot silently broaden, narrow, or
break recognition.

Identifier recognition is not among them: an identifier's shape comes from
the repository's own configuration, so it is derived by ``IdResolver``
rather than fixed here, and the last section exercises that surface.
"""

from __future__ import annotations

import re

import pytest

from elspais.graph.parsers import patterns
from elspais.utilities.patterns import build_resolver

# ---------------------------------------------------------------------------
# JNY_ID_PATTERN -- anchored, captures <descriptor> and <number>.
# Serves both "is this a valid journey ID?" (fullmatch) and "extract the
# descriptor slug" (match + named group) use cases.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text, expected_descriptor, expected_number",
    [
        ("JNY-checkout-001", "checkout", "001"),
        ("JNY-x-1", "x", "1"),
        ("JNY-FOO-99", "FOO", "99"),
        ("jny-foo-99", "foo", "99"),  # case-insensitive
        ("Jny-Mixed-Case-7", "Mixed-Case", "7"),  # mixed case + multi-segment descriptor
        ("JNY-multi-part-slug-12", "multi-part-slug", "12"),
        ("JNY-x-y-z-99", "x-y-z", "99"),
        ("JNY-with-many-parts-42", "with-many-parts", "42"),
    ],
)
def test_jny_id_pattern_accepts_and_captures(
    text: str, expected_descriptor: str, expected_number: str
) -> None:
    m = patterns.JNY_ID_PATTERN.fullmatch(text)
    assert m is not None, f"expected match for {text!r}"
    assert m.group("descriptor") == expected_descriptor
    assert m.group("number") == expected_number


@pytest.mark.parametrize(
    "text",
    [
        "REQ-d00001",
        "REQ-p00050",
        "checkout",
        "",
        "JNY",  # no slug
        "JNY-",  # empty slug
        "JNY-no-trailing-digits",  # missing -<number>
        "JNY-x",  # missing -<number>
        "Just prose with JNY-foo-1 inside",  # anchored: substring must not match
    ],
)
def test_jny_id_pattern_rejects_invalid(text: str) -> None:
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
# IdResolver.multi_assertion_reference_regex() -- an identifier plus its
# optional multi-assertion suffix, derived from the repository's identifier
# configuration by the one grammar authority.
# ---------------------------------------------------------------------------


def _config(
    *,
    namespace: str = "REQ",
    canonical: str = "{namespace}-{level.letter}{component}",
    component: dict | None = None,
    assertions: dict | None = None,
) -> dict:
    """A minimal configuration dictionary for ``build_resolver``."""
    return {
        "project": {"namespace": namespace},
        "levels": {
            "prd": {"rank": 1, "letter": "p"},
            "dev": {"rank": 2, "letter": "d"},
        },
        "id-patterns": {
            "canonical": canonical,
            "component": component or {"style": "numeric", "digits": 5},
            "assertions": assertions or {},
        },
    }


_FDA = _config(
    namespace="PRD",
    canonical="{namespace}-{component}",
    component={"style": "numeric", "digits": 3, "leading_zeros": True},
)


@pytest.mark.parametrize(
    "config, text, should_match",
    [
        # Default configuration: "REQ" namespace, "+" between labels.
        (_config(), "REQ-d00001-A", True),
        (_config(), "REQ-d00001-A+B+C", True),
        (_config(), "REQ-d00001-A+B+C+D+E", True),
        (_config(), "PRD-001-A", False),  # foreign namespace
        (_config(), "REQ-d00001-A,B", False),  # wrong multi-separator
        # FDA-style: a namespace-and-number identifier with no level letter.
        (_FDA, "PRD-001-A+B", True),
        (_FDA, "REQ-d00001-A+B", False),
        # Alternate multi-separator.
        (_config(assertions={"multi_separator": ","}), "REQ-d00001-A,B", True),
        (_config(assertions={"multi_separator": ","}), "REQ-d00001-A+B", False),
    ],
)
def test_multi_assertion_regex_matches_per_config(
    config: dict, text: str, should_match: bool
) -> None:
    """The regex answers for exactly the identifiers the configuration describes."""
    pattern = build_resolver(config).multi_assertion_reference_regex()
    match = pattern.search(text)
    if should_match:
        assert match is not None, f"expected match for {text!r}"
        # The full token must be captured, not truncated at the first label.
        assert match.group(0) == text
    else:
        assert match is None or match.group(0) != text


def test_multi_assertion_regex_treats_separator_as_literal() -> None:
    """A separator that is a regex metacharacter matches only itself."""
    # "." would mean "any char" if it reached the engine unescaped.
    pattern = build_resolver(
        _config(assertions={"multi_separator": "."})
    ).multi_assertion_reference_regex()
    m = pattern.search("REQ-d00001-A.B")
    assert m is not None
    assert m.group(0) == "REQ-d00001-A.B"
    # "+" is now an ordinary character with no role in the grammar.
    m_plus = pattern.search("REQ-d00001+A.B")
    assert m_plus is None or m_plus.group(0) != "REQ-d00001+A.B"


def test_multi_assertion_regex_is_case_insensitive_for_a_numeric_component() -> None:
    """A reference written in the wrong case is still recognised as a reference.

    Recognition is deliberately tolerant so a mis-cased reference is caught
    and normalised rather than read as prose. Nothing in a numeric-component
    identifier carries meaning through its case, so every part of it is
    case-insensitive.
    """
    pattern = build_resolver(_config()).multi_assertion_reference_regex()
    assert pattern.fullmatch("req-d00001-a+b") is not None
    assert pattern.fullmatch("Req-D00001-A+B") is not None


def test_multi_assertion_regex_keeps_a_case_style_component_case_sensitive() -> None:
    """A case-style component's case is what identifies it, so it is honoured.

    A ``kebab-case`` component is lowercase by definition; were it read
    case-insensitively it would swallow the uppercase assertion label that
    follows it and the reference would lose every label after the first.
    """
    pattern = build_resolver(
        _config(
            canonical="{namespace}-{level.letter}-{component}",
            component={"style": "kebab-case", "digits": 0, "leading_zeros": False},
        )
    ).multi_assertion_reference_regex()

    m = pattern.search("REQ-p-widget-A+C")
    assert m is not None
    assert m.group(0) == "REQ-p-widget-A+C"
    # An uppercase component is not a kebab-case component.
    assert pattern.fullmatch("REQ-p-Widget") is None


@pytest.mark.parametrize("empty_sep", [None, ""])
def test_multi_assertion_regex_defaults_empty_separator_to_plus(empty_sep) -> None:
    """An empty multi-separator falls back to "+" rather than dissolving.

    Without a separator between them, two labels run together into one
    token and a reference naming several assertions can no longer be told
    from a reference naming one.
    """
    pattern = build_resolver(
        _config(assertions={"multi_separator": empty_sep})
    ).multi_assertion_reference_regex()
    m = pattern.search("REQ-d00001-A+B")
    assert m is not None
    assert m.group(0) == "REQ-d00001-A+B"
