# Task 6: Branch Indicator in Header

## Status: DONE

## Summary

Added a branch badge in the viewer header (edit mode) showing:
- Branch name (monospace text)
- Colored status dot: green (clean feature branch), blue (dirty spec files), red (on main)
- Refresh button (visible when remote has diverged and fast-forward is possible) — triggers `doGitPull()`
- Warning icon `!` (visible when remote has diverged and fast-forward is NOT possible)

## Files Changed

- `src/elspais/html/templates/partials/_header.html.j2` — added branch badge HTML before edit toggle
- `src/elspais/html/templates/partials/css/_edit-mode.css.j2` — added branch badge styles
- `src/elspais/html/templates/partials/js/_edit-engine.js.j2` — added `refreshBranchStatus()`, `doGitPull()`, polling

## Assertions

- REQ-p00004-C: git status summary (branch, main detection, dirty files, divergence)
- REQ-p00004-D: branch creation and switching

## Polling

- `refreshBranchStatus()` called on page load
- `setInterval(refreshBranchStatus, 60000)` polls every 60 seconds
