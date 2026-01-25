# Future Plan: MCP Graph Integration

**Status:** Planned for Phase 2 (when user demand exists)
**Trigger:** Users requesting test coverage queries, hierarchy traversal, or metrics

---

## Current State

MCP server uses flat `Dict[str, Requirement]` cache in `WorkspaceContext`. Sufficient for:
- List/get requirements
- Basic search (regex)
- Validation
- Simple hierarchy analysis (re-computed on demand)

---

## Proposed Enhancement

Integrate TraceGraph as optional cached data source for richer queries.

### New Capabilities Enabled

| Query | Without Graph | With Graph |
|-------|--------------|------------|
| "What tests cover REQ-001?" | Not possible | `node.find_by_kind(TEST)` |
| "What's REQ-001 coverage?" | Not possible | `node.metrics["coverage_pct"]` |
| "Children of REQ-001" | Build map on demand | `node.children` |
| "Ancestors of DEV-001" | Walk implements recursively | `node.ancestors()` |
| "All failing tests" | Not possible | Filter by status |
| Orphaned requirements | Re-scan each time | Pre-computed |

### Cost Analysis

- Graph build adds ~50% overhead on top of parsing
- Trade-off: O(1) relationship traversal + pre-computed metrics
- Worthwhile for repos with test coverage enabled

---

## Implementation Sketch

### Changes to `mcp/context.py`

```python
@dataclass
class WorkspaceContext:
    # Existing
    _requirements_cache: Optional[Dict[str, Requirement]] = None

    # New: Graph cache
    _graph: Optional[TraceGraph] = None
    _validation: Optional[ValidationResult] = None

    def get_graph(self, force_refresh: bool = False) -> TraceGraph:
        """Get traceability graph with caching."""
        if self._graph is None or force_refresh:
            self._graph, self._validation = self._build_graph()
        return self._graph

    def _build_graph(self) -> Tuple[TraceGraph, ValidationResult]:
        """Build graph from requirements and tests."""
        requirements = self.get_requirements()

        builder = TraceGraphBuilder(
            repo_root=self.working_dir,
            schema=GraphSchema.from_config(self.config),
        )
        builder.add_requirements(requirements)

        # Optionally add tests if testing enabled
        if self.config.get("testing", {}).get("enabled"):
            test_nodes = self._scan_tests()
            builder.add_test_coverage(test_nodes)

        graph, validation = builder.build_and_validate()
        builder.compute_metrics(graph)
        return graph, validation
```

### New MCP Tools

```python
@mcp.tool()
def get_coverage(req_id: str) -> Dict[str, Any]:
    """Get test coverage metrics for a requirement."""
    graph = ctx.get_graph()
    node = graph.find_by_id(req_id)
    return {
        "id": req_id,
        "total_assertions": node.metrics.get("total_assertions", 0),
        "covered_assertions": node.metrics.get("covered_assertions", 0),
        "coverage_pct": node.metrics.get("coverage_pct", 0.0),
        "total_tests": node.metrics.get("total_tests", 0),
        "pass_rate_pct": node.metrics.get("pass_rate_pct", 0.0),
    }

@mcp.tool()
def get_tests_for_requirement(req_id: str) -> Dict[str, Any]:
    """Get all tests that validate a requirement."""
    graph = ctx.get_graph()
    node = graph.find_by_id(req_id)
    tests = list(node.find_by_kind(NodeKind.TEST))
    return {
        "id": req_id,
        "tests": [{"id": t.id, "name": t.test_ref.test_name, "status": t.metrics.get("_test_status")} for t in tests],
    }

@mcp.tool()
def get_hierarchy(req_id: str) -> Dict[str, Any]:
    """Get full hierarchy (ancestors and descendants) for a requirement."""
    graph = ctx.get_graph()
    node = graph.find_by_id(req_id)
    return {
        "id": req_id,
        "ancestors": [a.id for a in node.ancestors()],
        "children": [c.id for c in node.children if c.kind == NodeKind.REQUIREMENT],
        "depth": node.depth,
    }
```

### New MCP Resources

| Resource URI | Description |
|-------------|-------------|
| `graph://stats` | Graph node counts by kind |
| `graph://coverage` | Overall coverage metrics |
| `tests://requirement/{id}` | Tests validating a requirement |
| `hierarchy://{id}` | Full hierarchy for a requirement |

### Graph Invalidation Strategy

```python
def _is_stale(self) -> bool:
    """Check if any spec/test files changed since last build."""
    for path, mtime in self._graph_mtimes.items():
        if Path(path).stat().st_mtime > mtime:
            return True
    return False
```

Options:
1. **Explicit**: `invalidate_cache()` or `force_refresh=True`
2. **File-based**: Check mtimes before serving
3. **Time-based**: TTL cache (e.g., refresh after 30s)

---

## Files to Modify

| File | Changes |
|------|---------|
| `src/elspais/mcp/context.py` | Add `_graph` cache, `get_graph()`, `_build_graph()` |
| `src/elspais/mcp/server.py` | Add `get_coverage`, `get_tests_for_requirement`, `get_hierarchy` tools |
| `src/elspais/mcp/server.py` | Add `graph://stats`, `tests://` resources |

---

## Dependencies

- Requires TestParser unification (current plan) to be complete
- Test scanning must work via parser registry before MCP can use it

---

## References

- Current plan: `/home/metagamer/.claude/plans/glowing-nibbling-lamport.md`
- Graph reference: `.claude/graph-reference.md`
- TraceGraph: `src/elspais/core/graph.py`
- GraphBuilder: `src/elspais/core/graph_builder.py`
