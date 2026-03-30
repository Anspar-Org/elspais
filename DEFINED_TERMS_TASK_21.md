# Task 21: Inline Term Highlighting in REQ/JNY Cards

**Phase**: 9 (Viewer -- Inline Term Highlighting)
**Branch**: defined-terms2
**Ticket**: CUR-1082

## Description

Enhance simpleMarkdown() to annotate defined terms with clickable, hoverable spans in requirement and journey card bodies.

## Baseline

- 3508 passed, 321 deselected (2026-03-29)

## Applicable Assertions

- REQ-d00245-A: simpleMarkdown(text, true) wraps terms in .defined-term spans with data-term-key and data-tip, longest-first, word-boundary, case-insensitive
- REQ-d00245-B: Click opens term card via delegated handler, hover tooltip, no annotation in term cards

## Test Summary

5 tests in `tests/server/test_terms_highlight.py`:
- TestTermHighlightJs (5): annotateTerms param, termsRegex, defined-term class, delegated click handler, no annotation in term cards

## Implementation Summary

- Modified: `_card-stack.js.j2` -- enhanced simpleMarkdown(text, annotateTerms), added _buildTermsRegex(), delegated click handler on card-stack-body for .defined-term
- Modified: `_nav-tree.js.j2` -- invalidate termsRegex on reload
- Modified: `trace_unified.html.j2` -- added termsRegex to editState
- Modified: `_terms.css.j2` -- added .defined-term styles with dotted underline, hover highlight, tooltip via [data-tip]::after
- Updated call sites: remainder (true), journey context (true), journey sections (true), term definition (no arg = false)

## Verification

- 5/5 new tests pass
- 3513 passed, 321 deselected (full suite)
- Lint clean
