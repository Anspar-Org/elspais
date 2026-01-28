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

### [x] trace --view: Version shows "v1" instead of actual elspais version
  - **Issue**: `HTMLGenerator.__init__` had `version: int | str = 1` hardcoded default
  - **Fix**: Import `__version__` from elspais and use as default
  - **Completed**: 2026-01-27
  - **Commit**: [CUR-514] fix(html): Display actual package version in trace --view
