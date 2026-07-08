# Journey Step Result Matching + `<journey>/N` Normalization — Design

**Date:** 2026-07-08
**Branch:** CUR-1568-junit-path (elspais)
**Status:** Spec for a fresh implementing agent. Read this whole document first; it
assumes no prior conversation context.
**Companion repo:** hht_diary (`~/cure-hht/hht_diary-worktrees/CUR-1568-oq-jny`) —
some changes land there, called out explicitly as **[HHT]**.

---

## 1. Problem

In the elspais viewer, a journey card's per-step **Result** panel shows *every*
step's result under *each* step. Concretely, for `JNY-ENROLL-01` (5 steps), clicking
the Result badge on **step 1** lists 5 result rows — the results for steps 1–5 —
each rendered as `link-redeem.spec.ts:1`. The rows are real, distinct test
outcomes (durations differ), but they are **mis-attributed**: step 1 should show
only step 1's result.

Two secondary defects fall out of the same area:
- The result rows link to the **test source file** (`…/link-redeem.spec.ts:1`),
  not the **results artifact** (`…/e2e/results/junit.xml`) that recorded them.
- The step-addressing convention is `<journey>/step-N` (e.g. `JNY-ENROLL-01/step-1`),
  inconsistent with requirement/assertion addressing `<requirement>/A`.

## 2. How it works today (grounded map — read before changing anything)

Node model: `USER_JOURNEY` → (STRUCTURES) → `STEP` children; a `STEP` id is
`<journey_id>/step-<n>` (`graph/GraphNode.py:108-114`, `make_step_id`). Verification
chain the annotator reads: `STEP --VERIFIES--> TEST --YIELDS--> RESULT`
(`graph/annotators.py:1164-1174`, `_node_verifying_status`).

**Step → VERIFIES → TEST edges are name-based already.** They come from the *test
source file's* `// Verifies: JNY-…/step-N` comment (NOT the JUnit XML), resolved to
the STEP node by **exact-id dict lookup**:
- The reference transformer extracts journey/step refs via `JOURNEY_REF_PATTERN`
  (`graph/parsers/lark/transformers/reference.py:412-432`; pattern at
  `graph/parsers/patterns.py:39-42`, currently
  `r"JNY-[A-Za-z0-9][A-Za-z0-9-]*-\d+(?:/step-\d+)?"`).
- `_add_test_ref` queues a VERIFIES pending-link with the TEST as source
  (`graph/builder.py:3581-3582`).
- `build()` resolves the target by exact-id lookup `self._nodes.get(target_id)`
  (`graph/builder.py:4053-4055`) and wires `target.link(source, VERIFIES)`
  (`4171-4173`) → edge `STEP --VERIFIES--> TEST`. No fuzzy match, no step→journey
  fallback; an unmatched ref becomes a broken reference (`4187-4195`).
- A journey-level `// Verifies: JNY-ENROLL-01` (no `/step`) instead wires
  `JOURNEY --VERIFIES--> TEST`; the annotator credits such whole-journey tests to
  *every* step (`annotators.py:1197-1205`). (The hht `link-redeem.spec.ts` uses
  per-step comments on 5 `test()` blocks, so per-step edges DO exist here.)

**RESULT → TEST binding is source-location only — this is the conflation.** JUnit
results are wired by `(source_file, line)`:
- `graph/builder.py:4207-4243` (`_pending_source_result_links`): if a single TEST
  exists at `(source_file, line)` → `YIELDS` + `match_scope="test"`; **else fall
  back to linking EVERY test sharing the file** → `match_scope="file"`.
- The Playwright JUnit `<testcase>` carries `file="…/link-redeem.spec.ts"` but **no
  `line`** attribute (`graph/parsers/results/junit_xml.py:173-179`), so `line` is
  `None`, the precise match can't be attempted, and all 5 results fall to file
  scope — attaching to all 5 per-step TEST nodes. Each step then shows all 5.
- The testcase *name* embeds the exact step id (`… › JNY-ENROLL-01/step-1: …`) but
  is **never consulted** for binding; the JUnit ref extraction is REQ-only and its
  output is discarded (`junit_xml.py:182,254-273`; `_add_test_result` never reads
  `verifies`).

**Results-file path is discarded.** At parse time the results-file path is
`context.file_path` (`junit_xml.py:227`), but when a `file` attr is present it is
overwritten: `result_source = file_attr or source_path` (`junit_xml.py:173-174,195`),
so the RESULT node's `source_path`/`source_file` become the *test* file and the
`.xml` path is dropped. RESULT `_content` fields are exactly: `status, test_id,
duration, name, classname, message, parse_line, parse_end_line, source_path,
source_file, match, line, root_line, root_file, carried, target`
(`graph/builder.py:3608-3632`) — **no results-file field**.

**`parse_line=1` line-detection miss.** `claim_and_parse` builds a
`(classname,name) → line` index by scanning raw lines for `<testcase ` and
extracting attrs (`junit_xml.py:226-244`), else falls back to line 1. Even though
the hht junit.xml is 13 lines with one `<testcase>` per line, every result came
back `parse_line=1` — the index lookup misses (likely the `›`/`:`/`/` in the name
or attribute-order handling in `_attr_value`). So the existing per-testcase line is
not even captured today.

## 3. The fix (four coordinated changes)

### Change A — Per-step RESULT→TEST binding via the step id in the testcase name

**Goal:** a result whose testcase name embeds `<journey>/N` binds to the specific
TEST that verifies *that step*, not to every test in the file.

**Approach (elspais).** Add a step-id-aware binding path that runs **before** the
file-scope fallback in the source-result resolver (`graph/builder.py:4207-4243`):

1. Extract the step id from the result's `name` (and/or `classname`) using the
   journey-ref pattern (the same `JOURNEY_REF_PATTERN`, post-normalization it
   matches `<journey>/N`). The hht names look like
   `JNY-ENROLL-01: Joining the Study › JNY-ENROLL-01/1: reach …` — take the
   `<journey>/N` token.
2. Resolve it to the STEP node by exact-id lookup (same mechanism as the VERIFIES
   resolver, `builder.py:4055`).
3. From that STEP, take its outgoing `VERIFIES` targets (the TEST nodes it
   verifies) filtered to those whose FILE matches the result's `source_file`.
   Bind the RESULT to those TEST(s) via `YIELDS` and stamp a new
   `match_scope="step"`.
4. Only if no step id is present (or it doesn't resolve) fall through to the
   existing `(source_file,line)` → file-scope logic unchanged.

This keeps the existing `RESULT→YIELDS→TEST` convention (per the user's explicit
choice — do NOT attach RESULT directly to STEP); it just makes the binding precise
using the step identity already present in the data. It needs **no `line` attr**.

Precedence: step-scope > test-scope(location) > file-scope. Update the annotator's
`source_file_index` / crediting only if it special-cases `match_scope` (check
`annotators.py:1284-1296,1507-1513`, which currently branch on
`match_scope != "test"`); ensure `match_scope="step"` is treated like `"test"`
(a precise, non-file-fanout binding) wherever `"file"` vs `"test"` is
distinguished.

**Acceptance:** on the hht repo, `JNY-ENROLL-01` step 1's Result panel shows
exactly one result (its own), step 2 its own, etc.; no step shows another step's
result.

### Change B — Normalize step addressing `<journey>/step-N` → `<journey>/N`

Mirror `<requirement>/A`. Cut over cleanly (no dual `/step-N` + `/N` support);
update fixtures, tests, and **[HHT]** sources/docs in tandem. Sites (from the map):

- **Format:** `graph/GraphNode.py:114` `make_step_id` → `f"{journey_id}/{n}"`.
- **Label:** `graph/builder.py:3461` `"label": f"step-{step['n']}"` → the step
  number as a string (e.g. `str(step['n'])`). (Decide: keep `label` as the bare
  number to match the id suffix; the viewer strip below becomes a no-op.)
- **Parse pattern:** `graph/parsers/patterns.py:40` `JOURNEY_REF_PATTERN` →
  `r"JNY-[A-Za-z0-9][A-Za-z0-9-]*-\d+(?:/\d+)?"` (accept `/N`, drop `/step-`).
- **Rename slice:** `graph/builder.py:996-1011` (journey-rename cascade) — the
  `step_suffix = old_step_id[len(old_id):]` slice still works (it slices on
  `old_id`), but verify it produces `/N` and re-forms correctly.
- **Viewer strip:** `html/templates/partials/js/_card-stack.js.j2:1198`
  `(step.label||'').replace(/^step-/,'')` → with a bare-number label this is a
  no-op; simplify to use the label directly.
- **Label consumers:** `graph/annotators.py:1203,1209` (`failing_steps` appends
  `label`) and `server/routes_api.py:258-269` — now emit/consume `N` not `step-N`.
- **Grammar doc comment:** `graph/parsers/lark/grammars/reference.lark:76`.
- **The step *number* source is unchanged:** `_STEP_LINE_RE`
  (`lark/transformers/requirement.py:61`) still reads the markdown numbered-list
  item; only the id/label *format* changes.

**[HHT]** `link-redeem.spec.ts` (and any other journey e2e specs): update the 5
`// Verifies: JNY-ENROLL-01/step-N` comments and the `test('JNY-ENROLL-01/step-N: …')`
titles to `…/N`. Update `docs/e2e/` references. (The user owns these edits.)

### Change C — Results-file provenance

Thread the results-file path (and, once Change D lands, the per-testcase line)
onto the RESULT node, and link the viewer there.

- **Parser:** in `junit_xml.py claim_and_parse` (`227`) the results-file path is
  `context.file_path`; carry it (and the `<testcase>` line) as new ParsedContent
  keys, e.g. `result_file` + `result_line`. Do the same in `pytest_json.py`
  (results-file = `context.file_path`, already the `source_path` it writes — but
  set the dedicated field) and `flutter_machine.py` (stdout stream → no file;
  leave `result_file` empty/None). Do NOT change the existing `source_path`
  (it must remain the test file for the source-binding match key).
- **Factory:** thread the new keys through `graph/factory.py:129-146`
  (`_ingest_target_results`) into `parsed_data`.
- **RESULT node:** persist `result_file`/`result_line` in the `_content` dict
  (`graph/builder.py:3608-3632`).
- **Serializer:** expose them in `_serialize_test_info`'s per-result dicts
  (`mcp/server.py`, the `results.append({...})` block ~200-213) as e.g.
  `result_file` / `result_line` (falling back to the current `file`/`line` when
  absent, so non-junit sources still render).
- **Viewer:** in the journey-step **Results** panel
  (`_card-stack.js.j2`, the `journey-step-results` rendering added in commit
  3ce028c1 — the `stepResults.forEach` block), link each result to
  `result_file:result_line` when present, else the current behavior. Same for the
  assertion-level results rendering if it shows result rows.

Caveat to document: the hht junit.xml is **gitignored/ephemeral** (~1.5 KB), so the
link resolves locally but is not a permanent record; persistence "for posterity" is
explicitly **out of scope** (see §6).

### Change D — Fix JUnit per-testcase line detection

`claim_and_parse` (`junit_xml.py:226-244`) currently returns `parse_line=1` for
every result even when the XML has one `<testcase>` per line. Fix the
`(classname,name)`-keyed line index so it matches (debug `_attr_value` against the
real names containing `›`, `:`, `/`; likely a naive attr-regex or multi-line
`<testcase …>` open tag). After the fix, `result_line` (Change C) lands on the
correct `<testcase>` line, so the provenance link is line-precise for
pretty-printed XML.

**[HHT] companion:** add a pretty-print step to the Playwright JUnit output in the
test runner (reporter config or a post-process in `tools/uat/`). It is safe
(elspais parses via ElementTree, whitespace-insensitive), costs ~6% size, and gives
each `<testcase>` its own line so Change D's `result_line` is meaningful. This is an
hht-side change; elspais must simply not regress on either minified or pretty XML.

## 4. Affected elspais files (summary)

- `graph/builder.py` — Change A (new step-scope binding in the source-result
  resolver ~4207-4243), Change B (`3461` label, `996-1011` rename), Change C
  (RESULT `_content` fields ~3608-3632).
- `graph/GraphNode.py:114` — Change B (`make_step_id`).
- `graph/parsers/patterns.py:40` — Change B (`JOURNEY_REF_PATTERN`).
- `graph/parsers/results/junit_xml.py` — Change C (thread `result_file`/`result_line`),
  Change D (line-detection fix).
- `graph/parsers/results/pytest_json.py`, `flutter_machine.py` — Change C.
- `graph/factory.py:129-146` — Change C (thread new keys).
- `graph/annotators.py:1203,1209,1284-1296,1507-1513` — Change A (`match_scope="step"`
  treated as precise), Change B (label).
- `mcp/server.py` (`_serialize_test_info` ~194-221) — Change C (expose fields).
- `server/routes_api.py:258-269` — Change B (step label/counts).
- `html/templates/partials/js/_card-stack.js.j2:1198` + the `journey-step-results`
  block — Change B (label strip), Change C (results-file link).

## 5. Tests

Unit/integration (update to `<journey>/N`, add step-scope binding coverage):
- `tests/graph/test_journey_steps.py` — step ids now `<journey>/N`.
- `tests/graph/test_journey_verification.py` — per-step crediting.
- `tests/graph/parsers/test_parsers_patterns.py` — `JOURNEY_REF_PATTERN` accepts
  `/N`, rejects/ignores `/step-N` (post-cutover).
- Fixtures `tests/fixtures/journey-uat/*` (`untested-step/`, `steps-all-pass/`,
  `one-step-fails/`): update `.elspais.toml`/`results.xml`/`tests/test_stepN.py`
  refs to `<journey>/N`. **Add** a fixture (or extend one) that reproduces the
  conflation: multiple per-step testcases in one results file with no `line` attr,
  asserting each step's results bind only to that step (`match_scope="step"`) — the
  regression guard for Change A.
- New parser test: `result_file`/`result_line` populated from junit (Change C),
  and correct per-testcase line after Change D.
- New/updated test: `_serialize_test_info` exposes `result_file`/`result_line`.

Browser (`tests/e2e/test_viewer_browser.py`, `@pytest.mark.browser`):
- `test_d00256_D_journey_fail_verdict_badge` (line 444) hard-asserts `step-` labels:
  `failing_steps == ['step-2']` (447), `"step-2" in props` (465-467), rendered
  `step-2` (483-485). Update all to the `N` form (`'2'`).
- The `test_d00256_journey_step_*` tests (badge suppression, VER→tests / Result→results
  toggles, single-link) — verify still green; extend one to assert each step's
  Result panel shows only that step's result (Change A end-to-end) and that the
  result links to the results file (Change C).

**Test authorship:** per repo convention (CLAUDE.md), dispatch a sub-agent to write
tests. Tests must reference the governing requirement (§7).

## 6. Verification

- Build the hht graph via the worktree venv
  (`~/cure-hht/hht_diary-worktrees/CUR-1568-oq-jny/.venv/bin/python`, editable-bound
  to this elspais worktree) and confirm: each `JNY-ENROLL-01` step's verifying
  test holds only that step's RESULT (`match_scope="step"`), not all 5.
- Live viewer (`.venv/bin/elspais viewer --server --port 5001` from the hht repo):
  step 1's Result panel shows one result; the row links to
  `apps/daily-diary/clinical_diary/e2e/results/junit.xml` (line-precise once the hht
  pretty-XML + Change D are in).
- Full suite: `python -m pytest` (default) and the journey browser tests
  (`python -m pytest tests/e2e/test_viewer_browser.py -m browser -k journey`).
- CLI/MCP parity: `gaps`, `summary`, MCP `get_test_coverage` reflect per-step
  attribution (the conflation was in the graph, so these were wrong too).

## 7. Governing requirements

- **REQ-d00256** (journey step status / `annotate_journey_verification`) — reword to
  state per-step result attribution and `<journey>/N` addressing.
- **REQ-d00254-G** (source result→test binding) — add the `match_scope="step"`
  precise-binding tier (step-id-in-name resolves to the step's verifying test).
- **REQ-d00255** (journey UAT) — touch if step addressing is stated there.
- Re-hash affected spec blocks via `python -m elspais fix`; commit
  `spec/_generated/*`.

## 8. Constraints (for the implementing agent)

- **CLI:** the on-PATH `elspais` is a stale pipx install bound to a *different*
  worktree; use `python -m elspais …` and `git commit --no-verify` (the pre-commit
  hook runs the stale CLI). Bump the patch version in `pyproject.toml` each commit.
- Keep the existing `RESULT→YIELDS→TEST` convention (do not attach RESULT directly
  to STEP).
- Clean cutover to `<journey>/N` (no dual-support); update fixtures + [HHT] in
  tandem so the suite stays green.
- Do not change `source_path`/`source_file` on RESULT (they are the match key);
  add `result_file`/`result_line` as *new* fields.

## 9. Out of scope (deferred to a separate spec — "#2")

- **Configurable journey IDs** mirroring requirement `id_patterns` (prefix,
  component style, step separator/label style). Journeys are currently hardcoded to
  the `JNY-` prefix (`patterns.py:29-33`); making them configurable is a distinct
  subsystem and gets its own spec/plan.
- **Persisting results artifacts "for posterity"** (committing/archiving the
  junit.xml). It is gitignored/ephemeral today; a persistence decision is separate
  from this matching/provenance fix.
- **Line-precise links for genuinely minified XML** — addressed by the hht
  pretty-XML companion, not by elspais storing char offsets.
