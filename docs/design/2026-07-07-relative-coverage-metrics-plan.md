# Relative Coverage Metrics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make coverage badges intuitive by measuring Tested/Passing against a relative (chain) denominator, unifying the state vocabulary to `{full, partial, failing, missing}`, surfacing direct/indirect as a caveat, and replacing the implicit "active-role" coverage grouping with an explicit per-status `expects_implementation` flag.

**Architecture:** Projection/display layer only. `RollupMetrics` and the `direct`/`indirect` metrics + REFINES conduction are unchanged. Relative tiers are computed where both the numerator dimension and its denominator label-set are available (`html/generator.py`, `graph/aggregation.py`). The unified vocabulary and per-relationship labels are constants/config; `expects_implementation` and `allow_indirect` are new config resolved through single helpers.

**Tech Stack:** Python 3.10+ stdlib, pydantic v2 (`config/schema.py`), pytest. Viewer templates are Jinja2 + vanilla JS.

## Global Constraints

- Do NOT change the structure/encapsulation of `Graph`, `GraphTrace`, `GraphBuilder`, or `RollupMetrics`. No new `CoverageDimension` fields.
- Do NOT touch the `direct`/`indirect` metric computation or REFINES conduction.
- Coverage aggregation lives ONLY in `graph/aggregation.py`; tier/standing projection ONLY in `html/generator.py`. Do not recompute rollups elsewhere.
- Every config flag resolved through a single shared helper; no surface reads the raw config for it.
- TDD: failing test first. Tests reference a REQ. Use a sub-agent to write tests. No tautology tests.
- Bump patch version in `pyproject.toml` every commit. Commit prefix `[CUR-1568]`. Commit `spec/_generated/*` when spec text changes.
- Unit suite (`pytest`, ~26s) green before every commit; pre-commit runs lint + `elspais fix` + unit suite; pre-push adds e2e self-health (no broken refs / no new errors).
- Vocabulary contract (REQ-d00258-B): status words are exactly Implemented / Tested / Passing / UAT Covered / UAT Passed.

**Design doc:** `docs/design/2026-07-07-relative-coverage-metrics-design.md` (canonical; read §-references below).

---

## Phase 1 — Unified state vocabulary + per-relationship status words

Rename the three overlapping vocabularies to one: `{full, partial, failing, missing}`. Pure rename/relabel; NO denominator change yet (that is Phase 2). This isolates the large test-churn of the rename from the behavioral change.

### Task 1.1: Collapse `CoverageDimension.tier` to the unified vocabulary

**Files:**
- Modify: `src/elspais/graph/metrics.py:157-174` (`tier` property)
- Test: `tests/core/test_coverage_metrics.py`

**Interfaces:**
- Produces: `CoverageDimension.tier` returns one of `"failing" | "full" | "partial" | "missing"` (was `full-direct`/`full-indirect`/`none`). The direct/indirect distinction is NO LONGER in the tier — it moves to the `~` marker/hover (Phase 4).

- [ ] **Step 1: Write failing tests** (sub-agent). Cover, tagging REQ-d00258 (unified vocabulary): a dimension with all assertions direct → `tier == "full"` (was `full-direct`); all covered incl. indirect → `tier == "full"` (was `full-indirect`); some covered → `"partial"`; none covered → `"missing"` (was `"none"`); `has_failures` → `"failing"`.

- [ ] **Step 2: Run, verify fail.** `pytest tests/core/test_coverage_metrics.py -k tier -v` → FAIL (asserts `full`, code returns `full-direct`).

- [ ] **Step 3: Implement.** Replace the property body:

```python
    @property
    def tier(self) -> str:
        """Classify into a unified state key: 'failing' | 'full' | 'partial' |
        'missing'. The direct/indirect distinction is surfaced separately as a
        caveat (~ marker + hover), not as a tier (design §2, §4). Float sums are
        compared with a small epsilon so a fully-covered requirement reads full.
        """
        eps = 1e-9
        if self.has_failures:
            return "failing"
        if self.total > 0 and self.indirect >= self.total - eps:
            return "full"
        if self.direct > eps or self.indirect > eps:
            return "partial"
        return "missing"
```

Update the docstring above the property accordingly.

- [ ] **Step 4: Run, verify pass.** `pytest tests/core/test_coverage_metrics.py -k tier -v` → PASS.

- [ ] **Step 5: Sweep dependent tests.** `grep -rn 'full-direct\|full-indirect\|"none"\|full_direct\|full_indirect' tests/ src/elspais | grep -i tier` and update every assertion expecting the old tier strings to the new vocabulary. Run `pytest tests/core/ -k "tier or coverage or bucket" -v`.

- [ ] **Step 6: Commit.** `[CUR-1568] refactor: CoverageDimension.tier uses unified {full,partial,failing,missing} vocabulary`

### Task 1.2: Align `CoverageSeverityConfig`, `TIER_TO_BUCKET`, tier descriptions

**Files:**
- Modify: `src/elspais/config/schema.py:186-212` (`CoverageSeverityConfig`, `CoverageConfig`, `_uat_severity`)
- Modify: `src/elspais/graph/aggregation.py:23-30` (`TIER_TO_BUCKET`)
- Modify: `src/elspais/html/generator.py:150-156` (`_TIER_DESCRIPTIONS`), `:162-166` (`_tier_to_severity`)
- Test: `tests/core/test_html/`, `tests/core/test_coverage_metrics.py`

**Interfaces:**
- Produces: `CoverageSeverityConfig` fields become `full` (default `"ok"`), `partial` (`"warning"`), `failing` (`"error"`), `missing` (`"error"`). The `full_direct`/`full_indirect`/`none` fields are removed. `_uat_severity()` returns `CoverageSeverityConfig(missing="info")`. `verified` default keeps its softening as `CoverageSeverityConfig(missing="warning")`. `TIER_TO_BUCKET` is identity over `{full, partial, failing, missing}`.

- [ ] **Step 1: Write failing tests** (sub-agent). Tag REQ-d00258: `CoverageSeverityConfig().missing == "error"`, `.full == "ok"`; `_uat_severity().missing == "info"`; `_tier_to_severity("missing", CoverageSeverityConfig())` → `"error"`; `TIER_TO_BUCKET["missing"] == "missing"` and `["full"] == "full"`.

- [ ] **Step 2: Run, verify fail.** `pytest tests/core/test_coverage_metrics.py tests/core/test_html -k "severity or bucket or tier" -v` → FAIL.

- [ ] **Step 3: Implement.** In `schema.py`:

```python
class CoverageSeverityConfig(_StrictModel):
    """Severity mapping for a single coverage dimension's tier states.

    Each tier maps to a severity: 'ok', 'info', 'warning', or 'error'.
    """

    full: str = "ok"
    partial: str = "warning"
    failing: str = "error"
    missing: str = "error"


def _uat_severity() -> CoverageSeverityConfig:
    return CoverageSeverityConfig(missing="info")
```

In `CoverageConfig`, keep `verified` softened but on the new key:
```python
    verified: CoverageSeverityConfig = Field(
        default_factory=lambda: CoverageSeverityConfig(missing="warning")
    )
```
In `aggregation.py`:
```python
TIER_TO_BUCKET: dict[str, str] = {
    "full": "full",
    "partial": "partial",
    "failing": "failing",
    "missing": "missing",
}
```
In `generator.py`, `_TIER_DESCRIPTIONS`:
```python
_TIER_DESCRIPTIONS: dict[str, str] = {
    "failing": "test failures detected",
    "full": "fully covered",
    "partial": "some assertions covered",
    "missing": "no coverage",
}
```
`_tier_to_severity` no longer needs the hyphen→underscore replacement (tiers are single words now); simplify to `getattr(severity_config, tier, "error")`. Update `_SEVERITY_TO_BUCKET` mapping `"error": "missing"` (was `"none"`). Update `TierBuckets` dataclass field `none` → `missing` (grep `aggregation.py` for the dataclass) and any `buckets.none`/`TIER_TO_BUCKET.get(..., "none")` fallbacks → `"missing"`.

- [ ] **Step 4: Run, verify pass.** `pytest tests/core -k "severity or bucket or tier" -v` → PASS.

- [ ] **Step 5: Sweep.** `grep -rn 'full_direct\|full_indirect\|\.none\b\|"none"\|buckets\.none' src/elspais tests | grep -iE 'sever|bucket|tier|coverage'` and migrate. Update viewer filter code/tests referencing bucket `none` → `missing` (REQ-d00258-E). Run `pytest tests/core/test_html tests/core/test_aggregation* -v`.

- [ ] **Step 6: Commit.** `[CUR-1568] refactor: severity config + buckets use unified vocabulary (missing replaces none, full replaces direct/indirect split)`

### Task 1.3: Per-relationship status-word map (single source, configurable)

**Files:**
- Create: `src/elspais/config/status_words.py`
- Modify: `src/elspais/html/generator.py:121-127` (`_DIMENSION_LABELS` → derive from the map)
- Modify: `src/elspais/config/schema.py` (add `CoverageConfig.status_words` or a top-level map — see below)
- Test: `tests/core/test_status_words.py`

**Interfaces:**
- Produces: `get_status_words(config) -> dict[str, str]` returning dimension-key → label, defaulting to `{"implemented": "Implemented", "tested": "Tested", "verified": "Passing", "uat_coverage": "UAT Covered", "uat_verified": "UAT Passed"}`, overridable via `[coverage.status_words]` keyed by relationship name (`implements`, `verifies`, `yields`, `validates`, `validated`). A `RELATIONSHIP_TO_DIMENSION` map documents the edge→dimension link.

- [ ] **Step 1: Write failing tests** (sub-agent). Tag REQ-d00258 (per-relationship status word): default map returns the five REQ-d00258-B words; a config with `[coverage.status_words] verifies = "Exercised"` makes `get_status_words(config)["tested"] == "Exercised"`; unknown keys ignored.

- [ ] **Step 2: Run, verify fail.** `pytest tests/core/test_status_words.py -v` → FAIL (module missing).

- [ ] **Step 3: Implement.** `config/status_words.py`:

```python
"""Per-relationship coverage status words (single source for dimension labels).

The label shown on a coverage badge/button/hover is defined per RELATIONSHIP
(the edge kind whose presence confers the coverage), not by the raw edge-kind
name -- "Verifies"/"Yields" would read poorly as labels (design §2).
"""
from __future__ import annotations
from typing import Any

# relationship (config key) -> internal RollupMetrics dimension key
RELATIONSHIP_TO_DIMENSION: dict[str, str] = {
    "implements": "implemented",
    "verifies": "tested",
    "yields": "verified",
    "validates": "uat_coverage",
    "validated": "uat_verified",
}

_DEFAULT_WORDS: dict[str, str] = {
    "implemented": "Implemented",
    "tested": "Tested",
    "verified": "Passing",
    "uat_coverage": "UAT Covered",
    "uat_verified": "UAT Passed",
}


def get_status_words(config: dict[str, Any] | None) -> dict[str, str]:
    """dimension-key -> label, defaults overridable via [coverage.status_words]."""
    words = dict(_DEFAULT_WORDS)
    rules = (config or {}).get("rules", {})
    cov = rules.get("coverage", {}) if isinstance(rules, dict) else {}
    overrides = cov.get("status_words", {}) if isinstance(cov, dict) else {}
    if isinstance(overrides, dict):
        for rel, word in overrides.items():
            dim = RELATIONSHIP_TO_DIMENSION.get(str(rel).lower())
            if dim and isinstance(word, str) and word:
                words[dim] = word
    return words
```

Add `status_words: dict[str, str] = Field(default_factory=dict)` to `CoverageConfig` in schema.py so the key validates. In `generator.py`, replace uses of `_DIMENSION_LABELS[dim_key]` with `get_status_words(config)[dim_key]` (import at top of the two functions). Keep `_DIMENSION_LABELS` as the default fallback or delete it in favor of `_DEFAULT_WORDS`.

- [ ] **Step 4: Run, verify pass.** `pytest tests/core/test_status_words.py tests/core/test_html -v` → PASS.

- [ ] **Step 5: Commit.** `[CUR-1568] feat: per-relationship status-word map as single source for coverage labels (REQ-d00258)`

---

## Phase 2 — Relative chain denominators + missing-severity

Introduce the relative-denominator projection so Tested is measured over implemented and Passing over tested; an empty denominator yields `missing` at neutral severity.

### Task 2.1: `_relative_tier` projection helper

**Files:**
- Modify: `src/elspais/html/generator.py` (add helper near `_tier_to_severity`)
- Test: `tests/core/test_html/test_relative_tiers.py`

**Interfaces:**
- Produces: `_relative_tier(num_dim: CoverageDimension, denom_labels: set[str], *, allow_indirect: bool = True) -> tuple[str, bool]` returning `(tier, is_na)` where `tier ∈ {full, partial, failing, missing}` and `is_na` is True iff the denominator is empty. Consumed by Task 2.2 and by aggregation Task 2.3.

- [ ] **Step 1: Write failing tests** (sub-agent). Tag REQ-d00258 (relative chain). Build a `RollupMetrics` where implemented labels = {A,B}, tested labels = {A}; assert `_relative_tier(rollup.tested, denom={A,B})` → `("partial", False)` (1 of 2 implemented tested); `_relative_tier(rollup.tested, denom=set())` → `("missing", True)` (nothing implemented → N/A); with a failing label in denom → `("failing", False)`; all denom labels covered → `("full", False)`; denom non-empty but zero covered → `("missing", False)` (real gap, not N/A).

- [ ] **Step 2: Run, verify fail.** `pytest tests/core/test_html/test_relative_tiers.py -v` → FAIL (helper missing).

- [ ] **Step 3: Implement.**

```python
def _relative_tier(
    num_dim: "CoverageDimension",
    denom_labels: set[str],
    *,
    allow_indirect: bool = True,
) -> tuple[str, bool]:
    """Tier of ``num_dim`` measured over the relative denominator ``denom_labels``.

    Returns ``(tier, is_na)``. ``is_na`` is True when the denominator is empty
    (nothing to measure -> ``missing`` at neutral severity, design §1/§2). A
    failing label within the denominator wins (``failing``). ``allow_indirect``
    selects the credited per-label fractions (Phase 4 threads the config).
    """
    eps = 1e-9
    if not denom_labels:
        return "missing", True
    if num_dim.failing_labels & denom_labels:
        return "failing", False
    pct = num_dim.indirect_pct_by_label if allow_indirect else num_dim.direct_pct_by_label
    covered = sum(min(pct.get(lbl, 0.0), 1.0) for lbl in denom_labels)
    n = len(denom_labels)
    if covered >= n - eps:
        return "full", False
    if covered > eps:
        return "partial", False
    return "missing", False
```

- [ ] **Step 4: Run, verify pass.** → PASS.

- [ ] **Step 5: Commit.** `[CUR-1568] feat: _relative_tier projection helper for chain denominators (REQ-d00258)`

### Task 2.2: Wire relative tiers + missing-severity into `compute_coverage_tiers`

**Files:**
- Modify: `src/elspais/html/generator.py:262-313` (`dim_map` loop)
- Test: `tests/core/test_html/test_coverage_tiers*.py`

**Interfaces:**
- Consumes: `_relative_tier` (2.1). Produces: `compute_coverage_tiers` where `tested` uses denom = implemented label-set, `verified` uses denom = tested label-set, `uat_verified` uses denom = uat_coverage label-set; `implemented` and `uat_coverage` stay absolute (over all assertion labels). A `missing` tier with `is_na=True` resolves to neutral severity (`info`) regardless of the dimension's configured `missing` severity; a `missing` with `is_na=False` uses the configured severity.

- [ ] **Step 1: Write failing tests** (sub-agent). Tag REQ-d00258. The DIARY-GUI case: 0 implemented, status Active → `impl_tier == "missing"`, `impl_color` red; `tested_tier == "missing"` but `tested_color` GREY (neutral, `is_na`), NOT yellow. The 1/5 case: implemented partial (yellow), tested `full` green (1/1 implemented), verified `full` green. Assert `combined_bucket` unaffected by the neutral N/A dims.

- [ ] **Step 2: Run, verify fail.** `pytest tests/core/test_html -k "tier or diary or relative" -v` → FAIL.

- [ ] **Step 3: Implement.** Compute the denominator label sets once from the rollup, then in the loop pick relative vs absolute per dimension and apply the neutral-N/A severity override. Sketch:

```python
    impl_labels = set(rollup.implemented.indirect_pct_by_label)
    tested_labels = set(rollup.tested.indirect_pct_by_label)
    passing = tested_and_passing(rollup)
    passing_labels = set(passing.indirect_pct_by_label)
    uatcov_labels = set(rollup.uat_coverage.indirect_pct_by_label)
    all_labels = {c.get_field("label", "") for c in node.iter_children()
                  if c.kind == NodeKind.ASSERTION} - {""}

    # (dim_key, dim, sev_cfg, prefix, denom_labels_or_None-for-absolute)
    dim_map = [
        ("implemented", rollup.implemented, cov_config.implemented, "impl", None),
        ("tested", rollup.tested, cov_config.tested, "tested", impl_labels),
        ("verified", passing, cov_config.verified, "verified", tested_labels),
        ("uat_coverage", rollup.uat_coverage, uat_cov_cfg, "uat_cov", None),
        ("uat_verified", rollup.uat_verified, uat_ver_cfg, "uat_ver", uatcov_labels),
    ]
    for dim_key, dim, sev_cfg, prefix, denom in dim_map:
        if denom is None:
            tier = dim.tier          # absolute
            is_na = False
        else:
            tier, is_na = _relative_tier(dim, denom)  # allow_indirect wired in Phase 4
        severity = "info" if (tier == "missing" and is_na) else _tier_to_severity(tier, sev_cfg)
        color = _severity_color(severity)
        ...
```

Keep the existing worst-severity/combined_bucket logic below unchanged (neutral `info` already buckets `full`, so N/A dims don't drag — confirm the assertion in tests).

- [ ] **Step 4: Run, verify pass.** `pytest tests/core/test_html -v` → PASS.

- [ ] **Step 5: Commit.** `[CUR-1568] feat: Tested/Passing/UAT-Passed use relative denominators; empty denominator is neutral missing (REQ-d00258)`

### Task 2.3: Relative denominators in `aggregation.py` tier buckets

**Files:**
- Modify: `src/elspais/graph/aggregation.py:201-219` (`tier_buckets`)
- Test: `tests/core/test_aggregation*.py`

**Interfaces:**
- Consumes: relative-tier logic. Produces: `tier_buckets(graph, dimension=...)` where `tested`/`verified`/`uat_verified` bucket by their relative tier (not `dim.tier`). Extract a shared `relative_tier_for(rollup, dimension) -> tuple[str, bool]` used by BOTH generator and aggregation to avoid duplication (put it in `aggregation.py`, import into generator, or vice-versa — one home).

- [ ] **Step 1: Write failing tests** (sub-agent). Tag REQ-d00258-C/E. A graph where a requirement has implemented=partial, all-implemented tested → `tier_buckets(graph, "tested")` counts it `full`, not `partial`; a requirement with nothing implemented → its `tested` bucket is `missing` (N/A), and (per §5) does not count as a coverage gap.

- [ ] **Step 2: Run, verify fail.** → FAIL.

- [ ] **Step 3: Implement.** Add a shared helper (single home) returning the relative tier from a rollup + dimension name, using the denominator map (`tested`←implemented, `verified`←tested, `uat_verified`←uat_coverage; others absolute). Refactor `_relative_tier` (2.1) to consume label sets so both call sites share it. Use it in `tier_buckets`.

- [ ] **Step 4: Run, verify pass.** `pytest tests/core/test_aggregation* -v` → PASS.

- [ ] **Step 5: Commit.** `[CUR-1568] feat: aggregation tier buckets honor relative denominators (REQ-d00258-C)`

---

## Phase 3 — `expects_implementation` per-status + resolver

Replace the implicit "active-role-only" coverage grouping with an explicit per-status flag, and stop suppressing non-active coverage badges.

### Task 3.1: `StatusConfig.expects_implementation` + resolver

**Files:**
- Modify: `src/elspais/config/schema.py:401-403` (`StatusConfig`)
- Modify: `src/elspais/config/__init__.py` (add `status_expects_implementation`, export it)
- Test: `tests/core/test_config_status_expects_impl.py`

**Interfaces:**
- Produces: `StatusConfig` gains `expects_implementation: bool | None = None` (None = derive from role). `status_expects_implementation(config: dict, status: str | None) -> bool`: explicit `[statuses.<Name>].expects_implementation` wins; else role default (`role_of(status) == ACTIVE` → True, else False). Case-insensitive on status name (mirror `level_expects_validation`).

- [ ] **Step 1: Write failing tests** (sub-agent). Tag the new REQ (see 5.3). Default config: `status_expects_implementation(cfg, "Active")` True; `"Draft"` False; `"Deprecated"` False. With `[statuses.Draft] expects_implementation = true` → True. With hht-style `[rules.format.status_roles] active = ["Active","Draft"]` and no explicit flag → Draft derives True (role default). Unknown status → False? (role_of unknown → ACTIVE → True). Assert unknown → True to match `role_of` default, and document it.

- [ ] **Step 2: Run, verify fail.** → FAIL.

- [ ] **Step 3: Implement.** In schema:
```python
class StatusConfig(_StrictModel):
    """Optional per-status metadata. Keys match status names from status_roles."""

    color: str | None = None
    expects_implementation: bool | None = None
    ...
```
In `config/__init__.py` (mirror `level_expects_validation`):
```python
def status_expects_implementation(config: dict[str, Any], status: str | None) -> bool:
    """Whether a requirement's STATUS expects implementation (design §3).

    Explicit ``[statuses.<Name>].expects_implementation`` wins; otherwise the
    status's ROLE decides (active-role -> True, else False). Single source of
    truth; consumers (viewer, aggregation, health, gaps, summary, mcp) MUST call
    this rather than reading status roles for coverage-expectation. Replaces the
    coverage roles of ``StatusRolesConfig.is_excluded_from_coverage``.
    """
    statuses = (config or {}).get("statuses")
    if isinstance(statuses, dict) and status:
        target = status.lower()
        for key, spec in statuses.items():
            if isinstance(key, str) and key.lower() == target:
                val = spec.get("expects_implementation") if isinstance(spec, dict) \
                    else getattr(spec, "expects_implementation", None)
                if val is not None:
                    return bool(val)
    from elspais.config.status_roles import StatusRole
    return get_status_roles(config or {}).role_of(status) == StatusRole.ACTIVE
```
Add `"status_expects_implementation"` to `__all__`.

- [ ] **Step 4: Run, verify pass.** → PASS.

- [ ] **Step 5: Commit.** `[CUR-1568] feat: per-status expects_implementation flag + resolver (default from role)`

### Task 3.2: Badges always render; `Implemented` gap severity gated by the flag

**Files:**
- Modify: `src/elspais/html/generator.py:220` and `:401` (remove the coverage-excluded early return)
- Modify: `src/elspais/html/generator.py` (`implemented` severity resolution in `compute_coverage_tiers`)
- Test: `tests/core/test_html/test_expects_implementation.py`

**Interfaces:**
- Consumes: `status_expects_implementation` (3.1). Produces: `compute_coverage_tiers`/`compute_assertion_coverage_states` no longer return `empty`/`{}` for non-active statuses — they always compute. The `implemented` dimension's `missing` tier resolves to neutral `info` (grey) when `not status_expects_implementation(config, node.status)`, else the configured severity (red).

- [ ] **Step 1: Write failing tests** (sub-agent). Tag the new REQ. A Draft requirement (role default false) with 0 implemented → `compute_coverage_tiers` returns non-empty, `impl_tier == "missing"`, `impl_color` GREY (not empty, not red). An Active requirement with 0 implemented → `impl_color` red. A Draft req with `[statuses.Draft] expects_implementation=true` → red. `compute_assertion_coverage_states` returns per-assertion standings for a Draft req (non-empty).

- [ ] **Step 2: Run, verify fail.** → FAIL (currently returns empty for Draft).

- [ ] **Step 3: Implement.** Delete the two `if node.status in ... coverage_excluded_statuses(): return empty/{}` guards (lines 220, 401). In the `dim_map` loop, for `dim_key == "implemented"`, override severity when the status does not expect implementation:
```python
        if denom is None:
            tier = dim.tier
            is_na = False
        else:
            tier, is_na = _relative_tier(dim, denom)
        neutral = (tier == "missing" and is_na)
        if dim_key == "implemented" and tier == "missing" \
                and not status_expects_implementation(config or {}, node.status):
            neutral = True
        severity = "info" if neutral else _tier_to_severity(tier, sev_cfg)
```
Import `status_expects_implementation` at the top of the function.

- [ ] **Step 4: Run, verify pass.** `pytest tests/core/test_html -v` → PASS. Also run the viewer/routes tests: `pytest tests/core/test_server_routes.py -v`.

- [ ] **Step 5: Commit.** `[CUR-1568] feat: coverage always rendered; Implemented gap severity gated by expects_implementation`

### Task 3.3: Migrate aggregate rollup inclusion to the resolver

**Files:**
- Modify: `src/elspais/graph/aggregation.py:115,121` (`aggregate_by_level`), `:174` (`aggregate_dimension`), `:209` (`tier_buckets`)
- Modify callers passing `exclude_status`: `src/elspais/commands/summary.py:109`, `src/elspais/commands/health.py:2044,2047,2062,2102,2663`, `src/elspais/mcp/server.py:1787,2132`
- Test: `tests/core/test_aggregation*.py`, `tests/core/test_summary*.py`

**Interfaces:**
- Produces: coverage aggregates count a requirement iff `status_expects_implementation(config, node.status)` (replaces `node.status in coverage_excluded_statuses()`). The `is_excluded_from_coverage`/`coverage_excluded_statuses` methods remain in `status_roles.py` (used as the default source and possibly elsewhere) but are NO LONGER the coverage gate.

- [ ] **Step 1: Write failing tests** (sub-agent). Tag REQ-d00258-C + the new REQ. With default config, a Draft requirement is excluded from `aggregate_by_level` implemented totals (role default false) — same as today. With `[statuses.Draft] expects_implementation=true`, the Draft req IS counted. This is the behavior the old `active=["Active","Draft"]` hack gave, now surgical.

- [ ] **Step 2: Run, verify fail.** → FAIL.

- [ ] **Step 3: Implement.** Introduce a small predicate in `aggregation.py`, e.g. `_counts_for_coverage(config, node) -> bool` = `status_expects_implementation(config, node.status)`, and replace the `node.status in exclude_status` checks in the three aggregation functions with it (thread `config` where needed; `aggregate_dimension`/`tier_buckets` currently take `exclude_status` — add an optional `config` param and prefer the predicate, keeping `exclude_status` for callers not yet migrated OR migrate all callers in this task). Update the listed callers to pass `config` instead of computing `coverage_excluded_statuses()`. Keep health/summary/mcp output shape identical.

- [ ] **Step 2b: Note** — do NOT change `analysis.py` (aspirational/retired analysis exclusion stays on the role system) or `default_hidden_statuses`.

- [ ] **Step 4: Run, verify pass.** `pytest tests/core/test_aggregation* tests/core/test_summary* tests/commands/test_health* -v` → PASS. Run the e2e coverage-relevant subset if quick.

- [ ] **Step 5: Commit.** `[CUR-1568] refactor: coverage aggregate inclusion via expects_implementation (replaces is_excluded_from_coverage gate)`

---

## Phase 4 — `allow_indirect` toggle + direct/indirect hover provenance

### Task 4.1: `[coverage] allow_indirect` config + threading

**Files:**
- Modify: `src/elspais/config/schema.py` (`CoverageConfig` gains `allow_indirect: bool = True`)
- Modify: `src/elspais/html/generator.py` (thread into `_relative_tier` calls + implemented absolute tier), `src/elspais/graph/aggregation.py` (shared relative-tier helper)
- Test: `tests/core/test_html/test_allow_indirect.py`

**Interfaces:**
- Produces: `CoverageConfig.allow_indirect: bool = True`. When `False`, the credited fraction is `direct_pct_by_label` (not `indirect_pct_by_label`) everywhere the state/tier is computed — including the `implemented` absolute tier (use `direct >= total` instead of `indirect >= total`).

- [ ] **Step 1: Write failing tests** (sub-agent). Tag the new REQ. A requirement whose single assertion is covered ONLY via REFINES conduction (direct_pct=0, indirect_pct=1.0): with `allow_indirect=true` → tested `full`; with `[coverage] allow_indirect=false` → tested `missing` (direct 0).

- [ ] **Step 2: Run, verify fail.** → FAIL.

- [ ] **Step 3: Implement.** Add `allow_indirect: bool = True` to `CoverageConfig`. Read it in `compute_coverage_tiers` and pass `allow_indirect=cov_config.allow_indirect` to `_relative_tier`. For the absolute `implemented`/`uat_coverage` tiers, when `allow_indirect` is False compute the tier from `direct` sums — add an `allow_indirect` param to a small absolute-tier helper OR compute inline: `covered = dim.direct if not allow_indirect else dim.indirect`. Thread the same flag through the aggregation shared helper.

- [ ] **Step 4: Run, verify pass.** → PASS.

- [ ] **Step 5: Commit.** `[CUR-1568] feat: [coverage] allow_indirect toggles whether indirect credits coverage state (REQ-d00258)`

### Task 4.2: Direct/indirect provenance in hover + `~` marker per dimension

**Files:**
- Modify: `src/elspais/html/generator.py` (tip construction in `compute_coverage_tiers`)
- Modify: viewer template/JS hover if it renders its own tip — `src/elspais/html/templates/partials/js/_card-stack.js.j2` (grep for tip/title usage)
- Test: `tests/core/test_html/test_hover_provenance.py`

**Interfaces:**
- Produces: each dimension tip includes provenance: `"<Label>: <tier> — Nn% direct[, Mm% indirect ~]"`; a `~` marker is appended to the tip (and available as a per-dimension flag e.g. `impl_marker`) when `indirect > direct + eps`. Under `allow_indirect=false`, indirect shown as "(not credited)".

- [ ] **Step 1: Write failing tests** (sub-agent). Tag REQ-d00069-L + new REQ. A dimension with direct=0.4, indirect=1.0 of 1 assertion → tip contains "40% direct", "60% indirect", and ends with "~". A fully-direct dimension → tip has "100% direct", no "~". `allow_indirect=false` with indirect-only → tip notes "not credited".

- [ ] **Step 2: Run, verify fail.** → FAIL.

- [ ] **Step 3: Implement.** In the loop, compute `direct_pct = round(100*dim.direct/dim.total)`, `indirect_extra = dim.indirect - dim.direct`; build the provenance string and append `~` when `indirect_extra > eps`. Store `result[f"{prefix}_marker"] = "~" if ... else ""`. Ensure the template's badge/tooltip renders the marker + tip (check `_card-stack.js.j2` for where `*_tip`/`*_color` are consumed; wire the marker beside the badge glyph). Keep the existing headline `~` behavior consistent (REQ-d00069-L).

- [ ] **Step 4: Run, verify pass.** `pytest tests/core/test_html -v`; if browser test exists for tooltips, `pytest -m browser -k tooltip` (optional, pre-push).

- [ ] **Step 5: Commit.** `[CUR-1568] feat: hover shows direct/indirect provenance; per-dimension ~ marker (REQ-d00069-L)`

---

## Phase 5 — Health/gaps realignment + docs + governing requirements

### Task 5.1: Realign gap definitions to the relative denominator

**Files:**
- Modify: `src/elspais/commands/gaps.py`, `src/elspais/commands/health.py` (the `tests.coverage`/dimension checks)
- Test: `tests/commands/test_gaps*.py`, `tests/commands/test_health*.py`

**Interfaces:**
- Produces: a *testing* gap = implemented ∧ ¬tested; a *passing* gap = tested ∧ ¬passing; unimplemented assertions are NOT testing gaps. The `tests.coverage` health check counts only requirements where `status_expects_implementation` is true (mirror the `uat.coverage` level_filter pattern at `aggregation.py:176`).

- [ ] **Step 1: Write failing tests** (sub-agent). Tag REQ-d00258 + REQ-d00069-J. A requirement with an unimplemented assertion is NOT reported as a testing gap; an implemented-but-untested assertion IS. `tests.coverage` passes trivially when no status expects implementation.

- [ ] **Step 2: Run, verify fail.** → FAIL.

- [ ] **Step 3: Implement.** Update the gap predicate to intersect with the implemented/tested denominator label sets. Pass a `status_expects_implementation`-based filter to the dimension aggregate for the `tests.coverage` count (analogous to the existing `level_filter` for UAT).

- [ ] **Step 4: Run, verify pass.** `pytest tests/commands/test_gaps* tests/commands/test_health* -v` → PASS.

- [ ] **Step 5: Commit.** `[CUR-1568] fix: gaps/health realign to relative denominator; tests.coverage counts only expects_implementation reqs`

### Task 5.2: Legend + docs + init template + completion

**Files:**
- Modify: `src/elspais/html/theme.toml` (Legend entries for the unified states), viewer Legend partial
- Modify: `src/elspais/docs/cli/checks.md`, `docs/cli/test-targets.md`, `src/elspais/docs/configuration.md` (or `docs/configuration.md`)
- Modify: `src/elspais/commands/init.py` (config template: `[statuses.*]`, `[coverage] allow_indirect`, `[coverage.status_words]`)
- Test: `tests/` doc-sync tests (the pre-commit "Documentation sync tests")

**Interfaces:** none (docs/templates).

- [ ] **Step 1:** Update the viewer Legend to the unified `{full, partial, failing, missing}` states with their colors and the `~` caveat note. Grep `theme.toml`/Legend partial for the old tier labels.
- [ ] **Step 2:** Document `expects_implementation` (per-status, default from role, replaces the `active=["Active","Draft"]` reassignment) and `allow_indirect` in `configuration.md`; update coverage vocabulary docs to the relative chain.
- [ ] **Step 3:** Add the new keys (commented, with defaults) to the `init.py` config template and any shell completion list.
- [ ] **Step 4:** Run the documentation-sync tests: `pytest tests -k "doc or docs or completion" -v` → PASS.
- [ ] **Step 5: Commit.** `[CUR-1568] docs: legend + configuration + init template for relative coverage + expects_implementation + allow_indirect`

### Task 5.3: Governing REQ-d00258 sub-requirements (dogfood)

**Files:**
- Modify: `spec/dev-graph-core.md` (add sub-requirements under REQ-d00258; run `elspais fix`)
- Modify: `spec/INDEX.md` + `spec/_generated/*` (regenerated)
- Test: `pytest tests -k "spec or broken_ref"`; `elspais checks`

**Interfaces:** none (spec text).

- [ ] **Step 1:** Add the assertions from design §7 as new REQ-d00258 sub-requirements (unified vocabulary; relative chain + neutral missing; direct/indirect caveat + `allow_indirect`; per-relationship status word; `expects_implementation`). Where an existing assertion (e.g. REQ-d00258-E viewer buckets, REQ-d00069-L footing) needs rewording for the unified vocabulary, edit it in place.
- [ ] **Step 2:** Add `# Implements:`/`Verifies:` provenance tags in the code/tests written across Phases 1-4 pointing at the new sub-requirement IDs (grep the phase commits for untagged new functions; e.g. `status_expects_implementation`, `_relative_tier`, `get_status_words`).
- [ ] **Step 3:** `elspais fix` to re-hash; commit `spec/_generated/*` and `spec/INDEX.md`.
- [ ] **Step 4:** `elspais checks` → no broken references, no new errors. `pytest -k "spec or broken"` → PASS.
- [ ] **Step 5: Commit.** `[CUR-1568] spec: REQ-d00258 sub-requirements for relative coverage metrics + expects_implementation (re-hash)`

---

## Self-review notes

- **Spec coverage:** §1 chain → 2.1-2.3, 4.1; §2 unified vocab → 1.1-1.2, per-relationship words → 1.3; §3 expects_implementation → 3.1-3.3; §4 direct/indirect + allow_indirect → 4.1-4.2; §5 per-assertion/bucket → 2.2 (neutral N/A doesn't drag) + 3.2 (assertion states always render); §6 UAT symmetry → 2.2 (uat_verified relative) + 5.1 (uat.coverage pattern reused); §7 governing reqs → 5.3.
- **Per-assertion palette:** unchanged by design; `compute_assertion_coverage_states` keeps `{full,partial,failing,missing}` — only its early-return suppression is removed (3.2). No task changes the per-assertion standing rule.
- **Type consistency:** `_relative_tier(num_dim, denom_labels, *, allow_indirect) -> (tier, is_na)` used identically in 2.1/2.2/2.3/4.1; `status_expects_implementation(config, status) -> bool` used in 3.1/3.2/3.3/5.1; `get_status_words(config) -> dict` used in 1.3/2.2/4.2.
- **No RollupMetrics/CoverageDimension struct change** — verified: all relative logic reads existing `direct`/`indirect`/`*_pct_by_label`/`failing_labels` fields.
