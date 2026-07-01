# CUR-1557 — Per-PR target selectivity with faithful carry-forward

**Status:** Approved design (2026-07-01)
**Linear:** [CUR-1557](https://linear.app/cure-hht-diary/issue/CUR-1557) — related: CUR-1556 (centralized Dart test execution), CUR-1533 (Dart result→test matcher)
**Repos:** elspais (Part 1, this worktree) + hht_diary (Part 2, sibling worktree)

## Problem

CUR-1556 centralized Dart/Flutter test execution behind a single `elspais checks --run-tests`
invocation that renders the verified-coverage traceability matrix. `--run-tests` is
**all-or-nothing** — the central CI job runs **all 17** `[[scanning.test.targets]]` on **every PR**,
including full `flutter test --machine --coverage` for packages a PR never touched. This is slow.

We want the default PR CI to run **only the targets whose sources changed** and treat the rest as
**carried forward** from the last known results — while remaining correct (a target that was failing
still fails; nothing gets a free pass for being skipped). A full regression is still available (and is
what runs when promoting a build qa→uat).

## Division of labor

- **elspais = mechanism only.** A target *selector*, plus faithful ingestion and distinct rendering of
  results it did not run this invocation.
- **CI (hht_diary) = policy.** Chooses the diff base, computes the changed target set, seeds prior
  results into the workspace, and runs full regression on promotion.

## Key design decisions (settled during brainstorming)

1. **Selector, not git-mapping, in elspais.** CI decides *which* targets to run and passes them
   explicitly. elspais does not map git diffs to targets.
2. **Carry-forward is faithful — no free pass.** Freshness (ran-this-invocation vs. carried) is
   **orthogonal** to verdict (pass/fail). A carried *failing* result still shows failing and still
   gates `checks`. Only a target with **no data at all** is neutral.
3. **No baselines in the repo.** elspais never trusts committed or externally-authored results.
   Baselines come only from this CI's own prior runs, materialized into the workspace by CI before
   elspais runs.
4. **CI persistence via one canonical image per PR (GHCR).** Every PR commit produces a *single*
   canonical image carrying **all** targets' results at stable paths — fresh for changed targets,
   copied from the ancestor image for skipped ones. The image's *existence* is the completeness marker.

---

## Part 1 — elspais feature (this worktree)

### 1a. Target selector on `checks --run-tests`

- Add `--targets a,b,c` (comma-separated) to `ChecksArgs` (`src/elspais/commands/args.py:24`).
- It controls **execution only**. elspais still *ingests* every target's on-disk result/coverage
  files during the graph build (`src/elspais/graph/factory.py:720`), so unselected targets carry
  forward from whatever CI seeded into the workspace.
- `run_configured_targets` (`src/elspais/commands/test_runner.py:35`) filters iteration to the named
  subset. Unknown target names are an error (exit 2), listing valid names.
- The all-or-nothing "no target has a command" guard (`src/elspais/commands/health.py:3011`) is
  re-scoped to the **selected** subset.
- **No `--targets` = run all** → this *is* the full-regression / qa→uat path. No separate flag.

### 1b. Freshness provenance (fresh vs. carried vs. no-data)

- Thread the run set into the build. Tag each RESULT node with a freshness flag
  (`carried=True/False`), extending the existing per-RESULT `match` metadata
  (`src/elspais/graph/metrics.py:134`).
- **`CoverageDimension.tier` stays verdict-only** (`src/elspais/graph/metrics.py:122` —
  `failing / full-direct / full-indirect / partial / none`). Freshness rides as a **separate flag**,
  never folded into `tier`. This is what keeps carry-forward honest: a carried failing result keeps
  `tier=failing` and gates exactly like a fresh one.
- Three render outcomes per target/requirement:
  - **fresh** (ran this invocation) → normal, e.g. `4/4 100%`.
  - **carried** (not run this invocation, results present on disk) → `4/4 100% (baseline)` — real
    verdict, gates normally.
  - **no-data** (not run, *no* results on disk — only a brand-new target with no image history) →
    `—` / "not run", **non-gating** (unknown ≠ failing). This is CUR-1557's "skipped ≠ 0%" case and is
    rare, since a new/changed target is in the run set anyway.

### 1c. Stdout-channel reporters must ingest carried results from a file

- `flutter-machine` is a **stdout-channel** reporter (`src/elspais/graph/parsers/results/registry.py:42`):
  today elspais captures its output from the runner's stdout in-memory
  (`src/elspais/commands/health.py:3022`), not necessarily as a file.
- A **skipped** target produces no stdout, so its carried results must be ingested **from disk**.
  Requirement: for a target *not* in the run set, elspais ingests from the target's on-disk
  `results`/`coverage` files **even for stdout-channel reporters**. Correspondingly, the CI runner must
  materialize `machine.jsonl` to the target's `results` path so it can be baked into / restored from
  the canonical image.

### 1d. Renderer + legend

- Update `src/elspais/commands/trace.py` (`_get_node_data:205`, `_fmt_count:255`,
  `_column_headers:345`, and all `format_*` renderers) to emit the `(baseline)` marker and the `—`
  no-data glyph, plus a legend line so a skipped target never reads as a regression.
- **Text output is the reference implementation**; markdown/csv/html/json follow it.

### 1e. Tests + spec (elspais)

- New REQ/assertions covering the selector and the carried/no-data states (all tests reference a
  requirement).
- Regression tests (written by a sub-agent) covering:
  - subset execution runs only named targets;
  - carried **passing** result renders `(baseline)` and does not regress;
  - carried **failing** result still fails and **gates**;
  - no-data non-run target renders `—` and does not gate;
  - stdout-channel (`flutter-machine`) carried result ingested from file;
  - no-selector full run rewrites all results.

---

## Part 2 — hht_diary CI wiring (sibling worktree)

### 2a. Single canonical image per PR, always complete

Regardless of how CI splits into jobs/workflows, one canonical image is produced per PR commit,
carrying **all** targets' results at stable paths (e.g. `/opt/elspais/results/<target>/{machine.jsonl,lcov.info}`).
It is assembled as *fresh results for changed targets* + *carried results copied out of the ancestor
image for skipped targets*. Every canonical image is therefore a full audit snapshot **and** the
carry-forward source for its descendants.

### 2b. Per-run flow

1. Pull the ancestor canonical image — the previous PR-push commit's image if available, else main's
   post-merge image (walk ancestry to the nearest commit that has a canonical image).
2. Extract its results into the workspace → seeds **every** target.
3. Diff against that ancestor's commit → the changed target set.
4. Run only the changed targets (`elspais checks --run-tests --targets <changed>`); fresh output
   overwrites the seeded files.
5. elspais ingests: changed = fresh, rest = carried; renders the matrix; upserts the PR comment.
6. Build + push the new canonical image (fresh + carried merged) tagged by this commit SHA.

### 2c. Completeness = image existence

Step 6 pushes an image only when the run finishes, so **an image's existence is the completeness
marker**. An interrupted run pushes no image for that commit; the next push's ancestor walk skips it
and diffs against the nearest ancestor that *does* have an image (ultimately main). No separate
"interrupted?" bookkeeping.

### 2d. qa→uat promotion = full regression

Promotion runs `elspais checks --run-tests` with **no `--targets`** → every target runs live →
rewrites the whole canonical image.

### 2e. Verification items (confirm against real hht_diary CI)

- **Does the pipeline persist per-push canonical images in GHCR under a commit-addressable tag with
  enough retention?** Correctness does not depend on it (missing → fall back to diffing main, a safe
  superset), but the PR-branch *fast path* does. If missing, add tag+push per push.
- Confirm the current build persists results at a stable path; if not, add a copy step (Part 2a).
- Confirm the runner materializes `machine.jsonl` as a file (needed by Part 1c).

## Out of scope

- Any change to the verified-coverage matching itself (that was CUR-1533).
- elspais mapping git diffs to targets (CI owns target selection).

## Correctness invariants

- A carried failing result fails exactly as a fresh one would (no free pass for skipped targets).
- Skipping never *fabricates* coverage: a target with no results renders `—`, not `0%` and not
  `100%`.
- The system self-heals: any missing/incomplete ancestor image falls back to diffing main, a superset
  of the true change set.
