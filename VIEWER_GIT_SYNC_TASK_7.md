# Task 7: Branch Creation Modal

## Status: DONE

## Summary

Added a modal dialog that prompts the user for a branch name. Triggered in two scenarios:
1. On viewer load when on `main` AND dirty spec files exist
2. When toggling edit mode ON while on `main` (even with a clean tree)

Edit mode only activates after the branch is successfully created (via callback).

## Files Changed

- `src/elspais/html/templates/partials/css/_edit-mode.css.j2` — added modal overlay/dialog styles
- `src/elspais/html/templates/partials/js/_edit-engine.js.j2` — added `showBranchModal()`, modified `toggleEditMode()`

## Assertions

- REQ-p00004-D: create and switch to a new git branch

## Behavior

- `toggleEditMode()` now checks `/api/git/status` before enabling edit mode
- If `is_main` is true, shows branch modal with callback to activate edit mode
- Modal supports Enter to create, Escape to cancel, overlay click to dismiss
- On success: toast, refresh badge, invoke callback
- On error: inline error message in modal
