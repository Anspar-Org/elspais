# Ralph Loop Configuration

This file configures the ralph loop - a self-directed work pattern for implementing phases from MASTER_PLAN.md.

## Instructions

When the ralph loop is triggered (via Stop hook or user command):

1. **Read MASTER_PLAN.md** - Find the first incomplete phase (marked with `[ ]`)
2. **Implement using TDD** - Write tests first, then implementation
3. **Mark complete** - Change `[ ]` to `[x]` when done
4. **Run tests** - Verify with `pytest tests/arch3/ -v`
5. **Commit** - Create a git commit with `[CUR-514]` prefix
6. **If all phases complete** - Output `<promise>ALL_PHASES_COMPLETE</promise>`

## Current Status

Phases 1-7 are complete (173 tests passing).
Phases 8-15 are pending.

## Phase Dependencies

| Phase | Component | Depends On |
|-------|-----------|------------|
| 8 | Git Integration | - |
| 9 | Annotators | Phase 8 |
| 10 | Test Result Parsers | Phase 2 |
| 11 | Heredocs Parser | Phase 2 |
| 12 | Serialization | Phase 9 |
| 13 | HTML Generator | Phases 8, 9, 12 |
| 14 | CLI Integration | Phase 13 |
| 15 | Cleanup | Phase 14 |
