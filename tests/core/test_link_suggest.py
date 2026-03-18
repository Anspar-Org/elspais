# Implements: REQ-o00065-A, REQ-o00065-B, REQ-o00065-C, REQ-o00065-F
# Implements: REQ-d00072-A+B+C
"""Tests for the link suggestion engine (link_suggest.py).

Validates discover_assertions-based link suggestions for unlinked TEST nodes,
covering search term extraction, confidence scoring, deduplication, and the
apply_link_to_file helper.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from elspais.graph.builder import TraceGraph
from elspais.graph.GraphNode import GraphNode, NodeKind
from elspais.graph.link_suggest import (
    CONFIDENCE_HIGH,
    CONFIDENCE_MEDIUM,
    LinkSuggestion,
    _deduplicate_suggestions,
    _extract_search_terms,
    _find_unlinked_tests,
    apply_link_to_file,
    suggest_links,
)
from elspais.graph.relations import EdgeKind

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_graph() -> TraceGraph:
    """Create a minimal empty TraceGraph."""
    return TraceGraph()


def _add_requirement(
    graph: TraceGraph,
    req_id: str,
    title: str = "Requirement Title",
    *,
    as_root: bool = True,
) -> GraphNode:
    """Add a REQUIREMENT node to the graph."""
    node = GraphNode(id=req_id, kind=NodeKind.REQUIREMENT, label=title)
    graph._index[req_id] = node
    if as_root:
        graph._roots.append(node)
    return node


def _add_test(
    graph: TraceGraph,
    test_id: str,
    label: str = "test_func",
    *,
    function_name: str = "",
    class_name: str = "",
    file_path: str = "",
) -> GraphNode:
    """Add a TEST node to the graph."""
    node = GraphNode(id=test_id, kind=NodeKind.TEST, label=label)
    if function_name:
        node.set_field("function_name", function_name)
    if class_name:
        node.set_field("class_name", class_name)
    graph._index[test_id] = node

    # Optionally attach to a FILE node
    if file_path:
        file_id = f"file:{file_path}"
        file_node = graph._index.get(file_id)
        if not file_node:
            file_node = GraphNode(id=file_id, kind=NodeKind.FILE, label=file_path)
            file_node.set_field("relative_path", file_path)
            graph._index[file_id] = file_node
            graph._roots.append(file_node)
        file_node.link(node, EdgeKind.CONTAINS)

    return node


def _make_discover_fn(assertions: list[dict[str, Any]]):
    """Create a mock discover_fn that returns fixed assertions."""

    def discover_fn(graph, query, **kwargs):
        return {
            "assertions": assertions,
            "stats": {
                "requirements_matched": len({a["requirement_id"] for a in assertions}),
                "assertions_returned": len(assertions),
            },
        }

    return discover_fn


# ===========================================================================
# LinkSuggestion dataclass
# ===========================================================================


class TestLinkSuggestionDataclass:
    """Tests for LinkSuggestion confidence bands and serialization."""

    def test_REQ_d00072_A_confidence_band_high(self) -> None:
        s = LinkSuggestion("t1", "t1", "f.py", "REQ-1", "Title", 0.9)
        assert s.confidence_band == "high"

    def test_REQ_d00072_A_confidence_band_medium(self) -> None:
        s = LinkSuggestion("t1", "t1", "f.py", "REQ-1", "Title", 0.6)
        assert s.confidence_band == "medium"

    def test_REQ_d00072_A_confidence_band_low(self) -> None:
        s = LinkSuggestion("t1", "t1", "f.py", "REQ-1", "Title", 0.3)
        assert s.confidence_band == "low"

    def test_REQ_d00072_A_confidence_band_boundary_high(self) -> None:
        s = LinkSuggestion("t1", "t1", "f.py", "REQ-1", "Title", CONFIDENCE_HIGH)
        assert s.confidence_band == "high"

    def test_REQ_d00072_A_confidence_band_boundary_medium(self) -> None:
        s = LinkSuggestion("t1", "t1", "f.py", "REQ-1", "Title", CONFIDENCE_MEDIUM)
        assert s.confidence_band == "medium"

    def test_REQ_d00072_A_to_dict_serialization(self) -> None:
        s = LinkSuggestion("t1", "label", "f.py", "REQ-1", "Title", 0.85, ["reason1"])
        d = s.to_dict()
        assert d["test_id"] == "t1"
        assert d["confidence"] == 0.85
        assert d["confidence_band"] == "high"
        assert d["reasons"] == ["reason1"]

    def test_REQ_d00072_A_to_dict_rounds_confidence(self) -> None:
        s = LinkSuggestion("t1", "t1", "f.py", "REQ-1", "Title", 0.123456789)
        d = s.to_dict()
        assert d["confidence"] == 0.123


# ===========================================================================
# _find_unlinked_tests
# ===========================================================================


class TestFindUnlinkedTests:
    """Tests for _find_unlinked_tests()."""

    def test_REQ_o00065_A_finds_tests_without_req_parents(self) -> None:
        graph = _make_graph()
        _add_test(graph, "test:1", file_path="tests/test_foo.py")
        result = _find_unlinked_tests(graph)
        assert len(result) == 1
        assert result[0].id == "test:1"

    def test_REQ_o00065_A_skips_linked_tests(self) -> None:
        graph = _make_graph()
        req = _add_requirement(graph, "REQ-1")
        test = _add_test(graph, "test:1")
        req.link(test, EdgeKind.VERIFIES)
        result = _find_unlinked_tests(graph)
        assert len(result) == 0

    def test_REQ_o00065_A_skips_tests_linked_via_assertion(self) -> None:
        graph = _make_graph()
        req = _add_requirement(graph, "REQ-1")
        assertion = GraphNode(id="REQ-1-A", kind=NodeKind.ASSERTION, label="A")
        graph._index["REQ-1-A"] = assertion
        req.link(assertion, EdgeKind.STRUCTURES)
        test = _add_test(graph, "test:1")
        assertion.link(test, EdgeKind.VERIFIES)
        result = _find_unlinked_tests(graph)
        assert len(result) == 0

    def test_REQ_o00065_A_skips_tests_linked_via_code(self) -> None:
        graph = _make_graph()
        req = _add_requirement(graph, "REQ-1")
        code = GraphNode(id="code:1", kind=NodeKind.CODE, label="code")
        graph._index["code:1"] = code
        req.link(code, EdgeKind.IMPLEMENTS)
        test = _add_test(graph, "test:1")
        code.link(test, EdgeKind.VERIFIES)
        result = _find_unlinked_tests(graph)
        assert len(result) == 0

    def test_REQ_o00065_A_filters_by_file_path(self) -> None:
        graph = _make_graph()
        _add_test(graph, "test:1", file_path="tests/test_foo.py")
        _add_test(graph, "test:2", file_path="tests/test_bar.py")
        result = _find_unlinked_tests(graph, file_path="tests/test_foo.py")
        assert len(result) == 1
        assert result[0].id == "test:1"

    def test_REQ_o00065_A_file_path_filter_no_match(self) -> None:
        graph = _make_graph()
        _add_test(graph, "test:1", file_path="tests/test_foo.py")
        result = _find_unlinked_tests(graph, file_path="tests/test_other.py")
        assert len(result) == 0

    def test_REQ_o00065_A_skips_tests_without_source_when_filtering(self) -> None:
        graph = _make_graph()
        _add_test(graph, "test:1")  # No file_path
        result = _find_unlinked_tests(graph, file_path="tests/test_foo.py")
        assert len(result) == 0

    def test_REQ_o00065_A_mixed_linked_and_unlinked(self) -> None:
        graph = _make_graph()
        req = _add_requirement(graph, "REQ-1")
        linked = _add_test(graph, "test:linked")
        req.link(linked, EdgeKind.VERIFIES)
        _add_test(graph, "test:unlinked")
        result = _find_unlinked_tests(graph)
        assert len(result) == 1
        assert result[0].id == "test:unlinked"


# ===========================================================================
# _extract_search_terms
# ===========================================================================


class TestExtractSearchTerms:
    """Tests for search term extraction from test nodes."""

    def test_REQ_d00072_B_extracts_from_function_name(self) -> None:
        graph = _make_graph()
        test = _add_test(
            graph,
            "test:1",
            function_name="test_validate_config",
            file_path="tests/test_config.py",
        )
        terms = _extract_search_terms(test)
        assert "validate" in terms
        assert "config" in terms

    def test_REQ_d00072_B_strips_test_prefix_from_function(self) -> None:
        graph = _make_graph()
        test = _add_test(
            graph,
            "test:1",
            function_name="test_hash_integrity",
            file_path="tests/test_hash.py",
        )
        terms = _extract_search_terms(test)
        assert "test" not in terms.lower().split(" or ")
        assert "hash" in terms
        assert "integrity" in terms

    def test_REQ_d00072_B_extracts_from_class_name_camel_case(self) -> None:
        graph = _make_graph()
        test = _add_test(
            graph,
            "test:1",
            class_name="TestMcpInstallLocal",
            function_name="test_something",
            file_path="tests/test_mcp.py",
        )
        terms = _extract_search_terms(test)
        # CamelCase split: Mcp, Install, Local
        assert "mcp" in terms
        assert "install" in terms
        assert "local" in terms

    def test_REQ_d00072_B_extracts_from_file_name(self) -> None:
        graph = _make_graph()
        test = _add_test(
            graph,
            "test:1",
            file_path="tests/core/test_link_suggest.py",
        )
        terms = _extract_search_terms(test)
        assert "link" in terms
        assert "suggest" in terms

    def test_REQ_d00072_B_filters_stopwords(self) -> None:
        graph = _make_graph()
        test = _add_test(
            graph,
            "test:1",
            function_name="test_should_not_assert_when",
            file_path="tests/test_misc.py",
        )
        terms = _extract_search_terms(test)
        # "should", "not", "assert", "when" are stopwords
        assert "should" not in terms
        assert "assert" not in terms

    def test_REQ_d00072_B_filters_short_words(self) -> None:
        graph = _make_graph()
        test = _add_test(
            graph,
            "test:1",
            function_name="test_a_b_config",
            file_path="tests/test_x.py",
        )
        terms = _extract_search_terms(test)
        # "a" and "b" are too short (< 3 chars)
        for part in terms.split(" OR "):
            assert len(part.strip()) >= 3

    def test_REQ_d00072_B_deduplicates_words(self) -> None:
        graph = _make_graph()
        test = _add_test(
            graph,
            "test:1",
            function_name="test_config_validation",
            class_name="TestConfigValidation",
            file_path="tests/test_config.py",
        )
        terms = _extract_search_terms(test)
        parts = [p.strip() for p in terms.split(" OR ")]
        assert len(parts) == len(set(parts))

    def test_REQ_d00072_B_uses_or_joining(self) -> None:
        graph = _make_graph()
        test = _add_test(
            graph,
            "test:1",
            function_name="test_hash_mode",
            file_path="tests/test_hash.py",
        )
        terms = _extract_search_terms(test)
        assert " OR " in terms

    def test_REQ_d00072_B_empty_for_generic_test(self) -> None:
        graph = _make_graph()
        test = _add_test(graph, "test:1")
        # No function_name, class_name, file, or docstring
        terms = _extract_search_terms(test)
        assert terms == ""


# ===========================================================================
# suggest_links (integration with mock discover_fn)
# ===========================================================================


class TestSuggestLinks:
    """Tests for suggest_links with injected discover_fn."""

    def test_REQ_d00072_A_suggest_links_returns_sorted(self) -> None:
        graph = _make_graph()
        _add_test(
            graph,
            "test:1",
            function_name="test_validate_hash",
            file_path="tests/test_hash.py",
        )

        discover_fn = _make_discover_fn(
            [
                {
                    "id": "REQ-1-A",
                    "label": "A",
                    "text": "SHALL hash",
                    "requirement_id": "REQ-1",
                    "requirement_title": "Hash",
                    "level": "DEV",
                    "score": 50.0,
                    "direct_match": True,
                },
                {
                    "id": "REQ-2-B",
                    "label": "B",
                    "text": "SHALL validate",
                    "requirement_id": "REQ-2",
                    "requirement_title": "Validate",
                    "level": "DEV",
                    "score": 80.0,
                    "direct_match": True,
                },
            ]
        )
        result = suggest_links(graph, Path("/repo"), discover_fn=discover_fn)
        assert len(result) == 2
        assert result[0].confidence >= result[1].confidence

    def test_REQ_d00072_A_suggest_links_respects_limit(self) -> None:
        graph = _make_graph()
        _add_test(
            graph,
            "test:1",
            function_name="test_something",
            file_path="tests/test_foo.py",
        )
        discover_fn = _make_discover_fn(
            [
                {
                    "id": f"REQ-{i}-A",
                    "label": "A",
                    "text": f"assertion {i}",
                    "requirement_id": f"REQ-{i}",
                    "requirement_title": f"Req {i}",
                    "level": "DEV",
                    "score": 50.0,
                    "direct_match": False,
                }
                for i in range(10)
            ]
        )
        result = suggest_links(graph, Path("/repo"), limit=3, discover_fn=discover_fn)
        assert len(result) <= 3

    def test_REQ_d00072_A_suggest_links_empty_for_all_linked(self) -> None:
        graph = _make_graph()
        req = _add_requirement(graph, "REQ-1")
        test = _add_test(graph, "test:1", function_name="test_foo", file_path="tests/test_foo.py")
        req.link(test, EdgeKind.VERIFIES)
        discover_fn = _make_discover_fn([])
        result = suggest_links(graph, Path("/repo"), discover_fn=discover_fn)
        assert result == []

    def test_REQ_d00072_A_suggest_links_empty_graph(self) -> None:
        graph = _make_graph()
        discover_fn = _make_discover_fn([])
        result = suggest_links(graph, Path("/repo"), discover_fn=discover_fn)
        assert result == []

    def test_REQ_d00072_A_suggest_links_no_test_nodes(self) -> None:
        graph = _make_graph()
        _add_requirement(graph, "REQ-1")
        discover_fn = _make_discover_fn([])
        result = suggest_links(graph, Path("/repo"), discover_fn=discover_fn)
        assert result == []

    def test_REQ_d00072_A_suggest_links_none_discover_fn(self) -> None:
        """Without discover_fn, returns empty list."""
        graph = _make_graph()
        _add_test(graph, "test:1", function_name="test_foo", file_path="tests/test_foo.py")
        result = suggest_links(graph, Path("/repo"), discover_fn=None)
        assert result == []

    def test_REQ_d00072_A_suggest_links_file_path_filter(self) -> None:
        graph = _make_graph()
        _add_test(graph, "test:1", function_name="test_foo", file_path="tests/test_foo.py")
        _add_test(graph, "test:2", function_name="test_bar", file_path="tests/test_bar.py")
        discover_fn = _make_discover_fn(
            [
                {
                    "id": "REQ-1-A",
                    "label": "A",
                    "text": "something",
                    "requirement_id": "REQ-1",
                    "requirement_title": "Req 1",
                    "level": "DEV",
                    "score": 50.0,
                    "direct_match": False,
                },
            ]
        )
        result = suggest_links(
            graph,
            Path("/repo"),
            file_path="tests/test_foo.py",
            discover_fn=discover_fn,
        )
        # Only test:1 should be analyzed (file_path filter)
        test_ids = {s.test_id for s in result}
        assert "test:2" not in test_ids


# ===========================================================================
# _deduplicate_suggestions
# ===========================================================================


class TestDeduplicateSuggestions:
    """Tests for suggestion deduplication."""

    def test_REQ_d00072_C_dedup_keeps_highest_confidence(self) -> None:
        s1 = LinkSuggestion("t1", "t1", "f.py", "REQ-1", "Title", 0.5, ["r1"])
        s2 = LinkSuggestion("t1", "t1", "f.py", "REQ-1", "Title", 0.9, ["r2"])
        result = _deduplicate_suggestions([s1, s2])
        assert len(result) == 1
        assert result[0].confidence == 0.9

    def test_REQ_d00072_C_dedup_combines_reasons(self) -> None:
        s1 = LinkSuggestion("t1", "t1", "f.py", "REQ-1", "Title", 0.5, ["reason1"])
        s2 = LinkSuggestion("t1", "t1", "f.py", "REQ-1", "Title", 0.9, ["reason2"])
        result = _deduplicate_suggestions([s1, s2])
        assert "reason1" in result[0].reasons
        assert "reason2" in result[0].reasons

    def test_REQ_d00072_C_dedup_no_duplicate_reasons(self) -> None:
        s1 = LinkSuggestion("t1", "t1", "f.py", "REQ-1", "Title", 0.5, ["same"])
        s2 = LinkSuggestion("t1", "t1", "f.py", "REQ-1", "Title", 0.9, ["same"])
        result = _deduplicate_suggestions([s1, s2])
        assert result[0].reasons.count("same") == 1

    def test_REQ_d00072_C_dedup_different_pairs_preserved(self) -> None:
        s1 = LinkSuggestion("t1", "t1", "f.py", "REQ-1", "Title1", 0.5, ["r"])
        s2 = LinkSuggestion("t1", "t1", "f.py", "REQ-2", "Title2", 0.9, ["r"])
        result = _deduplicate_suggestions([s1, s2])
        assert len(result) == 2

    def test_REQ_d00072_C_dedup_empty_input(self) -> None:
        assert _deduplicate_suggestions([]) == []

    def test_REQ_d00072_C_dedup_single_item(self) -> None:
        s = LinkSuggestion("t1", "t1", "f.py", "REQ-1", "Title", 0.5, ["r"])
        result = _deduplicate_suggestions([s])
        assert len(result) == 1

    def test_REQ_d00072_C_dedup_does_not_mutate_originals(self) -> None:
        s1 = LinkSuggestion("t1", "t1", "f.py", "REQ-1", "Title", 0.5, ["r1"])
        s2 = LinkSuggestion("t1", "t1", "f.py", "REQ-1", "Title", 0.9, ["r2"])
        _deduplicate_suggestions([s1, s2])
        assert s1.confidence == 0.5
        assert s1.reasons == ["r1"]


# ===========================================================================
# apply_link_to_file
# ===========================================================================


class TestApplyLinkToFile:
    """Tests for apply_link_to_file()."""

    def test_REQ_o00065_F_apply_link_inserts_comment(self, tmp_path: Path) -> None:
        f = tmp_path / "test.py"
        f.write_text("line1\nline2\n")
        result = apply_link_to_file(f, 1, "REQ-001")
        assert result == "# Implements: REQ-001"
        assert "# Implements: REQ-001" in f.read_text()

    def test_REQ_o00065_F_apply_link_dry_run(self) -> None:
        result = apply_link_to_file(Path("/nonexistent"), 1, "REQ-001", dry_run=True)
        assert result == "# Implements: REQ-001"

    def test_REQ_o00065_F_apply_link_at_line_zero_top(self, tmp_path: Path) -> None:
        f = tmp_path / "test.py"
        f.write_text("existing\n")
        apply_link_to_file(f, 0, "REQ-001")
        lines = f.read_text().splitlines()
        assert lines[0] == "# Implements: REQ-001"

    def test_REQ_o00065_F_apply_link_at_specific_line(self, tmp_path: Path) -> None:
        f = tmp_path / "test.py"
        f.write_text("line1\nline2\nline3\n")
        apply_link_to_file(f, 2, "REQ-001")
        lines = f.read_text().splitlines()
        assert lines[1] == "# Implements: REQ-001"

    def test_REQ_o00065_F_apply_link_nonexistent_file(self) -> None:
        result = apply_link_to_file(Path("/nonexistent/file.py"), 1, "REQ-001")
        assert result is None

    def test_REQ_o00065_F_apply_link_dry_run_no_file_needed(self) -> None:
        result = apply_link_to_file(Path("/no/file"), 1, "REQ-001", dry_run=True)
        assert result is not None

    def test_REQ_o00065_F_apply_link_beyond_end_of_file(self, tmp_path: Path) -> None:
        f = tmp_path / "test.py"
        f.write_text("one line\n")
        apply_link_to_file(f, 999, "REQ-001")
        lines = f.read_text().splitlines()
        assert lines[-1] == "# Implements: REQ-001"

    def test_REQ_o00065_F_apply_link_preserves_encoding_lines(self, tmp_path: Path) -> None:
        f = tmp_path / "test.py"
        f.write_text("#!/usr/bin/env python\n# -*- coding: utf-8 -*-\ncode\n")
        apply_link_to_file(f, 0, "REQ-001")
        lines = f.read_text().splitlines()
        assert lines[0] == "#!/usr/bin/env python"
        assert lines[1] == "# -*- coding: utf-8 -*-"
        assert lines[2] == "# Implements: REQ-001"
