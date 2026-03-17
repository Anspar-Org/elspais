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

C. TraceGraphBuilder SHALL handle all relationship linking (implements, refines, addresses, satisfies, instance).

D. TraceGraphBuilder SHALL create assertion nodes as children of requirement nodes.

E. TraceGraphBuilder SHALL support optional TODO node creation for lossless reconstruction.

## Rationale

Centralizing graph construction ensures consistent hierarchy building, cycle detection, and validation across all entry points.

*End* *Graph Builder as Single Entry Point* | **Hash**: e3a0add2
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

G. All file write operations in output commands SHALL specify explicit `encoding="utf-8"` for cross-platform portability.

## Rationale

Direct graph consumption eliminates data structure conversion overhead and ensures consistency.

*End* *Output Generators Consume Graph Directly* | **Hash**: a3575fcc
---

## REQ-d00054: Annotation Pipeline Pattern

**Level**: DEV | **Status**: Active | **Implements**: REQ-o00051

Output generators SHALL follow a standard annotation pipeline pattern.

## Assertions

A. The pipeline SHALL be: parse -> build graph -> annotate nodes -> generate output.

## Rationale

A standard pipeline ensures consistent annotation across all output formats and simplifies debugging.

*End* *Annotation Pipeline Pattern* | **Hash**: 0256df47
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

**Level**: DEV | **Status**: Active | **Implements**: REQ-o00051

The coverage annotation system SHALL support an INDIRECT coverage source for whole-requirement tests that do not target specific assertions.

## Assertions

A. `CoverageSource` enum SHALL include an `INDIRECT` value representing whole-requirement test coverage.

B. `RollupMetrics` SHALL track `indirect_coverage_pct` as a separate percentage alongside strict `coverage_pct`.

C. `RollupMetrics` SHALL track `validated_with_indirect` count for assertions validated when including INDIRECT sources.

D. `RollupMetrics.finalize()` SHALL compute `indirect_coverage_pct` by including INDIRECT contributions alongside DIRECT, EXPLICIT, and INFERRED sources.

E. The coverage annotator SHALL emit INDIRECT contributions for all assertion labels when a TEST edge has empty `assertion_targets`.

F. When a whole-requirement test has passing results, the annotator SHALL count all assertions as validated for indirect mode.

G. A leaf assertion SHALL be defined as any assertion that has no `Refines:` child pointing at it. Leaf assertions can occur at any level or place in the hierarchy.

H. When a requirement declares `Satisfies: X`, the graph builder SHALL clone the template's REQ subtree with composite IDs (`declaring_id::original_id`), creating INSTANCE nodes linked to the declaring requirement via a SATISFIES edge. Coverage SHALL be computed through the standard coverage mechanism operating on the cloned nodes.

I. 100% coverage of a template instance SHALL be achieved when every leaf assertion in the cloned template subtree (excluding N/A assertions) has at least one `Implements:` reference.

J. A `Refines:` relationship SHALL NOT count as coverage in itself, but coverage of its child assertions SHALL propagate upward. An assertion with `Refines:` children SHALL have fractional coverage equal to the proportion of its covered leaf descendants.

K. The system SHALL report coverage gaps on template instance nodes through the standard coverage mechanisms. Instance nodes are normal graph nodes and participate in existing health checks.

## Rationale

Whole-requirement tests (e.g., `test_implements_req_d00087` with no assertion suffix) currently contribute zero assertion coverage. Adding INDIRECT as a separate source allows a "progress indicator" view alongside strict traceability, following the same pattern as INFERRED coverage for requirement-to-requirement relationships.

*End* *Indirect Coverage Source* | **Hash**: 114709f5
---

## REQ-d00070: Indirect Coverage Toggle Display

**Level**: DEV | **Status**: Active | **Implements**: REQ-p00006

The interactive trace view SHALL provide a toggle to switch between strict and indirect coverage display modes.

## Assertions

A. `TreeRow` SHALL include a `coverage_indirect` attribute computed from `indirect_coverage_pct` using the same thresholds as strict coverage (0=none, <100=partial, 100=full).

B. The template SHALL render a `data-coverage-indirect` attribute on each requirement row.

C. The template SHALL include a toggle control in the filter bar area to switch between strict and indirect coverage views.

D. The default display SHALL show strict coverage (toggle OFF).

E. The `has_failures` warning indicator SHALL display regardless of toggle state.

## Rationale

Users need both a strict traceability view (only assertion-targeted tests count) and a progress indicator view (whole-requirement tests cover all assertions). A toggle lets users switch between modes without regenerating the trace.

*End* *Indirect Coverage Toggle Display* | **Hash**: d483becb
---

## REQ-d00071: Unified Root vs Orphan Classification

**Level**: DEV | **Status**: Active | **Implements**: REQ-o00050, REQ-p00002

The graph builder SHALL distinguish between root nodes and orphan nodes using a unified classification based on meaningful children.

## Assertions

A. The graph builder SHALL classify a parentless node as a root only when it has at least one child whose kind is not a satellite kind.

B. The graph builder SHALL classify a parentless node as an orphan when it has no children whose kind is not a satellite kind.

C. Satellite node kinds SHALL be configurable via `[graph].satellite_kinds` in `.elspais.toml`, defaulting to ASSERTION and TEST_RESULT.

D. USER_JOURNEY nodes SHALL follow the same root vs orphan classification rules as REQUIREMENT nodes.

## Rationale

Currently, all parentless REQUIREMENTs and all USER_JOURNEYs are unconditionally treated as roots, even when disconnected from the rest of the graph. A PRD with only assertions but no OPS/DEV implementations is effectively orphaned — it anchors no subgraph. Unifying the classification rule across all node kinds simplifies the logic and produces more accurate orphan detection.

*End* *Unified Root vs Orphan Classification* | **Hash**: 46d2a3e2
---

## REQ-o00065: Agent-Assisted Link Suggestion

**Level**: OPS | **Status**: Active | **Implements**: REQ-p00050

The system SHALL provide an agent-assisted link suggestion engine that analyzes unlinked graph nodes and proposes requirement associations using scoring heuristics.

## Assertions

A. The suggestion engine SHALL identify unlinked TEST nodes (those without REQUIREMENT parents via VALIDATES edges) as suggestion candidates.

B. The suggestion engine SHALL score suggestions using multiple heuristics: import chain analysis, function name matching, file path proximity, and keyword overlap.

C. Each suggestion SHALL include a source node, target requirement, confidence score (0.0-1.0), confidence band (high/medium/low), and human-readable reason.

D. The suggestion engine SHALL be exposed through both CLI (`elspais link suggest`) and MCP tools (`suggest_links`).

E. The suggestion engine SHALL operate read-only on the graph, producing suggestions without modifying graph state.

F. The suggestion engine SHALL support applying suggestions by inserting `# Implements:` comments into source files.

## Rationale

Teams need to not just see what's unlinked but act on it efficiently. Combining existing building blocks (import analyzer, test-code linker, keyword search) into a scoring pipeline enables AI agents and humans to close traceability gaps systematically.

*End* *Agent-Assisted Link Suggestion* | **Hash**: 7c449e0c
---

## REQ-d00072: Link Suggestion Core Engine

**Level**: DEV | **Status**: Active | **Implements**: REQ-o00065

The `graph/link_suggest.py` module SHALL implement the link suggestion scoring pipeline using existing graph analysis building blocks.

## Assertions

A. `suggest_links(graph, repo_root, file_path?, limit?)` SHALL orchestrate all heuristics and return deduplicated `LinkSuggestion` instances sorted by confidence descending.

B. The import chain heuristic SHALL trace TEST→import→CODE→REQ relationships using `extract_python_imports()` and `module_to_source_path()` from `utilities/import_analyzer.py`, scoring matches at 0.9.

C. The function name heuristic SHALL match test function names to CODE nodes using `_extract_candidate_functions()` from `graph/test_code_linker.py`, scoring exact matches at 0.85 with decreasing scores for partial matches.

D. The file path proximity heuristic SHALL map test file paths to source directories and find REQUIREMENTs linked to CODE in those directories, scoring at 0.6.

E. The keyword overlap heuristic SHALL compare test name/docstring keywords against REQUIREMENT title keywords using `extract_keywords()` from `graph/annotators.py`, scoring at the overlap ratio capped at 0.5.

F. `_deduplicate_suggestions()` SHALL merge suggestions for the same (test, requirement) pair, keeping the highest confidence and combining reasons.

## Rationale

The core engine composes existing building blocks into a scoring pipeline. Each heuristic reuses proven code rather than reimplementing analysis logic.

*End* *Link Suggestion Core Engine* | **Hash**: 2cd50cdc
---

## REQ-d00073: Link Suggestion CLI Command

**Level**: DEV | **Status**: Draft | **Implements**: REQ-o00065-D

The `commands/link_suggest.py` module SHALL provide the `elspais link suggest` CLI command.

## Assertions

A. `elspais link suggest` SHALL scan all unlinked test nodes and print suggestions with confidence scores.

B. `--file <path>` SHALL restrict analysis to a single file.

C. `--format json` SHALL output suggestions as a JSON array for programmatic consumption.

D. `--min-confidence high|medium|low` SHALL filter suggestions by confidence band (high >= 0.8, medium >= 0.5, low < 0.5).

E. `--apply [--dry-run]` SHALL insert `# Implements:` comments into source files at the suggested locations, with dry-run previewing changes without writing.

## Rationale

CLI exposure enables both interactive use and CI pipeline integration. JSON output mode supports tooling and scripting workflows.

*End* *Link Suggestion CLI Command* | **Hash**: 44fd54e9
---

## REQ-d00126: FILE Node Data Model

**Level**: DEV | **Status**: Draft | **Implements**: REQ-p00050

The graph data model SHALL support FILE nodes and file-aware edge kinds for representing source file structure in the traceability graph.

## Assertions

A. `NodeKind` enum SHALL include a `FILE` value with string representation `"file"`.

B. A `FileType` enum SHALL exist alongside `NodeKind` with values: `SPEC`, `JOURNEY`, `CODE`, `TEST`, `RESULT`.

C. `EdgeKind` enum SHALL include `STRUCTURES`, `DEFINES`, and `YIELDS` values for file-aware structural edges.

D. `STRUCTURES`, `DEFINES`, and `YIELDS` edge kinds SHALL NOT contribute to coverage (i.e., `contributes_to_coverage()` returns `False`).

E. `Edge` dataclass SHALL have a `metadata: dict[str, Any]` field defaulting to an empty dict, excluded from `__eq__` and `__hash__` comparisons.

## Rationale

FILE nodes are the foundation for representing source files as first-class graph participants. The new edge kinds (STRUCTURES, DEFINES, YIELDS) enable domain-internal hierarchy, virtual node provenance, and test-result linking. Edge metadata carries mutable annotations (line ranges, render order) without affecting edge identity.

*End* *FILE Node Data Model* | **Hash**: 664d3990
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

## REQ-d00127: GraphNode API: Filtered Traversal and Edge-Only Relationships

**Level**: DEV | **Status**: Draft | **Implements**: REQ-p00050

GraphNode SHALL use edge-only relationships (via `link()`) and support filtered traversal by edge kind, eliminating the edge-less `add_child()` mechanism.

## Assertions

A. `GraphNode` SHALL NOT have an `add_child()` method. All parent-child relationships SHALL be created via `link()` with a typed `EdgeKind`.

B. `GraphNode.remove_child()` SHALL be renamed to `unlink()`, retaining identical behavior: severs all edges between two nodes and removes cache entries.

C. `iter_children()`, `iter_parents()`, `walk()`, and `ancestors()` SHALL accept an optional `edge_kinds` parameter. When provided, only nodes reachable via the specified edge kinds are returned. When `None` (default), all nodes are returned (backwards compatible).

D. `GraphNode.file_node()` SHALL walk incoming edges upward to find the nearest ancestor with `kind == NodeKind.FILE`, returning `None` if no FILE ancestor exists.

E. TEST_RESULT nodes SHALL be linked from TEST nodes via `EdgeKind.YIELDS` (TEST -> TEST_RESULT direction), not via `EdgeKind.CONTAINS`.

## Rationale

Eliminating `add_child()` ensures every relationship in the graph has a typed edge, enabling filtered traversal. The `file_node()` convenience method provides efficient navigation to FILE ancestors. Renaming `remove_child()` to `unlink()` creates API symmetry with `link()`. The YIELDS edge kind correctly models the TEST->TEST_RESULT relationship.

*End* *GraphNode API: Filtered Traversal and Edge-Only Relationships* | **Hash**: 12964863
---

## REQ-d00128: FILE Node Creation in Build Pipeline

**Level**: DEV | **Status**: Draft | **Implements**: REQ-p00050

The build pipeline SHALL create FILE nodes for every scanned file and wire CONTAINS edges from FILE to top-level content nodes, with RemainderParser mandatory for text-based file types.

## Assertions

A. `factory.py` SHALL create a FILE node with ID `file:<repo-relative-path>` for every scanned file before parsing its content.

B. FILE node content fields SHALL include: `file_type` (FileType enum), `absolute_path` (str), `relative_path` (str), `repo` (str or None), `git_branch` (str or None), `git_commit` (str or None).

C. `git_branch` and `git_commit` SHALL be captured once per repository, not per file.

D. `GraphBuilder.add_parsed_content()` SHALL accept an optional `file_node` parameter and wire CONTAINS edges from the FILE node to top-level content nodes (REQUIREMENT, USER_JOURNEY, file-level REMAINDER, CODE, TEST).

E. CONTAINS edge metadata SHALL include `start_line` (int), `end_line` (int or None), and `render_order` (float, sequential from 0.0).

F. ASSERTION and requirement-level REMAINDER nodes SHALL NOT receive CONTAINS edges from FILE; they are reached via STRUCTURES edges from their parent REQUIREMENT.

G. RemainderParser SHALL be mandatory for SPEC, JOURNEY, CODE, and TEST file types, ensuring every line is claimed by some parser.

H. RemainderParser SHALL NOT be registered for RESULT file types.

I. FILE nodes SHALL be additive: existing graph behavior (traceability, coverage, root/orphan detection) SHALL remain unaffected.

J. Template instantiation (`_instantiate_satisfies_templates()`) SHALL create DEFINES edges from the declaring requirement's FILE node to each INSTANCE node in the cloned subtree.

K. INSTANCE nodes SHALL NOT have CONTAINS edges. They are virtual nodes not physically present in any file.

L. `file_node()` SHALL return None for INSTANCE nodes. To find the originating file, navigate via the INSTANCE edge to the original node and call `file_node()` on it.

## Rationale

FILE nodes make source files first-class graph participants. Creating them in factory.py (which knows the file path and type) rather than the deserializer maintains separation of concerns. CONTAINS edges with line-range metadata enable file-level operations. RemainderParser ensures complete line coverage for text-based files. DEFINES edges from FILE to INSTANCE nodes establish provenance for virtual nodes created by template instantiation.

*End* *FILE Node Creation in Build Pipeline* | **Hash**: 166358a3
---

## REQ-d00129: SourceLocation Removal and Consumer Migration

**Level**: DEV | **Status**: Draft | **Implements**: REQ-p00050

The `SourceLocation` class and `GraphNode.source` field SHALL be removed. All consumers SHALL migrate to use `file_node()` for file paths and `get_field("parse_line")` / `get_field("parse_end_line")` for line numbers.

## Assertions

A. `SourceLocation` class SHALL NOT exist in the codebase. Importing it SHALL raise `ImportError`.

B. `GraphNode` SHALL NOT have a `source` field. Accessing `node.source` on any `GraphNode` instance SHALL raise `AttributeError`.

C. Content nodes SHALL store `parse_line` (int) and `parse_end_line` (int or None) as fields accessible via `get_field()`.

D. All consumers that previously read `node.source.path` SHALL use `node.file_node().get_field("relative_path")` (with None-guard for unlinked/INSTANCE nodes).

E. All consumers that previously read `node.source.line` SHALL use `node.get_field("parse_line")`.

F. All consumers that previously read `node.source.repo` SHALL use `node.file_node().get_field("repo")` (with None-guard).

G. External output (CLI text, MCP JSON responses, HTML, PDF) SHALL produce identical file paths and line numbers as before the migration.

## Rationale

SourceLocation duplicates information now available through the graph structure itself. FILE nodes carry path and repo identity; content nodes carry line numbers as fields. Removing SourceLocation eliminates redundancy and ensures all file identity flows through the graph's edge structure.

*End* *SourceLocation Removal and Consumer Migration* | **Hash**: 8bd81196
---

## REQ-d00130: Parameterized Root Iteration and Kind-Based Index Query

**Level**: DEV | **Status**: Draft | **Implements**: REQ-p00050

`TraceGraph.iter_roots()` SHALL accept an optional `NodeKind` filter, and `TraceGraph` SHALL provide `iter_by_kind()` for general kind-based index queries.

## Assertions

A. `iter_roots()` with no argument SHALL return the same nodes as current behavior (REQ and JOURNEY roots), excluding FILE nodes.

B. `iter_roots(NodeKind.FILE)` SHALL return all FILE nodes from `_index`.

C. `iter_roots(NodeKind.REQUIREMENT)` SHALL return only REQUIREMENT roots from `_roots`.

D. `iter_roots(NodeKind.USER_JOURNEY)` SHALL return only USER_JOURNEY roots from `_roots`.

E. `iter_by_kind(kind)` SHALL iterate all nodes of the given `NodeKind` from `_index`, equivalent to the existing `nodes_by_kind()` method.

F. FILE nodes SHALL NOT appear in the default `iter_roots()` results (no argument).

## Rationale

Parameterized roots enable view-specific entry points into the graph: domain consumers iterate REQ/JOURNEY roots as before, while file-level consumers iterate FILE nodes. `iter_by_kind()` provides a naming-consistent alternative to `nodes_by_kind()` aligned with the iterator-only API convention.

*End* *Parameterized Root Iteration and Kind-Based Index Query* | **Hash**: f56f8527
---

## REQ-d00131: Render Protocol for Graph Nodes

**Level**: DEV | **Status**: Draft | **Implements**: REQ-p00050

Each domain NodeKind SHALL have a render function that produces its text representation. Walking a FILE node's CONTAINS children in render_order and concatenating their rendered output SHALL produce the file's content.

## Assertions

A. Each `NodeKind` SHALL have a `render()` function that returns its text representation as a string, dispatched by kind.

B. `REQUIREMENT` render SHALL produce the full requirement block: header line (`## REQ-xxx: Title`), metadata line, body text, `## Assertions` heading with assertion lines from STRUCTURES children, non-normative sections from STRUCTURES children, and `*End*` marker with hash.

C. `ASSERTION` nodes SHALL be rendered by their parent REQUIREMENT's render function, not independently. Calling render on an ASSERTION directly SHALL raise `ValueError`.

D. `REMAINDER` render SHALL return its raw text verbatim, preserving all whitespace and content exactly as parsed.

E. `USER_JOURNEY` render SHALL produce the full journey block including header, actor/goal fields, body, and end marker.

F. `CODE` render SHALL produce the `# Implements:` comment line(s) as originally parsed.

G. `TEST` render SHALL produce the `# Tests:` or `# Validates:` comment line(s) as originally parsed.

H. `TEST_RESULT` render SHALL raise `ValueError` as test results are read-only and not rendered back to disk.

I. Rendering a FILE node SHALL walk its CONTAINS children sorted by `render_order` edge metadata, call render on each, and concatenate the results with appropriate line separators to produce the complete file content.

J. Requirement hash computation SHALL use order-independent assertion hashing: compute each assertion's normalized text hash individually, sort the hashes lexicographically, then hash the sorted collection into the requirement's final hash.

## Rationale

The render protocol is the inverse of parsing: each node kind knows how to serialize itself back to text. This enables the graph to reconstruct files from its internal state, which is the foundation for render-based persistence. Order-independent assertion hashing ensures that assertion reordering does not trigger false change-detection flags.

*End* *Render Protocol for Graph Nodes* | **Hash**: cc025b1a
---

## REQ-d00132: Render-Based Save Operation

**Level**: DEV | **Status**: Draft | **Implements**: REQ-p00050

`save_mutations()` SHALL write dirty FILE nodes to disk by rendering their CONTAINS children. `persistence.py` is replaced entirely by render-based serialization.

## Assertions

A. `save_mutations()` SHALL identify dirty FILE nodes by walking the mutation log to find which FILE nodes contain mutated content nodes, then render each dirty FILE node to produce the file content and write it to disk.

B. Safety branches SHALL be created before writing when `save_branch=True`, using the existing `create_safety_branch()` mechanism.

C. After saving, the graph SHALL be rebuilt from disk and compared to the pre-save in-memory graph as a consistency check. This check SHALL be on by default and skippable via configuration.

D. `persistence.py` SHALL be deleted and replaced entirely by the render-based save mechanism.

E. The mutation log and undo system SHALL continue to work unchanged. The mutation log SHALL be cleared after a successful save.

F. The render-based save SHALL derive implements and refines reference lists from the live graph edges rather than stored fields, ensuring edge mutations are correctly reflected in the output.

## Rationale

Render-based save replaces the brittle text surgery in persistence.py with graph-native serialization. Each FILE node renders its content from the graph, making the graph the single source of truth. The consistency check (rebuild + compare) proves round-trip fidelity.

*End* *Render-Based Save Operation* | **Hash**: 7043f7af
---

## REQ-d00134: Comprehensive Mutation Round-Trip Scenario Test

**Level**: DEV | **Status**: Draft | **Implements**: REQ-d00132

The system SHALL pass a comprehensive end-to-end scenario test that exercises all mutation types through the Flask API layer, saves to disk, reloads, and verifies round-trip fidelity.

## Assertions

A. The scenario test SHALL exercise at least 50 mutation operations across all mutation types (status, title, assertion CRUD, edge CRUD, requirement CRUD, undo) in a single deterministic run.

B. The scenario test SHALL build a starting fixture with at least 6 requirements across all three levels (PRD, OPS, DEV) with proper hierarchy and assertions.

C. The scenario test SHALL verify intermediate graph state at multiple checkpoints during the mutation sequence, not just at the end.

D. The scenario test SHALL save to disk via the Flask API, then reload from saved files and verify that the reloaded graph matches expected state for all surviving requirements, assertions, and edges.

E. The scenario test SHALL perform a second round of mutations after reload and verify a second save-reload cycle produces correct results.

F. The scenario test SHALL exercise undo operations at various points and verify that undone mutations are properly reverted in the final saved state.

## Rationale

A single large scenario test that exercises the full mutation API in a realistic sequence provides confidence that mutation operations compose correctly and that the render-save-reload pipeline is faithful. This complements the existing per-mutation-type unit tests with a holistic integration test.

*End* *Comprehensive Mutation Round-Trip Scenario Test* | **Hash**: 4772cbb4
---

## REQ-d00200: FederatedGraph Read-Only Delegation

**Level**: DEV | **Status**: Draft | **Implements**: REQ-p00050, REQ-p00005

FederatedGraph SHALL wrap one or more TraceGraph instances, each paired with its own configuration and repo root, delegating all read-only TraceGraph methods with documented federation strategies.

## Assertions

A. FederatedGraph SHALL wrap one or more TraceGraph instances via RepoEntry dataclass containing: name, graph (TraceGraph | None), config (ConfigLoader | None), repo_root (Path), git_origin (str | None), error (str | None).

B. FederatedGraph.from_single() classmethod SHALL create a federation-of-one from a single TraceGraph, config, and repo_root, using "root" as the default repo name.

C. All read-only TraceGraph public methods SHALL be explicitly implemented on FederatedGraph with a strategy comment (by_id, aggregate, or special).

D. by_id strategy methods (find_by_id, has_root) SHALL look up the owning graph via an internal ownership mapping and delegate to the correct sub-graph.

E. aggregate strategy methods (iter_roots, all_nodes, node_count, root_count, iter_by_kind, nodes_by_kind, all_connected_nodes, orphaned_nodes, has_orphans, orphan_count, broken_references, has_broken_references, iter_unlinked, iter_structural_orphans, deleted_nodes, has_deletions) SHALL combine results from all sub-graphs.

F. Aggregate methods SHALL skip repos with graph set to None (error-state repos).

G. repo_for(node_id) SHALL return the RepoEntry for the graph owning that node. config_for(node_id) SHALL return the config for that node's owning repo.

H. iter_repos() SHALL yield all RepoEntry objects including error-state repos.

## Rationale

FederatedGraph provides config isolation for multi-repo builds while presenting a unified API to consumers. The federation-of-one pattern ensures all code paths go through FederatedGraph, preventing accidental direct TraceGraph usage. Error-state repos (missing associates) are represented in the federation but skipped during aggregation, preserving graceful degradation.

*End* *FederatedGraph Read-Only Delegation* | **Hash**: 00000000
---

## REQ-d00201: FederatedGraph Mutation Delegation

**Level**: DEV | **Status**: Draft | **Implements**: REQ-p00050, REQ-d00200

FederatedGraph SHALL delegate all mutation operations to the appropriate sub-graph, maintain a unified mutation log across repos, and update internal ownership when IDs change.

## Assertions

A. by_id mutation methods (rename_node, update_title, change_status, delete_requirement, add_assertion, delete_assertion, update_assertion, rename_assertion, rename_file, fix_broken_reference) SHALL look up the owning repo via `_ownership`, delegate to the sub-graph, and update `_ownership` when IDs change.

B. FederatedGraph SHALL maintain a unified mutation log that records lightweight entries pointing to the repo name and sub-graph mutation ID, providing chronological ordering across all repos.

C. undo_last() SHALL read the federated log to identify which repo was last mutated, then delegate undo to that sub-graph. undo_to() SHALL undo back to a specific mutation ID across repos.

D. add_requirement SHALL accept a target_repo parameter to specify which sub-graph receives the new node. If omitted for federation-of-one, it SHALL default to the root repo.

E. Cross-graph mutation methods (add_edge, delete_edge, change_edge_kind, change_edge_targets, move_node_to_file) SHALL resolve source and target repos independently.

F. The mutation_log property SHALL return a log object whose iter_entries() yields full MutationEntry objects from sub-graphs in federated chronological order, compatible with existing consumers.

G. clone() SHALL perform federation-aware deep copy: deep-copy each sub-graph independently, then rebuild cross-graph edges and the ownership map.

## Rationale

Mutation delegation preserves TraceGraph's existing mutation+undo logic while adding federation awareness. The lightweight federated log avoids duplicating MutationEntry data. Ownership tracking ensures by_id lookups remain O(1) after mutations.

*End* *FederatedGraph Mutation Delegation* | **Hash**: 00000000
---

## REQ-d00202: Associates Config Loading

**Level**: DEV | **Status**: Draft | **Implements**: REQ-p00005

The config system SHALL parse `[associates.<name>]` sections from `.elspais.toml` to declare federated repository associations.

## Assertions

A. `get_associates_config(config)` SHALL read `[associates]` sections and return a `dict[str, dict]` mapping associate name to `{path: str, git: str | None}`.

B. The `path` field SHALL be required for each associate. The `git` field SHALL be optional (for clone assistance).

C. When no `[associates]` section exists in config, `get_associates_config()` SHALL return an empty dict.

D. Associates declaring their own `[associates]` section SHALL be a hard error: "Associate 'X' declares its own associates -- only the root repo may declare associates."

## Rationale

Associates are declared in the root repo's `.elspais.toml` using a structured TOML section. Each associate specifies a relative filesystem path and optional git remote URL. Transitive federation (associates of associates) is disallowed to keep the topology simple and predictable.

*End* *Associates Config Loading* | **Hash**: 00000000
---

## REQ-d00203: Multi-Repo Build Pipeline

**Level**: DEV | **Status**: Draft | **Implements**: REQ-p00005, REQ-d00200

The `build_graph()` factory SHALL build separate TraceGraph instances per repository when associates are configured, constructing a multi-repo FederatedGraph.

## Assertions

A. When `[associates]` config is present, `build_graph()` SHALL create a separate `TraceGraph` per associate repo, each with its own config-derived resolver.

B. Each associate's config SHALL be loaded from its own `.elspais.toml` and validated for transitive associates before building.

C. Missing associate paths SHALL produce error-state `RepoEntry` with `graph=None` and a descriptive `error` message (soft fail).

D. A `strict` parameter on `build_graph()` SHALL cause missing associates to raise an error instead of soft-failing.

E. The root repo and all valid associates SHALL be combined into a single `FederatedGraph` with the root repo as `_root_repo`.

## Rationale

Per-repo building ensures config isolation: each repo's hierarchy rules, format rules, and hash mode apply only to its own nodes. Error-state entries preserve visibility of missing associates in health reports without blocking the build.

*End* *Multi-Repo Build Pipeline* | **Hash**: 00000000

## REQ-d00204: Per-Repo Health Check Delegation

**Level**: DEV | **Status**: Draft | **Implements**: REQ-p00002, REQ-d00200

Health checks that depend on per-repo configuration SHALL run once per federated repo using that repo's own config, ensuring config isolation in multi-repo federations.

## Assertions

A. Config-sensitive health checks (hierarchy levels, format rules, reference resolution, structural orphans, changelog checks) SHALL run per-repo using each repo's own `ConfigLoader` from `RepoEntry.config`.

B. Non-config-sensitive health checks (file parseability, duplicate IDs, hash integrity, index staleness) SHALL run once on the full `FederatedGraph`.

C. Per-repo check results SHALL be merged into a single `HealthCheck` per check type, with `HealthFinding` entries annotated with a `repo` field identifying the source repository.

D. `HealthFinding` SHALL support an optional `repo` field (str | None) for per-repo attribution.

E. `check_broken_references` SHALL distinguish within-repo broken references (error severity) from cross-repo broken references where the target repo is in error state (warning severity with clone assistance info).

F. `run_spec_checks` SHALL accept a `FederatedGraph` and iterate `iter_repos()` for config-sensitive checks, using `FederatedGraph.from_single()` to create per-repo sub-federations.

## Rationale

Without per-repo delegation, all nodes are validated against the root repo's config. When repos have different hierarchy rules, format rules, or changelog policies, this produces false positives (root config rejects valid associate nodes) or false negatives (root config allows invalid associate nodes). Per-repo delegation ensures each repo is validated by its own rules.

*End* *Per-Repo Health Check Delegation* | **Hash**: 00000000
---
