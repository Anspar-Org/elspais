# Verifies: REQ-d00254-D
"""Block-scoped // Implements: coverage attribution (CUR-1533).

When a CODE node has no function range (parse_line == parse_end_line,
function_line not set), coverage is attributed by *marker block*: a run
of consecutive marker lines with no executable (line_coverage) line
between them owns the executable lines that follow, up to the next block
or EOF.
"""

from elspais.graph.annotators import CoverageCreditConfig, annotate_coverage
from elspais.graph.metrics import RollupMetrics
from tests.core.graph_test_helpers import (
    build_graph,
    make_code_ref,
    make_requirement,
)


def _make_dart_code_ref(implements, source_path, marker_line):
    """Create a single-line code ref (no function range) simulating a Dart marker."""
    return make_code_ref(
        implements=implements,
        source_path=source_path,
        start_line=marker_line,
        end_line=marker_line,  # 1-line marker, no function range
    )


def _credit(**kwargs):
    defaults = {
        "app_dirs": ("lib",),
        "coverage_dirs": ("lib",),
        "assertion_credit": "tested",
        "min_coverage_fraction": 0.0,
    }
    defaults.update(kwargs)
    return CoverageCreditConfig(**defaults)


# ---------------------------------------------------------------------------
# Case 1: Single header block owns whole file
# ---------------------------------------------------------------------------


class TestSingleBlockOwnsWholeFile:
    """A single Dart marker at line 1 should own all executable lines in the file."""

    def test_single_block_credits_assertion(self):
        """Marker at line 1 with file line_coverage on lines 5-20 -> assertion credited."""
        req = make_requirement(
            "REQ-p00001",
            assertions=[{"label": "A", "text": "SHALL A"}],
        )
        code = _make_dart_code_ref(
            implements=["REQ-p00001-A"],
            source_path="lib/src/foo.dart",
            marker_line=1,
        )
        g = build_graph(req, code)

        # Add line_coverage: lines 5-20, half covered
        fn = g.find_by_id("file:lib/src/foo.dart")
        assert fn is not None
        lc = {ln: (1 if ln % 2 == 0 else 0) for ln in range(5, 21)}
        fn.set_field("line_coverage", lc)

        annotate_coverage(g, _credit())

        rollup: RollupMetrics = g.find_by_id("REQ-p00001").get_metric("rollup_metrics")
        assert rollup is not None
        assert (
            "A" in rollup.lcov_tested.indirect_labels
        ), "Assertion A should be credited via block-scoped attribution"
        assert rollup.lcov_tested.indirect > 0, "indirect coverage should be > 0"

    def test_single_block_code_tested_indirect(self):
        """code_tested.indirect should count covered lines in the block region."""
        req = make_requirement(
            "REQ-p00001",
            assertions=[{"label": "A", "text": "SHALL A"}],
        )
        code = _make_dart_code_ref(
            implements=["REQ-p00001"],
            source_path="lib/src/bar.dart",
            marker_line=3,
        )
        g = build_graph(req, code)

        fn = g.find_by_id("file:lib/src/bar.dart")
        # Lines 10-15: only 10,12,14 covered
        lc = {10: 1, 11: 0, 12: 1, 13: 0, 14: 1, 15: 0}
        fn.set_field("line_coverage", lc)

        annotate_coverage(g, _credit())

        rollup: RollupMetrics = g.find_by_id("REQ-p00001").get_metric("rollup_metrics")
        assert rollup is not None
        assert rollup.code_tested.indirect > 0, "code_tested.indirect should be > 0"


# ---------------------------------------------------------------------------
# Case 2: Two blocks partition the file
# ---------------------------------------------------------------------------


class TestTwoBlocksPartitionFile:
    """Two markers partition the file by the executable lines between them."""

    def test_two_markers_split_on_executable_line(self):
        """Blocks split when an executable line falls strictly between two markers."""
        req = make_requirement(
            "REQ-p00001",
            assertions=[
                {"label": "A", "text": "SHALL A"},
                {"label": "B", "text": "SHALL B"},
            ],
        )
        code_a = _make_dart_code_ref(
            implements=["REQ-p00001-A"],
            source_path="lib/src/split.dart",
            marker_line=1,
        )
        code_b = _make_dart_code_ref(
            implements=["REQ-p00001-B"],
            source_path="lib/src/split.dart",
            marker_line=8,
        )
        g = build_graph(req, code_a, code_b)

        fn = g.find_by_id("file:lib/src/split.dart")
        # Lines 3-5 owned by block1, lines 9-12 owned by block2
        # Line 5 is strictly between markers 1 and 8 -> causes split
        lc = {3: 1, 4: 1, 5: 1, 9: 1, 10: 1, 11: 0, 12: 0}
        fn.set_field("line_coverage", lc)

        annotate_coverage(g, _credit())

        rollup: RollupMetrics = g.find_by_id("REQ-p00001").get_metric("rollup_metrics")
        assert rollup is not None
        assert "A" in rollup.lcov_tested.indirect_labels, "A should be credited"
        assert "B" in rollup.lcov_tested.indirect_labels, "B should be credited"


# ---------------------------------------------------------------------------
# Case 3: Boundary detection
# ---------------------------------------------------------------------------


class TestBoundaryDetection:
    """Markers with only non-executable lines between them stay in one block."""

    def test_markers_with_no_executable_between_stay_one_block(self):
        """Two adjacent markers (no executable lines between) form one block."""
        req = make_requirement(
            "REQ-p00001",
            assertions=[
                {"label": "A", "text": "SHALL A"},
                {"label": "B", "text": "SHALL B"},
            ],
        )
        code_a = _make_dart_code_ref(
            implements=["REQ-p00001-A"],
            source_path="lib/src/adjacent.dart",
            marker_line=1,
        )
        code_b = _make_dart_code_ref(
            implements=["REQ-p00001-B"],
            source_path="lib/src/adjacent.dart",
            marker_line=2,
        )
        g = build_graph(req, code_a, code_b)

        fn = g.find_by_id("file:lib/src/adjacent.dart")
        # Lines 5-8 are after both markers -> both A and B should own them
        lc = {5: 1, 6: 1, 7: 1, 8: 0}
        fn.set_field("line_coverage", lc)

        annotate_coverage(g, _credit())

        rollup: RollupMetrics = g.find_by_id("REQ-p00001").get_metric("rollup_metrics")
        assert rollup is not None
        assert "A" in rollup.lcov_tested.indirect_labels, "A in same block should be credited"
        assert "B" in rollup.lcov_tested.indirect_labels, "B in same block should be credited"

    def test_executable_line_strictly_between_splits_blocks(self):
        """An executable line strictly between markers causes a block split."""
        req = make_requirement(
            "REQ-p00001",
            assertions=[
                {"label": "A", "text": "SHALL A"},
                {"label": "B", "text": "SHALL B"},
            ],
        )
        code_a = _make_dart_code_ref(
            implements=["REQ-p00001-A"],
            source_path="lib/src/split2.dart",
            marker_line=1,
        )
        code_b = _make_dart_code_ref(
            implements=["REQ-p00001-B"],
            source_path="lib/src/split2.dart",
            marker_line=10,
        )
        g = build_graph(req, code_a, code_b)

        fn = g.find_by_id("file:lib/src/split2.dart")
        # Line 5 between markers -> split -> block1=[1], block2=[10]
        # Block1 owns: lines > 1 and < 10 -> line 5
        # Block2 owns: lines > 10 -> line 20
        lc = {5: 1, 20: 1}
        fn.set_field("line_coverage", lc)

        annotate_coverage(g, _credit())

        rollup: RollupMetrics = g.find_by_id("REQ-p00001").get_metric("rollup_metrics")
        assert rollup is not None
        assert "A" in rollup.lcov_tested.indirect_labels, "A owns line 5"
        assert "B" in rollup.lcov_tested.indirect_labels, "B owns line 20"


# ---------------------------------------------------------------------------
# Case 4: Function range still wins (backward compatibility)
# ---------------------------------------------------------------------------


class TestFunctionRangeWins:
    """When impl range is multi-line (start != end), use range-based attribution."""

    def test_code_with_multi_line_range_uses_range(self):
        """CODE node with multi-line range (start != end) should use range attribution."""
        req = make_requirement(
            "REQ-p00001",
            assertions=[{"label": "A", "text": "SHALL A"}],
        )
        # Multi-line ref simulates a Python function
        code = make_code_ref(
            implements=["REQ-p00001-A"],
            source_path="lib/src/python_style.py",
            start_line=10,
            end_line=20,
        )
        g = build_graph(req, code)

        fn = g.find_by_id("file:lib/src/python_style.py")
        lc = dict.fromkeys(range(10, 21), 1)
        fn.set_field("line_coverage", lc)

        annotate_coverage(g, _credit(coverage_dirs=("lib",)))

        rollup: RollupMetrics = g.find_by_id("REQ-p00001").get_metric("rollup_metrics")
        assert rollup is not None
        assert (
            "A" in rollup.lcov_tested.indirect_labels
        ), "Range-based attribution should still work for multi-line refs"
        assert rollup.lcov_tested.indirect > 0


# ---------------------------------------------------------------------------
# Case 5: No coverage data -> no credit
# ---------------------------------------------------------------------------


class TestNoCoverageData:
    """FILE without line_coverage -> no credit."""

    def test_no_line_coverage_means_no_credit(self):
        """Without line_coverage on the FILE node, no block credit is given."""
        req = make_requirement(
            "REQ-p00001",
            assertions=[{"label": "A", "text": "SHALL A"}],
        )
        code = _make_dart_code_ref(
            implements=["REQ-p00001-A"],
            source_path="lib/src/nocov.dart",
            marker_line=1,
        )
        g = build_graph(req, code)
        # Intentionally do NOT set line_coverage on FILE node

        annotate_coverage(g, _credit())

        rollup: RollupMetrics = g.find_by_id("REQ-p00001").get_metric("rollup_metrics")
        assert rollup is not None
        assert rollup.lcov_tested.indirect_labels == set(), "No line_coverage means no credit"
        assert rollup.lcov_tested.indirect == 0.0
        assert rollup.code_tested.indirect == 0


# ---------------------------------------------------------------------------
# Case 6: Multi-line CODE ref does not truncate single-line marker's owned lines
# ---------------------------------------------------------------------------


class TestMultiLineRefIgnoredInBlockMarkers:
    """A multi-line CODE ref in the same file must NOT be included in the marker
    list used by _block_region_lines. Only single-line markers (parse_line ==
    parse_end_line) count as block boundaries.

    Regression: previously any CODE child was used as a marker, so a multi-line
    Python function at line 10 would truncate the single-line Dart marker at
    line 1's owned region to lines 1-9 instead of the whole file.
    """

    def test_single_line_marker_not_truncated_by_multiline_ref(self):
        """Single-line marker at line 1 owns lines after it even when a multi-line
        CODE ref starts at line 10 in the same file.
        """
        req = make_requirement(
            "REQ-p00001",
            assertions=[{"label": "A", "text": "SHALL A"}],
        )
        # Single-line Dart marker at line 1 (the one we care about)
        code_single = make_code_ref(
            implements=["REQ-p00001-A"],
            source_path="lib/src/mixed.dart",
            start_line=1,
            end_line=1,
        )
        # Multi-line CODE ref at lines 10-30 (should NOT count as a block marker)
        code_multi = make_code_ref(
            implements=["REQ-p00001-A"],
            source_path="lib/src/mixed.dart",
            start_line=10,
            end_line=30,
        )
        g = build_graph(req, code_single, code_multi)

        fn = g.find_by_id("file:lib/src/mixed.dart")
        assert fn is not None
        # Executable lines span past line 30 -- if multi-line ref were a marker,
        # block region for line 1 would stop at line 9.
        lc = {5: 1, 15: 1, 35: 1}
        fn.set_field("line_coverage", lc)

        from elspais.graph.annotators import _block_region_lines

        region = _block_region_lines(fn, {})

        # The single-line marker at line 1 should own ALL executable lines > 1
        # (lines 5, 15, 35). If multi-line ref at 10 were treated as a second
        # marker, region[1] would be {5} only (lines > 1 and < 10).
        assert 1 in region, "Single-line marker at line 1 must have a region entry"
        owned = region[1]
        assert 35 in owned, (
            "Single-line marker must own lines past the multi-line ref's start (35 > 10); "
            f"got owned={owned}. Multi-line ref should NOT be a block boundary."
        )
        assert 15 in owned, "Line 15 (inside multi-line ref range) must be in owned set"
        assert 5 in owned, "Line 5 (before multi-line ref) must be in owned set"
