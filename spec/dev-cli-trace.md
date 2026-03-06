# CLI Trace Command

## REQ-d00084: Trace Command

**Level**: DEV | **Status**: Active | **Implements**: REQ-p00003

The `trace` command SHALL generate traceability output from the requirement graph, supporting multiple output formats.

## Assertions

A. The command SHALL support structured JSON graph output via `--graph-json`, including git change annotations when available.

## Rationale

A JSON graph output mode enables programmatic consumption of the full traceability graph with git-aware change tracking, supporting dashboard integrations and automated analysis pipelines.

*End* *Trace Command* | **Hash**: 02377a59
