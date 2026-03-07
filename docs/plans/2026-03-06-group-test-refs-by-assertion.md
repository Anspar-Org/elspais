# Group Test Refs by Assertion — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Group test references by assertion label in all trace report formats (markdown, HTML, CSV, JSON) so readers can see which tests cover which assertions.

**Architecture:** Enrich `_get_node_data()` to produce a `test_refs_grouped` dict mapping assertion labels to test IDs (using `edge.assertion_targets` from outgoing edges). Each formatter renders this grouped structure in its format-appropriate way. CSV gains a `Kind` row-type column.

**Tech Stack:** Python 3.10+, pytest, no new dependencies.

---

### Task 1: Add `test_refs_grouped` to `_get_node_data()`

**Files:**
- Modify: `src/elspais/commands/trace.py:93-152`
- Test: `tests/commands/test_trace_grouped_refs.py` (new)

**Step 1: Write the failing test**

Create `tests/commands/test_trace_grouped_refs.py`:

```python
"""Tests for grouped test ref output in trace formatters."""

from elspais.graph import NodeKind
from elspais.graph.GraphNode import GraphNode
from elspais.graph.builder import TraceGraph
from elspais.graph.relations import EdgeKind


def _build_graph_with_test_refs():
    """Build a minimal graph with a requirement, assertions, and TEST nodes.

    Graph structure:
        REQ-p00001 (PRD, Active, assertions A, B)
          -> TEST whole-req (no assertion targets)
          -> TEST assertion-A (targets ["A"])
          -> TEST assertion-B (targets ["B"])
          -> TEST assertion-AB (targets ["A", "B"])
    """
    graph = TraceGraph()

    # Requirement node
    req = GraphNode("REQ-p00001", NodeKind.REQUIREMENT, label="Test Requirement")
    req.set_field("level", "prd")
    req.set_field("status", "Active")
    graph._index[req.id] = req
    graph._roots.append(req)

    # Assertion nodes
    assert_a = GraphNode("REQ-p00001-A", NodeKind.ASSERTION, label="SHALL do A")
    assert_a.set_field("label", "A")
    graph._index[assert_a.id] = assert_a
    req.link(assert_a, EdgeKind.CONTAINS)

    assert_b = GraphNode("REQ-p00001-B", NodeKind.ASSERTION, label="SHALL do B")
    assert_b.set_field("label", "B")
    graph._index[assert_b.id] = assert_b
    req.link(assert_b, EdgeKind.CONTAINS)

    # TEST node: whole-requirement (no assertion targets)
    test_whole = GraphNode("test:tests/test_whole.py:1", NodeKind.TEST, label="test_whole")
    graph._index[test_whole.id] = test_whole
    req.link(test_whole, EdgeKind.VALIDATES)

    # TEST node: targets assertion A only
    test_a = GraphNode(
        "test:tests/test_a.py::test_REQ_p00001_A_works", NodeKind.TEST, label="test_a"
    )
    graph._index[test_a.id] = test_a
    req.link(test_a, EdgeKind.VALIDATES, assertion_targets=["A"])

    # TEST node: targets assertion B only
    test_b = GraphNode(
        "test:tests/test_b.py::test_REQ_p00001_B_works", NodeKind.TEST, label="test_b"
    )
    graph._index[test_b.id] = test_b
    req.link(test_b, EdgeKind.VALIDATES, assertion_targets=["B"])

    # TEST node: targets both A and B
    test_ab = GraphNode(
        "test:tests/test_ab.py::test_REQ_p00001_A_B_both", NodeKind.TEST, label="test_ab"
    )
    graph._index[test_ab.id] = test_ab
    req.link(test_ab, EdgeKind.VALIDATES, assertion_targets=["A", "B"])

    return graph


class TestGetNodeDataGroupedRefs:
    """Tests for test_refs_grouped in _get_node_data()."""

    def test_grouped_refs_whole_req(self):
        """Whole-requirement tests appear under '*' key."""
        from elspais.commands.trace import _get_node_data

        graph = _build_graph_with_test_refs()
        req = graph.find_by_id("REQ-p00001")
        data = _get_node_data(req, graph)

        assert "*" in data["test_refs_grouped"]
        assert len(data["test_refs_grouped"]["*"]) == 1
        assert "test:tests/test_whole.py:1" in data["test_refs_grouped"]["*"]

    def test_grouped_refs_assertion_targeted(self):
        """Assertion-targeted tests appear under their label keys."""
        from elspais.commands.trace import _get_node_data

        graph = _build_graph_with_test_refs()
        req = graph.find_by_id("REQ-p00001")
        data = _get_node_data(req, graph)

        assert "A" in data["test_refs_grouped"]
        # A should have test_a and test_ab
        a_refs = data["test_refs_grouped"]["A"]
        assert len(a_refs) == 2
        assert any("test_REQ_p00001_A_works" in r for r in a_refs)
        assert any("test_REQ_p00001_A_B_both" in r for r in a_refs)

    def test_grouped_refs_multi_target(self):
        """Multi-target tests appear under each targeted assertion."""
        from elspais.commands.trace import _get_node_data

        graph = _build_graph_with_test_refs()
        req = graph.find_by_id("REQ-p00001")
        data = _get_node_data(req, graph)

        # test_ab should appear under both A and B
        assert any("test_REQ_p00001_A_B_both" in r for r in data["test_refs_grouped"]["A"])
        assert any("test_REQ_p00001_A_B_both" in r for r in data["test_refs_grouped"]["B"])

    def test_flat_test_refs_still_present(self):
        """Flat test_refs list is still populated for backward compat."""
        from elspais.commands.trace import _get_node_data

        graph = _build_graph_with_test_refs()
        req = graph.find_by_id("REQ-p00001")
        data = _get_node_data(req, graph)

        assert len(data["test_refs"]) == 4
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/commands/test_trace_grouped_refs.py::TestGetNodeDataGroupedRefs -v`
Expected: FAIL — `test_refs_grouped` key doesn't exist in the dict.

**Step 3: Implement `test_refs_grouped` in `_get_node_data()`**

In `src/elspais/commands/trace.py`, replace the test_refs gathering block (lines 109-113) with:

```python
    # Get test references (TEST nodes that validate this requirement)
    # Build both flat list and grouped-by-assertion dict
    test_refs = []
    test_refs_grouped: dict[str, list[str]] = {}
    for edge in node.iter_outgoing_edges():
        if edge.target.kind == NodeKind.TEST:
            test_refs.append(edge.target.id)
            if edge.assertion_targets:
                for label in edge.assertion_targets:
                    test_refs_grouped.setdefault(label, []).append(edge.target.id)
            else:
                test_refs_grouped.setdefault("*", []).append(edge.target.id)
```

Add `"test_refs_grouped": test_refs_grouped,` to the return dict (after `"test_refs"`). Add this import at the top of the function or file: the `EdgeKind` isn't needed since we iterate all outgoing edges and filter by target kind.

**Step 4: Run test to verify it passes**

Run: `pytest tests/commands/test_trace_grouped_refs.py::TestGetNodeDataGroupedRefs -v`
Expected: 4 PASS

**Step 5: Commit**

```
[CUR-1081] feat: add test_refs_grouped to _get_node_data
```

---

### Task 2: Update Markdown Formatter

**Files:**
- Modify: `src/elspais/commands/trace.py:219-226` (format_markdown)
- Test: `tests/commands/test_trace_grouped_refs.py`

**Step 1: Write the failing test**

Add to `tests/commands/test_trace_grouped_refs.py`:

```python
class TestMarkdownGroupedRefs:
    """Tests for grouped test refs in markdown output."""

    def test_markdown_groups_by_assertion(self):
        """Markdown output groups test refs under assertion labels."""
        from elspais.commands.trace import ReportPreset, format_markdown

        graph = _build_graph_with_test_refs()
        preset = ReportPreset(
            name="full",
            columns=["id", "title"],
            include_test_refs=True,
        )

        output = "\n".join(format_markdown(graph, preset))

        # Should have assertion group headers
        assert "**Whole-requirement**" in output
        assert "**A**" in output
        assert "**B**" in output

    def test_markdown_whole_req_listed_first(self):
        """Whole-requirement tests are listed before assertion-specific ones."""
        from elspais.commands.trace import ReportPreset, format_markdown

        graph = _build_graph_with_test_refs()
        preset = ReportPreset(
            name="full",
            columns=["id", "title"],
            include_test_refs=True,
        )

        output = "\n".join(format_markdown(graph, preset))

        whole_pos = output.index("**Whole-requirement**")
        a_pos = output.index("**A**")
        assert whole_pos < a_pos

    def test_markdown_no_test_refs_no_section(self):
        """No test refs section when requirement has no tests."""
        from elspais.commands.trace import ReportPreset, format_markdown

        graph = TraceGraph()
        req = GraphNode("REQ-p00002", NodeKind.REQUIREMENT, label="No Tests")
        req.set_field("level", "prd")
        req.set_field("status", "Active")
        graph._index[req.id] = req
        graph._roots.append(req)

        preset = ReportPreset(
            name="full",
            columns=["id", "title"],
            include_test_refs=True,
        )

        output = "\n".join(format_markdown(graph, preset))
        assert "Test Refs" not in output
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/commands/test_trace_grouped_refs.py::TestMarkdownGroupedRefs -v`
Expected: FAIL — markdown still renders flat list without group headers.

**Step 3: Update `format_markdown()`**

Replace the test_refs block (lines 219-226) in `src/elspais/commands/trace.py`:

```python
        if preset.include_test_refs and data["test_refs_grouped"]:
            total = len(data["test_refs"])
            yield ""
            yield f"<details><summary>Test Refs ({total})</summary>"
            yield ""
            grouped = data["test_refs_grouped"]
            # Whole-requirement tests first, then assertion labels sorted
            for key in ["*"] + sorted(k for k in grouped if k != "*"):
                if key not in grouped:
                    continue
                refs = grouped[key]
                label = "Whole-requirement" if key == "*" else key
                yield f"**{label}** ({len(refs)}):"
                for ref in refs:
                    yield f"- `{ref}`"
                yield ""
            yield "</details>"
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/commands/test_trace_grouped_refs.py::TestMarkdownGroupedRefs -v`
Expected: 3 PASS

**Step 5: Commit**

```
[CUR-1081] feat: group test refs by assertion in markdown trace output
```

---

### Task 3: Update HTML Table Formatter

**Files:**
- Modify: `src/elspais/commands/trace.py:312-317` (format_html)
- Test: `tests/commands/test_trace_grouped_refs.py`

**Step 1: Write the failing test**

Add to `tests/commands/test_trace_grouped_refs.py`:

```python
class TestHtmlGroupedRefs:
    """Tests for grouped test refs in HTML output."""

    def test_html_groups_by_assertion(self):
        """HTML output groups test refs under assertion labels."""
        from elspais.commands.trace import ReportPreset, format_html

        graph = _build_graph_with_test_refs()
        preset = ReportPreset(
            name="full",
            columns=["id", "title"],
            include_test_refs=True,
        )

        output = "\n".join(format_html(graph, preset))

        assert "<strong>Whole-requirement</strong>" in output
        assert "<strong>A</strong>" in output
        assert "<strong>B</strong>" in output

    def test_html_test_refs_in_code_tags(self):
        """Each test ref is wrapped in <code> tags."""
        from elspais.commands.trace import ReportPreset, format_html

        graph = _build_graph_with_test_refs()
        preset = ReportPreset(
            name="full",
            columns=["id", "title"],
            include_test_refs=True,
        )

        output = "\n".join(format_html(graph, preset))

        assert "<code>test:tests/test_whole.py:1</code>" in output
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/commands/test_trace_grouped_refs.py::TestHtmlGroupedRefs -v`
Expected: FAIL — no `<strong>` assertion labels in output.

**Step 3: Update `format_html()`**

Replace the test_refs block (lines 312-317) in `src/elspais/commands/trace.py`:

```python
        if preset.include_test_refs:
            grouped = data["test_refs_grouped"]
            if grouped:
                parts = []
                for key in ["*"] + sorted(k for k in grouped if k != "*"):
                    if key not in grouped:
                        continue
                    refs = grouped[key]
                    label = "Whole-requirement" if key == "*" else key
                    ref_html = "<br>".join(
                        f"<code>{escape_html(r)}</code>" for r in refs
                    )
                    parts.append(
                        f"<strong>{escape_html(label)}</strong> ({len(refs)}):<br>{ref_html}"
                    )
                cells.append(f"<td class='refs'>{'<br><br>'.join(parts)}</td>")
            else:
                cells.append("<td>-</td>")
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/commands/test_trace_grouped_refs.py::TestHtmlGroupedRefs -v`
Expected: 2 PASS

**Step 5: Commit**

```
[CUR-1081] feat: group test refs by assertion in HTML trace output
```

---

### Task 4: Update JSON Formatter

**Files:**
- Modify: `src/elspais/commands/trace.py:354-355` (format_json)
- Test: `tests/commands/test_trace_grouped_refs.py`

**Step 1: Write the failing test**

Add to `tests/commands/test_trace_grouped_refs.py`:

```python
import json


class TestJsonGroupedRefs:
    """Tests for grouped test refs in JSON output."""

    def test_json_test_refs_is_dict(self):
        """JSON output uses grouped dict for test_refs."""
        from elspais.commands.trace import ReportPreset, format_json

        graph = _build_graph_with_test_refs()
        preset = ReportPreset(
            name="full",
            columns=["id", "title"],
            include_test_refs=True,
        )

        output = "\n".join(format_json(graph, preset))
        data = json.loads(output)

        req = data[0]
        assert isinstance(req["test_refs"], dict)
        assert "*" in req["test_refs"]
        assert "A" in req["test_refs"]
        assert "B" in req["test_refs"]

    def test_json_grouped_refs_content(self):
        """JSON grouped refs contain correct test IDs."""
        from elspais.commands.trace import ReportPreset, format_json

        graph = _build_graph_with_test_refs()
        preset = ReportPreset(
            name="full",
            columns=["id", "title"],
            include_test_refs=True,
        )

        output = "\n".join(format_json(graph, preset))
        data = json.loads(output)

        req = data[0]
        assert len(req["test_refs"]["*"]) == 1
        assert len(req["test_refs"]["A"]) == 2
        assert len(req["test_refs"]["B"]) == 2
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/commands/test_trace_grouped_refs.py::TestJsonGroupedRefs -v`
Expected: FAIL — `test_refs` is a list, not a dict.

**Step 3: Update `format_json()`**

In `src/elspais/commands/trace.py`, change line 355 from:

```python
            node_dict["test_refs"] = data["test_refs"]
```

to:

```python
            node_dict["test_refs"] = data["test_refs_grouped"]
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/commands/test_trace_grouped_refs.py::TestJsonGroupedRefs -v`
Expected: 2 PASS

**Step 5: Commit**

```
[CUR-1081] feat: group test refs by assertion in JSON trace output
```

---

### Task 5: Update CSV Formatter with Kind Column

**Files:**
- Modify: `src/elspais/commands/trace.py:229-260` (format_csv)
- Test: `tests/commands/test_trace_grouped_refs.py`

**Step 1: Write the failing test**

Add to `tests/commands/test_trace_grouped_refs.py`:

```python
class TestCsvGroupedRefs:
    """Tests for grouped test refs in CSV output with Kind column."""

    def test_csv_has_kind_column(self):
        """CSV header includes Kind as first column when test refs enabled."""
        from elspais.commands.trace import ReportPreset, format_csv

        graph = _build_graph_with_test_refs()
        preset = ReportPreset(
            name="full",
            columns=["id", "title"],
            include_test_refs=True,
        )

        lines = list(format_csv(graph, preset))
        header = lines[0]

        assert header.startswith("Kind,")
        assert "Assertion" in header
        assert "Test Ref" in header

    def test_csv_req_row_kind(self):
        """Requirement rows have Kind=REQ."""
        from elspais.commands.trace import ReportPreset, format_csv

        graph = _build_graph_with_test_refs()
        preset = ReportPreset(
            name="full",
            columns=["id", "title"],
            include_test_refs=True,
        )

        lines = list(format_csv(graph, preset))
        # Line 1 is the REQ row (line 0 is header)
        assert lines[1].startswith("REQ,")

    def test_csv_test_rows_follow_req(self):
        """TEST rows follow their parent REQ row."""
        from elspais.commands.trace import ReportPreset, format_csv

        graph = _build_graph_with_test_refs()
        preset = ReportPreset(
            name="full",
            columns=["id", "title"],
            include_test_refs=True,
        )

        lines = list(format_csv(graph, preset))
        test_lines = [l for l in lines[1:] if l.startswith("TEST,")]
        assert len(test_lines) == 4  # whole, A, B, AB (AB appears under both A and B)

    def test_csv_test_row_has_assertion_label(self):
        """TEST rows include assertion label column."""
        from elspais.commands.trace import ReportPreset, format_csv

        graph = _build_graph_with_test_refs()
        preset = ReportPreset(
            name="full",
            columns=["id", "title"],
            include_test_refs=True,
        )

        lines = list(format_csv(graph, preset))
        test_lines = [l for l in lines[1:] if l.startswith("TEST,")]
        # At least one should have "*" for whole-req
        assert any(",*," in l for l in test_lines)
        # At least one should have "A"
        assert any(",A," in l for l in test_lines)

    def test_csv_no_kind_column_without_test_refs(self):
        """Kind column is NOT added when test refs are not included."""
        from elspais.commands.trace import ReportPreset, format_csv

        graph = _build_graph_with_test_refs()
        preset = ReportPreset(
            name="full",
            columns=["id", "title"],
            include_test_refs=False,
        )

        lines = list(format_csv(graph, preset))
        assert not lines[0].startswith("Kind,")
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/commands/test_trace_grouped_refs.py::TestCsvGroupedRefs -v`
Expected: FAIL — no Kind column, no TEST rows.

**Step 3: Update `format_csv()`**

Replace the entire `format_csv()` function body with:

```python
def format_csv(graph: TraceGraph, preset: ReportPreset | None = None) -> Iterator[str]:
    """Generate CSV. Streams one node at a time.

    When test refs are included, adds a Kind column (first) and Assertion/Test Ref
    columns (last). Each test ref gets its own TEST row after its parent REQ row.
    """
    if preset is None:
        preset = REPORT_PRESETS[DEFAULT_PRESET]

    def escape(s: str) -> str:
        if "," in s or '"' in s or "\n" in s:
            return '"' + s.replace('"', '""') + '"'
        return s

    # Build header
    col_headers = _column_headers()
    header_names = [col_headers.get(c, c.title()) for c in preset.columns]

    extra_prefix = []
    extra_suffix = []
    if preset.include_test_refs:
        extra_prefix.append("Kind")
        extra_suffix.extend(["Assertion", "Test Ref"])
    if preset.include_assertions:
        extra_suffix.insert(0, "Assertions")

    yield ",".join(extra_prefix + header_names + extra_suffix)

    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        data = _get_node_data(node, graph)
        row_values = [escape(v) for v in _format_row(data, preset.columns)]

        # Build REQ row
        req_prefix = ["REQ"] if preset.include_test_refs else []
        req_suffix = []
        if preset.include_assertions:
            assertions_str = "; ".join(
                f"{a['label']}: {a['text']}" for a in data["assertions"]
            )
            req_suffix.append(escape(assertions_str))
        if preset.include_test_refs:
            req_suffix.extend(["", ""])  # Empty Assertion and Test Ref columns for REQ row

        yield ",".join(req_prefix + row_values + req_suffix)

        # Emit TEST child rows
        if preset.include_test_refs:
            grouped = data["test_refs_grouped"]
            empty_cols = [""] * len(preset.columns)
            empty_assertions = [""] if preset.include_assertions else []
            for key in ["*"] + sorted(k for k in grouped if k != "*"):
                if key not in grouped:
                    continue
                for ref in grouped[key]:
                    yield ",".join(
                        ["TEST"] + empty_cols + empty_assertions + [key, escape(ref)]
                    )
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/commands/test_trace_grouped_refs.py::TestCsvGroupedRefs -v`
Expected: 5 PASS

**Step 5: Run ALL test_trace tests to check for regressions**

Run: `pytest tests/commands/test_trace_grouped_refs.py tests/test_trace_command.py -v`
Expected: All PASS

**Step 6: Commit**

```
[CUR-1081] feat: group test refs by assertion in CSV trace output with Kind column
```

---

### Task 6: Fix Existing Tests for CSV Schema Change

**Files:**
- Modify: `tests/test_trace_command.py` (if any CSV tests break due to Kind column)

**Step 1: Run full test suite**

Run: `pytest tests/test_trace_command.py tests/commands/test_report.py -v`
Expected: Check if any existing tests need updating for the new CSV format (Kind column only appears when `include_test_refs=True`, so existing tests that don't use `--tests` should pass unchanged).

**Step 2: Fix any failures**

Existing CSV tests in `test_trace_command.py` don't set `include_test_refs=True` (they use the default preset without `--tests`), so they should pass without changes. If any break, update assertions to account for the new format.

**Step 3: Commit (only if changes needed)**

```
[CUR-1081] fix: update existing trace tests for CSV schema change
```

---

### Task 7: Regenerate Reports

**Step 1: Regenerate the reports to verify the new output**

Run the same commands used to generate `reports/trace-detailed.md` and spot-check the grouped output.

**Step 2: Commit updated reports (if tracked)**

```
[CUR-1081] chore: regenerate trace reports with grouped test refs
```
