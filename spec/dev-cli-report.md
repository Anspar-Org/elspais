# CLI Report Composition

## REQ-d00085: Unified Report Composition

**Level**: DEV | **Status**: Active | **Implements**: REQ-p00003, REQ-p00002

The CLI SHALL support composable report output by accepting multiple section names as positional arguments. Sections are rendered in the order specified and concatenated into a single output stream.

## Assertions

A. The CLI SHALL accept multiple section names (`health`, `coverage`, `trace`, `changed`) as positional arguments, rendering each in order and concatenating the output.

B. Shared flags (`--format`, `-o`, `-q`/`--quiet`, `-v`/`--verbose`, `--lenient`, `--mode`) SHALL apply globally across all sections in a composed report.

C. The exit code of a composed report SHALL be the worst-of-all-sections: non-zero if any section reports errors, or warnings without `--lenient`.

D. When a single section is specified, it SHALL behave identically to a standalone command invocation.

E. The `--format` flag SHALL support `text`, `markdown`, `json`, and `csv` output modes. Not all formats are valid for all sections; invalid combinations SHALL produce a clear error.

F. The `-q`/`--quiet` flag SHALL suppress all output except a single summary line per section. The `-v`/`--verbose` flag SHALL expand all available detail.

G. The `--lenient` flag SHALL allow warnings to pass without affecting the exit code. Without `--lenient`, any warning-level finding SHALL cause a non-zero exit code.

H. The `--format junit` option SHALL render health checks as JUnit XML, mapping categories to `<testsuite>` elements, checks to `<testcase>` elements, failures to `<failure>` elements, warnings to `<system-err>`, and info to `<system-out>`.

I. Each `HealthCheck` SHALL carry a `findings` list of `HealthFinding` dataclass instances, each with `message`, `file_path`, `line`, `node_id`, and `related` fields. The `to_dict()` serialization SHALL include findings. Existing renderers (text, markdown, JUnit) SHALL remain unchanged.

J. The `--format sarif` option SHALL render health findings as SARIF v2.1.0 JSON, with one `reportingDescriptor` per unique check name, one `result` per `HealthFinding` with physical locations, passing checks omitted, and coverage stats in `run.properties`.

## Rationale

Report-producing commands (`health`, `trace`, `coverage`, `changed`) currently exist as independent subcommands with inconsistent format support. Composing a combined report (e.g. health + coverage for a CI PR comment) requires multiple invocations and manual concatenation. A composable system builds the graph once, renders each section, and produces unified output. The `--lenient` flag provides an escape hatch for workflows that want to observe warnings without gating on them.

*End* *Unified Report Composition* | **Hash**: 82d76f1a
