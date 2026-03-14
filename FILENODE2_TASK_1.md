# FILENODE2 Task 1: iter_roots() Parameterization

**Branch**: claude/cross-cutting-requirements-2Zd0c
**Ticket**: CUR-1082

## Assertions

- REQ-d00130-A: `iter_roots()` no-arg returns REQ + JOURNEY roots (excludes FILE)
- REQ-d00130-B: `iter_roots(NodeKind.FILE)` returns all FILE nodes from `_index`
- REQ-d00130-C: `iter_roots(NodeKind.REQUIREMENT)` returns only REQ roots
- REQ-d00130-D: `iter_roots(NodeKind.USER_JOURNEY)` returns only JOURNEY roots
- REQ-d00130-E: `iter_by_kind(kind)` iterates all nodes of given kind from `_index`
- REQ-d00130-F: FILE nodes NOT in default `iter_roots()` results

## Status

- [x] Baseline: 2518 tests pass
- [x] Spec assertions created in spec/07-graph-architecture.md
- [x] Tests written (13 tests in tests/core/test_parameterized_roots.py)
- [x] Implementation done
- [x] All tests pass (2531 = 2518 + 13 new)
- [x] CHANGELOG updated
- [x] Version bumped (0.104.4 -> 0.104.5)
- [ ] Committed
