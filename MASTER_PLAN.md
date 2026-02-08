# MASTER PLAN 10 — Fix Encoding on Non-Spec File Writers

**Branch**: feature/CUR-514-viewtrace-port
**Ticket**: CUR-240
**CURRENT_ASSERTIONS**: REQ-d00052-G

## Context

An architecture review found 8 file-write operations outside of spec file mutations that are missing explicit `encoding="utf-8"`. These are lower risk than the spec-file writers (addressed in MASTER_PLAN 9) because they write output reports, generated files, and one-time config — not the canonical spec data. However, they should be fixed for correctness on non-UTF-8 default systems.

## Problem Summary

| File | Missing Writes | What It Writes |
|------|---------------|----------------|
| `src/elspais/commands/trace.py` | 5 instances | HTML view, JSON export, CSV/MD reports |
| `src/elspais/commands/index.py` | 1 instance | Generated `INDEX.md` |
| `src/elspais/commands/init.py` | 2 instances | `.elspais.toml`, example requirement template |

## Implementation Steps

### Step 1: Fix `trace.py` encoding

- [x] `output_path.write_text(content)` → add `encoding="utf-8"` (HTML view)
- [x] `Path(args.output).write_text(output)` → add `encoding="utf-8"` (JSON export)
- [x] `open(path, 'w')` → `open(path, 'w', encoding='utf-8')` (CSV/MD "both" format, 2 instances)
- [x] `open(path, 'w')` → `open(path, 'w', encoding='utf-8')` (single format output)

### Step 2: Fix `index.py` encoding

- [x] `spec_dirs[0] / "INDEX.md"` write → add `encoding="utf-8"`

### Step 3: Fix `init.py` encoding

- [x] `.elspais.toml` write → add `encoding="utf-8"`
- [x] Example requirement template write → add `encoding="utf-8"`

### Step 4: Tests

- [x] Existing tests pass (no behavior change)
- [x] Full test suite passes (1306 passed)

## Verification

1. `pytest tests/` — full suite passes (1306 passed)
2. Grep for `\.write_text\(` and `open(.*'w'` across `src/` — all have explicit `encoding="utf-8"`

## Archive

- [x] Mark phase complete in MASTER_PLAN.md
- [ ] Archive completed plan: `mv MASTER_PLAN.md ~/archive/YYYY-MM-DD/MASTER_PLAN_encoding_fix.md`
- [ ] Promote next plan: `mv MASTER_PLAN[lowest].md MASTER_PLAN.md`
- **CLEAR**: Reset checkboxes for next phase
