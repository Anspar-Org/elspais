# Test Impact Analysis (TIA)

Test Impact Analysis runs only the unit tests that the change since a
recorded baseline could have affected. It is a fast development-feedback
mode. It is not a verdict:

- The full unit tier still runs at commit (`.githooks/unit-verdict`), at push,
  and in CI. Those runs stay authoritative.
- TIA is an additional execution mode (`make test-impacted`), and an
  advisory CI job.
- When TIA cannot determine impact, it falls back to running more tests,
  up to the complete suite. It never treats missing, corrupt, stale or
  ambiguous data as "no tests need to run".

The implementation lives in `tools/tia/` (development tooling, not part of
the shipped `elspais` package). The rules live in `tools/tia/config.toml`.

## Scope

TIA applies to the **unit tier** only (`pytest tests/` with the default
marker expression `not e2e and not browser and not stress`, about 10,400
tests). That tier is the only one that records per-test line coverage
(`--cov-context=test`).

The e2e, browser and stress tiers spawn the `elspais` program as a
subprocess. The coverage of a subprocess is not attributed to the test that
spawned it, so there is no test-to-code map for those tiers. They are
unchanged and always run in full where they ran before.

## Quick start

```bash
make tia-baseline          # full unit tier + record .results/tia/baseline
# ... edit code ...
make test-impacted-list    # what would run, and why (no tests run)
make test-impacted         # run the impacted tests
make test-impacted ARGS=--full   # bypass TIA: run the full unit tier
TIA_FULL=1 make test-impacted    # same
```

Every `select`/`run` writes a manifest to `.results/tia/run/manifest.json`.

The commands underneath:

```bash
python -m tools.tia select [--baseline DIR] [--full] [--granularity file|test] [--list]
python -m tools.tia run    [--baseline DIR] [--full] [-- extra pytest args]
python -m tools.tia baseline show [--baseline DIR]
python -m tools.tia baseline build --run-dir DIR --coverage FILE --dest DIR
python -m tools.tia compare --tia-manifest M --full-junit J
python -m tools.tia calibrate [--full-junit J] [--mutants N --seed S]
```

## How a baseline is recorded

A baseline is produced by an ordinary full run of the unit tier with
`ELSPAIS_TIA_RECORD=1` (`make tia-baseline` does this). `.githooks/run-unit-tier`
then loads the recorder plugin (`-p tools.tia.recorder`). When pytest exits,
the tier builds the baseline directory. The tier's exit code is still pytest's.
A baseline that cannot be built is reported, and the tier's verdict is
unaffected.

The baseline directory (default `.results/tia/baseline`, or
`$ELSPAIS_TIA_BASELINE`) holds two files:

| File | Content |
| --- | --- |
| `coverage.db` | The run's coverage.py data file, copied verbatim. Its per-test contexts (`<nodeid>\|setup`, `\|run`, `\|teardown`) are the map from each test to the production lines it ran. |
| `baseline.json` | The identity, the environment, the test inventory and the recorder's attribution data (see below). Includes a checksum of `coverage.db`. |

### Identity: what exactly was tested

At session start the recorder records:

- `tree`: the output of `git write-tree`, which is the index;
- `commit`: `HEAD`, for information;
- `dirty`: every file whose worktree content differs from that tree
  (unstaged edits, deletions and untracked files). Each one is stored as a
  git blob (`git hash-object -w`).

Together these name the exact bytes the run tested. This holds for a clean
CI checkout and for a pre-commit run of a staged tree. At session end the
recorder takes the identity again. If the identity changed during the run,
the baseline is refused.

### What the recorder adds to coverage

Line coverage per test has blind spots. The recorder closes each one so that
selection can be conservative about it:

| Blind spot | What is recorded | How selection uses it |
| --- | --- | --- |
| Shared fixtures (session, module or class scope) run once, inside the *setup* of the first test that needs them. Their lines are credited to that one test. | For each test: the shared fixtures it depends on, and the shared fixtures that were executed in its setup (or finalized in its teardown). While a repository-defined shared fixture is being set up, its file reads, listings and spawns are attributed to the fixture itself (`fixture:<key>`). | A coverage hit in a test's setup or teardown phase is widened to every test that uses the shared fixtures that phase executed. A read attributed to a fixture selects exactly that fixture's users. Fixtures whose function is defined outside the repository (pytest built-ins and plugins, for example `tmp_path_factory`) run no repository code and never widen. This is decided by where the function lives, not by the fixture's `baseid`, whose spelling for the root directory has varied between pytest versions. |
| Files read as data, such as fixture projects, docs, templates, `.github/workflows` and the repository's own sources. | Through an audit hook, the repository files each test phase opened and the directories it listed. Import-machinery reads are excluded. | A changed non-Python file selects the tests that read it. For an added file, it selects the tests that listed its directory, or the nearest listed ancestor directory. |
| Subprocesses: code that runs in a child process is invisible to coverage. | The programs each test spawned. | A test that spawns `python*` or `elspais*` is *opaque*. It is selected whenever any non-test file changes. |
| Tests that did not pass have partial coverage. | The outcome of each test. | A test that did not pass in the baseline (failed, error, skipped, xfail) is always selected. |
| The interpreter or dependencies differ. | The Python version and every installed distribution except `elspais`. | Any difference runs the full suite (`on_environment_change`). |

The recorder never raises into the run. An internal error is written into
the shard. The error makes the baseline invalid instead of silently
incomplete.

## How selection works

`python -m tools.tia select` loads and validates the baseline. It then
compares the bytes of every file in the baseline (tree plus dirty overlay)
with the working tree, untracked files included. The "change" is therefore
everything between what the baseline tested and what is on disk now. This
includes commits made since the baseline, staged edits and unstaged edits.
Because the diff is always taken from the baseline, an older baseline stays
correct: it only selects more tests.

Each changed file is classified. The first matching `[[rule]]` in
`config.toml` decides. If no rule matches, a built-in category applies:

| Category | Selection |
| --- | --- |
| rule `full` (`pyproject.toml` beyond its version, lock files, `tools/tia/**`, `.githooks/run-unit-tier`, ...) | the full suite |
| rule `ignore` (`tests/_obsolete/**`) | nothing |
| test module, new or modified | every test in it |
| `conftest.py` or `__init__.py` under `tests/` | every test under that directory (`tests/conftest.py` is effectively the full suite) |
| other Python under `tests/` (helpers) | the test modules that import it, transitively. A helper that no test module imports runs the full suite. |
| production Python (`src/elspais/**.py`) | the structural impact analysis below |
| anything else (data) | the tests recorded reading the file or listing its directory. For package data under `src/`, it also selects the tests covering production modules whose string literals name the file. Package data that nothing is known to read runs the full suite. |

### Production Python: structural, not line-number, diffing

Changed lines are never compared by their current line numbers. Both
versions of the file are parsed. The two ASTs are compared unit by unit. A
unit is a function or method, keyed by its qualified name (for example
`CoverageDimension.rolled_direct`), or a class header. Module-level and
class-level statements are compared as a multiset. A changed unit's impact
is expressed in the unit's **baseline** line range, which is the coordinate
system the baseline coverage uses. Insertions and deletions elsewhere in the
file therefore cannot misdirect selection.

Each change gets one of three scopes:

| Scope | Triggered by | Selects |
| --- | --- | --- |
| FUNCTION | A function or method body changed, or its arguments or return annotation changed. A comment or formatting edit inside a function counts too (cheap, and some tests read sources as text). | The tests whose baseline coverage touches the outermost enclosing function's baseline lines. |
| FILE | A new top-level function or class whose name is not used as a string literal anywhere in `src`. A new method on a class without bases. An added `import`. A new module. | The tests covering any line of the file. For a new module: the tests that listed its directory (dynamic discovery), plus the module scope if an *unchanged* module already imports it. |
| MODULE | Changed module-level or class-level statements (constants, class attributes, docstrings, `__all__`). Changed decorators or class bases. A removed or renamed definition. A new method on a class with bases, or under a dunder or string-referenced name (it may override or be looked up). A memoized function (`@cache`, `@lru_cache`, ...). A file that no longer parses. A deleted module. | The tests covering any line of this module or of any module that imports it, transitively (the static import graph over `src/`, `tests/` and `tools/`, with function-level imports included). Also, every test module importing one of those modules, and every test under a `conftest.py` that imports one at import time. |

Escalation never narrows the selection:

- A FUNCTION region that no baseline test executed widens to FILE.
- A FILE that no baseline test executed widens to MODULE.
- A MODULE that no test executed or imported runs the full suite
  (`unmeasured-module`).

### Always-on additions

- **Baseline non-passing tests.** Every test that did not pass in the
  baseline is selected.
- **Opaque tests.** Every test that spawned a Python or `elspais` child
  process is selected when any non-test file changes.
- **`always_run`.** Every test listed in `always_run` (empty by default) is
  selected. This list is for a deliberate smoke set, not a safety net.

### Granularity

`granularity = "test"` is the default. It runs the selected node IDs,
widened to whole test classes. The suite declares ordering dependencies per
class: `@pytest.mark.incremental` chains a class's steps, and the conftest
tracks a failure per class. Widening to the class keeps each chain intact.
The tests are handed to pytest as their files, and a small plugin
(`tools/tia/pytest_select.py`) deselects the rest. Every test in a new or
modified test file runs.

`granularity = "file"` (or `--granularity file`) runs every test in any test
file that holds a selected test. It also protects *undeclared* dependencies
between tests of one module. Such a dependency is a test-isolation bug: it
already breaks `pytest -k`, and it would show up here as a spurious failure
or as a disagreement in calibration. For the measured changes, file
granularity ran 2.5 to 4 times as many tests (see [Measurements](#measurements)).

If the selection reaches `full_suite_threshold` (85%) of the suite, the full
suite runs instead. This is recorded as the `selection-near-full` fallback.

## Fallbacks (full suite)

Every fallback is listed in the manifest's `fallbacks` with a `kind`, a
`detail` and, where it applies, a `path`. Any fallback means the
`selection_mode` is `full`.

| Kind | When |
| --- | --- |
| `forced-full` | `--full` or `TIA_FULL=1` |
| `baseline-missing` | No baseline directory, or no `baseline.json` in it. |
| `baseline-malformed` | `baseline.json` does not parse, misses fields, or records no tests. |
| `baseline-stale` | A schema version mismatch, or the baseline is older than `max_baseline_age_days` (30). |
| `baseline-incomplete` | The baseline run was interrupted (pytest exit status other than 0 or 1), some tests never ran, or the recorder reported errors. |
| `baseline-identity` | No git identity was recorded, or the tree changed while the baseline was recording. |
| `baseline-revision-unavailable` | The baseline's tree or its dirty blobs are not in this clone. |
| `coverage-missing`, `coverage-corrupt` | `coverage.db` is absent, does not match its checksum, has an unsupported schema, holds no lines, or none of its contexts names a recorded test. |
| `environment-changed` | The interpreter or the installed distributions differ from the baseline's. |
| `broad-impact-file` | A changed file matched a `full` rule, or a manifest changed beyond its ignored keys. |
| `session-read` | A changed file was read by pytest before any test ran. That read is configuration. |
| `test-support-unknown` | A changed test helper that no test module is known to import. |
| `new-test-package` | A new `conftest.py` or `__init__.py` under `tests/`. |
| `package-data-unknown` | A changed file under `src/` that no test or module is known to read. |
| `unmeasured-module`, `unresolvable-module` | A changed production module whose dependants cannot be determined. |
| `selector-error` | Any exception inside the selector. |
| `selection-near-full` | The selection reached the threshold. This is an efficiency fallback, not a safety one. |

## The manifest

`.results/tia/run/manifest.json` (abridged):

```json
{
  "selection_mode": "test-impact",
  "baseline": {"commit": "...", "tree": "...", "dirty_files": [], "tests": 10369},
  "change": {"files": [{
      "path": "src/elspais/graph/metrics.py", "status": "modified",
      "category": "production-python",
      "regions": ["src/elspais/graph/metrics.py:203-205 CoverageDimension.rolled_direct changed"],
      "notes": ["hunk src/elspais/graph/metrics.py:205-205 (baseline) -> 205-206"],
      "tests_selected": 812}]},
  "granularity": "file",
  "total_tests": 10369, "selected_tests": 1003, "skipped_tests": 9366,
  "new_test_files": [], "fallbacks": [],
  "pytest_targets": ["tests/graph/test_metrics.py", "..."],
  "tests": [{"test": "tests/...::test_x", "reasons": ["covers changed region src/elspais/graph/metrics.py:203-205 (CoverageDimension.rolled_direct)"]}],
  "run": {"exit_code": 0, "elapsed_seconds": 41.2, "executed_tests": 1003, "outcomes": {"passed": 1003}}
}
```

Each selected test lists up to six reasons. The `run` block is added by
`run`. `skipped_tests` counts baseline tests that were not selected. Tests in
`new_test_files` are counted only after they run (`run.executed_tests`).

## Validating the selector

The selector's own tests are in `tests/tia/`. They build small synthetic git
repositories with synthetic coverage. They exercise:

- line edits;
- insertions that shift line numbers;
- deletions;
- new modules;
- new tests and modified tests;
- unrelated changes;
- shared configuration and dependency changes;
- missing, stale and malformed baselines;
- corrupt coverage.

Empirical evaluation (`make tia-calibrate`, nightly in CI) uses two
instruments:

1. **Same-revision comparison.** The selected suite and the complete suite
   both run against the current revision, and their outcomes are compared.
   A test that fails in the full run but was not selected is a *missed
   failure*. Tests that ran in both runs and disagree are reported as
   flaky or order-dependent.
2. **Mutant probes** (`MUTANTS=N`). A real change rarely makes a test fail,
   so instrument 1 is usually not put to the test. A mutant is a seeded,
   deterministic fault: a production function that the baseline saw
   executed gets `raise RuntimeError("tia-mutant")` as its first statement.
   TIA selects for that change, and then the tests it did **not** select are
   run. Any failure among them is a missed failure. Running only the
   complement keeps each probe affordable.

## CI

`.github/workflows/ci.yml`:

- `test` (unchanged) runs the full unit tier on every supported Python. On a
  push to `main`, the Python 3.13 leg also records a baseline and saves it to
  the Actions cache under the key `tia-baseline-v1-py3.13-<sha>`.
- `test-impact` (pull requests, advisory) restores the newest baseline from
  `main`, runs `python -m tools.tia run`, and uploads the manifest as the
  `tia-manifest` artifact. It does not replace the full unit job.
- `.github/workflows/tia-calibration.yml` (nightly and on demand) records a
  fresh baseline and runs `calibrate` with mutant probes. It uploads the
  report and fails when a failure was missed.

## Known limitations

- **Process-lifetime caches.** A production function memoized with a
  decorator is handled (MODULE scope). Other process-wide caches attribute a
  dependency only to the first test in each worker that filled the cache,
  for example a module-level dict filled lazily, a Jinja environment, or
  `linecache`. A change to the code that fills such a cache can miss later
  readers. The mutant probes are the instrument for finding these cases.
- **Dynamic lookup.** Code reached through `getattr` with a computed name,
  plugin discovery, or `importlib` with a computed name is only partly
  covered. String-literal references and recorded directory listings
  account for the common forms.
- **Import-time side effects of an added import.** An added import is FILE
  scope. If the imported module registers something global at import time,
  tests that use that registry without running this file are not selected.
- **Threads that outlive a test.** Coverage from a background thread is
  credited to whichever test is running at the time. This causes extra
  selection, never less.
- **Opaque tests.** Subprocess-spawning tests run on any non-test change,
  so they are a fixed cost. Measuring them would need subprocess coverage
  with per-test contexts.
- **Unit tier only.** See [Scope](#scope).
