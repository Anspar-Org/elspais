# Unified Report System Design

Date: 2026-03-06

## Problem

The CLI has multiple report-producing commands with overlapping concerns, inconsistent output format support, and missing capabilities:

- `analyze` has 3 subcommands (hierarchy, orphans, coverage) — all text-only, none used in CI
- `validate` overlaps heavily with `health` (both check specs/hierarchy)
- `health` is the most capable check command but lacks markdown output
- `trace` bundles traceability matrix, interactive viewer, Flask server, and graph-json export into one command
- No way to get a simple markdown coverage report
- No way to compose multiple report sections into a single output

## Design

### Multi-Command Composition

Commands that produce report sections can be composed by listing them together. The output is concatenated in the order listed.

```text
elspais health coverage trace --format markdown -o report.md
elspais health --format json
elspais coverage --format markdown
elspais health coverage --format text
```

When a single section is listed, it behaves as a standalone command. When multiple are listed, shared flags (`--format`, `-o`, `-q`, `-v`, `--lenient`) apply globally.

### Report Sections

| Section    | Replaces              | Content                                              |
|------------|-----------------------|------------------------------------------------------|
| `health`   | `health` + `validate` | Pass/fail checks by category (config, spec, code, tests) |
| `coverage` | `analyze coverage`    | Assertion coverage by level (implemented, validated, passing) |
| `trace`    | `trace`               | Traceability matrix with configurable columns        |
| `changed`  | `changed`             | Git-based change summary                             |

### Commands Removed

| Command             | Replacement                          |
|---------------------|--------------------------------------|
| `validate`          | `health -q`                          |
| `analyze coverage`  | `coverage`                           |
| `analyze orphans`   | `health` (already checked under spec.orphans) |
| `analyze hierarchy` | `trace --preset minimal`             |
| `analyze` (entire)  | Deleted                              |

### Commands Kept (Unchanged)

| Command  | Reason                                          |
|----------|-------------------------------------------------|
| `doctor` | Environment/installation diagnostic, not a project report |
| `pdf`    | Document compiler (Pandoc/LaTeX), separate concern |

### Commands Kept (Renamed/Reorganized)

| Current                    | New                        | Notes                    |
|----------------------------|----------------------------|--------------------------|
| `trace --edit-mode`        | `viewer` (or `serve`)      | Interactive Flask viewer |
| `trace --view`             | Stays as a trace flag      | Static HTML generation   |
| `trace --graph-json`       | Stays as a trace flag      | Graph export for tooling |

The interactive viewer and static HTML with `--embed-content` are critical and must not break. Only the CLI entry point name may change.

### Shared Flags

These flags apply to all report sections and to composed output:

| Flag                 | Effect                                          |
|----------------------|-------------------------------------------------|
| `--format text\|markdown\|json\|csv` | Output format (default: text). Not all formats make sense for all sections. |
| `-o` / `--output PATH` | Write to file (default: stdout)              |
| `-q` / `--quiet`    | Summary line only + exit code                   |
| (default)            | Category summaries                              |
| `-v` / `--verbose`  | Full details per check                          |
| `--lenient`          | Allow warnings without affecting exit code       |
| `--mode core\|combined` | Scope of spec scanning                        |

### Verbosity Tiers

```text
$ elspais health -q
HEALTHY: 17/17 checks passed

$ elspais health
(current default output: category summaries with status icons)

$ elspais health -v
(current default + expanded details per check)
```

### Trace Section Detail

The `trace` section has two independent axes of detail:

**Column presets** control which columns appear in the table:

| Preset     | Columns                                              |
|------------|------------------------------------------------------|
| `minimal`  | ID, Title, Level, Status                             |
| `standard` | + Implemented, Validated                             |
| `full`     | + Passing                                            |

**Detail flags** control whether expanded rows appear beneath each requirement:

| Flag             | Effect                                      |
|------------------|---------------------------------------------|
| `--body`         | Show requirement body text                  |
| `--assertions`   | Show individual assertions                  |
| `--tests`        | Show code and test references               |

These are independent: you can have `--preset full` (all columns) without `--assertions`, or `--preset minimal --assertions` (few columns but expanded assertion rows).

Coverage columns show per-requirement assertion coverage:

| Column        | Meaning                                                        |
|---------------|----------------------------------------------------------------|
| Implemented   | % of assertions with code `Implements:` refs (direct or transitive) |
| Validated     | % of assertions with test references                           |
| Passing       | % of validated assertions whose tests pass                     |

Example output (standard preset, markdown format):

```text
| ID | Title | Level | Status | Implemented | Validated |
|----|-------|-------|--------|-------------|-----------|
| REQ-p00001 | Authentication | PRD | Active | 4/5 (80%) | 3/5 (60%) |
| REQ-o00012 | Login Flow | OPS | Active | 2/2 (100%) | 2/2 (100%) |
```

### Exit Codes

| Condition                        | Exit Code |
|----------------------------------|-----------|
| All checks pass                  | 0         |
| Warnings only (default)          | 1         |
| Warnings only (with `--lenient`) | 0         |
| Any errors                       | 1         |

### Format Support Matrix

| Section    | text | markdown | json | csv |
|------------|------|----------|------|-----|
| `health`   | yes  | yes      | yes  | no  |
| `coverage` | yes  | yes      | yes  | yes |
| `trace`    | yes  | yes      | yes  | yes |
| `changed`  | yes  | yes      | yes  | no  |

### Implementation Architecture

Each section is a **renderer** that implements a common interface:

```python
class ReportSection(Protocol):
    def render(self, graph, config, format, verbosity) -> SectionResult:
        """Return rendered content and health status."""
        ...
```

`SectionResult` contains the rendered string and a pass/fail/warning status for exit code computation.

The CLI detects when multiple section names are given as positional args, builds the graph once, runs each renderer in order, and concatenates output.

### Migration Path

1. Implement `coverage` section with all format support
2. Add `--format markdown` to `health`
3. Add composition logic (multi-command detection + concat)
4. Add `--lenient`, `-q`/`-v` to shared flags
5. Add coverage columns to `trace`
6. Extract viewer into its own command entry point
7. Remove `analyze` command
8. Remove `validate` command (or alias to `health -q` for one release)
