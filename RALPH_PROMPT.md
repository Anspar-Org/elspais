# Ralph Loop: Complete MASTER_PLAN.md

## Your Mission

Complete all remaining phases in `MASTER_PLAN.md`. Work systematically through each unchecked item.

## Instructions

1. **Read MASTER_PLAN.md** to find the first unchecked `[ ]` item
2. **Complete that item** following the Workflow Steps
3. **Mark it `[x]`** when done
4. **Commit after each phase** with `[CUR-514]` prefix
5. **Continue** until all phases are complete

## Phase 6: Test Coverage Tools

Implement these MCP tools in `src/elspais/mcp/server.py`:

- `get_test_coverage(req_id)` - Find TEST nodes for a requirement
- `get_uncovered_assertions(req_id=None)` - Find assertions without tests
- `find_assertions_by_keywords(keywords, match_all)` - Search assertion text

**Pattern**: Follow existing MCP tool implementations. Use `@mcp.tool()` decorator.

## Phase 7: Comprehensive Assertion Coverage

Use Phase 6 tools to improve test-requirement traceability:

- Analyze test files, propose renames or new specs
- Analyze source files, ensure requirement coverage
- Track proposals in `docs/NEW_SPECS.md`
- Target: >80% assertion coverage

## Workflow Per Item

```
1. SPEC: Add/verify requirement in spec/
2. TEST: Write tests with REQ naming (test_REQ_xxx_A_...)
3. IMPL: Implement the feature
4. DEBUG: Run pytest, verify pass
5. COMMIT: git commit with [CUR-514] prefix
```

## Completion Signal

When ALL items in MASTER_PLAN.md are checked `[x]`:

```
<promise>MASTER_PLAN COMPLETE</promise>
```

## Current State

Check `MASTER_PLAN.md` for current progress. Check `git log --oneline -5` for recent work.

## Rules

- One phase section at a time
- Commit after completing each major section (6.2, 6.3, 6.4, etc.)
- Run `pytest` before committing
- Don't skip the SPEC step - add requirements to `spec/08-mcp-server.md`
- Use subagents for Phase 7 loops (test file analysis, code module analysis)
