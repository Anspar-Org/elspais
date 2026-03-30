# Task 20: Term Cards in Card Stack

**Phase**: 8 (Viewer -- Term Cards)
**Branch**: defined-terms2
**Ticket**: CUR-1082

## Description

Implement openTermCard() and buildTermCardHtml() so clicking a term in the nav tree opens a read-only card in the card stack showing definition, source link, and grouped references.

## Baseline

- 3503 passed, 321 deselected (2026-03-29)

## Applicable Assertions

- REQ-d00244-A: openTermCard fetches /api/term/{key}, card shows name, definition, defined-in, namespace, collection badge
- REQ-d00244-B: References grouped by namespace, clickable, empty state message, defined-in link opens source card
- REQ-d00244-C: Read-only (no edit controls), buildTermCardHtml(), kind === 'term' branch in renderCardStack

## Test Summary

5 tests in `tests/server/test_terms_card.py`:
- TestTermCardJsRendered (3): openTermCard in HTML, buildTermCardHtml in HTML, 'term' kind in renderCardStack
- TestTermCardApiIntegration (2): API returns card data fields, empty references array

## Implementation Summary

- Modified: `_card-stack.js.j2` -- added openTermCard(), buildTermCardHtml(), kind === 'term' in renderCardStack dispatch
- Modified: `_nav-tree.js.j2` -- removed stub openTermCard (real impl now in card-stack)
- Modified: `_terms.css.j2` -- added term card styles (.term-card, .term-collection-badge, .term-definition, .term-ref-row, etc.)
- Modified: `spec/prd-features.md` -- added REQ-d00244

## Verification

- 5/5 new tests pass
- 3508 passed, 321 deselected (full suite)
- Lint clean
