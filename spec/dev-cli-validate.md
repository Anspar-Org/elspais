# CLI Validate Command

## REQ-d00083: Validate Command

**Level**: DEV | **Status**: Deprecated | **Implements**: REQ-p00002

The `validate` command is superseded by the `health` command, which provides a superset of validation checks (format, hierarchy, hashes, code refs, test refs) with composable report output (REQ-d00085).

## Assertions

A. The command SHALL support structured JSON output of validation results via `--json`.

B. The command SHALL support structured JSON export of parsed requirement data via `--export`.

## Rationale

The `validate` command's spec-checking functionality is fully covered by the `health` command's spec category. The `--export` functionality is preserved as `health --export`. Maintaining a separate command creates confusion about which diagnostic to use and duplicates exit-code semantics (REQ-d00080).

*End* *Validate Command* | **Hash**: eddb3a52
