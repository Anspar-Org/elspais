# Report Schema Specification

This document defines the `ReportSchema` and `RollupMetrics` dataclasses for configurable traceability reports.

## Overview

The report system enables:
- Configurable column selection per report
- Metrics roll-up from leaves to roots
- Status-based exclusions for metrics calculations
- Named report presets (minimal, standard, full)

## RollupMetrics Dataclass

`RollupMetrics` stores computed metrics that accumulate from leaf nodes to root nodes.

```python
@dataclass
class RollupMetrics:
    """Metrics accumulated from children to parents.

    All counts are computed via post-order traversal, where each
    parent's count is the sum of its children's counts (unless excluded).

    Attributes:
        total_assertions: Count of assertion nodes in subtree.
        covered_assertions: Assertions with at least one test reference.
        total_tests: Count of test nodes in subtree.
        passed_tests: Tests with status "passed".
        failed_tests: Tests with status "failed".
        skipped_tests: Tests with status "skipped".
        total_code_refs: Count of code reference nodes in subtree.
        coverage_pct: Percentage of covered assertions (0.0-100.0).
        pass_rate_pct: Percentage of passed tests (0.0-100.0).
    """
    total_assertions: int = 0
    covered_assertions: int = 0
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    skipped_tests: int = 0
    total_code_refs: int = 0
    coverage_pct: float = 0.0
    pass_rate_pct: float = 0.0
```

### Metrics Calculation Rules

1. **Leaf Nodes** (assertions, tests, code refs):
   - Assertions: `total_assertions=1`, `covered_assertions=1` if has test children
   - Tests: `total_tests=1`, `passed_tests=1` if status is "passed"
   - Code refs: `total_code_refs=1`

2. **Internal Nodes** (requirements):
   - Sum all child metrics (excluding children with excluded statuses)
   - Recalculate percentages: `coverage_pct = (covered / total) * 100`

3. **Exclusions** (configurable via `[rules.metrics]`):
   - Requirements with status in `exclude_status` list are excluded from parent roll-up
   - Default excludes: `["Deprecated", "Superseded", "Draft"]`

## ReportSchema Dataclass

`ReportSchema` defines which fields and metrics appear in a report.

```python
@dataclass
class ReportSchema:
    """Schema defining report content and layout.

    Attributes:
        name: Report identifier (e.g., "minimal", "standard", "full").
        description: Human-readable description.
        include_fields: List of requirement fields to include.
        include_metrics: Whether to include RollupMetrics columns.
        metric_fields: Which metric fields to display (if include_metrics=True).
        include_children: Whether to expand child nodes in output.
        max_depth: Maximum hierarchy depth to display (None = unlimited).
        sort_by: Field to sort by ("id", "coverage_pct", "pass_rate_pct").
        sort_descending: Sort direction.
        filters: Optional filters (e.g., {"status": ["Active", "Draft"]}).
    """
    name: str
    description: str = ""
    include_fields: list[str] = field(default_factory=lambda: ["id", "title", "status"])
    include_metrics: bool = False
    metric_fields: list[str] = field(default_factory=list)
    include_children: bool = True
    max_depth: int | None = None
    sort_by: str = "id"
    sort_descending: bool = False
    filters: dict[str, list[str]] = field(default_factory=dict)
```

### Available Fields

#### Requirement Fields

- `id` - Requirement ID (e.g., "REQ-p00001")
- `title` - Requirement title
- `status` - Status (Active, Draft, Deprecated, etc.)
- `level` - Config type key (e.g., `prd`, `ops`, `dev`)
- `implements` - Parent requirement IDs
- `addresses` - User journey IDs
- `hash` - Content hash
- `file_path` - Source file path
- `line_number` - Line number in source

#### Metric Fields

- `total_assertions` - Total assertion count
- `covered_assertions` - Covered assertion count
- `total_tests` - Total test count
- `passed_tests` - Passed test count
- `failed_tests` - Failed test count
- `skipped_tests` - Skipped test count
- `total_code_refs` - Code reference count
- `coverage_pct` - Coverage percentage
- `pass_rate_pct` - Test pass rate percentage

## Built-in Report Presets

### Minimal

Basic traceability listing without metrics.

```python
ReportSchema(
    name="minimal",
    description="Basic requirement listing",
    include_fields=["id", "title", "status"],
    include_metrics=False,
    include_children=False,
    max_depth=1,
)
```

### Standard

Default report with coverage metrics.

```python
ReportSchema(
    name="standard",
    description="Standard report with coverage",
    include_fields=["id", "title", "status", "level", "implements"],
    include_metrics=True,
    metric_fields=["total_assertions", "covered_assertions", "coverage_pct"],
    include_children=True,
    max_depth=None,
)
```

### Full

Complete report with all metrics.

```python
ReportSchema(
    name="full",
    description="Full report with all metrics",
    include_fields=["id", "title", "status", "level", "implements", "addresses", "hash"],
    include_metrics=True,
    metric_fields=[
        "total_assertions",
        "covered_assertions",
        "total_tests",
        "passed_tests",
        "failed_tests",
        "skipped_tests",
        "total_code_refs",
        "coverage_pct",
        "pass_rate_pct",
    ],
    include_children=True,
    max_depth=None,
)
```

## Integration with GraphSchema

`GraphSchema` gains a `reports` field:

```python
@dataclass
class GraphSchema:
    # ... existing fields ...
    reports: dict[str, ReportSchema] = field(default_factory=dict)

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> GraphSchema:
        # Parse [trace.reports.*] sections
        reports = {}
        for name, report_config in config.get("trace", {}).get("reports", {}).items():
            reports[name] = ReportSchema(
                name=name,
                description=report_config.get("description", ""),
                include_fields=report_config.get("fields", ["id", "title", "status"]),
                include_metrics=report_config.get("include_metrics", False),
                metric_fields=report_config.get("metric_fields", []),
                include_children=report_config.get("include_children", True),
                max_depth=report_config.get("max_depth"),
                sort_by=report_config.get("sort_by", "id"),
                sort_descending=report_config.get("sort_descending", False),
                filters=report_config.get("filters", {}),
            )
        # Add defaults if not overridden
        for preset in ReportSchema.defaults().values():
            if preset.name not in reports:
                reports[preset.name] = preset
        return cls(reports=reports, ...)
```

## TraceNode Metrics Integration

`TraceNode` gains a `metrics` attribute of type `RollupMetrics`:

```python
@dataclass
class TraceNode:
    # ... existing fields ...
    metrics: RollupMetrics = field(default_factory=RollupMetrics)
```

Note: The existing `metrics: dict[str, Any]` field is replaced with the typed `RollupMetrics` dataclass.

## TraceGraphBuilder.compute_metrics()

New method for metrics computation:

```python
def compute_metrics(
    self,
    graph: TraceGraph,
    exclude_status: list[str] | None = None,
) -> None:
    """Compute roll-up metrics for all nodes.

    Uses post-order traversal to sum metrics from leaves to roots.
    Nodes with status in exclude_status are excluded from parent roll-ups.

    Args:
        graph: The graph to compute metrics for.
        exclude_status: Statuses to exclude from roll-up (default from config).
    """
    exclude = exclude_status or self._get_exclude_status_from_config()

    for node in graph.all_nodes(order="post"):
        if node.kind == NodeKind.ASSERTION:
            node.metrics.total_assertions = 1
            node.metrics.covered_assertions = 1 if node.children else 0
        elif node.kind == NodeKind.TEST:
            node.metrics.total_tests = 1
            result = self._get_test_result(node)
            if result == "passed":
                node.metrics.passed_tests = 1
            elif result == "failed":
                node.metrics.failed_tests = 1
            elif result == "skipped":
                node.metrics.skipped_tests = 1
        elif node.kind == NodeKind.CODE:
            node.metrics.total_code_refs = 1
        elif node.kind == NodeKind.REQUIREMENT:
            # Sum child metrics, respecting exclusions
            for child in node.children:
                if self._should_include(child, exclude):
                    node.metrics.total_assertions += child.metrics.total_assertions
                    node.metrics.covered_assertions += child.metrics.covered_assertions
                    # ... sum other fields ...
            # Compute percentages
            if node.metrics.total_assertions > 0:
                node.metrics.coverage_pct = (
                    node.metrics.covered_assertions / node.metrics.total_assertions
                ) * 100
            if node.metrics.total_tests > 0:
                node.metrics.pass_rate_pct = (
                    node.metrics.passed_tests / node.metrics.total_tests
                ) * 100
```

## CLI Integration

New `--report` flag:

```bash
elspais trace --report minimal    # Use minimal report schema
elspais trace --report standard   # Use standard report schema (default)
elspais trace --report full       # Use full report schema
elspais trace --report my-custom  # Use custom report from config
```

## Generator Interface Update

Generators receive `ReportSchema` parameter:

```python
def generate(
    self,
    requirements: dict[str, Requirement],
    output_path: Path,
    report_schema: ReportSchema | None = None,
) -> None:
    """Generate output with configurable schema.

    Args:
        requirements: Requirements to include.
        output_path: Output file path.
        report_schema: Schema defining fields and metrics to include.
    """
```
