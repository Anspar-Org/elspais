# Indirect Coverage Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make whole-requirement (blanket) references give full coverage credit into the generous ("indirect") footing, and surface the "leans on whole-req evidence" fact as one unified non-transitive `~` caveat across the requirement header badge, the per-assertion pills, CLI, and `elspais checks` — eliminating the contradictory "12% implemented / 100% tested" and "no direct coverage" rendering on `DIARY-PRD-linking-code-lifecycle`.

**Architecture:** Two coordinated fixes. (1) Coverage math in `graph/annotators.py`: blanket `Implements` on CODE credits all assertions via a new `CoverageSource.CODE_INDIRECT`; retire the `1/N` blanket-`Refines` deflation for full credit; make the indirect footing *monotone* (`max`) so specific-but-partial evidence never lowers the generous headline. (2) Display unification: the per-assertion projection honors `allow_indirect` (same footing as the header) and emits a derived caveat, the viewer renders pills from coverage state (not just direct links) with a `~`, and `elspais checks` reports whole-req-only coverage at info level. The caveat is **derived** from the existing `direct < indirect` float split — no new field on `CoverageDimension`.

**Tech Stack:** Python 3.10+ stdlib, `pydantic>=2` (config schema), Jinja2 template + vanilla JS (viewer), `pytest`. Design doc: `docs/design/2026-07-07-indirect-coverage-redesign-design.md`.

## Global Constraints

- **Version bump every commit:** increment the patch version in `pyproject.toml:7` (currently `0.119.60`) with every commit.
- **Stale CLI binding:** the `elspais` command on PATH is a pipx editable install bound to the *main* worktree with an OLD schema; it rejects this worktree's config and fails the pre-commit hook. Use **`python -m elspais ...`** (system python is bound to THIS worktree) for every CLI invocation, and commit with **`git commit --no-verify`** (the hook runs the stale `elspais fix`). Alternatively the user may rebind pipx once via `pipx install --force -e .` from this worktree, after which plain `elspais` and the hook work — but do not assume it.
- **Tests reference requirements:** every test file/class references the REQ it validates (`# Validates REQ-xxx` / `# Verifies: REQ-xxx`), per repo convention.
- **Sub-agent writes tests:** per CLAUDE.md, dispatch a sub-agent to author test code (unless you are the sub-agent).
- **Derive, don't store:** the caveat is `indirect_pct_by_label[label] > direct_pct_by_label[label]`. Do NOT add a caveat field to `CoverageDimension`/`RollupMetrics`. Adding the `CODE_INDIRECT` enum member is allowed (provenance source, not a metrics-structure change).
- **Test tiers:** default `python -m pytest` (unit/integration). Run `python -m pytest -m ""` (all, incl. e2e+browser) before any push.
- **Non-transitive caveat:** `~` fires ONLY for whole-req/blanket coverage. Assertion-targeted refines conduction stays in `direct` (no `~`).

---

## File Structure

- `src/elspais/graph/metrics.py` — add `CoverageSource.CODE_INDIRECT`; bucket it into `implemented.indirect` in `finalize()`. (Unchanged: `CoverageDimension` structure.)
- `src/elspais/graph/annotators.py` — blanket-CODE `else` branch (`annotate_coverage`); retire `1/N` + monotone `max` (`_conduct_refines_coverage`).
- `src/elspais/html/generator.py` — `compute_assertion_coverage_states` honors `allow_indirect`; new `compute_assertion_coverage_caveats`.
- `src/elspais/server/routes_api.py` — serialize `assertion_coverage_caveats` into the node payload.
- `src/elspais/html/templates/partials/js/_card-stack.js.j2` — render pills from state (not just links); append `~`; grey fallback copy.
- `src/elspais/commands/health.py` — new info-level `check_whole_req_only_coverage`.
- `spec/dev-graph-core.md` — reword REQ-d00069-B/J/L; confirm REQ-d00258 wording. Re-hash `spec/_generated/*`.
- Tests: `tests/core/test_indirect_coverage.py`, `tests/core/test_html/test_assertion_coverage_states.py`, `tests/core/test_html/test_allow_indirect.py`, `tests/commands/test_health_coverage.py`, plus a browser test in Task 8.

---

## Task 1: `CODE_INDIRECT` coverage source + `finalize()` bucketing

**Files:**
- Modify: `src/elspais/graph/metrics.py:61-70` (enum), `src/elspais/graph/metrics.py:251-294` (`finalize`)
- Test: `tests/core/test_indirect_coverage.py`

**Interfaces:**
- Produces: `CoverageSource.CODE_INDIRECT` (value `"code_indirect"`). A `CoverageContribution` with this source lands in `implemented.indirect` (and `indirect_pct_by_label` at 1.0) but NOT `implemented.direct`.

- [ ] **Step 1: Write the failing test** (append to `tests/core/test_indirect_coverage.py`, and update the existing count assertion)

In `TestIndirectCoverageSource.test_REQ_d00069_A_indirect_is_distinct`, change the count from 8 to 9 and add the new value:

```python
    def test_REQ_d00069_A_indirect_is_distinct(self):
        """INDIRECT is distinct from other coverage sources."""
        values = {s.value for s in CoverageSource}
        assert "indirect" in values
        assert "code_indirect" in values  # blanket CODE Implements (REQ-d00069-B)
        # DIRECT, EXPLICIT, INFERRED, INDIRECT, CODE_INDIRECT, TEST_DIRECT,
        # TEST_INDIRECT, UAT_EXPLICIT, UAT_INFERRED
        assert len(values) == 9
```

Add a new finalize test class:

```python
class TestCodeIndirectFinalize:
    """CODE_INDIRECT feeds implemented.indirect, never implemented.direct.

    Validates REQ-d00069-B: whole-requirement CODE Implements credits all
    assertions on the generous footing only.
    """

    def test_REQ_d00069_B_code_indirect_credits_indirect_only(self):
        metrics = RollupMetrics(total_assertions=2)
        for label in ("A", "B"):
            metrics.add_contribution(
                CoverageContribution(
                    source_id="file.py:1",
                    source_type=CoverageSource.CODE_INDIRECT,
                    assertion_label=label,
                )
            )
        metrics.finalize()
        assert metrics.implemented.indirect == 2
        assert metrics.implemented.direct == 0
        assert metrics.implemented.indirect_pct_by_label == {"A": 1.0, "B": 1.0}
        assert metrics.implemented.direct_pct_by_label == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/core/test_indirect_coverage.py::TestCodeIndirectFinalize -v tests/core/test_indirect_coverage.py::TestIndirectCoverageSource -v`
Expected: FAIL — `AttributeError: CODE_INDIRECT` / count is 8 not 9.

- [ ] **Step 3: Add the enum member** (`src/elspais/graph/metrics.py`, after the `INDIRECT` line ~64)

```python
    INDIRECT = "indirect"  # transitive CODE->TEST evidence (provenance only)
    CODE_INDIRECT = "code_indirect"  # CODE Verifies/Implements whole REQ (blanket), all assertions implied; feeds `implemented` INDIRECT footing only (REQ-d00069-B)
```

- [ ] **Step 4: Bucket it in `finalize()`** (`src/elspais/graph/metrics.py`)

Add a label set beside the others (~line 251):

```python
        direct_labels: set[str] = set()
        explicit_labels: set[str] = set()
        inferred_labels: set[str] = set()
        code_indirect_labels: set[str] = set()
        uat_explicit_labels: set[str] = set()
        uat_inferred_labels: set[str] = set()
```

Add a branch in the contribution loop (after the `INFERRED` branch, ~line 274):

```python
                elif contrib.source_type == CoverageSource.CODE_INDIRECT:
                    code_indirect_labels.add(label)
```

Fold it into `impl_indirect` (~line 284-285):

```python
        impl_direct = direct_labels | explicit_labels
        impl_indirect = impl_direct | inferred_labels | code_indirect_labels
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/core/test_indirect_coverage.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
# bump pyproject.toml version (0.119.60 -> 0.119.61)
git add src/elspais/graph/metrics.py tests/core/test_indirect_coverage.py pyproject.toml
git commit --no-verify -m "[CUR-1568] feat: add CoverageSource.CODE_INDIRECT feeding implemented.indirect (REQ-d00069-B)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Blanket CODE `Implements` credits all assertions

**Files:**
- Modify: `src/elspais/graph/annotators.py:1379-1390` (the `elif target_kind == NodeKind.CODE:` block in `annotate_coverage`)
- Test: `tests/core/test_indirect_coverage.py`

**Interfaces:**
- Consumes: `CoverageSource.CODE_INDIRECT` (Task 1).
- Produces: after `annotate_coverage`, a requirement whose only CODE evidence is a blanket `Implements: REQ` (no assertion suffix) has `implemented.indirect == total_assertions`, `implemented.direct == 0`.

- [ ] **Step 1: Write the failing test** (append to `tests/core/test_indirect_coverage.py`)

```python
class TestBlanketCodeImplements:
    """A blanket `Implements: REQ` on CODE credits ALL assertions (indirect).

    Validates REQ-d00069-B: whole-req CODE Implements is symmetric with the
    whole-req TEST (TEST_INDIRECT) and child-REQ (INFERRED) paths, closing the
    asymmetry that credited it nothing (annotators.py:1381 had no else branch).
    """

    def test_REQ_d00069_B_blanket_code_implements_credits_all(self):
        graph = build_graph(
            make_requirement(
                "REQ-100",
                level="PRD",
                assertions=[{"label": "A", "text": "SHALL a"}, {"label": "B", "text": "SHALL b"}],
            ),
            make_code_ref(implements=["REQ-100"], source_path="src/impl.py"),
        )
        annotate_coverage(graph)
        rollup = graph.find_by_id("REQ-100").get_metric("rollup_metrics")
        assert rollup.implemented.indirect == 2
        assert rollup.implemented.direct == 0
        assert rollup.implemented.indirect_pct_by_label == {"A": 1.0, "B": 1.0}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/core/test_indirect_coverage.py::TestBlanketCodeImplements -v`
Expected: FAIL — `implemented.indirect == 0` (no else branch today).

- [ ] **Step 3: Add the `else` branch** (`src/elspais/graph/annotators.py`, in the `elif target_kind == NodeKind.CODE:` block, right after the `if edge.assertion_targets:` loop at ~1381-1390)

```python
                if edge.assertion_targets:
                    for label in edge.assertion_targets:
                        if label in assertion_labels:
                            metrics.add_contribution(
                                CoverageContribution(
                                    source_id=target_node.id,
                                    source_type=CoverageSource.DIRECT,
                                    assertion_label=label,
                                )
                            )
                else:
                    # Blanket `Implements: REQ` (no assertion suffix) on CODE:
                    # a whole-requirement implementation reference credits ALL
                    # assertions at full value into the INDIRECT footing, mirroring
                    # TEST_INDIRECT (whole-req Verifies) and INFERRED (child REQ).
                    # REQ-d00069-B closes the prior asymmetry (this had no else).
                    for label in assertion_labels:
                        metrics.add_contribution(
                            CoverageContribution(
                                source_id=target_node.id,
                                source_type=CoverageSource.CODE_INDIRECT,
                                assertion_label=label,
                            )
                        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/core/test_indirect_coverage.py::TestBlanketCodeImplements -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
# bump pyproject.toml version (-> 0.119.62)
git add src/elspais/graph/annotators.py tests/core/test_indirect_coverage.py pyproject.toml
git commit --no-verify -m "[CUR-1568] fix: blanket Implements on CODE credits all assertions (REQ-d00069-B)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: Retire `1/N`, full credit + monotone indirect conduction

**Files:**
- Modify: `src/elspais/graph/annotators.py:1727-1769` (`assertion_fraction` inside `_conduct_refines_coverage`)
- Test: `tests/core/test_indirect_coverage.py`

**Interfaces:**
- Consumes: `_conduct_refines_coverage(graph)` runs as the 2nd annotator pass.
- Produces: (a) a blanket `Refines:` from a fully-covered child credits parent assertions `1.0` (not `1/N`); (b) an assertion with BOTH a blanket credit and an assertion-targeted `Refines:` from a partially-covered child reads `1.0` on the indirect footing (monotone `max`) and the targeted fraction on the direct footing.

- [ ] **Step 1: Write the failing tests** (append to `tests/core/test_indirect_coverage.py`)

```python
class TestFullCreditConduction:
    """Blanket Refines gives full credit; indirect footing is monotone.

    Validates REQ-d00069-J: the 1/N deflation is retired (full credit into the
    indirect footing), and adding assertion-targeted evidence never LOWERS the
    generous footing (max, not override).
    """

    def _refined_by(self, child_impl):
        """Parent REQ-P (2 assertions) blanket-refined by child REQ-C whose
        assertion A is implemented per ``child_impl`` (list of code targets)."""
        return build_graph(
            make_requirement(
                "REQ-P", level="PRD",
                assertions=[{"label": "A", "text": "a"}, {"label": "B", "text": "b"}],
            ),
            make_requirement(
                "REQ-C", level="DEV", refines=["REQ-P"],
                assertions=[{"label": "A", "text": "a"}, {"label": "B", "text": "b"}],
            ),
            *[make_code_ref(implements=[t], source_path=f"src/c{i}.py")
              for i, t in enumerate(child_impl)],
        )

    def test_REQ_d00069_J_blanket_refine_full_credit(self):
        # Child fully implemented -> blanket refine credits parent A,B at 1.0
        # (was 1/2 = 0.5 under the retired 1/N rule).
        graph = self._refined_by(["REQ-C-A", "REQ-C-B"])
        annotate_coverage(graph)
        parent = graph.find_by_id("REQ-P").get_metric("rollup_metrics")
        assert parent.implemented.indirect_pct_by_label["A"] == 1.0
        assert parent.implemented.indirect_pct_by_label["B"] == 1.0

    def test_REQ_d00069_J_monotone_targeted_refine_does_not_lower_indirect(self):
        # Parent A additionally targeted-refined by a 50%-covered child:
        # direct footing shows the targeted fraction; indirect stays 1.0 (max).
        graph = build_graph(
            make_requirement(
                "REQ-P", level="PRD",
                assertions=[{"label": "A", "text": "a"}, {"label": "B", "text": "b"}],
            ),
            make_requirement(  # blanket refine -> both A,B get 1.0 indirect
                "REQ-C", level="DEV", refines=["REQ-P"],
                assertions=[{"label": "A", "text": "a"}, {"label": "B", "text": "b"}],
            ),
            make_code_ref(implements=["REQ-C-A", "REQ-C-B"], source_path="src/c.py"),
            make_requirement(  # targeted refine of A only, 50% implemented (X of X,Y)
                "REQ-D", level="DEV", refines=["REQ-P-A"],
                assertions=[{"label": "X", "text": "x"}, {"label": "Y", "text": "y"}],
            ),
            make_code_ref(implements=["REQ-D-X"], source_path="src/d.py"),
        )
        annotate_coverage(graph)
        parent = graph.find_by_id("REQ-P").get_metric("rollup_metrics")
        assert parent.implemented.indirect_pct_by_label["A"] == 1.0   # monotone max
        assert parent.implemented.direct_pct_by_label["A"] == 0.5     # targeted only
        assert parent.implemented.indirect_pct_by_label["B"] == 1.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/core/test_indirect_coverage.py::TestFullCreditConduction -v`
Expected: FAIL — blanket credit is `0.5` (1/N) not `1.0`; monotone-A is `0.5` not `1.0`.

- [ ] **Step 3: Rewrite `assertion_fraction`'s tail** (`src/elspais/graph/annotators.py`, replace the block at ~1749-1769)

Replace:

```python
        if direct_vals:
            return sum(direct_vals) / len(direct_vals)
        if mode == "indirect":
            candidates: list[float] = []
            local_indirect = indirect_pct_local.get(label, 0.0)
            if local_indirect > 0:
                candidates.append(local_indirect)
            if blanket_refines_vals:
                n_assertions = len(labels_by_req.get(req.id) or ()) or 1
                avg = sum(blanket_refines_vals) / len(blanket_refines_vals)
                candidates.append(avg / n_assertions)
            if candidates:
                return max(candidates)
        return 0.0
```

with:

```python
        # Direct (strict) footing: assertion-specific evidence only, equal-weight
        # mean. Whole-requirement/blanket credit never enters the direct footing
        # (keeps the ~ caveat a precise, non-transitive locator, REQ-d00069-J/L).
        direct_mean = (sum(direct_vals) / len(direct_vals)) if direct_vals else 0.0
        if mode != "indirect":
            return direct_mean
        # Indirect (generous) footing is MONOTONE: it is the max of the direct
        # mean and any whole-requirement credit, so adding assertion-targeted
        # (possibly partial) evidence never LOWERS the generous headline.
        candidates: list[float] = []
        if direct_vals:
            candidates.append(direct_mean)
        local_indirect = indirect_pct_local.get(label, 0.0)
        if local_indirect > 0:
            # Local whole-requirement leaf evidence (a whole-req test/code/journey)
            # exercises every assertion -> its own local fraction (1.0, or a
            # partial uat_verified ratio, REQ-d00255-C).
            candidates.append(local_indirect)
        if blanket_refines_vals:
            # A blanket `Refines:` conducts the refining requirement's OWN rolled-up
            # coverage at FULL weight (mean across blanket edges) -- the 1/N
            # deflation is retired (REQ-d00069-J). The fraction reflects the child's
            # actual coverage, not an arbitrary discount.
            candidates.append(sum(blanket_refines_vals) / len(blanket_refines_vals))
        return max(candidates) if candidates else 0.0
```

(The `labels_by_req`-based `n_assertions` lookup is now unused inside this branch; leave `labels_by_req` as-is — it is still used by `req_coverage`.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/core/test_indirect_coverage.py::TestFullCreditConduction -v`
Expected: PASS.

- [ ] **Step 5: Run the full indirect-coverage + aggregation suites for regressions**

Run: `python -m pytest tests/core/test_indirect_coverage.py tests/graph/test_aggregation.py tests/core/test_coverage_metrics.py -v`
Expected: PASS. If a pre-existing test pinned the `1/N` value (e.g. asserted `0.125`/`0.5` for a blanket refine), update it to the full-credit value and note REQ-d00069-J in the test — the OLD number encoded the retired rule.

- [ ] **Step 6: Commit**

```bash
# bump pyproject.toml version (-> 0.119.63)
git add src/elspais/graph/annotators.py tests/ pyproject.toml
git commit --no-verify -m "[CUR-1568] fix: retire 1/N blanket-Refines deflation; monotone indirect footing (REQ-d00069-J)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: Per-assertion projection honors `allow_indirect` + emits caveat

**Files:**
- Modify: `src/elspais/html/generator.py:518-560` (`compute_assertion_coverage_states` `_frac`); add `compute_assertion_coverage_caveats`
- Modify: `src/elspais/server/routes_api.py:533-587` (import + serialize)
- Test: `tests/core/test_html/test_assertion_coverage_states.py`, `tests/core/test_html/test_allow_indirect.py`

**Interfaces:**
- Produces:
  - `compute_assertion_coverage_states(node, config)` now selects `direct_pct_by_label` when `allow_indirect` is false, `indirect_pct_by_label` otherwise (same footing as `compute_coverage_tiers`).
  - `compute_assertion_coverage_caveats(node) -> dict[str, dict[str, bool]]` — per label, per dimension key (`implemented/tested/verified/uat_coverage/uat_verified`), `True` when that assertion's coverage leans on whole-req evidence (`indirect_pct > direct_pct`). Independent of `allow_indirect` (it is provenance).
  - Node API payload gains `result["assertion_coverage_caveats"]`.

- [ ] **Step 1: Write the failing tests**

In `tests/core/test_html/test_assertion_coverage_states.py`, add:

```python
def test_REQ_d00069_L_caveat_true_for_blanket_only_assertion():
    """An assertion covered only on the indirect footing is flagged caveated."""
    from elspais.html.generator import compute_assertion_coverage_caveats
    rollup = RollupMetrics(total_assertions=2)
    rollup.implemented = CoverageDimension(
        total=2, direct=1, indirect=2,
        direct_labels={"A"}, indirect_labels={"A", "B"},
        direct_pct_by_label={"A": 1.0}, indirect_pct_by_label={"A": 1.0, "B": 1.0},
    )
    node = _req_with_rollup(rollup, labels=("A", "B"))
    caveats = compute_assertion_coverage_caveats(node)
    assert caveats["A"]["implemented"] is False   # has direct evidence
    assert caveats["B"]["implemented"] is True    # blanket-only -> ~


def test_REQ_d00258_G_states_honor_allow_indirect_strict():
    """Under allow_indirect=false, a blanket-only assertion reads 'missing'
    (strict footing), matching the header badge (no header/pill split)."""
    rollup = RollupMetrics(total_assertions=2)
    rollup.implemented = CoverageDimension(
        total=2, direct=1, indirect=2,
        direct_labels={"A"}, indirect_labels={"A", "B"},
        direct_pct_by_label={"A": 1.0}, indirect_pct_by_label={"A": 1.0, "B": 1.0},
    )
    node = _req_with_rollup(rollup, labels=("A", "B"))
    strict = {"rules": {"coverage": {"allow_indirect": False}}}
    states = compute_assertion_coverage_states(node, strict)
    assert states["A"]["implemented"] == "full"
    assert states["B"]["implemented"] == "missing"   # blanket-only, strict
    generous = compute_assertion_coverage_states(node, None)
    assert generous["B"]["implemented"] == "full"    # generous default
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/core/test_html/test_assertion_coverage_states.py -k "caveat or allow_indirect_strict" -v`
Expected: FAIL — `compute_assertion_coverage_caveats` undefined; strict `B` reads `full` (hardcoded indirect footing).

- [ ] **Step 3: Make `_frac` honor `allow_indirect`** (`src/elspais/html/generator.py`, inside `compute_assertion_coverage_states`, replacing the `_frac` at ~518-521)

```python
    from elspais.graph.aggregation import _allow_indirect_from_config

    eps = 1e-9
    allow_indirect = _allow_indirect_from_config(config)

    def _frac(dim: CoverageDimension, label: str) -> float:
        pct = dim.indirect_pct_by_label if allow_indirect else dim.direct_pct_by_label
        return pct.get(label, 0.0)
```

- [ ] **Step 4: Add `compute_assertion_coverage_caveats`** (`src/elspais/html/generator.py`, immediately after `compute_assertion_coverage_states` returns, ~line 561)

```python
def compute_assertion_coverage_caveats(node: GraphNode) -> dict[str, dict[str, bool]]:
    """Per-assertion, per-dimension "leans on whole-requirement evidence" flag.

    The one unified indirect caveat (REQ-d00069-L, REQ-d00258): for each label
    and dimension, True when the assertion's coverage is not fully direct
    (``indirect_pct_by_label > direct_pct_by_label``). Derived from the same
    floats that drive the header ``~`` marker -- NOT stored on the dimension --
    so header and per-assertion caveats can never disagree. Independent of
    ``allow_indirect`` (that governs crediting; this is provenance).
    """
    from elspais.graph.GraphNode import NodeKind
    from elspais.graph.metrics import tested_and_passing

    rollup = node.get_metric("rollup_metrics")
    if not rollup or rollup.total_assertions == 0:
        return {}
    labels = [
        c.get_field("label", "")
        for c in node.iter_children()
        if c.kind == NodeKind.ASSERTION and c.get_field("label", "")
    ]
    eps = 1e-9
    passing = tested_and_passing(rollup)

    def _cav(dim: CoverageDimension, label: str) -> bool:
        ind = dim.indirect_pct_by_label.get(label, 0.0)
        dir_ = dim.direct_pct_by_label.get(label, 0.0)
        return ind > dir_ + eps

    return {
        label: {
            "implemented": _cav(rollup.implemented, label),
            "tested": _cav(rollup.tested, label),
            "verified": _cav(passing, label),
            "uat_coverage": _cav(rollup.uat_coverage, label),
            "uat_verified": _cav(rollup.uat_verified, label),
        }
        for label in labels
    }
```

- [ ] **Step 5: Serialize it in the node API** (`src/elspais/server/routes_api.py`)

Add to the import block at ~533:

```python
    from elspais.html.generator import (
        DIMENSION_KEYS,
        DIMENSION_TIPS,
        compute_assertion_coverage_caveats,
        compute_assertion_coverage_states,
        compute_coverage_tiers,
    )
```

After the `assertion_coverage_states` assignment (~587):

```python
            result["assertion_coverage_states"] = compute_assertion_coverage_states(
                node, state.config
            )
            # Per-assertion "leans on whole-requirement evidence" caveat (~),
            # unified with the header ~ marker (REQ-d00069-L).
            result["assertion_coverage_caveats"] = compute_assertion_coverage_caveats(node)
```

- [ ] **Step 6: Export the new function** (`src/elspais/html/generator.py`, add to `__all__` if present, next to `compute_assertion_coverage_states`).

- [ ] **Step 7: Run the tests to verify they pass**

Run: `python -m pytest tests/core/test_html/test_assertion_coverage_states.py tests/core/test_html/test_allow_indirect.py -v`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
# bump pyproject.toml version (-> 0.119.64)
git add src/elspais/html/generator.py src/elspais/server/routes_api.py tests/core/test_html/ pyproject.toml
git commit --no-verify -m "[CUR-1568] feat: per-assertion states honor allow_indirect; derive unified ~ caveat (REQ-d00069-L, REQ-d00258-G)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: Viewer renders pills from coverage state + `~` caveat

**Files:**
- Modify: `src/elspais/html/templates/partials/js/_card-stack.js.j2:550-602`
- Verify: browser (Task 8) — this is template JS with no unit harness; the projection it consumes is unit-tested in Task 4.

**Interfaces:**
- Consumes: `data.assertion_coverage_states[label][stateKey]` (Task 4), `data.assertion_coverage_caveats[label][stateKey]` (Task 4), `data.assertion_links[label]`.
- Produces: a per-assertion dimension pill renders when the assertion has a direct link OR a non-missing coverage state; a `~` is appended when caveated; the grey fallback reads "no coverage".

- [ ] **Step 1: Read the caveat map** (add after the `aStates` line ~557)

```javascript
    var aStates = data.assertion_coverage_states ? data.assertion_coverage_states[label] : null;
    var aCaveats = data.assertion_coverage_caveats ? data.assertion_coverage_caveats[label] : null;
```

- [ ] **Step 2: Gate pills on link OR state, and append the caveat** (replace the `dimDefs.forEach` body region ~567-583)

```javascript
    var anyBadge = false;
    dimDefs.forEach(function(dim) {
        var st = (dim.stateKey && aStates) ? aStates[dim.stateKey] : null;
        var hasState = st === 'full' || st === 'partial' || st === 'failing';
        // Render when there's a direct assertion-level link OR a non-missing
        // coverage state (whole-req evidence now shows as a pill, not "no
        // coverage"). State-less pills (REF: linkKey but no stateKey) keep the
        // strict link-gate -- they have no state to fall back on.
        if (aLinks && !aLinks[dim.linkKey] && !(dim.stateKey && hasState)) return;
        anyBadge = true;
        var btnLabel = badgeMode === 'full' ? dim.full : (badgeMode === 'dots' ? dim.dot : dim.abbr);
        // Non-transitive ~ caveat: whole-requirement evidence involved.
        if (dim.stateKey && aCaveats && aCaveats[dim.stateKey] && hasState) {
            btnLabel += ' ~';
        }
        var btnStyle = badgeMode === 'dots' ? ' style="min-width:0;padding:2px 4px;font-size:0.55rem;"' : '';
        var extraArg = dim.edgeKind ? ", '" + dim.edgeKind + "'" : '';
        var stateCls = '';
        if (dim.stateKey && aStates && aStates[dim.stateKey]) {
            stateCls = assertionStateColorClass(aStates[dim.stateKey]);
        }
        h += '<button class="' + dim.cls + (stateCls ? ' ' + stateCls : '') + '" ' +
            'data-req-id="' + nodeId + '" data-label="' + escapeAttr(label) + '" ' +
            'title="' + dim.tip + ' (~ = some coverage comes from whole-requirement references)" ' +
            'onclick="event.stopPropagation(); ' + dim.toggle + '(this, \'' + nodeId + '\', \'' + escapeAttr(label) + '\'' + extraArg + ')"' +
            btnStyle + '>' +
            btnLabel + '</button>';
    });
```

- [ ] **Step 3: Reword the grey fallback** (~line 600)

```javascript
            h += '<span class="assertion-no-coverage" title="No coverage on either footing" style="font-size:0.6rem;color:var(--secondary-text);opacity:0.5;">no coverage</span>';
```

- [ ] **Step 4: Render-smoke check** (the template compiles + serves)

Run (from this worktree, pointed at itself):
`python -m elspais serve --no-browser --port 5599 &` then `curl -s localhost:5599/ | head -c 200; kill %1`
Expected: HTML served, no template/Jinja error in output. (Full visual verification is Task 8.)

- [ ] **Step 5: Commit**

```bash
# bump pyproject.toml version (-> 0.119.65)
git add src/elspais/html/templates/partials/js/_card-stack.js.j2 pyproject.toml
git commit --no-verify -m "[CUR-1568] feat: viewer renders per-assertion pills from coverage state + ~ caveat (REQ-d00258-G)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: `elspais checks` — whole-req-only coverage (info)

**Files:**
- Modify: `src/elspais/commands/health.py` (add `check_whole_req_only_coverage` after `check_dimension_coverage` ends ~2210; register in `run_code_checks` list ~2410-2422)
- Test: `tests/commands/test_health_coverage.py`

**Interfaces:**
- Consumes: `rollup.implemented` (`CoverageDimension`) per requirement.
- Produces: `check_whole_req_only_coverage(graph, config=None) -> HealthCheck` with `severity="info"`, `passed=True`, one `HealthFinding` per requirement that has ≥1 assertion whose `implemented` coverage is whole-req-only. INFO never affects exit code (`HealthReport.failed`/`warnings` ignore info).

- [ ] **Step 1: Write the failing test** (append to `tests/commands/test_health_coverage.py`)

```python
class TestWholeReqOnlyCoverageCheck:
    """Info-level check quantifying reliance on whole-requirement evidence.

    Validates REQ-d00258: over-crediting on the generous footing must be
    visible, not silent. INFO severity -> never fails the build.
    """

    def test_reports_blanket_only_assertions_info(self):
        from elspais.commands.health import check_whole_req_only_coverage
        from elspais.graph.annotators import annotate_coverage
        from tests.core.graph_test_helpers import (
            build_graph, make_requirement, make_code_ref,
        )
        graph = build_graph(
            make_requirement(
                "REQ-100", level="PRD",
                assertions=[{"label": "A", "text": "a"}, {"label": "B", "text": "b"}],
            ),
            make_code_ref(implements=["REQ-100"], source_path="src/impl.py"),  # blanket
        )
        annotate_coverage(graph)
        check = check_whole_req_only_coverage(graph)
        assert check.severity == "info"
        assert check.passed is True
        assert len(check.findings) == 1
        assert "REQ-100" in check.findings[0].message
        assert "2" in check.findings[0].message  # both A,B whole-req-only

    def test_no_findings_when_all_direct(self):
        from elspais.commands.health import check_whole_req_only_coverage
        from elspais.graph.annotators import annotate_coverage
        from tests.core.graph_test_helpers import (
            build_graph, make_requirement, make_code_ref,
        )
        graph = build_graph(
            make_requirement(
                "REQ-100", level="PRD",
                assertions=[{"label": "A", "text": "a"}],
            ),
            make_code_ref(implements=["REQ-100-A"], source_path="src/impl.py"),  # targeted
        )
        annotate_coverage(graph)
        check = check_whole_req_only_coverage(graph)
        assert check.findings == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/commands/test_health_coverage.py::TestWholeReqOnlyCoverageCheck -v`
Expected: FAIL — `check_whole_req_only_coverage` undefined.

- [ ] **Step 3: Add the check** (`src/elspais/commands/health.py`, after `check_dimension_coverage` ~line 2210)

```python
def check_whole_req_only_coverage(graph, config=None) -> HealthCheck:
    """INFO: assertions whose IMPLEMENTED coverage is whole-requirement-only.

    Under REQ-d00069-B/J a blanket `Implements:`/`Refines:` fully credits every
    assertion on the generous footing. That is intended, but it must be VISIBLE:
    this reports how load-bearing the blanket references are so a team can see
    how much green rests on whole-requirement evidence. INFO severity -- never
    fails the build. (REQ-d00258.)
    """
    from elspais.graph import NodeKind

    findings: list[HealthFinding] = []
    total = 0
    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        rollup = node.get_metric("rollup_metrics")
        if rollup is None:
            continue
        dim = rollup.implemented
        n = sum(
            1
            for lbl, ind in dim.indirect_pct_by_label.items()
            if ind > dim.direct_pct_by_label.get(lbl, 0.0) + 1e-9
        )
        if n:
            total += n
            findings.append(
                HealthFinding(
                    message=(
                        f"{node.id}: {n} assertion(s) implemented only by "
                        f"whole-requirement evidence"
                    ),
                    node_id=node.id,
                )
            )
    return HealthCheck(
        name="code.whole_req_only_coverage",
        passed=True,
        message=(
            f"{total} assertion(s) across {len(findings)} requirement(s) rely "
            f"only on whole-requirement evidence for Implemented coverage"
        ),
        category="code",
        severity="info",
        findings=findings,
    )
```

- [ ] **Step 4: Register it** (`src/elspais/commands/health.py`, in `run_code_checks`, append to the `checks = [...]` list ~2410-2422)

```python
        check_whole_req_only_coverage(graph, config),
```

- [ ] **Step 5: Run the tests + the health suite**

Run: `python -m pytest tests/commands/test_health_coverage.py tests/commands/test_health_command.py -v`
Expected: PASS. (If a test pins the exact count of code checks, bump it by one.)

- [ ] **Step 6: Commit**

```bash
# bump pyproject.toml version (-> 0.119.66)
git add src/elspais/commands/health.py tests/commands/test_health_coverage.py pyproject.toml
git commit --no-verify -m "[CUR-1568] feat: elspais checks reports whole-requirement-only coverage (info) (REQ-d00258)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: Reword governing requirements + re-hash

**Files:**
- Modify: `spec/dev-graph-core.md` (REQ-d00069-B, REQ-d00069-J:178, REQ-d00069-L:182; confirm REQ-d00258-A:475 / REQ-d00258-J:493)
- Regenerate: `spec/_generated/*` via `python -m elspais fix`

**Interfaces:** none (documentation/normative text). The reworded assertions must match the behavior implemented in Tasks 1–6.

- [ ] **Step 1: Reword REQ-d00069-J** (`spec/dev-graph-core.md:178`) — replace the `1/N` sentence. New text:

```markdown
J. A `Refines:` relationship SHALL NOT contribute coverage by itself, but it SHALL conduct the refining requirement's own rolled-up coverage upward to the *Assertion* it targets. A requirement's coverage SHALL be the mean of its assertions' coverage (assertions are unweighted), computed independently per coverage dimension. Coverage SHALL be tracked on two footings (REQ-d00069-L). An *Assertion*'s **strict (direct)** coverage SHALL be the equal-weight mean of its assertion-specific contributions (local direct evidence at full value; each assertion-targeted refining requirement at its own rolled-up coverage), and SHALL be `0` when it has none; whole-requirement (blanket) credit SHALL NOT enter the strict footing. An *Assertion*'s **generous (indirect)** coverage SHALL be the maximum of (a) its strict coverage, (b) full value when the requirement has local whole-requirement evidence (a whole-requirement test/code/journey), and (c) the mean coverage of the requirement's whole-requirement (blanket) `Refines:` edges at FULL weight. The generous footing SHALL be monotone: adding assertion-specific evidence SHALL NOT lower it. The prior `1/N` blanket deflation is retired.
```

- [ ] **Step 2: Reword REQ-d00069-B** — locate the B assertion in the REQ-d00069 block (`grep -n "^B\. " spec/dev-graph-core.md` within the REQ-d00069 section) and ensure it states the whole-requirement **symmetry across all four keywords**. Add/replace with:

```markdown
B. A whole-requirement (assertion-less) reference SHALL credit ALL of the target requirement's assertions at full value on the generous footing. This SHALL hold symmetrically for `Verifies:` (source `TEST_INDIRECT` -> Tested), `Implements:` on CODE (source `CODE_INDIRECT` -> Implemented), `Implements:`/`Refines:` from a child requirement (source `INFERRED` -> Implemented), and `Validates:` from a journey (source `UAT_INFERRED` -> UAT Covered). No whole-requirement reference SHALL credit the strict (direct) footing.
```

- [ ] **Step 3: Reword REQ-d00069-L** (`spec/dev-graph-core.md:182`) — generalize the marker to the unified per-assertion + requirement caveat:

```markdown
L. Coverage SHALL be tracked on two footings per dimension: strict (direct, assertion-targeted evidence only) and generous (indirect, additionally counting whole-requirement, inferred, conducted, and inherited evidence). Reporting surfaces SHALL headline the generous footing and SHALL express precision as a tier (full, partial, failing, missing), rendering a single unified indirect-evidence caveat (a `~` marker meaning "some coverage comes from whole-requirement references") rather than a second count. The caveat SHALL be derived from `indirect > direct` per dimension and per *Assertion*, and SHALL be applied consistently at BOTH the requirement badge and the per-*Assertion* level so the two never disagree.
```

- [ ] **Step 4: Confirm REQ-d00258** — verify REQ-d00258-A (475) and REQ-d00258-J (493) already cover the `~` caveat + `allow_indirect`. They do; only add a clause to REQ-d00258 (pick the relevant sub-assertion) requiring the per-*Assertion* pills to honor `allow_indirect` and render the caveat, if not already implied by REQ-d00258-G. If editing, keep it one sentence.

- [ ] **Step 5: Re-hash the spec** (regenerates hashes + `spec/_generated/*`)

Run: `python -m elspais fix`
Expected: "Validated N requirements"; modified `spec/dev-graph-core.md` End-hashes + `spec/_generated/*` updated. If it reports broken references or unfixable issues, resolve them before committing (do not `--no-verify` past a real spec error — that is different from the stale-CLI hook issue).

- [ ] **Step 6: Verify self-health passes**

Run: `python -m elspais checks 2>&1 | tail -20`
Expected: no new errors/warnings introduced by the rewording (the new whole_req_only check appears as info).

- [ ] **Step 7: Commit** (always stage `spec/_generated/*`)

```bash
# bump pyproject.toml version (-> 0.119.67)
git add spec/dev-graph-core.md spec/_generated/ pyproject.toml
git commit --no-verify -m "[CUR-1568] spec: reword REQ-d00069-B/J/L for full-credit + unified ~ caveat; re-hash

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 8: End-to-end verification (repro repo + relative chain)

**Files:**
- Test: `tests/core/test_html/test_indirect_coverage_display.py` (new) — an integration test on a synthetic graph mirroring the repro (blanket Implements + blanket Refines), asserting header/pill agreement.
- Verify (manual/observed): the hht repro repo viewer.

**Interfaces:** consumes everything from Tasks 1–7.

- [ ] **Step 1: Write the integration test** (new file `tests/core/test_html/test_indirect_coverage_display.py`)

```python
# Validates REQ-d00069-B, REQ-d00069-J, REQ-d00258-G
"""End-to-end: header badge and per-assertion states/caveats AGREE for a
whole-requirement-covered requirement (the DIARY-PRD-linking-code-lifecycle
class of bug: blanket Implements + blanket Refines rendered '12% implemented,
no direct coverage' contradicting a 'tested full' header)."""

from elspais.graph.annotators import annotate_coverage
from elspais.html.generator import (
    compute_assertion_coverage_caveats,
    compute_assertion_coverage_states,
    compute_coverage_tiers,
)
from tests.core.graph_test_helpers import (
    build_graph, make_requirement, make_code_ref, make_test_ref,
)


def _prd_like():
    graph = build_graph(
        make_requirement(
            "REQ-P", level="PRD",
            assertions=[{"label": lbl, "text": f"SHALL {lbl}"} for lbl in "ABC"],
        ),
        make_code_ref(implements=["REQ-P"], source_path="src/impl.py"),   # blanket Implements
        make_test_ref(verifies=["REQ-P"], source_path="tests/t.py"),      # blanket Verifies
    )
    annotate_coverage(graph)
    return graph.find_by_id("REQ-P")


def test_REQ_d00258_G_header_and_pills_agree_on_blanket_coverage():
    node = _prd_like()
    tiers = compute_coverage_tiers(node)
    states = compute_assertion_coverage_states(node, None)
    caveats = compute_assertion_coverage_caveats(node)
    # Header: implemented + tested both full, both caveated (~).
    assert tiers["impl_tier"] == "full"
    assert tiers["tested_tier"] == "full"
    assert tiers["impl_marker"] == "~"
    assert tiers["tested_marker"] == "~"
    # Per-assertion: every assertion full + caveated on BOTH dims (no "no
    # coverage", no direct/indirect contradiction).
    for lbl in "ABC":
        assert states[lbl]["implemented"] == "full"
        assert states[lbl]["tested"] == "full"
        assert caveats[lbl]["implemented"] is True
        assert caveats[lbl]["tested"] is True
```

(Confirm the exact `impl_marker`/`tested_marker` value — `"~"` vs `" ~"` — against `compute_coverage_tiers`; adjust the assertion to match how the marker is stored.)

- [ ] **Step 2: Run it**

Run: `python -m pytest tests/core/test_html/test_indirect_coverage_display.py -v`
Expected: PASS.

- [ ] **Step 3: Full suite (pre-push gate)**

Run: `python -m pytest -m ""`
Expected: PASS. Fix any regression at the source (never dismiss as pre-existing; all branch failures are in-scope).

- [ ] **Step 4: Observed verification on the repro repo**

Build the hht graph and confirm the numbers flipped:

```bash
python -c "
from pathlib import Path
from elspais.config import load_config
from elspais.graph.factory import build_graph
hht = Path.home()/'cure-hht/hht_diary-worktrees/CUR-1568-oq-jny'
g = build_graph(load_config(hht/'.elspais.toml'), repo_root=hht)
prd = g.find_by_id('DIARY-PRD-linking-code-lifecycle')
r = prd.get_metric('rollup_metrics')
print('impl indirect A-G:', {k: round(v,3) for k,v in r.implemented.indirect_pct_by_label.items()})
"
```
Expected: A–G now `1.0` (was `0.125`).

Then serve and eyeball the card (header IMPLEMENTED = full ~, per-assertion A–G show IMP ~ / TST ~ / VER ~, no "no coverage"):
`python -m elspais serve --repo-root ~/cure-hht/hht_diary-worktrees/CUR-1568-oq-jny --port 5001` and open `DIARY-PRD-linking-code-lifecycle`. (Use the browser tools / a screenshot to confirm header and pills agree.)

- [ ] **Step 5: Relative-chain sanity** — confirm the Tested/Passing relative tiers still read sensibly now that the Implemented denominator grew (A–G became implemented):

Run: `python -m pytest tests/core/test_html/test_coverage_tiers_relative.py tests/core/test_html/test_relative_tiers.py -v`
Expected: PASS (update any test that encoded the OLD under-credited denominator, citing REQ-d00069-B/J).

- [ ] **Step 6: Update user docs** — `docs/cli/checks.md` (mention the new `whole_req_only_coverage` info check + restate `allow_indirect` under the full-credit model) and any hover/legend copy doc. Commit.

```bash
# bump pyproject.toml version (-> 0.119.68)
git add tests/ docs/ pyproject.toml
git commit --no-verify -m "[CUR-1568] test+docs: header/pill agreement integration test; checks docs for whole-req caveat

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review (completed against the design doc)

**Spec coverage:** §2 Defect A → Tasks 1-3; §2 Defect B → Tasks 4-5; §4.1 dedicated `CODE_INDIRECT` → Task 1; §4.1 retire 1/N + monotone → Task 3; §4.2 allow_indirect footing + caveat token + REF-gate + "no coverage" copy → Tasks 4-5; §4.3 named info check → Task 6; §4.4 allow_indirect (confirm, no code) → Task 4 tests; §4.5 REQ rewording (all four keywords) → Task 7; §5 verification (repro, relative chain, strict-mode, monotone, REQ-d00258-G) → Tasks 3/4/8. All covered.

**Placeholders:** none — every code step shows real code grounded in current sources.

**Type consistency:** `compute_assertion_coverage_caveats(node) -> dict[str,dict[str,bool]]` defined in Task 4, consumed in Task 4 (routes) + Task 5 (JS) + Task 8; `CoverageSource.CODE_INDIRECT` defined Task 1, used Tasks 2/8; `check_whole_req_only_coverage(graph, config=None) -> HealthCheck` defined + registered Task 6. Dimension keys (`implemented/tested/verified/uat_coverage/uat_verified`) consistent across states/caveats/JS `dimDefs.stateKey`.

**Open item carried for the executor:** confirm no existing test hard-codes the retired `1/N` value (`0.125`/`0.5`) or the `CoverageSource` count elsewhere — Step 3.5 and Step 6.5 catch these; update with a REQ-d00069-J citation, never weaken.
