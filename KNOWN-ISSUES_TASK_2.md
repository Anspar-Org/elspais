# Task 2: Fix mutation refresh gaps in viewer

## Description

The current mutation flow only refreshes the card that was directly mutated. Several parts of the GUI are NOT refreshed:

1. Nav tree row for status/title changes
2. File viewer panel showing source content
3. Header stats after add/delete
4. Other open cards referencing the mutated node

## APPLICABLE_ASSERTIONS

- **REQ-p00006-A**: "The tool SHALL generate an interactive HTML view with clickable requirement navigation."
  - Navigation tree must stay in sync with mutations.

## Manual Test Plan

1. Open two cards that reference each other
2. Change title on card A -- verify nav tree updates AND card B shows new title
3. Change status on card A -- verify nav tree updates
4. Delete an edge -- verify both cards refresh
5. Undo -- verify affected cards refresh
6. Save -- verify file viewer updates if open

## Implementation

### Step A: loadTreeData() after status/title changes

- `_edit-engine.js.j2`: onStatusChange (~line 259), onTitleBlur (~line 288)

### Step B: refreshAllOpenCards() helper

- New async function using Promise.all on all open card IDs

### Step C: Use refreshAllOpenCards() in edge mutations and undo

- onToggleEdgeKind, onDeleteEdge, doUndo

### Step D: refreshFileViewer() in _file-viewer.js.j2

- Reload current file if viewer is open

### Step E: Call refreshFileViewer() after save

## Verification

- All 2654 tests pass (no regressions)
- No lint issues (JS in Jinja2 template, no linter configured)
- Manual verification: pending (user must verify in browser)
