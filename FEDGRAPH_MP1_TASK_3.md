# Task 3: Build Per-Repo TraceGraphs and Construct FederatedGraph

**Branch**: claude/cross-cutting-requirements-2Zd0c
**Ticket**: CUR-1082
**Status**: In Progress

## Description

When `[associates]` config is present, build separate TraceGraph per repo with
its own config. Missing associates create error-state RepoEntry. Thread --strict
flag to raise on missing associates.

## Applicable Assertions

- REQ-p00005-A: Cross-repo requirement references
- REQ-p00005-D: Discover associate identity from its config
- REQ-p00005-E: Report error when associate path missing
- REQ-d00202-A: Read associates from config
- REQ-d00202-D: Reject transitive associates

## Baseline

- 2734 passed, 299 deselected
