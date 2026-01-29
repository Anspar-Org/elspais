"""Tests for keyword extraction from requirements and assertions.

Tests REQ-o00064: Keyword Extraction for Requirements
- Extract keywords from requirement title/body
- Extract keywords from assertion text
- Store keywords in node._content["keywords"]
- Filter stopwords and common terms
"""

import pytest

from elspais.graph import NodeKind
from elspais.graph.builder import TraceGraph
from elspais.graph.GraphNode import GraphNode

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def simple_graph():
    """Create a simple graph with one requirement and assertions."""
    graph = TraceGraph(repo_root="/tmp/test")

    # Add a requirement node
    req_node = GraphNode(
        id="REQ-p00001",
        kind=NodeKind.REQUIREMENT,
        label="User Authentication System",
    )
    req_node._content = {
        "level": "PRD",
        "status": "Active",
        "hash": "abc12345",
    }
    graph._index["REQ-p00001"] = req_node
    graph._roots.append(req_node)

    # Add assertion children
    assertion_a = GraphNode(
        id="REQ-p00001-A",
        kind=NodeKind.ASSERTION,
        label="The system SHALL support OAuth2 authentication with GitHub",
    )
    assertion_a._content = {"label": "A"}
    graph._index["REQ-p00001-A"] = assertion_a
    req_node.add_child(assertion_a)

    assertion_b = GraphNode(
        id="REQ-p00001-B",
        kind=NodeKind.ASSERTION,
        label="The system SHALL validate JWT tokens using RSA signatures",
    )
    assertion_b._content = {"label": "B"}
    graph._index["REQ-p00001-B"] = assertion_b
    req_node.add_child(assertion_b)

    return graph


@pytest.fixture
def multi_req_graph():
    """Create a graph with multiple requirements for keyword aggregation tests."""
    graph = TraceGraph(repo_root="/tmp/test")

    # Requirement 1: Authentication
    req1 = GraphNode(
        id="REQ-p00001",
        kind=NodeKind.REQUIREMENT,
        label="OAuth Authentication",
    )
    req1._content = {"level": "PRD", "status": "Active"}
    graph._index["REQ-p00001"] = req1
    graph._roots.append(req1)

    a1 = GraphNode(
        id="REQ-p00001-A",
        kind=NodeKind.ASSERTION,
        label="Support GitHub OAuth provider",
    )
    a1._content = {"label": "A"}
    graph._index["REQ-p00001-A"] = a1
    req1.add_child(a1)

    # Requirement 2: API
    req2 = GraphNode(
        id="REQ-o00001",
        kind=NodeKind.REQUIREMENT,
        label="REST API Endpoints",
    )
    req2._content = {"level": "OPS", "status": "Active"}
    graph._index["REQ-o00001"] = req2
    graph._roots.append(req2)

    a2 = GraphNode(
        id="REQ-o00001-A",
        kind=NodeKind.ASSERTION,
        label="The API SHALL support JSON request bodies",
    )
    a2._content = {"label": "A"}
    graph._index["REQ-o00001-A"] = a2
    req2.add_child(a2)

    # Requirement 3: Also about API (shares keyword)
    req3 = GraphNode(
        id="REQ-d00001",
        kind=NodeKind.REQUIREMENT,
        label="API Rate Limiting",
    )
    req3._content = {"level": "DEV", "status": "Active"}
    graph._index["REQ-d00001"] = req3
    graph._roots.append(req3)

    return graph


# ─────────────────────────────────────────────────────────────────────────────
# Test: extract_keywords function
# ─────────────────────────────────────────────────────────────────────────────


class TestExtractKeywords:
    """Tests for the extract_keywords utility function."""

    def test_extracts_words_from_text(self):
        """Extract meaningful words from text."""
        from elspais.graph.annotators import extract_keywords

        text = "User Authentication System"
        keywords = extract_keywords(text)

        assert "user" in keywords
        assert "authentication" in keywords
        assert "system" in keywords

    def test_lowercases_keywords(self):
        """Keywords are normalized to lowercase."""
        from elspais.graph.annotators import extract_keywords

        text = "OAuth GitHub JWT"
        keywords = extract_keywords(text)

        assert "oauth" in keywords
        assert "github" in keywords
        assert "jwt" in keywords

    def test_filters_stopwords(self):
        """Common stopwords are filtered out."""
        from elspais.graph.annotators import extract_keywords

        text = "The system shall validate the input"
        keywords = extract_keywords(text)

        assert "the" not in keywords
        assert "shall" not in keywords
        assert "validate" in keywords
        assert "input" in keywords

    def test_filters_short_words(self):
        """Words shorter than 3 characters are filtered."""
        from elspais.graph.annotators import extract_keywords

        text = "A is to be or not"
        keywords = extract_keywords(text)

        assert "a" not in keywords
        assert "is" not in keywords
        assert "to" not in keywords
        assert "be" not in keywords
        assert "or" not in keywords

    def test_removes_punctuation(self):
        """Punctuation is stripped from words."""
        from elspais.graph.annotators import extract_keywords

        text = "OAuth2, JWT-based, (authentication)"
        keywords = extract_keywords(text)

        assert "oauth2" in keywords
        assert "jwt" in keywords or "jwt-based" in keywords
        assert "authentication" in keywords

    def test_handles_empty_text(self):
        """Empty text returns empty list."""
        from elspais.graph.annotators import extract_keywords

        keywords = extract_keywords("")
        assert keywords == []

    def test_deduplicates_keywords(self):
        """Duplicate keywords are removed."""
        from elspais.graph.annotators import extract_keywords

        text = "OAuth OAuth OAuth authentication"
        keywords = extract_keywords(text)

        assert keywords.count("oauth") == 1


# ─────────────────────────────────────────────────────────────────────────────
# Test: annotate_keywords function
# ─────────────────────────────────────────────────────────────────────────────


class TestAnnotateKeywords:
    """Tests for the annotate_keywords graph annotator."""

    def test_stores_keywords_in_node_content(self, simple_graph):
        """Keywords are stored in node._content["keywords"]."""
        from elspais.graph.annotators import annotate_keywords

        annotate_keywords(simple_graph)

        req_node = simple_graph._index["REQ-p00001"]
        keywords = req_node.get_field("keywords", [])

        assert isinstance(keywords, list)
        assert len(keywords) > 0

    def test_extracts_from_title(self, simple_graph):
        """Keywords include terms from requirement title."""
        from elspais.graph.annotators import annotate_keywords

        annotate_keywords(simple_graph)

        req_node = simple_graph._index["REQ-p00001"]
        keywords = req_node.get_field("keywords", [])

        # Title is "User Authentication System"
        assert "user" in keywords
        assert "authentication" in keywords

    def test_extracts_from_assertions(self, simple_graph):
        """Keywords include terms from assertion text."""
        from elspais.graph.annotators import annotate_keywords

        annotate_keywords(simple_graph)

        req_node = simple_graph._index["REQ-p00001"]
        keywords = req_node.get_field("keywords", [])

        # Assertion A mentions "OAuth2", "GitHub"
        assert "oauth2" in keywords
        assert "github" in keywords

        # Assertion B mentions "JWT", "RSA"
        assert "jwt" in keywords
        assert "rsa" in keywords

    def test_only_annotates_requirements(self, simple_graph):
        """Only REQUIREMENT nodes get keywords, not assertions."""
        from elspais.graph.annotators import annotate_keywords

        annotate_keywords(simple_graph)

        # Assertions should not have keywords field
        assertion_node = simple_graph._index["REQ-p00001-A"]
        keywords = assertion_node.get_field("keywords")

        assert keywords is None

    def test_handles_requirements_without_assertions(self, multi_req_graph):
        """Requirements without assertions still get keywords from title."""
        from elspais.graph.annotators import annotate_keywords

        annotate_keywords(multi_req_graph)

        # REQ-d00001 has no assertions
        req_node = multi_req_graph._index["REQ-d00001"]
        keywords = req_node.get_field("keywords", [])

        # Should have keywords from title "API Rate Limiting"
        assert "api" in keywords
        assert "rate" in keywords
        assert "limiting" in keywords


# ─────────────────────────────────────────────────────────────────────────────
# Test: find_by_keywords function
# ─────────────────────────────────────────────────────────────────────────────


class TestFindByKeywords:
    """Tests for keyword-based requirement search."""

    def test_finds_requirements_with_keyword(self, multi_req_graph):
        """Find requirements containing a specific keyword."""
        from elspais.graph.annotators import annotate_keywords, find_by_keywords

        annotate_keywords(multi_req_graph)
        results = find_by_keywords(multi_req_graph, ["api"])

        # REQ-o00001 and REQ-d00001 both mention API
        result_ids = [n.id for n in results]
        assert "REQ-o00001" in result_ids
        assert "REQ-d00001" in result_ids

    def test_finds_requirements_with_multiple_keywords(self, multi_req_graph):
        """Find requirements matching multiple keywords (AND logic)."""
        from elspais.graph.annotators import annotate_keywords, find_by_keywords

        annotate_keywords(multi_req_graph)
        results = find_by_keywords(multi_req_graph, ["api", "rate"])

        # Only REQ-d00001 has both "api" and "rate"
        result_ids = [n.id for n in results]
        assert "REQ-d00001" in result_ids
        assert len(result_ids) == 1

    def test_returns_empty_for_no_match(self, multi_req_graph):
        """Returns empty list when no requirements match."""
        from elspais.graph.annotators import annotate_keywords, find_by_keywords

        annotate_keywords(multi_req_graph)
        results = find_by_keywords(multi_req_graph, ["nonexistent"])

        assert results == []

    def test_keyword_matching_is_case_insensitive(self, multi_req_graph):
        """Keyword search is case-insensitive."""
        from elspais.graph.annotators import annotate_keywords, find_by_keywords

        annotate_keywords(multi_req_graph)

        # Search with uppercase should still match
        results = find_by_keywords(multi_req_graph, ["API"])
        result_ids = [n.id for n in results]

        assert len(result_ids) >= 2


# ─────────────────────────────────────────────────────────────────────────────
# Test: collect_all_keywords function
# ─────────────────────────────────────────────────────────────────────────────


class TestCollectAllKeywords:
    """Tests for collecting all keywords from a graph."""

    def test_collects_unique_keywords(self, multi_req_graph):
        """Collect all unique keywords from the graph."""
        from elspais.graph.annotators import annotate_keywords, collect_all_keywords

        annotate_keywords(multi_req_graph)
        all_keywords = collect_all_keywords(multi_req_graph)

        assert isinstance(all_keywords, list)
        assert "api" in all_keywords
        assert "oauth" in all_keywords
        assert "github" in all_keywords

    def test_returns_sorted_keywords(self, multi_req_graph):
        """Keywords are returned in sorted order."""
        from elspais.graph.annotators import annotate_keywords, collect_all_keywords

        annotate_keywords(multi_req_graph)
        all_keywords = collect_all_keywords(multi_req_graph)

        assert all_keywords == sorted(all_keywords)

    def test_no_duplicates(self, multi_req_graph):
        """Each keyword appears only once."""
        from elspais.graph.annotators import annotate_keywords, collect_all_keywords

        annotate_keywords(multi_req_graph)
        all_keywords = collect_all_keywords(multi_req_graph)

        assert len(all_keywords) == len(set(all_keywords))
