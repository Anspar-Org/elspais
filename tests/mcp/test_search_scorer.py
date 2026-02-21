# Validates REQ-d00061-L, REQ-d00061-M
"""Tests for score_node() and matches_node() scoring functions.

Validates REQ-d00061-L, REQ-d00061-M:
- REQ-d00061-L: Score results by field match quality (ID > title > keyword > body).
- REQ-d00061-M: Include score field in search results.
"""

from __future__ import annotations

from elspais.graph import NodeKind
from elspais.graph.GraphNode import GraphNode
from elspais.mcp.search import (
    ParsedQuery,
    SearchTerm,
    matches_node,
    score_node,
)

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _make_node(
    node_id: str = "REQ-d00099",
    title: str = "Test Requirement",
    body: str = "",
    keywords: list[str] | None = None,
) -> GraphNode:
    """Create a GraphNode for testing with optional body and keywords."""
    node = GraphNode(node_id, NodeKind.REQUIREMENT, title)
    if body:
        node.set_field("body_text", body)
    if keywords:
        node.set_field("keywords", keywords)
    return node


def _simple_query(*terms: str) -> ParsedQuery:
    """Build a ParsedQuery with one AND-group per term (all substring, no negation)."""
    and_groups = tuple((SearchTerm(text=t.lower(), exact=False, negated=False),) for t in terms)
    return ParsedQuery(and_groups=and_groups, excluded=(), phrases=())


def _or_query(*terms: str) -> ParsedQuery:
    """Build a ParsedQuery with a single AND-group containing multiple OR terms."""
    or_group = tuple(SearchTerm(text=t.lower(), exact=False, negated=False) for t in terms)
    return ParsedQuery(and_groups=(or_group,), excluded=(), phrases=())


def _exclusion_query(term: str) -> ParsedQuery:
    """Build a ParsedQuery with a single exclusion term and no AND-groups."""
    return ParsedQuery(
        and_groups=(),
        excluded=(SearchTerm(text=term.lower(), exact=False, negated=True),),
        phrases=(),
    )


def _phrase_query(phrase: str) -> ParsedQuery:
    """Build a ParsedQuery with a single phrase and no AND-groups."""
    return ParsedQuery(and_groups=(), excluded=(), phrases=(phrase.lower(),))


def _exact_keyword_query(keyword: str) -> ParsedQuery:
    """Build a ParsedQuery with one AND-group containing one exact keyword term."""
    return ParsedQuery(
        and_groups=((SearchTerm(text=keyword.lower(), exact=True, negated=False),),),
        excluded=(),
        phrases=(),
    )


def _empty_query() -> ParsedQuery:
    """Build an empty ParsedQuery."""
    return ParsedQuery(and_groups=(), excluded=(), phrases=())


# ─────────────────────────────────────────────────────────────────────────────
# Test: Field weight hierarchy - REQ-d00061-L
# ─────────────────────────────────────────────────────────────────────────────


class TestFieldWeightHierarchy:
    """Tests that field matches produce correct weight scores.

    Validates REQ-d00061-L, REQ-d00061-M:
    ID match (100) > title match (50) > keyword exact (40) >
    keyword substring (25) > body match (10).
    """

    def test_REQ_d00061_L_id_match_scores_100(self):
        """REQ-d00061-L: A match in the node ID field produces a score of 100."""
        node = _make_node(node_id="REQ-d00099", title="Unrelated Title")
        query = _simple_query("d00099")
        assert score_node(node, query) == 100.0

    def test_REQ_d00061_L_title_match_scores_50(self):
        """REQ-d00061-L: A match in the title field produces a score of 50."""
        node = _make_node(node_id="REQ-x00001", title="Platform Security")
        query = _simple_query("security")
        assert score_node(node, query) == 50.0

    def test_REQ_d00061_L_keyword_exact_match_scores_40(self):
        """REQ-d00061-L: An exact keyword match (=prefix) produces a score of 40."""
        node = _make_node(
            node_id="REQ-x00001",
            title="Unrelated",
            keywords=["encryption"],
        )
        query = _exact_keyword_query("encryption")
        assert score_node(node, query) == 40.0

    def test_REQ_d00061_L_keyword_substring_match_scores_25(self):
        """REQ-d00061-L: A keyword substring match produces a score of 25."""
        node = _make_node(
            node_id="REQ-x00001",
            title="Unrelated",
            keywords=["encryption"],
        )
        query = _simple_query("encrypt")
        assert score_node(node, query) == 25.0

    def test_REQ_d00061_L_body_match_scores_10(self):
        """REQ-d00061-L: A match in the body field produces a score of 10."""
        node = _make_node(
            node_id="REQ-x00001",
            title="Unrelated",
            body="All data must be encrypted at rest using AES-256.",
        )
        query = _simple_query("aes-256")
        assert score_node(node, query) == 10.0

    def test_REQ_d00061_L_id_beats_title(self):
        """REQ-d00061-L: When term matches both ID and title, highest weight (ID=100) wins."""
        node = _make_node(node_id="REQ-security", title="security overview")
        query = _simple_query("security")
        assert score_node(node, query) == 100.0

    def test_REQ_d00061_L_title_beats_keyword(self):
        """REQ-d00061-L: When term matches both title and keyword, title weight (50) wins."""
        node = _make_node(
            node_id="REQ-x00001",
            title="Security Overview",
            keywords=["security"],
        )
        query = _simple_query("security")
        assert score_node(node, query) == 50.0

    def test_REQ_d00061_L_keyword_beats_body(self):
        """REQ-d00061-L: When term matches both keyword and body, keyword weight (25) wins."""
        node = _make_node(
            node_id="REQ-x00001",
            title="Unrelated",
            keywords=["validation"],
            body="validation is important",
        )
        query = _simple_query("validation")
        assert score_node(node, query) == 25.0


# ─────────────────────────────────────────────────────────────────────────────
# Test: Exclusion returns 0 - REQ-d00061-L
# ─────────────────────────────────────────────────────────────────────────────


class TestExclusionReturnsZero:
    """Tests that exclusion terms cause score to drop to zero.

    Validates REQ-d00061-L, REQ-d00061-M:
    """

    def test_REQ_d00061_L_exclusion_in_id_returns_zero(self):
        """REQ-d00061-L: Exclusion matching in ID returns score 0."""
        node = _make_node(node_id="REQ-d00099", title="Some Title")
        query = ParsedQuery(
            and_groups=((SearchTerm(text="d00099", exact=False, negated=False),),),
            excluded=(SearchTerm(text="d00099", exact=False, negated=True),),
            phrases=(),
        )
        assert score_node(node, query) == 0.0

    def test_REQ_d00061_L_exclusion_in_body_returns_zero(self):
        """REQ-d00061-L: Exclusion matching in body returns score 0."""
        node = _make_node(
            node_id="REQ-x00001",
            title="Title",
            body="contains deprecated content",
        )
        query = ParsedQuery(
            and_groups=((SearchTerm(text="title", exact=False, negated=False),),),
            excluded=(SearchTerm(text="deprecated", exact=False, negated=True),),
            phrases=(),
        )
        assert score_node(node, query) == 0.0

    def test_REQ_d00061_L_exclusion_only_no_match_returns_zero(self):
        """REQ-d00061-L: Exclusion-only query with no match still returns 0 (no positive terms)."""
        node = _make_node(node_id="REQ-x00001", title="Good Title")
        query = _exclusion_query("nonexistent")
        # No and_groups and no phrases -> is_empty-like but with excluded
        # Query has exclusions but no positive terms, score returns 0
        assert score_node(node, query) == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Test: Phrase missing returns 0 - REQ-d00061-L
# ─────────────────────────────────────────────────────────────────────────────


class TestPhraseMissingReturnsZero:
    """Tests that missing phrases cause score to drop to zero.

    Validates REQ-d00061-L, REQ-d00061-M:
    """

    def test_REQ_d00061_L_phrase_not_found_returns_zero(self):
        """REQ-d00061-L: When a required phrase is not in any field, score is 0."""
        node = _make_node(
            node_id="REQ-x00001",
            title="Platform Security",
            body="Data is encrypted.",
        )
        query = _phrase_query("missing phrase")
        assert score_node(node, query) == 0.0

    def test_REQ_d00061_L_phrase_found_returns_positive(self):
        """REQ-d00061-L: When a phrase is found, score is positive (1.0 for phrase-only)."""
        node = _make_node(
            node_id="REQ-x00001",
            title="Platform Security Overview",
            body="Data is encrypted.",
        )
        query = _phrase_query("platform security")
        assert score_node(node, query) == 1.0

    def test_REQ_d00061_L_phrase_and_term_both_must_match(self):
        """REQ-d00061-L: When phrase is missing but term matches, score is still 0."""
        node = _make_node(
            node_id="REQ-x00001",
            title="Platform Security",
            body="Data is encrypted.",
        )
        query = ParsedQuery(
            and_groups=((SearchTerm(text="platform", exact=False, negated=False),),),
            excluded=(),
            phrases=("nonexistent phrase",),
        )
        assert score_node(node, query) == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Test: AND-group not satisfied returns 0 - REQ-d00061-L
# ─────────────────────────────────────────────────────────────────────────────


class TestAndGroupNotSatisfied:
    """Tests that unmatched AND-groups cause score to be 0.

    Validates REQ-d00061-L, REQ-d00061-M:
    """

    def test_REQ_d00061_L_single_and_group_no_match(self):
        """REQ-d00061-L: A single AND-group with no match returns 0."""
        node = _make_node(node_id="REQ-x00001", title="Platform Security")
        query = _simple_query("nonexistent")
        assert score_node(node, query) == 0.0

    def test_REQ_d00061_L_one_and_group_fails_returns_zero(self):
        """REQ-d00061-L: If any AND-group has no match, total score is 0."""
        node = _make_node(node_id="REQ-x00001", title="Platform Security")
        query = _simple_query("platform", "nonexistent")
        assert score_node(node, query) == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Test: Multiple AND-groups sum scores - REQ-d00061-L
# ─────────────────────────────────────────────────────────────────────────────


class TestMultipleAndGroupsSum:
    """Tests that scores from multiple AND-groups are summed.

    Validates REQ-d00061-L, REQ-d00061-M:
    """

    def test_REQ_d00061_L_two_and_groups_sum(self):
        """REQ-d00061-L: Two AND-groups each matching in title sum to 100."""
        node = _make_node(
            node_id="REQ-x00001",
            title="Platform Security Overview",
        )
        query = _simple_query("platform", "security")
        # Each term matches in title (50 each) -> 50 + 50 = 100
        assert score_node(node, query) == 100.0

    def test_REQ_d00061_L_and_groups_different_fields_sum(self):
        """REQ-d00061-L: AND-groups matching in different fields sum their weights."""
        node = _make_node(
            node_id="REQ-d00099",
            title="Unrelated Title",
            body="Some body content here.",
        )
        # "d00099" matches ID (100), "body" matches body (10) -> 110
        query = _simple_query("d00099", "body")
        assert score_node(node, query) == 110.0

    def test_REQ_d00061_L_three_and_groups_sum(self):
        """REQ-d00061-L: Three matching AND-groups produce correct sum."""
        node = _make_node(
            node_id="REQ-d00099",
            title="Platform Security",
            body="encrypted data",
        )
        # "d00099" -> ID=100, "platform" -> title=50, "encrypted" -> body=10
        query = _simple_query("d00099", "platform", "encrypted")
        assert score_node(node, query) == 160.0


# ─────────────────────────────────────────────────────────────────────────────
# Test: OR-group picks best score - REQ-d00061-L
# ─────────────────────────────────────────────────────────────────────────────


class TestOrGroupBestScore:
    """Tests that OR-groups return the best (highest) score among alternatives.

    Validates REQ-d00061-L, REQ-d00061-M:
    """

    def test_REQ_d00061_L_or_group_picks_best(self):
        """REQ-d00061-L: OR-group returns the highest score among matching terms."""
        node = _make_node(
            node_id="REQ-x00001",
            title="Platform Security",
            body="encryption is used",
        )
        # OR group: "platform" matches title (50), "encryption" matches body (10)
        # Best is 50
        query = _or_query("platform", "encryption")
        assert score_node(node, query) == 50.0

    def test_REQ_d00061_L_or_group_one_matches(self):
        """REQ-d00061-L: OR-group with only one matching term uses that score."""
        node = _make_node(
            node_id="REQ-x00001",
            title="Platform Security",
        )
        # OR group: "platform" matches title (50), "nonexistent" matches nothing (0)
        query = _or_query("platform", "nonexistent")
        assert score_node(node, query) == 50.0

    def test_REQ_d00061_L_or_group_none_match_returns_zero(self):
        """REQ-d00061-L: OR-group where no term matches returns 0."""
        node = _make_node(node_id="REQ-x00001", title="Platform")
        query = _or_query("nonexistent", "alsonot")
        assert score_node(node, query) == 0.0

    def test_REQ_d00061_L_or_group_prefers_id_over_body(self):
        """REQ-d00061-L: OR-group with ID match and body match picks ID (100)."""
        node = _make_node(
            node_id="REQ-security",
            title="Unrelated",
            body="security concern",
        )
        # Both "security" terms would match, but the OR-group contains them
        # as alternatives; each is scored independently. "security" matches
        # both ID (100) and body (10) -> best is 100.
        query = _or_query("security")
        assert score_node(node, query) == 100.0


# ─────────────────────────────────────────────────────────────────────────────
# Test: matches_node returns True/False - REQ-d00061-M
# ─────────────────────────────────────────────────────────────────────────────


class TestMatchesNode:
    """Tests that matches_node() correctly wraps score_node().

    Validates REQ-d00061-L, REQ-d00061-M:
    """

    def test_REQ_d00061_M_matches_node_true_on_positive_score(self):
        """REQ-d00061-M: matches_node returns True when score > 0."""
        node = _make_node(node_id="REQ-d00099", title="Test")
        query = _simple_query("d00099")
        assert matches_node(node, query) is True

    def test_REQ_d00061_M_matches_node_false_on_zero_score(self):
        """REQ-d00061-M: matches_node returns False when score == 0."""
        node = _make_node(node_id="REQ-x00001", title="Test")
        query = _simple_query("nonexistent")
        assert matches_node(node, query) is False

    def test_REQ_d00061_M_matches_node_false_on_exclusion(self):
        """REQ-d00061-M: matches_node returns False when exclusion kills score."""
        node = _make_node(node_id="REQ-d00099", title="Test")
        query = ParsedQuery(
            and_groups=((SearchTerm(text="d00099", exact=False, negated=False),),),
            excluded=(SearchTerm(text="d00099", exact=False, negated=True),),
            phrases=(),
        )
        assert matches_node(node, query) is False

    def test_REQ_d00061_M_matches_node_returns_bool_type(self):
        """REQ-d00061-M: matches_node always returns a bool, not a float."""
        node = _make_node(node_id="REQ-d00099", title="Test")
        query = _simple_query("d00099")
        result = matches_node(node, query)
        assert isinstance(result, bool)


# ─────────────────────────────────────────────────────────────────────────────
# Test: Field parameter restricts scoring - REQ-d00061-L
# ─────────────────────────────────────────────────────────────────────────────


class TestFieldParameterRestriction:
    """Tests that the field parameter restricts which fields are scored.

    Validates REQ-d00061-L, REQ-d00061-M:
    """

    def test_REQ_d00061_L_field_id_only_scores_id(self):
        """REQ-d00061-L: field='id' only scores against the ID field."""
        node = _make_node(
            node_id="REQ-security",
            title="security overview",
            body="security is important",
            keywords=["security"],
        )
        query = _simple_query("security")
        score = score_node(node, query, field="id")
        assert score == 100.0

    def test_REQ_d00061_L_field_id_misses_title_match(self):
        """REQ-d00061-L: field='id' does not score title matches."""
        node = _make_node(
            node_id="REQ-x00001",
            title="Platform Security",
        )
        query = _simple_query("security")
        assert score_node(node, query, field="id") == 0.0

    def test_REQ_d00061_L_field_title_only_scores_title(self):
        """REQ-d00061-L: field='title' only scores against the title field."""
        node = _make_node(
            node_id="REQ-security",
            title="Platform Security",
            body="security is important",
        )
        query = _simple_query("security")
        score = score_node(node, query, field="title")
        assert score == 50.0

    def test_REQ_d00061_L_field_title_misses_id_match(self):
        """REQ-d00061-L: field='title' does not score ID matches."""
        node = _make_node(node_id="REQ-d00099", title="Unrelated")
        query = _simple_query("d00099")
        assert score_node(node, query, field="title") == 0.0

    def test_REQ_d00061_L_field_keywords_only_scores_keywords(self):
        """REQ-d00061-L: field='keywords' only scores against keywords."""
        node = _make_node(
            node_id="REQ-x00001",
            title="Unrelated",
            keywords=["encryption"],
        )
        query = _simple_query("encrypt")
        score = score_node(node, query, field="keywords")
        assert score == 25.0

    def test_REQ_d00061_L_field_keywords_exact_only(self):
        """REQ-d00061-L: field='keywords' with exact term uses exact weight (40)."""
        node = _make_node(
            node_id="REQ-x00001",
            title="Unrelated",
            keywords=["encryption"],
        )
        query = _exact_keyword_query("encryption")
        score = score_node(node, query, field="keywords")
        assert score == 40.0

    def test_REQ_d00061_L_field_body_only_scores_body(self):
        """REQ-d00061-L: field='body' only scores against the body field."""
        node = _make_node(
            node_id="REQ-x00001",
            title="Unrelated",
            body="Data encrypted with AES.",
        )
        query = _simple_query("aes")
        score = score_node(node, query, field="body")
        assert score == 10.0

    def test_REQ_d00061_L_field_body_misses_title_match(self):
        """REQ-d00061-L: field='body' does not score title matches."""
        node = _make_node(
            node_id="REQ-x00001",
            title="AES Encryption",
            body="No mention here.",
        )
        query = _simple_query("aes")
        assert score_node(node, query, field="body") == 0.0

    def test_REQ_d00061_L_field_all_searches_every_field(self):
        """REQ-d00061-L: field='all' searches across all fields and picks best weight."""
        node = _make_node(
            node_id="REQ-x00001",
            title="Security Overview",
            body="encryption details",
            keywords=["security"],
        )
        # "security" is in title (50) and keywords (25) -> best is 50
        query = _simple_query("security")
        assert score_node(node, query, field="all") == 50.0


# ─────────────────────────────────────────────────────────────────────────────
# Test: Empty query returns 0 - REQ-d00061-L
# ─────────────────────────────────────────────────────────────────────────────


class TestEmptyQuery:
    """Tests that an empty query (is_empty=True) returns score 0.

    Validates REQ-d00061-L, REQ-d00061-M:
    """

    def test_REQ_d00061_L_empty_query_returns_zero(self):
        """REQ-d00061-L: An empty ParsedQuery returns score 0."""
        node = _make_node(node_id="REQ-d00099", title="Anything")
        query = _empty_query()
        assert query.is_empty is True
        assert score_node(node, query) == 0.0

    def test_REQ_d00061_M_empty_query_matches_node_false(self):
        """REQ-d00061-M: matches_node with empty query returns False."""
        node = _make_node(node_id="REQ-d00099", title="Anything")
        query = _empty_query()
        assert matches_node(node, query) is False
