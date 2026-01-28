# OLD_PLAN.md - Completed Enhancement Issues

This file contains completed enhancement issues moved from MASTER_PLAN.md.

---

## Completed Bugs

### [x] trace --report: All report types (minimal, standard, full) produce the same output
  - **Issue**: The `--report` CLI argument was defined but never used in the trace command implementation
  - **Fix**: Implemented `ReportPreset` dataclass with three presets:
    - `minimal`: ID, title, status only
    - `standard`: ID, title, level, status, implements (default)
    - `full`: All fields including body, assertions, hash, code/test refs
  - **Completed**: 2026-01-27
  - **Commit**: [CUR-514] fix(trace): Implement --report presets (minimal/standard/full)
