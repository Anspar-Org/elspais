# OLD_PLAN.md - Completed Enhancement Issues

This file contains completed enhancement issues moved from MASTER_PLAN.md.

---

## Completed Bugs

### [x] trace --report: All report types (minimal, standard, full) produce the same output
  - **Issue**: The `--report` CLI argument was defined but never used in the trace command implementation
  - **Fix**: Implemented `ReportPreset` dataclass with three presets:
    - `minimal`: ID, title, status only
    - `standard`: ID, title, level, status, implements (default)
    - `full`: All fields including body, assertions, hash, code/test refs
  - **Completed**: 2026-01-27
  - **Commit**: [CUR-514] fix(trace): Implement --report presets (minimal/standard/full)

### [x] trace --view: Version shows "v1" instead of actual elspais version
  - **Issue**: `HTMLGenerator.__init__` had `version: int | str = 1` hardcoded default
  - **Fix**: Import `__version__` from elspais and use as default
  - **Completed**: 2026-01-27
  - **Commit**: [CUR-514] fix(html): Display actual package version in trace --view

### [x] trace --view: Files filter toggle doesn't show files in tree hierarchy
  - **Issue**: "Files" filter was confusing - files aren't graph nodes, so it didn't work as expected
  - **Fix**: Replaced "Files" with "Tests" filter:
    - Shows TEST nodes in tree hierarchy (with 🧪 icon)
    - Badge displays count of test nodes instead of file count
    - Clicking badge shows test rows that validate requirements
    - Added `is_test` attribute to TreeRow and template
  - **Completed**: 2026-01-27
  - **Commit**: [CUR-514] fix(html): Replace Files filter with Tests filter

### [x] trace --view: Assoc (Associated) toggle is broken
  - **Issue**: Assoc filter used "SHOW ONLY" semantic while PRD/OPS/DEV used "HIDE" semantic
  - **Fix**: Changed to HIDE semantic - clicking Assoc badge now hides associated requirements
  - **Completed**: 2026-01-27
  - **Commit**: [CUR-514] fix(html): Fix Assoc toggle and add Core toggle

### [x] trace --view: Core toggle doesn't work
  - **Issue**: Core badge was added to HTML but filter logic was missing
  - **Fix**:
    - Added `core: false` to activeFilters state
    - Added filter logic: when active, hides non-associated (core) requirements
    - Added CSS active state styling for consistency
    - Integrated with restoreState() for cookie persistence
  - **Completed**: 2026-01-27
  - **Commit**: [CUR-514] fix(html): Fix Assoc toggle and add Core toggle

### [x] trace --view: State persistence with cookies
  - **Issue**: Tree collapse/expand state was not persisted - users lost their tree state on page refresh
  - **Fix**:
    - Added `collapsedNodes` array to saveStateToCookie() (Set → Array for JSON serialization)
    - Added restoration logic in restoreState() (Array → Set, plus toggle button visual updates)
    - Fixed initialization order: check for saved state before applying defaults (collapseAll)
    - Added collapsedNodes.clear() to clearAllCookies() reset
  - **Completed**: 2026-01-28
  - **Commit**: [CUR-514] fix(html): Add tree collapse/expand state persistence

---

## Completed Quick Wins

### [x] CLI implementation audit
  - **Issue**: Multiple CLI arguments were defined but never used in implementation (dead code)
  - **Audit Result**: Found 19 dead arguments across 3 commands
  - **Fix**:
    - Removed 5 dead args from `validate`: --fix, --core-repo, --tests, --no-tests, --mode
    - Removed 5 dead args from `trace`: --port, --mode, --sponsor, --graph, --depth
    - Simplified `reformat-with-claude` to stub (8 dead args removed, entire command not implemented)
    - Added NOTE comments explaining removed arguments
    - Kept properly-stubbed features (trace --edit-mode, --review-mode, --server)
  - **Completed**: 2026-01-28
  - **Commit**: [CUR-514] chore(cli): Remove dead code arguments from CLI
