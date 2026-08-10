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
| Python quality | `ruff check` and `black --check` on `src/ tests/` | `ruff`, `black` |
| Markdown linting | markdownlint on changed `.md` files | `markdownlint` |
| Index regeneration | `elspais fix`, staging what it regenerates | `elspais` |
| Unit tests | `pytest` with coverage, cached by tree hash | `pytest` |

The index step resolves this tree's `elspais` rather than whichever one is on
`PATH`: a different version rewrites hashes across spec files the commit never
touched, and reports success while doing it.

### pre-push

Runs before pushing, with PR-aware blocking behavior:

- **PR/feature branches**: validation failures BLOCK the push
- **Other branches**: validation failures show warnings only

| Check | Description | Required Tool |
| --- | --- | --- |
| Branch freshness | Fetches `origin/main`; auto-bumps the version if it matches main's | - |
| PR detection | Decides whether failures block or warn | `gh` (optional) |
| E2E tests | `pytest -m e2e`, cached by tree hash and CLI environment | `pytest` |
| Secret detection | Scans for leaked secrets | `gitleaks` |
| Doc sync tests | `pytest tests/test_doc_sync.py` | `pytest` |

**Why this list is short.** Nothing that pre-commit already gates is repeated
here. You cannot push what you have not committed, so every commit in a push
has already passed lint, formatting, markdown, index regeneration and the unit
tier. Pre-push runs only what pre-commit cannot: checks that are too expensive
to pay per commit (the e2e tier), and checks whose answer is not knowable at
commit time because it depends on the remote (branch freshness, PR state).

Re-running the rest would cost minutes per push to re-derive answers already
in hand. If you are tempted to add a check here, first ask whether it belongs
in pre-commit instead.

## Required Tools

Install these tools for full hook functionality:

```bash
# Python tools (via pip)
pip install ruff black pytest

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
