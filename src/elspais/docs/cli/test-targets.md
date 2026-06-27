# elspais test-targets

Configuring how elspais runs and ingests tests per package or suite.

## Overview

The `[[scanning.test.targets]]` array declares one entry per test package or
suite.  Each entry tells elspais two things:

1. **How to produce results** -- the `command` to run (optional; omit in CI
   where results are pre-produced), the `reporter` that parses output, and
   optional `coverage` file to ingest.
2. **How to match results back to assertions** -- `match` selects between
   per-test precise attribution (with file-granular fallback) or whole-app
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
| `junit` | file | Parses JUnit XML test result files matched by `results` glob |
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

See also: `elspais docs checks`
