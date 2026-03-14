# FILENODE_TASK_1: Core Data Model Additions

**Branch**: claude/cross-cutting-requirements-2Zd0c
**Ticket**: CUR-1082
**Date**: 2026-03-13

## Description

Add `NodeKind.FILE`, `FileType` enum, new `EdgeKind` values (STRUCTURES, DEFINES, YIELDS),
and `Edge.metadata` field. Purely additive changes — no existing behavior modified.

## APPLICABLE_ASSERTIONS

- REQ-d00126-A: NodeKind.FILE with value "file"
- REQ-d00126-B: FileType enum (SPEC, JOURNEY, CODE, TEST, RESULT)
- REQ-d00126-C: EdgeKind STRUCTURES, DEFINES, YIELDS
- REQ-d00126-D: New edge kinds do not contribute to coverage
- REQ-d00126-E: Edge.metadata field excluded from `__eq__`/`__hash__`

## Assertions Created

Added REQ-d00126 (FILE Node Data Model) with assertions A-E to `spec/07-graph-architecture.md`.

## Test Summary

Tests in `tests/core/test_file_node_data_model.py`:
- TestNodeKindFile: FILE value exists (REQ-d00126-A)
- TestFileTypeEnum: FileType enum values (REQ-d00126-B)
- TestEdgeKindFileAware: STRUCTURES, DEFINES, YIELDS exist (REQ-d00126-C)
- TestEdgeKindCoverage: New edge kinds don't contribute to coverage (REQ-d00126-D)
- TestEdgeMetadata: metadata field defaults, excluded from eq/hash (REQ-d00126-E)

## Implementation Summary

- `src/elspais/graph/GraphNode.py`: Added `NodeKind.FILE = "file"` and `FileType` enum (SPEC, JOURNEY, CODE, TEST, RESULT)
- `src/elspais/graph/relations.py`: Added `EdgeKind.STRUCTURES`, `DEFINES`, `YIELDS`; added `Edge.metadata: dict[str, Any]` with `field(default_factory=dict)`
- `src/elspais/graph/__init__.py`: Exported `FileType` in `__all__`
- `contributes_to_coverage()` already returns False for new edge kinds (whitelist pattern)
- `Edge.__eq__`/`__hash__` already exclude metadata (manually defined methods)

## Verification

2483 passed, 94 deselected in 11.46s (21 new tests + 2462 existing)

## Commit

(see git log)
