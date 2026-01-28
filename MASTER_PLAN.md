# MASTER_PLAN.md

This file contains a prioritized queue of enhancement phases for elspais. Follow the workflow in CLAUDE.md for implementation.

---

## Phase 1: Trace View Improvements
**Status:** [x] Complete

**Goal:** Enhance the `elspais trace --view` HTML output with better assertion support, sorting, and filter UX.

**Test Repository:** `~/cure-hht/hht_diary-worktrees/fda-specs/`

### 1.1 Assertion-Level Requirements Support
**Tasks:**
- [x] Validate that assertion-level IDs parse correctly
- [x] Verify `Implements: REQ-xxx-A-B-C` multi-assertion syntax expands properly
- [x] Confirm coverage rollup works for explicit assertion references
- [x] Test hierarchy display shows assertion badges correctly
- [x] Ensure traceability paths include assertion-level detail
- [x] Document any issues found and fix them (fixed assertion linking to use parent REQ)

**Acceptance Criteria:**
- Running `elspais validate` on the fda-specs repo produces no errors related to assertions
- `elspais trace --view` displays assertion references correctly
- Coverage metrics accurately reflect assertion-level implementation status

### 1.2 HTML View Child Sorting
**Current Behavior:** Children appear in undefined/insertion order.

**Desired Behavior:**
1. Assertion children (A, B, C, ...) sorted alphabetically ascending
2. REQ children follow, sorted by ID

**Tasks:**
- [x] Identify where child ordering is determined in trace view generation
- [x] Implement sorting logic: assertions first (ascending), then REQs
- [x] Update Jinja2 templates if needed (not needed)
- [x] Add tests for sort order (verified manually with fda-specs)

**Acceptance Criteria:**
- In HTML view, assertion children (A, B, C) appear before REQ children
- Within each group, items are sorted alphabetically/numerically

### 1.3 PRD/DEV/OPS Filter Button UX
**Current Behavior:** Buttons may start "on" with first click toggling off.

**Desired Behavior:**
1. On page load: all filter buttons are "off" (filled/active state), all levels visible
2. First click on PRD button: turns filter "on" (hollow/inactive state), PRD nodes hidden
3. Second click: turns filter "off" again, PRD nodes visible

**Tasks:**
- [x] Review current filter button implementation
- [x] Update initial state to "off" (all visible) - was already correct
- [x] Update click handler: toggle → hide level when "on"
- [x] Update CSS: "on" = hollow, "off" = filled
- [x] Test all filter combinations

**Acceptance Criteria:**
- Fresh page load shows all PRD, DEV, OPS nodes
- All three filter buttons appear filled/active
- Clicking PRD makes button hollow and hides PRD nodes
- Clicking again restores PRD nodes and fills button

---

## Phase 1.5: Quick Improvements
**Status:** [x] Complete

**Goal:** Small but impactful usability improvements.

### 1.5.1 User Journey Trace View GUI ✓
- [x] User journeys need a better `trace --view` GUI experience
- [x] Design improved visualization for journey nodes in HTML output
- [x] Consider journey-specific filtering or highlighting

**Implementation:**
- Added `actor` and `goal` fields to `JourneyItem` dataclass
- Updated `_collect_journeys()` to extract actor/goal from parsed journey data
- Enhanced journey card layout with structured Actor/Goal metadata section
- Added search/filter toolbar for journeys (searches ID, title, actor, goal)
- Improved card styling with hover effects and better visual hierarchy
- Enhanced empty state with example journey format

### 1.5.2 Git Repository Root Detection ✓
- [x] elspais should check if it is in a git repo
- [x] Always run as if in the repository root (auto-detect and chdir)
- [x] Handle edge cases: not in git repo, nested repos, worktrees

**Implementation:**
- Added `find_git_root()` to `config/__init__.py` - searches upward for `.git`
- CLI `main()` auto-detects git root and changes directory before command execution
- Works with worktrees (`.git` file pointing to gitdir)
- Silent by default, verbose mode shows "Working from repository root: ..."
- If not in a git repo, continues silently (warns with `-v`)

**Acceptance Criteria:**
- ✓ User journeys are clearly visible and navigable in trace view
- ✓ Journey cards show Actor and Goal metadata when available
- ✓ Search/filter functionality for journeys
- ✓ Running `elspais` from any subdirectory works as if run from repo root
- ✓ Clear warning when not in a git repository (with -v flag)

---

## Phase 2: Documentation Completeness & Correctness Audit
**Status:** [ ] Not Started

**Goal:** Ensure documentation covers ALL command-line options and ALL `.toml` configuration options, and verify that documented behavior matches actual implementation.

**Scope:**
1. CLI options: Every flag and argument for every subcommand
2. TOML options: Every configuration key in `elspais.toml` / `pyproject.toml [tool.elspais]`
3. Correctness: Documented behavior matches implementation

**Files to Audit:**
- `docs/cli/*.md` - User documentation topics
- CLI `--help` output for all commands
- `config/` - Configuration schema and loader

**Tasks:**

### Completeness
- [ ] Generate list of all CLI commands and their options
- [ ] Generate list of all TOML configuration keys
- [ ] Cross-reference against existing docs
- [ ] Document missing CLI options
- [ ] Document missing TOML options

### Correctness
- [ ] Verify documented default values match code defaults
- [ ] Verify documented option descriptions match actual behavior
- [ ] Verify documented examples actually work
- [ ] Check for stale/outdated documentation (removed features, renamed options)
- [ ] Validate TOML key names and types match config loader expectations
- [ ] Run `pytest tests/test_doc_sync.py` to verify sync

**Acceptance Criteria:**
- Every CLI option has documentation in `docs/cli/`
- Every TOML key has documentation
- Documented defaults match implementation defaults
- Documented behavior matches actual behavior
- No stale documentation for removed/changed features
- `test_doc_sync.py` passes
- `elspais docs` topics are complete and accurate

---

## Phase 3: Health Check Command
**Status:** [ ] Not Started

**Goal:** Add `elspais health` command to diagnose configuration and repository issues.

**Command Structure:**
```
elspais health              # Comprehensive check (default)
elspais health --config     # TOML format and validity only
elspais health --spec       # spec/ file consistency only
elspais health --code       # Code reference consistency only
elspais health --tests      # Test file consistency only
```

**Checks to Implement:**

### Config Checks (`--config`)
- [ ] TOML syntax validity
- [ ] Required fields present
- [ ] Pattern tokens valid
- [ ] Hierarchy rules consistent
- [ ] File paths exist

### Spec Checks (`--spec`)
- [ ] All spec files parseable
- [ ] No duplicate requirement IDs
- [ ] All `Implements:` references resolve
- [ ] All `Refines:` references resolve
- [ ] Hierarchy levels consistent with rules

### Code Checks (`--code`)
- [ ] `# Implements:` comments reference valid REQs
- [ ] No orphaned code references

### Test Checks (`--tests`)
- [ ] Test files with REQ references are valid
- [ ] JUnit/pytest result files parseable
- [ ] Test→REQ mappings resolve

**Output Format:**
- Summary: ✓ passed, ✗ failed, ⚠ warnings
- Detailed issues with file:line references
- Suggestions for fixes

**Files to Create/Modify:**
- `cli/commands/health.py` - New command implementation
- `cli/main.py` - Register command
- `health/` - New module for check implementations
- `docs/cli/health.md` - Documentation

**Tasks:**
- [ ] Design check result data structure
- [ ] Implement config checks
- [ ] Implement spec checks
- [ ] Implement code checks
- [ ] Implement test checks
- [ ] Create CLI command with subcommand flags
- [ ] Add comprehensive output formatting
- [ ] Write tests for each check category
- [ ] Document command in `docs/cli/health.md`

**Acceptance Criteria:**
- `elspais health` runs all checks and reports summary
- Each `--flag` runs only that category
- Clear, actionable error messages
- Exit code 0 for healthy, non-zero for issues
- Documentation complete

---

## Notes

**Priority Order:** Phases are ordered by estimated impact and dependency:
1. Phase 1 consolidates all trace view improvements (core visual output)
2. Phase 2 ensures users can learn the tool
3. Phase 3 adds developer experience tooling

**Commit Discipline:** Create one commit per phase with `[CUR-514]` prefix.
