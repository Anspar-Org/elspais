# Plan: Assertion-level references in all contexts

**Issue**: Priority 2 from MASTER_PLAN.md
**Status**: COMPLETE

## Comprehensive Audit Results

### Initial Gaps (5 Found):

- [x] **Gap 1: Code Parser** - FALSE POSITIVE
  - Pattern `REQ-[\w-]+` already matches `REQ-d00001-A`
  - Added 2 tests: `test_parse_assertion_level_reference`, `test_parse_multiple_assertion_refs`

- [x] **Gap 2: Hierarchy Rules** - INTENTIONAL DESIGN
  - Rules apply at requirement level, not assertion level

- [x] **Gap 3: Hierarchy Utilities** - INTENTIONAL DESIGN
  - Cycle detection operates at requirement level

- [x] **Gap 4: Coverage Analysis** - INTENTIONAL DESIGN
  - Coverage rolls up from assertions to requirements

- [x] **Gap 5: Pattern Extraction** - DEAD CODE
  - `extract_implements_ids()` is never used

### Additional Gap Found (Comprehensive Audit):

- [x] **Gap 6: Trace View Scanning** - FIXED
  - `trace_view/scanning.py` pattern didn't match assertion suffixes
  - Fixed: Updated pattern to `REQ-(?:([A-Z]+)-)?([pod]\d{5})(?:-[A-Z])?`
  - Assertion-level refs now matched and linked to parent requirement
  - Added 4 tests: `TestScanningPatterns` class

## All Contexts Verified

| Context | Handles Assertions | Tests |
|---------|-------------------|-------|
| patterns.PatternValidator | ✅ YES | ✅ YES |
| parser.RequirementParser | ✅ YES | ✅ YES |
| testing.scanner | ✅ YES | ✅ YES |
| parsers.test | ✅ YES | ✅ YES |
| parsers.code | ✅ YES | ✅ YES |
| parsers.junit_xml | ✅ YES | ✅ YES |
| parsers.pytest_json | ✅ YES | ✅ YES |
| trace_view.scanning | ✅ YES (FIXED) | ✅ YES |
| graph_builder | ✅ YES | ✅ YES |
| rules | ✅ YES | ✅ YES |

## Verification

- All 719 tests pass
- 6 new tests added for assertion-level refs
