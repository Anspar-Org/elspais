# MASTER PLAN — Indirect Coverage Toggle

**Branch**: `feature/CUR-240-unified-test-results`
**Ticket**: CUR-240
**CURRENT_ASSERTIONS**: REQ-d00069-A, REQ-d00069-B, REQ-d00069-C, REQ-d00069-D, REQ-d00069-E, REQ-d00069-F, REQ-d00070-A, REQ-d00070-B, REQ-d00070-C, REQ-d00070-D, REQ-d00070-E

## Goal

Add a toggle to the trace view HTML that lets whole-requirement tests (e.g., `test_implements_req_d00087` with no assertion suffix) count as covering all assertions. Currently these tests contribute zero coverage — only `has_failures` propagates. The toggle provides a "progress indicator" view alongside the strict traceability view.

## Principle: Same pattern as INFERRED

The system already handles this for requirements: when `REQ-child implements REQ-parent` without assertion targets, it adds `INFERRED` coverage for all assertions (annotators.py:531-540). The new `INDIRECT` source follows the same logic for TEST nodes.

## Edge Case Rules

### Case 1: Mixed direct + indirect

REQ has 11 assertions. 3 have direct tests (assertion-targeted). 1 whole-req test also exists.

| Mode | Coverage | Detail |
|------|----------|--------|
| Strict | 3/11 = 27% `partial` | Only assertion-targeted tests count |
| Indirect | 11/11 = 100% `full` | Whole-req test covers all 11 |

### Case 2: Multiple tests, one failing

Assertion A targeted by 3 tests: test1 passes, test2 passes, test3 fails.

- `has_failures = True` (any failure, **same in both modes**)
- Assertion A is `validated` (at least one passing result)
- Warning icon shows alongside coverage dot regardless of mode

### Case 3: Whole-req test, mixed results

REQ has 5 assertions. Whole-req test1 passes, whole-req test2 fails.

| Mode | Coverage | validated | has_failures |
|------|----------|-----------|-------------|
| Strict | 0/5 = 0% `none` | 0 | True |
| Indirect | 5/5 = 100% `full` | 5 | True |

Display in indirect mode: `full` coverage + warning icon.

### Case 4: No whole-req test, only assertion-specific

REQ has 5 assertions. Tests target A, B, C (all pass). D, E untested.

Both modes: 3/5 = 60% `partial`. Indirect mode only affects tests with empty `assertion_targets`.

## Implementation Steps

### Step 1: Add `CoverageSource.INDIRECT` + dual metrics

`src/elspais/graph/metrics.py`:
- [ ] Add `INDIRECT = "indirect"` to `CoverageSource` enum
- [ ] Add fields to `RollupMetrics`: `indirect_coverage_pct: float`, `validated_with_indirect: int`
- [ ] Update `finalize()`: compute `indirect_coverage_pct` including INDIRECT source alongside existing `coverage_pct` (which excludes INDIRECT)

### Step 2: Emit INDIRECT contributions in annotator

`src/elspais/graph/annotators.py` (around line 488):
- [ ] When TEST edge has `assertion_targets=[]`, add INDIRECT contributions for ALL assertion labels
- [ ] Track `validated_indirect_labels`: when whole-req test passes, add all assertion labels
- [ ] Set `metrics.validated_with_indirect` before finalize

### Step 3: Generator dual data attributes

`src/elspais/html/generator.py`:
- [ ] Add `coverage_indirect: str` field to `TreeRow` dataclass
- [ ] Compute from `indirect_coverage_pct` (same thresholds: 0=none, <100=partial, 100=full)
- [ ] Pass through to template

### Step 4: Template + JS toggle

`src/elspais/html/templates/trace_view.html.j2`:
- [ ] Add `data-coverage-indirect="{{ row.coverage_indirect }}"` attribute on `<tr>`
- [ ] Add toggle button in filter bar area
- [ ] JS function: swap which `data-coverage*` attribute drives the coverage icon text and class

### Step 5: Tests

- [ ] `tests/core/test_coverage_metrics.py`: INDIRECT source, dual coverage computation, all 4 edge cases
- [ ] Integration test: whole-req test → `coverage_pct=0`, `indirect_coverage_pct=100`

## Files to Modify

| File | Change |
|------|--------|
| `src/elspais/graph/metrics.py` | Add `INDIRECT` enum, `indirect_coverage_pct`, `validated_with_indirect`, update `finalize()` |
| `src/elspais/graph/annotators.py` | Add INDIRECT contributions for whole-req tests, track `validated_indirect_labels` |
| `src/elspais/html/generator.py` | Add `coverage_indirect` to TreeRow, compute from `indirect_coverage_pct` |
| `src/elspais/html/templates/trace_view.html.j2` | Add `data-coverage-indirect`, toggle button, JS toggle |
| `tests/core/test_coverage_metrics.py` | Tests for INDIRECT source, dual coverage, edge cases |

## What Stays the Same

- `coverage_pct` (strict) — existing behavior, no change to default display
- `has_failures` — global boolean, same in both modes
- DIRECT, EXPLICIT, INFERRED sources — unchanged
- Default view shows strict coverage (toggle starts OFF)
- All existing tests pass unchanged

## Verification

1. `python -m pytest tests/ -x -q` — all pass
2. Run on fda-specs: `python -m elspais trace --view --embed-content --output /tmp/trace.html`
3. REQ-d00087: `data-coverage="none"` + `data-coverage-indirect="full"`
4. Toggle in browser switches coverage icons between strict and indirect
5. Warning icon shows regardless of toggle state
6. Existing elspais repo trace unchanged (toggle OFF = same as before)

## Archive

- [ ] Mark phase complete in MASTER_PLAN.md
- [ ] Archive completed plan: `mv MASTER_PLAN.md ~/archive/YYYY-MM-DD/MASTER_PLANx.md`
- [ ] Promote next plan: `mv MASTER_PLAN[lowest].md MASTER_PLAN.md`
- **CLEAR**: Reset checkboxes for next phase
