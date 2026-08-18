# TRACEABILITY

## What is Traceability?

Traceability connects requirements to their implementations and tests:

  **Requirement** -> **Assertion** -> **Code** -> **Test** -> **Result**

This answers: "How do we know this requirement is satisfied?"

## Generating Reports

  $ elspais trace                    # Markdown table (default)
  $ elspais trace --format html      # Basic HTML matrix
  $ elspais trace --format csv       # Spreadsheet export
  $ elspais trace --format json      # JSON structured output
  $ elspais viewer                   # Interactive HTML tree (live server)
  $ elspais viewer --static          # Interactive HTML tree (static file)
  $ elspais graph                    # Export graph structure as JSON

## Coverage Columns

`trace` (standard/full presets) and `summary` report five coverage columns
using exactly this display vocabulary: **Implemented, Tested, Passing, UAT
Covered, UAT Passed** (plus `Code Tested` and `LCOV Tested` for line
coverage). These are the only words that denote a coverage dimension; in
particular "Validated" is not one of them, since it collides with the
`Validates:` keyword (journey → requirement UAT links).

**Total headline + the four measures behind it.** Every one of the five
assertion-based columns headlines the per-*Assertion* TOTAL: for each
assertion, the greatest of four measures, so an assertion covered more than
one way is counted once and a requirement's total can never exceed its
assertion count. The four measures answer two independent questions: what a
citation named (*direct* -- it named the assertion; *indirect* -- it named
only the whole requirement) crossed with where the evidence sits (*immediate*
-- attached to this requirement; *rolled-up* -- conducted from a refining
requirement's own coverage via `Refines:`). `trace --format csv` publishes
all four as columns of their own beside each dimension's total (`Tested
Immediate Direct`, `Tested Immediate Indirect`, `Tested Rolled Direct`,
`Tested Rolled Indirect`, and likewise for the other four dimensions);
`trace --format json` carries the same four fields per dimension in each
requirement's object. The text/markdown/html table intentionally does NOT
grow four more numbers per dimension -- it is already eleven columns wide,
and REQ-d00258-A requires the measures to be *available*, which `--format
json`/`csv` already satisfy without making the default table unreadable.
`summary` prints the four measures beneath each level's headline, naming
each one directly: "cited by name here" (immediate-direct), "whole-requirement"
(immediate-indirect), "conducted direct"/"conducted indirect" (the two
rolled-up measures). These words are now the canonical names for the four
REQ-d00069-L measures everywhere; the `health` coverage check's two
comparable-looking figures are LEGACY BLENDED footings that predate this
split and are labeled "legacy direct footing"/"legacy indirect footing" so
they are not mistaken for the same quantities. The viewer uses the same four
names: a requirement's dimension badge and each per-assertion pill headline
the total standing, and their hover text names all four measures behind it.
There is no caveat marker standing in for a measure a surface does not show --
where the difference between measures matters, the measures themselves are
reported. See `elspais docs checks`
(*Coverage Dimensions*) for the model underneath this.

**Relative denominators.** `Tested` and `Passing` measure against their own
denominator, not the whole spec: `Tested` is tested / **implemented** and
`Passing` is passing / **tested**. A row with nothing implemented shows an
empty `Tested`/`Passing` denominator as neutral `missing` (grey), never a red
gap -- the "not all built" story lives on the `Implemented` column. A failing
in-denominator label always reads `failing` (red).

**What Passing takes.** The `Passing` column (dimension key `verified`) counts
an assertion when a test *declared against that assertion* returned a passing
result, and none returned a failure. Nothing else credits it. Line coverage of
the code implementing an assertion does not: executing a line says the code was
reached, not that the assertion was checked, and a test can always carry its
own `Verifies:` -- so an assertion reported as passing without one would be
reporting an annotation nobody wrote. Passing is therefore always a subset of
Tested.

**Line coverage is its own dimension.** `Code Tested` and `LCOV Tested` report
how much of the implementation a run exercised. That is worth knowing and it is
reported in its own right, beside the traceability columns and never folded
into them. `credit_coverage` on a target governs whether that dimension is
computed at all; it no longer credits any traceability dimension.

**The Tested breakdown.** Every tested assertion is in exactly one of three
states, and all three are reported alongside the Tested figure: passed,
failed, and awaiting a result -- the last covering a test that has not run,
one whose results were never ingested, and one that returned no verdict.
`summary` renders it as `[N passed, N failed, N awaiting a result]`, `trace`
compactly as `[3P 0F 2A]` with a legend under the table, and `summary
--format csv` as three columns. It is a breakdown OF Tested, not a coverage
dimension of its own: the display vocabulary stays at the five terms above.
Passing alone would leave the remainder ambiguous -- an assertion missing
from it either failed or never returned a verdict, and those ask for opposite
things. `summary`'s level-aggregated
Passing figure gets a trailing `*` (footnoted) when any underlying RESULT
data was carried from a previous run -- see `elspais docs test-targets`
(*Per-PR selectivity*).

**Code Tested: per-test or `n/a`.** The `Code Tested` column reports
`code_tested.attributed_lines` -- implementation lines whose coverage.py **context**
names the specific test that exercised them (Python only, via pytest-cov's
`--cov-context=test`). When no per-test context data is available for a
requirement's covered lines (aggregate-only coverage tooling, or a coverage
format without a `contexts` map, e.g. LCOV), the cell renders `n/a` rather
than a misleading `0/N (0%)` -- there is no per-test attribution to report,
not zero coverage. See `elspais docs checks` (*code_tested — line coverage*)
and `elspais docs test-targets` (*Python/pytest Recipe*) for the
`[tool.coverage.json] show_contexts = true` + `--cov-context=test` setup
this requires.

## trace Command Options

  `--format {text,markdown,html,json,csv}`  Output format (default: markdown)
  `--preset {minimal,standard,full}`        Column preset
  `--body`                Show requirement body text
  `--assertions`          Show individual assertions
  `--tests`               Show test references
  `--output PATH`         Output file path
  `--dimension uat`       UAT-scoped report: only requirements validated by at least one journey (named on a journey's `Validates:` line), with validating journeys + verdicts and uat_coverage/uat_verified tiers; excludes code columns

## UAT Dimension

  $ elspais trace --dimension uat
  $ elspais trace --dimension uat --format markdown -o uat-traceability.md

Emits a focused UAT traceability report. Only requirements validated by at least
one user journey (i.e., named on a journey's `Validates:` line) appear in the
output. Columns: ID, Title, Level, Status, UAT Covered, UAT Passed, Journeys
(`JNY-id:verdict` pairs). Code-dimension columns (Implemented, Tested, Passing,
etc.) are excluded.

Coverage counts headline the per-*Assertion* total (the greatest of the four
measures behind it) -- see *Total headline + the four measures behind it*
above.

Journey verdicts: `pass` (all steps have a passing test, none failed), `fail`
(at least one failure), `partial` (some steps pass but not all), `unverified`
(no test results recorded).

## viewer Command Options

  `--static`              Generate static HTML file instead of live server
  `--server`              Start server without opening browser
  `--port PORT`           Server port (default: 5001)
  `--embed-content`       Embed full markdown in HTML (offline viewing)
  `--path DIR`            Path to repository root (default: auto-detect)

## graph Command

Export the full traceability graph as JSON:

  $ elspais graph                    # Print to stdout
  $ elspais graph -o graph.json      # Write to file

## Marking Code as Implementing

In Python, JavaScript, Go, etc., use comments:

```python
# Implements: REQ-d00001-A
def hash_password(plain: str) -> str:
    ...
```

Or:
```javascript
// Implements: REQ-d00001
function hashPassword(plain) { ... }
```

## Marking Tests as Validating

Reference requirement IDs in test function names:

```python
def test_REQ_d00001_A_bcrypt_cost():
    ...
```

Or with comments:
```python
# Tests: REQ-d00001-A
def test_password_uses_bcrypt():
    ...
```

## Coverage Indicators

In the interactive viewer:
  **None**    - No code implements this assertion
  **Partial** - Some assertions have implementations
  **Full**    - All assertions have implementations
  **Failure** - Test failures detected
  **Changed** - Modified vs main branch

## Understanding the Graph

  $ elspais graph -o graph.json

The graph shows:
- Requirements and their assertions
- Which code files implement which assertions
- Which tests validate which requirements
- Test pass/fail status from JUnit/pytest results
