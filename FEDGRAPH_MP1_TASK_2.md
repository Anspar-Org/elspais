# Task 2: Detect Transitive Associates (Hard Error)

**Branch**: claude/cross-cutting-requirements-2Zd0c
**Ticket**: CUR-1082
**Status**: In Progress

## Description

When loading an associate's `.elspais.toml`, check if it declares `[associates]`.
If so, raise FederationError. Only root repo may declare associates.

## Applicable Assertions

- REQ-d00202-D: Transitive associates are a hard error

## Baseline

- 2732 passed, 299 deselected
