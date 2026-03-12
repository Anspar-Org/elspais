# Task 3: Template Instantiation in the Builder

**Status**: Complete
**Branch**: claude/cross-cutting-requirements-2Zd0c
**Ticket**: CUR-1082

## Description

- Separate SATISFIES refs from `_pending_links` into own list
- Add `_instantiate_satisfies_templates()` to builder
- Sub-pass 1: mark template REQs and assertions as `stereotype=TEMPLATE`
- Sub-pass 2: clone template subtree with composite IDs (`declaring_id::original_id`)
  - Clone all descendant REQs (following REFINES edges) and their assertion children
  - Cloned nodes get `stereotype=INSTANCE`
  - Create INSTANCE edge from each clone to its original
  - Create SATISFIES edge from declaring REQ to cloned root
  - Preserve internal edges (REFINES, etc.) exactly as in original
  - Preserve source locations from originals
- Call new phase in `build()` between content parsing and link resolution

## APPLICABLE_ASSERTIONS

- **REQ-p00014-B**: When a requirement declares `Satisfies: X`, the graph builder SHALL clone the template's REQ subtree (all descendant REQs and their assertions) with composite IDs of the form `declaring_id::original_id`. The cloned root SHALL be linked to the declaring requirement via a SATISFIES edge. Internal edges and assertions SHALL be preserved exactly as in the original. Coverage of cloned nodes SHALL use the standard coverage mechanism.
- **REQ-p00014-C**: Each instance node SHALL have an INSTANCE edge to its template original.
- **REQ-d00069-H**: The graph builder SHALL clone the template's REQ subtree with composite IDs, creating INSTANCE nodes.
- **REQ-d00069-I**: 100% coverage of a template instance SHALL be achieved when every leaf assertion in the cloned template subtree has at least one Implements reference.

## Baseline

- 2368 passed, 94 deselected (all green)

## Tests Added

- `TestTemplateInstantiation.test_REQ_p00014_B_satisfies_clones_template_root`
- `TestTemplateInstantiation.test_REQ_p00014_B_satisfies_edge_from_declaring_to_clone`
- `TestTemplateInstantiation.test_REQ_p00014_C_instance_edge_from_clone_to_original`
- `TestTemplateInstantiation.test_REQ_p00014_B_cloned_assertions_exist`
- `TestTemplateInstantiation.test_REQ_p00014_B_template_marked_as_template`
- `TestTemplateInstantiation.test_REQ_p00014_B_cloned_subtree_preserves_refines`
- `TestTemplateInstantiation.test_REQ_p00014_B_multiple_satisfies_creates_separate_clones`
- `TestTemplateInstantiation.test_REQ_d00069_H_cloned_source_location_preserved`

## Implementation Summary

- SATISFIES refs separated from `_pending_links` into `_satisfies_links`
- Added `_instantiate_satisfies_templates()` with two sub-passes: mark templates, clone subtrees
- Pre-resolves REFINES edges within template subtrees before cloning
- Cloned nodes get composite IDs, INSTANCE stereotype, INSTANCE edges to originals
- SATISFIES edge from declaring REQ to cloned root
- Updated health check to find declaring reqs via INSTANCE edges
- Updated old SATISFIES edge tests to match new declaring→clone direction

## Verification

- 2376 passed, 94 deselected (all green, +8 new tests)
