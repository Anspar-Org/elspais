# Task 4: SourceLocation Removal

**Branch**: claude/cross-cutting-requirements-2Zd0c
**Ticket**: CUR-1082
**Requirement**: REQ-d00129

## Objective

Delete `SourceLocation` class and `GraphNode.source` field. Migrate all ~15 consumers to use `file_node()` for paths and `get_field("parse_line")`/`get_field("parse_end_line")` for line numbers.

## Audit: SourceLocation References

### Production code (src/elspais/)

1. `graph/GraphNode.py` - SourceLocation class definition (line 55), source field (line 102)
2. `graph/__init__.py` - SourceLocation export (lines 6, 24, 33)
3. `graph/builder.py` - SourceLocation import (line 19), 10+ construction sites
4. `graph/annotators.py` - node.source.path (lines 68, 129, 350-351)
5. `graph/serialize.py` - node.source.path/line/end_line/repo (lines 41-48, 195-196)
6. `graph/link_suggest.py` - node.source.path (lines 148-150, 214-217, 282, 329-347, 463)
7. `graph/test_code_linker.py` - node.source.path (lines 81-84, 199-201)
8. `commands/trace.py` - node.source.path/line (lines 151, 391-392)
9. `commands/validate.py` - node.source.path/line (lines 106-107, 220, 235, 253-255)
10. `commands/index.py` - node.source.path (lines 335, 359)
11. `commands/fix_cmd.py` - node.source (line 117)
12. `mcp/server.py` - node.source.path/line (lines 80-86, 166, 173, 190, 245, 255, 264, 388-390, 530-533, 2016-2017)
13. `server/app.py` - node.source.path/repo/line (lines 295-308, 380-381, 467-468)
14. `server/persistence.py` - node.source.path (lines 69-71, 176-178, 425)
15. `html/generator.py` - node.source.path/line (lines 299-302, 311, 391-393, 405-407, 532-533, 668-669, 702-703, 739-740, 800-802, 826-827, 886-887, 962-963)
16. `pdf/assembler.py` - node.source.path/line (lines 315-316, 320)
17. `utilities/git.py` - node.source.path (lines 250, 257)

### Test code (tests/)

95 occurrences of `source=SourceLocation(...)` across 11 test files.

## Assertions (REQ-d00129)

- A: SourceLocation class removed
- B: GraphNode.source field removed
- C: parse_line/parse_end_line as fields
- D: Consumers use file_node().get_field("relative_path")
- E: Consumers use get_field("parse_line")
- F: Consumers use file_node().get_field("repo")
- G: External output unchanged

## Progress

- [x] Baseline tests pass (2528)
- [x] Task file created
- [x] Audit complete
- [x] Spec requirement REQ-d00129 added
- [x] Tests written (test_source_location_removal.py)
- [x] Implementation complete (all consumers migrated, SourceLocation deleted)
- [x] Verification pass (2518 passed, 0 failed)
- [x] Docs updated (CHANGELOG, CLAUDE.md, spec)
- [x] Version bumped (0.104.4)
- [ ] Committed
