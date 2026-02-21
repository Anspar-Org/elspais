# Validates REQ-d00061-B, REQ-d00061-C, REQ-d00061-F, REQ-p00050-D
"""Tests for _matches_query() helper function.

Validates REQ-d00061-B, REQ-d00061-C, REQ-d00061-F, REQ-p00050-D:
- REQ-d00061-B: Supports field parameter (id, title, body, keywords, all).
- REQ-d00061-C: Supports regex=True for regex matching.
- REQ-d00061-F: Multi-term AND via parsed query delegation.
- REQ-p00050-D: Single code path for query matching.
"""

import re

import pytest

from elspais.graph import GraphNode, NodeKind
from elspais.mcp.search import parse_query

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


def _mq(fn, node, field, query):
    """Call _matches_query for non-regex with parsed query."""
    return fn(node, field=field, regex=False, compiled_pattern=None, parsed=parse_query(query))


def _mq_regex(fn, node, field, pattern):
    """Call _matches_query for regex path."""
    return fn(node, field=field, regex=True, compiled_pattern=pattern)


# ─────────────────────────────────────────────────────────────────────────────
# Test: field="id" matching - REQ-d00061-B
# ─────────────────────────────────────────────────────────────────────────────


class TestFieldIdMatch:
    """Tests for field='id' matching.

    Validates REQ-d00061-B, REQ-d00061-C, REQ-p00050-D:
    """

    def test_REQ_d00061_B_field_id_match_substring(self, _matches_query, match_node):
        """REQ-d00061-B: field='id' matches substring in node.id."""
        assert _mq(_matches_query, match_node, "id", "d00099")

    def test_REQ_d00061_B_field_id_no_match(self, _matches_query, match_node):
        """REQ-d00061-B: field='id' returns False when no substring match."""
        assert not _mq(_matches_query, match_node, "id", "zzz")

    def test_REQ_d00061_B_field_id_case_insensitive(self, _matches_query, match_node):
        """REQ-d00061-B: field='id' matching is case-insensitive."""
        assert _mq(_matches_query, match_node, "id", "req-d00099")

    def test_REQ_d00061_C_field_id_regex_match(self, _matches_query, match_node):
        """REQ-d00061-C: field='id' with regex=True uses compiled_pattern."""
        pattern = re.compile(r"REQ-d000\d+")
        assert _mq_regex(_matches_query, match_node, "id", pattern)

    def test_REQ_d00061_C_field_id_regex_no_match(self, _matches_query, match_node):
        """REQ-d00061-C: field='id' with regex returns False on no match."""
        pattern = re.compile(r"REQ-p\d+")
        assert not _mq_regex(_matches_query, match_node, "id", pattern)


# ─────────────────────────────────────────────────────────────────────────────
# Test: field="title" matching - REQ-d00061-B
# ─────────────────────────────────────────────────────────────────────────────


class TestFieldTitleMatch:
    """Tests for field='title' matching.

    Validates REQ-d00061-B, REQ-d00061-C, REQ-p00050-D:
    """

    def test_REQ_d00061_B_field_title_match_substring(self, _matches_query, match_node):
        """REQ-d00061-B: field='title' matches substring."""
        assert _mq(_matches_query, match_node, "title", "security")

    def test_REQ_d00061_B_field_title_no_match(self, _matches_query, match_node):
        """REQ-d00061-B: field='title' returns False when no match."""
        assert not _mq(_matches_query, match_node, "title", "database")

    def test_REQ_d00061_B_field_title_case_insensitive(self, _matches_query, match_node):
        """REQ-d00061-B: field='title' matching is case-insensitive."""
        # "platform security" as two AND terms both present in title
        assert _mq(_matches_query, match_node, "title", "platform security")

    def test_REQ_d00061_C_field_title_regex_match(self, _matches_query, match_node):
        """REQ-d00061-C: field='title' with regex uses compiled_pattern."""
        pattern = re.compile(r"Platform\s+Security")
        assert _mq_regex(_matches_query, match_node, "title", pattern)

    def test_REQ_d00061_C_field_title_regex_no_match(self, _matches_query, match_node):
        """REQ-d00061-C: field='title' regex returns False on no match."""
        pattern = re.compile(r"^Database")
        assert not _mq_regex(_matches_query, match_node, "title", pattern)

    def test_REQ_d00061_B_field_title_empty_label(self, _matches_query, empty_node):
        """REQ-d00061-B: field='title' handles empty label gracefully."""
        empty_node.set_label("")
        assert not _mq(_matches_query, empty_node, "title", "anything")


# ─────────────────────────────────────────────────────────────────────────────
# Test: field="body" matching - REQ-d00061-B
# ─────────────────────────────────────────────────────────────────────────────


class TestFieldBodyMatch:
    """Tests for field='body' matching.

    Validates REQ-d00061-B, REQ-d00061-C, REQ-p00050-D:
    """

    def test_REQ_d00061_B_field_body_match_substring(self, _matches_query, match_node):
        """REQ-d00061-B: field='body' matches substring in body_text."""
        assert _mq(_matches_query, match_node, "body", "encrypted")

    def test_REQ_d00061_B_field_body_no_match(self, _matches_query, match_node):
        """REQ-d00061-B: field='body' returns False when no match."""
        assert not _mq(_matches_query, match_node, "body", "database")

    def test_REQ_d00061_B_field_body_case_insensitive(self, _matches_query, match_node):
        """REQ-d00061-B: field='body' matching is case-insensitive."""
        assert _mq(_matches_query, match_node, "body", "aes-256")

    def test_REQ_d00061_C_field_body_regex_match(self, _matches_query, match_node):
        """REQ-d00061-C: field='body' with regex uses compiled_pattern."""
        pattern = re.compile(r"AES-\d+")
        assert _mq_regex(_matches_query, match_node, "body", pattern)

    def test_REQ_d00061_C_field_body_regex_no_match(self, _matches_query, match_node):
        """REQ-d00061-C: field='body' regex returns False on no match."""
        pattern = re.compile(r"RSA-\d+")
        assert not _mq_regex(_matches_query, match_node, "body", pattern)

    def test_REQ_d00061_B_field_body_empty(self, _matches_query, empty_node):
        """REQ-d00061-B: field='body' returns False when body_text absent."""
        assert not _mq(_matches_query, empty_node, "body", "anything")

    def test_REQ_d00061_C_field_body_regex_empty(self, _matches_query, empty_node):
        """REQ-d00061-C: field='body' regex returns False when body absent."""
        pattern = re.compile(r".*")
        assert not _mq_regex(_matches_query, empty_node, "body", pattern)


# ─────────────────────────────────────────────────────────────────────────────
# Test: field="keywords" matching - REQ-d00061-B
# ─────────────────────────────────────────────────────────────────────────────


class TestFieldKeywordsMatch:
    """Tests for field='keywords' matching.

    Validates REQ-d00061-B, REQ-d00061-C, REQ-p00050-D:
    """

    def test_REQ_d00061_B_field_keywords_match_substring(self, _matches_query, match_node):
        """REQ-d00061-B: field='keywords' matches substring."""
        assert _mq(_matches_query, match_node, "keywords", "encrypt")

    def test_REQ_d00061_B_field_keywords_exact_match(self, _matches_query, match_node):
        """REQ-d00061-B: field='keywords' matches exact keyword."""
        assert _mq(_matches_query, match_node, "keywords", "security")

    def test_REQ_d00061_B_field_keywords_no_match(self, _matches_query, match_node):
        """REQ-d00061-B: field='keywords' returns False when no match."""
        assert not _mq(_matches_query, match_node, "keywords", "database")

    def test_REQ_d00061_B_field_keywords_case_insensitive(self, _matches_query, match_node):
        """REQ-d00061-B: field='keywords' matching is case-insensitive."""
        assert _mq(_matches_query, match_node, "keywords", "aes")

    def test_REQ_d00061_C_field_keywords_regex_match(self, _matches_query, match_node):
        """REQ-d00061-C: field='keywords' regex uses compiled_pattern."""
        pattern = re.compile(r"^secur")
        assert _mq_regex(_matches_query, match_node, "keywords", pattern)

    def test_REQ_d00061_C_field_keywords_regex_no_match(self, _matches_query, match_node):
        """REQ-d00061-C: field='keywords' regex returns False on no match."""
        pattern = re.compile(r"^zzz")
        assert not _mq_regex(_matches_query, match_node, "keywords", pattern)

    def test_REQ_d00061_B_field_keywords_empty(self, _matches_query, empty_node):
        """REQ-d00061-B: field='keywords' returns False when absent."""
        assert not _mq(_matches_query, empty_node, "keywords", "anything")


# ─────────────────────────────────────────────────────────────────────────────
# Test: field="all" matching - REQ-d00061-B
# ─────────────────────────────────────────────────────────────────────────────


class TestFieldAllMatch:
    """Tests for field='all' matching across all fields.

    Validates REQ-d00061-B, REQ-d00061-C, REQ-p00050-D:
    """

    def test_REQ_d00061_B_field_all_matches_id(self, _matches_query, match_node):
        """REQ-d00061-B: field='all' matches against node.id."""
        assert _mq(_matches_query, match_node, "all", "d00099")

    def test_REQ_d00061_B_field_all_matches_title(self, _matches_query, match_node):
        """REQ-d00061-B: field='all' matches against title."""
        assert _mq(_matches_query, match_node, "all", "overview")

    def test_REQ_d00061_B_field_all_matches_body(self, _matches_query, match_node):
        """REQ-d00061-B: field='all' matches against body_text."""
        assert _mq(_matches_query, match_node, "all", "encrypted")

    def test_REQ_d00061_B_field_all_matches_keywords(self, _matches_query, match_node):
        """REQ-d00061-B: field='all' matches against keywords."""
        assert _mq(_matches_query, match_node, "all", "encryption")

    def test_REQ_d00061_B_field_all_no_match(self, _matches_query, match_node):
        """REQ-d00061-B: field='all' returns False when nothing matches."""
        assert not _mq(_matches_query, match_node, "all", "zzzznotfound")

    def test_REQ_d00061_C_field_all_regex_matches_id(self, _matches_query, match_node):
        """REQ-d00061-C: field='all' with regex matches node.id."""
        pattern = re.compile(r"REQ-d\d{5}")
        assert _mq_regex(_matches_query, match_node, "all", pattern)

    def test_REQ_d00061_C_field_all_regex_matches_title(self, _matches_query, match_node):
        """REQ-d00061-C: field='all' with regex matches title."""
        pattern = re.compile(r"Platform\s+\w+")
        assert _mq_regex(_matches_query, match_node, "all", pattern)

    def test_REQ_d00061_C_field_all_regex_matches_body(self, _matches_query, match_node):
        """REQ-d00061-C: field='all' with regex matches body_text."""
        pattern = re.compile(r"AES-\d+")
        assert _mq_regex(_matches_query, match_node, "all", pattern)

    def test_REQ_d00061_C_field_all_regex_matches_keywords(self, _matches_query, match_node):
        """REQ-d00061-C: field='all' with regex matches keywords."""
        pattern = re.compile(r"^encrypt")
        assert _mq_regex(_matches_query, match_node, "all", pattern)

    def test_REQ_d00061_C_field_all_regex_no_match(self, _matches_query, match_node):
        """REQ-d00061-C: field='all' regex returns False on no match."""
        pattern = re.compile(r"^NONEXISTENT$")
        assert not _mq_regex(_matches_query, match_node, "all", pattern)


# ─────────────────────────────────────────────────────────────────────────────
# Test: single code path - REQ-p00050-D
# ─────────────────────────────────────────────────────────────────────────────


class TestSingleCodePath:
    """Tests confirming _matches_query is a single reusable code path.

    Validates REQ-d00061-B, REQ-d00061-C, REQ-p00050-D:
    """

    def test_REQ_p00050_D_returns_bool(self, _matches_query, match_node):
        """REQ-p00050-D: _matches_query returns a bool."""
        result = _mq(_matches_query, match_node, "id", "d00099")
        assert isinstance(result, bool)

    def test_REQ_p00050_D_false_for_unrecognized_field(self, _matches_query, match_node):
        """REQ-p00050-D: unrecognized field returns False (no crash)."""
        result = _mq(_matches_query, match_node, "unknown_field", "d00099")
        assert result is False

    def test_REQ_p00050_D_field_id_does_not_match_title(self, _matches_query, match_node):
        """REQ-p00050-D: field='id' only checks id, not title."""
        assert not _mq(_matches_query, match_node, "id", "security overview")

    def test_REQ_p00050_D_field_title_does_not_match_body(self, _matches_query, match_node):
        """REQ-p00050-D: field='title' only checks title, not body."""
        assert not _mq(_matches_query, match_node, "title", "encrypted")

    def test_REQ_p00050_D_field_body_does_not_match_keywords(self, _matches_query, match_node):
        """REQ-p00050-D: field='body' only checks body, not keywords."""
        assert not _mq(_matches_query, match_node, "body", "encryption")

    def test_REQ_p00050_D_field_keywords_does_not_match_id(self, _matches_query, match_node):
        """REQ-p00050-D: field='keywords' only checks keywords, not id."""
        assert not _mq(_matches_query, match_node, "keywords", "req-d00099")


# ─────────────────────────────────────────────────────────────────────────────
# Test: multi-term AND delegation - REQ-d00061-F
# ─────────────────────────────────────────────────────────────────────────────


class TestMultiTermDelegation:
    """Tests for multi-term query delegation via parsed parameter.

    Validates REQ-d00061-F, REQ-p00050-D:
    """

    def test_REQ_d00061_F_delegates_to_parsed_query(self, _matches_query, match_node):
        """REQ-d00061-F: two AND terms both present matches."""
        assert _mq(_matches_query, match_node, "all", "Platform security")

    def test_REQ_d00061_F_parsed_query_or_group(self, _matches_query, match_node):
        """REQ-d00061-F: OR group matches when one alternative matches."""
        assert _mq(_matches_query, match_node, "all", "database OR security")

    def test_REQ_d00061_F_parsed_query_exclusion(self, _matches_query, match_node):
        """REQ-d00061-F: exclusion term causes False."""
        assert not _mq(_matches_query, match_node, "all", "-security")

    def test_REQ_d00061_F_parsed_query_no_match(self, _matches_query, match_node):
        """REQ-d00061-F: multi-term AND fails when one term absent."""
        assert not _mq(_matches_query, match_node, "all", "security database")

    def test_REQ_p00050_D_regex_ignores_parsed(self, _matches_query, match_node):
        """REQ-p00050-D: regex=True uses regex path regardless."""
        pattern = re.compile(r"REQ-d000\d+")
        assert _mq_regex(_matches_query, match_node, "id", pattern)

    def test_REQ_p00050_D_no_parsed_returns_false(self, _matches_query, match_node):
        """REQ-p00050-D: parsed=None returns False (no legacy fallback)."""
        result = _matches_query(
            match_node,
            field="all",
            regex=False,
            compiled_pattern=None,
            parsed=None,
        )
        assert result is False
