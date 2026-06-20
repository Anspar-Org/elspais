# elspais test-results

Integrating test execution results and code coverage into the traceability graph.

## Overview

When test result files and coverage reports are present, elspais enriches each
assertion with three distinct coverage dimensions:

```text
  tested       -- at least one // Verifies: test is linked to this assertion
  verified     -- a linked test passed (result file confirms it)
  lcov_tested  -- the code implementing this assertion was executed
                  (per [scanning.coverage] lcov report)
```

The summary headline shown by `elspais checks` and the GUI unions
`verified` and `lcov_tested`: an assertion is considered covered if it
has a passing test *or* its implementation lines were executed.

## Coverage Dimensions

### tested

An assertion is `tested` when at least one test file contains a
`// Verifies: REQ-xxx-A` marker (or equivalent for the configured
`reference_keyword`) that references the assertion.  This dimension
reflects structural linkage only -- it does not depend on whether any
result file was ingested.

### verified

An assertion is `verified` when a linked test is confirmed passing by an
ingested result file.

**Per-test matching (Python / pytest):** elspais matches each result
record (by test name) to the specific `// Verifies:` edge and marks
exactly those edges as verified.  A failure flips the dimension to
`failing` for those assertions.

**Per-app aggregate (Dart / Flutter):** Dart JUnit XML output is lossy --
individual test names may not round-trip cleanly through the Flutter test
machine protocol.  elspais therefore applies an *aggregate* green model:
an app directory is `green` iff it has at least one ingested result file
and zero failures.  All unmatched `// Verifies:` edges in that app's
scope can then receive `verified` credit by setting:

```toml
[scanning.result]
unmatched_credit = "verified"
```

With `unmatched_credit = "off"` (the default) only per-test matched edges
receive `verified` credit; unmatched edges remain at the `tested` level.

### lcov_tested

`lcov_tested` is a separate dimension driven by code coverage reports
(lcov `.info` files or similar).  When a line of code annotated with
`// Implements: REQ-xxx-A` appears in a covered section of the report,
elspais can credit the assertion.

Configure via `[scanning.coverage]`:

```toml
[scanning.coverage]
directories = [".elspais/coverage"]
file_patterns = ["lcov.info", "coverage.lcov"]
assertion_credit = "tested"      # "off" | "tested" | "verified"
min_coverage_fraction = 0.0      # fraction of impl lines that must be covered
```

`assertion_credit` controls *which* dimension receives credit:

- `"off"` (default): coverage reports are ingested but grant no assertion credit
- `"tested"`: covered impl lines count as `lcov_tested` (the assertion was exercised)
- `"verified"`: covered impl lines count as both `lcov_tested` and `verified`

`min_coverage_fraction` (default `0.0`) is the minimum fraction of an
assertion's implementing lines that must be covered before credit is
granted.  `0.0` means any execution counts; `1.0` requires every
implementing line to be covered.

## Per-App Green Model

elspais evaluates result health per *app directory* (one entry under
`[scanning.result].directories`).  An app is:

- **green** -- at least one result file ingested, zero test failures
- **red** -- at least one failure recorded in an ingested result file

A red app sets `has_failures = true` on the `tests.results` check and
flips the exit code of `elspais checks` to 1 (unless `--lenient`).

This scoped model means a failure in one app does not suppress the
`verified` credit of a completely separate app.

## Configuration Reference

### [scanning.result]

```toml
[scanning.result]
directories = [".elspais/results"]
file_patterns = ["TEST-*.xml", "pytest-results.json", "flutter-test.json"]
unmatched_credit = "off"   # "off" | "verified"
```

| Key | Values | Default | Description |
|-----|--------|---------|-------------|
| `unmatched_credit` | `"off"`, `"verified"` | `"off"` | Credit `verified` for unmatched `// Verifies:` edges when the app is green |

### [scanning.coverage]

```toml
[scanning.coverage]
directories = [".elspais/coverage"]
file_patterns = ["lcov.info"]
assertion_credit = "off"         # "off" | "tested" | "verified"
min_coverage_fraction = 0.0      # 0.0 to 1.0
```

| Key | Values | Default | Description |
|-----|--------|---------|-------------|
| `assertion_credit` | `"off"`, `"tested"`, `"verified"` | `"off"` | Dimension credited when impl lines are covered |
| `min_coverage_fraction` | float 0.0--1.0 | `0.0` | Minimum covered fraction of an assertion's impl lines |

## Per-Language Setup

### Python / pytest

```toml
[[scanning.test.runners]]
name = "python"
command = "pytest --json-report --json-report-file=.elspais/results/pytest.json"

[scanning.result]
directories = [".elspais/results"]
file_patterns = ["pytest-results.json"]

[scanning.coverage]
directories = [".elspais/coverage"]
file_patterns = ["lcov.info"]
assertion_credit = "tested"
```

Generate an lcov report with:

```text
pytest --cov=src --cov-report=lcov:.elspais/coverage/lcov.info
```

### Dart / Flutter

Flutter JUnit output is aggregated per app.  Use `unmatched_credit = "verified"`
to propagate the green-app signal to all linked assertions:

```toml
[[scanning.test.runners]]
name = "flutter"
command = "flutter test --machine > .elspais/results/flutter.json"
cwd = "app/"

[scanning.result]
directories = [".elspais/results"]
file_patterns = ["flutter*.json", "TEST-*.xml"]
unmatched_credit = "verified"

[scanning.coverage]
directories = [".elspais/coverage"]
file_patterns = ["lcov.info"]
assertion_credit = "tested"
min_coverage_fraction = 0.5
```

### Other Languages

For any language that produces JUnit XML or a compatible format:

```toml
[[scanning.test.runners]]
name = "jest"
command = "jest --reporters=jest-junit"

[scanning.result]
directories = ["test-results"]
file_patterns = ["TEST-*.xml"]
```

Set `unmatched_credit = "verified"` if the test runner cannot produce
per-test name records that match elspais's edge keys, or if you prefer
aggregate green-app semantics.

## Checks and Stale Detection

`elspais checks` evaluates result health via two check entries:

- `tests.results` -- fails if result files are configured but none exist on disk
- `tests.results_stale` -- fails if result files are older than the newest
  spec, code, or test file

Both are `severity = "warning"` and flip the exit code to 1 unless
`--lenient` is passed.

Coverage and dimension gaps appear in `elspais checks --tests` output and
the GUI traceability view.

See also: `elspais docs checks`
