# CUR-1557 Part 1 (elspais) — Target Selectivity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `--targets` flag to `elspais checks`/`summary`/`trace` so a per-PR CI run executes only the changed test targets and renders untouched ones as faithfully-carried `(baseline)` coverage — distinct from `0%` and from `—` (not-run/no-data).

**Architecture:** `--targets` names the *fresh* set. On `checks --run-tests` it filters execution; on all three commands it marks provenance. The set threads into `build_graph()`, which tags each RESULT node `carried` and stores the fresh set on the graph for the renderer. The `verified` `CoverageDimension` gains a `carried` flag (orthogonal to its pass/fail `tier`), and the trace renderer appends `(baseline)` for carried coverage and `—` for the rare selective-run no-data case. Empty/absent `--targets` = today's full-run behavior, unchanged.

**Tech Stack:** Python 3.10+ stdlib, `tyro` (CLI dataclasses), `pytest`. No new dependencies.

**Design doc:** `docs/design/2026-07-01-cur-1557-target-selectivity-design.md` (read it first).

## Global Constraints

- **No new dependencies.** Core is `tomlkit` + `pydantic>=2.0` + `tyro>=0.9` + stdlib only.
- **Bump the patch version** in `pyproject.toml` (`version = "0.118.32"` → `.33`, `.34`, … one bump per commit).
- **Every test references a requirement.** Add a `# Verifies: REQ-d00254-<label>` marker comment above each new test function (elspais test-file convention).
- **Use a sub-agent to write tests** (you are not the sub-agent unless told so).
- **Text output is the reference implementation**; markdown/csv/html/json follow it.
- **Run `pytest` (~26s) before every commit**; run `pytest -m ""` before any push.
- **Requirement/assertion edits go through the elspais MCP** (`mutate_add_assertion`, `save_mutations`), then `elspais fix` regenerates `spec/_generated/*` — commit those with the work.
- **Backward compatibility:** with no `--targets`, behavior is byte-for-byte identical to today (`fresh_targets is None` → nothing carried, no `—`).

---

### Task 1: Author the new assertions on REQ-d00254

**Files:**
- Modify (via MCP + `elspais fix`): `spec/dev-graph-core.md` (REQ-d00254 block), `spec/_generated/*`

**Interfaces:**
- Produces: assertion labels `REQ-d00254-H`, `REQ-d00254-I`, `REQ-d00254-J` referenced by later tasks' `# Verifies:` markers.

- [ ] **Step 1: Inspect the current requirement**

Run (MCP): `get_requirement("REQ-d00254")`. Confirm it has assertions A–G and that H/I/J are free.

- [ ] **Step 2: Add the three assertions**

Via MCP `mutate_add_assertion` on `REQ-d00254`, add exactly:

- **H** — "`elspais checks --run-tests` SHALL accept a `--targets` selector naming a subset of `[[scanning.test.targets]]` to execute; an unknown target name SHALL be an error, and an absent selector SHALL execute all targets. The same `--targets` flag on `summary`/`trace` SHALL mark provenance without executing anything."
- **I** — "A target absent from `--targets` (the fresh set) whose results are ingested from disk SHALL be tagged *carried*; its verdict SHALL be honored faithfully (a carried failing result still flags the requirement as failing), and the `verified` dimension SHALL carry a `carried` flag orthogonal to its pass/fail tier so the matrix can render it as `(baseline)`."
- **J** — "In a selective run (a `--targets` set is present), a requirement with test references but zero result records SHALL render as not-run (`—`), distinct from a run-but-uncovered `0%`; in a full run (no `--targets`) zero results SHALL keep the existing rendering."

- [ ] **Step 3: Persist and regenerate**

Run (MCP): `save_mutations`. Then on the CLI: `elspais fix`. Expected: "Validated N requirements", regenerates `spec/_generated/glossary.md` + `term-index.md`.

- [ ] **Step 4: Verify the assertions exist**

Run (MCP): `get_requirement("REQ-d00254")`. Expected: assertions H, I, J present with the text above.

- [ ] **Step 5: Commit**

```bash
# bump pyproject version to 0.118.33 first
git add spec/dev-graph-core.md spec/_generated pyproject.toml
git commit -m "[CUR-1557] Add REQ-d00254-H/I/J for target selectivity + carried state"
```

---

### Task 2: `--targets` execution selector on `checks --run-tests`

**Files:**
- Modify: `src/elspais/commands/args.py:25` (`ChecksArgs`)
- Modify: `src/elspais/commands/test_runner.py:35` (`run_configured_targets`)
- Modify: `src/elspais/commands/health.py:2996-3020` (`run`)
- Test: `tests/test_test_runner.py`

**Interfaces:**
- Produces: `run_configured_targets(config, repo_root, *, fail_fast=False, only: set[str] | None = None)`; `ChecksArgs.targets: list[str] | None`.
- Consumes: `TestTargetConfig.name`, `.command` (from `config.scanning.test.targets`).

- [ ] **Step 1: Write the failing test**

In `tests/test_test_runner.py` (create if absent; mirror existing runner tests):

```python
# Verifies: REQ-d00254-H
def test_only_runs_named_targets(tmp_path, monkeypatch):
    from elspais.commands.test_runner import run_configured_targets
    from elspais.config.schema import ElspaisConfig, TestTargetConfig

    calls: list[str] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        class R:  # minimal CompletedProcess stand-in
            returncode = 0
            stdout = ""
        return R()

    monkeypatch.setattr("elspais.commands.test_runner.subprocess.run", fake_run)

    cfg = ElspaisConfig()
    cfg.scanning.test.targets = [
        TestTargetConfig(name="a", command="echo a", reporter="junit"),
        TestTargetConfig(name="b", command="echo b", reporter="junit"),
    ]
    results, _ = run_configured_targets(cfg, tmp_path, only={"a"})

    assert [r.name for r in results] == ["a"]
    assert calls == ["echo a"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_test_runner.py::test_only_runs_named_targets -v`
Expected: FAIL — `run_configured_targets() got an unexpected keyword argument 'only'`.

- [ ] **Step 3: Add the `only` filter to `run_configured_targets`**

In `src/elspais/commands/test_runner.py`, change the signature and add a skip at the top of the loop:

```python
def run_configured_targets(
    config: ElspaisConfig,
    repo_root: Path,
    *,
    fail_fast: bool = False,
    only: set[str] | None = None,
) -> tuple[list[RunnerResult], dict[str, str]]:
```

```python
    for target in config.scanning.test.targets:
        if not target.command:
            continue
        if only is not None and target.name not in only:
            continue
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_test_runner.py::test_only_runs_named_targets -v`
Expected: PASS.

- [ ] **Step 5: Add the CLI arg + validation test**

Add to `ChecksArgs` in `src/elspais/commands/args.py` (after the `fail_fast` field, line ~63):

```python
    targets: list[str] | None = None
    """Run/mark only these [[scanning.test.targets]] by name (space-separated). Default: all. With --run-tests, executes only this subset; on summary/trace, marks the rest as carried baselines."""
```

Add to `src/elspais/commands/health.py` `run()` — replace the guard block at lines 3011-3020 with:

```python
        selected = getattr(args, "targets", None)
        only = {t for t in selected} if selected else None
        target_names = {t.name for t in cfg.scanning.test.targets}
        if only is not None:
            unknown = sorted(only - target_names)
            if unknown:
                print(
                    f"error: unknown --targets: {', '.join(unknown)}. "
                    f"Configured targets: {', '.join(sorted(target_names))}.",
                    file=sys.stderr,
                )
                return 2
        commandful = [
            t for t in cfg.scanning.test.targets
            if t.command and (only is None or t.name in only)
        ]
        if not commandful:
            print(
                "error: --run-tests requires at least one "
                "[[scanning.test.targets]] entry with a command field "
                "(within --targets when given). "
                "See docs/cli/test-targets.md for configuration examples.",
                file=sys.stderr,
            )
            return 2
        repo_root = find_git_root() or Path.cwd()
        results, captured_map = run_configured_targets(
            cfg, repo_root, fail_fast=fail_fast, only=only
        )
```

- [ ] **Step 6: Write the unknown-name test**

In `tests/test_health_command.py` (or the module holding `checks` tests):

```python
# Verifies: REQ-d00254-H
def test_unknown_target_name_errors(capsys, monkeypatch, tmp_path):
    import argparse
    from elspais.commands import health

    args = argparse.Namespace(run_tests=True, targets=["nope"], config=None)
    monkeypatch.chdir(tmp_path)
    # minimal config with one real target named "a"
    monkeypatch.setattr(health, "_validate_config", lambda d: _cfg_with_target("a"))
    monkeypatch.setattr(health, "get_config", lambda *a, **k: {})
    rc = health.run(args)
    assert rc == 2
    assert "unknown --targets: nope" in capsys.readouterr().err
```

Add a small `_cfg_with_target` helper (or inline an `ElspaisConfig` with one `TestTargetConfig(name="a", command="echo", reporter="junit")`). Run it, confirm FAIL then PASS after Step 5 code is in.

- [ ] **Step 7: Run the full checks test module + commit**

Run: `pytest tests/test_test_runner.py tests/test_health_command.py -v`
Expected: PASS.

```bash
# bump pyproject to 0.118.34
git add src/elspais/commands/args.py src/elspais/commands/test_runner.py src/elspais/commands/health.py tests/test_test_runner.py tests/test_health_command.py pyproject.toml
git commit -m "[CUR-1557] --targets selector: run only named test targets (REQ-d00254-H)"
```

---

### Task 3: Thread the fresh set into the build and tag RESULT.carried

**Files:**
- Modify: `src/elspais/commands/args.py:199` (`TraceArgs`), `:329` (`SummaryArgs`)
- Modify: `src/elspais/commands/health.py:3022` (`run`), `:3084-3119` (`_run_local_checks`)
- Modify: `src/elspais/graph/factory.py:65` (`_ingest_target_results`), `:478` (`build_graph`), `:720-763` (ingestion loop)
- Modify: `src/elspais/commands/trace.py:787,822,860` (build_graph calls), `src/elspais/commands/summary.py:55` (`run`)
- Test: `tests/graph/test_factory_targets.py`

**Interfaces:**
- Produces: `build_graph(..., fresh_targets: set[str] | None = None)`; each RESULT node carries fields `carried: bool` and `target: str`; `graph.render_fresh_targets: set[str] | None`.
- Consumes: `ChecksArgs.targets` / `TraceArgs.targets` / `SummaryArgs.targets`.

- [ ] **Step 1: Write the failing test**

In `tests/graph/test_factory_targets.py`:

```python
# Verifies: REQ-d00254-I
def test_result_nodes_tagged_carried(tmp_path):
    from elspais.graph.factory import build_graph
    # Build a tiny project on disk with two targets 'a' and 'b', each with a
    # committed junit results file, using the shared on-disk fixture helper.
    project = _make_two_target_project(tmp_path)  # see fixtures below
    graph = build_graph(config_path=project / ".elspais.toml", fresh_targets={"a"})

    carried_by_target = {
        r.get_field("target"): r.get_field("carried")
        for r in graph.primary.iter_by_kind(__import__("elspais.graph.GraphNode", fromlist=["NodeKind"]).NodeKind.RESULT)
    }
    assert carried_by_target["a"] is False   # in fresh set
    assert carried_by_target["b"] is True    # complement -> carried
    assert graph.render_fresh_targets == {"a"}
```

(Use the project's existing on-disk fixture utilities to author `_make_two_target_project`; two `[[scanning.test.targets]]` with `reporter="junit"`, `results="TEST-*.xml"`, and a passing JUnit file each.)

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/graph/test_factory_targets.py::test_result_nodes_tagged_carried -v`
Expected: FAIL — `build_graph() got an unexpected keyword argument 'fresh_targets'`.

- [ ] **Step 3: Add `carried`/`target` to `_ingest_target_results`**

In `src/elspais/graph/factory.py`, change the signature and the `parsed_data` dict:

```python
def _ingest_target_results(
    builder, target, results_text: str, repo_root: Path, source_path: str = "",
    *, carried: bool = False,
) -> int:
```

```python
        parsed_data = {
            "id": rec["id"],
            "status": rec.get("status"),
            # ... existing fields unchanged ...
            "match": target.match,
            "carried": carried,
            "target": target.name,
            "line": rec.get("line"),
            "root_line": rec.get("root_line"),
            "root_file": root_file,
        }
```

- [ ] **Step 4: Add `fresh_targets` to `build_graph` and the ingestion loop**

In `src/elspais/graph/factory.py`, add the param to `build_graph` (line 478 block):

```python
    captured_results: dict[str, str] | None = None,
    fresh_targets: set[str] | None = None,
) -> FederatedGraph:
```

In the ingestion loop (lines 720-763), compute `carried` once per target and pass it to both ingest calls:

```python
            for target in typed_config.scanning.test.targets:
                if not target.reporter:
                    continue
                carried = fresh_targets is not None and target.name not in fresh_targets
                # ... existing cwd-escape guard unchanged ...
                if target.name in _captured:
                    _ingest_target_results(
                        builder, target, _captured[target.name], repo_root, "", carried=carried
                    )
                elif target.results:
                    matched = glob(str(cwd_path / target.results), recursive=True)
                    if matched:
                        for f in matched:
                            if Path(f).is_file():
                                _get_or_create_file_node(Path(f), FileType.RESULT)
                                _ingest_target_results(
                                    builder, target,
                                    Path(f).read_text(encoding="utf-8", errors="replace"),
                                    repo_root, str(Path(f)), carried=carried,
                                )
                    # ... existing else/debug branches unchanged ...
```

After `graph = builder.build()` (line 765), stash the fresh set for the renderer:

```python
    graph = builder.build()
    graph.render_fresh_targets = fresh_targets
```

(If `build_graph` returns via federation wrapping, set the attribute on the returned `FederatedGraph` just before `return`.)

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/graph/test_factory_targets.py::test_result_nodes_tagged_carried -v`
Expected: PASS.

- [ ] **Step 6: Thread the arg from the commands into `build_graph`**

`src/elspais/commands/health.py` `run()` — after `args._captured_results = captured_map` (line 3022) add:

```python
        args._fresh_targets = only
```

`_run_local_checks` (line 3084) — read it and pass it:

```python
    captured = getattr(args, "_captured_results", None)
    fresh_targets = getattr(args, "_fresh_targets", None)
```
```python
        graph = build_graph(
            spec_dirs=[spec_dir] if spec_dir else None,
            config_path=config_path,
            captured_results=captured,
            fresh_targets=fresh_targets,
        )
```

Add the same field to `TraceArgs` (args.py:199) and `SummaryArgs` (args.py:329):

```python
    targets: list[str] | None = None
    """Mark only these [[scanning.test.targets]] as freshly-run; render the rest as carried baselines."""
```

In `src/elspais/commands/trace.py`, at each `build_graph(` call (lines 787, 822, 860) add:

```python
            fresh_targets=({t for t in args.targets} if getattr(args, "targets", None) else None),
```

In `src/elspais/commands/summary.py` `run()`, where it builds the graph (it delegates to trace's `run_graph`/`build_graph` — pass `args.targets` through the same way).

- [ ] **Step 7: Run test to verify the render pathway carries the flag**

In `tests/test_trace_command.py`:

```python
# Verifies: REQ-d00254-I
def test_trace_targets_marks_fresh_set(two_target_project):
    import argparse
    from elspais.commands import trace
    args = argparse.Namespace(targets=["a"], format="json", config=str(two_target_project / ".elspais.toml"), spec_dir=None)
    # run_graph builds the graph; assert graph.render_fresh_targets == {"a"} via a spy,
    # or assert the rendered JSON marks b's verified as baseline (see Task 5).
```

Run: `pytest tests/graph/test_factory_targets.py tests/test_trace_command.py -v`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
# bump pyproject to 0.118.35
git add src/elspais/commands/args.py src/elspais/commands/health.py src/elspais/graph/factory.py src/elspais/commands/trace.py src/elspais/commands/summary.py tests/graph/test_factory_targets.py tests/test_trace_command.py pyproject.toml
git commit -m "[CUR-1557] Tag RESULT nodes carried from the --targets fresh set (REQ-d00254-I)"
```

---

### Task 4: Propagate `carried` to the `verified` CoverageDimension

**Files:**
- Modify: `src/elspais/graph/metrics.py:103-110` (`CoverageDimension` fields), `populate_test_dimensions`
- Modify: `src/elspais/graph/annotators.py:1320-1424`
- Test: `tests/graph/test_carried_dimension.py`

**Interfaces:**
- Produces: `CoverageDimension.carried: bool`; `RollupMetrics.populate_test_dimensions(..., verified_carried: bool = False)`.
- Consumes: RESULT node field `carried` (from Task 3).

- [ ] **Step 1: Write the failing test**

```python
# Verifies: REQ-d00254-I
def test_verified_dimension_carried_flag(two_target_project):
    from elspais.graph.factory import build_graph
    graph = build_graph(config_path=two_target_project / ".elspais.toml", fresh_targets={"a"})
    # REQ covered only by target 'b' (carried) -> verified.carried True
    req_b = graph.primary.find_by_id("REQ-...b...")
    assert req_b.get_metric("rollup_metrics").verified.carried is True
    # REQ covered only by target 'a' (fresh) -> verified.carried False
    req_a = graph.primary.find_by_id("REQ-...a...")
    assert req_a.get_metric("rollup_metrics").verified.carried is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/graph/test_carried_dimension.py -v`
Expected: FAIL — `AttributeError: 'CoverageDimension' object has no attribute 'carried'`.

- [ ] **Step 3: Add the field + populate kwarg**

In `src/elspais/graph/metrics.py`, add to `CoverageDimension` (after `indirect_pct_by_label`, line ~110):

```python
    carried: bool = False
```

In `populate_test_dimensions`, add a keyword and set it on the `verified` dimension only:

```python
    def populate_test_dimensions(
        self,
        *,
        tested_direct_labels, tested_indirect_labels,
        verified_direct_labels, verified_indirect_labels,
        verified_failures,
        verified_carried: bool = False,
        uat_verified_direct_labels, uat_verified_indirect_labels,
        uat_verified_failures,
    ):
        # ... existing body ...
        self.verified.carried = verified_carried
```

(Match the existing signature exactly; only add the `verified_carried` keyword and the one assignment.)

- [ ] **Step 4: Compute `verified_carried` in the annotator**

In `src/elspais/graph/annotators.py`, inside the automated TEST loop (around lines 1321-1383), track freshness alongside the existing `has_failures`. Initialize before the loop:

```python
        verified_saw_signal = False
        verified_all_carried = True
```

At each point a RESULT contributes a verified signal (the `status in ("passed"...)` credit branch *and* the `status in ("failed"...)` branch, both the inline path ~1341-1350 and the `source_file_index` path ~1358-1369), record:

```python
                    verified_saw_signal = True
                    if not (result.get_field("carried") or False):
                        verified_all_carried = False
```

For the `source_file_index` file-granular path (which reads statuses, not RESULT nodes), look up carried from the same index — extend `source_file_index` construction to also record whether each contributing RESULT was carried, and set `verified_all_carried = False` if any contributing status came from a fresh RESULT. (If that index does not currently retain node identity, add a parallel `source_file_carried: dict[str, bool]` mapping `rel -> all(result.carried)` built in the same pass that builds `source_file_index`.)

Then pass it into the finalize call (line 1415):

```python
        metrics.populate_test_dimensions(
            tested_direct_labels=tested_labels,
            tested_indirect_labels=tested_indirect_labels,
            verified_direct_labels=validated_labels,
            verified_indirect_labels=validated_indirect_labels,
            verified_failures=has_failures,
            verified_carried=(verified_saw_signal and verified_all_carried),
            uat_verified_direct_labels=uat_validated_direct_labels,
            uat_verified_indirect_labels=uat_validated_indirect_labels,
            uat_verified_failures=uat_has_failures,
        )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/graph/test_carried_dimension.py -v`
Expected: PASS.

- [ ] **Step 6: Run the metrics/annotator suites + commit**

Run: `pytest tests/graph -v`
Expected: PASS (no regressions).

```bash
# bump pyproject to 0.118.36
git add src/elspais/graph/metrics.py src/elspais/graph/annotators.py tests/graph/test_carried_dimension.py pyproject.toml
git commit -m "[CUR-1557] verified.carried flag propagated from carried results (REQ-d00254-I)"
```

---

### Task 5: Renderer — `(baseline)` and `—` (no-data) + legend

**Files:**
- Modify: `src/elspais/commands/trace.py:255-307` (`_get_node_data`), `format_markdown` legend (`:389`)
- Test: `tests/test_trace_command.py`

**Interfaces:**
- Consumes: `rollup.verified.carried` (Task 4), `graph.render_fresh_targets` (Task 3), `test_refs` (already computed in `_get_node_data`).

- [ ] **Step 1: Write the failing tests**

```python
# Verifies: REQ-d00254-I
def test_markdown_marks_carried_baseline(two_target_project):
    out = _render_trace_markdown(two_target_project, targets=["a"])
    # target 'b' requirement's verified cell carries the baseline marker
    assert "(baseline)" in _verified_cell(out, "REQ-...b...")
    # target 'a' requirement's verified cell does NOT
    assert "(baseline)" not in _verified_cell(out, "REQ-...a...")

# Verifies: REQ-d00254-J
def test_markdown_no_data_dash_in_selective_run(no_result_target_project):
    out = _render_trace_markdown(no_result_target_project, targets=["a"])
    # a requirement whose only target 'b' was skipped with no seeded results -> '—'
    assert _verified_cell(out, "REQ-...b...").strip() == "—"

# Verifies: REQ-d00254-J
def test_full_run_keeps_existing_rendering(no_result_target_project):
    out = _render_trace_markdown(no_result_target_project, targets=None)
    assert "—" not in _verified_cell(out, "REQ-...b...")  # full run: today's behavior
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_trace_command.py -k "carried or no_data or full_run" -v`
Expected: FAIL (no `(baseline)` / `—` emitted yet).

- [ ] **Step 3: Render carried + no-data in `_get_node_data`**

In `src/elspais/commands/trace.py` `_get_node_data`, after the `_DIMS` loop populates `data[key]` (around line 307), special-case the `verified` column. Add near the top of the function:

```python
    fresh_targets = getattr(graph, "render_fresh_targets", None)
    selective = fresh_targets is not None
```

After the loop that sets `data["verified"]` via `_fmt_count`, override it:

```python
    if rollup:
        vdim = rollup.verified
        eps = 1e-9
        no_verified = vdim.direct <= eps and vdim.indirect <= eps and not vdim.has_failures
        if selective and vdim.total > 0 and no_verified and test_refs:
            data["verified"] = "—"  # em dash: not run this PR, no baseline
        elif vdim.carried and vdim.total > 0:
            data["verified"] = f"{data['verified']} (baseline)"
```

(Use `"—"` — an em dash — per the ASCII-diagram rule this is data, not line-art; the codebase already emits non-ASCII glyphs in matrices. If the team prefers ASCII, use `"--"`.)

- [ ] **Step 4: Add the legend line**

In `format_markdown` (`src/elspais/commands/trace.py:389`), append to the legend/footnote block:

```python
    lines.append("")
    lines.append("> Legend: `(baseline)` = carried from a prior run (not re-run this PR, verdict still honored); `—` = target not run and no baseline (skipped, not a regression).")
```

(Place it alongside the existing legend text; match the surrounding list/blockquote style.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_trace_command.py -k "carried or no_data or full_run" -v`
Expected: PASS.

- [ ] **Step 6: Full trace suite + commit**

Run: `pytest tests/test_trace_command.py tests/test_summary_command.py -v`
Expected: PASS.

```bash
# bump pyproject to 0.118.37
git add src/elspais/commands/trace.py tests/test_trace_command.py pyproject.toml
git commit -m "[CUR-1557] Render carried (baseline) + no-data em-dash in trace matrix (REQ-d00254-I/J)"
```

---

### Task 6: Documentation, CLI help, and config surface

**Files:**
- Modify: `docs/cli/test-targets.md`, `docs/cli/checks.md` (+ `trace.md`/`summary.md` if present)
- Modify: `docs/configuration.md`
- Modify: CLI epilog/help text for `checks`/`trace`/`summary` (search `args.py` docstrings — already added in Tasks 2-3; verify examples)
- Modify: shell completion if the repo ships it (`grep -rl "run-tests" completions/ 2>/dev/null`)

**Interfaces:** none (docs only).

- [ ] **Step 1: Document `--targets` in `docs/cli/test-targets.md`**

Add a "Per-PR selectivity" section explaining: `--targets` = the fresh set; on `checks --run-tests` it executes only that subset; on `summary`/`trace` it marks provenance; the complement renders `(baseline)` (carried, verdict honored) or `—` (no baseline); absent `--targets` = full run. Include a worked example:

```bash
# Per-PR: run only changed targets, render the rest as carried
elspais checks --run-tests --targets clinical_diary portal_ui_evs
elspais summary trace --targets clinical_diary portal_ui_evs --format markdown

# Full regression (qa->uat promotion): omit --targets
elspais checks --run-tests
```

- [ ] **Step 2: Cross-reference from `checks.md` and `configuration.md`**

Add a one-line pointer in `docs/cli/checks.md` under `--run-tests`, and a note in `docs/configuration.md` near the `[[scanning.test.targets]]` docs that per-PR selectivity is driven by `--targets` (not config).

- [ ] **Step 3: Verify docs load + no broken CLI examples**

Run: `elspais docs test-targets` (confirm the new section renders). Run: `elspais checks --help` and `elspais summary trace --help` (confirm `--targets` appears with the help text from Tasks 2-3).

- [ ] **Step 4: Commit**

```bash
# bump pyproject to 0.118.38
git add docs/cli/test-targets.md docs/cli/checks.md docs/configuration.md pyproject.toml
git commit -m "[CUR-1557] Document --targets per-PR selectivity + carried/no-data states"
```

---

### Final: full-suite gate before handing off to Part 2

- [ ] **Run the complete suite** (unit + e2e + browser): `pytest -m ""`
  Expected: all pass (~182s). Fix any failure at the source — no "pre-existing" excuses.
- [ ] **Manual smoke** on this repo (self-validation): `elspais checks --run-tests --targets <one-real-target>` then `elspais summary trace --targets <same> --format markdown` and eyeball the `(baseline)` markers on the untouched requirements.

---

## Self-Review (author checklist — completed)

**Spec coverage:**
- Design 1a (`--targets` execution + provenance) → Task 2 (execution) + Task 3 (provenance threading). ✓
- Design 1b (carried tag on RESULT + verified dim) → Task 3 (RESULT.carried) + Task 4 (dimension). ✓
- Design 1b three render outcomes (fresh/carried/no-data) → Task 5. ✓
- Design 1c (stdout-channel carried-from-file) → covered structurally: the ingestion loop already ingests a non-run target's `results` glob (Task 3 Step 4 keeps that branch); a `flutter-machine` target must set `results` in config for carry-forward. **Documented in Task 6 Step 1.** (No separate code task — the existing `elif target.results` branch is the file path, and Task 3 tags it carried.)
- Design 1d (renderer + legend, text is reference) → Task 5. ✓
- Design 1e (tests + spec) → Task 1 (spec) + per-task TDD. ✓

**Placeholder scan:** No TBD/TODO. Test bodies reference fixture helpers (`_make_two_target_project`, `_verified_cell`) that the implementer wires to existing on-disk fixture utilities — these are named, concrete stubs, not vague "add a test" directives.

**Type consistency:** `fresh_targets: set[str] | None` used identically in `build_graph`, `_run_local_checks`, and the trace/summary calls. `only: set[str] | None` in `run_configured_targets`. RESULT fields `carried`/`target` set in Task 3, read in Tasks 4-5. `CoverageDimension.carried` defined in Task 4, read in Task 5. `graph.render_fresh_targets` set in Task 3, read in Task 5. ✓

## Out of scope (this plan)

- Part 2 (hht_diary CI: canonical-image carry-forward, `--targets` wiring, GHCR persistence) — its own spec→plan cycle in the sibling worktree.
- Carrying the `lcov_tested` dimension's baseline provenance (only `verified` carries a `carried` flag in Part 1).
- A precise requirement→target map for no-data (Task 5 uses the "selective + has-tests + zero-results" heuristic; documented limitation).
