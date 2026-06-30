# elspais trace

Generate a traceability matrix from the requirements graph.

## Synopsis

```text
elspais trace [--format FORMAT] [--preset PRESET] [--dimension DIMENSION]
              [--body] [--assertions] [--tests] [-o OUTPUT]
```

## Description

The `trace` command emits a traceability matrix for every requirement in the
graph. Output formats include Markdown tables, CSV, HTML, and JSON.

## Options

`--format FORMAT`
: Output format. One of `markdown` (default), `text`, `csv`, `html`, `json`.

`--preset PRESET`
: Column preset. One of `minimal`, `standard` (default), `full`.
`minimal` shows ID, Title, Level, Status.
`standard` and `full` add Implemented, Tested, Verified, UAT Coverage, UAT Verified, Code Tested, LCOV Tested.

`--dimension DIMENSION`
: Restrict the report to a dimension group. Currently supported value: `uat`.

`--body`
: Include requirement body text in detail rows (Markdown and HTML only).

`--assertions`
: Split coverage columns into assertion-label ranges + percentages.

`--tests`
: Include test reference rows grouped by assertion label.

`-o OUTPUT`, `--output OUTPUT`
: Write output to a file instead of stdout.

## UAT Dimension

```text
elspais trace --dimension uat [--format FORMAT]
```

Emits a focused UAT traceability report. Only requirements that have at least
one **incoming `Validates:`** reference (i.e. are validated by at least one
user journey) appear in the output.

### Columns in UAT mode

| Column | Description |
|---|---|
| ID | Requirement ID |
| Title | Requirement title |
| Level | Hierarchy level |
| Status | Requirement status |
| UAT Coverage | Fraction of assertions covered by validating journeys |
| UAT Verified | Fraction of assertions verified (fully-passed journeys only) |
| Journeys | Semicolon-separated list of `JNY-id:verdict` pairs |

Code-dimension columns (`Implemented`, `Tested`, `Verified`, `Code Tested`,
`LCOV Tested`) are excluded from the UAT view.

### Journey verdicts

Each validating journey is reported with one of four verdicts:

| Verdict | Meaning |
|---|---|
| `pass` | All journey steps have at least one passing verifying test and no failures |
| `fail` | At least one verifying test returned a failure result |
| `partial` | Some steps pass but not all |
| `unverified` | No verifying tests are recorded for this journey |

### Example output (Markdown)

```text
# Traceability Matrix

| ID | Title | Level | Status | UAT Coverage | UAT Verified | Journeys |
|----|----|----|----|----|----|----|
| REQ-d00001 | Login Requirement | dev | Active | 1/1 (100%) | 1/1 (100%) | JNY-OQ-Login-01:pass |
```

### Example output (JSON)

```json
[
  {
    "id": "REQ-d00001",
    "title": "Login Requirement",
    "level": "dev",
    "status": "Active",
    "uat_coverage": "1/1 (100%)",
    "uat_verified": "1/1 (100%)",
    "journeys": [
      {"id": "JNY-OQ-Login-01", "verdict": "pass"}
    ]
  }
]
```

## Examples

```text
# Default markdown matrix
elspais trace

# JSON format with full preset
elspais trace --format json --preset full

# UAT-scoped report in markdown
elspais trace --dimension uat

# UAT-scoped report as JSON
elspais trace --dimension uat --format json

# UAT report saved to file
elspais trace --dimension uat -o uat_matrix.md
```
