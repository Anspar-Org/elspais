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

## Target Folders and Fresh Results

Every target writes into a folder of its own, `<output_root>/<name>`.
`output_root` is set under `[scanning.test]` and defaults to `.results`. A
target's `results` and `coverage` name files inside that folder. These paths
are relative to the folder -- `results = "junit.xml"` -- for every value of the
target's `cwd`. When elspais reads the configuration, it
refuses an absolute path or a path that climbs out with `..`. The refusal
message names the folder. Consequently, two targets never overwrite each
other's reports.

When elspais runs a target (`elspais checks --run-tests`), it takes these
steps:

1. It empties the target's folder. Consequently, elspais cannot read a file
   from an earlier run as the results of this run.
2. It records a fingerprint of the target's inputs in the folder. The
   fingerprint holds the path of every input file and a digest of its content.
3. It runs `command` with the absolute path of the folder in the
   `ELSPAIS_TARGET_OUTPUT` environment variable. The command reads that
   variable to find where to write.
4. It notes any input that changed during the run.

`elspais checks` then judges the results of each target separately. The
results are **fresh** while no input has changed since the run began. This
rule holds whichever run produced them. Results that a previous run left are
as good as new ones against the same inputs. `elspais checks` reports nothing
about fresh results. The results are **stale** when an input changed or when
no run recorded a fingerprint for them. If an input changed, then the finding
names it. `tests.results_stale` states which reason applies. File timestamps
play no part. Results read from an *Evidence Snapshot* are judged by the
snapshot's tree digest instead: a snapshot whose digest differs from that of
the tree of the repository naming it is stale, and the finding names the
snapshot directory. A federation member's snapshot is judged against that
member's tree.

Every report that reads results applies the same judgement. A result of a
target whose results are stale was produced by a tree other than the one
being reported on, so it is **carried** whatever the invocation selected:
`trace` marks the figure it makes `(baseline)`, `summary` counts its target
among the carried ones, and `tests.results` states how many results are
stale. A stale failure is still a failure, and its finding states why the
results are stale. Run the target again to replace it.

A target's **inputs** are every file in the repository by default, whether or
not git tracks it. Three sets of paths are never inputs: the output root, the
*Evidence Snapshot* directory that `[scanning.test] evidence` names, and the
paths that the global `[scanning] skip` list names. The per-kind
`skip_dirs`/`skip_files` of `[scanning.spec]`, `[scanning.code]` and the rest
do not apply here. Put anything that changes during every run in that global
list. Examples are `.git`, `.elspais/`, and caches that a test tool writes
while it runs, such as `**/.pytest_cache` and `.coverage`. `elspais init`
writes the common ones.

Write a skip entry so that it reaches every place the file or directory can
appear. An entry holding a `/` is a path from the repository root, for a file
and a directory alike, so `**/.pytest_cache` skips that directory at any depth
and `**/.coverage` skips that file at any depth. An entry of a single name
skips a file of that name at any depth, but a directory of that name only at
the repository root: a bare `.pytest_cache` leaves `pkg/.pytest_cache` among
the inputs, and every run that writes it reads as stale. See
`elspais docs ignore` for the full rule.
A target narrows its inputs with `inputs`. `inputs` has exactly the same form
as a scanning kind's file selection:

```toml
[[scanning.test.targets]]
name    = "unit"
command = "pytest tests/ --junitxml=$ELSPAIS_TARGET_OUTPUT/junit.xml"
reporter = "junit"
results = "junit.xml"
inputs  = { skip_dirs = ["docs", "spec"], skip_files = ["*.md"] }
```

`directories` and `file_patterns` choose the files. `directories` names
directories only, from the repository root. `skip_dirs` and `skip_files`
remove files. A removal wins over a choice. The example keeps every file
except documentation. Edits to documentation cannot change what the tests
report.

### Recording a run elspais did not execute

A git hook or a CI job that runs a target's tests itself brackets the run.
Consequently, its results carry a fingerprint:

```bash
out=$(elspais fingerprint start unit)      # empties the folder, prints it
ELSPAIS_TARGET_OUTPUT="$out" pytest tests/ --junitxml="$out/junit.xml"
elspais fingerprint finish unit            # notes inputs that changed meanwhile
```

elspais refuses a `finish` that no `start` began. The reason is that `start`
empties the folder. Consequently, elspais cannot stamp results that already
sit in the folder as the results of a run. Every recorder computes the
fingerprint in the same way. The fingerprint records what a run saw. It is
not evidence of where results came from.

Copy results from elsewhere with their folder, fingerprint included. An
example is a baseline that another job produced. Such results read as fresh
exactly while the inputs here match the inputs they ran against. The
fingerprint records the root of the tree the run executed in, and elspais
reads an absolute path a reporter wrote under that root relative to it.
Consequently, results keep matching their tests after the tree moves or is
copied to another directory.

`elspais fingerprint` writes no [record of the last run](#the-record-of-the-last-run).
That record lists only the targets elspais itself executed, so a report after
a bracketed run names the target with `--targets` rather than `last-run`.

### The fingerprint file

The fingerprint is the JSON file `.elspais-run.json` in the target's folder.
Its `version` field states the format. Its `root` field names the directory
the run executed in. Its `inputs` field lists one object for each input file,
with a `path` field and a `digest` field. The digest is the
SHA-256 of the file's content. No path is ever a JSON key. Consequently, a
secret scanner that looks for a secret-like key beside a long hex value finds
nothing in the file. The file is safe to include in build output that a
secret scan reads. elspais reads a fingerprint of another format version as
no fingerprint. Consequently, its results read as stale until one fresh run
rewrites the fingerprint.

### A run in progress

A run is in progress from the time its fingerprint is written by `start` until
`finish` records its end. While it is, its folder holds results and coverage
that are partial or not yet written, so elspais reads nothing from that folder.
`elspais checks` reports the target under `tests.run_in_progress` (info),
stating when the run started, and does not judge its freshness. A target the
run expects (`--expect`) needs its results, so a run of it in progress also
fails `tests.ingestion_fault`: its results are missing. A run that stopped without `finish` reads the same way:
the fingerprint cannot tell a run that is still going from one that died, so the
report states the start time and leaves that judgement to the reader.

### The record of the last run

Every run that executes targets, `elspais test` or
`elspais checks --run-tests`, records which targets it executed. The record is
the JSON file `.elspais-last-run.json` in the output root, by default
`.results/.elspais-last-run.json`. It sits beside the target folders and never
inside one, because a target's folder is emptied when that target runs. A
target name cannot start with `.`, so no target folder can take the record's
name.

```json
{
 "executed": ["api", "unit"],
 "finished_at": "2026-01-01T12:00:00+00:00",
 "version": 1
}
```

`version` states the format. `executed` lists the names of the targets the
run executed, sorted. `finished_at` is the time the run ended, in ISO 8601
UTC. Each run replaces the record of the run before it. A target is listed
only if its run began: a target refused before it started, such as one whose
`cwd` resolves outside the repository, is not listed, and neither is a target
that `--fail-fast` kept from starting. A run that executed nothing, such as a
`--stale-only` run whose selected targets were all fresh, records an empty
list.

A later `summary` or `trace` names the record with `--targets last-run` (see
[Groups](#groups)), so it marks fresh exactly the results that run produced.

### Results written while a daemon is serving

A daemon or viewer serving the graph watches every file the graph was built
from, in every member of the federation: configuration, the files the spec,
code and test scans select, and each target's folder -- its fingerprint, its
results and its coverage. A file the scans skip or decline, such as a
`__pycache__` file, is not watched, so writing one does not rebuild the graph;
a new file the scans select is. Results written after the daemon started, by
`elspais checks --run-tests` or by a recorder bracketing its run with
`elspais fingerprint`, are read by the next command the daemon answers. While a
run is in progress only its fingerprint is watched, so the coverage file a
suite writes for minutes does not rebuild the graph on every request; `finish`
rewrites the fingerprint, and that rebuilds it.

A daemon does not rebuild while it holds unsaved changes. Until they are saved
or discarded, every answer it gives says that its graph predates the files that
changed and names them: the command line prints a warning, `/api/check-freshness`
lists them in `stale_files`, and the MCP `get_graph_status` tool lists them in
`graph_predates`.

The word *fresh* in [Per-PR selectivity](#per-pr-selectivity) has another
meaning. There it names the targets that the caller tells a reporting command
ran in this invocation. `--stale-only` joins the two: it uses the fingerprint
judgement to decide which targets to execute, and those targets are the ones a
later `summary` or `trace` names as fresh, with `--targets last-run`.

## Target Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | string | (required) | Unique label for this target; appears in output |
| `cwd` | string | `""` (repo root) | Directory relative to repo root where the command runs, and the base for relative source paths in its coverage report |
| `command` | string | (omit in CI) | Shell command to execute when `--run-tests` is passed |
| `reporter` | string | (required) | Parser format -- one of the names in the reporters table below |
| `results` | string | `""` | Glob pattern for result files (file-channel reporters), relative to the target's folder |
| `coverage` | string | `""` | Path to an lcov.info, coverage.py JSON or `.coverage` file (format auto-detected), relative to the target's folder |
| `inputs` | table | every file | The files whose change makes this target's results stale: `directories`, `file_patterns`, `skip_dirs`, `skip_files` |
| `match` | string | `"source"` | `"source"` or `"aggregate"` -- matching strategy |
| `classname` | string | `""` (the reporter's own) | `"python-module"` or `"source-file"` -- how this target's results name the test that produced them |
| `environment` | string | `""` (the reporter's own) | `"results-path"` or `"suite-hostname"` -- where the environment a result was recorded in is read from |
| `groups` | list | `[]` (the `default` group) | Which groups this target belongs to |
| `resources` | list | `[]` | Declared shared resources this target uses; two targets naming a common one never run at the same time (see [Concurrent Targets](#concurrent-targets)) |
| `credit_coverage` | string | `"off"` | `"off"`, `"tested"`, or `"verified"` -- lcov_tested credit |
| `min_coverage_fraction` | float | `0.0` | Fraction of impl lines that must be covered (0.0-1.0) |

The target's folder is `<output_root>/<name>`, from the repository root.
elspais reads `results` and `coverage` from that folder. Consequently, a
target with `cwd = "app"` still writes `coverage = "lcov.info"`. `cwd` does
not move the folder.

`cwd` sets where the command runs. It is also the base for a relative source
path inside the coverage report, because the measuring tool writes the path
from there. Flutter writes `SF:lib/src/end_event.dart` for a package in `app/`,
and elspais reads that line as `app/lib/src/end_event.dart`. A target without
`cwd` runs in the repository root, and its relative paths are read from the
root. An absolute path is read as it stands. A path that names no scanned file
under that base credits nothing.

## Reporters and Matching

### Reporters

<!-- generated: reporters -->
<!-- Rendered from the program's own definitions; edits here are overwritten. Regenerate: python -m elspais.utilities.doc_tables -->

| Reporter | Channel | Kind | Description |
| --- | --- | --- | --- |
| `coverage-json` | file | coverage | Parses the JSON report `coverage json` (coverage.py) writes, in either its aggregate or its per-context form, into per-file line coverage. |
| `coverage-sqlite` | file | coverage | Reads coverage.py's own `.coverage` SQLite data file through coverage.py's public API, so per-test contexts are read compactly rather than through a JSON expansion of them. Needs the `coverage` package (`elspais[coverage]`) importable, and degrades to unattributed coverage where it is not. |
| `evidence-snapshot` | file | results | Reads the `results.jsonl` of an Evidence Snapshot. A build reads it for each target that has not run in the tree and that the run does not execute, from the directory `[scanning.test] evidence` names, tagging those results carried. |
| `flutter-machine` | stdout | results | Parses the `flutter test --machine` JSON-line protocol from the command's stdout. Carries the file and line where each test is declared, and the file that executed it, so `match = "source"` binds each result to its test, including a test declared in a shared file that a runner file executes. A test run in a browser records no Dart line, so its result binds by the test's full name. Each result also carries its duration and the output its test printed. |
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
(e.g., the declaring file and line from `flutter-machine`).  A result also
reaches a citation written above the `group()` that holds its test.
Consequently, a citation on a group takes its verdict from the tests inside
it.  If a line does not resolve to a known test node (shared-helper or
generated tests), then elspais links the result to the file only.  The result
names no test.  Consequently, it credits and flags nothing.  The assertions
its file's tests cite stay awaiting a result.
Requires a reporter that emits real file paths and, for per-test resolution,
the test's source line (`flutter-machine`).

A test can be declared in a shared scenario file and executed through a
runner file, one runner for each backend. `flutter-machine` then reports the
file and line of the declaration (`test.url`, `test.line`) and the runner
(`suite.path`). elspais binds the result to the test at the declaration,
where its `Verifies:` citations are. Each runner's run is a result of that one
test. The test passes only if every run passed. A failure names the runner
that produced it, as `(run by <runner file>)`.

A result that records no source line binds by its test's full name instead.
The full name is the descriptions of the `group()` calls that enclose the test
and the test's own description, in order, joined by single spaces -- the name
the Dart runner records. A test run in a browser (`flutter test --platform
chrome`) needs this: its runner reports a line of the compiled JavaScript,
which is no line of the Dart file, so elspais keeps only the suite file and
the name. elspais knows a description only where the source writes it as
string literals (adjacent literals join, as in Dart). A description that
interpolates a value (`'adds $count items'`), or that is not a literal at all,
leaves the test with no full name. A result whose name matches no test, or
matches more than one test in its file, is linked to its file only and credits
nothing; `tests.file_bound_results` reports it, saying whether its name matched
no test or several. A recorded line is never overridden by a name.

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
attribution -- elspais reads the file and line where the Flutter test machine
protocol says each test is declared, and matches each result to the specific
test node at that `(path, line)` in the graph. A test declared in a shared
scenario file binds there, whichever runner file executed it.

### Single-package example

```toml
[[scanning.test.targets]]
name        = "app"
cwd         = "app"
command     = "flutter test --machine --coverage --coverage-path=$ELSPAIS_TARGET_OUTPUT/lcov.info"
reporter    = "flutter-machine"
coverage    = "lcov.info"
match       = "source"
credit_coverage = "verified"
```

`--coverage-path` writes the lcov report into the target's folder,
`.results/app/`. `coverage` names the report relative to that folder. The
`SF:` paths inside the report are relative to the package, and elspais reads
them from `cwd`.

### Two-package example (one with a shared DB)

```toml
[scanning.test]
concurrency = 2

[scanning.test.resources]
db = "The local Postgres instance the backend suites share"

[[scanning.test.targets]]
name        = "app"
cwd         = "app"
command     = "flutter test --machine --coverage --coverage-path=$ELSPAIS_TARGET_OUTPUT/lcov.info"
reporter    = "flutter-machine"
coverage    = "lcov.info"
match       = "source"
credit_coverage = "verified"

[[scanning.test.targets]]
name        = "backend"
cwd         = "backend"
command     = "flutter test --machine --coverage --concurrency=1 --coverage-path=$ELSPAIS_TARGET_OUTPUT/lcov.info"
reporter    = "flutter-machine"
coverage    = "lcov.info"
match       = "source"
credit_coverage = "verified"
resources   = ["db"]
```

Use one `[[scanning.test.targets]]` block per package.  The `cwd` field
runs each package's tests in its own directory. Each target's folder keeps
its coverage apart from the other's. With `concurrency = 2` the two packages
run at the same time. `backend` names the `db` resource, so any other target
that names `db` waits until `backend` finishes, and `backend` waits for it.

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
command = "flutter test --machine --coverage --concurrency=1 --coverage-path=$ELSPAIS_TARGET_OUTPUT/lcov.info"
```

Flutter's `--concurrency` and elspais's `[scanning.test] concurrency` govern
different things. Flutter's flag sets how many test files run at once inside
one target. elspais's setting sets how many targets run at once. When two
targets share the database, name it in `resources` on both, so that elspais
never runs them at the same time.

**Coverage file location.**  `flutter test --coverage` without
`--coverage-path` writes to `<package-root>/coverage/lcov.info`. That path is
outside the target's folder. Consequently, elspais refuses a `coverage` path
there.  Pass
`--coverage-path=$ELSPAIS_TARGET_OUTPUT/lcov.info` and set:

```toml
coverage = "lcov.info"
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
command  = "pytest tests/ --json-report --json-report-file=$ELSPAIS_TARGET_OUTPUT/pytest.json"
reporter = "pytest-json"
results  = "pytest.json"
match    = "aggregate"
```

For JUnit XML output (compatible with many CI systems):

```toml
[[scanning.test.targets]]
name     = "unit"
command  = "pytest tests/ --junit-xml=$ELSPAIS_TARGET_OUTPUT/TEST-unit.xml"
reporter = "junit"
results  = "TEST-*.xml"
match    = "aggregate"
```

### Coverage-only target with per-test direct attribution

If your suite produces no machine-readable results file (no `--json-report` /
`--junit-xml` step) but you already run under `pytest-cov`, you can still get
`code_tested.attributed_lines` (per-test line attribution, see `elspais docs checks`).
`Verifies:` wiring still comes from `# Verifies:` comments scanned in your
test files -- independent of this target.

**Recommended: point `coverage` at the `.coverage` SQLite database.**
coverage.py already writes this file (its own native data format) whenever you
run under `--cov`. `COVERAGE_FILE` puts the file in the target's folder.
elspais reads it directly via coverage.py's public
API (`coverage.Coverage`/`coverage.CoverageData`), never by parsing the
SQLite schema itself. Format detection sniffs the file's SQLite header, so
no `reporter` field is required:

```toml
[[scanning.test.targets]]
name     = "unit"
command  = "COVERAGE_FILE=$ELSPAIS_TARGET_OUTPUT/.coverage pytest tests/ --cov=src/yourpkg --cov-context=test"
coverage = ".coverage"
```

`--cov-context=test` (pytest-cov's per-test dynamic context, keyed by pytest
nodeid + `|run`/`|setup`/`|teardown`) populates contexts in that database.

Reading `.coverage` requires the `coverage` package to be importable in
elspais's own interpreter -- install it with `pip install elspais[coverage]`
(or ensure `coverage`/`pytest-cov` are already present, e.g. as a dev
dependency). If it isn't importable, ingestion degrades gracefully:
no line is attributed and `Code Tested` renders `n/a`, with a single
warning naming the extra to install -- it does not fail the build.

A stale `.coverage` file misattributes contexts: line numbers were recorded
against the source as it was at measurement time, so after editing source
files the per-test attribution points at the old line numbers. The target's
fingerprint reports exactly this condition. After a source edit, its results
read as stale until the suite runs again.

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
command  = "pytest tests/ --cov=src/yourpkg --cov-context=test --cov-report=json:$ELSPAIS_TARGET_OUTPUT/coverage.json"
coverage = "coverage.json"
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
   that reports each `test(...)` call, and add the spec directories /
   `*.spec.ts` to the test `directories` / `file_patterns`.  Each
   attribution record carries `file`, `function`, `line`, an optional `class`
   and an optional `end_line`.  The name is the test's own -- an attribution
   record names one test, so its spelling decides nothing -- and `line` is
   the line the test is declared on.  A citation written above that line
   belongs to the test below it, as it does in every language elspais scans
   itself.  This rule also holds where an attribution record carries no
   `end_line`.  elspais never reads the comments directly above a test as
   the body of the test before it.
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
results   = "junit.xml"   # glob relative to the target's folder
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

A result whose source file resolves but whose line matches no test in it binds
to every test in that file. It names no test, so it credits no assertion:
crediting it would credit the assertions of tests that possibly did not run.
`elspais checks` reports such results under `tests.file_bound_results`, one
finding per artifact holding them, naming the tests they could have bound to,
and `elspais summary` states their number beside its coverage figures. A
producer that records each test's source line removes the condition; for
Playwright, use the reporter below. For a Dart test run in a browser, which
records no source line, give each test a unique literal name.

### A reporter that names each test's source

Playwright holds each test's location and uses it only in the message of a
failure. elspais ships a reporter that writes the same report and adds the
location as attributes, so a result binds to the test that produced it rather
than to every test in its file. The reporter is at
`recipes/playwright-junit-reporter.mjs` in the installed package. Copy it into
the repository that runs the tests.

```ts
// playwright.config.ts
reporter: [['./elspais-junit-reporter.mjs', { outputFile: `${process.env.ELSPAIS_TARGET_OUTPUT}/junit.xml` }]]
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
readings: each project's result records are told apart, and each result names the
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

# Command to run when `elspais checks --run-tests` is invoked. The command
# writes into the target's folder. The command reads the folder path from
# ELSPAIS_TARGET_OUTPUT.
# Omit this field in CI -- elspais will ingest pre-produced result files.
command = "my-test-runner --output $ELSPAIS_TARGET_OUTPUT/results.xml"

# Reporter format: "junit" | "pytest-json" | "flutter-machine"
reporter = "junit"

# Glob for result files (file-channel reporters), relative to the target's
# folder <output_root>/<name> -- here .results/my-suite/*.xml, for every cwd.
results = "*.xml"

# Path to an lcov.info or coverage.py JSON file (format auto-detected),
# relative to the target's folder. Omit if no coverage report.
# coverage = "lcov.info"

# inputs names the files whose change makes this target's results stale. The
# default is every file in the repository. inputs has the same form as a
# scanning kind's file selection.
# inputs = { directories = ["packages/my-package"] }

# Shared resources this target uses, each declared under
# [scanning.test.resources] with a description. Two targets naming a common
# resource never run at the same time. Matters only where
# [scanning.test] concurrency is above 1.
# resources = ["db"]

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
produced.  The CI step writes into the target's folder. The CI step also
brackets its run with `elspais fingerprint start` and `finish` (see
[Recording a run elspais did not execute](#recording-a-run-elspais-did-not-execute)).
Consequently, the results read as fresh:

```toml
[[scanning.test.targets]]
name     = "app"
cwd      = "app"
# No `command` -- CI already ran flutter test
reporter = "flutter-machine"
# flutter-machine is a stdout reporter, so `results` is unused.
# To get per-test pass/fail attribution in CI, save `flutter test --machine`
# output to a file in the target's folder and point `results` at it:
#   results = "test-results.jsonl"
# Without `results`, only coverage credit is applied (no pass/fail signal).
coverage = "lcov.info"
match    = "source"
credit_coverage = "verified"
```

Run elspais in CI after the test step:

```text
elspais checks
```

### Parallel jobs and one gate

`elspais test` executes test targets and records their results. It evaluates
no check. Its exit code is 1 if any target it executed failed, and 0 if all
passed. It selects with `--targets` exactly as `checks --run-tests` does, and
`elspais test --stale-only` executes only the selected targets whose results
are not fresh (see [Executing only what is stale](#executing-only-what-is-stale)).

Split the suite across jobs with `elspais test`, collect each job's target
folders, and evaluate the checks once:

```text
# job 1                      # job 2
elspais test --targets unit  elspais test --targets postgres

# gate job, after the results of both are in place
elspais checks --expect unit postgres
```

A job then fails only for its own tests. A specification error fails the
gate alone. `--expect` makes a missing result of a named target a fault, so
the gate stays strict.

`elspais test` reads nothing while a command runs. Consequently, every target
it executes whose reporter reads test results must declare a `results` pattern
that matches what the command writes into `$ELSPAIS_TARGET_OUTPUT`. A stdout
reporter's output is not recorded on its own. The command refuses (exit 2),
before it runs anything, a selection that holds such a target with no
`results` pattern. A coverage target is not affected.

Separate jobs divide a suite across machines. On one machine, `[scanning.test]
concurrency` runs several targets of one run at the same time, and
`--concurrency N` sets that number for one run (see
[Concurrent Targets](#concurrent-targets)).

## Concurrent Targets

`[scanning.test] concurrency` is the most targets one run executes at the same
time. It is a whole number of 1 or more, and it applies to
`elspais checks --run-tests` and `elspais test` alike.

```toml
[scanning.test]
concurrency = 4
```

With `concurrency = 1`, the default, targets run one at a time in declaration
order. Their output passes straight through to the terminal.

With a larger value, a run schedules its targets as follows:

- Targets start in declaration order as places free up.
- Two targets that name a common shared resource never run at the same time.
  All other targets may overlap.
- A target held back by a resource does not hold back the targets after it.
  The next target that can start, starts.

elspais schedules targets, not tests. A target's own runner owns the
parallelism inside that target, such as `pytest -n` or
`flutter test --concurrency`.

`--concurrency N`, on `elspais test` and on `elspais checks --run-tests`,
replaces `[scanning.test] concurrency` for that run alone. A CI job on a
larger machine raises it; `--concurrency 1` runs the targets one at a time, so
their output reads one target after another. A value below 1 is refused
(exit 2):

```text
error: --concurrency 0 must be a whole number of targets, 1 or more; 1 runs the targets one at a time
```

`elspais checks` without `--run-tests` executes nothing, so it refuses
`--concurrency` as it refuses `--targets`.

### Output of targets that run together

Lines from targets that run together arrive interleaved. Consequently, every
line a target writes, on stdout and on stderr, is shown with the target's name
in front of it. A banner names each target as it starts, and a tally line
states its outcome and elapsed time:

```text
>>> Running 'unit' target: pytest tests/unit --junitxml=$ELSPAIS_TARGET_OUTPUT/junit.xml
>>> Running 'backend' target: flutter test --machine --coverage ...
[unit] ============================= test session starts ==============================
[backend] {"protocolVersion":"0.1.1","runnerVersion":"1.25.0","type":"start"}
<<< unit: passed (1.2s)
<<< backend: FAILED (exit 3) (4.7s)
```

The stdout of a file-channel target goes to elspais's stdout, and its stderr
goes to elspais's stderr. The stdout of a stdout-channel target is its results,
so elspais shows it on stderr and captures it for that target alone. A target
never reads another target's output as its results. No target reads stdin:
each one runs with its stdin at `/dev/null`.

### Shared resources

Each target already writes into a folder of its own, so two targets never
write the same report. What two targets can still share is outside elspais: a
database, a network port, a device or emulator, a local service stack. Declare
each such resource with a description of what it is, and have each target name
the resources it uses:

```toml
[scanning.test.resources]
db          = "The local Postgres instance the integration suites share"
"port-8080" = "The port the local API server listens on"

[[scanning.test.targets]]
name      = "api"
command   = "pytest tests/api --junitxml=$ELSPAIS_TARGET_OUTPUT/junit.xml"
reporter  = "junit"
results   = "junit.xml"
resources = ["db", "port-8080"]

[[scanning.test.targets]]
name      = "migrations"
command   = "pytest tests/migrations --junitxml=$ELSPAIS_TARGET_OUTPUT/junit.xml"
reporter  = "junit"
results   = "junit.xml"
resources = ["db"]
```

Here `api` and `migrations` never overlap, and every other target may run
beside either of them. The description is required, because the declaration
is the only place a reader learns what the name stands for. Names are matched
without regard to case. A configuration that declares two names differing only
in case is refused. A target that names a resource the project does not
declare is refused when the configuration is read. A misspelled name would
otherwise let two conflicting targets overlap without any warning.

Concurrency is off by default for this reason. Targets that share something no
declaration names, such as a database, would corrupt each other's runs.

### Writing outside the target's folder

A target's inputs default to every file in the repository (see
[Target Folders and Fresh Results](#target-folders-and-fresh-results)). A
target that writes outside its own folder while another target runs changes
that other target's inputs. Examples are a tool cache, or a coverage file in
the repository root. The other target's results then read as stale:
`tests.results_stale` reports that its inputs changed while it ran, and names
the file. Put such paths in the global
`[scanning] skip` list, or narrow the other target's `inputs`.

### Stopping at the first failure

`--fail-fast` stops a run at the first target that fails. With
`concurrency = 1`, no target after the failing one runs. With a larger value,
no further target starts, and the targets already running finish. elspais does
not stop a running target, because a stopped target leaves a run that records
a start and no end. Its results would then read as in progress. In
`elspais checks --run-tests`, a failure under `--fail-fast` also skips the
checks pass.

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

Four names are reserved. A project cannot declare them, give them to a
target, or have a target claim them:

- **`default`** — what a run executes when it names nothing. A target that
  claims no group belongs here, so a project that declares no groups has every
  target in `default` and a bare run does exactly what it always did. If
  every target claims another group, then `default` holds no target. The tool
  then refuses a run naming nothing (exit 2) and does not report on nothing.
  Bare `summary`, bare `trace` and bare `checks --run-tests` are such runs.
- **`all`** — every target. Every target belongs to it whether it says so or
  not, so naming `all` names everything.
- **`none`** — no target. A run naming it marks no target fresh.
  Consequently, `summary` and `trace` render every result read from disk as
  carried from an earlier run, an associate's results included.
- **`last-run`** — the targets that the last run of `elspais test` or
  `elspais checks --run-tests` executed, read from its record (see
  [The record of the last run](#the-record-of-the-last-run)). It is read by
  `summary`, `trace` and composed reports holding either, so a report marks
  those results fresh and every other result carried, with no names passed
  by hand. It combines with other names like any group. If the record lists
  no target, then `last-run` means what `none` means.

A group is an **alias for a set of targets**, so it is named where a target is
named — there is no separate flag:

```text
elspais checks --run-tests                  # the `default` group
elspais checks --run-tests --targets uat    # every target in the `uat` group
elspais checks --run-tests --targets all    # everything
elspais checks --run-tests --targets uat elspais-unit   # the group, plus one more
elspais checks --run-tests --targets uat --targets elspais-unit   # the same
elspais trace --targets none                # every result carried
elspais trace --targets last-run            # fresh: what the last run executed
```

A run executes every target it names, whether it named it directly or through a
group. To run a narrower set, name the targets.

A description is required with each declaration: a group named `slow` tells a
newcomer nothing about whether their change should have run it, and this is the
only place that explanation has to live. A name that is neither declared nor
reserved is refused — whether a target claims it or a run selects it — because a
selection that quietly selects nothing produces a report that reads exactly like
one whose targets all passed. For the same reason, the tool refuses a
selection that resolves to no target (exit 2). One case is a named selection,
such as a declared group no target claims. The other case is a run naming
nothing where `default` holds no target. A project that configures no test
targets at all is exempt. On `summary` and `trace`, a run names `none` to ask
for a run in which nothing ran fresh. No other way exists. The refusal states
this:

```text
error: --targets <names> stands for no configured target. To report every result as carried from an earlier run, name the reserved group `none` (--targets none).
error: the `default` group holds no test target, so a run naming no targets selects none. Name targets or groups with --targets, or have a target claim the `default` group, or name the reserved group `none` (--targets none) to report every result as carried from an earlier run.
```

`checks --run-tests` executes what it selects. Consequently, a selection of
no target leaves it nothing to run, `none` included. Its refusal lists the
names the user could give instead:

```text
error: --targets <names> names no test target to run. Configured targets: .... Groups: ....
error: --targets none selects no test target, so there is nothing to run. Configured targets: .... Groups: ....
error: the `default` group holds no test target, so a run naming no targets selects none. Name targets or groups with --targets, or have a target claim the `default` group. Configured targets: .... Groups: ....
```

`last-run` is refused (exit 2) where it cannot say which results ran fresh.
With no readable record, the refusal names the record's absolute path and how to write
one. With a record that names a target the configuration no longer holds, it
names that target:

```text
error: --targets last-run names the targets the last recorded run executed, and no readable record exists at <repo>/.results/.elspais-last-run.json. Run `elspais test` or `elspais checks --run-tests` to write one, or name the targets with --targets.
error: --targets last-run: the last recorded run (<repo>/.results/.elspais-last-run.json) executed <names>, which the configuration no longer holds. Run the targets again to replace the record, or name the targets with --targets. Configured targets: ....
```

A run that executes targets, and `--expect`, each ask about the run in
progress, so both refuse `last-run` (exit 2). The refusal names the flag that
carried it, `--targets` or `--expect`:

```text
error: --targets last-run names the targets an earlier run executed, and --targets here names what this run itself covers. Name the targets or groups instead; `last-run` is read by `summary` and `trace` to mark the last run's results fresh.
```

Because targets and groups are named in one place, they share one namespace: a
configuration declaring a group with the same name as a test target is refused
when it is read, rather than resolved by a precedence rule every reader of that
configuration would then have to know.

### Targets of a federation member

A run that executes targets reaches another federation member only where it
names that member's target or group as `NAMESPACE:NAME`. The name resolves by
that member's own configuration. The target executes with that member's
configuration and repository root, and writes into that member's output area.
A bare name, a run naming nothing, and the `default` group select only the
invoking repository's targets:

```text
elspais test --targets LIB:unit              # the member LIB's `unit` target, in LIB
elspais checks --run-tests --targets unit LIB:unit   # one in each repository
```

A member's target executes a command that the member's configuration declares.
Consequently, the reader names it explicitly. A namespace no member declares,
and a name the member does not declare, are refused (exit 2) before anything
runs. `checks --run-tests` reads a member's results from its output area, so it
refuses a member's target whose reporter reads test results and that declares
no `results` pattern. `summary` and `trace` execute no target. Their
`--targets` names only the invoking repository's targets, and they refuse a
`NAMESPACE:NAME` as an unknown name.

## Per-PR selectivity

`--targets NAME ...` (accepted by `checks --run-tests`, `summary` and `trace`,
alone or composed with other report sections) names the
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
  earlier run. `--targets none` marks no target fresh. Consequently, every
  result read from disk renders as carried. `--targets last-run` marks fresh
  the targets the last executing run recorded, so the names need not be
  repeated. The names are the invoking repository's targets. A run of those
  executes no target of an associate, so wherever `--targets` is given, every
  result an associate holds renders as carried.

On `trace`, the complement (non-named) targets render one of two ways in the
per-requirement `verified` value, depending on whether prior result data
exists for them:

- **`(baseline)`** — carried. The target has existing RESULT data from a
  previous run, or its results are stale (see the freshness judgement
  above); that verdict is reused and rendered with a `(baseline)`
  suffix (e.g. `4/4 100% (baseline)`). A requirement credited through the
  requirements that refine it carries the suffix when every result behind
  its figure, its own and those conducted to it, was carried, and loses it
  as soon as one fresh result contributes. A carried **failing** target still
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

A `> Legend: ...` line is appended to `trace`'s markdown table whenever at
least one row actually used a marker, explaining only the markers used
(never shown on a full run, and never shown for `--dimension uat`, which
does not state `verified`). The report an Evidence Snapshot holds describes
that snapshot's own run, so its results carry no `(baseline)` marker.

`summary` is level-aggregated, not per-requirement, so it can't show
`(baseline)`/`—` inline. Instead, when any RESULT target was carried, the
level table's **Passing** figure (the union of `verified` and `lcov_tested`
— the "tested & passing" headline) gets a trailing `*`, and a footnote is
appended:

```text
* 1/2 test results from previous runs
```

The `N/M` counts are distinct RESULT targets, a target of each federation
member counted separately even where two members use one name: `M` targets
have any result data at all, `N` of those were carried (not freshly produced this
invocation, or stale). A full run (no `--targets`, or `--targets` covering every
result-bearing target) whose results are all fresh has zero carried targets,
so neither the `*` nor the footnote appears. Stale results are carried on any
run, so they bring the `*` and the footnote with them. The
`json`/`csv` formats expose the same counts as structured fields
(`carried_result_targets`, `total_result_targets`) instead of the `*`.

`elspais checks` itself (the health-report / gate command) only consumes
`--targets` for *execution* under `--run-tests`; it does not render
`(baseline)`/`—`/`*` — that provenance rendering is `summary`/`trace`'s job.
Without `--run-tests`, `checks` executes nothing, so it refuses `--targets`,
`--fail-fast`, `--stale-only` and `--concurrency` (exit 2) rather than accept
a selection nothing reads; to
require results a run did not execute, name them with `--expect` (see below).
`checks --run-tests --targets none` selects nothing to run. Consequently, the
command refuses it.

In a composed report the selection marks provenance exactly as it does on
`summary` or `trace` alone, and is refused the same way: `elspais checks
summary --targets NAME` marks NAME fresh for the summary and refuses an
unknown name. A composition holding neither `summary` nor `trace` reads no
provenance, so it refuses `--targets`.

### Worked example

Per-PR: run only the targets whose results this change made stale, then
render the full matrix with the rest carried as baselines:

```bash
elspais checks --run-tests --stale-only
elspais trace --targets last-run --format markdown
```

The targets the first command executed show fresh, just-run results. The
first command records them (see
[The record of the last run](#the-record-of-the-last-run)), and
`--targets last-run` reads that record. Every other configured target shows
`(baseline)` (carried from its last run) or `—` (no prior result data for that
target).

To choose the targets by hand instead, name them on the run. The report still
reads the record, so the names are written once:

```bash
elspais checks --run-tests --targets clinical_diary portal_ui_evs
elspais trace --targets last-run --format markdown
```

Full regression (e.g. promoting a build from qa to uat): omit `--targets` so
every configured target runs and renders fresh:

```bash
elspais checks --run-tests
```

### Executing only what is stale

`--stale-only`, on `elspais checks --run-tests` and on `elspais test`, executes
only the selected targets whose results are not fresh. The selection is the
`--targets` selection, or the `default` group. Freshness is the judgement
`tests.results_stale` reports (see
[Target Folders and Fresh Results](#target-folders-and-fresh-results)). A
selected target is executed when any of these holds:

- Its results are stale: an input changed since its run began, or no run
  recorded a fingerprint for them.
- It has no results on disk. A target with no `results` pattern therefore
  always runs. A coverage-only target is one example. A stdout reporter with
  no `results` pattern is another under `checks --run-tests`; `elspais test`
  refuses such a target (see
  [Parallel jobs and one gate](#parallel-jobs-and-one-gate)).
- Its last run recorded a start and no end.

Every other selected target's results are carried forward, exactly as in a
selective run with `--targets`. In `checks`, every selected target is still
expected. A carried failing result still fails the gate, because fresh means
the inputs are unchanged, not that the tests passed.

```bash
elspais checks --run-tests --stale-only
```

The run states its division on stderr before anything runs:

```text
stale-only: executing api, unit; carrying fresh results of backend
```

If every selected target is fresh, nothing executes and the run succeeds.
`elspais test --stale-only` then prints
`no target executed: the results of every selected target are fresh` and
exits 0. A run without `--stale-only` executes every target it names, fresh
or not.

To render `summary` or `trace` afterwards with the rest marked as carried,
name the record the run left:

```bash
elspais trace --targets last-run --format markdown
```

The stale-only line is for a reader. The record is how a later report learns
which targets ran fresh. If every selected target was fresh, then the record
lists no target, and `last-run` marks every result carried.

### Expected results

Which targets a run executes and which targets' results it requires are two
questions. A tier can produce its results in an earlier job and leave them on
disk for a later run to read; that later run names them with
`elspais checks --expect NAME ...`, by target or group name, with or without
`--run-tests`. Every target `--run-tests` executes is expected too.

| Target | No results on disk | Results, no coverage it declares |
|--------|--------------------|----------------------------------|
| executed or expected | `tests.ingestion_fault` | `tests.ingestion_fault` |
| neither | `tests.not_run` (info) | `tests.ingestion_fault` |

The rule is the same for a target that reads a results file and for one that
reads its runner's output. A target another federation member declares is
expected only where the run names it, as `NAMESPACE:NAME`; the name is resolved
by that member's own configuration, so a group of that member stands for that
member's targets. An associate's targets the run does not name, with no
results, read as not run. Because a target nobody ran is never a fault,
`tests.ingestion_fault` is reported at `error`: what reaches it is evidence
the run said would be there. A target or group name cannot contain `:`, which
is what keeps the namespace apart from the name.

```bash
# The e2e job left .results/e2e behind; the merge run executes the unit tier
# and requires both.
elspais checks --run-tests --targets unit --expect e2e

# The associate `lib` left its unit results too; require them.
elspais checks --run-tests --targets unit --expect e2e lib:unit
```

See also: `elspais docs checks`

## Evidence Snapshot

An *Evidence Snapshot* is the normalized results of one test run of one tree.
It is bound to that tree by its digest, and it is stored in the repository
with the traceability report derived from it. A project commits it with the
change it describes. CI then confirms that the snapshot describes that
change. A consumer that pins the commit can cite its report without running
the suites.

A target's folder and the snapshot have different roles:

| | `<output_root>/<target>/` | *Evidence Snapshot* |
| --- | --- | --- |
| Holds | The raw output of the target's last run, its coverage and its fingerprint | The normalized results of every selected target, and the report |
| Lifetime | Local; emptied when a run starts | Committed with the change it describes |
| Valid while | Its fingerprint matches the current inputs | Its tree digest matches the current tree |

Name the snapshot's directory, from the repository root:

```toml
[scanning.test]
evidence = "test-evidence"
```

The directory is never an input of a target. Consequently, writing a
snapshot does not make a target's results stale.

### What the snapshot holds

- `results.jsonl` holds one line for each result of the selected targets.
  Each line names the target, the repo-relative file and line that declare
  the test, the test name, the file that executed the test where that file
  differs, the outcome (`passed`, `failed` or `skipped`), and the skip reason
  where the test gives one. Two runs of one test with one outcome are two
  lines.
- `snapshot.json` holds the digest of the tree, each selected target with the
  digest of its inputs, the facts declared about the run, and the elspais
  version that wrote it. No name is a JSON key beside a digest.
- `timings.jsonl` holds each result's duration and the output the test
  printed. `flutter-machine` supplies the printed output.
- `TRACEABILITY.md` is `elspais trace --format markdown --preset evidence`,
  rendered from the snapshot and the specification alone. For each assertion
  it names the code that implements it and the tests that verify it, with
  each test's outcome, by repo-relative file and line.

Every file except `timings.jsonl` holds no duration, timestamp, absolute
path, machine name or failure message. Consequently, two runs of one tree
with the same outcomes and the same facts write the same bytes.

The tree digest covers every file git tracks or has staged, except the
snapshot directory. The same digest results in a working tree before a
commit and in a checkout of that commit in CI. A target's digest covers the
same files: an input that git ignores, such as a build cache, exists only
where the run executed, so it never reaches the snapshot.

### Writing and verifying

```text
elspais test                                       # run the targets
elspais evidence write --fact backends=vm,postgres # hold their results
elspais evidence verify --fact backends=vm,postgres
```

`evidence write` holds the results that the selected targets left in their
folders. It refuses (exit 2), naming the target, a selected target whose
results are absent, stale or in a run that is still in progress: a snapshot
describes a finished run of the tree. It also refuses a selected target
whose results the build could not read in full: a reporter that no parser
reads, a results file that does not parse, or a stream that ends inside a
test. A snapshot of those results would hold a shorter run as a finished
one. A member's target is named as `NAMESPACE:NAME`, as it was selected.
Where the tree holds changes that no
commit holds, `write` names them on stderr and still writes. That snapshot
then matches no checkout of any commit.

`evidence verify` derives the same snapshot in memory and compares it with
the snapshot in the directory. It lists each test whose outcome differs,
each result on one side only, a tree digest that differs, a fact or a target
that differs, and a report that differs. Durations and printed output are
never compared. It exits 0 when the two agree and 1 when they differ.
`--run` first executes the selected targets, as `elspais test` does.

`--targets` selects as `checks --run-tests` does. elspais takes the facts
from `--fact NAME=VALUE`, because only the project knows which toolchain
or backend a target's command used. Pass the same facts to `verify` that
the snapshot holds.

### Reading a snapshot back

A target that has not run in this tree, and that the run does not execute,
reads its results from the snapshot. These results are tagged carried.
Consequently, `trace`, `summary` and `checks` report from a checkout that
has run nothing. A target that has results of its own reads only those. A
target that ran and left no results is missing them.

A snapshot whose tree digest differs from the digest of the current tree
describes another tree. Its results are still read, and
`tests.results_stale` names the snapshot directory. A snapshot is judged
whenever a target is read from it, also where that target's run produced no
result. For a federation member's snapshot, the finding names
`elspais evidence write --targets NAMESPACE:NAME`, because a bare `write`
reaches only the invoking repository.

### A federation member's snapshot

A federation member that names a snapshot, and that holds no results of its
own, reads its results from its snapshot. The snapshot is judged against
the member's own tree. A consumer that integrates the member then credits
the tests of the member's recorded run.

`--targets NAMESPACE:NAME` writes or verifies the member's snapshot, in the
member's repository, with the member's configuration. A snapshot describes
one repository, so a selection that names targets of two repositories is
refused (exit 2).

### The consumer's workflow

```text
# developer
elspais test --targets all
elspais evidence write --targets all --fact backends=vm,postgres
git add test-evidence && git commit

# CI: jobs run the targets in parallel and the gate job collects their folders
elspais evidence verify --targets all --fact backends=vm,postgres
```

CI passes the facts the snapshot claims, so CI runs every backend that the
snapshot names. A gate job that collects no folders runs
`elspais evidence verify --run` instead.

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
| `suite-hostname` | The `hostname` attribute of the `<testsuite>` holding the result record |

Use `results-path` where each environment writes its own artifact:

```toml
[[scanning.test.targets]]
name        = "devices"
reporter    = "junit"
results     = "*/journey-results.xml"
environment = "results-path"            # .results/devices/pixel-8/... -> "pixel-8"
```

The environment is what the wildcard stood for, and not the whole path
segment it sits in. A pattern names the environment inside a segment as
readily as it names a whole one:

```toml
results     = "junit-*.xml"    # junit-pixel-8.xml -> "pixel-8"
```

Use `suite-hostname` where one artifact holds every environment and the
producer writes the environment into the suite:

```toml
[[scanning.test.targets]]
name        = "browsers"
reporter    = "junit"
results     = "junit.xml"
environment = "suite-hostname"          # <testsuite hostname="firefox">
```

A declared source does not always give an answer. A `results` glob holding
`**`, holding more than one wildcard segment, or holding more than one
wildcard within its wildcard segment, does not say which part of the path is
the environment. A result record may also sit in a suite that names no
hostname. In each of these the result carries no environment and
`elspais checks` reports that none was derived. The tool does not guess,
because a guess reads exactly like a reading in every figure that follows.

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
