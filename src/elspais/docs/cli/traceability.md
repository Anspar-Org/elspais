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

## Coverage Values

`trace` (standard/full presets) and `summary` report five coverage values
using exactly this display vocabulary: **Implemented, Tested, Passing, UAT
Covered, UAT Passed** (plus `Code Tested` and `LCOV Tested` for line
coverage). These are the only words that denote a coverage dimension; in
particular "Validated" is not one of them, since it collides with the
`Validates:` keyword (journey → requirement UAT links).

**Total headline + the four measures behind it.** Every one of the five
assertion-based values headlines the per-*Assertion* TOTAL: for each
assertion, the greatest of four measures, so an assertion covered more than
one way is counted once and a requirement's total can never exceed its
assertion count. The four measures answer two independent questions: what a
citation named (*direct* -- it named the assertion; *indirect* -- it named
only the whole requirement) crossed with where the evidence sits (*immediate*
-- attached to this requirement; *rolled-up* -- conducted from a refining
requirement's own coverage via `Refines:`). Each is selectable in its own
right beside the dimension's total: `--values tested,tested.immediate_direct`
states a `Tested` column and a `Tested (cited by name here)` column under
`--format csv`, and nests the measure inside the dimension's object under
`--format json`. No report states all four uninvited -- the default table is
already eleven columns wide, and REQ-d00258-A requires the measures to be
*available*, which naming them satisfies without making the default
unreadable.
`summary` prints the four measures beneath each level's headline, naming
each one directly: "cited by name here" (immediate-direct), "whole-requirement"
(immediate-indirect), "conducted direct"/"conducted indirect" (the two
rolled-up measures). These words are now the canonical names for the four
REQ-d00069-L measures everywhere, and the `health` coverage check prints them
too: it headlines the same per-assertion total and lists the measures behind
it under those same four words. Its "cited by name here" figure is shown even
when it is zero, because that zero is what explains a `gaps` entry the check
counts as covered. The viewer uses the same four
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
gap -- the "not all built" story lives on the `Implemented` value. A failing
in-denominator label always reads `failing` (red).

**What Passing takes.** The `Passing` value (dimension key `verified`) counts
an assertion when a test *declared against that assertion* returned a passing
result, and none returned a failure. Nothing else credits it. Line coverage of
the code implementing an assertion does not: executing a line says the code was
reached, not that the assertion was checked, and a test can always carry its
own `Verifies:` -- so an assertion reported as passing without one would be
reporting an annotation nobody wrote. Passing is therefore always a subset of
Tested.

**Line coverage is its own dimension.** `Code Tested` and `LCOV Tested` report
how much of the implementation a run exercised. That is worth knowing and it is
reported in its own right, beside the traceability values and never folded
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

**Code Tested: per-test or `n/a`.** The `Code Tested` value reports
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
  `--preset {minimal,standard,full}`        Named default value set
  `--values KEY,KEY,...`  State exactly these values, in this order
  `--body`                Show requirement body text
  `--assertions`          Show individual assertions
  `--tests`               Show test references
  `--output PATH`         Output file path
  `--dimension uat`       UAT-scoped value set: UAT Covered, UAT Passed and the validating journeys with their verdicts; excludes the code values

## Choosing Values

  $ elspais trace --values id,title,tested,tested.immediate_direct
  $ elspais trace --format csv --values uat_coverage.immediate_direct,code_tested

`--preset` names a DEFAULT set -- what you get when you ask for no values in
particular. `--values` states the report's values outright, replacing that
set, in the order you name them. The report is refused if any name is not a
value it offers; a report is never produced under half a selection.

Which values a report states and which requirements it is about are separate
choices: `--values` never changes which rows appear, and `--level`/`--status`/
`--scope` never change which values do.

Value keys are stable names, never the words a project displays them under --
rename a display label and every committed selection still means what it meant:

  identity    `id` `title` `level` `status` `implements` `hash` `file` `journeys`
  dimensions  `implemented` `tested` `verified` `uat_coverage` `uat_verified`
  measures    `<dimension>.immediate_direct` `.immediate_indirect`
              `.rolled_direct` `.rolled_indirect`
  scalars     `<figure>.count` `<figure>.total` `<figure>.ratio`
              where `<figure>` is a dimension or one of its measures
  tested only `tested.passed` `tested.failed` `tested.awaiting` (counts only)
  provenance  `verified.carried` (`trace` only)
  lcov credit `lcov_tested` (counts assertions from line evidence; no measures)
  line cover  `code_tested` and `.count` `.total` `.ratio` `.attributed`
              (measured in LINES; no measures)

A dimension key states that dimension's per-*Assertion* total; a measure key
states one of the four measures behind it, and its heading names both the
dimension and the measure. `id` is always stated, so every row says what it is
about. The selection is the same in every format -- markdown, csv, html and
json state what you named and nothing else, each in its own kind.

One named value is one value. A table states a figure in one cell, carrying its
denominator and its proportion inside that cell (`5/5 (100%)`), with the Tested
breakdown riding in the Tested cell (`5/5 (100%) [3P 0F 2A]`) because it
qualifies that figure rather than being a figure of its own. A structured
format states the same figure as an object of the numbers behind it:

  $ elspais trace --format json --values implemented

  { "id": "REQ-d00081", "implemented": { "count": 3.0, "total": 7.0, "ratio": 0.42857142857142855 } }

That composite is what a table wants; a program wants the numbers, and should
not have to cut them back out of a sentence. Every figure therefore also offers
the three scalars behind it -- `.count` (the assertions credited), `.total` (the
assertions the credit was counted over) and `.ratio` (their proportion) -- each
selectable alone. A key is a path and the object mirrors it: asking for
`implemented.count` states `{"implemented": {"count": 3.0}}`, and a measure's
scalar nests one level deeper again:

  $ elspais trace --format json --values implemented.count,implemented.ratio
  $ elspais trace --format json --values tested.immediate_direct.total
  $ elspais trace --format json --values tested.failed

JSON states a scalar as a number, never as a string. The proportion is derived
rather than stored and is never rounded in the value, so it always equals
`.count` over `.total`; a table rounds it to three places, which is a cell and
not the value. `tested.passed`, `tested.failed` and `tested.awaiting` are the
same three counts the breakdown states in prose, individually selectable -- ask
for the failures and you get the failures. They sit in the Tested object beside
its three scalars, and they are counts and nothing else, so no `.ratio` is
offered beneath them.

`code_tested` is the one figure measured in LINES rather than assertions, and
it decomposes the same way -- `.count` is the lines covered, `.total` the lines
measured, `.ratio` their proportion:

  $ elspais trace --format json --values code_tested

  { "id": "REQ-d00081", "code_tested": { "count": 16.0, "total": 20.0, "ratio": 0.8, "attributed": null } }

`.attributed` is a further reading of the same lines: how many of them a
verifying test can be named for. It is a different question from the figure, so
it has its own name and its own absence -- coverage tooling that records no
per-test contexts can attribute nothing, and the value is `null` rather than
`0`. The lines covered and measured stand regardless, because those were
measured. `summary` offers `code_tested` too, summed over each level's
requirements under the same status gate `checks --code-checks` uses, so the two
reconcile. `lcov_tested` is not a line figure: it credits assertions from line
evidence, so it is counted over assertions and decomposes into the same three
scalars every assertion-counted figure does.

`verified.carried` is the provenance behind the Passing figure: whether the
verdict was carried from a baseline rather than produced by the run being
reported. It is not a number, so a table states it as a word -- `baseline` or
`fresh` -- while json states a boolean, or `null` where no verdict was taken.
`trace` offers it; `summary` does not, having no per-requirement bit to state,
and discloses carried results for the report as a whole instead.

A value a row does not have is stated as an absence and never as zero: `null`
in json, `n/a` in a `trace` cell, `-` in a `summary` cell. Under `--targets`, a
requirement carrying test references but no result record at all has no
verified verdict to state, so its `trace` cell reads `—` and its
`verified.count`, `verified.ratio` and `verified.carried` are each `null`.

A project can declare a value set under a name beside the scope it belongs to
(`[scopes.<name>] values = [...]`), so one name refers to a whole audience:
the requirements it reads and the facts it reads about them. `--values` on the
invocation replaces a declared set rather than narrowing it.

## UAT Dimension

  $ elspais trace --dimension uat
  $ elspais trace --dimension uat --format markdown -o uat-traceability.md

Emits a focused UAT traceability report. It states ID, Title, Level, Status,
UAT Covered, UAT Passed and Journeys (`JNY-id:verdict` pairs). Code-dimension
values (Implemented, Tested, Passing, etc.) are excluded.

`--dimension uat` chooses values, not rows. Every requirement the scope selects
appears; one no journey validates is a row with an empty Journeys cell, which is
the fact worth seeing. To report only the validated ones, narrow the rows -- that
is what a scope is for.

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
def hash_password(plain: str) -> str: ...
```

Or:
```javascript
// Implements: REQ-d00001-A
function hashPassword(plain) { ... }
```

The citation attributes the lines of the function it is written above. Decorators
and a class header do not break that: write it above the decorators, or between
the last decorator and the `def` -- both name the same function.

```python
# Implements: REQ-d00001-A
@app.route("/hash")
def hash_password(plain: str) -> str: ...
```

A citation above a `class` binds to the first function inside it, and to nothing
at all if the class opens with a docstring, a field, or an enum member -- a class
is not itself an extent. Where a citation names no function, it instead speaks for
the executable lines following it, up to the next citation or the end of the file.

## Marking Tests as Validating

Write a comment above the test. This is the only form that links a test --
a requirement ID in the function name references nothing:

```python
# Verifies: REQ-d00001-A
def test_password_uses_bcrypt(): ...
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
