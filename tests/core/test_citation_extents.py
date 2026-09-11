# Verifies: REQ-d00254-D
"""// Implements: coverage attribution (CUR-1533).

``_citation_extents`` answers a whole file at once, because three of its four
bounds are relationships BETWEEN citations rather than properties of any one
of them:

* Citations with no executable (``line_coverage``) line between them form one
  RUN and share one answer.
* A run written ABOVE a function attributes that function's EXECUTABLE lines.
* Any other run attributes the executable lines FOLLOWING it, up to the
  earliest of the next citation, the end of its enclosing function, or the
  end of the file.
* A run above a function therefore overlaps the runs inside it. That is the
  only overlap admitted.

Only a line that can appear in the numerator may stand in the denominator, so
every rule counts executable lines and nothing else -- a function's extent is
a BOUND, never a list of its lines. A docstring, a blank and a comment sit
inside a function and no run can reach them. The coverage map is the only
thing that knows which lines are code, so every rule attributes nothing at
all until one is ingested: an absent figure, never a false one.

How many lines a citation's own comment occupies enters none of this
(REQ-d00269-M). A citation spans several lines whenever its reference list is
continued (REQ-d00269-H), and it attributes what a one-line citation in the
same place would; a citation's comment lines are never its implementation.

``TestCitationExtentRules`` pins the four rules one by one; the cases above it
exercise them through the coverage metrics.  Case 9, at the foot of the file,
chains the pre-scan to the rules, because which function a citation was read
as written above is what decides which of the four it is answered by.
"""

from pathlib import Path

import pytest

from elspais.graph.aggregation import covered_labels
from elspais.graph.annotators import CoverageCreditConfig, annotate_coverage
from elspais.graph.GraphNode import make_file_id
from elspais.graph.metrics import RollupMetrics
from tests.core.graph_test_helpers import (
    HELPER_NAMESPACE,
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
# Case 1: a single run owns the whole file
# ---------------------------------------------------------------------------


class TestSingleRunOwnsWholeFile:
    """A single Dart marker at line 1 should own all executable lines in the file."""

    def test_single_run_credits_assertion(self):
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
        fn = g.find_by_id(make_file_id(HELPER_NAMESPACE, "lib/src/foo.dart"))
        assert fn is not None
        lc = {ln: (1 if ln % 2 == 0 else 0) for ln in range(5, 21)}
        fn.set_field("line_coverage", lc)

        annotate_coverage(g, _credit())

        rollup: RollupMetrics = g.find_by_id("REQ-p00001").get_metric("rollup_metrics")
        assert rollup is not None
        assert "A" in covered_labels(rollup.lcov_tested, "total"), (
            "Assertion A should be credited from the run's extent"
        )
        assert rollup.lcov_tested.covered > 0, "indirect coverage should be > 0"

    def test_single_run_code_tested_indirect(self):
        """code_tested.covered should count covered lines in the run's extent."""
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

        fn = g.find_by_id(make_file_id(HELPER_NAMESPACE, "lib/src/bar.dart"))
        # Lines 10-15: only 10,12,14 covered
        lc = {10: 1, 11: 0, 12: 1, 13: 0, 14: 1, 15: 0}
        fn.set_field("line_coverage", lc)

        annotate_coverage(g, _credit())

        rollup: RollupMetrics = g.find_by_id("REQ-p00001").get_metric("rollup_metrics")
        assert rollup is not None
        assert rollup.code_tested.covered_lines > 0, "covered_lines should be > 0"


# ---------------------------------------------------------------------------
# Case 2: two runs partition the file
# ---------------------------------------------------------------------------


class TestTwoRunsPartitionFile:
    """Two markers partition the file by the executable lines between them."""

    def test_two_markers_split_on_executable_line(self):
        """Runs split when an executable line falls strictly between two citations."""
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

        fn = g.find_by_id(make_file_id(HELPER_NAMESPACE, "lib/src/split.dart"))
        # Lines 3-5 owned by the first run, lines 9-12 by the second
        # Line 5 is strictly between markers 1 and 8 -> causes split
        lc = {3: 1, 4: 1, 5: 1, 9: 1, 10: 1, 11: 0, 12: 0}
        fn.set_field("line_coverage", lc)

        annotate_coverage(g, _credit())

        rollup: RollupMetrics = g.find_by_id("REQ-p00001").get_metric("rollup_metrics")
        assert rollup is not None
        assert "A" in covered_labels(rollup.lcov_tested, "total"), "A should be credited"
        assert "B" in covered_labels(rollup.lcov_tested, "total"), "B should be credited"


# ---------------------------------------------------------------------------
# Case 3: Boundary detection
# ---------------------------------------------------------------------------


class TestBoundaryDetection:
    """Citations with only non-executable lines between them stay in one run."""

    def test_citations_with_no_executable_between_stay_one_run(self):
        """Two adjacent citations (no executable lines between) form one run."""
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

        fn = g.find_by_id(make_file_id(HELPER_NAMESPACE, "lib/src/adjacent.dart"))
        # Lines 5-8 are after both markers -> both A and B should own them
        lc = {5: 1, 6: 1, 7: 1, 8: 0}
        fn.set_field("line_coverage", lc)

        annotate_coverage(g, _credit())

        rollup: RollupMetrics = g.find_by_id("REQ-p00001").get_metric("rollup_metrics")
        assert rollup is not None
        assert "A" in covered_labels(rollup.lcov_tested, "total"), (
            "A in the same run should be credited"
        )
        assert "B" in covered_labels(rollup.lcov_tested, "total"), (
            "B in the same run should be credited"
        )

    def test_executable_line_strictly_between_splits_runs(self):
        """An executable line strictly between citations splits the run."""
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

        fn = g.find_by_id(make_file_id(HELPER_NAMESPACE, "lib/src/split2.dart"))
        # Line 5 between citations -> split -> runs at [1] and [10]
        # First run owns: lines > 1 and < 10 -> line 5
        # Second run owns: lines > 10 -> line 20
        lc = {5: 1, 20: 1}
        fn.set_field("line_coverage", lc)

        annotate_coverage(g, _credit())

        rollup: RollupMetrics = g.find_by_id("REQ-p00001").get_metric("rollup_metrics")
        assert rollup is not None
        assert "A" in covered_labels(rollup.lcov_tested, "total"), "A owns line 5"
        assert "B" in covered_labels(rollup.lcov_tested, "total"), "B owns line 20"


# ---------------------------------------------------------------------------
# Case 4: a run above a function is answered by that function
# ---------------------------------------------------------------------------


class TestFunctionRangeWins:
    """A citation that SITS IN A FUNCTION attributes that function's lines.

    The choice is made by whether the citation has an enclosing function, and
    by nothing else (REQ-d00254-D). The comment the citation is written in may
    occupy one line or several -- a continued reference list (REQ-d00269-H)
    occupies two -- and that division must not change the answer
    (REQ-d00269-M), so both spellings are run against the same function.
    """

    # A function at lines 10-20, fully exercised; two further executable
    # lines below it that were never run. Run attribution would sweep 25
    # and 26 in (13 lines, 11 covered); the function's own range must not.
    _COVERAGE = {**dict.fromkeys(range(10, 21), 1), 25: 0, 26: 0}

    # Verifies: REQ-d00254-D, REQ-d00269-M
    @pytest.mark.parametrize(
        ("comment_start", "comment_end"),
        [(9, 9), (8, 9)],
        ids=["one-line-comment", "continued-comment"],
    )
    def test_function_bound_citation_attributes_its_function(self, comment_start, comment_end):
        req = make_requirement(
            "REQ-p00001",
            assertions=[{"label": "A", "text": "SHALL A"}],
        )
        code = make_code_ref(
            implements=["REQ-p00001-A"],
            source_path="lib/src/python_style.py",
            start_line=comment_start,
            end_line=comment_end,
            function_name="do_thing",
            function_line=10,
            function_end_line=20,
        )
        g = build_graph(req, code)

        fn = g.find_by_id(make_file_id(HELPER_NAMESPACE, "lib/src/python_style.py"))
        fn.set_field("line_coverage", dict(self._COVERAGE))

        annotate_coverage(g, _credit(coverage_dirs=("lib",)))

        rollup: RollupMetrics = g.find_by_id("REQ-p00001").get_metric("rollup_metrics")
        assert rollup is not None
        assert rollup.code_tested.total_lines == 11, (
            f"the function's lines are attributed, not the code below it; got {rollup.code_tested}"
        )
        assert rollup.code_tested.covered_lines == 11
        # Every attributed line ran, so the credit is whole. Under run
        # attribution the unexercised lines 25 and 26 would drag it to 11/13.
        assert rollup.lcov_tested.immediate_direct_by_label == pytest.approx({"A": 1.0})


# ---------------------------------------------------------------------------
# Case 5: No coverage data -> no credit
# ---------------------------------------------------------------------------


class TestNoCoverageData:
    """FILE without line_coverage -> no credit."""

    def test_no_line_coverage_means_no_credit(self):
        """Without line_coverage on the FILE node, nothing is attributed."""
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
        assert covered_labels(rollup.lcov_tested, "total") == set(), (
            "No line_coverage means no credit"
        )
        assert rollup.lcov_tested.covered == 0.0
        assert rollup.code_tested.covered_lines == 0


# ---------------------------------------------------------------------------
# Case 6: a continued citation starts a run like any other
# ---------------------------------------------------------------------------


class TestContinuedCitationStartsItsOwnRun:
    """A citation whose reference list is continued onto a second comment line
    (REQ-d00269-H) starts a run exactly as a one-line citation does.

    The retired rule counted only single-line citations as boundaries, so the
    code a continued citation preceded was credited to whichever requirement
    the PREVIOUS citation named -- evidence attributed to a requirement nobody
    cited there. Under REQ-d00269-M the division of a reference list decides
    nothing, so the two citations partition the file between them.
    """

    # Verifies: REQ-d00269-M, REQ-d00254-D
    def test_two_citations_partition_the_covered_lines(self):
        from elspais.graph.annotators import _citation_extents

        req = make_requirement(
            "REQ-p00001",
            assertions=[
                {"label": "A", "text": "SHALL A"},
                {"label": "B", "text": "SHALL B"},
            ],
        )
        # A one-line citation at line 1 ...
        code_single = make_code_ref(
            implements=["REQ-p00001-A"],
            source_path="lib/src/mixed.dart",
            start_line=1,
            end_line=1,
        )
        # ... and a citation at lines 10-11 whose list is continued.
        code_continued = make_code_ref(
            implements=["REQ-p00001-B"],
            source_path="lib/src/mixed.dart",
            start_line=10,
            end_line=11,
        )
        g = build_graph(req, code_single, code_continued)

        fn = g.find_by_id(make_file_id(HELPER_NAMESPACE, "lib/src/mixed.dart"))
        assert fn is not None
        covered = {5: 1, 15: 1, 35: 1}
        fn.set_field("line_coverage", dict(covered))

        region = _citation_extents(fn, {})

        # Line 5 falls between the two citations, so they are separate runs:
        # each owns the covered lines after it, up to the next citation.
        assert region == {1: {5}, 10: {15, 35}}, (
            "the continued citation must start its own run; "
            f"got {region}. Under the retired rule line 1 owned all three lines."
        )

        # The partition property: every covered line is owned by exactly one
        # run, and no line is owned twice or lost.
        owners = [start for start, owned in region.items() for _ in owned]
        assert len(owners) == len(covered)
        assert set().union(*region.values()) == set(covered)

        annotate_coverage(g, _credit())

        rollup: RollupMetrics = g.find_by_id("REQ-p00001").get_metric("rollup_metrics")
        assert rollup is not None
        # B is credited from the lines its own citation precedes -- under the
        # retired rule it owned nothing and A was credited for all three.
        assert covered_labels(rollup.lcov_tested, "total") == {"A", "B"}


# ---------------------------------------------------------------------------
# Case 7: How a reference list is divided changes nothing (REQ-d00269-M)
# ---------------------------------------------------------------------------

_SPEC_TEXT = (
    "# REQ-d00001: Thing\n\n"
    "**Level**: dev | **Status**: Active | **Implements**: -\n\n"
    "## Assertions\n\n"
    "A. The system SHALL do a thing.\n\n"
    "B. The system SHALL do another thing.\n\n"
    "*End* *Thing* | **Hash**: 00000000\n"
)

# The three equivalent spellings of one pair of citations. Each puts the same
# executable code on lines 3, 4 and 5, so the lines a citation attributes are
# comparable across spellings; only the division of the references differs.
SPELLINGS = {
    # (1) two keyword lines, one reference each -> two CODE nodes
    "separate-keyword-lines": (
        "# Implements: REQ-d00001-A\n# Implements: REQ-d00001-B\nVALUE = 1\nOTHER = 2\nTHIRD = 3\n"
    ),
    # (2) one keyword line, comma-separated list -> one 1-line CODE node
    "comma-separated-list": (
        "# Implements: REQ-d00001-A, REQ-d00001-B\n\nVALUE = 1\nOTHER = 2\nTHIRD = 3\n"
    ),
    # (3) one keyword line continued onto the next comment line (REQ-d00269-H)
    # -> one 2-line CODE node
    "continued-list": (
        "# Implements: REQ-d00001-A,\n#             REQ-d00001-B\nVALUE = 1\nOTHER = 2\nTHIRD = 3\n"
    ),
}

# Lines 3 and 4 ran, line 5 did not. Three executable lines is what tells
# "attributed the code" (3) from "attributed the citation's own comment
# lines" (1 or 2, depending on the spelling) apart.
_LINE_COVERAGE = {3: 1, 4: 1, 5: 0}


def _elspais_repo_root():
    return Path(__file__).resolve().parents[2]


def _build_module_level_project(tmp_path, code_text):
    """Build a one-file project whose citation has no enclosing function.

    Returns ``(graph, file_node)`` with ``line_coverage`` already recorded on
    the code FILE node, ready for :func:`annotate_coverage`.
    """
    from elspais.config import load_config
    from elspais.graph.factory import build_graph as build_real_graph
    from elspais.graph.GraphNode import NodeKind

    (tmp_path / ".elspais.toml").write_text((_elspais_repo_root() / ".elspais.toml").read_text())
    spec = tmp_path / "spec"
    spec.mkdir()
    (spec / "r.md").write_text(_SPEC_TEXT)
    src = tmp_path / "src"
    src.mkdir()
    (src / "m.py").write_text(code_text)

    config_path = tmp_path / ".elspais.toml"
    graph = build_real_graph(
        load_config(config_path),
        config_path=config_path,
        repo_root=tmp_path,
        scan_code=True,
        scan_tests=False,
    )
    file_node = next(
        n for n in graph.iter_by_kind(NodeKind.FILE) if n.get_field("relative_path") == "src/m.py"
    )
    file_node.set_field("line_coverage", dict(_LINE_COVERAGE))
    return graph, file_node


def _implements_targets(req_node):
    """The (requirement id, assertion label) pairs the IMPLEMENTS edges declare."""
    from elspais.graph.GraphNode import NodeKind
    from elspais.graph.relations import EdgeKind

    pairs = []
    for edge in req_node.iter_outgoing_edges():
        if edge.kind != EdgeKind.IMPLEMENTS or edge.target.kind != NodeKind.CODE:
            continue
        for label in edge.assertion_targets or ():
            pairs.append((req_node.id, label))
    return pairs


class TestReferenceDivisionIsInvariant:
    """Validates REQ-d00269-M: how references are divided between lists and
    lines changes neither the relationships declared nor the lines those
    relationships attribute.

    The three spellings differ structurally on purpose -- (1) builds two
    single-line CODE nodes, (2) one single-line node, (3) one two-line node --
    because the nodes model the file's text. Nothing observable downstream may
    differ.
    """

    # Verifies: REQ-d00269-M, REQ-d00254-D
    @pytest.mark.parametrize("spelling", sorted(SPELLINGS))
    def test_spelling_declares_the_same_relationships_and_lines(self, tmp_path, spelling):
        from elspais.graph.annotators import _citation_extents

        graph, file_node = _build_module_level_project(tmp_path, SPELLINGS[spelling])
        req = graph.find_by_id("REQ-d00001")
        assert req is not None, f"{spelling}: the requirement must be in the graph"

        # 1. The same relationships: both assertions of the same requirement,
        #    named by two IMPLEMENTS edges to code.
        assert sorted(_implements_targets(req)) == [
            ("REQ-d00001", "A"),
            ("REQ-d00001", "B"),
        ], f"{spelling}: declared relationships differ"

        # 2. The same attributed lines: the executable code beneath the
        #    citation (3, 4, 5), never the comment lines it is written on.
        region = _citation_extents(file_node, {})
        assert region, f"{spelling}: the citation must attribute something"
        assert {frozenset(owned) for owned in region.values()} == {frozenset({3, 4, 5})}, (
            f"{spelling}: attributed lines {region} are not the code beneath the citation"
        )

        annotate_coverage(
            graph,
            _credit(app_dirs=("src",), coverage_dirs=("src",)),
        )
        rollup: RollupMetrics = req.get_metric("rollup_metrics")
        assert rollup is not None

        # 3. The same coverage metrics.
        assert rollup.implemented.total == 2
        assert rollup.implemented.covered == pytest.approx(2.0)
        assert rollup.implemented.immediate_direct_by_label == pytest.approx({"A": 1.0, "B": 1.0})
        assert rollup.implemented.immediate_indirect_by_label == {}
        assert rollup.implemented.rolled_direct_by_label == {}
        assert rollup.implemented.rolled_indirect_by_label == {}

        # 4. The same line-coverage extent: 3 lines attributed, 2 of them run.
        assert rollup.code_tested.total_lines == 3, (
            f"{spelling}: expected the 3 code lines, got {rollup.code_tested}"
        )
        assert rollup.code_tested.covered_lines == 2
        assert rollup.lcov_tested.immediate_direct_by_label == pytest.approx(
            {"A": 2 / 3, "B": 2 / 3}
        )


class TestContinuedCitationAttributesTheCodeBeneath:
    """Regression (REQ-d00254-D): what a citation attributes is decided by whether a
    citation sits in a function, NOT by how many lines its comment occupies.

    A citation with no enclosing function whose reference list is continued
    onto a second comment line used to fail the ``impl_end == impl_start``
    test and so attributed its own two comment lines -- lines no coverage
    tool ever reports as executable, so the citation credited nothing, while
    the equivalent two-marker spelling credited the code.
    """

    # Verifies: REQ-d00254-D, REQ-d00269-M
    def test_two_line_citation_attributes_the_executable_lines_below(self, tmp_path):
        graph, _file_node = _build_module_level_project(tmp_path, SPELLINGS["continued-list"])
        req = graph.find_by_id("REQ-d00001")
        annotate_coverage(graph, _credit(app_dirs=("src",), coverage_dirs=("src",)))
        rollup: RollupMetrics = req.get_metric("rollup_metrics")
        assert rollup is not None

        # The citation occupies lines 1-2; the code it precedes is 3-5. Two
        # attributed lines would mean it had attributed itself.
        assert rollup.code_tested.total_lines == 3, (
            "a continued citation must attribute the 3 code lines beneath it, "
            f"not its own 2 comment lines; got {rollup.code_tested}"
        )
        assert rollup.code_tested.covered_lines == 2, f"lines 3 and 4 ran; got {rollup.code_tested}"
        assert covered_labels(rollup.lcov_tested, "total") == {"A", "B"}, (
            "both assertions of a continued list must take line-coverage credit"
        )
        assert rollup.lcov_tested.covered > 0


# ---------------------------------------------------------------------------
# Case 8: the four rules of _citation_extents, one test each
# ---------------------------------------------------------------------------


def _extents(citations, coverage, path="src/m.py"):
    """Return ``_citation_extents`` for a file holding *citations*.

    Each citation is ``(first_line, last_line, function_line,
    function_end_line)`` -- the two extents the pre-scan records for it, with
    ``0, 0`` meaning it found no enclosing function. ``coverage`` is the
    executable lines, or None for a file no run has measured.
    """
    from elspais.graph.annotators import _citation_extents

    req = make_requirement("REQ-p00001", assertions=[{"label": "A", "text": "SHALL A"}])
    refs = [
        make_code_ref(
            implements=["REQ-p00001-A"],
            source_path=path,
            start_line=first,
            end_line=last,
            function_name="fn" if func_line else None,
            function_line=func_line,
            function_end_line=func_end,
        )
        for first, last, func_line, func_end in citations
    ]
    graph = build_graph(req, *refs)
    file_node = graph.find_by_id(make_file_id(HELPER_NAMESPACE, path))
    if coverage is not None:
        file_node.set_field("line_coverage", dict.fromkeys(coverage, 1))
    return _citation_extents(file_node, {})


class TestCitationExtentRules:
    """The four rules ``_citation_extents`` states, one test each.

    This is a stated design rather than an implementation detail, so each rule
    is pinned on its own and each test asserts the WHOLE returned map -- which
    is what says nothing else was attributed to anybody.
    """

    # Verifies: REQ-d00269-M, REQ-d00254-D
    def test_rule_1_citations_with_no_code_between_them_share_one_answer(self):
        """Citations with no executable line between them are one run.

        This is what makes the division of a reference list immaterial: two
        adjacent citations answer identically, so splitting a list across lines
        cannot change what it attributes (REQ-d00269-M). Without the run, the
        second citation would bound the first and the first would speak for
        nothing at all.
        """
        assert _extents([(3, 3, 0, 0), (4, 4, 0, 0)], [6, 7]) == {3: {6, 7}, 4: {6, 7}}

        # The contrast: an executable line BETWEEN them ends the run, and then
        # each speaks only for its own code.
        assert _extents([(3, 3, 0, 0), (6, 6, 0, 0)], [4, 7]) == {3: {4}, 6: {7}}

    # Verifies: REQ-d00254-D
    def test_rule_2_a_run_above_a_function_attributes_that_functions_code(self):
        """A run written above a ``def`` attributes that function's EXECUTABLE
        lines -- the function bounds the answer, and executability picks it.

        Both halves are visible here. Lines 7 and 9 lie inside the function and
        are absent from the coverage map -- a docstring, a blank, a comment --
        so they are not attributed: a denominator holding lines the numerator
        can never reach reports the requirement as less covered than its code
        is. Line 12 is executable but past the function's end, so the function
        still bounds the answer and nobody claims it.
        """
        code = {6, 8, 10}
        assert _extents([(4, 4, 6, 10), (5, 5, 6, 10)], [6, 8, 10, 12]) == {4: code, 5: code}

    # Verifies: REQ-d00254-D
    def test_rule_3_a_run_inside_a_function_is_bounded_three_ways(self):
        """Any other run attributes the executable lines that follow it, up to
        the earliest of the next citation, its function's end, or the file's.

        All three bounds are exercised at once: line 9 lies past the function's
        end and belongs to nobody, the citation on line 5 stops the one on line
        2, and the run beginning at 5 reaches the end of the function.
        """
        assert _extents([(2, 2, 1, 8), (5, 5, 1, 8)], [3, 4, 6, 7, 9]) == {
            2: {3, 4},
            5: {6, 7},
        }

    # Verifies: REQ-d00254-D
    def test_rule_4_only_an_enclosing_function_overlaps_what_it_contains(self):
        """A run above a function and a run inside it overlap -- and that is
        the only overlap the rules admit.

        The citation on line 2 speaks for the code of the function 3-8; the one
        on line 5 speaks for the part of it after itself. They genuinely share
        lines 6 and 7, which is correct: the outer citation claims the
        function, the inner one claims a piece of the same function. The
        module-level citation on line 9 sits in neither and overlaps neither.

        Lines 3, 5 and 8 lie inside the function and are absent from the
        coverage map, so the outer citation does not claim them either.
        """
        extents = _extents([(2, 2, 3, 8), (5, 5, 3, 8), (9, 9, 0, 0)], [4, 6, 7, 10])
        assert extents == {2: {4, 6, 7}, 5: {6, 7}, 9: {10}}

        # The overlap happens, and it is exactly the contained run's lines.
        assert extents[2] & extents[5] == {6, 7}

        # ...and it is the ONLY one: every other pair is disjoint.
        overlapping = {
            frozenset((a, b))
            for a in extents
            for b in extents
            if a != b and extents[a] & extents[b]
        }
        assert overlapping == {frozenset((2, 5))}, (
            f"only an enclosing function may overlap what it contains; got {overlapping}"
        )


# ---------------------------------------------------------------------------
# Case 9: the pre-scan and the extent rules, chained
# ---------------------------------------------------------------------------


def _extents_from_source(source, coverage, path="src/m.py"):
    """Run the pre-scan over real source, then answer the extents from it.

    The two halves of REQ-d00254-D meet here.  ``build_line_context`` decides
    which function a citation was written above; ``_citation_extents`` decides
    what that citation therefore attributes.  Exercising them apart cannot see
    the consequence of the first getting it wrong, because a citation bound to
    no function does not fail -- it silently falls to D's second branch and
    claims the executable lines below it as far as the next citation or the end
    of the file.
    """
    from elspais.graph.parsers.prescan import build_line_context

    lines = [(i + 1, text) for i, text in enumerate(source.rstrip("\n").split("\n"))]
    context = build_line_context(lines, "python")
    citations = [
        (ln, ln, context[ln][2], context[ln][3]) for ln, text in lines if "Implements:" in text
    ]
    assert citations, "source must hold at least one citation"
    return _extents(citations, coverage, path=path)


# A lone citation above a decorated function, with an unrelated function below
# it.  Nothing separates the two but blank lines, so under D's second branch
# the citation would reach the second function's code as well.
DECORATED_THEN_UNRELATED = """\
# Implements: REQ-p00001-A
@app.route("/x")
def handler():
    value = 1
    return value


def unrelated():
    other = 2
    return other
"""


# Verifies: REQ-d00254-D
def test_REQ_d00254_D_a_citation_above_a_decorated_function_claims_only_that_function():
    """A citation above a decorated ``def`` attributes that function and no more.

    The decorator stands between the citation and the function it was written
    above.  Passing over it is what puts the citation in D's FIRST branch,
    where the function bounds the answer; failing to pass over it puts the
    citation in the second, where nothing nearer than the end of the file does
    -- and the unrelated function below is then attributed to a requirement it
    implements no part of.

    The whole map is asserted, which is what says nobody else was attributed
    anything either.
    """
    extents = _extents_from_source(DECORATED_THEN_UNRELATED, [4, 5, 9, 10])

    assert extents == {1: {4, 5}}, (
        "the citation speaks for handler's executable lines and for nothing below it"
    )
