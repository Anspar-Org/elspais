# Graph Architecture Specification

This document specifies the unified TraceGraph architecture and design principles that all elspais modules MUST follow.

---

## REQ-p00050: Unified Graph Architecture

**Level**: PRD | **Status**: Active | **Implements**: REQ-p00001

The elspais system SHALL use a unified graph-based architecture where TraceGraph is the single source of truth for all requirement data, hierarchy, and metrics.

## Assertions

A. The system SHALL use TraceGraph as the ONE and ONLY data structure for representing requirement hierarchies and relationships.
B. ALL outputs (HTML, Markdown, CSV, JSON, MCP resources) SHALL consume TraceGraph directly without creating intermediate data structures.
C. The system SHALL NOT create parallel data structures that duplicate information already in the graph.
D. The system SHALL NOT have multiple code paths that independently compute hierarchy, coverage, or relationships.

## Rationale

Multiple data structures lead to synchronization bugs, duplicated logic, and maintenance burden. A single graph provides:
- Single source of truth
- Consistent hierarchy traversal
- Centralized metrics computation
- Easier testing and debugging

*End* *Unified Graph Architecture* | **Hash**: 4a1e5d0b
---

## REQ-o00050: Graph Builder as Single Entry Point

**Level**: OPS | **Status**: Active | **Implements**: REQ-p00050

TraceGraphBuilder SHALL be the single entry point for constructing requirement graphs from parsed data.

## Assertions

A. The system SHALL use TraceGraphBuilder to construct all TraceGraph instances.
B. No module SHALL directly instantiate TraceGraph except TraceGraphBuilder.
C. TraceGraphBuilder SHALL handle all relationship linking (implements, refines, addresses).
D. TraceGraphBuilder SHALL create assertion nodes as children of requirement nodes.
E. TraceGraphBuilder SHALL support optional TODO node creation for lossless reconstruction.

## Rationale

Centralizing graph construction ensures consistent hierarchy building, cycle detection, and validation across all entry points.

*End* *Graph Builder as Single Entry Point* | **Hash**: cf6ace9c
---

## REQ-o00051: Composable Annotation Design

**Level**: OPS | **Status**: Active | **Implements**: REQ-p00050

The system SHALL use a composable annotation pattern where the graph provides iteration and separate annotator functions enrich nodes.

## Assertions

A. The graph SHALL provide an iterator (`graph.all_nodes()`) for traversing all nodes.
B. Annotation SHALL be a separate concern from graph construction.
C. Annotator functions SHALL be standalone pure functions that mutate `node.metrics` in place.
D. Annotator functions SHALL operate on individual TraceNode instances.
E. Annotation SHALL be composable - multiple annotators can be applied in sequence.
F. The system SHALL support phased annotation (e.g., base graph -> git state -> display info -> coverage).

## Rationale

Separating iteration from annotation enables:
- Reusable annotator functions across different contexts
- Clear separation of concerns
- Easy testing of individual annotators
- Flexible composition of annotation pipelines

*End* *Composable Annotation Design* | **Hash**: c73a6e32
---

## REQ-d00050: Node Annotator Functions

**Level**: DEV | **Status**: Active | **Implements**: REQ-o00051

The `core/annotators.py` module SHALL provide standalone annotator functions for enriching graph nodes.

## Assertions

A. `annotate_git_state(node, git_info)` SHALL add git metrics (is_uncommitted, is_moved, is_new, etc.) to node.metrics.
B. `annotate_display_info(node)` SHALL add display metrics (is_roadmap, display_filename, repo_prefix, etc.) to node.metrics.
C. `annotate_implementation_files(node, files)` SHALL add implementation file references to node.metrics.
D. Annotator functions SHALL only operate on REQUIREMENT nodes (skip other node kinds).
E. Annotator functions SHALL be idempotent - calling twice produces same result.

## Rationale

Per-node annotators enable fine-grained control over which annotations are applied and when.

*End* *Node Annotator Functions* | **Hash**: 35713bbd
---

## REQ-d00051: Graph Aggregate Functions

**Level**: DEV | **Status**: Active | **Implements**: REQ-o00051, REQ-p00050

The `core/annotators.py` module SHALL provide aggregate functions that compute statistics from annotated graphs.

## Assertions

A. `count_by_level(graph)` SHALL return requirement counts by level (PRD/OPS/DEV) with active/all breakdown.
B. `count_by_repo(graph)` SHALL return requirement counts by repository prefix.
C. `count_implementation_files(graph)` SHALL return total implementation file count.
D. `collect_topics(graph)` SHALL return sorted list of unique topics from file names.
E. `get_implementation_status(node)` SHALL return coverage status (Full/Partial/Unimplemented) from node.metrics.
F. Aggregate functions SHALL NOT duplicate iteration - they SHALL use graph.all_nodes().

## Rationale

Aggregate functions provide reusable statistics computation that any output format can use.

*End* *Graph Aggregate Functions* | **Hash**: bdf07870
---

## REQ-d00052: Output Generators Consume Graph Directly

**Level**: DEV | **Status**: Active | **Implements**: REQ-p00050

All output generators SHALL consume TraceGraph directly without creating intermediate data structures.

## Assertions

A. HTMLGenerator SHALL accept TraceGraph in constructor, not Dict[str, Requirement].
B. Markdown generator SHALL use graph.roots and node.children for hierarchy traversal.
C. CSV generator SHALL iterate graph.all_nodes() for flat output.
D. Generators SHALL NOT create Dict[str, TraceViewRequirement] or similar intermediate structures.
E. Generators SHALL read node.metrics for display information, not recompute it.
F. Generators SHALL use aggregate functions from annotators module for statistics.

## Rationale

Direct graph consumption eliminates data structure conversion overhead and ensures consistency.

*End* *Output Generators Consume Graph Directly* | **Hash**: 8dc48cec
---

## REQ-d00053: No Duplicate Library Functions

**Level**: DEV | **Status**: Active | **Implements**: REQ-p00050

The system SHALL NOT have duplicate implementations of core functionality across modules.

## Assertions

A. Hierarchy traversal SHALL only exist in TraceGraph (roots, children, parents, find_by_id).
B. Coverage calculation SHALL only exist in TraceGraphBuilder (computed during build).
C. Requirement loading SHALL only exist in core/loader.py (create_parser, parse_requirements_from_directories).
D. Git state detection SHALL only exist in core/git.py (get_git_changes, GitChangeInfo).
E. Pattern validation SHALL only exist in core/patterns.py (PatternValidator).
F. The system SHALL NOT have hierarchy.py files in multiple locations.

## Rationale

Duplicate implementations lead to inconsistencies, bugs, and maintenance burden. Centralizing functionality ensures single source of truth.

*End* *No Duplicate Library Functions* | **Hash**: 2e4696ef
---

## REQ-d00054: Annotation Pipeline Pattern

**Level**: DEV | **Status**: Active | **Implements**: REQ-o00051

Output generators SHALL follow a standard annotation pipeline pattern.

## Assertions

A. The pipeline SHALL be: parse -> build graph -> annotate nodes -> generate output.
B. Annotation SHALL occur after graph construction, before output generation.
C. The standard annotation sequence SHALL be: git_state -> display_info -> implementation_files.
D. Generators MAY add additional annotations specific to their output format.
E. The pipeline SHALL be implemented in TraceViewGenerator._annotate_graph_nodes().

## Rationale

A standard pipeline ensures consistent annotation across all output formats and simplifies debugging.

*End* *Annotation Pipeline Pattern* | **Hash**: 2fe44acd
---

## REQ-d00055: Node Metrics as Extension Point

**Level**: DEV | **Status**: Active | **Implements**: REQ-o00051

TraceNode.metrics SHALL be the single extension point for adding data to nodes.

## Assertions

A. All annotation data SHALL be stored in node.metrics dict.
B. Annotators SHALL NOT modify node.children, node.parents, or other structural fields.
C. Metrics keys SHALL use consistent naming (snake_case, descriptive names).
D. Standard metrics keys SHALL include: is_uncommitted, is_moved, is_new, is_roadmap, display_filename, repo_prefix, implementation_files, coverage_pct.
E. Custom metrics MAY be added by specific annotators without modifying TraceNode class.

## Rationale

Using metrics dict as the extension point enables adding new annotations without modifying the core TraceNode dataclass.

*End* *Node Metrics as Extension Point* | **Hash**: 86ea9541
---

## REQ-d00069: Indirect Coverage Source

**Level**: DEV | **Status**: Draft | **Implements**: REQ-o00051

The coverage annotation system SHALL support an INDIRECT coverage source for whole-requirement tests that do not target specific assertions.

## Assertions

A. `CoverageSource` enum SHALL include an `INDIRECT` value representing whole-requirement test coverage.
B. `RollupMetrics` SHALL track `indirect_coverage_pct` as a separate percentage alongside strict `coverage_pct`.
C. `RollupMetrics` SHALL track `validated_with_indirect` count for assertions validated when including INDIRECT sources.
D. `RollupMetrics.finalize()` SHALL compute `indirect_coverage_pct` by including INDIRECT contributions alongside DIRECT, EXPLICIT, and INFERRED sources.
E. The coverage annotator SHALL emit INDIRECT contributions for all assertion labels when a TEST edge has empty `assertion_targets`.
F. When a whole-requirement test has passing results, the annotator SHALL count all assertions as validated for indirect mode.

## Rationale

Whole-requirement tests (e.g., `test_implements_req_d00087` with no assertion suffix) currently contribute zero assertion coverage. Adding INDIRECT as a separate source allows a "progress indicator" view alongside strict traceability, following the same pattern as INFERRED coverage for requirement-to-requirement relationships.

*End* *Indirect Coverage Source* | **Hash**: ________
---

## REQ-d00070: Indirect Coverage Toggle Display

**Level**: DEV | **Status**: Draft | **Implements**: REQ-p00006

The interactive trace view SHALL provide a toggle to switch between strict and indirect coverage display modes.

## Assertions

A. `TreeRow` SHALL include a `coverage_indirect` attribute computed from `indirect_coverage_pct` using the same thresholds as strict coverage (0=none, <100=partial, 100=full).
B. The template SHALL render a `data-coverage-indirect` attribute on each requirement row.
C. The template SHALL include a toggle control in the filter bar area to switch between strict and indirect coverage views.
D. The default display SHALL show strict coverage (toggle OFF).
E. The `has_failures` warning indicator SHALL display regardless of toggle state.

## Rationale

Users need both a strict traceability view (only assertion-targeted tests count) and a progress indicator view (whole-requirement tests cover all assertions). A toggle lets users switch between modes without regenerating the trace.

*End* *Indirect Coverage Toggle Display* | **Hash**: ________
---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                        PARSE PHASE                                   │
│  ┌──────────────┐    ┌───────────────┐    ┌──────────────────────┐ │
│  │ core/loader  │───>│ core/parser   │───>│ Dict[str,Requirement]│ │
│  └──────────────┘    └───────────────┘    └──────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        BUILD PHASE                                   │
│  ┌────────────────────┐         ┌────────────────────────────────┐ │
│  │ TraceGraphBuilder  │────────>│ TraceGraph                     │ │
│  │ - add_requirements │         │ - roots: List[TraceNode]       │ │
│  │ - add_tests        │         │ - all_nodes(): Iterator        │ │
│  │ - build()          │         │ - find_by_id(id): TraceNode    │ │
│  └────────────────────┘         └────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       ANNOTATE PHASE                                 │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ for node in graph.all_nodes():                               │   │
│  │     annotate_git_state(node, git_info)                       │   │
│  │     annotate_display_info(node)                              │   │
│  │     annotate_implementation_files(node, impl_files)          │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  TraceNode.metrics = {                                               │
│      "is_uncommitted": bool,                                         │
│      "is_moved": bool,                                               │
│      "is_roadmap": bool,                                             │
│      "display_filename": str,                                        │
│      "implementation_files": List[Tuple[str, int]],                  │
│      "coverage_pct": float,                                          │
│      ...                                                             │
│  }                                                                   │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       OUTPUT PHASE                                   │
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐           │
│  │ HTMLGenerator │  │ MarkdownGen   │  │ CSVGenerator  │           │
│  │ (graph)       │  │ (graph)       │  │ (graph)       │           │
│  └───────────────┘  └───────────────┘  └───────────────┘           │
│         │                  │                  │                      │
│         ▼                  ▼                  ▼                      │
│  Uses graph.roots    Uses graph.roots   Uses graph.all_nodes()      │
│  Uses node.children  Uses node.children  Uses node.metrics          │
│  Uses node.metrics   Uses node.metrics                              │
│  Uses aggregates     Uses aggregates                                 │
└─────────────────────────────────────────────────────────────────────┘
```

## Anti-Patterns to Avoid

1. **Creating parallel data structures**
   ```python
   # BAD: Creating intermediate dict
   requirements = {r.id: TraceViewRequirement.from_core(r) for r in reqs}

   # GOOD: Use graph directly
   generator = HTMLGenerator(graph)
   ```

2. **Duplicating hierarchy logic**
   ```python
   # BAD: Finding children manually
   children = [r for r in requirements if parent_id in r.implements]

   # GOOD: Use graph relationships
   children = parent_node.children
   ```

3. **Computing coverage in multiple places**
   ```python
   # BAD: Calculating coverage in generator
   def _calculate_coverage(self, node):
       ...

   # GOOD: Read from graph metrics (computed during build)
   coverage = node.metrics.get("coverage_pct", 0)
   ```

4. **Iterating graph multiple times for same data**
   ```python
   # BAD: Multiple iterations
   by_level = self._count_by_level()  # iterates graph
   by_repo = self._count_by_repo()    # iterates graph again

   # GOOD: Use aggregate functions (designed for reuse)
   by_level = count_by_level(self.graph)
   by_repo = count_by_repo(self.graph)
   ```
