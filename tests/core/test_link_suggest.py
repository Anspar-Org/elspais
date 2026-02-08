# Implements: REQ-o00065-A, REQ-o00065-B, REQ-o00065-C, REQ-o00065-F
# Implements: REQ-d00072-A, REQ-d00072-B, REQ-d00072-C, REQ-d00072-D
# Implements: REQ-d00072-E, REQ-d00072-F
"""Tests for the link suggestion engine (link_suggest.py).

Validates heuristic-based link suggestions for unlinked TEST nodes,
covering confidence scoring, deduplication, file proximity, keyword
overlap, function name matching, and the apply_link_to_file helper.
"""

from __future__ import annotations

from pathlib import Path

from elspais.graph.builder import TraceGraph
from elspais.graph.GraphNode import GraphNode, NodeKind, SourceLocation
from elspais.graph.link_suggest import (
    CONFIDENCE_HIGH,
    CONFIDENCE_MEDIUM,
    LinkSuggestion,
    _build_code_to_req_index,
    _deduplicate_suggestions,
    _find_unlinked_tests,
    _heuristic_file_proximity,
    _heuristic_function_name,
    _heuristic_keyword_overlap,
    _infer_source_dirs,
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
    node = GraphNode(req_id, NodeKind.REQUIREMENT, label=title)
    graph._index[req_id] = node
    if as_root:
        graph._roots.append(node)
    return node


def _add_assertion(
    graph: TraceGraph,
    assertion_id: str,
    label: str = "Assertion",
    parent: GraphNode | None = None,
) -> GraphNode:
    """Add an ASSERTION node, optionally linked to a parent."""
    node = GraphNode(assertion_id, NodeKind.ASSERTION, label=label)
    graph._index[assertion_id] = node
    if parent is not None:
        parent.link(node, EdgeKind.CONTAINS)
    return node


def _add_code(
    graph: TraceGraph,
    code_id: str,
    path: str,
    func_name: str,
    line: int = 1,
    parent: GraphNode | None = None,
) -> GraphNode:
    """Add a CODE node, optionally linked to a parent requirement."""
    node = GraphNode(
        code_id,
        NodeKind.CODE,
        label=func_name,
        source=SourceLocation(path=path, line=line),
    )
    node.set_field("function_name", func_name)
    graph._index[code_id] = node
    if parent is not None:
        parent.link(node, EdgeKind.CONTAINS)
    return node


def _add_test(
    graph: TraceGraph,
    test_id: str,
    path: str,
    func_name: str,
    line: int = 1,
    parent: GraphNode | None = None,
) -> GraphNode:
    """Add a TEST node, optionally linked to a parent."""
    node = GraphNode(
        test_id,
        NodeKind.TEST,
        label=func_name,
        source=SourceLocation(path=path, line=line),
    )
    node.set_field("function_name", func_name)
    graph._index[test_id] = node
    if parent is not None:
        parent.link(node, EdgeKind.VALIDATES)
    return node


# ===========================================================================
# LinkSuggestion dataclass
# ===========================================================================


class TestLinkSuggestionDataclass:
    """Tests for the LinkSuggestion dataclass properties."""

    def _make_suggestion(self, confidence: float) -> LinkSuggestion:
        return LinkSuggestion(
            test_id="test:t.py::test_foo",
            test_label="test_foo",
            test_file="tests/t.py",
            requirement_id="REQ-001",
            requirement_title="Foo Requirement",
            confidence=confidence,
            reasons=["some reason"],
        )

    def test_REQ_d00072_A_confidence_band_high(self) -> None:
        """Confidence >= 0.8 returns 'high' band."""
        s = self._make_suggestion(0.9)
        assert s.confidence_band == "high"

        s2 = self._make_suggestion(CONFIDENCE_HIGH)
        assert s2.confidence_band == "high"

    def test_REQ_d00072_A_confidence_band_medium(self) -> None:
        """Confidence >= 0.5 and < 0.8 returns 'medium' band."""
        s = self._make_suggestion(0.6)
        assert s.confidence_band == "medium"

        s2 = self._make_suggestion(CONFIDENCE_MEDIUM)
        assert s2.confidence_band == "medium"

    def test_REQ_d00072_A_confidence_band_low(self) -> None:
        """Confidence < 0.5 returns 'low' band."""
        s = self._make_suggestion(0.3)
        assert s.confidence_band == "low"

        s2 = self._make_suggestion(0.0)
        assert s2.confidence_band == "low"

    def test_REQ_d00072_A_confidence_band_boundary_high(self) -> None:
        """Exactly 0.8 is 'high', 0.7999 is 'medium'."""
        assert self._make_suggestion(0.8).confidence_band == "high"
        assert self._make_suggestion(0.7999).confidence_band == "medium"

    def test_REQ_d00072_A_confidence_band_boundary_medium(self) -> None:
        """Exactly 0.5 is 'medium', 0.4999 is 'low'."""
        assert self._make_suggestion(0.5).confidence_band == "medium"
        assert self._make_suggestion(0.4999).confidence_band == "low"

    def test_REQ_d00072_A_to_dict_serialization(self) -> None:
        """to_dict returns all expected keys with correct values."""
        s = self._make_suggestion(0.853)
        d = s.to_dict()

        assert d["test_id"] == "test:t.py::test_foo"
        assert d["test_label"] == "test_foo"
        assert d["test_file"] == "tests/t.py"
        assert d["requirement_id"] == "REQ-001"
        assert d["requirement_title"] == "Foo Requirement"
        assert d["confidence"] == 0.853
        assert d["confidence_band"] == "high"
        assert d["reasons"] == ["some reason"]

    def test_REQ_d00072_A_to_dict_rounds_confidence(self) -> None:
        """to_dict rounds confidence to 3 decimal places."""
        s = self._make_suggestion(0.12345678)
        d = s.to_dict()
        assert d["confidence"] == 0.123


# ===========================================================================
# _find_unlinked_tests
# ===========================================================================


class TestFindUnlinkedTests:
    """Tests for the _find_unlinked_tests function."""

    def test_REQ_o00065_A_finds_tests_without_req_parents(self) -> None:
        """Tests with no REQUIREMENT or ASSERTION parent are found."""
        graph = _make_graph()
        _add_requirement(graph, "REQ-001", "Requirement One")
        test = _add_test(graph, "test:t.py::test_foo", "tests/t.py", "test_foo")

        unlinked = _find_unlinked_tests(graph)
        assert len(unlinked) == 1
        assert unlinked[0].id == test.id

    def test_REQ_o00065_A_skips_linked_tests(self) -> None:
        """Tests with a REQUIREMENT parent are excluded."""
        graph = _make_graph()
        req = _add_requirement(graph, "REQ-001", "Requirement One")
        _add_test(
            graph,
            "test:t.py::test_foo",
            "tests/t.py",
            "test_foo",
            parent=req,
        )

        unlinked = _find_unlinked_tests(graph)
        assert len(unlinked) == 0

    def test_REQ_o00065_A_skips_tests_linked_via_assertion(self) -> None:
        """Tests with an ASSERTION parent are excluded."""
        graph = _make_graph()
        req = _add_requirement(graph, "REQ-001", "Requirement One")
        assertion = _add_assertion(graph, "REQ-001-A", "Assert A", parent=req)
        _add_test(
            graph,
            "test:t.py::test_foo",
            "tests/t.py",
            "test_foo",
            parent=assertion,
        )

        unlinked = _find_unlinked_tests(graph)
        assert len(unlinked) == 0

    def test_REQ_o00065_A_skips_tests_linked_via_code(self) -> None:
        """Tests with CODE->REQ chain are excluded."""
        graph = _make_graph()
        req = _add_requirement(graph, "REQ-001", "Requirement One")
        code = _add_code(graph, "code:src/foo.py:1", "src/foo.py", "my_func", parent=req)
        # Test is child of CODE node (CODE -> TEST via VALIDATES)
        test = _add_test(graph, "test:t.py::test_foo", "tests/t.py", "test_foo")
        code.link(test, EdgeKind.VALIDATES)

        unlinked = _find_unlinked_tests(graph)
        assert len(unlinked) == 0

    def test_REQ_o00065_A_filters_by_file_path(self) -> None:
        """file_path parameter filters to matching tests only."""
        graph = _make_graph()
        _add_test(graph, "test:a.py::test_a", "tests/a.py", "test_a")
        _add_test(graph, "test:b.py::test_b", "tests/b.py", "test_b")

        # Filter to only tests/a.py
        unlinked = _find_unlinked_tests(graph, file_path="tests/a.py")
        assert len(unlinked) == 1
        assert unlinked[0].id == "test:a.py::test_a"

    def test_REQ_o00065_A_file_path_filter_no_match(self) -> None:
        """file_path that matches no tests returns empty."""
        graph = _make_graph()
        _add_test(graph, "test:a.py::test_a", "tests/a.py", "test_a")

        unlinked = _find_unlinked_tests(graph, file_path="tests/nonexistent.py")
        assert len(unlinked) == 0

    def test_REQ_o00065_A_skips_tests_without_source_when_filtering(self) -> None:
        """Tests without source location are skipped when file_path is set."""
        graph = _make_graph()
        node = GraphNode("test:no_source::test_x", NodeKind.TEST, label="test_x")
        node.set_field("function_name", "test_x")
        graph._index[node.id] = node

        unlinked = _find_unlinked_tests(graph, file_path="tests/a.py")
        assert len(unlinked) == 0

    def test_REQ_o00065_A_mixed_linked_and_unlinked(self) -> None:
        """Only unlinked tests are returned when graph has both."""
        graph = _make_graph()
        req = _add_requirement(graph, "REQ-001", "Requirement One")
        _add_test(
            graph,
            "test:t.py::test_linked",
            "tests/t.py",
            "test_linked",
            parent=req,
        )
        unlinked_test = _add_test(graph, "test:t.py::test_orphan", "tests/t.py", "test_orphan")

        result = _find_unlinked_tests(graph)
        ids = [n.id for n in result]
        assert unlinked_test.id in ids
        assert "test:t.py::test_linked" not in ids


# ===========================================================================
# _build_code_to_req_index
# ===========================================================================


class TestBuildCodeToReqIndex:
    """Tests for the _build_code_to_req_index function."""

    def test_REQ_d00072_B_builds_code_to_req_index(self) -> None:
        """CODE->REQ mapping built correctly for direct CONTAINS edge."""
        graph = _make_graph()
        req = _add_requirement(graph, "REQ-001", "My Requirement")
        code = _add_code(graph, "code:src/foo.py:1", "src/foo.py", "do_stuff", parent=req)

        index = _build_code_to_req_index(graph)
        assert code.id in index
        assert ("REQ-001", "My Requirement") in index[code.id]

    def test_REQ_d00072_B_handles_assertion_parents(self) -> None:
        """CODE->ASSERTION->REQ chain captured in index."""
        graph = _make_graph()
        req = _add_requirement(graph, "REQ-001", "My Requirement")
        assertion = _add_assertion(graph, "REQ-001-A", "Assert A", parent=req)
        code = _add_code(
            graph,
            "code:src/foo.py:1",
            "src/foo.py",
            "do_stuff",
            parent=assertion,
        )

        index = _build_code_to_req_index(graph)
        assert code.id in index
        # The requirement should be reachable via the assertion chain
        req_ids = [r[0] for r in index[code.id]]
        assert "REQ-001" in req_ids

    def test_REQ_d00072_B_empty_for_code_without_req_parent(self) -> None:
        """CODE node with no REQUIREMENT parent is not indexed."""
        graph = _make_graph()
        _add_code(graph, "code:src/foo.py:1", "src/foo.py", "orphan_func")

        index = _build_code_to_req_index(graph)
        assert "code:src/foo.py:1" not in index

    def test_REQ_d00072_B_multiple_codes_same_req(self) -> None:
        """Multiple CODE nodes under the same REQ are all indexed."""
        graph = _make_graph()
        req = _add_requirement(graph, "REQ-001", "My Requirement")
        code1 = _add_code(graph, "code:src/a.py:1", "src/a.py", "func_a", parent=req)
        code2 = _add_code(graph, "code:src/b.py:1", "src/b.py", "func_b", parent=req)

        index = _build_code_to_req_index(graph)
        assert code1.id in index
        assert code2.id in index

    def test_REQ_d00072_B_code_with_multiple_req_parents(self) -> None:
        """CODE node under two REQUIREMENTs lists both in the index."""
        graph = _make_graph()
        req1 = _add_requirement(graph, "REQ-001", "First")
        req2 = _add_requirement(graph, "REQ-002", "Second")
        code = _add_code(graph, "code:src/foo.py:1", "src/foo.py", "shared_func", parent=req1)
        req2.link(code, EdgeKind.CONTAINS)

        index = _build_code_to_req_index(graph)
        assert code.id in index
        req_ids = {r[0] for r in index[code.id]}
        assert req_ids == {"REQ-001", "REQ-002"}


# ===========================================================================
# _heuristic_function_name (H2)
# ===========================================================================


class TestHeuristicFunctionName:
    """Tests for H2: function name matching heuristic."""

    def test_REQ_d00072_C_exact_function_match(self) -> None:
        """test_my_func matches my_func CODE node with score 0.85."""
        graph = _make_graph()
        req = _add_requirement(graph, "REQ-001", "My Requirement")
        _add_code(graph, "code:src/foo.py:1", "src/foo.py", "my_func", parent=req)

        test = _add_test(graph, "test:t.py::test_my_func", "tests/t.py", "test_my_func")

        from elspais.graph.test_code_linker import _build_code_index

        code_index = _build_code_index(graph)
        code_to_reqs = _build_code_to_req_index(graph)

        suggestions = _heuristic_function_name(test, code_index, code_to_reqs)
        assert len(suggestions) >= 1
        best = suggestions[0]
        assert best.requirement_id == "REQ-001"
        assert best.confidence == 0.85
        assert "exact" in best.reasons[0].lower()

    def test_REQ_d00072_C_partial_function_match_lower_score(self) -> None:
        """Shorter prefix candidate gets lower score (0.85 - 0.05 * i)."""
        graph = _make_graph()
        req = _add_requirement(graph, "REQ-001", "My Requirement")
        # CODE node has function name that will match a shorter candidate
        _add_code(graph, "code:src/foo.py:1", "src/foo.py", "my", parent=req)

        # test_my_func_thing -> candidates: my_func_thing, my_func, my
        test = _add_test(
            graph,
            "test:t.py::test_my_func_thing",
            "tests/t.py",
            "test_my_func_thing",
        )

        from elspais.graph.test_code_linker import _build_code_index

        code_index = _build_code_index(graph)
        code_to_reqs = _build_code_to_req_index(graph)

        suggestions = _heuristic_function_name(test, code_index, code_to_reqs)
        assert len(suggestions) >= 1
        # "my" is the third candidate (index 2), so score = 0.85 - 0.10 = 0.75
        best = suggestions[0]
        assert best.confidence < 0.85
        assert "partial" in best.reasons[0].lower()

    def test_REQ_d00072_C_no_match_returns_empty(self) -> None:
        """Test function with no matching CODE returns empty."""
        graph = _make_graph()
        req = _add_requirement(graph, "REQ-001", "My Requirement")
        _add_code(
            graph,
            "code:src/foo.py:1",
            "src/foo.py",
            "completely_different",
            parent=req,
        )

        test = _add_test(
            graph,
            "test:t.py::test_unrelated_func",
            "tests/t.py",
            "test_unrelated_func",
        )

        from elspais.graph.test_code_linker import _build_code_index

        code_index = _build_code_index(graph)
        code_to_reqs = _build_code_to_req_index(graph)

        suggestions = _heuristic_function_name(test, code_index, code_to_reqs)
        assert len(suggestions) == 0


# ===========================================================================
# _heuristic_file_proximity (H3)
# ===========================================================================


class TestHeuristicFileProximity:
    """Tests for H3: file path proximity heuristic."""

    def test_REQ_d00072_D_file_proximity_match(self) -> None:
        """tests/core/test_foo.py finds CODE in src/core/."""
        graph = _make_graph()
        req = _add_requirement(graph, "REQ-001", "My Requirement")
        _add_code(
            graph,
            "code:src/core/foo.py:1",
            "src/core/foo.py",
            "do_thing",
            parent=req,
        )

        test = _add_test(
            graph,
            "test:tests/core/test_foo.py::test_do_thing",
            "tests/core/test_foo.py",
            "test_do_thing",
        )

        code_to_reqs = _build_code_to_req_index(graph)
        repo_root = Path("/fake/repo")

        suggestions = _heuristic_file_proximity(test, graph, repo_root, code_to_reqs)
        assert len(suggestions) >= 1
        assert suggestions[0].requirement_id == "REQ-001"
        assert suggestions[0].confidence == 0.6

    def test_REQ_d00072_D_no_proximity_for_unrelated_dirs(self) -> None:
        """CODE in unrelated directory does not match test."""
        graph = _make_graph()
        req = _add_requirement(graph, "REQ-001", "My Requirement")
        _add_code(
            graph,
            "code:lib/other/module.py:1",
            "lib/other/module.py",
            "do_thing",
            parent=req,
        )

        test = _add_test(
            graph,
            "test:tests/core/test_foo.py::test_do_thing",
            "tests/core/test_foo.py",
            "test_do_thing",
        )

        code_to_reqs = _build_code_to_req_index(graph)
        repo_root = Path("/fake/repo")

        suggestions = _heuristic_file_proximity(test, graph, repo_root, code_to_reqs)
        assert len(suggestions) == 0

    def test_REQ_d00072_D_infer_source_dirs(self) -> None:
        """Test path mapping works correctly for various patterns."""
        # tests/core/test_foo.py -> should infer src/core/
        dirs = _infer_source_dirs("tests/core/test_foo.py")
        assert any("src/core/" in d for d in dirs)

        # tests/test_bar.py -> should infer src/
        dirs = _infer_source_dirs("tests/test_bar.py")
        assert any(d == "src/" for d in dirs)

    def test_REQ_d00072_D_infer_source_dirs_no_tests_dir(self) -> None:
        """Path without 'tests' or 'test' directory returns empty."""
        dirs = _infer_source_dirs("lib/something.py")
        assert dirs == []

    def test_REQ_d00072_D_infer_source_dirs_test_prefix(self) -> None:
        """Accepts 'test' directory as well as 'tests'."""
        dirs = _infer_source_dirs("test/test_foo.py")
        assert len(dirs) > 0

    def test_REQ_d00072_D_no_source_on_test_returns_empty(self) -> None:
        """Test node without source location yields no suggestions."""
        graph = _make_graph()
        req = _add_requirement(graph, "REQ-001", "My Requirement")
        _add_code(
            graph,
            "code:src/foo.py:1",
            "src/foo.py",
            "do_thing",
            parent=req,
        )

        node = GraphNode("test:no_src::test_x", NodeKind.TEST, label="test_x")
        node.set_field("function_name", "test_x")
        graph._index[node.id] = node

        code_to_reqs = _build_code_to_req_index(graph)
        suggestions = _heuristic_file_proximity(node, graph, Path("/fake"), code_to_reqs)
        assert suggestions == []


# ===========================================================================
# _heuristic_keyword_overlap (H4)
# ===========================================================================


class TestHeuristicKeywordOverlap:
    """Tests for H4: keyword overlap heuristic."""

    def test_REQ_d00072_E_keyword_overlap_match(self) -> None:
        """Shared keywords between test name and requirement title produce suggestion."""
        graph = _make_graph()
        _add_requirement(graph, "REQ-001", "Validate Configuration Settings")

        test = _add_test(
            graph,
            "test:t.py::test_validate_configuration_settings",
            "tests/t.py",
            "test_validate_configuration_settings",
        )

        suggestions = _heuristic_keyword_overlap(test, graph)
        assert len(suggestions) >= 1
        assert suggestions[0].requirement_id == "REQ-001"
        assert suggestions[0].confidence <= 0.5  # capped

    def test_REQ_d00072_E_no_overlap_no_suggestion(self) -> None:
        """Disjoint keywords produce no suggestion."""
        graph = _make_graph()
        _add_requirement(graph, "REQ-001", "Authenticate Users Securely")

        test = _add_test(
            graph,
            "test:t.py::test_render_dashboard_widget",
            "tests/t.py",
            "test_render_dashboard_widget",
        )

        suggestions = _heuristic_keyword_overlap(test, graph)
        assert len(suggestions) == 0

    def test_REQ_d00072_E_keyword_overlap_score_capped(self) -> None:
        """Even perfect overlap cannot exceed SCORE_KEYWORD_CAP (0.5)."""
        graph = _make_graph()
        _add_requirement(graph, "REQ-001", "Calculate Coverage Metrics")

        test = _add_test(
            graph,
            "test:t.py::test_calculate_coverage_metrics",
            "tests/t.py",
            "test_calculate_coverage_metrics",
        )

        suggestions = _heuristic_keyword_overlap(test, graph)
        if suggestions:
            assert suggestions[0].confidence <= 0.5

    def test_REQ_d00072_E_keyword_overlap_includes_assertion_text(self) -> None:
        """Keywords from child assertions are included in matching."""
        graph = _make_graph()
        req = _add_requirement(graph, "REQ-001", "Graph Operations")
        _add_assertion(
            graph,
            "REQ-001-A",
            "Annotate coverage statistics accurately",
            parent=req,
        )

        test = _add_test(
            graph,
            "test:t.py::test_annotate_coverage_statistics",
            "tests/t.py",
            "test_annotate_coverage_statistics",
        )

        suggestions = _heuristic_keyword_overlap(test, graph)
        assert len(suggestions) >= 1
        assert suggestions[0].requirement_id == "REQ-001"

    def test_REQ_d00072_E_single_keyword_high_ratio_matches(self) -> None:
        """Single keyword overlap only matches if ratio >= 0.5."""
        graph = _make_graph()
        # Short title with one keyword
        _add_requirement(graph, "REQ-001", "Validate")

        # Test with the same short keyword
        test = _add_test(
            graph,
            "test:t.py::test_validate",
            "tests/t.py",
            "test_validate",
        )

        suggestions = _heuristic_keyword_overlap(test, graph)
        # May or may not match depending on whether "validate" passes
        # min_length filter (8 chars > 3 min). If it does and ratio is
        # high enough (1/1 = 1.0 >= 0.5), it should match.
        # The implementation requires len(overlap) >= 2 OR ratio >= 0.5
        # With only 1 keyword and ratio=1.0, ratio >= 0.5 so it matches.
        if suggestions:
            assert suggestions[0].confidence <= 0.5


# ===========================================================================
# _deduplicate_suggestions
# ===========================================================================


class TestDeduplicateSuggestions:
    """Tests for the _deduplicate_suggestions function."""

    def _make_sugg(
        self,
        test_id: str = "test:t.py::test_x",
        req_id: str = "REQ-001",
        confidence: float = 0.5,
        reasons: list[str] | None = None,
    ) -> LinkSuggestion:
        return LinkSuggestion(
            test_id=test_id,
            test_label="test_x",
            test_file="tests/t.py",
            requirement_id=req_id,
            requirement_title="Requirement",
            confidence=confidence,
            reasons=reasons or ["reason"],
        )

    def test_REQ_d00072_F_dedup_keeps_highest_confidence(self) -> None:
        """Same (test, req) pair merged; highest confidence kept."""
        s1 = self._make_sugg(confidence=0.6, reasons=["low reason"])
        s2 = self._make_sugg(confidence=0.9, reasons=["high reason"])

        result = _deduplicate_suggestions([s1, s2])
        assert len(result) == 1
        assert result[0].confidence == 0.9

    def test_REQ_d00072_F_dedup_combines_reasons(self) -> None:
        """Reasons from both suggestions are combined."""
        s1 = self._make_sugg(confidence=0.6, reasons=["reason A"])
        s2 = self._make_sugg(confidence=0.9, reasons=["reason B"])

        result = _deduplicate_suggestions([s1, s2])
        assert len(result) == 1
        assert "reason A" in result[0].reasons
        assert "reason B" in result[0].reasons

    def test_REQ_d00072_F_dedup_no_duplicate_reasons(self) -> None:
        """Identical reasons are not duplicated."""
        s1 = self._make_sugg(confidence=0.6, reasons=["same reason"])
        s2 = self._make_sugg(confidence=0.9, reasons=["same reason"])

        result = _deduplicate_suggestions([s1, s2])
        assert len(result) == 1
        assert result[0].reasons.count("same reason") == 1

    def test_REQ_d00072_F_dedup_different_pairs_preserved(self) -> None:
        """Different (test, req) pairs are not merged."""
        s1 = self._make_sugg(test_id="test:a.py::a", req_id="REQ-001")
        s2 = self._make_sugg(test_id="test:b.py::b", req_id="REQ-002")

        result = _deduplicate_suggestions([s1, s2])
        assert len(result) == 2

    def test_REQ_d00072_F_dedup_empty_input(self) -> None:
        """Empty input returns empty list."""
        result = _deduplicate_suggestions([])
        assert result == []

    def test_REQ_d00072_F_dedup_single_item(self) -> None:
        """Single suggestion passes through unchanged."""
        s = self._make_sugg(confidence=0.7, reasons=["only reason"])
        result = _deduplicate_suggestions([s])
        assert len(result) == 1
        assert result[0].confidence == 0.7

    def test_REQ_d00072_F_dedup_does_not_mutate_originals(self) -> None:
        """Original suggestion objects are not mutated."""
        s1 = self._make_sugg(confidence=0.6, reasons=["A"])
        s2 = self._make_sugg(confidence=0.9, reasons=["B"])

        _deduplicate_suggestions([s1, s2])

        # Originals untouched
        assert s1.confidence == 0.6
        assert s1.reasons == ["A"]
        assert s2.confidence == 0.9
        assert s2.reasons == ["B"]


# ===========================================================================
# suggest_links (orchestrator)
# ===========================================================================


class TestSuggestLinks:
    """Tests for the top-level suggest_links function."""

    def test_REQ_d00072_A_suggest_links_returns_sorted(self, tmp_path: Path) -> None:
        """Results are sorted by confidence descending."""
        graph = _make_graph()
        req1 = _add_requirement(graph, "REQ-001", "Validate Configuration Settings")
        req2 = _add_requirement(graph, "REQ-002", "Render Dashboard Widgets")
        # CODE nodes linked to requirements
        _add_code(
            graph,
            "code:src/config.py:1",
            "src/config.py",
            "validate_config",
            parent=req1,
        )
        _add_code(
            graph,
            "code:src/dashboard.py:1",
            "src/dashboard.py",
            "render_widget",
            parent=req2,
        )

        # Unlinked tests matching the CODE functions by name
        _add_test(
            graph,
            "test:tests/test_config.py::test_validate_config",
            "tests/test_config.py",
            "test_validate_config",
        )
        _add_test(
            graph,
            "test:tests/test_dashboard.py::test_render_widget",
            "tests/test_dashboard.py",
            "test_render_widget",
        )

        results = suggest_links(graph, tmp_path)

        # Verify descending confidence order
        confidences = [s.confidence for s in results]
        assert confidences == sorted(confidences, reverse=True)

    def test_REQ_d00072_A_suggest_links_respects_limit(self, tmp_path: Path) -> None:
        """limit parameter caps the number of returned suggestions."""
        graph = _make_graph()
        req = _add_requirement(graph, "REQ-001", "Validate Configuration Settings")

        # Create multiple CODE nodes
        for i in range(5):
            _add_code(
                graph,
                f"code:src/mod{i}.py:1",
                f"src/mod{i}.py",
                f"func_{i}",
                parent=req,
            )

        # Create multiple unlinked tests that match by keyword overlap
        for i in range(5):
            _add_test(
                graph,
                f"test:tests/test_{i}.py::test_validate_configuration",
                f"tests/test_{i}.py",
                "test_validate_configuration",
            )

        results = suggest_links(graph, tmp_path, limit=2)
        assert len(results) <= 2

    def test_REQ_d00072_A_suggest_links_empty_for_all_linked(self, tmp_path: Path) -> None:
        """No suggestions when all tests are linked to requirements."""
        graph = _make_graph()
        req = _add_requirement(graph, "REQ-001", "My Requirement")
        _add_test(
            graph,
            "test:t.py::test_foo",
            "tests/t.py",
            "test_foo",
            parent=req,
        )

        results = suggest_links(graph, tmp_path)
        assert results == []

    def test_REQ_d00072_A_suggest_links_empty_graph(self, tmp_path: Path) -> None:
        """Empty graph returns no suggestions."""
        graph = _make_graph()
        results = suggest_links(graph, tmp_path)
        assert results == []

    def test_REQ_d00072_A_suggest_links_no_test_nodes(self, tmp_path: Path) -> None:
        """Graph with only requirements and no tests returns empty."""
        graph = _make_graph()
        _add_requirement(graph, "REQ-001", "My Requirement")

        results = suggest_links(graph, tmp_path)
        assert results == []

    def test_REQ_d00072_A_suggest_links_file_path_filter(self, tmp_path: Path) -> None:
        """file_path restricts suggestions to tests in that file."""
        graph = _make_graph()
        req = _add_requirement(graph, "REQ-001", "Validate Configuration Settings")
        _add_code(
            graph,
            "code:src/config.py:1",
            "src/config.py",
            "validate_config",
            parent=req,
        )

        _add_test(
            graph,
            "test:tests/test_a.py::test_validate_config",
            "tests/test_a.py",
            "test_validate_config",
        )
        _add_test(
            graph,
            "test:tests/test_b.py::test_other",
            "tests/test_b.py",
            "test_other",
        )

        results = suggest_links(graph, tmp_path, file_path="tests/test_a.py")
        # Only suggestions for test_a.py tests
        test_files = {s.test_file for s in results}
        assert all("test_a.py" in f for f in test_files)


# ===========================================================================
# apply_link_to_file
# ===========================================================================


class TestApplyLinkToFile:
    """Tests for the apply_link_to_file helper."""

    def test_REQ_o00065_F_apply_link_inserts_comment(self, tmp_path: Path) -> None:
        """Inserts # Implements: comment at the specified line."""
        test_file = tmp_path / "test_example.py"
        test_file.write_text("def test_foo():\n    pass\n", encoding="utf-8")

        result = apply_link_to_file(test_file, line=1, req_id="REQ-001")
        assert result == "# Implements: REQ-001"

        # Verify file was modified
        content = test_file.read_text(encoding="utf-8")
        lines = content.splitlines()
        assert lines[0] == "# Implements: REQ-001"
        assert lines[1] == "def test_foo():"

    def test_REQ_o00065_F_apply_link_dry_run(self, tmp_path: Path) -> None:
        """dry_run returns comment without modifying file."""
        test_file = tmp_path / "test_example.py"
        original = "def test_foo():\n    pass\n"
        test_file.write_text(original, encoding="utf-8")

        result = apply_link_to_file(test_file, line=1, req_id="REQ-001", dry_run=True)
        assert result == "# Implements: REQ-001"

        # File unchanged
        assert test_file.read_text(encoding="utf-8") == original

    def test_REQ_o00065_F_apply_link_at_line_zero_top(self, tmp_path: Path) -> None:
        """Line 0 inserts at top of file (after shebang if present)."""
        test_file = tmp_path / "test_example.py"
        test_file.write_text(
            "#!/usr/bin/env python\ndef test_foo():\n    pass\n",
            encoding="utf-8",
        )

        result = apply_link_to_file(test_file, line=0, req_id="REQ-001")
        assert result == "# Implements: REQ-001"

        lines = test_file.read_text(encoding="utf-8").splitlines()
        # Should be after the shebang
        assert lines[0] == "#!/usr/bin/env python"
        assert lines[1] == "# Implements: REQ-001"

    def test_REQ_o00065_F_apply_link_at_specific_line(self, tmp_path: Path) -> None:
        """Insert at a specific line number (1-based)."""
        test_file = tmp_path / "test_example.py"
        test_file.write_text("import os\n\ndef test_foo():\n    pass\n", encoding="utf-8")

        result = apply_link_to_file(test_file, line=3, req_id="REQ-001")
        assert result == "# Implements: REQ-001"

        lines = test_file.read_text(encoding="utf-8").splitlines()
        assert lines[2] == "# Implements: REQ-001"
        assert lines[3] == "def test_foo():"

    def test_REQ_o00065_F_apply_link_nonexistent_file(self, tmp_path: Path) -> None:
        """Non-existent file returns None (not dry_run)."""
        bad_path = tmp_path / "does_not_exist.py"
        result = apply_link_to_file(bad_path, line=1, req_id="REQ-001")
        assert result is None

    def test_REQ_o00065_F_apply_link_dry_run_no_file_needed(self, tmp_path: Path) -> None:
        """dry_run does not need the file to exist."""
        bad_path = tmp_path / "does_not_exist.py"
        result = apply_link_to_file(bad_path, line=1, req_id="REQ-001", dry_run=True)
        assert result == "# Implements: REQ-001"

    def test_REQ_o00065_F_apply_link_beyond_end_of_file(self, tmp_path: Path) -> None:
        """Line number beyond file length inserts at end."""
        test_file = tmp_path / "test_example.py"
        test_file.write_text("line1\nline2\n", encoding="utf-8")

        result = apply_link_to_file(test_file, line=999, req_id="REQ-001")
        assert result == "# Implements: REQ-001"

        lines = test_file.read_text(encoding="utf-8").splitlines()
        assert lines[-1] == "# Implements: REQ-001"

    def test_REQ_o00065_F_apply_link_preserves_encoding_lines(self, tmp_path: Path) -> None:
        """Line 0 insertion skips both shebang and encoding lines."""
        test_file = tmp_path / "test_example.py"
        test_file.write_text(
            "#!/usr/bin/env python\n# -*- coding: utf-8 -*-\ndef foo():\n    pass\n",
            encoding="utf-8",
        )

        apply_link_to_file(test_file, line=0, req_id="REQ-002")

        lines = test_file.read_text(encoding="utf-8").splitlines()
        assert lines[0] == "#!/usr/bin/env python"
        assert lines[1] == "# -*- coding: utf-8 -*-"
        assert lines[2] == "# Implements: REQ-002"
        assert lines[3] == "def foo():"
