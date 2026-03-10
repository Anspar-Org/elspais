# CLI Coverage Report

## REQ-d00086: Coverage Report Section

**Level**: DEV | **Status**: Active | **Implements**: REQ-p00003

The `coverage` section SHALL produce a coverage report showing implementation, validation, and test-passing status at the requirement and assertion level.

## Assertions

A. The report SHALL group requirements by level (PRD, OPS, DEV) and show counts and percentages of requirements with code references, test references, and passing tests.

B. The report SHALL compute per-requirement assertion coverage: implemented (assertions with `Implements:` code refs, direct or transitive), validated (assertions with test refs), and passing (validated assertions whose tests pass).

C. The report SHALL support `text`, `markdown`, `json`, and `csv` output formats.

D. The report SHALL use existing graph aggregate functions and annotator data rather than reimplementing coverage logic.

## Rationale

Coverage data is already computed during graph construction but is only surfaced through the interactive viewer or the underpowered `analyze coverage` text output. A dedicated coverage section with multi-format support enables CI badge generation, PR comment summaries, and developer-facing markdown reports.

*End* *Coverage Report Section* | **Hash**: 12e1ecaf
