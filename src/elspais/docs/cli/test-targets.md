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
| `reporter` | string | (required) | Parser format -- one of the names in the reporters table below |
| `results` | string | `""` | Glob pattern for result files (file-channel reporters) |
| `coverage` | string | `""` | Path to an lcov.info or coverage.py JSON file (format auto-detected), relative to `cwd` |
| `match` | string | `"source"` | `"source"` or `"aggregate"` -- matching strategy |
| `classname` | string | `""` (the reporter's own) | `"python-module"` or `"source-file"` -- how this target's results name the test that produced them |
| `environment` | string | `""` (the reporter's own) | `"results-path"` or `"suite-hostname"` -- where the environment a result was recorded in is read from |
| `groups` | list | `[]` (the `default` group) | Which groups this target belongs to |
| `credit_coverage` | string | `"off"` | `"off"`, `"tested"`, or `"verified"` -- lcov_tested credit |
| `min_coverage_fraction` | float | `0.0` | Fraction of impl lines that must be covered (0.0-1.0) |

## Reporters and Matching

### Reporters

<!-- generated: reporters -->
<!-- Rendered from the program's own definitions; edits here are overwritten. Regenerate: python -m elspais.utilities.doc_tables -->

| Reporter | Channel | Kind | Description |
| --- | --- | --- | --- |
| `coverage-json` | file | coverage | Parses the JSON report `coverage json` (coverage.py) writes, in either its aggregate or its per-context form, into per-file line coverage. |
| `coverage-sqlite` | file | coverage | Reads coverage.py's own `.coverage` SQLite data file through coverage.py's public API, so per-test contexts are read compactly rather than through a JSON expansion of them. Needs the `coverage` package (`elspais[coverage]`) importable, and degrades to unattributed coverage where it is not. |
| `flutter-machine` | stdout | results | Parses the `flutter test --machine` JSON-line protocol from the command's stdout. Carries the real `suite.path` and test line, so `match = "source"` binds each result to the test that produced it. |
| `junit` | file | results | Parses JUnit XML result files matched by the `results` glob. Honours an optional per-`<testcase>` `file` attribute (a real source path) and `line` attribute, so `match = "source"` can bind to a scanned test node. |
| `lcov` | file | coverage | Parses an LCOV report -- the `lcov.info` that `flutter test --coverage` and most language toolchains write -- into per-file line coverage. |
| `pytest-json` | file | results | Parses the report pytest's `--json-report` writes, matched by the `results` glob. |

These are the reporters the tool is built with. `register_reporter()` admits
further formats at run time, so a project that registers one has a reporter
this table does not name.
<!-- /generated: reporters -->

A **stdout-channel** reporter captures output directly from the running
`command`; the `results` field is not used.  Capturing it does not hide it: each
line is echoed to elspais's stderr as it arrives, so the run is visible live
while the text itself is kept for the parser.  The command's own stderr is never
captured and passes straight through.

A **file-channel** reporter reads files from disk -- those matched by the
`results` glob for a results-kind reporter, and the `coverage` path for a
coverage-kind one.  Those files can be pre-produced by CI.  A coverage-kind
reporter is chosen by sniffing the file at `coverage`, so a coverage-only
target need not name one.

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

### Coverage-only target with per-test direct attribution

If your suite produces no machine-readable results file (no `--json-report` /
`--junit-xml` step) but you already run under `pytest-cov`, you can still get
`code_tested.attributed_lines` (per-test line attribution, see `elspais docs checks`).
`Verifies:` wiring still comes from `# Verifies:` comments scanned in your
test files -- independent of this target.

**Recommended: point `coverage` at the `.coverage` SQLite database.**
coverage.py already writes this file (its own native data format) to the
repo root whenever you run under `--cov`; nothing extra needs to be
configured to produce it. elspais reads it directly via coverage.py's public
API (`coverage.Coverage`/`coverage.CoverageData`), never by parsing the
SQLite schema itself. Format detection sniffs the file's SQLite header, so
no `reporter` field is required:

```toml
[[scanning.test.targets]]
name     = "unit"
coverage = ".coverage"
```

Run pytest with `--cov-context=test` (pytest-cov's per-test dynamic context,
keyed by pytest nodeid + `|run`/`|setup`/`|teardown`) to populate contexts in
that database:

```bash
pytest tests/ --cov=src/yourpkg --cov-context=test
```

Reading `.coverage` requires the `coverage` package to be importable in
elspais's own interpreter -- install it with `pip install elspais[coverage]`
(or ensure `coverage`/`pytest-cov` are already present, e.g. as a dev
dependency). If it isn't importable, ingestion degrades gracefully:
no line is attributed and `Code Tested` renders `n/a`, with a single
warning naming the extra to install -- it does not fail the build.

A stale `.coverage` file misattributes contexts: line numbers were recorded
against the source as it was at measurement time, so after editing source
files the per-test attribution points at the old line numbers. Regenerate
`.coverage` (rerun the suite) after editing sources.

**Do not** also set `[tool.coverage.run] dynamic_context = "test_function"`.
That is coverage.py's own context-switching (keyed by dotted test qualname,
no file path, no `|run` suffix) and it silently wins over pytest-cov's
`--cov-context=test` when both are active, replacing the nodeid-shaped
contexts elspais expects with an incompatible format -- attribution
then stays `0` everywhere even though contexts are present.

**Alternative: portable but large -- coverage.json with `show_contexts`.**
For small suites where a self-contained JSON report is more convenient than a
binary data file (e.g. shipping a single artifact off-host), the same
contexts can instead be exported into the JSON report:

```toml
[[scanning.test.targets]]
name     = "unit"
coverage = ".results/coverage.json"
```

```toml
# pyproject.toml
[tool.coverage.json]
show_contexts = true   # required to export the per-line contexts map
```

`show_contexts` alone only controls whether the JSON *report* includes the
per-line `contexts` map; `--cov-context=test` still has to record them
during the run, same as above. Be aware this map grows with (statements x
distinct contexts) -- on large suites (thousands of tests) it can produce a
JSON report many gigabytes in size, with a matching spike in graph-build
memory. The `.coverage` SQLite route above stores the same information far
more compactly and does not have this problem, so prefer it unless you have
a specific reason to want a portable JSON artifact.

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
2. **elspais knows what the recorded name means.**  Playwright's JUnit reporter
   omits the per-`<testcase>` `file` attribute and writes the spec's basename
   into `classname`.  Left to itself elspais reads a `classname` as a Python
   module path -- right for pytest, and never a match for a `.spec.ts` -- so
   the result binds to nothing and the coverage figure reads zero.  Declare
   `classname = "source-file"` on the target and the name is read as naming the
   test's source file instead.
3. **The target uses `match = "source"`.**

```toml
[[scanning.test.targets]]
name      = "e2e"
reporter  = "junit"
results   = "test-results/junit.xml"   # glob relative to cwd
match     = "source"                    # per-spec binding
classname = "source-file"               # <testcase classname="foo.spec.ts">
```

A name declared to be a source file is resolved among the tests scanned under
this target's `cwd`, and binds only where it picks out exactly one of them.
Where it picks out none, or more than one, the result binds to nothing and
`elspais checks` reports it under `tests.unmatched_results` saying which
happened -- a name pointing at a file that is not there, or two files sharing
one name.  Post-processing the XML to inject `file="<repo-relative path>"` into
each `<testcase>` still works and takes precedence, since a producer that names
the source file leaves nothing to resolve.

### A reporter that names each test's source

Playwright holds each test's location and uses it only in the message of a
failure. elspais ships a reporter that writes the same report and adds the
location as attributes, so a result binds to the test that produced it rather
than to every test in its file. The reporter is at
`recipes/playwright-junit-reporter.mjs` in the installed package. Copy it into
the repository that runs the tests.

```ts
// playwright.config.ts
reporter: [['./elspais-junit-reporter.mjs', { outputFile: 'junit.xml' }]]
```

```toml
[[scanning.test.targets]]
name        = "e2e"
reporter    = "junit"
results     = "junit.xml"
match       = "source"
environment = "suite-hostname"
line_base   = 1
```

`line_base` is required and is the part most easily missed. The `junit`
reporter declares that its producers count lines from zero, because that is
what pytest writes. This reporter counts from one, as Playwright does, so the
target says so. Without it every line arrives one too high and no result finds
its test.

The reporter keeps `hostname` on each suite, so one report serves both
readings: each project's records are told apart, and each result names the
project it came from.

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

## Groups

Not every target costs the same to run. A unit suite is a compilation away; an
end-to-end suite may need a live backend, a device farm, or an account somebody
pays for. Groups are how a project says which of its targets a run is about.

Declare them as a keyword and a description:

```toml
[scanning.test.groups]
uat    = "End-to-end journeys needing a live stack"
device = "Mobile suites needing a real device or a cloud device farm"
```

Then a target claims the groups it belongs to:

```toml
[[scanning.test.targets]]
name   = "diary-e2e-uat"
groups = ["uat"]
command = "./scripts/run-enroll-e2e.sh"
```

Two names are reserved and cannot be declared:

- **`default`** — what a run executes when it names nothing. A target that
  claims no group belongs here, so a project that declares no groups has every
  target in `default` and a bare run does exactly what it always did.
- **`all`** — every target. Every target belongs to it whether it says so or
  not, so naming `all` names everything.

A group is an **alias for a set of targets**, so it is named where a target is
named — there is no separate flag:

```text
elspais checks --run-tests                  # the `default` group
elspais checks --run-tests --targets uat    # every target in the `uat` group
elspais checks --run-tests --targets all    # everything
elspais checks --run-tests --targets uat elspais-unit   # the group, plus one more
elspais checks --run-tests --targets uat --targets elspais-unit   # the same
```

A run executes every target it names, whether it named it directly or through a
group. To run a narrower set, name the targets.

A description is required with each declaration: a group named `slow` tells a
newcomer nothing about whether their change should have run it, and this is the
only place that explanation has to live. A name that is neither declared nor
reserved is refused — whether a target claims it or a run selects it — because a
selection that quietly selects nothing produces a report that reads exactly like
one whose targets all passed.

Because targets and groups are named in one place, they share one namespace: a
configuration declaring a group with the same name as a test target is refused
when it is read, rather than resolved by a precedence rule every reader of that
configuration would then have to know.

## Per-PR selectivity

`--targets NAME ...` (accepted by `checks`, `summary`, and `trace`) names the
subset of `[[scanning.test.targets]]` that are **fresh** for this invocation.
Everything else is the **complement** — targets not named on `--targets`.
A run that covers every configured target is a full run; one that leaves any
configured target out is selective, and that distinction follows from which
targets ran rather than from whether a flag was passed.

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
per-requirement `verified` value, depending on whether prior result data
exists for them:

- **`(baseline)`** — carried. The target has existing RESULT data from a
  previous run; that verdict is reused and rendered with a `(baseline)`
  suffix (e.g. `4/4 100% (baseline)`). A carried **failing** target still
  fails/gates — carrying only skips re-execution, it never launders a
  failure into a pass. The same provenance is selectable on its own as
  `verified.carried`, which states `baseline` or `fresh` in a cell and a
  boolean in json, so a reader taking only the numbers still gets it.
- **`—`** (em dash) — no baseline. The target has test references (so
  coverage is expected) but zero result data at all — nothing to carry.
  This renders as skipped and is **not** gating; it's treated as "not run
  this PR" rather than a regression. Nothing was measured, so the numbers
  behind the figure are absent rather than zero: `verified.count`,
  `verified.ratio` and `verified.carried` each state `null` in json and
  `n/a` in a cell.

A `> Legend: ...` line explaining both markers is appended to `trace`'s
markdown output whenever at least one row actually used one (never shown on
a full run, and never shown for `--dimension uat`, which does not state
`verified`).

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

## The Environment a Result Was Recorded In

One test suite run across several devices or browsers writes one result for
each of them. Each of those results is held on its own, and it may also carry
the environment it was recorded in.

A result carries an environment only where the target declares where to read
one. There is no default, because the same field means different things in
different producers: the JUnit `hostname` attribute holds the machine that ran
the tests when pytest writes it, and the project under test when Playwright
does. A label naming the wrong thing is worse than no label, so the project
says which it has.

Two sources are available:

| Source | Reads |
|--------|-------|
| `results-path` | The part of the path that the wildcard in this target's `results` glob matched |
| `suite-hostname` | The `hostname` attribute of the `<testsuite>` holding the record |

Use `results-path` where each environment writes its own artifact:

```toml
[[scanning.test.targets]]
name        = "devices"
reporter    = "junit"
results     = "evidence/*/journey-results.xml"
environment = "results-path"            # evidence/pixel-8/... -> "pixel-8"
```

The environment is what the wildcard stood for, and not the whole path
segment it sits in. A pattern names the environment inside a segment as
readily as it names a whole one:

```toml
results     = "evidence/junit-*.xml"    # evidence/junit-pixel-8.xml -> "pixel-8"
```

Use `suite-hostname` where one artifact holds every environment and the
producer writes the environment into the suite:

```toml
[[scanning.test.targets]]
name        = "browsers"
reporter    = "junit"
results     = "test-results/junit.xml"
environment = "suite-hostname"          # <testsuite hostname="firefox">
```

A declared source does not always give an answer. A `results` glob holding
`**`, holding more than one wildcard segment, or holding more than one
wildcard within its wildcard segment, does not say which part of the path is
the environment. A record may also hold no hostname at all. In each of these
the result carries no environment and `elspais checks` reports that none was
derived. The tool does not guess, because a guess reads exactly like a
reading in every figure that follows.

### Where the Environment Is Shown

An environment belongs to the result that carries it, and it is shown
there. The trace viewer prints it beside the result in the results panel,
`elspais -v checks --tests` names it in each failing-result finding, and the MCP
tools that read or list results carry it as a key of its own. A result
that carries none is presented exactly as it was before.

The name of the test does not change. One test is one test wherever it
ran, so the environment is never added to its name.

`elspais checks` counts RESULTS, not tests. One test run in several
environments gives one result for each of them, and the tally counts them
all. A result that errored counts as a failure, because the test did not
pass.
