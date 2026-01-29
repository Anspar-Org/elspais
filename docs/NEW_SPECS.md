# Proposed New Specifications

> **Purpose**: Track requirements discovered through test/code analysis that don't have existing specs.
> **Workflow**: After analyzing a test file or source module, add proposed requirements here.
> Once reviewed and approved, move requirements to appropriate `spec/*.md` files.

---

## Coverage Analysis Summary

| Metric | Value | Notes |
|--------|-------|-------|
| Total Requirements | 48 | In spec/ directory |
| Total Assertions | 269 | SHALL statements |
| Total Tests | 89+ | In tests/ directory |
| Tests with REQ refs | 30+ | After TestParser regex fix |
| Assertion Coverage | ~10% | Target: 80%+ (improving) |

### Bug Fix Applied

**TestParser regex** wasn't capturing assertion suffixes (`_A` in `test_REQ_d00060_A_...`).

Fixed regex pattern to capture:

- `REQ_d00060` → REQ-d00060 (requirement level)
- `REQ_d00060_A` → REQ-d00060-A (assertion level)
- `REQ_d00060_A_B` → REQ-d00060-A-B (multi-assertion)

---

## Analysis Progress

### Test Files Analyzed

| File | Status | Tests | Matched | Proposed |
|------|--------|-------|---------|----------|
| `tests/conftest.py` | ⏳ Pending | - | - | - |
| `tests/test_doc_sync.py` | ⏳ Pending | - | - | - |
| `tests/test_edit.py` | ⏳ Pending | - | - | - |
| `tests/test_example_cmd.py` | ⏳ Pending | - | - | - |
| `tests/test_health.py` | ⏳ Pending | - | - | - |
| `tests/test_init.py` | ⏳ Pending | - | - | - |
| `tests/test_trace_command.py` | ⏳ Pending | - | - | - |
| `tests/core/*` | ⏳ Pending | - | - | - |
| `tests/graph/*` | ⏳ Pending | - | - | - |
| `tests/mcp/*` | ⏳ Pending | - | - | - |

### Source Modules Analyzed

| Module | Status | Requirement |
|--------|--------|-------------|
| `src/elspais/cli.py` | ⏳ Pending | - |
| `src/elspais/graph/*` | ⏳ Pending | - |
| `src/elspais/mcp/*` | ⏳ Pending | - |
| `src/elspais/config/*` | ⏳ Pending | - |
| `src/elspais/validation/*` | ⏳ Pending | - |
| `src/elspais/utilities/*` | ⏳ Pending | - |
| `src/elspais/html/*` | ⏳ Pending | - |
| `src/elspais/commands/*` | ⏳ Pending | - |

---

## Proposed Requirements

### Category: [Pending Analysis]

*Requirements will be added here as test/code analysis proceeds.*

<!-- Template for new requirements:

### REQ-dXXXXX: [Title]

**Source**: Discovered analyzing `[file]`
**Implements**: [parent requirement or "New PRD needed"]

**Assertions:**
- **A**: The system SHALL [behavior 1]
- **B**: The system SHALL [behavior 2]

-->

---

## Test Rename Proposals

*Tests that can be renamed to reference existing assertions.*

<!-- Template:
| Current Name | Proposed Name | Assertion |
|--------------|---------------|-----------|
| `test_foo_validates_input` | `test_REQ_p00001_A_validates_input` | REQ-p00001-A |
-->

| Current Name | Proposed Name | Assertion |
|--------------|---------------|-----------|
| *Pending analysis* | - | - |
