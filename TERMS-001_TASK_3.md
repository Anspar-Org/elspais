# TERMS-001 Task 3: Grammar Extension — DEF_LINE and definition_block

## Description
Add `DEF_LINE` terminal and `definition_block` grammar rule to `requirement.lark`. Add transformer handler.

## Applicable Assertions
- **REQ-d00221-A**: Grammar SHALL include DEF_LINE terminal and definition_block rule in appropriate contexts.
- **REQ-d00221-B**: Transformer SHALL handle definition_block nodes, extracting term, definition, collection, indexed.

## Progress
- [x] Baseline: 3233 passed
- [x] TASK_FILE created
- [x] Assertions created: REQ-d00221 A-B
- [x] Failing tests written: tests/test_definition_grammar.py (8 tests)
- [x] Implementation complete
- [x] Verification passed: 3241 passed, 321 deselected
- [x] Version bumped: 0.111.82 -> 0.111.83
- [x] Committed

## Tests
- `test_REQ_d00221_A_definition_between_requirements`
- `test_REQ_d00221_A_definition_in_requirement_preamble`
- `test_REQ_d00221_A_definition_in_named_block`
- `test_REQ_d00221_A_definition_not_in_assertions`
- `test_REQ_d00221_B_extracts_term_and_definition`
- `test_REQ_d00221_B_collection_flag`
- `test_REQ_d00221_B_indexed_flag`
- `test_REQ_d00221_B_multiline_definition`

## Implementation
- `requirement.lark`: Added DEF_LINE.3 terminal, definition_block rule, added definition_block to _item, preamble_line, content_line, jny_body_line, jny_content_line (NOT assertion_item or changelog_block)
- `requirement.py` transformer: Added _extract_definition_block() and _transform_definition_block() methods. File-level definitions produce standalone ParsedContent(content_type="definition_block"). Requirement-level definitions stored in parsed_data["definitions"].
- `spec/prd-core.md`: Added REQ-d00221 with assertions A-B
