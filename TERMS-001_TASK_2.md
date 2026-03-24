# TERMS-001 Task 2: TermDictionary Data Model

## Description
Create `graph/terms.py` with `TermEntry`, `TermRef`, and `TermDictionary` data classes.

## Applicable Assertions
- **REQ-d00220-A**: `TermDictionary.add()` SHALL store a `TermEntry` keyed by normalized (lowercased) term name. If the term already exists, it SHALL return the existing entry without overwriting.
- **REQ-d00220-B**: `TermDictionary.lookup()` SHALL perform case-insensitive lookup and return the `TermEntry` or `None`.
- **REQ-d00220-C**: `TermDictionary.iter_indexed()` SHALL yield only entries where `indexed` is `True`. `iter_collections()` SHALL yield only entries where `collection` is `True`.
- **REQ-d00220-D**: `TermDictionary.merge()` SHALL combine two dictionaries and return a list of `(TermEntry, TermEntry)` pairs for duplicate terms detected across namespaces.

## Progress
- [x] Baseline: 3224 passed
- [x] TASK_FILE created
- [x] Assertions created: REQ-d00220 A-D
- [x] Failing tests written: tests/test_term_dictionary.py (9 tests)
- [x] Implementation complete: src/elspais/graph/terms.py
- [x] Verification passed: 3233 passed, 321 deselected
- [x] Version bumped: 0.111.81 -> 0.111.82
- [x] Committed

## Tests
- `test_REQ_d00220_A_add_stores_entry`
- `test_REQ_d00220_A_add_returns_none_first_time`
- `test_REQ_d00220_A_add_duplicate_returns_existing`
- `test_REQ_d00220_B_lookup_case_insensitive`
- `test_REQ_d00220_B_lookup_missing_returns_none`
- `test_REQ_d00220_C_iter_indexed`
- `test_REQ_d00220_C_iter_collections`
- `test_REQ_d00220_D_merge_combines`
- `test_REQ_d00220_D_merge_detects_duplicates`

## Implementation
- `src/elspais/graph/terms.py`: TermRef, TermEntry (dataclasses), TermDictionary (add, lookup, iter_all, iter_indexed, iter_collections, merge)
- `spec/prd-core.md`: Added REQ-d00220 with assertions A-D
