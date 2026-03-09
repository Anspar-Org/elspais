# Task 8: Push Modal

## Status: Complete

## Objective

Add Push button to header and modal for committing and pushing spec changes.

## Assertions

- REQ-p00004-E: The tool SHALL commit modified spec files and optionally push, refusing to operate on main/master branches.
- REQ-p00004-C: The tool SHALL provide a git status summary reporting current branch, main-branch detection, dirty spec files, and remote divergence state.

## Changes

1. `src/elspais/html/templates/partials/_header.html.j2` — Add Push button after Revert button
2. `src/elspais/html/templates/partials/js/_edit-engine.js.j2` — Add `showPushModal()`, update `refreshBranchStatus()` for Push button
3. `src/elspais/html/templates/partials/css/_edit-mode.css.j2` — Add file list and btn-success styles
