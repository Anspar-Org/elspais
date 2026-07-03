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
coverage). "Validated" never denotes test coverage on any surface -- it
collides with the `Validates:` keyword (journey → requirement UAT links).

**Generous footing + `~` marker.** Every one of the five assertion-based
columns headlines the *generous* footing -- `CoverageDimension.indirect`,
which counts an assertion covered whether the link named it directly
(`REQ-xxx-A`) or only the whole requirement (`REQ-xxx`). A trailing `~`
appended to a cell means that column's count is not fully backed by
direct (assertion-level) evidence, i.e. `indirect > direct` for at least one
covered assertion in that row. No marker means the generous and strict
(direct) counts agree -- every bit of credit is assertion-specific. See
`elspais docs checks` (*Coverage Dimensions*) for the direct/indirect/tier
model underneath this.

**Passing is a union.** The `Passing` column (dimension key `verified`) is
the union of two kinds of evidence: a passing `Verifies:` test result
(`verified`), or a covered `Implements:` line under a target with
`credit_coverage = "verified"` (`lcov_tested`, and only if that target isn't
also failing). Either alone is enough to count as passing; see
`tested_and_passing()` in `graph/metrics.py`. `summary`'s level-aggregated
Passing figure gets a trailing `*` (footnoted) instead of `~` when any
underlying RESULT data was carried from a previous run -- see `elspais docs
test-targets` (*Per-PR selectivity*).

**Code Tested: per-test or `n/a`.** The `Code Tested` column reports
`code_tested.direct` -- implementation lines whose coverage.py **context**
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

Coverage counts headline on the generous footing (direct + indirect evidence);
a trailing `~` marker flags a count whose evidence isn't fully direct.

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
