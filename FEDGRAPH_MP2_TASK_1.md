# Task 1: Redirect Associate Call Sites to New Config System

**Branch**: claude/cross-cutting-requirements-2Zd0c
**Ticket**: CUR-1082
**Status**: Complete

## Description

Skip legacy sponsor scanning when [associates] config is present, redirecting
to the new federation pipeline. Old system still works for repos without [associates].

## Implementation

Modified factory.py: when `[associates]` config is present and `_build_associates=True`,
skip the old `scan_sponsors` logic to avoid double-loading associate specs.

## Verification

- 2743 tests pass
- Tested on hht_diary: old system (5373 merged) and new system (4320+1053 federated)
