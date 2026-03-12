# Task 1: Add Stereotype Enum and INSTANCE EdgeKind

**Status**: Complete
**Branch**: claude/cross-cutting-requirements-2Zd0c
**Ticket**: CUR-1082

## Description

Add `Stereotype` enum (`CONCRETE`, `TEMPLATE`, `INSTANCE`) to `graph/relations.py`.
Add `EdgeKind.INSTANCE = "instance"` to EdgeKind enum.
`INSTANCE` and `SATISFIES` must NOT contribute to coverage.
Coverage must propagate through INSTANCE and SATISFIES edges (like REFINES).

## APPLICABLE_ASSERTIONS

- **REQ-p00014-C**: The system SHALL classify nodes using a `Stereotype` field: `CONCRETE` (default), `TEMPLATE` (original nodes targeted by Satisfies), or `INSTANCE` (cloned copies). Each instance node SHALL have an INSTANCE edge to its template original.
- **REQ-d00069-H**: When a requirement declares `Satisfies: X`, the graph builder SHALL clone the template's REQ subtree with composite IDs (`declaring_id::original_id`), creating INSTANCE nodes linked to the declaring requirement via a SATISFIES edge. (This task covers the INSTANCE EdgeKind portion only.)
- **REQ-p00050-A**: The system SHALL use TraceGraph as the ONE and ONLY data structure (ensure new enum lives in existing relations.py).

## Baseline

- 2358 passed, 94 deselected (all green)

## Tests Added

- `TestStereotypeEnum.test_REQ_p00014_C_stereotype_concrete_value`
- `TestStereotypeEnum.test_REQ_p00014_C_stereotype_template_value`
- `TestStereotypeEnum.test_REQ_p00014_C_stereotype_instance_value`
- `TestStereotypeEnum.test_REQ_p00014_C_stereotype_default_is_concrete`
- `TestEdgeKindSatisfies.test_REQ_p00014_C_instance_enum_value`
- `TestEdgeKindSatisfies.test_REQ_p00014_C_instance_does_not_contribute_to_coverage`

## Implementation Summary

- Added `Stereotype` enum to `src/elspais/graph/relations.py` with `CONCRETE`, `TEMPLATE`, `INSTANCE` values
- Added `EdgeKind.INSTANCE = "instance"` to EdgeKind enum
- INSTANCE does not contribute to coverage (same as SATISFIES, REFINES)
- Exported `Stereotype` from `src/elspais/graph/__init__.py`

## Verification

- 2364 passed, 94 deselected (all green, +6 new tests)
