# Relative (Chain) Coverage Denominators, Unified Vocabulary + Per-Status `expects_implementation`

**Date:** 2026-07-07
**Branch:** CUR-1568-junit-path
**Status:** Approved design (pending spec review)

## Problem

Three related defects in how coverage reads:

1. **Absolute denominators mislead on downstream dimensions.** `Tested` and
   `Passing` are computed against *all* assertions, so a requirement with
   nothing implemented shows `Tested`/`Passing` as a gap against the full spec.
   Combined with the `verified.none = "warning"` default this produced the
   reported artifact: `Passing: no coverage` rendered **yellow** (looks partial)
   while `Implemented`/`Tested` were red — three "no coverage" states, three
   colors, no intuitive reason. You cannot test what is not built; measuring
   downstream dimensions against the whole spec double-counts the upstream gap.

2. **Three overlapping state vocabularies.** Tiers (`full-direct`,
   `full-indirect`, `partial`, `none`, `failing`), buckets (`full`, `partial`,
   `none`, `failing`), and per-assertion standings (`full`, `partial`,
   `failing`, `missing`) all name the same underlying states differently. The
   requirement tier and the per-assertion standing should be one vocabulary.

3. **"Expects implementation" is implicit and blunt.** Whether a requirement's
   missing implementation is an error is derived from the 4-role status system:
   `is_excluded_from_coverage` returns true for every role except `active`, and
   non-active requirements have their coverage badges **suppressed entirely**
   (`generator.py:220,401`). The only way to make a `Draft` requirement count is
   to reassign it into the `active` role
   (`[rules.format.status_roles] active = ["Active", "Draft"]`, as hht_diary does
   today) — which also changes its color, sort order, analysis inclusion, and
   default visibility. Implementation-expectation is entangled with role.

## Decisions (locked)

- **Chain interpretation (b):** `Tested / implemented`, `Passing / tested`.
- **One state vocabulary** for tier *and* standing *and* bucket:
  `full` / `partial` / `failing` / `missing`.
- **Empty denominator → `missing`** at neutral severity (grey), never a gap.
- **Failing always wins → red** (via per-label `failing_labels`, Task-Q).
- **`full-direct`/`full-indirect` collapse to `full`** (state word). The
  direct/indirect quality is a **caveat**, not a state: carried by the existing
  `~` marker and by hover text. The badge **color shade is dropped** (one green).
  The underlying `direct`/`indirect` **metrics are unchanged**.
- **Per-relationship status word** is the single source for dimension labels
  (buttons, hover, tier, standing): `Implements`→Implemented, `Verifies`→Tested,
  `Yields`→Passing, `Validates`→UAT Covered, (validation verified)→UAT Passed.
  Configurable, defaulting to these REQ-d00258-B words.
- **`allow_indirect`** — global `[coverage]` boolean, default `true`. When
  `false`, only direct coverage credits the state; indirect is still computed and
  shown in hover as non-credited.
- **`expects_implementation`** — per-status (lifecycle), default derived from
  role (active→true; others→false), overridable. Gates `Implemented`.
- **Separate axes:** `expects_implementation` per-status gates `Implemented`;
  `expects_validation` per-level gates `UAT Covered`. Orthogonal.
- **Per-assertion palette unchanged** (full/partial/failing/missing). An
  implemented-but-untested assertion is grey `missing`, same as an unimplemented
  one; the gap surfaces only at the requirement badge via the denominator.

## 1. The relative chain

Each dimension answers one question against its own denominator:

```text
Implemented   built     / ALL assertions        (absolute)
Tested        tested    / IMPLEMENTED assertions (relative)
Passing       passing   / TESTED assertions      (relative)
```

- **Empty denominator** (nothing implemented → Tested; nothing tested →
  Passing) yields state `missing` at **neutral severity** (grey), never a gap.
- **Failing** on any in-denominator label → red, regardless of fraction.
- The former "partial-complete" case (all implemented assertions tested, but not
  all assertions built) is now genuinely `full` on `Tested` — 100% of the
  *implemented* denominator. The "not all built" story lives on the `Implemented`
  badge; the "via indirect evidence" story lives on the `~` marker.

**No `RollupMetrics` struct change.** Relative denominators are computed at the
tier/standing *projection* from per-label fractions already on the dimensions
(`implemented.indirect_pct_by_label`, `tested.…`). Lands in `graph/aggregation.py`
and `html/generator.py`; `CoverageDimension.tier` itself is not the relative
computation (it lacks the sibling dimension) — the relative tier is a projection.

## 2. Unified vocabulary + per-relationship status words

### State vocabulary (tier = standing = bucket)

```text
full      green    100% of the dimension's (credited) denominator
partial   yellow   0 < f < 1
failing   red      a failed result on an in-denominator label
missing   grey     no coverage  (red only when it is an in-scope gap, via severity)
```

- `none` folds into `missing` — one "no coverage" word. Whether a `missing`
  reads **red gap** or **grey N/A** is a *severity* resolution (from
  `expects_implementation` + empty-denominator), not a separate state word. This
  reuses the catalog/severity decoupling the system already has, and removes the
  need for any `not_applicable` token (which would have collided with the
  authored `SHALL be NOT APPLICABLE` assertion-exclusion feature).
- `full-direct`/`full-indirect` fold into `full`; see §4 for the caveat.
- `TIER_TO_BUCKET` becomes identity over `{full, partial, failing, missing}`.

### Per-relationship status word

The dimension label (button/hover/tier/standing) is defined **per relationship**,
not by the raw edge-kind name (which would read as the confusing "Verified" /
"Yielded"):

| Relationship (edge) | Status word |
|---------------------|-------------|
| `Implements` | **Implemented** |
| `Verifies` | **Tested** |
| `Yields` | **Passing** |
| `Validates` | **UAT Covered** |
| (validation verified) | **UAT Passed** |

Re-keyed from the internal dimension key (`_DIMENSION_LABELS`) to the
relationship, exposed as a single configurable map (defaulting to the words
above, the REQ-d00258-B contract). A badge renders as `<status word>` colored by
`<state>`; hover is "`<status word>`: `<state>` — `<direct/indirect detail>`".

## 3. `expects_implementation` (per-status)

- New boolean in the per-status `[status.<Name>]` metadata block.
- **Default derived from role:** active→true; provisional/aspirational/retired→
  false. Overridable per status.
- **Single resolver** `status_expects_implementation(config, status)`, mirroring
  `level_expects_validation(config, level)`. No surface reads the flag directly.
- **Gates the `Implemented` dimension** (`Tested`/`Passing` get grey-when-empty
  for free from the chain):
  - `true` → `Implemented` gap is **red** (error).
  - `false` → `Implemented` gap is **neutral grey**, not flagged.
- **Replaces `is_excluded_from_coverage`** in its two coverage roles: badge
  severity, and aggregate-rollup inclusion (`aggregation.py:115`) — a
  non-expecting requirement is excluded from the project "% implemented"
  denominator, exactly as excluded statuses are today. The 4-role system stays
  for analysis exclusion, default-hidden, sorting, and as the flag's default
  source. Net: coverage badges are now **always rendered** (today's suppression
  is removed); the flag decides red-vs-grey and rollup inclusion.

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

Migration is graceful: with derive-from-role defaults, an existing
`active = ["Active", "Draft"]` already yields `expects_implementation = true`, so
nothing breaks. Projects may then move Draft back to `provisional` and use the
explicit flag for the surgical (impl-only) behavior.

## 4. Direct vs indirect: the caveat and `allow_indirect`

The `direct`/`indirect` metrics and the REFINES-conduction machinery are
**unchanged**. Only the *display* treats direct as the desired metric and
indirect as a credited-but-flagged fallback:

- The badge **state color** does not distinguish direct from indirect (one green
  for `full`).
- The **`~` marker** flags "not fully direct" (indirect > direct) — the caveat.
- **Hover always states provenance** — e.g. "Tested: full — 100% direct" vs
  "Tested: full `~` — 40% direct, 60% indirect".

**`allow_indirect`** — global `[coverage] allow_indirect` boolean, default
`true`:

- `true` — indirect credits the headline state (today's generous footing,
  REQ-d00069-L); `~` marks indirect > direct.
- `false` — only **direct** credits the state/gap. A requirement covered *only*
  via conduction reads `missing`/`partial`, not `full`. Indirect is still
  computed and shown in hover as a non-credited note ("60% indirect, not
  credited"), so the fallback is visible without masking a direct gap.

Global scope now (YAGNI); per-dimension/per-relationship can be added later if a
real need appears.

## 5. Per-assertion vs requirement tier + combined_bucket

- **Per-assertion palette unchanged** (full/partial/failing/missing). Grey
  `missing` = no evidence on this dimension for this assertion, whether N/A
  (unimplemented) or a gap (implemented, untested). The distinction is a
  requirement-level aggregate, not a per-assertion color.
- **Requirement tier** aggregates each relative dimension over its denominator's
  label set (credited per `allow_indirect`).
- **combined_bucket** = worst among *applicable* dimensions. `missing` at neutral
  severity and `expects_implementation=false` gaps do not drag the bucket. An
  all-neutral requirement → neutral bucket. Worst-severity derivation (design
  §2.3) otherwise unchanged.

## 6. UAT symmetry + health/gaps

- **UAT already embodies this shape:** `expects_validation` (per-level) gates
  `UAT Covered`, and `uat_verified` was made proportional/grey-when-empty
  (Task-P, REQ-d00255-C). `UAT Passed` is already relative to `UAT Covered`; it
  adopts the unified `missing`/neutral treatment for the empty case.
- **Health/gaps realign to the denominator:**
  - a *testing* gap = implemented ∧ ¬tested
  - a *passing* gap = tested ∧ ¬passing
  - unimplemented assertions are no longer "testing gaps"
  - the `tests.coverage` check counts only `expects_implementation` requirements,
    mirroring how `uat.coverage` counts only `expects_validation` levels; with no
    expecting statuses it passes trivially.

## 7. Governing requirements (dogfood)

New / revised sub-requirements under REQ-d00258:

- **Unified vocabulary:** requirement tier, per-assertion standing, and bucket
  SHALL use one state vocabulary — `full`, `partial`, `failing`, `missing`.
- **Relative chain:** `Tested`/`Passing` (and `UAT Passed`) SHALL be computed
  against a relative denominator (implemented / tested / uat-covered); an empty
  denominator SHALL render `missing` at neutral severity (not a gap); a failing
  in-denominator label SHALL render `failing` regardless of fraction.
- **Direct/indirect caveat + `allow_indirect`:** the direct/indirect distinction
  SHALL be surfaced as a caveat (`~` marker + hover provenance), not a distinct
  state color; a global `allow_indirect` (default true) SHALL control whether
  indirect coverage credits the state.
- **Per-relationship status word:** dimension labels SHALL derive from a single
  per-relationship map (`Implements`→Implemented, `Verifies`→Tested,
  `Yields`→Passing, `Validates`→UAT Covered, validation-verified→UAT Passed),
  configurable, used by all surfaces.
- **`expects_implementation`:** a per-status flag (default derived from role)
  SHALL declare whether a status expects implementation; when it does not, absent
  implementation SHALL be neither flagged, red, nor counted against aggregate
  implemented coverage; all surfaces SHALL resolve it through a single helper; it
  SHALL replace the coverage roles of `is_excluded_from_coverage`.

`elspais fix` re-hashes affected spec files; `spec/_generated/*` committed.

## Worked examples

- **DIARY-GUI-join-study-screen (0 implemented, status Active):** Implemented
  `missing` → **red** (Active expects it; in-scope gap). Tested & Passing
  denominators empty → grey **`missing`** neutral (no more misleading yellow).
- **1/5 implemented, that one tested + passing (all direct):** Implemented
  **yellow** `partial` (1/5); Tested **green** `full` (1/1 of implemented);
  Passing **green** `full` (1/1 of tested). combined_bucket **yellow**.
- **Same, but the one assertion covered only via REFINES conduction:** with
  `allow_indirect=true`, Tested `full` with `~`, hover "100% indirect"; with
  `allow_indirect=false`, Tested `missing` (direct 0), hover "100% indirect, not
  credited".
- **Draft req, 2/5 implemented, those tested + passing, `expects_implementation`
  unset (role default false):** Implemented gap grey (not red); the 2 built
  assertions show real Tested/Passing coverage. Excluded from project
  implemented-% denominator.

## Scope boundaries (YAGNI)

- No `RollupMetrics` structural change; no change to `direct`/`indirect` metrics
  or REFINES conduction — projection/display layer only.
- No change to analysis scoring, default-hidden filtering, or status sorting —
  those stay on the role system.
- No new per-level implementation flag; PRD-via-refinement is handled by REFINES
  conduction.
- `allow_indirect` is global for now.
- Not touching Graph / GraphTrace / GraphBuilder structure or encapsulation.

## Affected modules

- `config/schema.py` — per-status `expects_implementation` (`[status.*]`);
  `[coverage] allow_indirect`; per-relationship status-word map; `missing`
  severity (neutral default), retire the split `full_direct`/`full_indirect`
  severity keys into `full`.
- `config/__init__.py` — `status_expects_implementation` resolver.
- `config/status_roles.py` — role stays as default source; coverage-exclusion
  callers migrate to the resolver.
- `graph/aggregation.py` — relative denominators; `TIER_TO_BUCKET` identity over
  the unified set; rollup inclusion via the resolver.
- `graph/metrics.py` — tier naming aligned to the unified vocabulary (`missing`
  replaces `none`; `full` replaces the direct/indirect split at the state level).
- `html/generator.py` — `compute_coverage_tiers` /
  `compute_assertion_coverage_states` relative denominators + unified states;
  `_DIMENSION_LABELS` re-keyed to the per-relationship map; hover provenance.
- `graph/health.py`, `commands/gaps.py` — gap definitions realigned.
- `html/theme.toml` — unified state catalog (`full`/`partial`/`failing`/
  `missing`), grey `missing`; Legend updated.
- `commands/trace.py`, `mcp/server.py` — label/vocabulary alignment.
- `spec/dev-graph-core.md` — new/revised REQ-d00258 sub-requirements.
- Docs (`docs/cli/*.md`, `docs/configuration.md`), `commands/init.py` template,
  shell completion — surface the flags and vocabulary.
