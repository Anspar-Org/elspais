# Git Hooks for elspais

This directory contains Git hooks for maintaining code quality in the
elspais repository.

## Installation

Run this command from the repository root:

```bash
git config core.hooksPath .githooks
```

## Hooks

### commit-msg

Validates commit message format:

| Check | Description | Required Tool |
| --- | --- | --- |
| Ticket number | Message must start with `[TICKET-NUMBER]` | - |

**Format**: `[XXX-NNN] description` where XXX is 2-10 uppercase letters.

**Examples**:

- `[CUR-514] fix: Add validation for user input`
- `[PROJ-123] feat: Implement new feature`

**Skipped for**: Merge commits, revert commits, fixup/squash commits.

### pre-commit

Runs before each commit. This is where content is gated: everything that can
be decided from the tree alone happens here, once per commit.

| Check | Description | Required Tool |
| --- | --- | --- |
| Branch protection | Blocks commits to main/master | - |
| Unstaged changes | Refuses a partial commit of `src/` or `tests/` | - |
| Python quality | `ruff check` and `ruff format --check` on `src/ tests/` | `ruff` |
| Markdown linting | markdownlint on changed `.md` files | `markdownlint` |
| Index regeneration | `elspais fix`, staging every file it wrote; a file that already held unstaged edits is named and left unstaged | `elspais` |
| Unit tests | `unit-verdict`, running `run-unit-tier` in parallel with per-test coverage, cached by tree hash; deferred on a checkpoint commit | `pytest`, `pytest-cov`, `pytest-xdist` |

The index step resolves this tree's `elspais` rather than whichever one is on
`PATH`: a different version rewrites hashes across spec files the commit never
touched, and reports success while doing it.

The unit tier runs through `run-unit-tier`, which `make test`, the
`elspais-unit` target in `.elspais.toml` and CI's unit job also call. It runs
the tier with `pytest-xdist` and `--dist loadfile`, so each test file stays on
one worker in order, and records which test ran each line
(`--cov-context=test`); pytest-cov combines the workers' coverage into the
one `.coverage` file elspais reads, beside `junit.xml` and `coverage.json`.
Every parallel tier takes its worker count from `test-workers`: half the
processors this process may run on, and at least one, so the unit and e2e
tiers together never take the whole machine. `ELSPAIS_TEST_WORKERS`
overrides it; a value that is not a positive whole number stops the tier with
a message naming the variable.

The hook runs `run-unit-tier` through `with-fingerprint`, which brackets it with
`elspais fingerprint start` and `finish` for the `elspais-unit` target. Its
results and coverage land in `.results/elspais-unit/` with a fingerprint of the
tree they ran against, so `elspais checks` reads them as fresh until an input
changes -- including after a later commit skips the run because the tree is
unchanged. The e2e tier does the same for `elspais-e2e`.

A checkpoint commit, `ELSPAIS_CHECKPOINT=1 git commit ...`, runs every gate in
this table except the unit tier. It records no unit verdict for its tree.
Consequently, pre-push runs the tier for the tree it pushes. Use a checkpoint
as a safety net for an intermediate commit on a branch that is squash-merged:
only the pushed tree reaches review, so only the pushed tree needs a verdict.

### pre-push

Runs before pushing, with PR-aware blocking behavior:

- **PR/feature branches**: validation failures BLOCK the push
- **Other branches**: validation failures show warnings only

| Check | Description | Required Tool |
| --- | --- | --- |
| Branch freshness | Fetches `origin/main`; auto-bumps the version if it matches main's | - |
| PR detection | Decides whether failures block or warn | `gh` (optional) |
| Unit tests | `unit-verdict` for the pushed tree; runs the tier where no commit earned a verdict for that tree | `pytest`, `pytest-cov`, `pytest-xdist` |
| E2E tests | `e2e-verdict`, running `run-e2e-tier`; cached by tree hash and CLI environment | `pytest`, `pytest-xdist` |
| Secret detection | Scans for leaked secrets | `gitleaks` |
| Doc sync tests | `pytest tests/test_doc_sync.py` | `pytest` |

The e2e stage is `e2e-verdict`, the one writer of `.results/.test-cache-e2e`.
It records `<tree> PASS <environment>` for the tree `git write-tree` names
when the tier passes, and honours that record for the same tree and
environment. A failed run records nothing and removes any earlier record, so
the next invocation runs the tier again: a failure caused by the environment
is never reported again for a run that did not happen. `unit-verdict` keeps
its cache the same way. Running `e2e-verdict` before `git push` moves the run
out of the push.

`e2e-verdict` runs the tier through `run-e2e-tier`, which `make test-e2e` and
the `elspais-e2e` target in `.elspais.toml` also call, so every way of running
the tier runs it the same way:

1. A parallel pass over the e2e tests not marked `serial`, with
   `pytest-xdist` and `--dist loadfile`. Each module stays on one worker, in
   order, beside the project and daemon its module fixture built.
2. A serial pass over the tests marked `serial`, with no other test process
   alive, for a test sharing state no worker owns. None is marked: each e2e
   test works in its own copy of a fixture or of this checkout, on a port its
   viewer bound itself, and with a private home for the claude CLI. A pass
   that collects nothing is not a failure.

Both passes always run, with coverage off, and their results are merged into
the target's one `junit.xml`. `tests/conftest.py` fails a `serial` test that
an xdist worker runs, so the split cannot be undone by a selection mistake,
and fails every e2e and browser test when the `elspais` it would spawn does
not import elspais from this checkout's `src`. The parallel pass's worker
count comes from `test-workers`. CI's `e2e-test` job runs `run-e2e-tier` too.

**Why this list is short.** Nothing that pre-commit already gates is repeated
here. You cannot push what you have not committed, so every commit in a push
has already passed lint, formatting, markdown, index regeneration and the unit
tier, except a checkpoint commit, which deferred the unit tier. Pre-push runs
only what pre-commit cannot or did not: the unit tier for a pushed tree that no
commit verified, checks that are too expensive to pay per commit (the e2e
tier), and checks whose answer is not knowable at commit time because it
depends on the remote (branch freshness, PR state). A pushed tree that a full
commit already verified is a cache hit, so the unit stage then costs nothing.

Re-running the rest would cost minutes per push to re-derive answers already
in hand. If you are tempted to add a check here, first ask whether it belongs
in pre-commit instead.

## The test runner: tiers, artifacts and state

This section is the review of how the test tiers, the artifacts they write
and the checks that read those artifacts fit together. It lives here, beside
the scripts it describes, because the runner is this repository's own tooling
rather than part of the product: `docs/` and `src/elspais/docs/` describe
elspais to its users, and nothing there would be read by the developer whose
hook just failed.

A tier must report the state of the tree it was asked about, and report it
the same way twice. So every piece of state a tier keeps outside the tree is
listed below with what happens when it is wrong: either the dependency is
removed, or the runner says what is wrong and how to fix it. A dependency a
developer has to remember is a defect in this list.

### How each tier runs

Each tier is a `[[scanning.test.targets]]` entry in `.elspais.toml`, and every
way of running it from a terminal or a hook brackets the run with
`with-fingerprint`. That script asks `elspais fingerprint start` to empty the
target's output area under `.results/<target>/` and record a *Result
Fingerprint* of the tree, runs the tier with `ELSPAIS_TARGET_OUTPUT` naming
the area, and asks `elspais fingerprint finish` to note any input that
changed while it ran.

| Tier | Target | Run by | Writes into its output area |
| --- | --- | --- | --- |
| unit | `elspais-unit` | `unit-verdict` (pre-commit, pre-push), `make test`, CI's unit job | `junit.xml`, `.coverage` (per-test contexts), `coverage.json`, `.elspais-run.json` |
| e2e | `elspais-e2e` | `e2e-verdict` (pre-push), `make test-e2e`, CI's e2e job | `junit-parallel.xml`, `junit-serial.xml`, the merged `junit.xml`, `.elspais-run.json` |
| browser | `elspais-browser` | `make test-browser`, CI's browser job | `junit.xml`, `.elspais-run.json` |
| stress | `elspais-stress` | `make test-stress`, CI's stress job | `junit.xml`, `.elspais-run.json` |

CI runs the tier scripts or pytest directly, in a fresh container, so it
keeps none of the state below between runs. `elspais checks --run-tests`
runs a target's `command` with the same fingerprint bracket, and also writes
`.results/.elspais-last-run.json`, naming the targets it executed.

The hooks and the Makefile run a tier through `lib-tier-run.sh`, which keeps
a state directory per target: `.results/run-unit`, `.results/run-e2e`, and
`.results/run-<target>` for the others. It holds the run's `pid`, `key`,
`log`, `rc` and the scripts that make up the run. A hook runs the tier
detached, in a process group of its own, so a signal to the hook's own
process group -- its caller's timeout firing -- leaves the run going, and the
next invocation attaches to it. `run-target`, which the Makefile calls, runs
it in the foreground under the same guards.

### Which check reads which artifact

Every elspais build reads each target's output area: the results pattern
(`junit.xml`) becomes RESULT nodes, the unit target's `.coverage` becomes line
coverage, and the fingerprint decides whether those results are fresh.

- `tests.results` counts the ingested results by status, and says how many
  come from stale results; `tests.external` names the stale reason beside a
  verdict read from stale results.
- `tests.results_stale` reports each target whose fingerprint judgement is
  stale: no fingerprint, or an input changed since or during the run.
- `tests.run_in_progress` reports a target whose fingerprint records a start
  and no finish.
- `tests.not_run` and `tests.ingestion_fault` report a target with no
  results.
- `tests.tested`, `tests.verified` and the other coverage checks, `summary`,
  `trace`, MCP and the viewer read the RESULT nodes. A result whose target's
  results are stale is carried: `trace` marks its figure `(baseline)`,
  `summary` counts its target as carried, and a failure among them still
  fails and says why its results are stale. The unit target's line coverage
  is carried by the same rule, and `code.code_tested` says why it is stale.
- `--targets last-run` reads `.results/.elspais-last-run.json`.

Two files belong to the hooks alone. `.results/.test-cache-unit` holds the
tree a unit run passed for, and `.results/.test-cache-e2e` holds the tree and
interpreter an e2e run passed for. Each verdict script honours its record for
the same key and runs the tier otherwise. Nothing in elspais reads them, and
`coverage.json` is read by nothing in this repository either.

### State outside the tree, and what happens when it is wrong

| Dependency | Tiers | Kept or removed | When it bites |
| --- | --- | --- | --- |
| Results an earlier run left in `.results/` | all | Removed as an input to a test: e2e tests work in private copies of a fixture or of this checkout, which carry no `.results/`, and no unit test reads the live checkout's output areas. Kept as an input to a report | A report marks results the current tree did not produce as carried, and `tests.results_stale` names why |
| A cached verdict | unit, e2e | Kept, for passes only: a failed run removes the record, so a failure never decides what the next run says | The hook prints that the tree is cached as passed; `ELSPAIS_UNIT_FORCE=1` or `ELSPAIS_E2E_FORCE=1` runs it again |
| A run in progress in the same worktree | all | Kept: starting a second run of one target empties the first one's output area | `lib-tier-run.sh` refuses, naming the run's pid and log. A recorded pid counts only while that process is running the recorded run, so a pid reused by an unrelated process reads as a run that ended. `elspais checks --run-tests` starts a target's run without this guard |
| Coverage shards (`.coverage.<host>.pid<N>.*`) | unit | Kept: pytest-cov writes one per process and combines them at the end | Before a run, `lib-tier-run.sh` removes every shard whose writer is not a live Python process, so a killed run's shard cannot fail the next run's teardowns |
| This checkout's build | e2e, browser | Kept: the tiers spawn `elspais` | `tests/conftest.py` fails each e2e and browser test when the program it would spawn does not import elspais from this checkout, and `e2e-verdict` refuses to start under such an interpreter |
| The venv first on `PATH` | e2e | Kept: a fixture's target shells out to a bare `python` | The hooks and `run-target` put `.venv/bin` first on `PATH`. A session selecting e2e tests where no `python` is on `PATH` stops with a usage error saying so; the program the tests spawn is found in this checkout's venv whatever `PATH` says |
| The `mcp` extra | all | Kept | A session without it stops with a usage error naming `make setup`, unless `ELSPAIS_TEST_WITHOUT` names `mcp` |
| The `browser` extra and chromium | e2e, browser | Kept | A session whose marker expression selects browser tests stops with a usage error naming `make setup`, unless `ELSPAIS_TEST_WITHOUT` names `browser`; `pytest -m browser` without playwright stops whatever that variable says |
| `ELSPAIS_TEST_WORKERS` | unit, e2e | Kept, as an override of half the available processors | A value that is not a positive whole number stops the tier with a message naming the variable |
| Git's hook environment (`GIT_DIR` and the rest) | all | Removed: `tests/conftest.py` and `unit-verdict` clear it | Never |
| The developer's daemon, home and Claude configuration | e2e | Removed: each e2e test that runs elspais works in its own copy with its own daemon, on a port its viewer bound, with a private home for the claude CLI | Never |
| `pandoc`, `xelatex`, the `claude` CLI | e2e | Kept, as optional tools | The tests needing them skip, and the skip reason names the missing tool; the claude CLI test also skips inside a Claude Code session |
| `tail`, to relay a detached run's log | all | Kept -- `lib-tier-run.sh` has no other way to show a growing file as it is written | `tier_require` stops the tier before it starts, naming `tail`, on a machine that has none. `bash`, `ps` and `/proc` are the rest of the runner's platform surface: `bash` is assumed throughout, and `ps -ww -o args= -p` (BSD and GNU alike) is the fallback `tier_pid_args` uses where `/proc` is absent |

## Required Tools

Install these tools for full hook functionality:

```bash
# This tree's venv, its editable elspais and the Python test tools -- ruff,
# pytest, pytest-cov, pytest-xdist and the rest of the `dev` extra -- plus
# the browser extra and chromium for the browser tests the e2e tier runs.
# The hooks prefer .venv/bin, and the e2e tier refuses to run against an
# elspais that does not import from this checkout.
make setup

# Markdown linting (via npm)
npm install -g markdownlint-cli

# Secret detection
# See: https://github.com/gitleaks/gitleaks#installing

# GitHub CLI (for PR detection)
# See: https://cli.github.com/
```

## Bypassing Hooks

**Not recommended**, but if necessary:

```bash
# Skip pre-commit hooks
git commit --no-verify

# Skip pre-push hooks
git push --no-verify
```

## PR-Aware Blocking

The pre-push hook detects if your branch:

1. Has an open pull request
2. Is named `feature/*`, `fix/*`, or `release/*`

If either condition is true, validation failures will **block** the push
to ensure code quality before PR review.
