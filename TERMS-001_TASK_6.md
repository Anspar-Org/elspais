# TERMS-001 Task 6: Glossary and Term Index Generators

## Description
Create `commands/glossary_cmd.py` with generate_glossary, generate_term_index, generate_collection_manifest.

## Applicable Assertions
- **REQ-d00224-A**: generate_glossary() alphabetical Markdown with letter headings
- **REQ-d00224-B**: generate_term_index() indexed terms only, namespace grouping
- **REQ-d00224-C**: generate_collection_manifest() standalone per collection term
- **REQ-d00224-D**: auto-generated header, markdown/json format support

## Progress
- [x] Baseline: 3256 passed
- [x] TASK_FILE created
- [x] Assertions created: REQ-d00224 A-D
- [x] Failing tests written: tests/test_glossary_cmd.py (9 tests)
- [x] Implementation complete: src/elspais/commands/glossary_cmd.py
- [x] Verification passed: 3265 passed, 321 deselected
- [x] Version bumped: 0.111.85 -> 0.111.86
- [x] Committed
