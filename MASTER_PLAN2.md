# MASTER PLAN 2 — Pattern Consolidation (Future)

> **Status**: NOT STARTED — Items identified during hash pattern fix work.

**CURRENT_ASSERTIONS**: REQ-p00002-A, REQ-p00004-A

> All code and tests in this plan MUST reference assertions from CURRENT_ASSERTIONS.
> - Source files: `# Implements: REQ-xxx-Y`
> - Test names: `test_REQ_xxx_Y_description`
> - Test class docstrings: `Validates REQ-xxx-Y: ...`

## Out-of-Scope Pattern Duplications

These inline regex patterns are duplicated across multiple files. Each should be consolidated into a shared function or constant.

### 1. Blank Line Cleanup `r"\n{3,}"`

| File | Line | Context |
|------|------|---------|
| `src/elspais/commands/edit.py` | 383 | Post-edit cleanup |
| `src/elspais/mcp/server.py` | 1312 | MCP block extraction |

### 2. Integer/Float Detection

| File | Lines | Context |
|------|-------|---------|
| `src/elspais/config/__init__.py` | 338, 342 | YAML-like value parsing |
| `src/elspais/associates.py` | 162, 166 | Same parsing, duplicated |

### 3. Implements Field Pattern

| File | Line | Context |
|------|------|---------|
| `src/elspais/graph/parsers/requirement.py` | 39 | Class-level `IMPLEMENTS_PATTERN` |
| `src/elspais/commands/edit.py` | 228 | Inline compiled |

### 4. Status Field Pattern

| File | Line | Context |
|------|------|---------|
| `src/elspais/graph/parsers/requirement.py` | 38 | Class-level `ALT_STATUS_PATTERN` |
| `src/elspais/commands/edit.py` | 305 | Inline compiled |

### 5. Requirement Header by ID (6 inline copies)

| File | Line | Context |
|------|------|---------|
| `src/elspais/commands/edit.py` | 180 | Find header for edit |
| `src/elspais/commands/edit.py` | 218 | Block start for implements |
| `src/elspais/commands/edit.py` | 295 | Block start for status |
| `src/elspais/commands/edit.py` | 422 | All requirement headers |
| `src/elspais/mcp/server.py` | 1298 | Full block extraction |

**Note**: `file_mutations.py` also had this but is being fixed in current work.

### 6. Assertion Line Pattern (slight variation)

| File | Line | Pattern | Difference |
|------|------|---------|------------|
| `src/elspais/graph/parsers/requirement.py` | 46 | `^\s*([A-Z0-9]+)\.\s+(.+)$` | Leading whitespace, `.+` |
| `src/elspais/graph/builder.py` | 806 | `^([A-Z0-9]+)\.\s+(.*)$` | No leading ws, `.*` |

## Approach

Each group should be consolidated into either:
- A **constant** (for simple patterns like blank line cleanup)
- A **function** (for parameterized patterns like `_find_req_header(content, req_id)`)
- An **import from the canonical location** (e.g., reuse `RequirementParser.IMPLEMENTS_PATTERN`)
