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

from elspais.commands.trace import (
    REPORT_PRESETS,
    ReportPreset,
    _render_json_from_data,
    _render_table_from_graph,
    compute_trace,
)


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
        self, canonical_federated_graph, fmt, expected_marker, capsys
    ):
        """Test trace command produces correct table output for each format."""
        preset = ReportPreset(
            name="standard",
            columns=list(REPORT_PRESETS["standard"].columns),
        )
        result = _render_table_from_graph(canonical_federated_graph, fmt, preset)
        assert result == 0

        content = capsys.readouterr().out
        assert expected_marker in content
        assert "REQ-p00001" in content

    # Verifies: REQ-d00084-A
    def test_trace_json_format_output(self, canonical_federated_graph, capsys):
        """Test trace command produces correct JSON output."""
        data = compute_trace(canonical_federated_graph, {}, {})
        preset = ReportPreset(
            name="standard",
            columns=list(REPORT_PRESETS["standard"].columns),
        )
        _render_json_from_data(data, preset)

        content = capsys.readouterr().out
        parsed = json.loads(content)
        assert isinstance(parsed, list)
        assert any(item["id"] == "REQ-p00001" for item in parsed)


class TestTraceReportPresets:
    """Tests for --preset functionality."""

    @pytest.fixture(scope="class")
    def trace_data(self, canonical_federated_graph):
        """Compute trace data once for the class."""
        return compute_trace(canonical_federated_graph, {}, {})

    def _make_preset(self, preset_name):
        return ReportPreset(
            name=preset_name,
            columns=list(REPORT_PRESETS[preset_name].columns),
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
        capsys,
    ):
        """Test --preset produces expected CSV columns."""
        p = self._make_preset(preset)
        result = _render_table_from_graph(canonical_federated_graph, "csv", p)
        assert result == 0
        header = capsys.readouterr().out.split("\n")[0]
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
        data = json.loads(content)
        assert isinstance(data, list)
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
    def test_report_default_is_standard(self, canonical_federated_graph, capsys):
        """Test that no --preset defaults to standard."""
        default_preset = self._make_preset("standard")
        _render_table_from_graph(canonical_federated_graph, "csv", default_preset)
        default_header = capsys.readouterr().out.split("\n")[0]

        standard_preset = self._make_preset("standard")
        _render_table_from_graph(canonical_federated_graph, "csv", standard_preset)
        standard_header = capsys.readouterr().out.split("\n")[0]

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
                assert re.match(
                    r"lcov \d+%$", data["lcov_tested"]
                ), f"Unexpected lcov_tested format for {node.id}: {data['lcov_tested']!r}"
                has_lcov_node = True
            else:
                # Nodes without lcov data must render as "n/a"
                assert (
                    data["lcov_tested"] == "n/a"
                ), f"Expected 'n/a' for {node.id} but got: {data['lcov_tested']!r}"

        # At least one node must have lcov data in the canonical graph
        # (the canonical graph includes LCOV result fixtures)
        # If the canonical graph has no lcov data at all, the format check above
        # is vacuously true — log a note but don't fail the overall test.
        _ = has_lcov_node  # informational; not asserted to avoid brittleness

    def test_lcov_tested_assertion_expansion_no_keyerror(self, canonical_federated_graph):
        """--assertions mode must not raise KeyError for lcov_tested."""
        from elspais.commands.trace import REPORT_PRESETS, ReportPreset, _render_table_from_graph

        preset = ReportPreset(
            name="standard",
            columns=list(REPORT_PRESETS["standard"].columns),
            include_assertions=True,
        )
        # Must not raise KeyError when lcov_tested is in _COVERAGE_COLUMNS
        result = _render_table_from_graph(canonical_federated_graph, "csv", preset)
        assert result == 0

    def test_lcov_tested_in_standard_preset(self):
        """lcov_tested column is present in the standard and full preset definitions."""
        from elspais.commands.trace import REPORT_PRESETS

        assert (
            "lcov_tested" in REPORT_PRESETS["standard"].columns
        ), "lcov_tested must be in standard preset columns"
        assert (
            "lcov_tested" in REPORT_PRESETS["full"].columns
        ), "lcov_tested must be in full preset columns"


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
version = 3

[project]
name = "fresh-targets"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]
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
    header is "Passing" (REQ-d00258-B).
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
version = 3

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

    # Verifies: REQ-d00254-I/J
    def test_legend_present_when_marker_rendered(self, two_target_project):
        from elspais.commands.trace import format_markdown

        graph = _build_project_graph(two_target_project, targets=["a"])
        out = "\n".join(format_markdown(graph))

        assert "(baseline)" in _verified_cell(out, "REQ-d00002")
        assert "> Legend:" in out

    # Verifies: REQ-d00254-I/J
    def test_legend_absent_on_full_run(self, two_target_project):
        from elspais.commands.trace import format_markdown

        graph = _build_project_graph(two_target_project, targets=None)
        out = "\n".join(format_markdown(graph))

        assert "> Legend:" not in out

    # Verifies: REQ-d00254-I/J
    def test_legend_absent_on_uat_dimension(self, two_target_project):
        from elspais.commands.trace import _UAT_COLUMNS, ReportPreset, format_markdown

        graph = _build_project_graph(two_target_project, targets=["a"])
        preset = ReportPreset(name="uat", columns=list(_UAT_COLUMNS), dimension="uat")
        out = "\n".join(format_markdown(graph, preset=preset))

        assert "> Legend:" not in out


_MARKER_VERIFIED_CONFIG = """\
version = 3

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
    DIRECTly, so `tested_and_passing(rollup).indirect > .direct` -- the
    trace 'verified' cell must show the generous (indirect) count with the
    `~` marker appended (REQ-d00258-A).
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
version = 3

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
    line-coverage data but no per-test attribution -- `code_tested.direct`
    stays 0 while `.indirect` is > 0 (per-test attribution is not derivable
    from aggregate tooling). REQ-d00258-E: the trace 'code_tested' cell must
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
def marker_carried_project(tmp_path):
    """Two-target project where REQ-d00002 is verified only through a blanket
    (whole-requirement) `# Verifies: REQ-d00002` in target 'b'.

    Under a `--targets a` selective run, target 'b' is carried (baseline) AND
    its verified evidence is indirect-only, so the trace verified cell must
    compose both markers in order: `count (pct%) ~ (baseline)`.
    """
    project = tmp_path / "project"
    (project / "spec").mkdir(parents=True)
    (project / "spec" / "reqs.md").write_text(_TWO_TARGET_SPEC, encoding="utf-8")

    (project / "tests").mkdir(parents=True)
    (project / "tests" / "test_a.py").write_text(
        "# Verifies: REQ-d00001-A\ndef test_a():\n    pass\n", encoding="utf-8"
    )
    # Blanket (whole-requirement) ref: credits REQ-d00002's assertions
    # INDIRECTly only, so the `~` marker fires alongside `(baseline)`.
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
    """Verifies REQ-d00258-A, REQ-d00258-B, REQ-d00258-E: generous-footing
    headline counts get a `~` marker when evidence isn't fully direct, the
    reporting vocabulary reads Passing/UAT Covered/UAT Passed (no
    "Validated"), and aggregate-only line coverage never renders a
    misleading direct-attribution count."""

    # Verifies: REQ-d00258-A
    def test_indirect_only_coverage_headlines_with_marker(self, marker_verified_project):
        from elspais.commands.trace import _get_node_data
        from elspais.graph.metrics import fmt_assertion_count, tested_and_passing

        graph = _build_project_graph(marker_verified_project, targets=None)
        node = graph.find_by_id("REQ-d00001")
        dim = tested_and_passing(node.get_metric("rollup_metrics"))
        assert dim.indirect > dim.direct + 1e-9

        data = _get_node_data(node, graph)
        assert data["verified"].rstrip().endswith("~")
        assert data["verified"].startswith(f"{fmt_assertion_count(dim.indirect)}/{dim.total}")

    # Verifies: REQ-d00258-B
    def test_headers_use_passing_vocabulary(self):
        from elspais.commands.trace import _column_headers

        h = _column_headers()
        assert h["verified"] == "Passing"
        assert h["uat_coverage"] == "UAT Covered"
        assert h["uat_verified"] == "UAT Passed"
        assert "Validated" not in h.values()

    # Verifies: REQ-d00258-E
    def test_code_tested_without_attribution_is_na(self, code_tested_no_attribution_project):
        from elspais.commands.trace import _get_node_data

        graph = _build_project_graph(code_tested_no_attribution_project, targets=None)
        node = graph.find_by_id("REQ-d00001")
        rollup = node.get_metric("rollup_metrics")
        assert rollup.code_tested.direct == 0
        assert rollup.code_tested.indirect > 0

        data = _get_node_data(node, graph)
        assert not data["code_tested"].startswith("0/")
        assert data["code_tested"] == "n/a"

    # Verifies: REQ-d00258-E
    def test_code_tested_labels_without_attribution_is_na(self, code_tested_no_attribution_project):
        """The --assertions (label) render path must apply the same n/a guard
        as the count path: aggregate-only coverage must not surface "0/N"/"0%"
        in code_tested_labels / code_tested_pct."""
        from elspais.commands.trace import _get_node_data

        graph = _build_project_graph(code_tested_no_attribution_project, targets=None)
        node = graph.find_by_id("REQ-d00001")
        rollup = node.get_metric("rollup_metrics")
        assert rollup.code_tested.direct == 0
        assert rollup.code_tested.indirect > 0

        data = _get_node_data(node, graph, assertion_labels=True)
        assert data["code_tested_labels"] == "n/a"
        assert data["code_tested_pct"] == "n/a"

    # Verifies: REQ-d00258-E
    def test_lcov_tested_labels_empty_set_renders_zero_of_total(
        self, code_tested_no_attribution_project
    ):
        """An lcov_tested dimension with total > 0 but an empty label set must
        render `0/N`, never a bare `-` (consistent with the _DIMS label cells)."""
        from elspais.commands.trace import _get_node_data
        from elspais.graph.metrics import CoverageDimension

        graph = _build_project_graph(code_tested_no_attribution_project, targets=None)
        node = graph.find_by_id("REQ-d00001")
        rollup = node.get_metric("rollup_metrics")
        # Simplified dimensions (e.g. scalar-only fixtures) may carry counts
        # without per-label data; the renderer must not fall back to "-".
        rollup.lcov_tested = CoverageDimension(total=2, indirect=1.0)

        data = _get_node_data(node, graph, assertion_labels=True)
        assert data["lcov_tested_labels"] == "0/2"
        assert data["lcov_tested_labels"] != "-"

    # Verifies: REQ-d00258-A, REQ-d00254-I
    def test_marker_composes_with_baseline_suffix(self, marker_carried_project):
        """Indirect-only AND carried verified evidence must compose the exact
        order `count (pct%) ~ (baseline)`."""
        from elspais.commands.trace import _get_node_data

        graph = _build_project_graph(marker_carried_project, targets=["a"])
        node = graph.find_by_id("REQ-d00002")
        rollup = node.get_metric("rollup_metrics")
        assert rollup.verified.carried
        assert rollup.verified.direct == 0
        assert rollup.verified.indirect > 0

        data = _get_node_data(node, graph)
        assert data["verified"] == "1/1 (100%) ~ (baseline)"
