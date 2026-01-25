# Graph Rename Specification

This document defines the complete mapping for renaming "tree" terminology to "graph" terminology across the elspais codebase.

## Rationale

The data structure is a Directed Acyclic Graph (DAG), not a tree:
- Nodes can have multiple parents (e.g., a test validating multiple assertions)
- The "implements" relationship creates a DAG, not a strict tree hierarchy
- "Graph" more accurately describes the traceability structure

## File Renames

| Original Path | New Path |
|---------------|----------|
| `src/elspais/core/tree.py` | `src/elspais/core/graph.py` |
| `src/elspais/core/tree_schema.py` | `src/elspais/core/graph_schema.py` |
| `src/elspais/core/tree_builder.py` | `src/elspais/core/graph_builder.py` |
| `tests/test_tree.py` | `tests/test_graph.py` |
| `tests/test_tree_builder.py` | `tests/test_graph_builder.py` |
| `tests/test_tree_schema.py` | `tests/test_graph_schema.py` |

## Class Renames

| Original Class | New Class | Location |
|----------------|-----------|----------|
| `TraceTree` | `TraceGraph` | `graph.py` |
| `TraceTreeBuilder` | `TraceGraphBuilder` | `graph_builder.py` |
| `TreeSchema` | `GraphSchema` | `graph_schema.py` |

## Function Renames

| Original Function | New Function | Location |
|-------------------|--------------|----------|
| `build_tree_from_requirements` | `build_graph_from_requirements` | `graph_builder.py` |
| `build_tree_from_repo` | `build_graph_from_repo` | `graph_builder.py` |

## CLI Flag Changes

| Original Flag | New Flag | Description |
|---------------|----------|-------------|
| `--tree` | `--graph` | Use unified traceability graph |
| `--tree-json` | `--graph-json` | Output graph structure as JSON |

## Output Filename Changes

| Original Filename | New Filename |
|-------------------|--------------|
| `traceability_tree.md` | `traceability_graph.md` |
| `traceability_tree.html` | `traceability_graph.html` |
| `traceability_tree.csv` | `traceability_graph.csv` |
| `traceability_tree.json` | `traceability_graph.json` |

## Import Updates Required

### Files with `from elspais.core.tree import ...`

1. `src/elspais/core/tree_builder.py` → `graph_builder.py`
2. `src/elspais/commands/trace.py`
3. `src/elspais/parsers/__init__.py`
4. `src/elspais/parsers/test.py`
5. `src/elspais/parsers/requirement.py`
6. `src/elspais/parsers/code.py`
7. `src/elspais/parsers/journey.py`
8. `src/elspais/parsers/pytest_json.py`
9. `src/elspais/parsers/junit_xml.py`

### Files with `from elspais.core.tree_schema import ...`

1. `src/elspais/core/tree_builder.py` → `graph_builder.py`
2. `src/elspais/parsers/__init__.py`
3. `src/elspais/parsers/test.py`
4. `src/elspais/parsers/requirement.py`
5. `src/elspais/parsers/code.py`
6. `src/elspais/parsers/journey.py`
7. `src/elspais/parsers/pytest_json.py`
8. `src/elspais/parsers/junit_xml.py`

### Test Files

All test files in the list above need import updates:
- `tests/test_tree.py` → `tests/test_graph.py`
- `tests/test_tree_builder.py` → `tests/test_graph_builder.py`
- `tests/test_tree_schema.py` → `tests/test_graph_schema.py`
- `tests/test_parsers.py`

## Configuration Key Changes

| Original Key | New Key |
|--------------|---------|
| `[tree]` | `[graph]` |
| `[tree.nodes]` | `[graph.nodes]` |
| `[tree.relationships]` | `[graph.relationships]` |
| `[tree.parsers]` | `[graph.parsers]` |
| `[tree.validation]` | `[graph.validation]` |
| `default_root_kind` | `default_root_kind` (unchanged) |

## Documentation Updates

Files requiring updates:
- `CLAUDE.md` - Update CLI examples and architecture references
- `docs/overview.md` - Update trace command examples
- `docs/roadmap/review_executive_summary_developers.md`
- `docs/roadmap/review_executive_summary_auditors.md`

## Backwards Compatibility

For the initial release, we will NOT maintain backwards compatibility for:
- Old CLI flags (`--tree`, `--tree-json`)
- Old config keys (`[tree]`)
- Old class names

This is acceptable as the tree-based trace feature is still in development and has no external consumers.

## Verification Commands

After refactor, verify with:

```bash
# Ensure no "tree" references remain in core code (except comments)
grep -r "TraceTree\|TreeSchema\|tree_builder\|tree_schema\|tree\.py" src/elspais/

# Verify imports work
python -c "from elspais.core.graph import TraceGraph, TraceNode, NodeKind"
python -c "from elspais.core.graph_schema import GraphSchema"
python -c "from elspais.core.graph_builder import TraceGraphBuilder"

# Run tests
pytest tests/test_graph*.py -v
```
