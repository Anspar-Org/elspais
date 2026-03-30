# Task 22: Polish and Edge Cases

**Phase**: 9 (Viewer -- Polish)
**Branch**: defined-terms2
**Ticket**: CUR-1082

## Description

Verify edge cases, fix any issues, run full test suite, check off KNOWN_ISSUES.md items.

## Edge Cases to Verify

1. Terms tab with empty TermDictionary shows "No defined terms found"
2. Term cards with zero references show "No references resolved yet"
3. Term card scroll-into-view on open (reuse focusCard pattern)
4. Cookie persistence of Terms tab (activeNavTab='terms' survives reload)
5. Terms data reloads on graph refresh (after save/checkpoint)
6. Regex rebuilt when terms data reloads

## Verification Results

1. PASS -- renderNavTree() terms branch shows "No defined terms found" when empty
2. PASS -- buildTermCardHtml() shows "No references resolved yet" when refs.length === 0
3. PASS -- openTermCard() calls focusCard() which uses scrollIntoView
4. PASS -- editState.activeNavTab included in saveState()/loadState() cookie persistence
5. FIXED -- loadTreeData() now calls loadTermsData() at end, so terms reload on every graph refresh
6. PASS -- loadTermsData() sets editState.termsRegex = null to invalidate cached regex

## Issues Fixed

- loadTermsData() was only called on page init, not after mutations/saves. Fixed by having loadTreeData() call it.
- Marked 2 KNOWN_ISSUES.md items as done: "defined terms — viewer" and "Term Index and Glossary tabs"

## Full Test Suite

- 3513 passed, 321 deselected
