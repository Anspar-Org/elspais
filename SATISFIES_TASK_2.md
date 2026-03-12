# Task 2: Add stereotype field to GraphNode

**Status**: Complete
**Branch**: claude/cross-cutting-requirements-2Zd0c
**Ticket**: CUR-1082

## Description

Add `stereotype` field to GraphNode, default `Stereotype.CONCRETE`.
Use `set_field("stereotype", ...)` / `get_field("stereotype", ...)`.

## APPLICABLE_ASSERTIONS

- **REQ-p00014-C**: The system SHALL classify nodes using a `Stereotype` field: `CONCRETE` (default), `TEMPLATE` (original nodes targeted by Satisfies), or `INSTANCE` (cloned copies). Each instance node SHALL have an INSTANCE edge to its template original.

## Baseline

- 2364 passed, 94 deselected (all green)

## Tests Added

- `TestGraphNodeStereotype.test_REQ_p00014_C_default_stereotype_is_concrete`
- `TestGraphNodeStereotype.test_REQ_p00014_C_set_stereotype_template`
- `TestGraphNodeStereotype.test_REQ_p00014_C_set_stereotype_instance`
- `TestGraphNodeStereotype.test_REQ_p00014_C_builder_sets_default_stereotype`

## Implementation Summary

- Added `Stereotype.CONCRETE` default to `GraphNode.__post_init__()` via `_content.setdefault()`
- Added `stereotype: Stereotype.CONCRETE` to builder's `_add_requirement()` content dict
- Fixed serializer to convert Enum values to `.value` for JSON compatibility

## Verification

- 2368 passed, 94 deselected (all green, +4 new tests)
