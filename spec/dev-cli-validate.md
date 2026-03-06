# CLI Validate Command

## REQ-d00083: Validate Command

**Level**: DEV | **Status**: Active | **Implements**: REQ-p00002

The `validate` command SHALL check spec files for format compliance, hierarchy integrity, and content hash freshness, reporting results to stdout.

## Assertions

A. The command SHALL support structured JSON output of validation results via `--json`.

B. The command SHALL support structured JSON export of parsed requirement data via `--export`.

## Rationale

Machine-readable output modes enable CI/CD integration and programmatic consumption of validation results. The `--json` flag reports validation diagnostics, while `--export` serializes the parsed requirement model for downstream tooling.

*End* *Validate Command* | **Hash**: eddb3a52
