# Validates REQ-d00061-B, REQ-d00061-C, REQ-p00050-D
"""Tests for _matches_query() helper function.

Validates REQ-d00061-B, REQ-d00061-C, REQ-p00050-D:
- REQ-d00061-B: Supports field parameter (id, title, body, keywords, all).
- REQ-d00061-C: Supports regex=True for regex matching.
- REQ-p00050-D: Single code path for query matching.
"""

import re

import pytest

from elspais.graph import GraphNode, NodeKind

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def match_node():
    """Create a GraphNode with id, label, body_text, and keywords fields."""
    node = GraphNode(
        id="REQ-d00099",
        kind=NodeKind.REQUIREMENT,
        label="Platform Security Overview",
    )
    node._content = {
        "level": "DEV",
        "status": "Active",
        "hash": "aaa11111",
        "body_text": "All data must be encrypted at rest using AES-256.",
        "keywords": ["encryption", "security", "AES"],
    }
    return node


@pytest.fixture
def empty_node():
    """Create a GraphNode with no body_text and no keywords."""
    node = GraphNode(
        id="REQ-p00077",
        kind=NodeKind.REQUIREMENT,
        label="Empty Requirement",
    )
    node._content = {
        "level": "PRD",
        "status": "Draft",
        "hash": "bbb22222",
    }
    return node


@pytest.fixture
def _matches_query():
    """Import and return the _matches_query function."""
    pytest.importorskip("mcp")
    from elspais.mcp.server import _matches_query

    return _matches_query


# ─────────────────────────────────────────────────────────────────────────────
# Test: field="id" matching - REQ-d00061-B
# ─────────────────────────────────────────────────────────────────────────────


class TestFieldIdMatch:
    """Tests for field='id' matching.

    Validates REQ-d00061-B, REQ-d00061-C, REQ-p00050-D:
    """

    def test_REQ_d00061_B_field_id_match_substring(self, _matches_query, match_node):
        """REQ-d00061-B: field='id' matches substring in node.id."""
        assert _matches_query(
            match_node,
            field="id",
            regex=False,
            compiled_pattern=None,
            query_lower="d00099",
        )

    def test_REQ_d00061_B_field_id_no_match(self, _matches_query, match_node):
        """REQ-d00061-B: field='id' returns False when no substring match."""
        assert not _matches_query(
            match_node,
            field="id",
            regex=False,
            compiled_pattern=None,
            query_lower="zzz",
        )

    def test_REQ_d00061_B_field_id_case_insensitive(self, _matches_query, match_node):
        """REQ-d00061-B: field='id' matching is case-insensitive."""
        assert _matches_query(
            match_node,
            field="id",
            regex=False,
            compiled_pattern=None,
            query_lower="req-d00099",
        )

    def test_REQ_d00061_C_field_id_regex_match(self, _matches_query, match_node):
        """REQ-d00061-C: field='id' with regex=True uses compiled_pattern."""
        pattern = re.compile(r"REQ-d000\d+")
        assert _matches_query(
            match_node,
            field="id",
            regex=True,
            compiled_pattern=pattern,
            query_lower=None,
        )

    def test_REQ_d00061_C_field_id_regex_no_match(self, _matches_query, match_node):
        """REQ-d00061-C: field='id' with regex=True returns False on no match."""
        pattern = re.compile(r"REQ-p\d+")
        assert not _matches_query(
            match_node,
            field="id",
            regex=True,
            compiled_pattern=pattern,
            query_lower=None,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Test: field="title" matching - REQ-d00061-B
# ─────────────────────────────────────────────────────────────────────────────


class TestFieldTitleMatch:
    """Tests for field='title' matching.

    Validates REQ-d00061-B, REQ-d00061-C, REQ-p00050-D:
    """

    def test_REQ_d00061_B_field_title_match_substring(self, _matches_query, match_node):
        """REQ-d00061-B: field='title' matches substring in node.get_label()."""
        assert _matches_query(
            match_node,
            field="title",
            regex=False,
            compiled_pattern=None,
            query_lower="security",
        )

    def test_REQ_d00061_B_field_title_no_match(self, _matches_query, match_node):
        """REQ-d00061-B: field='title' returns False when no substring match."""
        assert not _matches_query(
            match_node,
            field="title",
            regex=False,
            compiled_pattern=None,
            query_lower="database",
        )

    def test_REQ_d00061_B_field_title_case_insensitive(self, _matches_query, match_node):
        """REQ-d00061-B: field='title' matching is case-insensitive."""
        assert _matches_query(
            match_node,
            field="title",
            regex=False,
            compiled_pattern=None,
            query_lower="platform security",
        )

    def test_REQ_d00061_C_field_title_regex_match(self, _matches_query, match_node):
        """REQ-d00061-C: field='title' with regex=True uses compiled_pattern."""
        pattern = re.compile(r"Platform\s+Security")
        assert _matches_query(
            match_node,
            field="title",
            regex=True,
            compiled_pattern=pattern,
            query_lower=None,
        )

    def test_REQ_d00061_C_field_title_regex_no_match(self, _matches_query, match_node):
        """REQ-d00061-C: field='title' regex returns False on no match."""
        pattern = re.compile(r"^Database")
        assert not _matches_query(
            match_node,
            field="title",
            regex=True,
            compiled_pattern=pattern,
            query_lower=None,
        )

    def test_REQ_d00061_B_field_title_empty_label(self, _matches_query, empty_node):
        """REQ-d00061-B: field='title' handles node with empty label gracefully."""
        empty_node.set_label("")
        assert not _matches_query(
            empty_node,
            field="title",
            regex=False,
            compiled_pattern=None,
            query_lower="anything",
        )


# ─────────────────────────────────────────────────────────────────────────────
# Test: field="body" matching - REQ-d00061-B
# ─────────────────────────────────────────────────────────────────────────────


class TestFieldBodyMatch:
    """Tests for field='body' matching.

    Validates REQ-d00061-B, REQ-d00061-C, REQ-p00050-D:
    """

    def test_REQ_d00061_B_field_body_match_substring(self, _matches_query, match_node):
        """REQ-d00061-B: field='body' matches substring in body_text."""
        assert _matches_query(
            match_node,
            field="body",
            regex=False,
            compiled_pattern=None,
            query_lower="encrypted",
        )

    def test_REQ_d00061_B_field_body_no_match(self, _matches_query, match_node):
        """REQ-d00061-B: field='body' returns False when no substring match."""
        assert not _matches_query(
            match_node,
            field="body",
            regex=False,
            compiled_pattern=None,
            query_lower="database",
        )

    def test_REQ_d00061_B_field_body_case_insensitive(self, _matches_query, match_node):
        """REQ-d00061-B: field='body' matching is case-insensitive."""
        assert _matches_query(
            match_node,
            field="body",
            regex=False,
            compiled_pattern=None,
            query_lower="aes-256",
        )

    def test_REQ_d00061_C_field_body_regex_match(self, _matches_query, match_node):
        """REQ-d00061-C: field='body' with regex=True uses compiled_pattern."""
        pattern = re.compile(r"AES-\d+")
        assert _matches_query(
            match_node,
            field="body",
            regex=True,
            compiled_pattern=pattern,
            query_lower=None,
        )

    def test_REQ_d00061_C_field_body_regex_no_match(self, _matches_query, match_node):
        """REQ-d00061-C: field='body' regex returns False on no match."""
        pattern = re.compile(r"RSA-\d+")
        assert not _matches_query(
            match_node,
            field="body",
            regex=True,
            compiled_pattern=pattern,
            query_lower=None,
        )

    def test_REQ_d00061_B_field_body_empty(self, _matches_query, empty_node):
        """REQ-d00061-B: field='body' returns False when body_text is absent."""
        assert not _matches_query(
            empty_node,
            field="body",
            regex=False,
            compiled_pattern=None,
            query_lower="anything",
        )

    def test_REQ_d00061_C_field_body_regex_empty(self, _matches_query, empty_node):
        """REQ-d00061-C: field='body' with regex returns False when body_text is absent."""
        pattern = re.compile(r".*")
        assert not _matches_query(
            empty_node,
            field="body",
            regex=True,
            compiled_pattern=pattern,
            query_lower=None,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Test: field="keywords" matching - REQ-d00061-B
# ─────────────────────────────────────────────────────────────────────────────


class TestFieldKeywordsMatch:
    """Tests for field='keywords' matching.

    Validates REQ-d00061-B, REQ-d00061-C, REQ-p00050-D:
    """

    def test_REQ_d00061_B_field_keywords_match_substring(self, _matches_query, match_node):
        """REQ-d00061-B: field='keywords' matches substring in keyword list."""
        assert _matches_query(
            match_node,
            field="keywords",
            regex=False,
            compiled_pattern=None,
            query_lower="encrypt",
        )

    def test_REQ_d00061_B_field_keywords_exact_match(self, _matches_query, match_node):
        """REQ-d00061-B: field='keywords' matches exact keyword."""
        assert _matches_query(
            match_node,
            field="keywords",
            regex=False,
            compiled_pattern=None,
            query_lower="security",
        )

    def test_REQ_d00061_B_field_keywords_no_match(self, _matches_query, match_node):
        """REQ-d00061-B: field='keywords' returns False when no keyword matches."""
        assert not _matches_query(
            match_node,
            field="keywords",
            regex=False,
            compiled_pattern=None,
            query_lower="database",
        )

    def test_REQ_d00061_B_field_keywords_case_insensitive(self, _matches_query, match_node):
        """REQ-d00061-B: field='keywords' matching is case-insensitive."""
        assert _matches_query(
            match_node,
            field="keywords",
            regex=False,
            compiled_pattern=None,
            query_lower="aes",
        )

    def test_REQ_d00061_C_field_keywords_regex_match(self, _matches_query, match_node):
        """REQ-d00061-C: field='keywords' with regex=True uses compiled_pattern."""
        pattern = re.compile(r"^secur")
        assert _matches_query(
            match_node,
            field="keywords",
            regex=True,
            compiled_pattern=pattern,
            query_lower=None,
        )

    def test_REQ_d00061_C_field_keywords_regex_no_match(self, _matches_query, match_node):
        """REQ-d00061-C: field='keywords' regex returns False on no match."""
        pattern = re.compile(r"^zzz")
        assert not _matches_query(
            match_node,
            field="keywords",
            regex=True,
            compiled_pattern=pattern,
            query_lower=None,
        )

    def test_REQ_d00061_B_field_keywords_empty(self, _matches_query, empty_node):
        """REQ-d00061-B: field='keywords' returns False when keywords absent."""
        assert not _matches_query(
            empty_node,
            field="keywords",
            regex=False,
            compiled_pattern=None,
            query_lower="anything",
        )


# ─────────────────────────────────────────────────────────────────────────────
# Test: field="all" matching - REQ-d00061-B
# ─────────────────────────────────────────────────────────────────────────────


class TestFieldAllMatch:
    """Tests for field='all' matching across all fields.

    Validates REQ-d00061-B, REQ-d00061-C, REQ-p00050-D:
    """

    def test_REQ_d00061_B_field_all_matches_id(self, _matches_query, match_node):
        """REQ-d00061-B: field='all' matches against node.id."""
        assert _matches_query(
            match_node,
            field="all",
            regex=False,
            compiled_pattern=None,
            query_lower="d00099",
        )

    def test_REQ_d00061_B_field_all_matches_title(self, _matches_query, match_node):
        """REQ-d00061-B: field='all' matches against node label (title)."""
        assert _matches_query(
            match_node,
            field="all",
            regex=False,
            compiled_pattern=None,
            query_lower="overview",
        )

    def test_REQ_d00061_B_field_all_matches_body(self, _matches_query, match_node):
        """REQ-d00061-B: field='all' matches against body_text."""
        assert _matches_query(
            match_node,
            field="all",
            regex=False,
            compiled_pattern=None,
            query_lower="encrypted",
        )

    def test_REQ_d00061_B_field_all_matches_keywords(self, _matches_query, match_node):
        """REQ-d00061-B: field='all' matches against keywords."""
        assert _matches_query(
            match_node,
            field="all",
            regex=False,
            compiled_pattern=None,
            query_lower="encryption",
        )

    def test_REQ_d00061_B_field_all_no_match(self, _matches_query, match_node):
        """REQ-d00061-B: field='all' returns False when no field matches."""
        assert not _matches_query(
            match_node,
            field="all",
            regex=False,
            compiled_pattern=None,
            query_lower="zzzznotfound",
        )

    def test_REQ_d00061_C_field_all_regex_matches_id(self, _matches_query, match_node):
        """REQ-d00061-C: field='all' with regex matches node.id."""
        pattern = re.compile(r"REQ-d\d{5}")
        assert _matches_query(
            match_node,
            field="all",
            regex=True,
            compiled_pattern=pattern,
            query_lower=None,
        )

    def test_REQ_d00061_C_field_all_regex_matches_title(self, _matches_query, match_node):
        """REQ-d00061-C: field='all' with regex matches title."""
        pattern = re.compile(r"Platform\s+\w+")
        assert _matches_query(
            match_node,
            field="all",
            regex=True,
            compiled_pattern=pattern,
            query_lower=None,
        )

    def test_REQ_d00061_C_field_all_regex_matches_body(self, _matches_query, match_node):
        """REQ-d00061-C: field='all' with regex matches body_text."""
        pattern = re.compile(r"AES-\d+")
        assert _matches_query(
            match_node,
            field="all",
            regex=True,
            compiled_pattern=pattern,
            query_lower=None,
        )

    def test_REQ_d00061_C_field_all_regex_matches_keywords(self, _matches_query, match_node):
        """REQ-d00061-C: field='all' with regex matches keywords."""
        pattern = re.compile(r"^encrypt")
        assert _matches_query(
            match_node,
            field="all",
            regex=True,
            compiled_pattern=pattern,
            query_lower=None,
        )

    def test_REQ_d00061_C_field_all_regex_no_match(self, _matches_query, match_node):
        """REQ-d00061-C: field='all' with regex returns False on no match."""
        pattern = re.compile(r"^NONEXISTENT$")
        assert not _matches_query(
            match_node,
            field="all",
            regex=True,
            compiled_pattern=pattern,
            query_lower=None,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Test: single code path - REQ-p00050-D
# ─────────────────────────────────────────────────────────────────────────────


class TestSingleCodePath:
    """Tests confirming _matches_query is a single reusable code path.

    Validates REQ-d00061-B, REQ-d00061-C, REQ-p00050-D:
    """

    def test_REQ_p00050_D_returns_bool(self, _matches_query, match_node):
        """REQ-p00050-D: _matches_query returns a bool."""
        result = _matches_query(
            match_node,
            field="id",
            regex=False,
            compiled_pattern=None,
            query_lower="d00099",
        )
        assert isinstance(result, bool)

    def test_REQ_p00050_D_false_for_unrecognized_field(self, _matches_query, match_node):
        """REQ-p00050-D: unrecognized field returns False (no crash)."""
        result = _matches_query(
            match_node,
            field="unknown_field",
            regex=False,
            compiled_pattern=None,
            query_lower="d00099",
        )
        assert result is False

    def test_REQ_p00050_D_field_id_does_not_match_title(self, _matches_query, match_node):
        """REQ-p00050-D: field='id' only checks id, not title."""
        # "Security" is in the title but not the id
        assert not _matches_query(
            match_node,
            field="id",
            regex=False,
            compiled_pattern=None,
            query_lower="security overview",
        )

    def test_REQ_p00050_D_field_title_does_not_match_body(self, _matches_query, match_node):
        """REQ-p00050-D: field='title' only checks title, not body."""
        # "encrypted" is in the body but not the title
        assert not _matches_query(
            match_node,
            field="title",
            regex=False,
            compiled_pattern=None,
            query_lower="encrypted",
        )

    def test_REQ_p00050_D_field_body_does_not_match_keywords(self, _matches_query, match_node):
        """REQ-p00050-D: field='body' only checks body, not keywords."""
        # "encryption" is a keyword but not in the body_text
        assert not _matches_query(
            match_node,
            field="body",
            regex=False,
            compiled_pattern=None,
            query_lower="encryption",
        )

    def test_REQ_p00050_D_field_keywords_does_not_match_id(self, _matches_query, match_node):
        """REQ-p00050-D: field='keywords' only checks keywords, not id."""
        # "REQ-d00099" is the id but not a keyword
        assert not _matches_query(
            match_node,
            field="keywords",
            regex=False,
            compiled_pattern=None,
            query_lower="req-d00099",
        )
