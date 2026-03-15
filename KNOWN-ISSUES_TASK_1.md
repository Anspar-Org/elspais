# Task 1: Fix scroll-to targeting in REQ Card column

## Description

The `focusCard()` function in `_card-stack.js.j2` calls `card.scrollIntoView()` on the card element, then calls `renderCardStack()` which rebuilds the entire card DOM -- the element scrolled to gets replaced and the scroll position becomes stale.

**Fix**: Render first, then scroll to the newly-rendered card element.

## APPLICABLE_ASSERTIONS

- **REQ-p00006-A**: "The tool SHALL generate an interactive HTML view with clickable requirement navigation."
  - No new assertion needed; scroll-to-card is part of clickable navigation.

## Manual Test Plan

Since this is a JS-only fix in a Jinja2 template with no automated test harness:

1. Open viewer, open 3+ cards
2. Click between cards in nav tree -- each should scroll to correct card
3. Click same card twice -- no jitter

## Implementation

- File: `src/elspais/html/templates/partials/js/_card-stack.js.j2`
- Function: `focusCard()` (lines 42-57)
- Change: Move `renderCardStack()` and `saveState()` BEFORE `scrollIntoView()`, re-query card element after render.

## Verification

- All 2654 tests pass (no regressions)
- No lint issues (JS in Jinja2 template, no linter configured)
- Manual verification: pending (user must verify in browser)
