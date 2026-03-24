# TERMS-001 Task 4: TraceGraph._terms and GraphBuilder Integration

## Description
Add `_terms: TermDictionary` to `TraceGraph`. Wire `definition_block` content type through `GraphBuilder`. Add cross-repo merge in `FederatedGraph`.

## Applicable Assertions
- **REQ-d00222-A**: TraceGraph._terms + GraphBuilder definition_block handling
- **REQ-d00222-B**: defined_in points to REQUIREMENT or FILE ancestor
- **REQ-d00222-C**: FederatedGraph merges per-repo _terms

## Progress
- [x] Baseline: 3241 passed
- [x] TASK_FILE created
- [x] Assertions created: REQ-d00222 A-C
- [x] Failing tests written: tests/test_terms_integration.py (6 tests)
- [x] Implementation complete
- [x] Verification passed: 3247 passed, 321 deselected
- [x] Version bumped: 0.111.83 -> 0.111.84
- [x] Committed

## Tests
- `test_REQ_d00222_A_tracegraph_has_terms`
- `test_REQ_d00222_A_builder_creates_remainder_for_definition`
- `test_REQ_d00222_A_builder_populates_terms`
- `test_REQ_d00222_A_collection_flag_preserved`
- `test_REQ_d00222_B_defined_in_points_to_file`
- `test_REQ_d00222_B_defined_in_points_to_requirement`

## Implementation
- `src/elspais/graph/builder.py`:
  - Added `_terms: TermDictionary` field to `TraceGraph` dataclass
  - Added `_pending_terms` list to `GraphBuilder`
  - Added `definition_block` handler in `add_parsed_content()`
  - Added `_add_definition_block()` method creating REMAINDER nodes with content_type="definition_block"
  - Added definition handling in `_add_requirement()` for requirement-level definitions
  - Added _terms population in `build()` with defined_in ancestor resolution
- `src/elspais/graph/federated.py`:
  - Added `_merge_terms()` method merging per-repo _terms into federated TermDictionary
  - Called during `__init__()` after mutation log setup
- `spec/prd-core.md`: Added REQ-d00222 with assertions A-C
