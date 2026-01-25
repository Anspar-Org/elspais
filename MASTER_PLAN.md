# Master Plan: elspais Enhancement Issues

This file tracks a queue of enhancement issues to be implemented sequentially. After each `/clear`, Claude should read this file and continue with the next incomplete issue.

## Workflow

1. **Pick next issue**: Find the first `[ ]` (incomplete) issue below
2. **Refine into plan**: Use sub-agents to analyze the codebase and create a detailed implementation plan
3. **Implement**: Execute the plan, writing code and tests
4. **Verify**: Run tests, ensure the feature works
5. **Mark complete**: Change `[ ]` to `[x]` for the issue
6. **Commit**: Create a git commit for the changes
7. **Clear context**: Run `/clear` to free up context
8. **Resume**: After clear, read this file and continue with next issue

---

## Issue Queue (Prioritized)

### Priority 1: Fix HTML hierarchy toggle state in --view
- **Status**: [x] Complete
- **Priority**: P1 - Bug fix (quick win, immediate UX improvement)
- **Description**: Open/close markers in `--view` HTML hierarchy default to the wrong state. Users have to double-toggle them to get them to work.
- **Files likely involved**: `src/elspais/trace_view/html/static/`, JavaScript
- **Acceptance criteria**:
  - [x] Toggle markers work on first click
  - [x] Default state is consistent and expected
  - [x] Test toggle behavior (all 713 tests pass)
- **Resolution**: Fixed hierarchy view initialization to set ALL expandable items to collapsed state (not just roots), ensuring icon state matches visual state.

---

### Priority 2: Assertion-level references in all contexts
- **Status**: [x] Complete
- **Priority**: P1 - Core correctness (builds on recent work)
- **Description**: Ensure assertion-level references (REQ-xxx-A) are handled properly in all contexts throughout the codebase.
- **Files likely involved**: All parsers, graph builder, reporters
- **Acceptance criteria**:
  - [x] Audit all contexts where requirement refs are used
  - [x] Verify assertion refs work in each context
  - [x] Add tests for any gaps found (6 new tests)
- **Resolution**: Comprehensive audit of 10+ contexts. Found 1 real gap in `trace_view/scanning.py` - fixed. All other "gaps" were either intentional design or false positives.

---

### Priority 3: Update coverage report with direct/explicit vs inferred breakdown
- **Status**: [x] Complete
- **Priority**: P2 - Feature completion (completes coverage semantics work)
- **Description**: Coverage report should treat direct and explicit coverage equally. Report both "Direct/Explicit" numbers and "Inferred (including direct/explicit)" numbers. Avoid double-counting.
- **Files likely involved**: `src/elspais/core/graph_builder.py`, `src/elspais/core/graph_schema.py`, report generators
- **Acceptance criteria**:
  - [x] Report shows "Direct/Explicit" coverage count
  - [x] Report shows "Inferred (total including direct/explicit)" count
  - [x] Inferred count >= Direct/Explicit count (no double-counting)
  - [x] Update any affected tests (all 719 tests pass)
- **Resolution**: Added direct_covered, explicit_covered, inferred_covered to standard/full report presets. Updated summary metrics table to show breakdown with "Direct/Explicit (high confidence)" combined count.

---

### Priority 4: Fix local links in static HTML (--view without --embed-content)
- **Status**: [x] Complete
- **Priority**: P2 - UX fix (may require investigation)
- **Description**: Opening links from static HTML without `--embed-content` doesn't work. Either fix the links, remove them, or detect if they'll work and enable/disable accordingly.
- **Files likely involved**: `src/elspais/trace_view/html/`, JavaScript files
- **Acceptance criteria**:
  - [x] Investigate if local file links can work (security restrictions)
  - [x] If they can work sometimes: detect and enable/disable dynamically
  - [x] If they can never work: remove or hide the broken links
  - [x] Document the behavior
- **Resolution**: Added info banner when not using --embed-content explaining that file links are disabled due to browser security. Banner shows available options: --embed-content or --server.

---

### Priority 5: Diff view for changed files in --view
- **Status**: [ ] Incomplete
- **Priority**: P3 - Feature enhancement
- **Description**: In `--view` mode, changes are indicated but there's no way to see the actual file diff. Add diff visualization for changed files.
- **Files likely involved**: `src/elspais/trace_view/`, `src/elspais/commands/trace.py`
- **Acceptance criteria**:
  - [ ] Show file diff when change is indicated
  - [ ] Integrate with git diff or compute diff inline
  - [ ] Display in HTML view with syntax highlighting

---

### Priority 6: Configurable graph depth scoping
- **Status**: [ ] Incomplete
- **Priority**: P3 - Feature enhancement
- **Description**: Graph generation should support scoping to various depth levels: requirements, assertions, files, tests, etc. Since this is a configurable system, depth levels should come from config.
- **Files likely involved**: `src/elspais/core/graph_schema.py`, `src/elspais/commands/trace.py`
- **Acceptance criteria**:
  - [ ] Add `--depth` flag or similar to control graph scope
  - [ ] Depth levels derived from schema/config
  - [ ] Document the depth options

---

### Priority 7: INDEX regeneration should pass markdownlint
- **Status**: [ ] Incomplete
- **Priority**: P4 - Polish
- **Description**: Regenerating INDEX files should produce output that passes markdown lint validation.
- **Files likely involved**: `src/elspais/commands/index.py`, output generation
- **Acceptance criteria**:
  - [ ] Generated INDEX files pass markdownlint
  - [ ] Proper heading structure, spacing, and formatting

---

### Priority 8: MCP TODO items
- **Status**: [ ] Incomplete
- **Priority**: P4 - Unknown scope (needs file location)
- **Description**: Address items from MCP TODO file. (Note: File location needs to be provided by user)
- **Files likely involved**: `src/elspais/mcp/`
- **Acceptance criteria**:
  - [ ] Locate MCP TODO file
  - [ ] Implement each item
  - [ ] Test MCP functionality

---

## Completed Issues

(Move completed issues here with completion date)

---

## Priority Legend

| Priority | Meaning |
|----------|---------|
| P1 | Bug fixes, core correctness - do first |
| P2 | Feature completion, UX fixes |
| P3 | Feature enhancements |
| P4 | Polish, unknown scope |

---

## Notes

- Each issue should result in a single commit or small commit series
- Run full test suite before marking complete
- Update CHANGELOG.md for user-visible changes
- Update CLAUDE.md if architecture changes significantly
