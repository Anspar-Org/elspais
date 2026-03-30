# Task 18: Terms API Endpoints

**Phase**: 6 (Viewer -- API Endpoints)
**Branch**: defined-terms2
**Ticket**: CUR-1082

## Description

Add two REST API endpoints to the viewer server:
- `GET /api/terms` -- returns JSON array of all terms (alphabetical)
- `GET /api/term/{term_key}` -- returns full detail for one term

## Baseline

- 3490 passed, 321 deselected (2026-03-29)

## Applicable Assertions

- REQ-d00242-A: GET /api/terms returns sorted term list with summary fields
- REQ-d00242-B: GET /api/term/{key} returns full detail with resolved references
- REQ-d00242-C: GET /api/term/{nonexistent} returns 404

(Created in spec/prd-features.md)

## Test Summary

9 tests in `tests/server/test_terms_api.py`:
- TestTermsListEndpoint (5): sorted order, required fields, truncation, ref_count, empty dict
- TestTermDetailEndpoint (3): full detail, node_title resolution, reference fields
- TestTermNotFound (1): 404 for nonexistent key

## Implementation Summary

- Modified: `src/elspais/server/routes_api.py` -- added `api_terms()` and `api_term()` functions
- Modified: `src/elspais/server/app.py` -- imported and registered routes
- `api_terms()` accesses `state.graph._terms`, sorts by term.lower(), truncates definitions >150 chars
- `api_term()` resolves node_title via `state.graph.find_by_id(ref.node_id)`

## Verification

- 9/9 new tests pass
- 3499 passed, 321 deselected (full suite)
- Lint clean
