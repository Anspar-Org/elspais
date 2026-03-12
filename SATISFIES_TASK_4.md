# Task 4: File-Based Attribution Algorithm for Link Resolution

**Status**: Complete
**Branch**: claude/cross-cutting-requirements-2Zd0c
**Ticket**: CUR-1082

## Description

During link resolution (Phase 3), detect `Implements:` refs targeting TEMPLATE nodes.
For each template ref, find the template root (walk up REFINES).
Find sibling `Implements:` refs in the same source file targeting CONCRETE nodes.
For each concrete target, walk up ancestors to find SATISFIES declaration matching template root.
First match wins — construct instance ID (`declaring_id::target_id`), redirect edge.
Warn if no attribution path found.
Support multiple templates (`Satisfies: REQ-FDA, REQ-GDPR`).

## APPLICABLE_ASSERTIONS

- **REQ-p00014-D**: The system SHALL attribute `Implements:` references to template assertions to the correct instance by finding a sibling `Implements:` reference to a CONCRETE node in the same source file, walking that node's ancestors to the first node with a `Satisfies:` declaration matching the template, and constructing the instance ID from the declaring node's ID and the referenced node's ID.

## Baseline

- 2376 passed, 94 deselected (all green)

## Tests Added

- `TestFileBasedAttribution.test_REQ_p00014_D_template_ref_redirected_to_instance`
- `TestFileBasedAttribution.test_REQ_p00014_D_no_attribution_without_concrete_sibling`
- `TestFileBasedAttribution.test_REQ_p00014_D_multiple_templates_attributed_independently`

## Implementation Summary

- Added `_attribute_template_refs()` method to GraphBuilder
- Walks concrete target + ancestors to find SATISFIES declaration matching template root
- Redirects link to instance clone ID (`declaring_id::target_id`)
- Unattributed template refs recorded as broken references

## Verification

- 2379 passed, 94 deselected (all green, +3 new tests)
