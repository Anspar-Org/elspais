# Multi-Assertion Reference Expansion

## Purpose

This document specifies the multi-assertion reference expansion feature, which allows compact notation for referencing multiple assertions of the same requirement. A dedicated separator character joins assertion labels to avoid ambiguity with configurable ID patterns.

---

## REQ-d00081: Multi-Assertion Reference Expansion

**Level**: DEV | **Status**: Active | **Implements**: REQ-p00001

Multi-assertion references allow compact notation for referencing multiple assertions of the same requirement. A dedicated separator character (distinct from ID separators) joins assertion labels after the first: `REQ-p00001-A+B+C` expands to individual assertion references `REQ-p00001-A`, `REQ-p00001-B`, `REQ-p00001-C`.

## Assertions

A. The `multi_assertion_separator` key SHALL be available in `[references.defaults]` configuration.

B. The default value of `multi_assertion_separator` SHALL be `"+"`.

C. Config validation SHALL reject configurations where the multi-assertion separator character appears in the `separators` list.

D. Expansion SHALL occur in the graph builder's link resolution, applying uniformly to all parser types (requirement, code, test, result).

E. The expansion pattern SHALL derive from the configured assertion label pattern and multi-assertion separator.

F. When `multi_assertion_separator` is empty or `false`, expansion SHALL be disabled.

G. A reference containing no multi-assertion separator character SHALL pass through unchanged.

## Rationale

The previous implementation hardcoded expansion in RequirementParser only, using a regex that assumed uppercase letter labels and hyphen separators. This created silent failures when code comments (`# Implements: REQ-x-A-B-C`) and test names (`test_REQ_x_A_B_C`) were not expanded. A dedicated separator character eliminates ambiguity regardless of the configured assertion label style (uppercase, numeric, alphanumeric).

*End* *Multi-Assertion Reference Expansion* | **Hash**: 2474ef93
