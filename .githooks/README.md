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
overrides it.

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
It records `<tree> PASS|FAIL <environment>` for the tree `git write-tree`
names, and honours a recorded verdict for the same tree and environment.
Running it before `git push` moves the run out of the push.

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
