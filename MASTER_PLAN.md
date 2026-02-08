# MASTER PLAN 9 — Consolidate Spec File I/O

**Branch**: feature/CUR-514-viewtrace-port
**Ticket**: CUR-240
**CURRENT_ASSERTIONS**: REQ-o00063 (A-B, D)

## Context

An architecture review found `move_requirement()` duplicated across `edit.py` (CLI) and `server.py` (MCP) with divergent behavior, 4 spec-file writes in `edit.py` missing `encoding="utf-8"`, and the shared utility `mcp/file_mutations.py` mislocated under `mcp/` despite being CLI-consumed. Fixes to one move/status path don't propagate to the other.

## Problem Summary

| Issue | Severity | Files |
|-------|----------|-------|
| Missing `encoding="utf-8"` on spec writes | **Bug** | `edit.py` (4 writes) |
| Duplicate `move_requirement()` (~90 lines each) | Maintenance | `edit.py`, `server.py` |
| `file_mutations.py` under `mcp/` but used by CLI | Misplacement | `mcp/file_mutations.py` |
| `add_status_to_file()` never called; `edit.py` reimplements | Dead code | `mcp/file_mutations.py` |

## Implementation Steps

### Step 1: Relocate and extend `spec_writer.py`

**Move**: `src/elspais/mcp/file_mutations.py` -> `src/elspais/utilities/spec_writer.py`

Keep existing functions:
- `update_hash_in_file(file_path, req_id, new_hash)` — unchanged
- `add_status_to_file(file_path, req_id, status)` — unchanged

Add consolidated functions from `edit.py` and `server.py`:
- [x] `move_requirement(source_file, dest_file, req_id, dry_run=False)` — merge two implementations
- [x] `modify_implements(file_path, req_id, new_implements, dry_run=False)` — from `edit.py`
- [x] `modify_status(file_path, req_id, new_status, dry_run=False)` — from `edit.py`
- [x] `change_reference_type(file_path, target_id, new_type)` — from `server.py`

All functions use `encoding="utf-8"` consistently.

### Step 2: Update callers

- [x] **`edit.py`**: Remove inline `modify_implements()`, `modify_status()`, `move_requirement()`; import from `utilities.spec_writer`
- [x] **`server.py`**: Delegate `_move_requirement()` and `_change_reference_type()` to `spec_writer` (keep safety-branch wrappers)
- [x] **`hash_cmd.py`**: Update import from `elspais.mcp.file_mutations` to `elspais.utilities.spec_writer`
- [x] **`mcp/file_mutations.py`**: Replace with re-export shim or delete

### Step 3: Update `# Implements:` headers

- [x] Update `REQ-o00063-*` references on affected files

### Step 4: Tests

- [x] Existing tests for `edit.py`, `hash_cmd.py`, MCP pass
- [x] Add focused test for `utilities/spec_writer.py` covering consolidated `move_requirement()`
- [x] Full test suite passes (1306 passed)

## Files to Modify

| File | Action |
|------|--------|
| `src/elspais/utilities/spec_writer.py` | **Create** (from `mcp/file_mutations.py` + extracted functions) |
| `src/elspais/mcp/file_mutations.py` | Replace with re-export shim or delete |
| `src/elspais/commands/edit.py` | Remove 3 functions, import from `spec_writer` |
| `src/elspais/mcp/server.py` | Delegate `_move_requirement` + `_change_reference_type` |
| `src/elspais/commands/hash_cmd.py` | Update import path |
| `tests/core/test_spec_writer.py` | **Create** (consolidation tests) |

## Design Decisions

1. **`utilities/` not `mcp/`**: Module serves both CLI and MCP — belongs in shared utilities
2. **Keep functions stateless**: Each takes `file_path`, operates independently — no class needed
3. **Preserve return-value contracts**: `edit.py` returns `Dict[str, Any]`; `file_mutations.py` returns `str | None` — consolidated module preserves both
4. **Safety branches stay in MCP layer**: MCP-specific orchestration, not file I/O

## Verification

1. `pytest tests/commands/test_edit.py` — edit command tests pass
2. `pytest tests/mcp/` — MCP tests pass
3. `pytest tests/` — full suite passes (1277+)
4. `elspais edit --req-id REQ-p00001 --status Draft --dry-run` — still works
5. `elspais hash update --dry-run` — still works
6. Grep for `encoding=` in all `spec_writer.py` writes — all explicit UTF-8

## Archive

- [ ] Mark phase complete in MASTER_PLAN.md
- [ ] Archive completed plan: `mv MASTER_PLAN.md ~/archive/YYYY-MM-DD/MASTER_PLAN_spec_writer.md`
- [ ] Promote next plan: `mv MASTER_PLAN[lowest].md MASTER_PLAN.md`
- **CLEAR**: Reset checkboxes for next phase
