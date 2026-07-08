# Indirect Coverage Redesign — Design

**Date:** 2026-07-07
**Branch:** CUR-1568-junit-path
**Supersedes brief:** `docs/design/indirect-coverage-redesign-BRIEF.md`
**Governing requirements:** REQ-d00069-B, REQ-d00069-J, REQ-d00069-L, REQ-d00258

## 1. Problem

`DIARY-PRD-linking-code-lifecycle` (8 assertions A–H; DEV refines it with a
blanket `Refines:`) renders internally-contradictory coverage in every surface.
The requirement header badge reads **IMPLEMENTED partial (yellow)** but
**TESTED / VERIFIED full (green)** — "fully tested, 12% implemented," which is
impossible — while assertions A–G render the grey **"no direct coverage"** hint
even though the header claims they are covered.

Verified live on the viewer (`localhost:5001`, this branch) and against the
built graph: for A–G, `implemented.indirect = 0.125`, `tested.indirect = 1.0`.

## 2. Root cause — TWO independent defects

Both must be fixed; fixing either alone leaves the badges nonsensical.

### Defect A — coverage math (`graph/annotators.py`)

Whole-requirement (assertion-less / "blanket") references are credited
**asymmetrically**, and blanket `Refines:` is fractionally deflated:

1. **Blanket `Implements:` on a CODE node credits nothing.** `annotate_coverage`
   (~line 1379-1390) handles `CODE` targets with `if edge.assertion_targets:`
   and **no `else`** — a blanket `Implements: REQ` from code adds zero
   `implemented` credit. By contrast a blanket `Verifies: REQ` (TEST_INDIRECT)
   and a blanket `Implements: REQ` from a child *requirement* (INFERRED) both
   credit **all** assertions. So the same "covers the whole requirement"
   semantics is honored for tests and child-reqs but dropped for code.
2. **Blanket `Refines:` is worth only `1/N`.** `_conduct_refines_coverage`
   (~line 1760-1766) credits a parent assertion (lacking direct evidence) with
   `mean(child coverage) / n_assertions` for a blanket refine. That `1/8` is the
   entire source of A–G's `0.125`.

Result: `tested.indirect = 1.0` (whole-req `Verifies` credits all) but
`implemented.indirect = 0.125` (blanket `Implements` credits ~nothing; only the
`1/N` refine leaks through).

### Defect B — display split (`html/templates/partials/js/_card-stack.js.j2`)

The per-assertion pills (IMP/TST/VER/VAL/ACC) are gated on **`assertion_links`**
— the presence of a *direct assertion-level link* (`if (aLinks && !aLinks[dim.linkKey]) return;`, ~line 568). Whole-req references never populate a
per-assertion link, so A–G fall through to the grey **"no direct coverage"**
text (~line 600) — even though `assertion_coverage_states[label]` (which reads
the generous `indirect_pct_by_label`) already computes "full" for them.

So the requirement header badge uses the **indirect (generous) footing** while
the per-assertion pills use **direct-link gating**. They use different footings
and therefore contradict each other. **Fixing Defect A alone does not fix this**
— A–G would still show "no direct coverage" because the pill is suppressed by
the link gate, not by the number.

## 3. The model — full credit + a derived caveat

Replace fractional "squishy" indirect with **full credit + a boolean caveat**.

1. **Whole-requirement references give FULL credit.** An `Implements`,
   `Refines`, or `Verifies` that names no assertion references **all** assertions
   equally at **full** credit — as if written `/A+B+…+Z`. No more `1/N`; no more
   fractional per-assertion indirect amounts.
2. **The "indirect caveat" is derived, not stored.** The fact "this assertion is
   covered, and its coverage leans on a whole-req reference" is already fully
   determined by the existing per-label floats:
   `indirect_pct_by_label[label] > direct_pct_by_label[label]`. `CoverageDimension`
   is **not** restructured (honors the CLAUDE.md encapsulation rule). `direct`
   and `indirect` are **nested footings, not a partition**: `direct ⊆ indirect`,
   so `indirect ≥ direct` always, and the caveat is exactly "`indirect` strictly
   exceeds `direct`."
3. **Display the caveat as a `~`, not a deflated number.** Same (full) number
   either way; a trailing `~` on the badge / `elspais checks` / viewer hover /
   per-assertion pill signals "some of this is whole-req/indirect evidence."

### Worked example (4 assertions; 1 whole-req ref + direct refs to A, B)

```text
              direct_pct   indirect_pct   caveat (indirect > direct)?
  A (direct)     1.0           1.0         no
  B (direct)     1.0           1.0         no
  C (blanket)    0.0           1.0         YES
  D (blanket)    0.0           1.0         YES
  ─────────────────────────────────────
  REQ sum        2.0 (50%)     4.0 (100%)  YES  (4.0 > 2.0)  -> "full ~"
```

The requirement is **full ~** (100% covered, caveated because 2 of 4 assertions
rely on the whole-req ref). A, B read clean full; C, D read full ~.

### The caveat is NON-transitive (deliberate)

The marker fires **only** for whole-req / blanket coverage. Assertion-targeted
coverage that is *conducted* up a `Refines:` edge from a child requirement lands
in `direct` and gets **no** `~` — it is transitive but assertion-specific. This
keeps the marker a precise locator of *where whole-req evidence is doing the
work*, rather than flagging all non-local coverage.

## 4. Changes

### 4.1 Coverage math (`graph/annotators.py`)

- **Blanket CODE `Implements` symmetry.** Add the missing `else` branch so a
  blanket `Implements: REQ` on a CODE node credits **all** assertions into the
  `implemented` **indirect** footing (not `direct`) — mirroring the INFERRED
  (child-req) and TEST_INDIRECT (whole-req test) paths. Implementation choice
  for the plan: reuse `CoverageSource.INFERRED` (its semantics — "whole-req
  implied, all assertions, indirect-only" — already match) vs. add a dedicated
  code-blanket source. Verify nothing downstream assumes INFERRED implies a REQ
  source before reusing it.
- **Retire the `1/N` blanket-`Refines` rule.** In `_conduct_refines_coverage`,
  drop the `/ n_assertions` divisor (~line 1764-1766) so a blanket refine
  credits `mean(child coverage)` at **full weight** into the **indirect** mode
  only. `direct` mode is unchanged (assertion-targeted refines still conduct at
  full weight into `direct`, per the non-transitive-caveat rule).

Net: A–G get `implemented.indirect = 1.0`; header reads IMPLEMENTED full ~,
consistent with TESTED/VERIFIED full ~.

### 4.2 Display unification (viewer + CLI)

- **Per-assertion pills read the indirect footing + caveat.** In
  `_card-stack.js.j2`, stop suppressing a dimension pill purely because there is
  no direct assertion-level link. When `assertion_coverage_states[label][dim]`
  is `full`/`partial`, render the pill with its state color and a `~` when the
  assertion's coverage is caveated (indirect > direct). Reserve
  "no direct coverage" for genuinely uncovered assertions
  (`missing`, no inherited template coverage).
- **Expose the per-assertion caveat as a first-class token.**
  `compute_assertion_coverage_states` (`html/generator.py`) currently returns
  only a standing token per dimension. Add the derived caveat bit (from
  `indirect_pct_by_label[label] > direct_pct_by_label[label]`) so the JS can
  render `~` without re-deriving. This is the one "indirect caveat" concept that
  both header badges and per-assertion pills consume.
- **Unify with the existing `~` marker (REQ-d00069-L).** CLI `summary`/`trace`
  already emit `~` at the dimension level via `indirect > direct`
  (`summary._marker`, `trace.py:314`). Keep that; the new per-assertion caveat
  is the same rule projected down one level. There must be exactly ONE "indirect
  caveat" concept, not two.

### 4.3 `elspais checks` (`commands/health.py`)

Surface the indirect caveat in checks output so a requirement whose coverage is
whole-req-only is visibly flagged (not silently counted as fully covered).

### 4.4 `[rules.coverage] allow_indirect`

Already behaves correctly under the new model and needs no code change, only a
doc/spec re-statement: `aggregation.py` selects `indirect_pct_by_label` when
`allow_indirect=True` (generous, default) and `direct_pct_by_label` when
`False` (strict). Under full-credit blanket refs, `allow_indirect=False`
therefore means "an assertion/dimension whose ONLY coverage is whole-req
(indirect-flagged) does NOT count as covered" — exactly the brief's intended
redefinition. Confirm with a test rather than re-implement.

### 4.5 Governing requirement rewording (spec)

- **REQ-d00069-J** — replace the `1/N` fractional-conduction rule with
  full-credit-into-indirect + the non-transitive caveat definition.
- **REQ-d00069-B** — state the whole-req `Implements`/`Verifies`/`Refines`
  symmetry (all credit all assertions fully, into the indirect footing).
- **REQ-d00069-L** — generalize the `~` footing marker to cover the unified
  per-assertion + requirement-level indirect caveat.
- **REQ-d00258** — vocabulary/surfaces: the caveat displays as `~` on badges,
  per-assertion pills, `elspais checks`, and viewer hover.

Re-hash affected spec blocks via `elspais fix`; commit `spec/_generated/*`.

## 5. Verification

- **Reproduction repo:** `~/cure-hht/hht_diary-worktrees/CUR-1568-oq-jny`. After
  the fix, `implemented.indirect_pct_by_label` for A–G = `1.0` (was `0.125`);
  header IMPLEMENTED reads full ~; per-assertion A–G render IMP ~ / TST ~ /
  VER ~ instead of "no direct coverage"; header and pills agree.
- **Relative chain (`graph/aggregation.py`).** `Tested` is measured relative to
  `implemented` (frac>0). Full-credit blanket refs grow the implemented
  denominator (A–G become implemented), so re-verify the relative tiers still
  read sensibly on the repro requirement.
- **Consistency invariant (REQ-d00258-G):** every assertion `full` ⇒ requirement
  dimension is a full tier; any assertion `failing` ⇒ `has_failures`. Header and
  per-assertion standings must never disagree.
- **Tests:** unit coverage for the annotator symmetry + retired `1/N`; a
  projection test for the derived per-assertion caveat; an e2e/browser check
  that the viewer badges and pills agree on the repro requirement. Tests must
  reference requirements (create/extend REQ-d00069/REQ-d00258 sub-reqs).

## 6. Key code locations

- `graph/annotators.py` — `annotate_coverage` (blanket CODE `else`, ~1379-1390);
  `_conduct_refines_coverage` (retire `1/N`, ~1760-1766).
- `graph/metrics.py` — `CoverageDimension` (unchanged structure); `direct`/
  `indirect` nested-footing semantics; `tier`.
- `graph/aggregation.py` — `relative_tier*` / `absolute_tier` / `allow_indirect`.
- `html/generator.py` — `compute_assertion_coverage_states` (add caveat token);
  `compute_coverage_tiers`.
- `html/templates/partials/js/_card-stack.js.j2` — per-assertion pill gating
  (~550-602); retire the direct-link-only suppression.
- `commands/summary.py` / `commands/trace.py` — dimension-level `~` (keep,
  unify). `commands/health.py` — `elspais checks` caveat surfacing.

## 7. Out of scope

- No new field on `CoverageDimension` / `RollupMetrics` (derive, don't store).
- No change to the `Graph`/`GraphBuilder`/`GraphTrace` structure or encapsulation.
- No change to non-coverage dimensions (`code_tested` line-based rollup).
