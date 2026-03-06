# Reference Configuration

## REQ-d00082: Unified Reference Configuration

**Level**: DEV | **Status**: Active | **Implements**: REQ-p00001-A

The system SHALL provide a unified, configurable reference pattern system used by all parsers (CodeParser, TestParser, JUnitXMLParser, PytestJSONParser) to locate requirement references in source files.

## Assertions

D. The reference configuration SHALL support case-sensitive and case-insensitive ID matching.

E. The reference configuration SHALL support configurable ID separators including underscore and hyphen.

F. The reference configuration SHALL support file-type specific overrides via glob patterns (e.g., `*.py`, `tests/legacy/**`).

G. The reference configuration SHALL extract ID components (prefix, type, number) from matched references.

H. The reference configuration SHALL support configurable comment styles (e.g., `#`, `//`, `--`) for code reference detection.

I. CodeParser SHALL accept PatternConfig and ReferenceResolver for configurable reference matching in source files.

J. TestParser SHALL accept PatternConfig and ReferenceResolver for configurable reference matching in test files.

K. JUnitXMLParser SHALL accept PatternConfig and ReferenceResolver for configurable reference matching in JUnit XML reports.

L. PytestJSONParser SHALL accept PatternConfig and ReferenceResolver for configurable reference matching in pytest JSON reports.

## Rationale

Different projects use different ID conventions, comment styles, and directory structures. A unified reference configuration allows all parsers to share the same configurable pattern matching, avoiding duplicated logic and ensuring consistent behavior across parser types.

*End* *Unified Reference Configuration* | **Hash**: 89956cd7
