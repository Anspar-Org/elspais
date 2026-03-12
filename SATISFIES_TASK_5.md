# Task 5: MCP Server and Viewer Updates for Instance Nodes

**Status**: Complete
**Branch**: claude/cross-cutting-requirements-2Zd0c
**Ticket**: CUR-1082

## Description

- Serialize `stereotype` field in `_serialize_node_generic()` response
- Include INSTANCE edges in serialization
- Update viewer card label "Implements / Refines" to include Satisfies
- Update edge toggle to handle satisfies kind
- Update add-relationship form to offer satisfies option

## APPLICABLE_ASSERTIONS

- **REQ-p00014-B**: Coverage of cloned nodes SHALL use the standard coverage mechanism.
- **REQ-p00014-C**: Stereotype field serialization.

## Baseline

- 2379 passed, 94 deselected (all green)

## Tests Added

- `TestMCPStereotypeSerialization.test_REQ_p00014_C_serialized_stereotype_concrete`
- `TestMCPStereotypeSerialization.test_REQ_p00014_C_serialized_stereotype_template`
- `TestMCPStereotypeSerialization.test_REQ_p00014_C_serialized_stereotype_instance`

## Implementation Summary

- MCP: Added `stereotype` to REQUIREMENT properties in `_serialize_node_generic()`
- MCP: Added INSTANCE to hierarchical edge filter (parents/links sections)
- Viewer: Updated card label to "Implements / Refines / Satisfies"
- Viewer: Edge toggle cycles through implements/refines/satisfies
- Viewer: Add-relationship form includes Satisfies option

## Verification

- 2382 passed, 94 deselected (all green, +3 new tests)
