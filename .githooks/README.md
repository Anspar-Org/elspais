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

Runs before each commit to validate staged changes:

| Check | Description | Required Tool |
| --- | --- | --- |
| Branch protection | Blocks commits to main/master | - |
| Python linting | ruff check on changed .py files | `ruff` |
| Python formatting | black check/fix on changed .py files | `black` |
| Markdown linting | markdownlint on changed .md files | `markdownlint` |

### pre-push

Runs before pushing with PR-aware blocking behavior:

- **PR/feature branches**: Validation failures BLOCK the push
- **Other branches**: Validation failures show warnings only

| Check | Description | Required Tool |
| --- | --- | --- |
| Doc sync tests | pytest tests/test_doc_sync.py | `pytest` |
| Deprecated options | Scans for deprecated config usage | - |
| CLI verification | Verifies `elspais --help` works | - |
| Python quality | Full ruff + black check on src/ | `ruff`, `black` |
| Markdown linting | markdownlint on changed .md files | `markdownlint` |
| Secret detection | Scans for leaked secrets | `gitleaks` |
| Fixture validation | Runs elspais validate on fixtures | - |
| Full test suite | pytest tests/ | `pytest` |

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
