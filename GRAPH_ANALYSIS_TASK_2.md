# Task 2: Create CLI command `elspais analysis`

## Description

Create `src/elspais/commands/analysis_cmd.py` and register the `analysis` subcommand in `cli.py`.

## Spec

`docs/superpowers/specs/2026-03-09-graph-analysis-design.md`

## APPLICABLE_ASSERTIONS

- REQ-d00125-A: --top N option (default 10)
- REQ-d00125-B: --weights W1,W2,W3 option
- REQ-d00125-C: --format table|json option (default table)
- REQ-d00125-D: --show foundations|leaves|all option (default all)
- REQ-d00125-E: --level prd|ops|dev filter
- REQ-d00125-F: --include-code flag
- REQ-d00125-G: Table output with Rank, ID, Title, Centrality, Fan-In, Uncovered, Score columns
- REQ-d00125-H: JSON output serializes FoundationReport

## Tests

- 20 e2e tests in `tests/e2e/test_analysis_cmd.py`
- All 8 assertions covered across 3 test classes

## Implementation

- `src/elspais/commands/analysis_cmd.py`: run(), _render_table(), _render_json()
- Registered in `cli.py` with full argparse setup
- Added to `commands/__init__.py`

## Verification

- 20/20 e2e tests pass
- Full unit suite: 2338 passed, 94 deselected
