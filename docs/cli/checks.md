# elspais checks

Verify requirements traceability and configuration.

## Synopsis

    elspais checks [--spec] [--code] [--tests] [--terms]
                   [--run-tests [--fail-fast]]
                   [--format text|markdown|json|junit|sarif]
                   [--status STATUS ...]
                   [--lenient] [--include-passing-details]
                   [-o PATH]

## Scope flags

`--spec`, `--code`, `--tests`, `--terms` restrict the run to one category.
Passing none of them runs all categories.

## Running tests as part of checks

`--run-tests` executes each entry in `[[scanning.test.runners]]` from the
active `.elspais.toml`, in declaration order, before evaluating checks.
Each runner shells out via the system shell; stdout and stderr stream
live to the terminal so you see test output as it happens.

`--fail-fast` (only meaningful with `--run-tests`) stops at the first
runner that exits non-zero and skips the checks pass entirely. Without
this flag, all configured runners run and checks then evaluate against
whatever result files were produced.

Configure runners in `.elspais.toml`:

    [[scanning.test.runners]]
    name = "python"
    command = "pytest --json-report --json-report-file=.elspais/results/pytest.json"

    [[scanning.test.runners]]
    name = "flutter"
    command = "flutter test --machine > .elspais/results/flutter.json"
    cwd = "app/"

The `command` must put output where `[scanning.result].file_patterns`
expects to find it. `cwd` is optional and resolves relative to the
repository root; an empty value means the repo root.

## Stale result detection

Even without `--run-tests`, `elspais checks` warns when:

- Result files are configured in `[scanning.result].file_patterns` but
  none exist on disk: the `tests.results` check returns `passed=false`,
  `severity=warning` (was `passed=true severity=info` prior to v0.115),
  which flips the exit code to 1 unless `--lenient` is passed.
- Result files exist but the oldest result mtime is earlier than the
  newest scanned spec/code/test file mtime: a separate
  `tests.results_stale` check is returned with `passed=false`,
  `severity=warning`, also flipping the exit code unless `--lenient`.

`--lenient` keeps these warnings from affecting the exit code; the
checks are still emitted in the report and remain visible in `--format
json`.

## Exit codes

- `0` -- all runners (if `--run-tests`) and all checks passed.
- `1` -- any runner failed, any check failed, or `--fail-fast` triggered.
- `2` -- `--run-tests` was passed but no runners are configured, or
  configuration could not be loaded.

## Examples

Verify everything:

    elspais checks

Run tests then verify:

    elspais checks --run-tests

Stop on first failure:

    elspais checks --run-tests --fail-fast

JSON output for CI:

    elspais checks --format json --lenient
