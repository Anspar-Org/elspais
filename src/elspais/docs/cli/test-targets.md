# elspais test-targets

Configuring how elspais runs and ingests tests per package or suite.

## Overview

The `[[scanning.test.targets]]` array declares one entry per test package or
suite.  Each entry tells elspais two things:

1. **How to produce results** -- the `command` to run (optional; omit in CI
   where results are pre-produced), the `reporter` that parses output, and
   optional `coverage` file to ingest.
2. **How to match results back to assertions** -- `match` selects between
   per-test source attribution (with file-granular fallback) or whole-app
   aggregate credit, and `credit_coverage` controls the `lcov_tested` dimension.

### Produce vs ingest split

```text
  Development (--run-tests):        CI (pre-produced results):
  +-----------------------+         +------------------------+
  | elspais checks        |         | flutter test --machine |
  |   --run-tests         |         |   > results.jsonl      |
  |                       |         |                        |
  | 1. runs `command`     |         | (done by CI pipeline)  |
  | 2. captures stdout or |         +------------------------+
  |    reads `results`    |
  | 3. reads `coverage`   |         elspais checks
  | 4. runs checks        |         (reads results + coverage files)
  +-----------------------+
```

When `command` is absent, `elspais checks` skips execution and ingests
whatever files are already on disk at the `results` glob or `coverage` path.
This is the correct pattern for CI.

## Target Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | string | (required) | Unique label for this target; appears in output |
| `cwd` | string | `""` (repo root) | Directory relative to repo root where the command runs |
| `command` | string | (omit in CI) | Shell command to execute when `--run-tests` is passed |
| `reporter` | string | (required) | Parser format: `flutter-machine`, `junit`, `pytest-json` |
| `results` | string | `""` | Glob pattern for result files (file-channel reporters) |
| `coverage` | string | `""` | Path to an lcov.info or coverage.py JSON file (format auto-detected), relative to `cwd` |
| `match` | string | `"source"` | `"source"` or `"aggregate"` -- matching strategy |
| `credit_coverage` | string | `"off"` | `"off"`, `"tested"`, or `"verified"` -- lcov_tested credit |
| `min_coverage_fraction` | float | `0.0` | Fraction of impl lines that must be covered (0.0-1.0) |

## Reporters and Matching

### Reporters

| Reporter | Channel | Description |
|----------|---------|-------------|
| `flutter-machine` | stdout | Parses `flutter test --machine` JSON-line protocol; includes real `suite.path` and test line for per-test matching |
| `junit` | file | Parses JUnit XML test result files matched by `results` glob. Honors an optional per-`<testcase>` `file` attribute (real source path) and `line` attribute so `match = "source"` can bind to a scanned test node -- see below |
| `pytest-json` | file | Parses pytest `--json-report` output matched by `results` glob |

**Stdout-channel reporters** (`flutter-machine`) capture output directly from
the running `command`.  The `results` field is not used.

**File-channel reporters** (`junit`, `pytest-json`) read files from disk
matched by the `results` glob.  These files can be pre-produced by CI.

### match

`match` controls how test results are attributed to `// Verifies:` edges:

**`match = "source"` (default):** Per-test attribution.  elspais matches each
result record to the specific `test()` by its source path AND line number
(e.g., the `suite.path` + test line from `flutter-machine`).  When a line does
not resolve to a known test node (shared-helper or generated tests), it falls
back to file granularity: all passing results for that file credit the file's
`Verifies:` assertions; any failure flags them.  Requires a reporter that emits
real file paths and, for per-test resolution, the test's source line
(`flutter-machine`); results without a line fall back to file granularity.

The `junit` reporter also supports `match = "source"` when the JUnit XML
carries a per-`<testcase>` `file` attribute naming the test's real source path
(and, optionally, a `line` attribute).  When `file` is present, elspais binds
the result to the scanned test node at that path instead of trying to
reconstruct a Python `test:...` identifier from the JUnit `classname` -- which
is how non-Python suites (e.g. Playwright `.spec.ts`) reach source matching at
all.  Because most JUnit reporters emit no true per-test source *line*, the
binding is typically **file-granular** (all of a passing spec's `Verifies:`
edges are credited; any failure flags them).  When the XML carries no `file`
attribute (standard pytest JUnit), behavior is unchanged -- use
`match = "aggregate"` (see the Playwright recipe below).

**`match = "aggregate"` (opt-in coarse mode):** The whole target is green or
red.  When green (at least one result ingested, zero failures), all
`// Verifies:` assertions in scope receive credit.  Use this when per-test
attribution is lossy or the test runner output does not round-trip test
identifiers cleanly.

### credit_coverage

Controls whether covered `// Implements:` lines feed the `lcov_tested`
dimension:

- `"off"` (default): coverage data is ingested but grants no assertion credit
- `"tested"`: covered impl lines credit `lcov_tested`
- `"verified"`: covered impl lines credit `lcov_tested`; if the target is red
  (any failing test), `lcov_tested` is also marked failing so coverage credit
  does not suppress a failure signal

## Flutter/Dart Recipe

This is the recommended setup for Flutter/Dart packages.  Use
`reporter = "flutter-machine"` with `match = "source"` to get real per-test
attribution -- elspais reads the `suite.path` and test source line emitted by
the Flutter test machine protocol and matches each result to the specific test
node at that `(path, line)` in the graph, with a file-granular fallback for
shared helpers and generated tests.

### Single-package example

```toml
[[scanning.test.targets]]
name        = "app"
cwd         = "app"
command     = "flutter test --machine --coverage"
reporter    = "flutter-machine"
coverage    = "coverage/lcov.info"
match       = "source"
credit_coverage = "verified"
```

`flutter test --coverage` writes the lcov report to
`<cwd>/coverage/lcov.info`.  The `coverage` field is relative to `cwd`, so
`"coverage/lcov.info"` resolves to `app/coverage/lcov.info` from the repo
root.

### Two-package example (one with a shared DB)

```toml
[[scanning.test.targets]]
name        = "app"
cwd         = "app"
command     = "flutter test --machine --coverage"
reporter    = "flutter-machine"
coverage    = "coverage/lcov.info"
match       = "source"
credit_coverage = "verified"

[[scanning.test.targets]]
name        = "backend"
cwd         = "backend"
command     = "flutter test --machine --coverage --concurrency=1"
reporter    = "flutter-machine"
coverage    = "coverage/lcov.info"
match       = "source"
credit_coverage = "verified"
```

Use one `[[scanning.test.targets]]` block per package.  The `cwd` field
isolates each package so `coverage/lcov.info` resolves correctly for each.

### Gotchas

**flutter not on PATH.**  The `elspais` process may run in an environment
where `flutter` is not on the system PATH.  Prefix your invocation:

```text
PATH="$HOME/flutter-sdk/flutter/bin:$PATH" elspais checks --run-tests
```

Or set `PATH` in your shell profile / CI environment before calling elspais.

**Postgres-racing suites.**  When multiple test files share a single database,
parallel test execution causes flakes.  Add `--concurrency=1` to the
`command` to serialise test files within that package:

```toml
command = "flutter test --machine --coverage --concurrency=1"
```

**Coverage file location.**  `flutter test --coverage` (without
`--coverage-path`) always writes to `<package-root>/coverage/lcov.info`.
The `coverage` field is relative to the target's `cwd`, so set:

```toml
coverage = "coverage/lcov.info"
```

**One target per package.**  Each Flutter package must have its own
`[[scanning.test.targets]]` block with its own `cwd`.  Sharing a single
target across packages is not supported.

## Python/pytest Recipe

Use `reporter = "pytest-json"` with a pre-generated JSON report file:

```toml
[[scanning.test.targets]]
name     = "unit"
cwd      = "."
command  = "pytest tests/ --json-report --json-report-file=.elspais/results/pytest.json"
reporter = "pytest-json"
results  = ".elspais/results/pytest.json"
match    = "aggregate"
```

For JUnit XML output (compatible with many CI systems):

```toml
[[scanning.test.targets]]
name     = "unit"
command  = "pytest tests/ --junit-xml=.elspais/results/TEST-unit.xml"
reporter = "junit"
results  = ".elspais/results/TEST-*.xml"
match    = "aggregate"
```

## Playwright / TypeScript Recipe (source-bound JUnit)

Any suite that produces JUnit XML can bind results to scanned test nodes with
`match = "source"` **if each `<testcase>` carries a `file` attribute** naming
the test's real source path (see the `junit` reporter note under *Reporters
and Matching*).  This is how a Playwright `.spec.ts` suite feeds
journey/step UAT coverage per spec rather than as one whole-suite verdict.

Three things must be true:

1. **Specs are scanned as TEST nodes.**  elspais cannot parse TypeScript
   natively, so point `[scanning.test].prescan_command` at an external scanner
   that emits `test_`-prefixed functions for each `test(...)` call, and add the
   spec directories / `*.spec.ts` to the test `directories` / `file_patterns`.
2. **The JUnit XML carries `file`.**  Playwright's JUnit reporter omits the
   per-`<testcase>` `file` attribute, so a small post-processing step in the
   runner injects `file="<repo-relative spec path>"` (derivable from
   `classname`) into each `<testcase>` before elspais ingests it.
3. **The target uses `match = "source"`.**

```toml
[[scanning.test.targets]]
name     = "e2e"
reporter = "junit"
results  = "test-results/junit.xml"   # glob relative to cwd
match    = "source"                    # per-spec binding via <testcase file=...>
```

Because JUnit `line` values are not true source lines, binding is
**file-granular**: a passing spec credits all of its `// Verifies:` step-edges;
any failing case flags them.  The journey verdict is all-or-nothing -- `full`
only when every step is verified-passing, `partial` if any step is uncovered,
`fail` if any is failing.  If you cannot inject `file=`, fall back to
`match = "aggregate"` for a whole-suite pass/fail signal.

## Your Language Here

Template for any language.  Fill in the fields marked with comments:

```toml
[[scanning.test.targets]]
# Unique name for this test suite / package.
name = "my-suite"

# Directory (relative to repo root) where the command runs.
# Omit or set to "." if running from repo root.
cwd = "packages/my-package"

# Command to run when `elspais checks --run-tests` is invoked.
# Omit this field in CI -- elspais will ingest pre-produced result files.
command = "my-test-runner --output results.xml"

# Reporter format: "junit" | "pytest-json" | "flutter-machine"
reporter = "junit"

# Glob for result files (file-channel reporters).
# Relative to cwd (not repo root).  With cwd = "packages/my-package",
# this resolves to packages/my-package/results/*.xml from the repo root.
results = "results/*.xml"

# Path to an lcov.info or coverage.py JSON file (format auto-detected), relative to cwd.
# Omit if no coverage report.
# coverage = "coverage/lcov.info"

# "source" (default): source-location attribution (requires file paths in results).
# "aggregate" (opt-in): whole-suite green/red; use when results lack file paths.
match = "source"

# "off" | "tested" | "verified" -- lcov_tested dimension credit.
# credit_coverage = "off"

# Minimum fraction of impl lines that must be covered (0.0 = any).
# min_coverage_fraction = 0.0
```

## CI Usage

In CI, omit `command` so elspais only ingests files that the pipeline already
produced.  Point `results` and `coverage` at the paths your CI step writes:

```toml
[[scanning.test.targets]]
name     = "app"
cwd      = "app"
# No `command` -- CI already ran flutter test
reporter = "flutter-machine"
# flutter-machine is a stdout reporter, so `results` is unused.
# To get per-test pass/fail attribution in CI, save `flutter test --machine`
# output to a file in the CI step and point `results` at it (relative to cwd):
#   results = "build/test-results.jsonl"
# Without `results`, only coverage credit is applied (no pass/fail signal).
coverage = "coverage/lcov.info"
match    = "source"
credit_coverage = "verified"
```

Run elspais in CI after the test step:

```text
elspais checks
```

## Per-PR selectivity

`--targets NAME ...` (accepted by `checks`, `summary`, and `trace`) names the
subset of `[[scanning.test.targets]]` that are **fresh** for this invocation.
Everything else is the **complement** — targets not named on `--targets`.
Omitting `--targets` entirely runs/marks everything as fresh (the full-run
behavior is unchanged from before this flag existed).

The flag means something slightly different depending on the command:

- **`elspais checks --run-tests --targets NAME ...`** — execution. Only the
  named targets are run (their `command`, if any, is executed and their
  results ingested). Targets not named are skipped entirely for this
  invocation: their `command` does not run and no new results are produced
  for them. An unknown name is an error (exit 2).
- **`elspais summary --targets NAME ...`** / **`elspais trace --targets NAME
  ...`** — provenance/rendering. These commands don't run tests themselves;
  `--targets` tells them which targets' results were freshly produced *this
  invocation* (normally by a preceding `checks --run-tests --targets ...`
  with the same names) versus which targets' results are left over from an
  earlier run.

On `trace`, the complement (non-named) targets render one of two ways in the
per-requirement `verified` column, depending on whether prior result data
exists for them:

- **`(baseline)`** — carried. The target has existing RESULT data from a
  previous run; that verdict is reused and rendered with a `(baseline)`
  suffix (e.g. `4/4 100% (baseline)`). A carried **failing** target still
  fails/gates — carrying only skips re-execution, it never launders a
  failure into a pass.
- **`—`** (em dash) — no baseline. The target has test references (so
  coverage is expected) but zero result data at all — nothing to carry.
  This renders as skipped and is **not** gating; it's treated as "not run
  this PR" rather than a regression.

A `> Legend: ...` line explaining both markers is appended to `trace`'s
markdown output whenever at least one row actually used one (never shown on
a full run, and never shown for `--dimension uat`, which has no `verified`
column).

`summary` is level-aggregated, not per-requirement, so it can't show
`(baseline)`/`—` inline. Instead, when any RESULT target was carried, the
level table's **Passing** figure (the union of `verified` and `lcov_tested`
— the "tested & passing" headline) gets a trailing `*`, and a footnote is
appended:

```text
* 1/2 test results from previous runs
```

The `N/M` counts are distinct RESULT target names: `M` targets have any
result data at all, `N` of those were carried (not freshly produced this
invocation). A full run (no `--targets`, or `--targets` covering every
result-bearing target) has zero carried targets, so neither the `*` nor the
footnote appears — output is unchanged from before this flag existed. The
`json`/`csv` formats expose the same counts as structured fields
(`carried_result_targets`, `total_result_targets`) instead of the `*`.

`elspais checks` itself (the health-report / gate command) only consumes
`--targets` for *execution* under `--run-tests`; it does not render
`(baseline)`/`—`/`*` — that provenance rendering is `summary`/`trace`'s job.
Running `elspais checks --targets NAME ...` without `--run-tests` accepts
the flag but has no execution or rendering effect.

### Worked example

Per-PR: run only the targets touched by this change, then render the full
matrix with the rest carried as baselines:

```bash
elspais checks --run-tests --targets clinical_diary portal_ui_evs
elspais trace --targets clinical_diary portal_ui_evs --format markdown
```

`clinical_diary` and `portal_ui_evs` show fresh, just-run results.  Every
other configured target shows `(baseline)` (carried from its last run) or
`—` (no prior result data for that target).

Full regression (e.g. promoting a build from qa to uat): omit `--targets` so
every configured target runs and renders fresh:

```bash
elspais checks --run-tests
```

See also: `elspais docs checks`
