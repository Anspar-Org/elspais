# Task 9: Unsaved Changes Warning

## Status: Complete

## Objective

Add `beforeunload` handler that fires when pending mutations exist OR uncommitted spec files exist.

## Assertions

- REQ-p00004-E: The tool SHALL commit modified spec files and optionally push, refusing to operate on main/master branches.

## Changes

1. `src/elspais/html/templates/partials/js/_edit-engine.js.j2` — Add `beforeunload` event handler
