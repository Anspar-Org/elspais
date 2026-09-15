# Command API Boundary — Phase A Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every `compute_*` function take a typed request holding final values, so a declared `--scope` is derived exactly once at the edge it was invoked from.

**Architecture:** Each surface (CLI, HTTP, MCP) derives its own inputs once and constructs a frozen request dataclass. `compute_*` resolves nothing and never sees a `dict[str, str]` or an `argparse.Namespace`. The `written` provenance flag is consumed at the edge and never travels.

**Tech Stack:** Python 3.10+, `tomlkit`, `pydantic>=2`, `tyro>=0.9`, pytest.

**Spec:** `docs/design/2026-09-14-command-api-boundary-design.md`

## Global Constraints

- **No backwards compatibility.** Per CLAUDE.md, do not add a shim, alias, or branch accepting the old shape. Where an input is no longer admitted, refuse it with a message naming what to change.
- **One authority per concern.** Value/scope resolution stays in `graph/values.py` and `graph/scope`; this plan moves *call sites*, never logic.
- **Citation comments.** Every new function carries `# Implements: <REQ ids>` per the repo's convention. Reuse the REQ ids already cited at the site being moved.
- **Test tiers.** `pytest` (unit, ~26s) during development. `pytest -m ""` before push.
- **Commit discipline.** One commit per task.
- **Sub-agent for tests.** Per CLAUDE.md, dispatch a sub-agent to write test code unless you are the sub-agent.

## Scope

This plan covers **Phase A only** — the six `compute_*` functions and their three
surfaces. Phase B (parser emits final values; one parse; `_to_namespace`
deleted) is a separate plan; the spec's open question is resolved in its
Appendix and B is unblocked.

## File Structure

| File | Responsibility |
|---|---|
| `src/elspais/commands/_requests.py` | **Create.** The six frozen request dataclasses. No logic beyond construction. |
| `src/elspais/commands/_edges.py` | **Create.** `from_args()` / `from_params()` builders — the two derivation edges, one place each. |
| `src/elspais/commands/summary.py` | `compute_summary` takes `SummaryRequest`; `run` builds it; dual-shape helpers deleted. |
| `src/elspais/commands/trace.py` | Same for `compute_trace`. |
| `src/elspais/commands/gaps.py` | Same for `compute_gaps`; the hand-rolled resolve-before-send becomes the shared edge. |
| `src/elspais/commands/analysis_cmd.py` | Same for `compute_analysis`. |
| `src/elspais/commands/health.py` | `compute_checks` takes `ChecksRequest`; `fake_args` deleted. |
| `src/elspais/commands/search_cmd.py` | Same for `compute_search`. |
| `src/elspais/commands/_values.py` | `resolve_report_values(args_or_params, ...)` dual shape deleted. |
| `src/elspais/commands/_scope.py` | `resolve_scope_for_report(graph, args_or_params, ...)` dual shape deleted. |
| `src/elspais/server/routes_api.py` | All six routes build requests via one translator. |
| `src/elspais/commands/_engine.py` | `call()` takes a request; serializes for HTTP itself. |
| `tests/commands/test_report_values.py` | `_run_listing` extended to `summary` and `trace`. |
| `tests/commands/test_request_edges.py` | **Create.** Per-surface parity tests. |

---

### Task 1: The request types and the two edges

**Files:**
- Create: `src/elspais/commands/_requests.py`
- Create: `src/elspais/commands/_edges.py`
- Test: `tests/commands/test_request_edges.py`

**Interfaces:**
- Consumes: `elspais.graph.values.resolve_values`, `ValueSelection`; `elspais.commands._values.values_from_args/values_from_params`; `elspais.commands._scope.scope_from_args/scope_from_params`; `elspais.graph.scope.ReportScope`.
- Produces: `ReportInputs`, `SummaryRequest`, `TraceRequest`, `GapsRequest`, `AnalysisRequest`, `ChecksRequest`, `SearchRequest`; `report_inputs_from_args(args, config, offered, identity_key)`, `report_inputs_from_params(params, offered, identity_key)`.

- [ ] **Step 1: Write the failing test**

Create `tests/commands/test_request_edges.py`:

```python
# Verifies: REQ-d00280-D, REQ-d00282-E
"""The two derivation edges arrive at the same final values.

A declared name is the project's and passes over what a report does not offer;
a written selection is the reader's and is refused. Only the CLI edge can tell
them apart, because only it has seen the config. Once derived, both edges
produce the same tuple -- a difference here is a daemon-served report
disagreeing with a locally computed one.
"""

from __future__ import annotations

import argparse

import pytest

OFFERED = ("level", "requirements", "tested")


def test_a_declared_name_passes_over_what_this_report_does_not_offer():
    from elspais.commands._edges import report_inputs_from_args

    config = {"scopes": {"board": {"values": ["id", "requirements", "tested"]}}}
    args = argparse.Namespace(scope="board", values=None)
    inputs = report_inputs_from_args(args, config, OFFERED, identity_key="level")
    assert inputs.values == ("level", "requirements", "tested")


def test_a_written_selection_naming_an_unoffered_value_is_refused():
    from elspais.commands._edges import report_inputs_from_args
    from elspais.commands._values import UnofferedValues

    args = argparse.Namespace(scope=None, values="id,tested")
    with pytest.raises(UnofferedValues) as excinfo:
        report_inputs_from_args(args, None, OFFERED, identity_key="level")
    assert excinfo.value.unoffered == ("id",)


def test_the_params_edge_reaches_the_same_values_the_args_edge_did():
    """What travels is the selection as RESOLVED, so the serving process is
    handed a finished list and judges it only against its own offer."""
    from elspais.commands._edges import report_inputs_from_args, report_inputs_from_params

    config = {"scopes": {"board": {"values": ["id", "requirements", "tested"]}}}
    args = argparse.Namespace(scope="board", values=None)
    local = report_inputs_from_args(args, config, OFFERED, identity_key="level")
    served = report_inputs_from_params(local.to_params(), OFFERED, identity_key="level")
    assert served.values == local.values


@pytest.mark.parametrize(
    "request_factory",
    (
        lambda R: R.GapsRequest(values=("tested",), command="untested", treat_active=("draft",)),
        lambda R: R.AnalysisRequest(values=("id",), top=5, include_code=True, weights="pagerank"),
        lambda R: R.ChecksRequest(spec_only=True, treat_active=("draft",)),
        lambda R: R.SearchRequest(q="widget", field="title", limit=5, regex=True),
    ),
)
def test_no_field_is_lost_on_the_way_to_a_serving_process(request_factory):
    """A field left out of ``to_params`` is a field a daemon-served report is
    computed without, and the report still looks like the one asked for."""
    import dataclasses

    from elspais.commands import _requests

    request = request_factory(_requests)
    params = request.to_params()
    for field in dataclasses.fields(request):
        if field.name == "scope":
            continue
        value = getattr(request, field.name)
        if value in ((), None, False, ""):
            continue
        assert any(field.name == key for key in params), f"{field.name} never travels"


def test_nothing_named_stays_None_so_the_default_report_is_distinguishable():
    """An unstamped payload IS the default report; collapsing None into the
    default set would make a consumer unable to tell a reader who asked for
    everything from one who asked for nothing."""
    from elspais.commands._edges import report_inputs_from_args

    args = argparse.Namespace(scope=None, values=None)
    assert report_inputs_from_args(args, None, OFFERED, identity_key="level").values is None
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/commands/test_request_edges.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'elspais.commands._edges'`

- [ ] **Step 3: Write `_requests.py`**

```python
# Implements: REQ-d00282-A+E, REQ-d00280-D
"""What a report operation is asked for, as final values.

A request is what reaches a ``compute_*`` function. It holds values that have
already been derived -- a scope expanded, a selection resolved, a repeated flag
flattened -- so the operation states a report rather than deciding what was
asked for. Deriving happens once, at whichever edge was invoked; nothing here
reads a config, an ``argparse.Namespace`` or a query string.

``values`` is ``None`` where nothing was named, which is NOT the same as the
default set: an unstamped payload is the default report (REQ-d00282-E).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from elspais.graph.scope import ReportScope


@dataclass(frozen=True)
class ReportInputs:
    """The two axes every report over a set of requirements reads."""

    scope: ReportScope | None = None
    values: tuple[str, ...] | None = None

    def to_params(self) -> dict[str, str]:
        """Serialize for a serving process. The mirror of ``report_inputs_from_params``."""
        from elspais.commands._scope import scope_to_params
        from elspais.commands._values import VALUES_PARAM
        from elspais.graph.values import VALUE_LIST_SEPARATOR

        params = dict(scope_to_params(self.scope))
        if self.values is not None:
            params[VALUES_PARAM] = VALUE_LIST_SEPARATOR.join(self.values)
        return params


@dataclass(frozen=True)
class SummaryRequest(ReportInputs):
    """Coverage rolled up by level."""


@dataclass(frozen=True)
class TraceRequest(ReportInputs):
    """Facts about each requirement."""


@dataclass(frozen=True)
class GapsRequest(ReportInputs):
    """Requirements one dimension has not credited.

    ``command`` names which shorthand is being produced, so a section asked for
    alone and the same section composed with others offer the same values
    (REQ-d00279-C).
    """

    command: str = "gaps"
    treat_active: tuple[str, ...] = ()

    def to_params(self) -> dict[str, str]:
        """Every field, not only the inherited two: a field left out of this
        map is a field a daemon-served report is computed without."""
        params = super().to_params()
        params["command"] = self.command
        if self.treat_active:
            params["treat_active"] = ",".join(self.treat_active)
        return params


@dataclass(frozen=True)
class AnalysisRequest(ReportInputs):
    """Requirements ranked by foundational importance."""

    top: int = 10
    include_code: bool = False
    weights: str | None = None

    def to_params(self) -> dict[str, str]:
        params = super().to_params()
        params["top"] = str(self.top)
        if self.include_code:
            params["include_code"] = "true"
        if self.weights:
            params["weights"] = self.weights
        return params


@dataclass(frozen=True)
class ChecksRequest:
    """Health findings about the project.

    Reads no scope and no value selection: it reports findings rather than facts
    about each requirement (REQ-d00282-F).
    """

    spec_only: bool = False
    code_only: bool = False
    tests_only: bool = False
    terms_only: bool = False
    lenient: bool = False
    treat_active: tuple[str, ...] = ()

    @property
    def run_all(self) -> bool:
        return not any([self.spec_only, self.code_only, self.tests_only, self.terms_only])

    def to_params(self) -> dict[str, str]:
        params = {
            name: "true"
            for name in ("spec_only", "code_only", "tests_only", "terms_only", "lenient")
            if getattr(self, name)
        }
        if self.treat_active:
            params["treat_active"] = ",".join(self.treat_active)
        return params


@dataclass(frozen=True)
class SearchRequest:
    """A multi-term query over the graph."""

    q: str = ""
    field: str = "all"
    limit: int = 50
    regex: bool = False

    def to_params(self) -> dict[str, str]:
        params = {"q": self.q, "limit": str(self.limit)}
        if self.field:
            params["field"] = self.field
        if self.regex:
            params["regex"] = "true"
        return params
```

- [ ] **Step 4: Write `_edges.py`**

```python
# Implements: REQ-d00282-E, REQ-d00280-D
"""The two places a report's inputs are derived.

There are exactly two, because there are exactly two things an invocation can
arrive as: what a reader typed, and what a serving process was handed. They
differ in one respect only -- the first has seen the project's config and can
expand a declared name, the second has not and must not try.

Derivation is the SAME operation at both edges: ``resolve_values`` passes over
what a declaration names and this report does not offer, and refuses what a
reader wrote. On an already-resolved list it validates and changes nothing, so
the params edge judges a finished selection only against its own offer.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from elspais.commands._requests import ReportInputs


# Implements: REQ-d00280-D
def report_inputs_from_args(
    args: Any,
    config: Mapping[str, Any] | None,
    offered: Sequence[str],
    identity_key: str = "id",
) -> ReportInputs:
    """Derive from what a reader typed. The ONLY edge that reads config."""
    from elspais.commands._scope import scope_from_args
    from elspais.commands._values import values_from_args
    from elspais.graph.values import resolve_values

    selection = values_from_args(args, config)
    return ReportInputs(
        scope=scope_from_args(args, config),
        values=None if selection is None else resolve_values(selection, offered, identity_key),
    )


# Implements: REQ-d00282-E
def report_inputs_from_params(
    params: Mapping[str, str],
    offered: Sequence[str],
    identity_key: str = "id",
) -> ReportInputs:
    """Derive from what a serving process was handed.

    No config: a declaration was expanded by the edge that had one, so what
    arrives here is a finished list. Judging it again is validation, and a name
    this report does not offer is a caller's mistake (REQ-d00282-F).
    """
    from elspais.commands._scope import scope_from_params
    from elspais.commands._values import values_from_params
    from elspais.graph.values import resolve_values

    selection = values_from_params(params)
    return ReportInputs(
        scope=scope_from_params(params),
        values=None if selection is None else resolve_values(selection, offered, identity_key),
    )
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/commands/test_request_edges.py -q`
Expected: PASS (4 passed)

- [ ] **Step 6: Commit**

```bash
git add src/elspais/commands/_requests.py src/elspais/commands/_edges.py tests/commands/test_request_edges.py
git commit -m "[TOOL-82] Derive a report's inputs once, at the edge that was invoked"
```

---

### Task 2: `summary` honours a declared scope

**Files:**
- Modify: `src/elspais/commands/summary.py:233-262` (delete `_resolve_values_for` dual shape, rework `_stamp_values`), `:297` (`compute_summary`), `:331-360` (`run`)
- Test: `tests/commands/test_report_values.py`

**Interfaces:**
- Consumes: `report_inputs_from_args`, `report_inputs_from_params`, `SummaryRequest` from Task 1.
- Produces: `compute_summary(graph, config, request: SummaryRequest) -> dict`.

- [ ] **Step 1: Write the failing test**

Add to `tests/commands/test_report_values.py`, inside
`TestADeclarationNarrowsAShortfallListing`'s module (after the `scoped_project`
fixture at `:1735`). First extend the fixture config by adding this block to
`_SCOPED_PROJECT` (`:1707`):

```toml
[scopes.board]
level = ["prd"]
values = ["id", "requirements", "tested"]
```

Then extend `_run_listing` (`:1767`) with two branches, before the final
`return gaps_cmd.run(...)`:

```python
    if command == "summary":
        from elspais.commands import summary as summary_cmd

        return summary_cmd.run(
            argparse.Namespace(
                config=config, scope=scope, values=values, format="text",
                spec_dir=None, output=None, quiet=False, verbose=False,
            )
        )
    if command == "trace":
        from elspais.commands import trace as trace_cmd

        return trace_cmd.run(
            argparse.Namespace(
                config=config, scope=scope, values=values, format="text",
                spec_dir=None, output=None, quiet=False, verbose=False,
            )
        )
```

Then add the test class:

```python
# REQ-d00280-D: a declaration reaches the reports that state facts, too
class TestADeclarationNarrowsAFactStatingReport:
    """`gaps` resolves its selection before sending it; `summary` and `trace`
    sent the declaration raw and let the compute path judge it a second time,
    where nothing could know a project had declared it. The three reports a
    declared name spans have to agree about what the name means."""

    # Verifies: REQ-d00280-D, REQ-d00282-E
    def test_summary_passes_over_the_value_it_does_not_offer(self, scoped_project, no_compute):
        """`board` names id, which states what a ROW is about in a
        per-requirement report; summary's rows are levels, so it passes over
        and the identity value `level` takes its place."""
        with pytest.raises(_Computed) as excinfo:
            _run_listing("summary", scoped_project, scope="board")
        assert excinfo.value.params["values"] == "level,requirements,tested"

    # Verifies: REQ-d00280-D, REQ-d00282-E
    def test_trace_passes_over_a_different_value_of_the_same_declaration(
        self, scoped_project, no_compute
    ):
        """The same name against a report offering a different set: `trace`
        states facts per requirement, so `requirements` -- a count OF
        requirements -- is what passes over here."""
        with pytest.raises(_Computed) as excinfo:
            _run_listing("trace", scoped_project, scope="board")
        assert excinfo.value.params["values"] == "id,tested"

    # Verifies: REQ-d00280-D, REQ-d00282-F
    def test_a_value_the_reader_wrote_is_still_refused_by_summary(
        self, scoped_project, no_compute, capsys
    ):
        """Provenance is the whole of the difference: the same name a
        declaration passes over is, written here, a mistake."""
        try:
            code = _run_listing("summary", scoped_project, values="id")
        except _Computed:
            pytest.fail("'summary' computed a report under a value it does not offer")
        assert code == 2
        assert "id" in capsys.readouterr().err
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/commands/test_report_values.py -k ADeclarationNarrowsAFactStating -q`
Expected: FAIL, exactly:
```
AssertionError: assert 'id,requirements,tested' == 'level,requirements,tested'
AssertionError: assert 'id,requirements,tested' == 'id,tested'
```
(The third test passes already — the CLI-side pre-flight refusal is correct today. Keep it: it is the guard that the fix must not retire.)

- [ ] **Step 3: Rework `summary.py`**

Delete `_resolve_values_for` (`:233`) entirely. Replace `_stamp_values` (`:246`) with a version taking final values:

```python
# Implements: REQ-d00282-E
def _stamp_values(data: dict, values: tuple[str, ...] | None) -> None:
    """Record the stated values on the payload, where a selection named any.

    Stamped only when something was named: an unstamped payload is the default
    report, and stamping the default would make a consumer unable to tell a
    reader who asked for everything from one who asked for nothing.
    """
    if values is not None:
        data["values"] = list(values)
```

Change `compute_summary` (`:297`):

```python
# Implements: REQ-d00279-C
def compute_summary(graph: FederatedGraph, config: dict, request: SummaryRequest) -> dict:
    """The coverage summary this request asks for.

    Resolves nothing: the scope was expanded and the selection resolved at the
    edge that was invoked, which is the only place that could tell a project's
    declaration from a reader's own words (REQ-d00280-D).
    """
    from elspais.commands._scope import scope_disclosure
    from elspais.graph.scope import scoped_requirements

    result = scoped_requirements(graph, request.scope, config)
    ids = None if len(result.ids) == result.population else result.ids
    data = collect_coverage(graph, config=config, node_ids=ids)
    data["scope"] = scope_disclosure(result)
    _stamp_values(data, request.values)
    return data
```

In `run` (`:331-360`), replace the pre-flight block and `params` construction:

```python
    # Implements: REQ-d00282-F
    # Derived before anything is built or asked of a serving process: a report
    # is not produced under a selection the tool cannot honour, and a reader
    # told so before the work starts is told the same thing however the report
    # would have been answered.
    try:
        inputs = report_inputs_from_args(args, config, OFFERED_VALUES, IDENTITY_VALUE)
    except UnofferedValues as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 2

    request = SummaryRequest(scope=inputs.scope, values=inputs.values)
```

and pass `request` to both `compute_summary(graph, config, request)` and
`engine_call("/api/run/summary", request, compute_summary, ...)`.

Update `render_section` (`:266`) to derive once and call the same helper:

```python
    try:
        inputs = report_inputs_from_args(args, config, OFFERED_VALUES, IDENTITY_VALUE)
    except UnofferedValues as exc:
        return f"Coverage Summary\nerror: {exc}", 1
    data = compute_summary(graph, config, SummaryRequest(inputs.scope, inputs.values))
    return _render(data, fmt, config).rstrip("\n"), 0
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/commands/test_report_values.py tests/commands/test_summary.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/elspais/commands/summary.py tests/commands/test_report_values.py
git commit -m "[TOOL-82] Let summary read a declared scope as the project's, not the reader's"
```

---

### Task 3: `trace` honours a declared scope

**Files:**
- Modify: `src/elspais/commands/trace.py:192-222` (`compute_trace`), `:1045` (`render_section`), `:1175-1189` (`_resolve_values_or_report`), `:1262` (params construction)

**Interfaces:**
- Consumes: Task 1's builders; `TraceRequest`.
- Produces: `compute_trace(graph, config, request: TraceRequest) -> dict`.

- [ ] **Step 1: The failing test already exists** — `test_trace_passes_over_a_different_value_of_the_same_declaration` from Task 2 Step 1.

Run: `.venv/bin/python -m pytest tests/commands/test_report_values.py -k trace_passes_over -q`
Expected: FAIL with `assert 'id,requirements,tested' == 'id,tested'`

- [ ] **Step 2: Replace `_resolve_values_or_report` (`:1175`)**

```python
# Implements: REQ-d00282-A+F
def _resolve_inputs_or_report(
    args: argparse.Namespace,
    preset: ReportPreset,
    config: dict | None,
) -> ReportInputs | None:
    """This invocation's scope and values as final values, or None once the
    reader has been told why the selection was refused.

    One derivation, not two: the values the report renders and the values it
    asks a serving process for are the same tuple, because a second derivation
    is where they start disagreeing (REQ-d00282-E).
    """
    from elspais.commands._edges import report_inputs_from_args

    try:
        return report_inputs_from_args(args, config, OFFERED_VALUES, identity_key="id")
    except UnofferedValues as err:
        print(f"Error: {err}", file=sys.stderr)
        return None
```

**The preset default is applied by the caller, not the builder.**
`report_inputs_from_args` returns `values=None` where nothing was named, which is
what keeps "asked for nothing" distinguishable from "asked for everything"
(REQ-d00282-E). So `run` renders with:

```python
    values = inputs.values or _default_values(preset)
```

and passes `values` to the formatters while passing `inputs.values` (possibly
`None`) inside the request. `summary` needs no equivalent line: its
`_values_from_data` (`summary.py:226-229`) already falls back to
`DEFAULT_VALUES` when the payload carries no `values` key.

- [ ] **Step 3: Change `compute_trace` (`:192`)**

```python
def compute_trace(graph: FederatedGraph, config: dict, request: TraceRequest) -> dict:
    from elspais.commands._scope import scope_disclosure
    from elspais.graph.scope import scoped_requirements

    result = scoped_requirements(graph, request.scope, config)
    scope_ids = None if len(result.ids) == result.population else result.ids
    nodes = [_get_node_data(node, graph) for node in _scoped_requirements(graph, scope_ids)]
    payload: dict = {"nodes": nodes, "scope": scope_disclosure(result)}
    if request.values is not None:
        payload["values"] = list(request.values)
    return payload
```

- [ ] **Step 4: Update `run` (`:1262`)**

Replace `params = dict(scope_params_from_args(args, config)); params.update(value_params)` with
`request = TraceRequest(scope=inputs.scope, values=inputs.values)`, and pass
`request` to `compute_trace(...)` and `_engine.call("/api/run/trace", request, compute_trace, ...)`.
`resolve_scope_for_report(graph, params, config)` at `:1277` and `:1296` becomes
`scoped_requirements(graph, request.scope, config)`.

- [ ] **Step 5: Run the tests**

Run: `.venv/bin/python -m pytest tests/commands/test_report_values.py tests/test_trace_command.py tests/commands/test_scope_disclosure.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/elspais/commands/trace.py
git commit -m "[TOOL-82] Derive trace's values once and render from what travelled"
```

---

### Task 4: `gaps` and `analysis` take requests

**Files:**
- Modify: `src/elspais/commands/gaps.py:411-416` (`gap_sections`), `:535` (`compute_gaps`), `:585-630` (`run`)
- Modify: `src/elspais/commands/analysis_cmd.py:18` (`compute_analysis`) and its `run`

**Interfaces:**
- Produces: `compute_gaps(graph, config, request: GapsRequest) -> dict`, `compute_analysis(graph, config, request: AnalysisRequest) -> dict`, `gap_sections(values: tuple[str, ...] | None, command: str) -> list[str]`.

`gaps` already resolves before sending, so this task is a shape change, not a
behaviour change. Its existing tests are the regression guard: they must pass
unchanged.

- [ ] **Step 1: Run the existing gaps tests and record the baseline**

Run: `.venv/bin/python -m pytest tests/commands/test_report_values.py -k Shortfall -q`
Expected: PASS (this is the behaviour to preserve exactly)

- [ ] **Step 2: Change `gap_sections` to take final values**

```python
# Implements: REQ-d00282-O
def gap_sections(values: tuple[str, ...] | None, command: str = "gaps") -> list[str]:
    """The sections this request asks for, in the order it named them.

    Takes values already resolved against this command's offer, so composing a
    section and asking for it alone choose listings the same way (REQ-d00279-C).
    """
    offered = COMMAND_VALUES.get(command, OFFERED_VALUES)
    keys = offered if values is None else values
    return [GAP_SECTION_FOR_VALUE[key] for key in keys]
```

- [ ] **Step 3: Change `compute_gaps` and `run`**

`compute_gaps(graph, config, request: GapsRequest)` reads
`gap_sections(request.values, request.command)` and `request.treat_active`
instead of `params`. In `run`, build:

```python
    try:
        inputs = report_inputs_from_args(
            args, config, COMMAND_VALUES.get(command, OFFERED_VALUES), identity_key=""
        )
    except UnofferedValues as exc:
        print(f"Error: {command}: {exc}", file=sys.stderr)
        return 1

    request = GapsRequest(
        scope=inputs.scope,
        values=inputs.values,
        command=command,
        treat_active=flag_values(args, "treat_active"),
    )
```

Delete the hand-rolled `values_to_params(ValueSelection(keys=tuple(...)))` block
at `:614-621`; the edge now does what it was doing by hand.

- [ ] **Step 4: Change `analysis_cmd`**

`compute_analysis` (`analysis_cmd.py:18`) currently reads `params["top"]`,
`params["include_code"]` and `params["weights"]` (`:208-213`). Replace with:

```python
def compute_analysis(graph: Any, config: dict[str, Any], request: AnalysisRequest) -> dict:
    from elspais.commands._scope import scope_disclosure
    from elspais.graph.scope import scoped_requirements

    result = scoped_requirements(graph, request.scope, config)
    ids = None if len(result.ids) == result.population else result.ids
    data = _analyse(graph, config, ids, top=request.top,
                    include_code=request.include_code, weights=request.weights)
    data["scope"] = scope_disclosure(result)
    if request.values is not None:
        data["values"] = list(request.values)
    return data
```

and in its `run`:

```python
    try:
        inputs = report_inputs_from_args(args, config, OFFERED_VALUES, identity_key="id")
    except UnofferedValues as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    request = AnalysisRequest(
        scope=inputs.scope,
        values=inputs.values,
        top=getattr(args, "top", 10),
        include_code=bool(getattr(args, "include_code", False)),
        weights=getattr(args, "weights", None),
    )
```

- [ ] **Step 5: Run the tests**

Run: `.venv/bin/python -m pytest tests/commands/ -q`
Expected: PASS, with the Shortfall tests unchanged from Step 1's baseline

- [ ] **Step 6: Commit**

```bash
git add src/elspais/commands/gaps.py src/elspais/commands/analysis_cmd.py
git commit -m "[TOOL-82] Give gaps and analysis the same request shape"
```

---

### Task 5: `checks` and `search` take requests; `fake_args` deleted

**Files:**
- Modify: `src/elspais/commands/health.py:2723` (`_status_flags`), `:2766` (`_resolve_exclude_status`), `:4716-4740` (`compute_checks`), `:4916-4940` (params construction in `run`)
- Modify: `src/elspais/commands/search_cmd.py:18` (`compute_search`) and its `run`

**Interfaces:**
- Produces: `compute_checks(graph, config, request: ChecksRequest)`, `compute_search(graph, config, request: SearchRequest)`, `_status_flags(treat_active: tuple[str, ...]) -> set[str]`, `_resolve_exclude_status(treat_active: tuple[str, ...], config) -> set[str]`.

- [ ] **Step 1: Write the failing test**

Add to `tests/commands/test_request_edges.py`:

```python
# Verifies: REQ-d00258-C
def test_status_flags_reads_a_tuple_not_a_namespace():
    """`--treat-active Draft` promotes Draft to active-like. The helper needs
    the names and nothing else, so an API caller has no reason to build an
    argparse.Namespace to reach it."""
    from elspais.commands.health import _status_flags

    assert _status_flags(("draft", "review")) == {"Draft", "Review"}
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/commands/test_request_edges.py -k status_flags -q`
Expected: FAIL — `AttributeError: 'tuple' object has no attribute 'treat_active'` (raised inside `flag_values`)

- [ ] **Step 3: Rewrite the two helpers**

```python
# Implements: REQ-d00258-C
def _status_flags(treat_active: tuple[str, ...]) -> set[str]:
    """Title-cased set of statuses named via ``--treat-active`` (empty when unset)."""
    return {s.title() for s in treat_active}


def _resolve_exclude_status(
    treat_active: tuple[str, ...],
    config: dict[str, Any] | None = None,
) -> set[str]:
    from elspais.config import get_status_roles

    roles = get_status_roles(config or {})
    return roles.coverage_excluded_statuses() - _status_flags(treat_active)
```

Update all call sites to pass `flag_values(args, "treat_active")` at the edge, or
`request.treat_active` at compute.

- [ ] **Step 4: Delete the `fake_args` block**

In `compute_checks` (`:4733`), delete:

```python
    fake_args = argparse.Namespace()
    treat_str = params.get("treat_active", None)
    fake_args.treat_active = treat_str.split(",") if treat_str else None
```

and the now-unused `import argparse` at `:4722`. Replace uses with
`request.treat_active`. `run_all` comes from `request.run_all`.

- [ ] **Step 5: Change `search_cmd`**

`compute_search` (`search_cmd.py:18`) reads `params` for `q`, `field`, `limit`
and `regex`. Replace with:

```python
def compute_search(graph: Any, config: dict[str, Any], request: SearchRequest) -> dict:
    return {"results": _search(graph, config, request.q, field=request.field,
                               limit=request.limit, regex=request.regex)}
```

and in its `run`, build the request at the edge:

```python
    request = SearchRequest(
        q=getattr(args, "query", "") or "",
        field=getattr(args, "field", "all") or "all",
        limit=int(getattr(args, "limit", 50) or 50),
        regex=bool(getattr(args, "regex", False)),
    )
```

`SearchArgs.query` is a `tyro.conf.Positional[str]` and `field` defaults to
`"all"`, so `SearchRequest` declares `q: str = ""` and `field: str = "all"`.

- [ ] **Step 6: Run the tests**

Run: `.venv/bin/python -m pytest tests/ -q -x`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/elspais/commands/health.py src/elspais/commands/search_cmd.py tests/commands/test_request_edges.py
git commit -m "[TOOL-82] Stop the API impersonating the CLI to reach its own helpers"
```

---

### Task 6: One HTTP translator; the gaps route stops returning 500

**Files:**
- Modify: `src/elspais/server/routes_api.py:707-717` (`api_search`), `:1284-1345` (the five run routes)
- Test: `tests/server/test_routes_api.py`

**Interfaces:**
- Produces: `_request_or_400(build)` in `routes_api.py`.

- [ ] **Step 1: Write the failing test**

```python
# Verifies: REQ-d00282-F
@pytest.mark.parametrize(
    "endpoint",
    ("/api/run/summary", "/api/run/trace", "/api/run/gaps", "/api/run/analysis"),
)
def test_a_value_a_report_does_not_offer_is_a_bad_request_not_a_crash(client, endpoint):
    """Every report that has values to select among refuses an unoffered name
    the same way. `gaps` returned 500 because its route alone carried no guard,
    which is what a guard written once per route costs."""
    response = client.get(endpoint, params={"values": "no_such_value"})
    assert response.status_code == 400
    assert response.json()["error"] == "unoffered_values"
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/server/test_routes_api.py -k does_not_offer -q`
Expected: FAIL for `/api/run/gaps` with a 500 and `UnofferedValues` in the traceback; the other three pass.

- [ ] **Step 3: Add the shared translator**

```python
# Implements: REQ-d00282-F, REQ-o00062-O
def _request_or_400(build: Callable[[], Any]) -> Any | JSONResponse:
    """Build a request from this query, or the one refusal every route gives.

    ONE place, not one per route: a guard each handler writes for itself is a
    guard a handler can be written without, which is how `/api/run/gaps` came
    to answer 500 where its siblings answered 400.
    """
    from elspais.commands._values import UnofferedValues

    try:
        return build()
    except UnofferedValues as exc:
        return JSONResponse({"error": "unoffered_values", "message": str(exc)}, status_code=400)
```

- [ ] **Step 4: Rewrite each route through it**

```python
async def api_run_summary(request: Request) -> JSONResponse:
    """GET /api/run/summary - Coverage summary data."""
    from elspais.commands._edges import report_inputs_from_params
    from elspais.commands._requests import SummaryRequest
    from elspais.commands.summary import IDENTITY_VALUE, OFFERED_VALUES, compute_summary

    state = _st(request)
    params = dict(request.query_params)
    def _build() -> SummaryRequest:
        inputs = report_inputs_from_params(params, OFFERED_VALUES, IDENTITY_VALUE)
        return SummaryRequest(scope=inputs.scope, values=inputs.values)

    built = _request_or_400(_build)
    if isinstance(built, JSONResponse):
        return built
    return JSONResponse(compute_summary(state.graph, state.config, built))
```

Repeat for `trace`, `gaps`, `analysis`; `checks` and `search` build their
requests directly from `params` (no value selection, so no refusal path).

- [ ] **Step 5: Run the tests**

Run: `.venv/bin/python -m pytest tests/server/ -q`
Expected: PASS (all four endpoints 400)

- [ ] **Step 6: Commit**

```bash
git add src/elspais/server/routes_api.py tests/server/test_routes_api.py
git commit -m "[TOOL-82] Refuse an unoffered value identically on every route"
```

---

### Task 7: `_engine.call` carries a request; the dual shapes are deleted

**Files:**
- Modify: `src/elspais/commands/_engine.py:26-60`
- Modify: `src/elspais/commands/_values.py` (delete `resolve_report_values`), `src/elspais/commands/_scope.py` (delete `resolve_scope_for_report`)
- Modify: `src/elspais/commands/report.py:155-190` (`_refuse_unhonourable_values`), `:250` (`_render_section`)

**Interfaces:**
- Produces: `call(endpoint, request, compute_fn, skip_daemon=False, config_path=None) -> dict`.

- [ ] **Step 1: Change `call`'s signature**

```python
def call(
    endpoint: str,
    request: Any,
    compute_fn: Callable[[Any, dict[str, Any], Any], dict],
    skip_daemon: bool = False,
    config_path: str | None = None,
) -> dict:
    """Run an operation via daemon or locally, returning the same dict shape.

    The request is the operation's input on both paths. Only the daemon path
    serializes it, and it does so here -- a caller that had to produce query
    parameters would be a caller deciding how its own inputs travel.
    """
    if not skip_daemon:
        daemon_result = _try_daemon(endpoint, request.to_params())
        ...
    graph, config = _ensure_local_graph(config_path=config_path)
    result = compute_fn(graph, config, request)
    result["graph_source"] = {"type": "local"}
    return result
```

- [ ] **Step 2: Delete `_values.resolve_report_values` and `_scope.resolve_scope_for_report`**

Both are the `args_or_params: Any` dual shapes. Remove them from `__all__`.
Every caller now uses `report_inputs_from_args` / `report_inputs_from_params`.

- [ ] **Step 3: Rework `report.py`'s composed path**

`_refuse_unhonourable_values` (`:155`) currently resolves for the exception and
discards the result — the third instance of the defect. Replace it with a
function that RETURNS the derived inputs per section, and hand those to
`_render_section` instead of `args`:

```python
# Implements: REQ-d00282-F, REQ-d00279-C
def _section_inputs(sections: list[str], args, config) -> dict[str, ReportInputs] | str:
    """Each section's derived inputs, or the refusal to print instead.

    Derived ONCE per section and carried to the renderer: deriving again where
    the section is rendered is how a composed report and the same section asked
    for alone start stating different values.
    """
    from elspais.commands._edges import report_inputs_from_args
    from elspais.commands._values import UnofferedValues, value_silent_refusal

    silent = [s for s in sections if s not in VALUE_SECTIONS]
    if silent:
        refusal = value_silent_refusal(args, config, ", ".join(sorted(set(silent))))
        if refusal is not None:
            return refusal
    out: dict[str, ReportInputs] = {}
    for section in sections:
        if section not in VALUE_SECTIONS:
            continue
        try:
            out[section] = report_inputs_from_args(args, config, _offered_by(section), "")
        except UnofferedValues as exc:
            return f"{section}: {exc}"
    return out
```

- [ ] **Step 4: Run the whole unit tier**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS

- [ ] **Step 5: Run the e2e tier**

Run: `.venv/bin/python -m pytest -m e2e -q`
Expected: PASS (~143s)

- [ ] **Step 6: Commit**

```bash
git add -A src/elspais tests
git commit -m "[TOOL-82] Retire the dual-shape readers; params is a wire format, not an input"
```

---

### Task 8: Documentation and completions

**Files:**
- Modify: `src/elspais/docs/cli/*.md` (any topic describing `--scope`/`--values` interaction)
- Modify: `docs/configuration.md` (`[scopes.<name>] values` behaviour)
- Modify: `AGENT_DESIGN_PRINCIPLES.md` / `CLAUDE.md` — add the derive-boundary rule to the "No Duplicate Library Functions" list

- [ ] **Step 1: Add the rule to CLAUDE.md's authority list**

Insert after the "Severity resolution" bullet:

```markdown
- Report input derivation: only `report_inputs_from_args` / `report_inputs_from_params` in `commands/_edges.py`. A `--scope` name is expanded against config at the edge that was invoked and NOWHERE else — a compute path handed a raw declaration cannot tell a project's words from a reader's, and REQ-d00280-D turns on exactly that difference. `compute_*` functions take a frozen request from `commands/_requests.py` holding final values and resolve nothing; `dict[str, str]` is an HTTP wire format, never an input to a command. Do NOT write a function taking `args_or_params`.
```

- [ ] **Step 2: Update the user-facing docs**

Per CLAUDE.md's workflow rule, dispatch a sub-agent to update `src/elspais/docs/cli/*.md` and `docs/configuration.md` so a declared scope's values are described as *passing over* values a report does not offer, while a written `--values` is refused.

- [ ] **Step 3: Run the full tier**

Run: `.venv/bin/python -m pytest -m "" -q`
Expected: PASS (~190s)

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "[TOOL-82] Record the derive boundary where the next command will look"
```

---

## Appendix: the spec's open question, resolved

The spec left open how a composed report reaches tyro. It is resolvable and
does not block Phase A.

`report.parse_shared_args` (`report.py:63`) registers 17 flags that duplicate
`ScopeOptions` plus `--values`, `--treat-active` and the global flags — a
hand-maintained copy whose own comments admit the risk ("a selection it does not
register is a selection the composed report cannot honour").

`cli.py:302` already scans leading section names off the front of argv. That
scan is not a second parse; it produces the section list, after which the
remainder is parsed once. The fix is therefore a direct substitution:

- add `ReportArgs(ScopeOptions)` carrying `format`, `output`, `quiet`, `verbose`,
  `lenient`, `mode`, `config`, `spec_dir`, `values`, `treat_active`;
- replace `report.run(sections, argv[i:])` with
  `report.run(sections, tyro.cli(ReportArgs, args=argv[i:]))`;
- delete `parse_shared_args` and the `argparse` import in `report.py`.

One parser, one library, one set of defaults. This becomes Task 1 of the Phase B
plan.
