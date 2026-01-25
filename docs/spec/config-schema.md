# Configuration Schema Specification

This document defines the TOML configuration structure for `[trace.reports.*]` and `[rules.metrics]` sections.

## Overview

Configuration enables:
- Custom report definitions in `.elspais.toml`
- Metrics exclusion rules
- Per-project report customization

## Configuration Sections

### `[trace.reports.*]` - Report Definitions

Each named report is defined under `[trace.reports.NAME]`:

```toml
[trace.reports.minimal]
description = "Basic requirement listing"
fields = ["id", "title", "status"]
include_metrics = false
include_children = false
max_depth = 1

[trace.reports.standard]
description = "Standard report with coverage"
fields = ["id", "title", "status", "level", "implements"]
include_metrics = true
metric_fields = ["total_assertions", "covered_assertions", "coverage_pct"]
include_children = true
# max_depth omitted = unlimited

[trace.reports.full]
description = "Full report with all metrics"
fields = ["id", "title", "status", "level", "implements", "addresses", "hash"]
include_metrics = true
metric_fields = [
    "total_assertions",
    "covered_assertions",
    "total_tests",
    "passed_tests",
    "failed_tests",
    "skipped_tests",
    "total_code_refs",
    "coverage_pct",
    "pass_rate_pct",
]
include_children = true
sort_by = "id"
sort_descending = false

[trace.reports.audit]
# Custom report for compliance audits
description = "Audit-focused report"
fields = ["id", "title", "status", "level", "implements"]
include_metrics = true
metric_fields = ["total_assertions", "covered_assertions", "coverage_pct", "pass_rate_pct"]
include_children = true
filters = { status = ["Active"] }  # Only active requirements
sort_by = "coverage_pct"
sort_descending = false  # Lowest coverage first
```

### Report Configuration Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `description` | string | `""` | Human-readable description |
| `fields` | array[string] | `["id", "title", "status"]` | Requirement fields to include |
| `include_metrics` | boolean | `false` | Whether to include metrics columns |
| `metric_fields` | array[string] | `[]` | Metrics to display (if `include_metrics=true`) |
| `include_children` | boolean | `true` | Expand child nodes |
| `max_depth` | integer or null | `null` | Max hierarchy depth (null=unlimited) |
| `sort_by` | string | `"id"` | Sort field |
| `sort_descending` | boolean | `false` | Sort direction |
| `filters` | table | `{}` | Field filters |

### Available `fields` Values

```toml
# Requirement fields
fields = [
    "id",           # Requirement ID (REQ-p00001)
    "title",        # Requirement title
    "status",       # Status (Active, Draft, Deprecated, etc.)
    "level",        # Level (PRD, OPS, DEV)
    "implements",   # Parent requirement IDs
    "addresses",    # User journey IDs
    "hash",         # Content hash
    "file_path",    # Source file path
    "line_number",  # Line number in source
]
```

### Available `metric_fields` Values

```toml
# Metric fields (require include_metrics = true)
metric_fields = [
    "total_assertions",    # Total assertion count in subtree
    "covered_assertions",  # Assertions with test coverage
    "total_tests",         # Total test count in subtree
    "passed_tests",        # Tests with status "passed"
    "failed_tests",        # Tests with status "failed"
    "skipped_tests",       # Tests with status "skipped"
    "total_code_refs",     # Code reference count
    "coverage_pct",        # Coverage percentage (0.0-100.0)
    "pass_rate_pct",       # Test pass rate percentage (0.0-100.0)
]
```

### Filter Syntax

Filters restrict which requirements appear in the report:

```toml
# Include only specific statuses
filters = { status = ["Active", "Draft"] }

# Include only specific levels
filters = { level = ["PRD", "OPS"] }

# Combine filters (AND logic)
filters = { status = ["Active"], level = ["DEV"] }
```

## `[rules.metrics]` - Metrics Configuration

Controls how metrics are calculated:

```toml
[rules.metrics]
# Statuses to exclude from roll-up calculations
# Requirements with these statuses won't count toward parent metrics
exclude_status = ["Deprecated", "Superseded", "Draft"]

# Whether to count assertions with placeholder text
count_placeholder_assertions = false
```

### Metrics Configuration Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `exclude_status` | array[string] | `["Deprecated", "Superseded", "Draft"]` | Statuses excluded from parent roll-up |
| `count_placeholder_assertions` | boolean | `false` | Count removed/obsolete assertions |

## `[graph]` - Graph Configuration

The existing `[tree]` section is renamed to `[graph]`:

```toml
[graph]
default_root_kind = "requirement"

[graph.nodes.requirement]
id_pattern = "REQ-{type}{id}"
source = "spec"
has_assertions = true

[graph.nodes.user_journey]
id_pattern = "JNY-{descriptor}-{number}"
source = "spec"
is_root = true

[graph.relationships.implements]
from_kind = ["requirement"]
to_kind = ["requirement"]
direction = "up"
source_field = "implements"
required_for_non_root = true

[graph.validation]
orphan_check = true
cycle_check = true
broken_link_check = true
```

## Complete Example Configuration

```toml
# .elspais.toml

[project]
name = "my-project"

[directories]
spec = "spec"
src = "src"
tests = "tests"

# Graph structure configuration
[graph]
default_root_kind = "requirement"

[graph.validation]
orphan_check = true
cycle_check = true
broken_link_check = true

# Report definitions
[trace.reports.minimal]
description = "Quick overview"
fields = ["id", "title", "status"]
include_metrics = false
include_children = false
max_depth = 1

[trace.reports.standard]
description = "Standard traceability report"
fields = ["id", "title", "status", "level", "implements"]
include_metrics = true
metric_fields = ["total_assertions", "covered_assertions", "coverage_pct"]

[trace.reports.full]
description = "Complete report with all details"
fields = ["id", "title", "status", "level", "implements", "addresses", "hash"]
include_metrics = true
metric_fields = [
    "total_assertions",
    "covered_assertions",
    "total_tests",
    "passed_tests",
    "failed_tests",
    "coverage_pct",
    "pass_rate_pct",
]

[trace.reports.compliance]
description = "FDA compliance audit report"
fields = ["id", "title", "status", "level"]
include_metrics = true
metric_fields = ["total_assertions", "covered_assertions", "coverage_pct", "pass_rate_pct"]
filters = { status = ["Active"] }
sort_by = "coverage_pct"

# Metrics calculation rules
[rules.metrics]
exclude_status = ["Deprecated", "Superseded", "Draft"]
count_placeholder_assertions = false
```

## Default Configuration

If no `[trace.reports]` section is present, the following defaults are used:

```toml
[trace.reports.minimal]
fields = ["id", "title", "status"]
include_metrics = false
include_children = false
max_depth = 1

[trace.reports.standard]
fields = ["id", "title", "status", "level", "implements"]
include_metrics = true
metric_fields = ["total_assertions", "covered_assertions", "coverage_pct"]

[trace.reports.full]
fields = ["id", "title", "status", "level", "implements", "addresses", "hash"]
include_metrics = true
metric_fields = [
    "total_assertions",
    "covered_assertions",
    "total_tests",
    "passed_tests",
    "failed_tests",
    "skipped_tests",
    "total_code_refs",
    "coverage_pct",
    "pass_rate_pct",
]
```

## CLI Usage

```bash
# Use default report (standard)
elspais trace --graph --format markdown

# Use specific report
elspais trace --graph --report minimal --format markdown
elspais trace --graph --report full --format csv
elspais trace --graph --report compliance --format html

# Override default report
elspais trace --graph --report full -o report.html
```

## Parser Implementation Notes

The configuration parser in `config/loader.py` must:

1. Parse `[trace.reports.*]` sections into `dict[str, ReportSchema]`
2. Parse `[rules.metrics]` into metrics configuration
3. Handle the rename from `[tree]` to `[graph]`
4. Merge user-defined reports with built-in presets (user overrides win)

Example parsing logic:

```python
def parse_reports_config(config: dict) -> dict[str, ReportSchema]:
    """Parse [trace.reports.*] sections."""
    reports = {}
    trace_config = config.get("trace", {})
    reports_config = trace_config.get("reports", {})

    for name, report_dict in reports_config.items():
        reports[name] = ReportSchema(
            name=name,
            description=report_dict.get("description", ""),
            include_fields=report_dict.get("fields", ["id", "title", "status"]),
            include_metrics=report_dict.get("include_metrics", False),
            metric_fields=report_dict.get("metric_fields", []),
            include_children=report_dict.get("include_children", True),
            max_depth=report_dict.get("max_depth"),
            sort_by=report_dict.get("sort_by", "id"),
            sort_descending=report_dict.get("sort_descending", False),
            filters=report_dict.get("filters", {}),
        )

    # Add defaults for missing presets
    for preset_name, preset in ReportSchema.defaults().items():
        if preset_name not in reports:
            reports[preset_name] = preset

    return reports


def parse_metrics_config(config: dict) -> dict:
    """Parse [rules.metrics] section."""
    rules = config.get("rules", {})
    metrics = rules.get("metrics", {})

    return {
        "exclude_status": metrics.get(
            "exclude_status",
            ["Deprecated", "Superseded", "Draft"]
        ),
        "count_placeholder_assertions": metrics.get(
            "count_placeholder_assertions",
            False
        ),
    }
```
