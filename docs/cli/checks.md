# elspais checks

Verify requirements traceability and configuration.

## Synopsis

    elspais checks [--spec] [--code] [--tests] [--terms]
                   [--run-tests [--fail-fast]] [--targets NAME ...]
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

`--targets NAME ...` restricts `--run-tests` to the named subset of
`[[scanning.test.targets]]` (space-separated names), instead of running
every configured target. An unknown name is an error (exit 2); an
absent `--targets` runs all targets as before.

    elspais checks --run-tests --targets python

    elspais checks --run-tests --targets python flutter

`--targets` on `checks` only controls *execution* under `--run-tests`; it
does not itself render carried/no-data provenance -- that's `summary`/`trace`'s
job. See `elspais docs test-targets` (Per-PR selectivity) for the full model,
including the `(baseline)` and `—` render states on `summary --targets` /
`trace --targets`.

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

## Coverage provenance checks

Among the `code` category checks is `code.whole_req_only_coverage`, an
always-INFO check (it never fails the build) that counts assertions whose
Implemented coverage rests only on whole-requirement evidence -- a blanket
`Implements:`/`Refines:` that names no specific assertion. Under the
full-credit model, that blanket evidence fully credits every assertion's
Implemented state; this check makes how much green rests on blanket
evidence visible per requirement, rather than leaving it silent.

`[rules.coverage].allow_indirect` (default `true`) controls whether
indirect/blanket evidence credits a dimension's headline *tier* in the
viewer and `elspais summary` badges: with the default, indirect evidence
counts toward `full`/`partial` and a trailing `~` marker (and this check)
flag where it came from; with `allow_indirect = false`, only direct
assertion-level evidence counts toward those tiers, and a requirement
covered only indirectly reads `missing`/`partial` in the summary/viewer
badge buckets and the relative-chain denominators (Tested/implemented,
Passing/tested, etc.) instead of `full`.

This setting does **not** change `elspais checks`' per-dimension coverage
checks (`code.implemented`, `tests.tested`, `tests.verified`,
`uat.uat_coverage`, `uat.uat_verified`). Those checks source their counts
from `aggregate_dimension` (`src/elspais/graph/aggregation.py`), which sums
direct and indirect evidence unconditionally -- it never calls
`allow_indirect`-aware tiering -- and only fails a check when a result
records an actual test failure (`has_failures`), never on a missing/partial
tier. A requirement covered only indirectly still reports `passed=true`
(`severity=info`) on these checks regardless of `allow_indirect`. See
`docs/configuration.md` ("`allow_indirect` (direct vs indirect credit)")
for the full model of what it *does* affect (viewer/summary badge tiers
and relative-chain buckets).

## Exit codes

- `0` -- all runners (if `--run-tests`) and all checks passed.
- `1` -- any runner failed, any check failed, or `--fail-fast` triggered.
- `2` -- `--run-tests` was passed but no runners are configured (or none
  remain within `--targets`), `--targets` named an unconfigured target,
  or configuration could not be loaded.

## Examples

Verify everything:

    elspais checks

Run tests then verify:

    elspais checks --run-tests

Stop on first failure:

    elspais checks --run-tests --fail-fast

JSON output for CI:

    elspais checks --format json --lenient
