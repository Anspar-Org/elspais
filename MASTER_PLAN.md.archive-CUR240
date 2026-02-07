# MASTER PLAN — CUR-240 TOML Parser Fix + Remaining Work

**CURRENT_ASSERTIONS**: REQ-p00002-A

## Phase 1: Pattern Consolidation (DONE)

Consolidated 6 groups of duplicated regex patterns into shared constants/imports.

- [x] Group 1: BLANK_LINE_CLEANUP_RE to patterns.py
- [x] Group 2: `_try_parse_numeric()` to `config/__init__.py`
- [x] Group 3: IMPLEMENTS_PATTERN from RequirementParser in edit.py
- [x] Group 4: ALT_STATUS_PATTERN from RequirementParser in edit.py
- [x] Group 5: find_req_header() to patterns.py
- [x] Group 6: ASSERTION_LINE_PATTERN from RequirementParser in builder.py

Commit: `9a41fbf`

## Phase 2: Fix TOML Parser — Replace Custom Parser with tomlkit

**Bug**: `elspais config add` corrupts TOML files during round-trips:
1. Multi-line arrays collapsed to string `"["`
2. Arrays with comma-containing strings split incorrectly
3. Only the target field updated correctly; all other arrays destroyed

**Root cause**: Custom TOML parser in `config/__init__.py` processes line-by-line (can't handle multi-line arrays) and uses naive `inner.split(",")` (doesn't respect quoted strings).

**Fix**: Replace custom parser/serializer with `tomlkit` library.

### Implementation Steps

- [x] Add `tomlkit>=0.12` to `pyproject.toml` dependencies
- [x] Replace `_parse_toml()` in `config/__init__.py` with `tomlkit.parse().unwrap()`
- [x] Add `parse_toml_document()` for round-trip editing (returns TOMLDocument)
- [x] Remove dead code: `_parse_value()`, `_ensure_nested()`
- [x] Keep `_try_parse_numeric()` (used by `associates.py`)
- [x] Update `config_cmd.py`: add `_load_user_config_doc()` for write commands
- [x] Update `config_cmd.py`: replace `_write_config()` with `tomlkit.dumps()`
- [x] Update `config_cmd.py`: fix `isinstance(dict)` to `isinstance(MutableMapping)` in path helpers
- [x] Update `config_cmd.py`: use `tomlkit.table()` for new sections in `_set_by_path()`
- [x] Remove dead code: `serialize_toml()`, `_is_inline_table()`, `_serialize_value()`
- [x] Update version in `pyproject.toml`
- [x] Update CHANGELOG.md
- [x] Update CLAUDE.md (remove "zero dependencies" claims)
- [x] Update docs references (README.md, docs/overview.md, roadmap docs)
- [x] Write tests (sub-agent): multi-line arrays, comma-in-strings, inline comments, round-trip
- [x] Run full test suite — verify no regressions (954 passed)
- [ ] Commit

## Phase 3: Coverage Improvement (Ralph Loop)

Use ralph_loop to add `# Implements:` and `# Validates:` markers for Active requirements with low coverage.

**Target requirements** (0% coverage, Active status):
- REQ-p00001, REQ-p00003, REQ-p00005, REQ-p00006
- REQ-p00050, REQ-p00060
- REQ-o00050–o00064, REQ-d00050–d00068

**Partially covered** (improve):
- REQ-p00002 (33% — missing B, C)
- REQ-p00004 (50% — missing B)

## Phase 4: Push

Push branch when all phases complete.
