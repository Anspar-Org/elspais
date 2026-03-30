# Task 19: Terms Tab in Nav Tree

**Phase**: 7 (Viewer -- Terms Tab)
**Branch**: defined-terms2
**Ticket**: CUR-1082

## Description

Add a "Terms" tab in the viewer nav panel that shows an alphabetical list of defined terms with letter headings and reference count badges.

## Baseline

- 3499 passed, 321 deselected (2026-03-29)

## Applicable Assertions

- REQ-d00243-A: Terms tab button with data-kind="terms", switchNavTab, cookie persistence
- REQ-d00243-B: Flat alphabetical list with letter headings, term name, ref count badge, empty state
- REQ-d00243-C: Hide expand/collapse, tree/flat toggle, filter groups; text filter filters terms

## Test Summary

4 tests in `tests/server/test_terms_nav.py`:
- TestTermsTabRendering (2): button rendered with data-kind="terms", switchNavTab onclick
- TestTermsNavEmpty (1): empty dictionary returns [] (data flow)
- TestTermsNavControls (1): JS references 'terms' tab and view-mode-toggle

## Implementation Summary

- Modified: `trace_unified.html.j2` -- added Terms tab button, termsData/termsLookup in editState, loadTermsData() call, CSS include
- Modified: `_nav-tree.js.j2` -- added loadTermsData(), terms branch in renderNavTree() with letter headings and text filter, updated switchNavTab() to hide controls
- Created: `partials/css/_terms.css.j2` -- styles for letter headings, term rows, ref count badges
- Modified: `spec/prd-features.md` -- added REQ-d00243

## Verification

- 4/4 new tests pass
- 3503 passed, 321 deselected (full suite)
- Lint clean
