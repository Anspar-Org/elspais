# Indirect Coverage Redesign — Design

**Date:** 2026-07-07
**Branch:** CUR-1568-junit-path
**Supersedes brief:** `docs/design/indirect-coverage-redesign-BRIEF.md`
**Governing requirements:** REQ-d00069-B, REQ-d00069-J, REQ-d00069-L, REQ-d00258

## 1. Problem

`DIARY-PRD-linking-code-lifecycle` (8 assertions A–H; DEV refines it with a
blanket `Refines:`) renders internally-contradictory coverage in every surface.
The requirement header badge reads **IMPLEMENTED partial (yellow)** but
**TESTED / VERIFIED full (green)**, while assertions A–G render the grey
**"no direct coverage"** hint even though the header claims they are covered.

The defensible complaint is not "fully tested but not fully implemented" — that
is legitimately reachable (tests authored ahead of implementation). It is that
**syntactically identical whole-requirement references are honored for
`Verifies:` and dropped for `Implements:`**: a blanket `Verifies: REQ` credits
all 8 assertions as tested, but a blanket `Implements: REQ` credits none. The
same "this covers the whole requirement" semantics yields full on one dimension
and ~empty on another, and the per-assertion pills then contradict the header.

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
   `Refines`, `Verifies`, or `Validates` that names no assertion references
   **all** assertions equally at **full** credit — as if written `/A+B+…+Z`. The
   arbitrary `1/N` deflation is gone. Fractions do **not** vanish entirely: a
   *conducted* blanket `Refines:` still passes through the refining child's
   **actual** coverage (`mean(child coverage)`), so a 60%-covered child credits
   its refined parent assertions `0.6 ~`. That is the intended semantics — the
   fraction now reflects real child coverage instead of an arbitrary discount —
   not the `1/8`-from-nowhere the bug produced.
2. **The "indirect caveat" is derived, not stored.** The fact "this assertion is
   covered, and its coverage leans on a whole-req reference" is already fully
   determined by the existing per-label floats:
   `indirect_pct_by_label[label] > direct_pct_by_label[label]`. `CoverageDimension`
   is **not** restructured (honors the CLAUDE.md encapsulation rule). `direct`
   and `indirect` are **nested footings, not a partition**: `direct ⊆ indirect`,
   so `indirect ≥ direct` always, and the caveat is exactly "`indirect` strictly
   exceeds `direct`."
3. **Display the caveat as a `~`, not a deflated number.** A trailing `~` on the
   badge / `elspais checks` / viewer hover / per-assertion pill signals **"some
   of this coverage comes from a whole-requirement reference."** Note this is a
   narrower claim than "indirect evidence" in the everyday sense (see §3
   vocabulary note) — it means specifically *whole-req / assertion-less*.

### Worked example (5 assertions; 1 whole-req ref; direct refs to A, B; an
assertion-targeted `Refines: R/E` from a 30%-covered child)

```text
                        direct_pct   indirect_pct   caveat (indirect > direct)?
  A (direct)               1.0          1.0         no
  B (direct)               1.0          1.0         no
  C (blanket only)         0.0          1.0         YES
  D (blanket only)         0.0          1.0         YES
  E (targeted refine 0.3)  0.3          1.0*        YES   (*monotone: see §4.1)
  ───────────────────────────────────────────────
  REQ sum                  2.3 (46%)    5.0 (100%)  YES  (5.0 > 2.3) -> "full ~"
```

A, B read clean full. C, D read `full ~` (blanket only). E reads `partial`
(0.3) on the strict footing and `full ~` on the generous footing — the `~`
correctly says "the full reading leans on the whole-req blanket." Without the
monotone rule (§4.1 finding 3), E's indirect would *drop* to 0.3 because the
targeted refine suppresses the blanket candidate — adding specific evidence
would lower the headline. The monotone rule prevents that.

### The caveat is NON-transitive (deliberate)

The marker fires **only** for whole-req / blanket coverage. Assertion-targeted
coverage that is *conducted* up a `Refines:` edge from a child requirement lands
in `direct` and gets **no** `~` — it is transitive but assertion-specific. This
keeps the marker a precise locator of *where whole-req evidence is doing the
work*, rather than flagging all non-local coverage.

**Vocabulary consequence.** After this change, `direct` means "assertion-specific
(possibly conducted from a grandchild)" and `~` means specifically "a
whole-requirement reference is involved" — **not** "indirect" in the everyday
sense. UI copy must track this precise meaning (see §4.2): hover/legend reads
"some coverage comes from whole-requirement references," and the grey fallback
becomes "no coverage" (an uncovered assertion has nothing on *either* footing,
so the old "no direct coverage" wording would re-import the confusion).

## 4. Changes

### 4.1 Coverage math (`graph/annotators.py`)

- **Blanket CODE `Implements` symmetry.** Add the missing `else` branch so a
  blanket `Implements: REQ` on a CODE node credits **all** assertions into the
  `implemented` **indirect** footing (not `direct`) — mirroring the INFERRED
  (child-req) and TEST_INDIRECT (whole-req test) paths. **Use a dedicated source
  `CoverageSource.CODE_INDIRECT`**, mirroring the existing `TEST_DIRECT` /
  `TEST_INDIRECT` split — do **not** reuse `INFERRED`. `RollupMetrics` tracks
  `inferred_covered` with the specific meaning "implied by a child *requirement*";
  folding code-blanket credit into `INFERRED` would silently corrupt that
  provenance count and any hover that reads "inferred from child requirement."
  Wire `CODE_INDIRECT` into `finalize()` so it lands in `impl_indirect` (not
  `impl_direct`).
- **Retire the `1/N` blanket-`Refines` rule.** In `_conduct_refines_coverage`,
  drop the `/ n_assertions` divisor (~line 1764-1766) so a blanket refine
  credits `mean(child coverage)` at **full weight** into the **indirect** mode
  only. `direct` mode is unchanged (assertion-targeted refines still conduct at
  full weight into `direct`, per the non-transitive-caveat rule).
- **Monotone indirect footing (finding 3 — DECIDED).** The current suppression
  `if direct_vals: return mean(direct_vals)` (annotators.py:1749-1750) discards
  the whole-req candidate whenever an assertion has *any* assertion-targeted
  contributor — so adding a partially-covered `Refines: R/E` to an
  otherwise-blanket-covered assertion would *lower* its indirect value (E in the
  worked example: 1.0 → 0.3). That penalizes precision. **Decision:** in
  **indirect mode only**, return `max(mean(direct_vals), <whole-req candidates>)`
  so the generous footing never decreases when more-specific evidence is added.
  The **direct** footing is untouched (E stays 0.3 there), so E reads `partial`
  strict / `full ~` generous. Rationale: the whole point of the indirect footing
  is the generous reading; evidence must never reduce the headline. (Open to veto
  — the alternative "specific evidence overrides the blanket claim" is defensible
  but surprising, and makes the worked example not generalize.)

Net: A–G get `implemented.indirect = 1.0`; header reads IMPLEMENTED full ~,
consistent with TESTED/VERIFIED full ~.

### 4.2 Display unification (viewer + CLI)

- **Per-assertion states honor `allow_indirect` (finding 1 — MUST-FIX).**
  `compute_coverage_tiers` selects its footing from `[rules.coverage]
  allow_indirect` (generator.py:314,317), but `compute_assertion_coverage_states`
  currently hardcodes the indirect footing (generator.py:521). If the pills are
  unsuppressed while still hardcoded to indirect, then under `allow_indirect =
  false` the header reads the strict (direct) footing while the pills read the
  generous one — re-creating the *exact* header-vs-pill split this design exists
  to kill, and violating REQ-d00258-G. **The per-assertion projection must select
  its footing (`direct_pct_by_label` vs `indirect_pct_by_label`) from the same
  `allow_indirect` config as the tiers**, so header and pills always agree.
- **Per-assertion pills read the state footing + caveat.** In
  `_card-stack.js.j2`, stop suppressing a dimension pill purely because there is
  no direct assertion-level link. When the state is `full`/`partial`, render the
  pill with its state color and a `~` when the assertion's coverage is caveated
  (whole-req involved). **Exception:** state-less pills keep the link-gate — the
  `REF` pill has a `linkKey` but no `stateKey` (`_card-stack.js.j2:560`), so it
  has no coverage state to fall back on and must still gate on `assertion_links`.
- **Grey fallback becomes "no coverage."** Reserve the fallback for genuinely
  uncovered assertions and reword it from "no direct coverage" to "no coverage"
  (per §3 vocabulary note — after this change an uncovered assertion has nothing
  on either footing). Keep the existing INSTANCE "inherits from template" branch.
- **Expose the per-assertion caveat as a first-class token.**
  `compute_assertion_coverage_states` (`html/generator.py`) currently returns
  only a standing token per dimension. Add the derived caveat bit (the chosen
  footing's `indirect_pct > direct_pct` for that label) so the JS can render `~`
  without re-deriving. This is the one "indirect caveat" concept that both header
  badges and per-assertion pills consume.
- **Unify with the existing `~` marker (REQ-d00069-L).** CLI `summary`/`trace`
  already emit `~` at the dimension level via `indirect > direct`
  (`summary._marker`, `trace.py:314`). Keep that; the new per-assertion caveat
  is the same rule projected down one level. There must be exactly ONE "indirect
  caveat" concept, not two. Hover/legend copy: "some coverage comes from
  whole-requirement references."

### 4.3 `elspais checks` (`commands/health.py`)

**Own the trade-off explicitly.** Today's bug *under*-credits (blanket code
`Implements` = 0). The fix *over*-credits on the generous footing: one lazy
`Implements: REQ` on one helper marks all N assertions fully implemented. That
is acceptable — the `~` is unmissable and `allow_indirect = false` gives a
strict footing — **but it must be visible, not silent.**

Add a named, **info-level** check (not failing) that quantifies how load-bearing
the blankets are — e.g. `whole-requirement-only-coverage`: report a count and
list of "N assertions whose only coverage is whole-requirement evidence"
(per dimension where useful), so a team can see at a glance how much of their
green rests on blanket references. Output shape: one info line per affected
requirement (or a rollup count in the summary), consistent with the existing
`elspais checks` severity/format conventions. This replaces the current
one-sentence placeholder.

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
- **REQ-d00069-B** — state the whole-req symmetry across **all four** coverage
  keywords: `Implements`, `Verifies`, `Refines`, **and `Validates`** (blanket
  journey refs already credit all assertions via `UAT_INFERRED`, so the code is
  correct — but the reworded requirement must name Validates too, or it states a
  symmetry rule that visibly omits one edge kind).
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
- **Strict-mode agreement (finding 1):** with `allow_indirect = false`, header
  badge and per-assertion pills must read the **same** (strict) footing — a
  blanket-only assertion reads `missing`/no-pill on both, not `partial` header +
  `full` pill. Add an explicit test.
- **Monotone footing (finding 3):** an assertion covered by a blanket ref *plus*
  a partially-covered assertion-targeted `Refines:` must read `full ~` on the
  generous footing (not the lower targeted fraction) and `partial` on strict.
  Add an explicit test.
- **Tests:** unit coverage for the annotator symmetry (`CODE_INDIRECT`) + retired
  `1/N` + monotone rule; a projection test for the derived per-assertion caveat
  under both `allow_indirect` settings; an e2e/browser check that the viewer
  badges and pills agree on the repro requirement. Tests must reference
  requirements (create/extend REQ-d00069/REQ-d00258 sub-reqs).

## 6. Key code locations

- `graph/annotators.py` — `annotate_coverage` (blanket CODE `else` →
  `CODE_INDIRECT`, ~1379-1390); `_conduct_refines_coverage` (retire `1/N` +
  monotone `max` in indirect mode, ~1749-1766).
- `graph/metrics.py` — `CoverageSource` (add `CODE_INDIRECT`); `finalize()`
  (bucket `CODE_INDIRECT` into `impl_indirect`); `CoverageDimension` (unchanged
  structure); `direct`/`indirect` nested-footing semantics; `tier`.
- `graph/aggregation.py` — `relative_tier*` / `absolute_tier` / `allow_indirect`.
- `html/generator.py` — `compute_assertion_coverage_states` (honor
  `allow_indirect` footing + add caveat token); `compute_coverage_tiers`.
- `html/templates/partials/js/_card-stack.js.j2` — per-assertion pill gating
  (~550-602); retire the direct-link-only suppression (but keep it for the
  state-less `REF` pill at ~560); grey fallback copy → "no coverage".
- `commands/summary.py` / `commands/trace.py` — dimension-level `~` (keep,
  unify). `commands/health.py` — `elspais checks` whole-req-only info check.

## 7. Out of scope

- No new **caveat field** on `CoverageDimension` / `RollupMetrics` — the caveat
  is derived from the existing `direct`/`indirect` floats, not stored. (Adding
  the `CODE_INDIRECT` **enum member** to `CoverageSource` is a provenance-source
  addition, not a structural change to the metrics dataclasses.)
- No change to the `Graph`/`GraphBuilder`/`GraphTrace` structure or encapsulation.
- No change to non-coverage dimensions (`code_tested` line-based rollup).
