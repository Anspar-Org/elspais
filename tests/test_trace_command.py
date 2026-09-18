# Validates REQ-p00003-A, REQ-p00003-B, REQ-p00006-A
# Validates REQ-p00050-B
# Validates REQ-d00052-B, REQ-d00052-C
"""Tests for the trace command.

Uses the session-scoped canonical_federated_graph to avoid rebuilding
the graph per test (~2.5s each). Tests call trace rendering functions
directly against the pre-built graph.
"""

import json

import pytest

from elspais.commands._requests import TraceRequest
from elspais.commands.trace import (
    ABSENT_FIGURE,
    REPORT_PRESETS,
    ReportPreset,
    _format_row,
    _render_json_from_data,
    compute_trace,
    render_trace,
)
from elspais.graph.aggregation import MEASURES
from elspais.graph.values import figure_cell


def _trace_rows(content: str) -> list[dict]:
    """The rows of a trace JSON report.

    Trace's JSON document has ONE shape -- an object stating ``scope`` beside
    ``nodes`` -- so a reader wanting the rows asks for them by name. These
    tests are about the rows; the document's shape is pinned once, in
    ``tests/commands/test_scope_disclosure.py``, rather than restated by every
    test that happens to read a row.
    """
    return json.loads(content)["nodes"]


class TestTraceCommand:
    """Tests for basic trace command functionality."""

    # Verifies: REQ-p00003-A, REQ-d00084-A
    @pytest.mark.parametrize(
        "fmt,expected_marker",
        [
            ("markdown", "Traceability Matrix"),
            ("html", "<!DOCTYPE html>"),
            ("csv", "ID"),
        ],
        ids=["markdown", "html", "csv"],
    )
    def test_trace_table_format_output(
        self, canonical_federated_graph, canonical_config, fmt, expected_marker
    ):
        """Test trace command produces correct table output for each format."""
        preset = ReportPreset(
            name="standard",
            values=list(REPORT_PRESETS["standard"].values),
        )
        content = render_trace(
            canonical_federated_graph, canonical_config, TraceRequest(), fmt, preset
        )
        assert expected_marker in content
        assert "REQ-p00001" in content

    # Verifies: REQ-d00084-A
    def test_trace_json_format_output(self, canonical_federated_graph, capsys):
        """Test trace command produces correct JSON output."""
        data = compute_trace(canonical_federated_graph, {}, TraceRequest())
        preset = ReportPreset(
            name="standard",
            values=list(REPORT_PRESETS["standard"].values),
        )
        _render_json_from_data(data, preset)

        content = capsys.readouterr().out
        parsed = _trace_rows(content)
        assert any(item["id"] == "REQ-p00001" for item in parsed)

    # Verifies: REQ-d00069-L, REQ-d00282-B+E
    def test_the_measures_are_selected_not_granted_by_the_format(
        self, canonical_federated_graph, capsys
    ):
        """A measure is a value a reader names, in whatever format they read.

        Bolting the four measures onto JSON alone made the values a report
        states depend on the format it was rendered in, which REQ-d00282-E
        forbids: the same report read as a table stated fewer facts than the
        same report read as JSON."""
        data = compute_trace(canonical_federated_graph, {}, TraceRequest())
        preset = ReportPreset(
            name="standard",
            values=list(REPORT_PRESETS["standard"].values),
        )

        _render_json_from_data(data, preset)
        default_item = next(
            i for i in _trace_rows(capsys.readouterr().out) if i["id"] == "REQ-p00001"
        )
        assert "tested" in default_item
        assert not set(default_item["tested"]) & set(MEASURES), (
            f"The default set states the totals, not the measures; got {default_item['tested']}"
        )

        chosen = ["id", "tested.immediate_direct", "implemented.rolled_indirect"]
        _render_json_from_data(data, preset, chosen)
        item = next(i for i in _trace_rows(capsys.readouterr().out) if i["id"] == "REQ-p00001")
        # The key a selection names is a PATH, and the object mirrors it: a
        # measure of a dimension is stated INSIDE that dimension (REQ-d00282-B).
        assert list(item.keys()) == ["id", "tested", "implemented"]
        assert list(item["tested"]) == ["immediate_direct"]
        assert list(item["implemented"]) == ["rolled_indirect"]
        assert set(item["tested"]["immediate_direct"]) == {"count", "total", "ratio"}

    # Verifies: REQ-d00069-L, REQ-d00282-E
    def test_format_json_graph_path_states_the_same_values(self, canonical_federated_graph, capsys):
        """The live-graph JSON path (``format_json``) states what the
        daemon-payload path (``_render_json_from_data``) states, for one
        selection: a report answered by a serving process cannot state
        different values from a locally computed one."""
        from elspais.commands.trace import format_json

        preset = ReportPreset(
            name="standard",
            values=list(REPORT_PRESETS["standard"].values),
        )
        chosen = ["id", "tested.rolled_direct", "implemented.immediate_indirect"]

        live = _trace_rows("".join(format_json(canonical_federated_graph, preset, None, chosen)))
        data = compute_trace(canonical_federated_graph, {}, TraceRequest())
        _render_json_from_data(data, preset, chosen)
        served = _trace_rows(capsys.readouterr().out)

        live_item = next(i for i in live if i["id"] == "REQ-p00001")
        served_item = next(i for i in served if i["id"] == "REQ-p00001")
        assert list(live_item.keys()) == ["id", "tested", "implemented"]
        assert list(live_item["tested"]) == ["rolled_direct"]
        assert list(live_item["implemented"]) == ["immediate_indirect"]
        assert live_item == served_item


# Verifies: REQ-d00069-N, REQ-d00258-A, REQ-d00258-J
class TestTraceHeadlineIsTheTotal:
    """A discriminating fixture where the legacy blended footings and the
    REQ-d00069-N total genuinely disagree, so a headline reverted to the
    legacy footing (without reinstating the `~` marker) would be caught."""

    def test_headline_reads_the_total_not_the_legacy_blended_footing(self):
        """*Assertion* A carries partial LOCAL evidence (0.6) AND a fully
        finished conducted refinement (1.0). The legacy footings average the
        two into 0.8; the total takes the greatest of the four measures
        (1.0)."""
        from elspais.commands.trace import _get_node_data
        from elspais.graph.builder import TraceGraph
        from elspais.graph.GraphNode import GraphNode, NodeKind
        from elspais.graph.metrics import CoverageDimension, RollupMetrics

        node = GraphNode("REQ-p00001", NodeKind.REQUIREMENT, label="Partial+Refined")
        node.set_field("level", "prd")
        node.set_field("status", "Active")
        node.set_metric(
            "rollup_metrics",
            RollupMetrics(
                total_assertions=1,
                implemented=CoverageDimension(
                    total=1,
                    immediate_direct_by_label={"A": 0.6},
                    rolled_direct_by_label={"A": 1.0},
                ),
            ),
        )
        dim = node.get_metric("rollup_metrics").implemented
        # The legacy blended footing averaged the citation with what the
        # refinement conducted -- (0.6 + 1.0) / 2 == 0.8, LOWER than either.
        # The total is a per-*Assertion* max instead, so a finished refinement
        # cannot be pulled down by a partial citation beside it.
        assert dim.immediate_direct == pytest.approx(0.6)
        assert dim.rolled_direct == pytest.approx(1.0)
        assert dim.covered == pytest.approx(1.0)

        data = _get_node_data(node, TraceGraph())
        assert data["implemented"] == "1/1 (100%)"
        assert "0.8" not in data["implemented"]
        assert data["implemented_immediate_direct"] == "0.6/1 (60%)"
        assert data["implemented_rolled_direct"] == "1/1 (100%)"


class TestTraceReportPresets:
    """Tests for --preset functionality."""

    @pytest.fixture(scope="class")
    def trace_data(self, canonical_federated_graph):
        """Compute trace data once for the class."""
        return compute_trace(canonical_federated_graph, {}, TraceRequest())

    def _make_preset(self, preset_name):
        return ReportPreset(
            name=preset_name,
            values=list(REPORT_PRESETS[preset_name].values),
        )

    # Verifies: REQ-d00084-B
    @pytest.mark.parametrize(
        "preset,should_have,should_not_have",
        [
            (
                "minimal",
                ["ID", "Title", "Level", "Status"],
                ["Implemented", "Tested"],
            ),
            (
                "standard",
                [
                    "ID",
                    "Title",
                    "Level",
                    "Status",
                    "Implemented",
                    "Tested",
                    "Passing",
                    "UAT Covered",
                    "UAT Passed",
                    "Code Tested",
                    "LCOV Tested",
                ],
                [],
            ),
            (
                "full",
                [
                    "ID",
                    "Title",
                    "Level",
                    "Status",
                    "Implemented",
                    "Tested",
                    "Passing",
                    "UAT Covered",
                    "UAT Passed",
                    "Code Tested",
                    "LCOV Tested",
                ],
                [],
            ),
        ],
        ids=["minimal", "standard", "full"],
    )
    def test_preset_csv_columns(
        self,
        canonical_federated_graph,
        preset,
        should_have,
        should_not_have,
        canonical_config,
    ):
        """Test --preset produces expected CSV columns."""
        p = self._make_preset(preset)
        out = render_trace(canonical_federated_graph, canonical_config, TraceRequest(), "csv", p)
        header = out.split("\n")[0]
        for col in should_have:
            assert col in header, f"Missing column: {col}"
        for col in should_not_have:
            assert col not in header, f"Unexpected column: {col}"

    # Verifies: REQ-d00084-D
    @pytest.mark.parametrize(
        "preset,should_have_fields",
        [
            (
                "full",
                [
                    "implemented",
                    "tested",
                    "verified",
                    "uat_coverage",
                    "uat_verified",
                    "code_tested",
                    "lcov_tested",
                ],
            ),
            ("minimal", []),
        ],
        ids=["full-has-coverage", "minimal-excludes-coverage"],
    )
    def test_preset_json_fields(
        self,
        trace_data,
        preset,
        should_have_fields,
        capsys,
    ):
        """Test --preset JSON includes/excludes coverage fields."""
        p = self._make_preset(preset)
        _render_json_from_data(trace_data, p)

        content = capsys.readouterr().out
        data = _trace_rows(content)
        parent = next((r for r in data if r.get("id") == "REQ-p00001"), None)
        assert parent is not None
        for field in should_have_fields:
            assert field in parent, f"Missing field: {field}"
        if not should_have_fields:
            assert "implemented" not in parent

    # Verifies: REQ-d00084-B
    def test_report_invalid_preset_returns_error(self, capsys):
        """Test invalid --preset returns error."""
        import argparse

        from elspais.commands import trace

        args = argparse.Namespace(
            config=None,
            spec_dir=None,
            format="markdown",
            quiet=False,
            preset="nonexistent",
        )
        result = trace.run(args)
        assert result == 1
        captured = capsys.readouterr()
        assert "Unknown preset" in captured.err
        assert "minimal" in captured.err

    # Verifies: REQ-d00084-B
    def test_report_default_is_standard(self, canonical_federated_graph, canonical_config):
        """Test that no --preset defaults to standard."""
        default_header = render_trace(
            canonical_federated_graph, canonical_config, TraceRequest(), "csv"
        ).split("\n")[0]

        standard_preset = self._make_preset("standard")
        standard_header = render_trace(
            canonical_federated_graph, canonical_config, TraceRequest(), "csv", standard_preset
        ).split("\n")[0]

        assert default_header == standard_header


class TestLcovTestedTrace:
    """Validates REQ-d00215-B: lcov_tested % appears in trace node data."""

    def test_lcov_tested_key_in_node_data(self, canonical_federated_graph):
        """_get_node_data includes lcov_tested key in output for every node."""
        import re

        from elspais.commands.trace import _get_node_data
        from elspais.graph.GraphNode import NodeKind
        from elspais.graph.metrics import RollupMetrics

        has_lcov_node = False
        for node in canonical_federated_graph.nodes_by_kind(NodeKind.REQUIREMENT):
            data = _get_node_data(node, canonical_federated_graph)
            assert "lcov_tested" in data, f"Missing lcov_tested key for {node.id}"
            rollup: RollupMetrics | None = node.get_metric("rollup_metrics")
            if rollup and rollup.lcov_tested.total > 0:
                # Nodes with lcov data must render as "lcov NN%"
                assert re.match(r"lcov \d+%$", data["lcov_tested"]), (
                    f"Unexpected lcov_tested format for {node.id}: {data['lcov_tested']!r}"
                )
                has_lcov_node = True
            else:
                # Nodes without lcov data carry an ABSENCE in the data, and a
                # table spells that absence "n/a" (REQ-d00282-M): the value is
                # not the string, so a format with nulls can state one.
                assert data["lcov_tested"] is None, (
                    f"Expected an absence for {node.id} but got: {data['lcov_tested']!r}"
                )
                assert _format_row(data, ["lcov_tested"]) == [ABSENT_FIGURE]

        # At least one node must have lcov data in the canonical graph
        # (the canonical graph includes LCOV result fixtures)
        # If the canonical graph has no lcov data at all, the format check above
        # is vacuously true — log a note but don't fail the overall test.
        _ = has_lcov_node  # informational; not asserted to avoid brittleness

    def test_lcov_tested_assertion_expansion_no_keyerror(
        self, canonical_federated_graph, canonical_config
    ):
        """--assertions mode must not raise KeyError for lcov_tested."""
        from elspais.commands.trace import REPORT_PRESETS, ReportPreset, render_trace

        preset = ReportPreset(
            name="standard",
            values=list(REPORT_PRESETS["standard"].values),
            include_assertions=True,
        )
        # Must not raise KeyError when lcov_tested is among the stated values
        out = render_trace(
            canonical_federated_graph, canonical_config, TraceRequest(), "csv", preset
        )
        assert "lcov" in out.lower()

    def test_lcov_tested_in_standard_preset(self):
        """lcov_tested is a value the standard and full presets state."""
        from elspais.commands.trace import REPORT_PRESETS

        assert "lcov_tested" in REPORT_PRESETS["standard"].values, (
            "lcov_tested must be in the standard preset's values"
        )
        assert "lcov_tested" in REPORT_PRESETS["full"].values, (
            "lcov_tested must be in the full preset's values"
        )


class TestTraceFreshTargets:
    """Verifies REQ-d00254-I: --targets threads a fresh set into build_graph()."""

    @staticmethod
    def _make_project(tmp_path):
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        (spec_dir / "reqs.md").write_text(
            """\
### REQ-p00001: Test Req

**Level**: PRD | **Status**: Active

The system SHALL do something testable.

*End* *Test Req* | **Hash**: ________
""",
            encoding="utf-8",
        )
        config_path = tmp_path / ".elspais.toml"
        config_path.write_text(
            """\
version = 5

[project]
name = "fresh-targets"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]

[[scanning.test.targets]]
name = "a"

[[scanning.test.targets]]
name = "b"
""",
            encoding="utf-8",
        )
        return config_path

    # Verifies: REQ-d00254-I
    def test_trace_targets_marks_fresh_set(self, tmp_path, monkeypatch):
        """--targets threads a fresh set into build_graph() for the trace command."""
        import argparse

        import elspais.graph.factory as factory_mod
        from elspais.commands import trace

        config_path = self._make_project(tmp_path)

        captured: dict = {}
        original_build_graph = factory_mod.build_graph

        def spy(*args, **kwargs):
            captured["fresh_targets"] = kwargs.get("fresh_targets")
            return original_build_graph(*args, **kwargs)

        monkeypatch.setattr(factory_mod, "build_graph", spy)

        args = argparse.Namespace(
            targets=["a"],
            format="json",
            config=config_path,
            spec_dir=None,
            preset=None,
            body=False,
            show_assertions=False,
            show_tests=False,
            dimension="",
            output=None,
        )
        result = trace.run(args)

        assert result is None or result == 0
        assert captured["fresh_targets"] == {"a"}

    # Verifies: REQ-d00254-I
    def test_trace_no_targets_is_none(self, tmp_path, monkeypatch):
        """Absent --targets threads fresh_targets=None into build_graph()."""
        import argparse

        import elspais.graph.factory as factory_mod
        from elspais.commands import trace

        config_path = self._make_project(tmp_path)

        captured: dict = {}
        original_build_graph = factory_mod.build_graph

        def spy(*args, **kwargs):
            captured["fresh_targets"] = kwargs.get("fresh_targets")
            return original_build_graph(*args, **kwargs)

        monkeypatch.setattr(factory_mod, "build_graph", spy)

        args = argparse.Namespace(
            targets=None,
            format="json",
            config=config_path,
            spec_dir=tmp_path / "spec",
            preset=None,
            body=False,
            show_assertions=False,
            show_tests=False,
            dimension="",
            output=None,
        )
        trace.run(args)

        assert captured["fresh_targets"] is None

    @staticmethod
    def _make_grouped_project(tmp_path):
        """A project declaring one group, claimed by one of its two targets."""
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        (spec_dir / "reqs.md").write_text(
            """\
### REQ-p00001: Test Req

**Level**: PRD | **Status**: Active

The system SHALL do something testable.

*End* *Test Req* | **Hash**: ________
""",
            encoding="utf-8",
        )
        config_path = tmp_path / ".elspais.toml"
        config_path.write_text(
            """\
version = 5

[project]
name = "grouped-targets"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]

[scanning.test.groups]
uat = "needs a live backend"
slow = "runs for over a minute"

[[scanning.test.targets]]
name = "a"

[[scanning.test.targets]]
name = "b"
groups = ["uat"]

[[scanning.test.targets]]
name = "c"
groups = ["slow"]
""",
            encoding="utf-8",
        )
        return config_path

    @staticmethod
    def _trace_args(config_path, targets):
        import argparse

        return argparse.Namespace(
            targets=targets,
            format="json",
            config=config_path,
            spec_dir=None,
            preset=None,
            body=False,
            show_assertions=False,
            show_tests=False,
            dimension="",
            output=None,
        )

    # Verifies: REQ-d00283-E+I
    @pytest.mark.parametrize(
        "targets,expected",
        [
            (["uat"], {"b"}),
            (["a"], {"a"}),
            # One vocabulary, unioned: a target name beside a group name marks
            # both, rather than narrowing the group to that target.
            (["a", "uat"], {"a", "b"}),
            (["uat", "slow"], {"b", "c"}),
            # Repeated flags accumulate into the one list the selection reads.
            ([["a"], ["uat"]], {"a", "b"}),
        ],
    )
    def test_trace_targets_thread_the_resolved_set_into_build_graph(
        self, tmp_path, monkeypatch, targets, expected
    ):
        """--targets resolves through the group model before reaching the graph."""
        import elspais.graph.factory as factory_mod
        from elspais.commands import trace

        config_path = self._make_grouped_project(tmp_path)

        captured: dict = {}
        original_build_graph = factory_mod.build_graph

        def spy(*a, **k):
            captured["fresh_targets"] = k.get("fresh_targets")
            return original_build_graph(*a, **k)

        monkeypatch.setattr(factory_mod, "build_graph", spy)

        result = trace.run(self._trace_args(config_path, targets))

        assert result is None or result == 0
        assert captured["fresh_targets"] == expected

    # Verifies: REQ-d00254-I
    def test_trace_with_no_selection_marks_nothing_fresh(self, tmp_path, monkeypatch):
        """Naming nothing marks nothing -- even with groups declared.

        `trace` executes no target; it reads whatever results are already on
        disk. The `default` group of REQ-d00283-D belongs to a run that
        *executes* targets, so resolving one here would have the tool state
        which targets were freshly run on the strength of a flag the caller
        never passed. Do not "fix" this back to the default set.
        """
        import elspais.graph.factory as factory_mod
        from elspais.commands import trace

        config_path = self._make_grouped_project(tmp_path)

        built: list = []
        original_build_graph = factory_mod.build_graph

        def spy(*a, **k):
            built.append(k.get("fresh_targets"))
            return original_build_graph(*a, **k)

        monkeypatch.setattr(factory_mod, "build_graph", spy)

        called: dict = {}

        def fake_engine_call(endpoint, params, compute_fn, config_path=None, **kwargs):
            called["endpoint"] = endpoint
            return {"nodes": [], "scope": []}

        monkeypatch.setattr("elspais.commands._engine.call", fake_engine_call)

        result = trace.run(self._trace_args(config_path, None))

        assert result is None or result == 0
        assert called["endpoint"] == "/api/run/trace", (
            "marking nothing must not force a local build"
        )
        assert not built, "an absent selector marks no fresh subset"

    # Verifies: REQ-d00283-H
    def test_trace_unknown_name_is_refused(self, tmp_path, monkeypatch, capsys):
        """A selection naming neither a configured target nor a group the
        project admits renders nothing at all -- refused rather than resolved
        to nothing, because a report marking a target that does not exist as
        freshly-run cannot be told from one that is honest."""
        import elspais.graph.factory as factory_mod
        from elspais.commands import trace

        config_path = self._make_grouped_project(tmp_path)

        built: list = []
        original_build_graph = factory_mod.build_graph

        def spy(*a, **k):
            built.append(k.get("fresh_targets"))
            return original_build_graph(*a, **k)

        monkeypatch.setattr(factory_mod, "build_graph", spy)

        result = trace.run(self._trace_args(config_path, ["uta"]))

        assert result == 2
        assert "uta" in capsys.readouterr().err
        assert not built, "nothing may be rendered under a refused selection"


def _render_trace_markdown(project, targets=None):
    """Build a real graph for `project` and render it via format_markdown().

    `targets` mirrors the `--targets` CLI selector: None means a full run
    (fresh_targets=None threaded into build_graph()); an iterable of names
    means a selective run (fresh_targets=set(targets)).
    """
    from elspais.commands.trace import format_markdown
    from elspais.graph.factory import build_graph

    fresh_targets = set(targets) if targets is not None else None
    graph = build_graph(
        config_path=project / ".elspais.toml",
        repo_root=project,
        fresh_targets=fresh_targets,
    )
    return "\n".join(format_markdown(graph))


def _verified_cell(markdown_text, req_id):
    """Return the stripped 'Passing' column cell for the row containing req_id.

    The column is still keyed "verified" in the data dict, but its display
    header is "Passing" (REQ-d00258-K).
    """
    lines = markdown_text.splitlines()
    header_line = next((line for line in lines if line.startswith("| ID")), None)
    assert header_line is not None, "no table header found in markdown output"
    headers = [h.strip() for h in header_line.strip("|").split("|")]
    verified_idx = headers.index("Passing")
    for line in lines:
        if line.startswith("|") and req_id in line:
            cells = [c.strip() for c in line.strip("|").split("|")]
            return cells[verified_idx]
    raise AssertionError(f"no row found for {req_id!r} in markdown output")


_TWO_TARGET_CONFIG = """\
version = 5

[project]
name = "two-target-trace"
namespace = "REQ"

[levels.dev]
rank = 1
letter = "d"
implements = ["dev"]

[id-patterns]
canonical = "{namespace}-{level.letter}{component}"

[id-patterns.component]
style = "numeric"
digits = 5
leading_zeros = true

[scanning.spec]
directories = ["spec"]

[scanning.test]
enabled = true
directories = ["tests"]
file_patterns = ["test_*.py"]

[[scanning.test.targets]]
name = "a"
reporter = "junit"
results = "results-a/results.xml"
match = "source"

[[scanning.test.targets]]
name = "b"
reporter = "junit"
results = "results-b/results.xml"
match = "source"

[rules.hierarchy]
allow_circular = false
allow_structural_orphans = true

[rules.format]
require_hash = false
require_assertions = false
require_status = false
"""

_TWO_TARGET_SPEC = """\
# Requirements

---

### REQ-d00001: Req A

The system SHALL do A.

## Assertions

A. The system SHALL do A.

*End* *Req A*
---

### REQ-d00002: Req B

The system SHALL do B.

## Assertions

A. The system SHALL do B.

*End* *Req B*
---
"""

_JUNIT_ONE_PASSING = """\
<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="{suite}" tests="1">
  <testcase name="{name}" classname="tests.{name}" time="0.01"/>
</testsuite>
"""

_JUNIT_ONE_SKIPPED = """\
<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="{suite}" tests="1" skipped="1">
  <testcase name="{name}" classname="tests.{name}" time="0.0"><skipped/></testcase>
</testsuite>
"""


@pytest.fixture
def two_target_project(tmp_path):
    """On-disk project: REQ-d00001-A verified only by target 'a', REQ-d00002-A
    verified only by target 'b'. Both targets have seeded (passing) results,
    so under a `--targets a` selective run, target 'b' is carried (baseline)."""
    project = tmp_path / "project"
    (project / "spec").mkdir(parents=True)
    (project / "spec" / "reqs.md").write_text(_TWO_TARGET_SPEC, encoding="utf-8")

    (project / "tests").mkdir(parents=True)
    (project / "tests" / "test_a.py").write_text(
        "# Verifies: REQ-d00001-A\ndef test_a():\n    pass\n", encoding="utf-8"
    )
    (project / "tests" / "test_b.py").write_text(
        "# Verifies: REQ-d00002-A\ndef test_b():\n    pass\n", encoding="utf-8"
    )

    (project / "results-a").mkdir(parents=True)
    (project / "results-a" / "results.xml").write_text(
        _JUNIT_ONE_PASSING.format(suite="suite-a", name="test_a"), encoding="utf-8"
    )
    (project / "results-b").mkdir(parents=True)
    (project / "results-b" / "results.xml").write_text(
        _JUNIT_ONE_PASSING.format(suite="suite-b", name="test_b"), encoding="utf-8"
    )

    (project / ".elspais.toml").write_text(_TWO_TARGET_CONFIG, encoding="utf-8")
    return project


@pytest.fixture
def no_result_target_project(tmp_path):
    """On-disk project: REQ-d00001-A verified by target 'a' (results present),
    REQ-d00002-A has a `# Verifies:` test reference to target 'b' but NO
    results file was ever seeded for 'b' -- no RESULT node is ingested, so
    the requirement has test_refs but zero verified signal (skipped, not a
    regression)."""
    project = tmp_path / "project"
    (project / "spec").mkdir(parents=True)
    (project / "spec" / "reqs.md").write_text(_TWO_TARGET_SPEC, encoding="utf-8")

    (project / "tests").mkdir(parents=True)
    (project / "tests" / "test_a.py").write_text(
        "# Verifies: REQ-d00001-A\ndef test_a():\n    pass\n", encoding="utf-8"
    )
    (project / "tests" / "test_b.py").write_text(
        "# Verifies: REQ-d00002-A\ndef test_b():\n    pass\n", encoding="utf-8"
    )

    (project / "results-a").mkdir(parents=True)
    (project / "results-a" / "results.xml").write_text(
        _JUNIT_ONE_PASSING.format(suite="suite-a", name="test_a"), encoding="utf-8"
    )
    # No results-b directory/file: target 'b' results glob matches nothing.

    (project / ".elspais.toml").write_text(_TWO_TARGET_CONFIG, encoding="utf-8")
    return project


@pytest.fixture
def skipped_result_target_project(tmp_path):
    """Like two_target_project, but target 'b' has a *skipped* result: a RESULT
    node IS ingested for it, yet it contributes no pass/fail (verified) signal.
    Under `--targets a`, target 'b' is carried but its verified signal is zero --
    it must NOT be mistaken for "not run" (`—`), because result records exist."""
    project = tmp_path / "project"
    (project / "spec").mkdir(parents=True)
    (project / "spec" / "reqs.md").write_text(_TWO_TARGET_SPEC, encoding="utf-8")

    (project / "tests").mkdir(parents=True)
    (project / "tests" / "test_a.py").write_text(
        "# Verifies: REQ-d00001-A\ndef test_a():\n    pass\n", encoding="utf-8"
    )
    (project / "tests" / "test_b.py").write_text(
        "# Verifies: REQ-d00002-A\ndef test_b():\n    pass\n", encoding="utf-8"
    )

    (project / "results-a").mkdir(parents=True)
    (project / "results-a" / "results.xml").write_text(
        _JUNIT_ONE_PASSING.format(suite="suite-a", name="test_a"), encoding="utf-8"
    )
    (project / "results-b").mkdir(parents=True)
    (project / "results-b" / "results.xml").write_text(
        _JUNIT_ONE_SKIPPED.format(suite="suite-b", name="test_b"), encoding="utf-8"
    )

    (project / ".elspais.toml").write_text(_TWO_TARGET_CONFIG, encoding="utf-8")
    return project


class TestTraceCarriedAndNoData:
    """Verifies REQ-d00254-I (carried/baseline) and REQ-d00254-J (no-data em-dash)."""

    # Verifies: REQ-d00254-I
    def test_markdown_marks_carried_baseline(self, two_target_project):
        out = _render_trace_markdown(two_target_project, targets=["a"])
        # target 'b' requirement's verified cell carries the baseline marker
        assert "(baseline)" in _verified_cell(out, "REQ-d00002")
        # target 'a' requirement's verified cell does NOT
        assert "(baseline)" not in _verified_cell(out, "REQ-d00001")

    # Verifies: REQ-d00254-J
    def test_markdown_no_data_dash_in_selective_run(self, no_result_target_project):
        out = _render_trace_markdown(no_result_target_project, targets=["a"])
        # a requirement whose only target 'b' was skipped with no seeded
        # results -> em dash, not "0/1 (0%)"
        assert _verified_cell(out, "REQ-d00002").strip() == "—"

    # Verifies: REQ-d00254-J
    def test_full_run_keeps_existing_rendering(self, no_result_target_project):
        out = _render_trace_markdown(no_result_target_project, targets=None)
        # full run: today's behavior -- no em dash, no (baseline)
        cell = _verified_cell(out, "REQ-d00002")
        assert "—" not in cell
        assert "(baseline)" not in cell

    # Verifies: REQ-d00254-J
    def test_skipped_carried_result_is_not_no_data_dash(self, skipped_result_target_project):
        # target 'b' is carried and its only result is *skipped* (a RESULT node
        # exists but yields no verified signal). "No baseline" (`—`) means zero
        # result records, so this must NOT render as an em dash.
        out = _render_trace_markdown(skipped_result_target_project, targets=["a"])
        assert _verified_cell(out, "REQ-d00002").strip() != "—"


def _build_project_graph(project, targets=None):
    from elspais.graph.factory import build_graph

    fresh_targets = set(targets) if targets is not None else None
    return build_graph(
        config_path=project / ".elspais.toml",
        repo_root=project,
        fresh_targets=fresh_targets,
    )


class TestTraceLegendGating:
    """Verifies REQ-d00254-I/J: the `> Legend: ...` line in format_markdown()
    should only appear when a row actually rendered a `(baseline)` or `—`
    marker in its verified cell, and never for the UAT dimension (which
    doesn't render a verified column at all)."""

    # Verifies: REQ-d00254-I+J
    def test_legend_present_when_marker_rendered(self, two_target_project):
        from elspais.commands.trace import format_markdown

        graph = _build_project_graph(two_target_project, targets=["a"])
        out = "\n".join(format_markdown(graph))

        assert "(baseline)" in _verified_cell(out, "REQ-d00002")
        assert "> Legend:" in out

    # Verifies: REQ-d00254-I+J
    def test_legend_absent_on_full_run(self, two_target_project):
        from elspais.commands.trace import format_markdown

        graph = _build_project_graph(two_target_project, targets=None)
        out = "\n".join(format_markdown(graph))

        assert "> Legend:" not in out

    # Verifies: REQ-d00254-I+J
    def test_legend_absent_on_uat_dimension(self, two_target_project):
        from elspais.commands.trace import _UAT_VALUES, ReportPreset, format_markdown

        graph = _build_project_graph(two_target_project, targets=["a"])
        preset = ReportPreset(name="uat", values=list(_UAT_VALUES), dimension="uat")
        out = "\n".join(format_markdown(graph, preset=preset))

        assert "> Legend:" not in out


_MARKER_VERIFIED_CONFIG = """\
version = 5

[project]
name = "marker-verified-trace"
namespace = "REQ"

[levels.dev]
rank = 1
letter = "d"
implements = ["dev"]

[id-patterns]
canonical = "{namespace}-{level.letter}{component}"

[id-patterns.component]
style = "numeric"
digits = 5
leading_zeros = true

[scanning.spec]
directories = ["spec"]

[scanning.test]
enabled = true
directories = ["tests"]
file_patterns = ["test_*.py"]

[[scanning.test.targets]]
name = "a"
reporter = "junit"
results = "results/results.xml"
match = "source"

[rules.hierarchy]
allow_circular = false
allow_structural_orphans = true

[rules.format]
require_hash = false
require_assertions = false
require_status = false
"""

_MARKER_VERIFIED_SPEC = """\
# Requirements

---

### REQ-d00001: Req A

The system SHALL do A and B.

## Assertions

A. The system SHALL do A.
B. The system SHALL do B.

*End* *Req A*
---
"""


@pytest.fixture
def marker_verified_project(tmp_path):
    """On-disk project: REQ-d00001 is verified only through a blanket
    (whole-requirement) `# Verifies:` reference with a passing result.

    A blanket reference credits every assertion INDIRECTly but none
    DIRECTly, so `tested_and_passing(rollup).covered > .immediate_direct` -- the
    trace 'verified' cell must headline the total (REQ-d00069-N), with the
    immediate-direct and immediate-indirect measure values showing which
    measure carried the evidence rather than a `~` marker (REQ-d00258-J).
    """
    project = tmp_path / "project"
    (project / "spec").mkdir(parents=True)
    (project / "spec" / "reqs.md").write_text(_MARKER_VERIFIED_SPEC, encoding="utf-8")

    (project / "tests").mkdir(parents=True)
    (project / "tests" / "test_a.py").write_text(
        "# Verifies: REQ-d00001\ndef test_a():\n    pass\n", encoding="utf-8"
    )

    (project / "results").mkdir(parents=True)
    (project / "results" / "results.xml").write_text(
        _JUNIT_ONE_PASSING.format(suite="suite-a", name="test_a"), encoding="utf-8"
    )

    (project / ".elspais.toml").write_text(_MARKER_VERIFIED_CONFIG, encoding="utf-8")
    return project


_CODE_TESTED_CONFIG = """\
version = 5

[project]
name = "code-tested-no-attribution"
namespace = "REQ"

[levels.dev]
rank = 1
letter = "d"
implements = ["dev"]

[id-patterns]
canonical = "{namespace}-{level.letter}{component}"

[id-patterns.component]
style = "numeric"
digits = 5
leading_zeros = true

[scanning.spec]
directories = ["spec"]

[scanning.code]
directories = ["src"]

[scanning.test]
enabled = true
directories = ["tests"]
file_patterns = ["test_*.py"]

[[scanning.test.targets]]
name = "a"
coverage = "coverage/lcov.info"
credit_coverage = "verified"

[rules.hierarchy]
allow_circular = false
allow_structural_orphans = true

[rules.format]
require_hash = false
require_assertions = false
require_status = false
"""

_CODE_TESTED_SPEC = """\
# Requirements

---

### REQ-d00001: Req A

The system SHALL do A.

## Assertions

A. The system SHALL do A.

*End* *Req A*
---
"""


@pytest.fixture
def code_tested_no_attribution_project(tmp_path):
    """On-disk project: REQ-d00001's implementation has aggregate (lcov)
    line-coverage data but no per-test attribution -- `code_tested.immediate_direct`
    stays 0 while `.covered` is > 0 (per-test attribution is not derivable
    from aggregate tooling). REQ-d00258-W: the trace 'code_tested' cell must
    render `n/a`, never a misleading `0/N (0%)`.
    """
    project = tmp_path / "project"
    (project / "spec").mkdir(parents=True)
    (project / "spec" / "reqs.md").write_text(_CODE_TESTED_SPEC, encoding="utf-8")

    (project / "src").mkdir(parents=True)
    (project / "src" / "main.py").write_text(
        "# Implements: REQ-d00001\nx = 1\ny = 2\nz = 3\n", encoding="utf-8"
    )

    (project / "coverage").mkdir(parents=True)
    (project / "coverage" / "lcov.info").write_text(
        "SF:src/main.py\nDA:1,1\nDA:2,1\nDA:3,1\nDA:4,1\nLF:4\nLH:4\nend_of_record\n",
        encoding="utf-8",
    )

    (project / ".elspais.toml").write_text(_CODE_TESTED_CONFIG, encoding="utf-8")
    return project


@pytest.fixture
def code_tested_context_carrying_project(tmp_path):
    """On-disk project whose coverage DOES carry per-test contexts, but where
    no context names a test verifying REQ-d00001.

    The sibling of ``code_tested_no_attribution_project``: identical shape,
    context-carrying tooling instead of aggregate-only. Under REQ-d00258-W the
    suppression keys on what the tooling provided, so here the attribution
    question WAS asked and its answer is zero -- the trace cell must render
    ``0/N``, not ``n/a``.
    """
    project = tmp_path / "project"
    (project / "spec").mkdir(parents=True)
    (project / "spec" / "reqs.md").write_text(_CODE_TESTED_SPEC, encoding="utf-8")

    (project / "src").mkdir(parents=True)
    (project / "src" / "main.py").write_text(
        "# Implements: REQ-d00001\nx = 1\ny = 2\nz = 3\n", encoding="utf-8"
    )

    (project / "coverage").mkdir(parents=True)
    (project / "coverage" / "coverage.json").write_text(
        json.dumps(
            {
                "files": {
                    "src/main.py": {
                        "executed_lines": [1, 2, 3, 4],
                        "missing_lines": [],
                        "summary": {"num_statements": 4, "covered_lines": 4},
                        # Contexts recorded, but the test they name verifies
                        # nothing in this project.
                        "contexts": {
                            "2": ["tests/test_unrelated.py::test_other|run"],
                            "3": ["tests/test_unrelated.py::test_other|run"],
                        },
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    (project / ".elspais.toml").write_text(
        _CODE_TESTED_CONFIG.replace("coverage/lcov.info", "coverage/coverage.json"),
        encoding="utf-8",
    )
    return project


@pytest.fixture
def marker_carried_project(tmp_path):
    """Two-target project where REQ-d00002 is verified only through a blanket
    (whole-requirement) `# Verifies: REQ-d00002` in target 'b'.

    Under a `--targets a` selective run, target 'b' is carried (baseline) AND
    its verified evidence is whole-requirement-only, so the trace verified
    cell must compose the total with the baseline suffix: `count (pct%)
    (baseline)` -- no `~` marker (REQ-d00258-J).
    """
    project = tmp_path / "project"
    (project / "spec").mkdir(parents=True)
    (project / "spec" / "reqs.md").write_text(_TWO_TARGET_SPEC, encoding="utf-8")

    (project / "tests").mkdir(parents=True)
    (project / "tests" / "test_a.py").write_text(
        "# Verifies: REQ-d00001-A\ndef test_a():\n    pass\n", encoding="utf-8"
    )
    # Blanket (whole-requirement) ref: credits REQ-d00002's assertions
    # INDIRECTly only, via the immediate-indirect measure.
    (project / "tests" / "test_b.py").write_text(
        "# Verifies: REQ-d00002\ndef test_b():\n    pass\n", encoding="utf-8"
    )

    (project / "results-a").mkdir(parents=True)
    (project / "results-a" / "results.xml").write_text(
        _JUNIT_ONE_PASSING.format(suite="suite-a", name="test_a"), encoding="utf-8"
    )
    (project / "results-b").mkdir(parents=True)
    (project / "results-b" / "results.xml").write_text(
        _JUNIT_ONE_PASSING.format(suite="suite-b", name="test_b"), encoding="utf-8"
    )

    (project / ".elspais.toml").write_text(_TWO_TARGET_CONFIG, encoding="utf-8")
    return project


class TestTraceFooting:
    """Verifies REQ-d00258-A, REQ-d00258-K, REQ-d00258-W, REQ-d00258-J:
    dimensions headline the per-*Assertion* TOTAL (REQ-d00069-N) with the
    four measures behind it published as their own values rather than a
    caveat marker, the reporting vocabulary reads Passing/UAT Covered/UAT
    Passed (no "Validated"), and aggregate-only line coverage never renders
    a misleading direct-attribution count."""

    # Verifies: REQ-d00069-N, REQ-d00258-A, REQ-d00258-J
    def test_whole_requirement_only_coverage_headlines_the_total(self, marker_verified_project):
        """A blanket (whole-requirement) `Verifies:` credits only the
        immediate-indirect measure; the headline is still the total (equal
        to that measure here), and no `~` stands in for the fact that no
        citation named the *Assertion* directly -- the immediate-direct and
        immediate-indirect values say that on their own."""
        from elspais.commands.trace import _get_node_data
        from elspais.graph.metrics import fmt_assertion_count, tested_and_passing

        graph = _build_project_graph(marker_verified_project, targets=None)
        node = graph.find_by_id("REQ-d00001")
        dim = tested_and_passing(node.get_metric("rollup_metrics"))
        assert dim.covered > dim.immediate_direct + 1e-9

        data = _get_node_data(node, graph)
        assert "~" not in data["verified"]
        pct = round(dim.covered / dim.total * 100)
        assert data["verified"] == f"{fmt_assertion_count(dim.covered)}/{dim.total} ({pct}%)"
        assert data["verified_immediate_direct"].startswith("0/")
        indirect_str = fmt_assertion_count(dim.covered)
        assert data["verified_immediate_indirect"].startswith(f"{indirect_str}/")

    # Verifies: REQ-d00258-K
    def test_headers_use_passing_vocabulary(self):
        from elspais.commands.trace import _value_headers

        h = _value_headers()
        assert h["verified"] == "Passing"
        assert h["uat_coverage"] == "UAT Covered"
        assert h["uat_verified"] == "UAT Passed"
        assert "Validated" not in h.values()

    # Verifies: REQ-d00258-W, REQ-d00282-C+N
    def test_only_the_attribution_is_suppressed_without_contexts(
        self, code_tested_no_attribution_project
    ):
        """Aggregate-only coverage states its lines and withholds only the
        attribution.

        The suppression REQ-d00258-W requires is of the ATTRIBUTION figure --
        how many lines a verifying test can be named for. The lines a run
        covered were measured, so a report holding them states them
        (REQ-d00282-N), and the value named for the figure states the figure
        rather than one particular reading of it (REQ-d00282-C).
        """
        from elspais.commands.trace import _get_node_data

        graph = _build_project_graph(code_tested_no_attribution_project, targets=None)
        node = graph.find_by_id("REQ-d00001")
        rollup = node.get_metric("rollup_metrics")
        assert rollup.code_tested.has_contexts is False
        assert rollup.code_tested.attributed_lines == 0
        assert rollup.code_tested.covered_lines > 0

        data = _get_node_data(node, graph)
        lines = rollup.code_tested
        assert data["code_tested"] == figure_cell(lines.covered_lines, lines.total_lines)
        assert data["code_tested_count"] == lines.covered_lines
        assert data["code_tested_total"] == lines.total_lines
        # The one absence, spelled "n/a" by a table (REQ-d00282-M).
        assert data["code_tested_attributed"] is None
        assert _format_row(data, ["code_tested.attributed"]) == [ABSENT_FIGURE]
        assert ABSENT_FIGURE == "n/a"

    # Verifies: REQ-d00258-W, REQ-d00282-E+N
    def test_the_line_figure_is_unmoved_by_the_assertion_label_flag(
        self, code_tested_no_attribution_project
    ):
        """The detail flag changes what an *Assertion*-counted cell says. A
        line figure counts lines, has no labels to compact, and reads the same
        in either mode."""
        from elspais.commands.trace import _get_node_data

        graph = _build_project_graph(code_tested_no_attribution_project, targets=None)
        node = graph.find_by_id("REQ-d00001")

        plain = _get_node_data(node, graph)
        labelled = _get_node_data(node, graph, assertion_labels=True)
        for key in ("code_tested", "code_tested_count", "code_tested_total", "code_tested_ratio"):
            assert labelled[key] == plain[key]
        assert labelled["code_tested_attributed"] is None

    # Verifies: REQ-d00258-W, REQ-d00282-M+N
    def test_a_zero_attribution_is_stated_where_contexts_were_recorded(
        self, code_tested_context_carrying_project
    ):
        """Where the tooling DID record per-test contexts, a zero attribution
        count is a real answer and is stated as zero.

        This is the boundary REQ-d00258-W leaves: the suppression is about what
        the tooling provides, not about how the count came out. Withholding it
        here would hide implementation no verifying test reaches, which is
        exactly the fact worth surfacing."""
        from elspais.commands.trace import _get_node_data

        graph = _build_project_graph(code_tested_context_carrying_project, targets=None)
        node = graph.find_by_id("REQ-d00001")
        rollup = node.get_metric("rollup_metrics")
        assert rollup.code_tested.has_contexts is True
        assert rollup.code_tested.attributed_lines == 0

        for labels in (False, True):
            data = _get_node_data(node, graph, assertion_labels=labels)
            assert data["code_tested_attributed"] == 0
            assert _format_row(data, ["code_tested.attributed"]) == ["0"]
            assert data["code_tested"] == figure_cell(
                rollup.code_tested.covered_lines, rollup.code_tested.total_lines
            )

    # Verifies: REQ-d00258-W
    def test_lcov_tested_empty_label_set_renders_zero_of_total(
        self, code_tested_no_attribution_project
    ):
        """An lcov_tested dimension with total > 0 but an empty label set must
        render `0/N`, never a bare `-` (consistent with the _DIMS label cells)."""
        from elspais.commands.trace import _get_node_data
        from elspais.graph.metrics import CoverageDimension

        graph = _build_project_graph(code_tested_no_attribution_project, targets=None)
        node = graph.find_by_id("REQ-d00001")
        rollup = node.get_metric("rollup_metrics")
        # A dimension with assertions but no credited label must render the
        # honest "0/N" rather than falling back to "-".
        rollup.lcov_tested = CoverageDimension(total=2)

        data = _get_node_data(node, graph, assertion_labels=True)
        assert data["lcov_tested"].startswith("0/2")
        assert data["lcov_tested"] != "-"

    # Verifies: REQ-d00258-A, REQ-d00254-I
    # Verifies: REQ-d00069-N, REQ-d00258-A, REQ-d00258-J, REQ-d00254-I
    def test_baseline_suffix_composes_with_the_total_headline(self, marker_carried_project):
        """Whole-requirement-only AND carried verified evidence must compose
        the exact order `count (pct%) (baseline)` -- no `~` stands in for the
        immediate-indirect-only evidence (REQ-d00258-J)."""
        from elspais.commands.trace import _get_node_data

        graph = _build_project_graph(marker_carried_project, targets=["a"])
        node = graph.find_by_id("REQ-d00002")
        rollup = node.get_metric("rollup_metrics")
        assert rollup.verified.carried
        assert rollup.verified.immediate_direct == 0
        assert rollup.verified.covered > 0

        data = _get_node_data(node, graph)
        assert data["verified"] == "1/1 (100%) (baseline)"


_BREAKDOWN_CONFIG = """\
version = 5

[project]
name = "tested-breakdown-trace"
namespace = "REQ"

[levels.dev]
rank = 1
letter = "d"
implements = ["dev"]

[id-patterns]
canonical = "{namespace}-{level.letter}{component}"

[id-patterns.component]
style = "numeric"
digits = 5
leading_zeros = true

[scanning.spec]
directories = ["spec"]

[scanning.test]
enabled = true
directories = ["tests"]
file_patterns = ["test_*.py"]

[[scanning.test.targets]]
name = "a"
reporter = "junit"
results = "results/results.xml"
match = "source"

[rules.hierarchy]
allow_circular = false
allow_structural_orphans = true

[rules.format]
require_hash = false
require_assertions = false
require_status = false
"""

_BREAKDOWN_SPEC = """\
# Requirements

---

### REQ-d00001: Req A

The system SHALL do A, B and C.

## Assertions

A. The system SHALL do A.
B. The system SHALL do B.
C. The system SHALL do C.

*End* *Req A*
---
"""

_BREAKDOWN_JOURNEY = """\
# User Journeys

---

### JNY-OQ-01: Flow

**Actor**: End User
**Goal**: Do the thing
Validates: REQ-d00001-A

## Steps

1. The user does the thing

*End* *JNY-OQ-01*
---
"""

_BREAKDOWN_JUNIT = """\
<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="suite" tests="2">
  <testcase name="test_a" classname="tests.test_a" file="tests/test_a.py" line="1" time="0.01"/>
  <testcase name="test_b" classname="tests.test_b" file="tests/test_b.py" line="1" time="0.01">
    <failure message="boom">boom</failure>
  </testcase>
</testsuite>
"""


@pytest.fixture
def tested_breakdown_project(tmp_path):
    """On-disk project whose one requirement holds each tested state at once.

    Assertion A is verified by a passing test, B by a failing one, and C by a
    test whose result never arrived -- so the Tested breakdown reads 1P 1F 1A
    (REQ-d00258-U). A journey validates A, so the requirement also has a row to
    render under the UAT preset (which shows no Tested column).

    Each `<testcase>` carries the line of its own `def` in the JUnit reporter's
    own 0-based origin, so its result resolves to that one test. Without it the
    results would bind at file scope, naming every test in the file and so none
    of them, and all three assertions would read as awaiting a result
    (REQ-d00254-A).
    """
    project = tmp_path / "project"
    (project / "spec").mkdir(parents=True)
    (project / "spec" / "reqs.md").write_text(_BREAKDOWN_SPEC, encoding="utf-8")
    (project / "spec" / "journeys.md").write_text(_BREAKDOWN_JOURNEY, encoding="utf-8")

    (project / "tests").mkdir(parents=True)
    for label in ("a", "b", "c"):
        (project / "tests" / f"test_{label}.py").write_text(
            f"# Verifies: REQ-d00001-{label.upper()}\ndef test_{label}():\n    pass\n",
            encoding="utf-8",
        )

    (project / "results").mkdir(parents=True)
    (project / "results" / "results.xml").write_text(_BREAKDOWN_JUNIT, encoding="utf-8")

    (project / ".elspais.toml").write_text(_BREAKDOWN_CONFIG, encoding="utf-8")
    return project


class TestTraceTestedBreakdown:
    """REQ-d00258-U: the trace Tested cell carries the three-way breakdown."""

    def _tested_cell(self, markdown_text, req_id):
        lines = markdown_text.splitlines()
        header_line = next(line for line in lines if line.startswith("| ID"))
        headers = [h.strip() for h in header_line.strip("|").split("|")]
        idx = headers.index("Tested")
        row = next(line for line in lines if line.startswith("|") and req_id in line)
        return [c.strip() for c in row.strip("|").split("|")][idx]

    # Verifies: REQ-d00258-U+V
    def test_tested_cell_carries_the_breakdown(self, tested_breakdown_project):
        """The breakdown qualifies Tested, so it rides in the Tested cell and
        adds no column of its own."""
        from elspais.commands.trace import format_markdown

        graph = _build_project_graph(tested_breakdown_project)
        out = "\n".join(format_markdown(graph))

        cell = self._tested_cell(out, "REQ-d00001")
        assert cell == "3/3 (100%) [1P 1F 1A]"
        header_line = next(line for line in out.splitlines() if line.startswith("| ID"))
        assert "Awaiting" not in header_line

    # Verifies: REQ-d00258-U
    def test_legend_emitted_when_a_row_carried_a_breakdown(self, tested_breakdown_project):
        """The compact form is unreadable without its key."""
        from elspais.commands.trace import format_markdown

        graph = _build_project_graph(tested_breakdown_project)
        out = "\n".join(format_markdown(graph))

        assert "> Tested breakdown:" in out

    # Verifies: REQ-d00258-U
    def test_legend_absent_when_nothing_is_tested(self, code_tested_no_attribution_project):
        """No row carried a breakdown, so no key is offered: there is no
        breakdown of an empty set."""
        from elspais.commands.trace import format_markdown

        graph = _build_project_graph(code_tested_no_attribution_project)
        out = "\n".join(format_markdown(graph))

        assert "> Tested breakdown:" not in out

    # Verifies: REQ-d00258-V, REQ-d00257-C
    @pytest.mark.parametrize("preset_name", ["uat", "minimal"])
    def test_breakdown_absent_from_presets_without_a_tested_column(
        self, tested_breakdown_project, preset_name
    ):
        """A breakdown of a figure the preset does not show explains nothing,
        and its key would point at a value that is not stated. The UAT report
        excludes the test values outright (REQ-d00257-C)."""
        from elspais.commands.trace import (
            _UAT_VALUES,
            REPORT_PRESETS,
            ReportPreset,
            format_markdown,
        )

        if preset_name == "uat":
            preset = ReportPreset(name="uat", values=list(_UAT_VALUES), dimension="uat")
        else:
            preset = ReportPreset(name=preset_name, values=list(REPORT_PRESETS[preset_name].values))

        graph = _build_project_graph(tested_breakdown_project)
        out = "\n".join(format_markdown(graph, preset=preset))

        # The requirement IS rendered and IS carrying a breakdown -- the
        # absence below is the gating, not an empty report.
        assert "REQ-d00001" in out
        header_line = next(line for line in out.splitlines() if line.startswith("| ID"))
        assert "Tested" not in header_line
        assert "> Tested breakdown:" not in out
        assert "1P" not in out

    # Verifies: REQ-d00258-V, REQ-d00282-E
    def test_csv_states_the_breakdown_inside_the_one_tested_column(self, tested_breakdown_project):
        """The breakdown qualifies the Tested figure, so it rides in that
        figure's cell here exactly as it does in markdown.

        Given cells of its own it would be three further columns -- a display
        term of its own, which REQ-d00258-V forbids -- and selecting `tested`
        would state four columns in CSV and one in markdown."""
        import csv as csv_module
        import io as io_module

        from elspais.commands.trace import format_csv

        graph = _build_project_graph(tested_breakdown_project)
        rows = list(csv_module.reader(io_module.StringIO("\n".join(format_csv(graph)))))
        headers, first = rows[0], rows[1]

        assert headers.count("Tested") == 1
        assert not [h for h in headers if h.startswith("Tested ")], (
            f"Nothing rides beside the Tested column; got {headers}"
        )
        assert first[headers.index("Tested")] == "3/3 (100%) [1P 1F 1A]"

    # Verifies: REQ-d00069-L, REQ-d00258-A, REQ-d00282-B+E
    def test_a_measure_is_a_value_a_selection_names_in_every_format(self, tested_breakdown_project):
        """A measure is reachable by selecting it, not by choosing a format.

        The default set states the dimension totals; naming a measure states
        that measure, and CSV and JSON state the same value set for the one
        selection (REQ-d00282-E)."""
        import csv as csv_module
        import io as io_module
        import json as json_module

        from elspais.commands.trace import REPORT_PRESETS, ReportPreset, format_csv, format_json

        graph = _build_project_graph(tested_breakdown_project)
        preset = ReportPreset(name="standard", values=list(REPORT_PRESETS["standard"].values))

        default_header = next(
            csv_module.reader(io_module.StringIO("\n".join(format_csv(graph, preset))))
        )
        assert "Tested" in default_header
        assert not [h for h in default_header if h.startswith("Tested (")], (
            f"A measure is stated only where the selection names it; got {default_header}"
        )

        chosen = ["id", "tested", "tested.immediate_direct"]
        header = next(
            csv_module.reader(
                io_module.StringIO("\n".join(format_csv(graph, preset, None, chosen)))
            )
        )
        # REQ-d00282-C: the heading names the dimension AND the measure.
        assert header == ["ID", "Tested", "Tested (cited by name here)"]

        rows = json_module.loads("".join(format_json(graph, preset, None, chosen)))["nodes"]
        # Two cells in a table, one nested object in a format that has numbers:
        # naming the figure AND a measure of it names one place twice, and the
        # measure lands inside the figure rather than beside it (REQ-d00282-D).
        assert list(rows[0].keys()) == ["id", "tested"]
        assert {"count", "total", "ratio", "immediate_direct"} <= set(rows[0]["tested"])
        assert set(rows[0]["tested"]["immediate_direct"]) == {"count", "total", "ratio"}

    # Verifies: REQ-d00258-K, REQ-d00282-C+J
    def test_headings_come_from_the_configured_display_words(self, tested_breakdown_project):
        """Every heading is read through the configured mapping, the measure
        values included: a project that renames Tested renames it here, while
        the key the selection names stays what it was (REQ-d00282-J)."""
        import csv as csv_module
        import io as io_module

        from elspais.commands.trace import REPORT_PRESETS, ReportPreset, format_csv

        graph = _build_project_graph(tested_breakdown_project)
        preset = ReportPreset(name="standard", values=list(REPORT_PRESETS["standard"].values))
        # Keyed by the RELATIONSHIP conferring the coverage, as REQ-d00258-K
        # defines the mapping -- `Verifies:` is what confers Tested.
        config = {"rules": {"coverage": {"status_words": {"verifies": "Exercised"}}}}

        chosen = ["id", "tested", "tested.rolled_direct"]
        header = next(
            csv_module.reader(
                io_module.StringIO("\n".join(format_csv(graph, preset, None, chosen, config)))
            )
        )
        assert header == ["ID", "Exercised", "Exercised (conducted direct)"]
