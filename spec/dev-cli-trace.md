# CLI Trace Command

## REQ-d00084: Trace Command

**Level**: DEV | **Status**: Active | **Implements**: REQ-p00003

The `trace` command SHALL generate traceability output from the requirement graph, supporting multiple output formats with configurable column presets and detail levels.

## Assertions

A. The command SHALL support structured JSON graph output via `--graph-json`, including git change annotations when available.

B. The command SHALL support column presets (`--preset minimal|standard|full`) controlling which columns appear in tabular output: minimal (ID, Title, Level, Status), standard (+ Implemented, Validated), full (+ Passing).

C. The command SHALL support independent detail flags (`--body`, `--assertions`, `--tests`) that control whether expanded rows appear beneath each requirement, orthogonal to column presets.

D. Coverage columns SHALL show per-requirement assertion-level coverage: Implemented (assertions with code refs, direct or transitive), Validated (assertions with test refs), Passing (validated assertions whose tests pass), each displayed as N/M (%).

## Rationale

A JSON graph output mode enables programmatic consumption of the full traceability graph with git-aware change tracking, supporting dashboard integrations and automated analysis pipelines. Column presets and detail flags are independent axes of control: a user may want a compact table with full coverage columns, or a minimal table with expanded assertion rows.

*End* *Trace Command* | **Hash**: f8d407a5
