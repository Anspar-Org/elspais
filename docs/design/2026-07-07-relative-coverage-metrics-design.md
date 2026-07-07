# Relative (Chain) Coverage Denominators + Per-Status `expects_implementation`

**Date:** 2026-07-07
**Branch:** CUR-1568-junit-path
**Status:** Approved design (pending spec review)

## Problem

Two related defects in how coverage badges read:

1. **Absolute denominators mislead on downstream dimensions.** `Tested` and
   `Passing` are computed against *all* assertions, so a requirement with
   nothing implemented shows `Tested`/`Passing` as a gap against the full spec.
   Combined with the `verified.none = "warning"` default this produced the
   reported artifact: `Passing: no coverage` rendered **yellow** (looks
   partial) while `Implemented`/`Tested` were red — three "no coverage" states,
   three different colors, no intuitive reason. You cannot test what is not
   built; measuring downstream dimensions against the whole spec double-counts
   the upstream gap.

2. **"Expects implementation" is implicit and blunt.** Whether a requirement's
   missing implementation is an error is currently derived from the 4-role
   status system: `is_excluded_from_coverage` returns true for every role
   except `active`, and non-active requirements have their coverage badges
   **suppressed entirely** (`generator.py:220,401`). The only way to make a
   `Draft` requirement count like an active one is to reassign it into the
   `active` role (`[rules.format.status_roles] active = ["Active", "Draft"]`, as
   hht_diary does today) — which also changes its badge color, sort order,
   analysis inclusion, and default visibility. Implementation-expectation is
   entangled with role membership.

## Decisions (locked)

- **Chain interpretation (b):** `Tested / implemented`, `Passing / tested`.
- **Empty denominator → `not_applicable`:** grey, neutral severity, never a gap.
- **Failing always wins → red** (via per-label `failing_labels`, Task-Q).
- **`expects_implementation` is per-status** (lifecycle), **default derived from
  role** (active→true; provisional/aspirational/retired→false), overridable.
- **Separate axes:** `expects_implementation` per-status gates `Implemented`;
  `expects_validation` per-level gates `UAT Covered`. Orthogonal; both may apply
  to one requirement.
- **Per-assertion palette unchanged** (full/partial/failing/missing). An
  implemented-but-untested assertion is grey `missing`, same as an unimplemented
  one; the *gap* surfaces only at the requirement badge via the denominator.

## 1. The relative chain

Each dimension answers exactly one question against its own denominator:

```text
Implemented   built     / ALL assertions        (absolute)
Tested        tested    / IMPLEMENTED assertions (relative)
Passing       passing   / TESTED assertions      (relative)
```

- **Empty denominator** (implemented-count = 0 for `Tested`; tested-count = 0
  for `Passing`) yields a new **`not_applicable`** tier: grey, neutral severity,
  never counted as a gap. Distinct from `none` (a real gap that is in scope).
- **Failing** on any in-denominator label → red, regardless of fraction.
- Existing tier palette expresses the "partial-complete vs partial-incomplete"
  distinction directly, fed the *relative* fraction:
  - all implemented assertions tested, but not all assertions implemented →
    `full_indirect` (light-green) — "partial-complete"
  - some implemented assertions untested → `partial` (yellow) —
    "partial-incomplete"
  - all assertions implemented **and** tested → `full_direct` (green)

**No `RollupMetrics` struct change.** The relative denominators are computed at
the tier/standing *projection* from per-label fractions already present on the
dimensions (`implemented.indirect_pct_by_label`, `tested.indirect_pct_by_label`,
etc.). Implementation lands in `graph/aggregation.py` (tier/bucket rollups) and
`html/generator.py` (`compute_coverage_tiers`, `compute_assertion_coverage_states`).

## 2. `expects_implementation` (per-status)

- New boolean in the per-status `[status.<Name>]` metadata block.
- **Default derived from role:** active-role statuses → `true`;
  provisional/aspirational/retired → `false`. Overridable per status.
- **Single resolver** `status_expects_implementation(config, status)`, mirroring
  `level_expects_validation(config, level)`. All surfaces resolve through it —
  no surface reads the flag independently.
- **What it gates** (the `Implemented` dimension only; `Tested`/`Passing` get
  grey-when-empty for free from the chain):
  - `true` → `Implemented` gap is **red** (error, "coverage required").
  - `false` → `Implemented` gap is **neutral grey**, not flagged.
- **Replaces `is_excluded_from_coverage`** in its two coverage roles:
  1. **Badge severity** — red vs grey for the `Implemented` gap.
  2. **Aggregate-rollup inclusion** — a non-expecting requirement is excluded
     from the project "% implemented" denominator, exactly as excluded statuses
     are today (`aggregation.py:115`).

  The 4-role system **stays** for analysis exclusion (`analysis.py`),
  default-hidden (retired), sorting, and as the **default source** for the flag.
  Net change: coverage badges are now **always rendered** (today's full
  suppression is removed); the flag decides red-vs-grey and rollup inclusion.

### What it replaces (concrete)

```text
# today — blunt: Draft becomes active for EVERYTHING (color, sort, analysis)
[rules.format.status_roles]
active = ["Active", "Draft"]

# new — surgical: Draft keeps its provisional role; only impl-expectation flips
[rules.format.status_roles]
active = ["Active"]
[status.Draft]
expects_implementation = true
```

**Migration is graceful.** With derive-from-role defaults, an existing
`active = ["Active", "Draft"]` already yields `expects_implementation = true`
for Draft, so nothing breaks. Projects may then move Draft back to `provisional`
and use the explicit flag to recover the surgical (impl-only) behavior.

## 3. Per-assertion vs requirement tier + combined_bucket

- **Per-assertion palette unchanged** (full/partial/failing/missing). Grey
  `missing` = no evidence on this dimension for this assertion, whether N/A
  (unimplemented) or a gap (implemented, untested). The distinction is a
  requirement-level aggregate, not a per-assertion color.
- **Requirement tier** aggregates each relative dimension over its denominator's
  label set (e.g. `Tested` tier over the implemented-label set only).
- **combined_bucket** = worst among *applicable* dimensions. `not_applicable`
  (grey) tiers and `expects_implementation=false` gaps are neutral — they do not
  drag the bucket. An all-N/A requirement → neutral bucket. Worst-severity
  derivation (design §2.3) is otherwise unchanged.

## 4. UAT symmetry + health/gaps

- **UAT already embodies this shape:** `expects_validation` (per-level) gates
  `UAT Covered`, and `uat_verified` was made proportional/grey-when-empty
  (Task-P, REQ-d00255-C). So `UAT Passed` is already relative to `UAT Covered`.
  This work brings the *code* chain into symmetry; `UAT Passed` adopts the same
  `not_applicable` neutral treatment when its denominator is empty.
- **Health/gaps realign to the denominator:**
  - a *testing* gap = implemented ∧ ¬tested
  - a *passing* gap = tested ∧ ¬passing
  - unimplemented assertions are no longer "testing gaps"
  - the `tests.coverage` check counts only `expects_implementation` requirements,
    mirroring how `uat.coverage` counts only `expects_validation` levels; with no
    expecting statuses it passes trivially.

## 5. Governing requirements (dogfood)

New sub-requirements under REQ-d00258:

- **Relative chain + `not_applicable`:** `Tested`/`Passing` (and `UAT Passed`)
  SHALL be computed against a relative denominator (implemented / tested /
  uat-covered respectively); an empty denominator SHALL render `not_applicable`
  (grey, neutral, not a gap); a failing in-denominator label SHALL render
  failing regardless of fraction.
- **`expects_implementation`:** a per-status flag (default derived from role)
  SHALL declare whether a requirement's status expects implementation; when it
  does not, absent implementation SHALL be neither flagged nor red nor counted
  against aggregate implemented coverage; all surfaces SHALL resolve it through
  a single shared helper; it SHALL replace the coverage roles of
  `is_excluded_from_coverage`.

`elspais fix` re-hashes affected spec files; `spec/_generated/*` committed.

## Worked examples

- **DIARY-GUI-join-study-screen (0 implemented, status Active):** Implemented
  `none` → **red** (Active expects it). Tested & Passing denominators empty →
  grey **`not_applicable`** (no more misleading yellow).
- **1/5 implemented, that one tested + passing:** Implemented **yellow** (1/5
  absolute); Tested **light-green** (`full_indirect`, 1/1 of implemented);
  Passing **green** (1/1 of tested). combined_bucket **yellow** (worst
  applicable).
- **Draft req, 2/5 implemented, those tested + passing, `expects_implementation`
  unset (role default false):** Implemented gap grey (not red); the 2 built
  assertions still show their real Tested/Passing coverage. Excluded from the
  project implemented-% denominator.

## Scope boundaries (YAGNI)

- No `RollupMetrics` structural change; projection-layer only.
- No change to analysis scoring, default-hidden filtering, or status sorting —
  those stay on the role system.
- No new per-level implementation flag; PRD-via-refinement is already handled by
  REFINES conduction (indirect implemented coverage).
- Not touching Graph / GraphTrace / GraphBuilder structure or encapsulation.

## Affected modules

- `config/schema.py` — per-status `expects_implementation` (in `[status.*]`),
  `CoverageSeverityConfig` gains `not_applicable` (neutral default).
- `config/__init__.py` — `status_expects_implementation` resolver.
- `config/status_roles.py` — role remains the default source; coverage-exclusion
  callers migrate to the resolver.
- `graph/aggregation.py` — relative denominators in tier/bucket rollups; rollup
  inclusion via the resolver.
- `html/generator.py` — `compute_coverage_tiers` /
  `compute_assertion_coverage_states` relative denominators + `not_applicable`.
- `graph/health.py`, `commands/gaps.py` — gap definitions realigned.
- `html/theme.toml` — `not_applicable` standing/severity → grey catalog token;
  Legend entry.
- `spec/dev-graph-core.md` — new REQ-d00258 sub-requirements.
- Docs (`docs/cli/*.md`, `docs/configuration.md`), `commands/init.py` template,
  shell completion — surface the new flag.
