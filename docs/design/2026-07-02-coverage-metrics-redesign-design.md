# Coverage Metrics & Reporting Redesign — Design

**Date:** 2026-07-02
**Status:** Approved (pending final spec review)
**Branch:** CUR-1568-junit-path (follow-on work; new branch per phase as appropriate)

## Context

An audit of the coverage/verification roll-up (spec + implementation + a live
federated project) found that the graph-layer model (REQ-d00069, REQ-d00254) is
implemented faithfully, but the reporting surfaces disagree with each other and
with reader intuition:

1. **Footing asymmetry.** Trace and summary report `implemented` on the
   generous footing (`indirect`) but `tested`/`verified`/`passing` on the
   strict footing (`direct`) — `summary.py:169-171`, `trace.py:272-278`. A
   requirement fully covered by whole-requirement passing tests reads
   `Verified 0/5 (0%)`.
2. **Divergent summaries.** CLI `summary` (assertion-fraction sums, three
   dimensions, integration-aware) and MCP `get_project_summary` →
   `count_by_coverage` (requirement-level buckets on `implemented` only,
   integration-blind) answer the same question differently.
3. **Dead color mapping.** The viewer nav-tree coverage filter buckets on
   color *strings* and maps `yellow-green` (the `full-indirect` / UAT-info
   color) to "none" (`routes_api.py:616-621`). `SEVERITY_TO_COLOR` is
   hard-coded (`generator.py:112-117`).
4. **Structurally-zero column.** `code_tested.direct` is always 0
   (`annotators.py:810` — per-test line attribution unimplemented), so the
   trace `Code Tested` cell renders `0/76 (0%)` beside `lcov 100%`.
5. **Silent gap-listing threshold.** Assertions with conducted fractional
   coverage (0 < f < 1) count toward summary percentages but appear in gap
   surfaces indistinguishable from zero-evidence assertions.
6. **Spec contradictions.** REQ-d00069-I vs REQ-p00014-K (what saturates
   INSTANCE coverage); REQ-d00084-D/d00086-B vs REQ-d00252-D/F (whether
   inherited coverage counts as "implemented"); the strict-vs-indirect
   two-footing design is implied but never stated; viewer badges/filters have
   no normative spec; "Validated" collides with `Validates:`/UAT.
7. **Journey cards lag requirement cards.** USER_JOURNEY viewer cards render
   step VERIFIED/PASSED badges as non-clickable spans and always expand the
   verifying-tests list (`_card-stack.js.j2:1099-1148`); REQUIREMENT cards use
   clickable badge buttons with collapsed link panels.
8. **dart_prescan unbalanced spans.** Dart triple-quoted (`'''`) and raw
   (`r'…'`) strings defeat the per-line bracket scanner
   (`prescan.py:_iter_code_brackets`), producing "could not balance" warnings
   and inverted spans (`parse_end_line < parse_line`).

Not a defect (resolved during analysis): assertion-reference separators are
config-driven and work for both REQUIREMENT and USER_JOURNEY parsing. The
observed "Dart verified-crediting gap" in hht_diary was a config/data mismatch
(`/A` refs under a `-` separator), fixed on the hht side by configuration and
data normalization. **Decision: elspais will not attempt to recognize
off-config suffix syntax, and no assertion-suffix health check is added**
(declined to avoid complicating the parser around wrong syntax).

## 1. Semantic model

### 1.1 Footing policy: generous primary, strict as tier

Every reporting surface's headline count answers "does evidence exist?" using
**all** evidence: direct (assertion-targeted), blanket (whole-requirement),
inferred (req→req), conducted (REFINES), and inherited (INSTANCE, INTEGRATES).
Numerically this is the existing `CoverageDimension.indirect` side.

Precision is expressed as the existing **tier** (`full-direct`,
`full-indirect`, `partial`, `none`, `failing`), not as a second number:

- Trace/text: indirect-only coverage carries a `~` marker — `5/5 (100%) ~`;
  fully-direct coverage renders unmarked — `3/5 (60%)`.
- Viewer: full-direct badge solid; indirect-only badge outlined/pale
  (existing tier → severity → color pipeline).
- The strict count remains available in detail surfaces (hover/tooltips,
  MCP per-label payloads); it is no longer any surface's headline.

This makes `implemented` (already generous) consistent with every other
dimension instead of the current asymmetry.

### 1.2 Display vocabulary

Five display words, used identically by trace, summary, viewer, and MCP:

| Display word | Dimension | Meaning |
|---|---|---|
| Implemented | `implemented` | code evidence: `Implements:` refs, conducted, inherited (INSTANCE/INTEGRATES) |
| Tested | `tested` | test evidence exists (`Verifies:` refs), regardless of results |
| Passing | `tested_and_passing` (verified ∪ lcov_tested) | tested evidence whose results pass, no failures |
| UAT Covered | `uat_coverage` | journey `Validates:` coverage |
| UAT Passed | `uat_verified` | journey verification verdicts |

The word **"Validated" is retired** as a test-coverage term (fatal collision
with `Validates:`/UAT). Internal dimension names are unchanged; this is a
display contract.

## 2. Reporting surfaces

### 2.1 One aggregation module

A single aggregation (in the graph layer, beside `annotators.py`/`metrics.py`)
computes, from each node's `RollupMetrics`:

- per-level assertion-fraction sums for the five display dimensions
  (integration-aware, as CLI summary does today), and
- requirement-level tier buckets (full / partial / none / failing) per
  dimension.

CLI `summary`, MCP `get_project_summary`, and the viewer all read this one
module. `count_by_coverage` remains as a thin delegate (MCP API
compatibility). The three headline numbers share the §1.1 footing.

### 2.2 Trace command

- All coverage columns use §1.1 footing with the `~` indirect marker.
- The `Code Tested` direct-side rendering (`0/N`) is removed from default
  presets. Line coverage surfaces once, as the existing `lcov N%` cell.
  Where per-test attribution exists (§3), `Code Tested` renders real
  direct numbers.
- The label-range formatter renders empty coverage as `0/N (0%)` (same as
  the non-label path), never bare `-`.
- CUR-1557 selective-run semantics (`—` not-run, `(baseline)` carried) are
  unchanged.

### 2.3 Viewer colors, Legend, filter

- `SEVERITY_TO_COLOR` (hard-coded dict) is replaced by theme.toml
  LegendCatalog entries — one named entry per severity (e.g.
  `coverage.ok`, `coverage.info`, `coverage.warning`, `coverage.error`)
  with `color_key` and description. Colors become purely presentational
  and user-definable, like status colors.
- The coverage tier states appear in the viewer Legend (auto-rendered from
  the catalog, as other categories are).
- The nav-tree coverage filter buckets on **tier/severity semantics**, never
  color strings: full = any full tier (`full-direct` or `full-indirect`),
  partial = `partial`, none = `none`, with the existing `has_failures`
  overlay. `combined_color` remains worst-of-dimensions (triage signal), and
  the row tooltip lists per-dimension states so a red row explains itself.
- Config keys under `[rules.coverage.<dim>]` (tier → severity) are unchanged.

### 2.4 Gap surfaces: partial conduction becomes visible

The "covered" threshold stays ≈100% (`≥ 1.0 − 1e-9`). Gap surfaces annotate
partially-conducted assertions instead of listing them bare, reading the
already-stored `rollup_metrics.<dim>.indirect_pct_by_label`:

- MCP `get_test_coverage` / `get_uncovered_assertions`: uncovered entries gain
  `fraction` and `via` fields (`server.py:3416-3432`, `3813-3823`).
- `gaps` command output renders `A — 40% via refines-conduction`
  (`gaps.py:164-185`).

No new storage.

## 3. Per-test line attribution for Python (no regression on dogfooding)

Python is the original supported language and this repo dogfoods itself;
`code_tested.direct` must be real for Python rather than structurally zero.

- Ingest coverage.py **dynamic contexts** (pytest-cov `--cov-context=test`):
  when the configured coverage file carries contexts (coverage.py JSON/SQLite
  export), map each context's test id to its TEST node and attribute covered
  implementation lines per test → populates `code_tested.direct`.
- Target config: reuse the existing `coverage` key on
  `[[scanning.test.targets]]` with format auto-detection (lcov text vs
  coverage.py JSON export; contexts used when present in the JSON).
- Languages whose standard tooling emits only aggregate coverage (Dart/Flutter
  lcov, JS, Go) keep aggregate crediting; their surfaces render the indirect
  side with the `~` marker rather than a misleading direct 0 (§2.2).
- elspais's own CI/dev test targets adopt `--cov-context=test` so the repo
  exercises the direct path end-to-end.

## 4. Viewer journey-card interaction parity

USER_JOURNEY cards adopt the REQUIREMENT card interaction pattern
(`_card-stack.js.j2`):

- Step VERIFIED/PASSED badges become clickable **buttons** (like assertion
  badge buttons, lines 531-548) that toggle a collapsed panel.
- The verifying-tests list (currently always-expanded inline, lines
  1134-1148) moves inside that collapsed-by-default panel, showing the same
  test/result rows.
- Whole-journey Verifies/Yields link lists are collapsed by default,
  identical to requirement cards.

## 5. dart_prescan lexer fix (subagent task)

Upgrade the bracket scanner to a small stateful cross-line lexer:

- Track Dart multiline strings (`'''`, `"""`) across lines.
- Honor raw-string prefix `r` (backslash is literal, not an escape).
- Optionally skip `/* … */` block comments.
- Guard emitted spans: `parse_end_line ≥ parse_line`.

Acceptance: the two real failing files
(`seed_config_test.dart` — multiline strings; `canonical_json_test.dart` —
raw strings) prescan cleanly with correct spans; no "could not balance"
warning on the hht_diary corpus.

## 6. Spec reconciliation (spec/ edits)

1. **REQ-d00069-I → align to REQ-p00014-K**: instance coverage saturates via
   all coverage edge kinds (IMPLEMENTS/VERIFIES/VALIDATES), not
   `Implements:` only.
2. **REQ-d00084-D, REQ-d00086-B**: "Implemented" includes conducted and
   inherited (INSTANCE/INTEGRATES) coverage; adopt §1.2 vocabulary
   (Tested/Passing replace Validated/Passing wording).
3. **REQ-d00069**: add an explicit assertion stating the two-footing design —
   strict (direct) vs generous (indirect) — and that reporting surfaces
   headline the generous footing with precision expressed as tiers (§1.1).
4. **New DEV requirement** (dev-graph-core.md or dev-traceview-review.md):
   normative viewer badge/filter/Legend semantics — tier→severity→named
   catalog color pipeline, filter buckets on tiers, journey-card interaction
   parity (§2.3, §4).
5. **Journeys**: replace stale `elspais analyze coverage` invocations with the
   current command names.

## Out of scope

- Assertion-suffix mismatch health check (**declined** — no parser
  speculation about wrong syntax).
- Multi-separator/alternate-syntax parsing.
- hht_diary data normalization (journeys to `/` style, `multi_separator`) —
  already handled by the user in the hht worktree.
- Per-test line attribution for non-Python languages (future work, per-language
  as tooling allows).

## Testing

- **Unit**: aggregation module (fraction sums + tier buckets) against the
  canonical graph fixture; tier/`~`-marker rendering; label-range formatter
  `0/N` case; coverage-contexts ingestion with a small contexts-bearing
  coverage export fixture; dart_prescan lexer against reduced multiline/raw
  string cases.
- **Consistency**: a test asserting CLI summary and MCP `get_project_summary`
  emit identical numbers for the canonical fixture (guards §2.1 permanently).
- **E2E**: extend the appropriate existing fixture files (per repo
  conventions: `test_e2e_standard` for trace/summary rendering;
  `test_e2e_global` for self-dogfooding coverage contexts; browser-marked
  Playwright checks for filter buckets, Legend entries, and journey-card
  collapse/expand).
- All tests reference requirements (including the new/updated ones from §6).

## Decision log

| # | Decision | Outcome |
|---|---|---|
| D1 | Footing: generous primary, strict as tier | Approved |
| D2 | Vocabulary: Implemented/Tested/Passing/UAT Covered/UAT Passed | Approved |
| D3 | Assertion-suffix health check | **Declined** (config was the fix; keep parser simple) |
| D4 | Code Tested column + Python per-test attribution | Approved; Python contexts ingestion **in scope** (no dogfood regression) |
| D5 | Colors as named catalog entries, Legend, semantic filter | Approved |
| D6 | One aggregation for CLI/MCP/viewer | Approved |
| D7 | Gap surfaces annotate partial conduction | Approved (display-only) |
| D8 | Spec reconciliation edits | Approved |
| D9 | dart_prescan lexer fix | Approved (subagent task in this plan) |
| D10 | hht_diary separator/data normalization | User-handled, done |
| D11 | Journey-card interaction parity | Approved |
