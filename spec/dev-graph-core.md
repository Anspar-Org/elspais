# Graph Core Development Requirements

## REQ-d00050: Node Annotator Functions

**Level**: dev | **Status**: Active | **Implements**: REQ-o00051

The `core/annotators.py` module SHALL provide standalone annotator functions for enriching graph nodes.

## Assertions

A. Graph nodes SHALL carry git state annotations (is_uncommitted, is_moved, is_new) in node.metrics.

B. Graph nodes SHALL carry display metadata (is_roadmap, display_filename, repo_prefix) in node.metrics.

C. Graph nodes SHALL carry implementation file references in node.metrics.

D. Annotator functions SHALL only operate on REQUIREMENT nodes (skip other node kinds).

E. Annotator functions SHALL be idempotent - calling twice produces same result.

## Rationale

Per-node annotators enable fine-grained control over which annotations are applied and when.

## Changelog

- 2026-04-23 | 8ca0389e | - | Developer (dev@example.com) | Auto-fix: add missing changelog section

*End* *Node Annotator Functions* | **Hash**: 8ca0389e
---

## REQ-d00051: Graph Aggregate Functions

**Level**: dev | **Status**: Active | **Implements**: REQ-o00051, REQ-p00050

The `core/annotators.py` module SHALL provide aggregate functions that compute statistics from annotated graphs.

## Assertions

A. The system SHALL provide aggregate requirement counts by level (PRD/OPS/DEV) with active/all breakdown.

B. The system SHALL provide aggregate requirement counts by repository prefix.

C. The system SHALL provide total implementation file count.

D. The system SHALL provide a sorted list of unique topics derived from file names.

E. The system SHALL provide per-requirement coverage status (Full/Partial/Unimplemented) from node.metrics.

F. Aggregate functions SHALL NOT duplicate iteration - they SHALL use graph.all_nodes().

## Rationale

Aggregate functions provide reusable statistics computation that any output format can use.

## Changelog

- 2026-04-23 | 97c0f6fc | - | Developer (dev@example.com) | Auto-fix: add missing changelog section

*End* *Graph Aggregate Functions* | **Hash**: 97c0f6fc
---

## REQ-d00052: Output Generators Consume Graph Directly

**Level**: dev | **Status**: Active | **Implements**: REQ-p00050

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

## Changelog

- 2026-04-23 | a3575fcc | - | Developer (dev@example.com) | Auto-fix: add missing changelog section

*End* *Output Generators Consume Graph Directly* | **Hash**: a3575fcc
---

## REQ-d00054: Annotation Pipeline Pattern

**Level**: dev | **Status**: Active | **Implements**: REQ-o00051

Output generators SHALL follow a standard annotation pipeline pattern.

## Assertions

A. The pipeline SHALL be: parse -> build graph -> annotate nodes -> generate output.

## Rationale

A standard pipeline ensures consistent annotation across all output formats and simplifies debugging.

## Changelog

- 2026-04-23 | 0256df47 | - | Developer (dev@example.com) | Auto-fix: add missing changelog section

*End* *Annotation Pipeline Pattern* | **Hash**: 0256df47
---

## REQ-d00055: Node Metrics as Extension Point

**Level**: dev | **Status**: Active | **Implements**: REQ-o00051

TraceNode.metrics SHALL be the single extension point for adding data to nodes.

## Assertions

A. All annotation data SHALL be stored in node.metrics dict.

B. Annotators SHALL NOT modify node.children, node.parents, or other structural fields.

C. Metrics keys SHALL use consistent naming (snake_case, descriptive names).

D. Standard metrics keys SHALL include: is_uncommitted, is_moved, is_new, is_roadmap, display_filename, repo_prefix, implementation_files, referenced_pct.

E. Custom metrics MAY be added by specific annotators without modifying TraceNode class.

## Rationale

Using metrics dict as the extension point enables adding new annotations without modifying the core TraceNode dataclass.

## Changelog

- 2026-04-23 | 0073a9c3 | - | Developer (dev@example.com) | Auto-fix: add missing changelog section

*End* *Node Metrics as Extension Point* | **Hash**: 0073a9c3
---

## REQ-d00069: Indirect Coverage Source

**Level**: dev | **Status**: Active | **Implements**: REQ-o00051

The coverage annotation system SHALL support an INDIRECT coverage source for whole-requirement tests that do not target specific assertions.

## Assertions

A. `CoverageSource` enum SHALL include an `INDIRECT` value representing whole-requirement test coverage.

B. `RollupMetrics` SHALL track `indirect_referenced_pct` as a separate percentage alongside strict `referenced_pct`.

C. `RollupMetrics` SHALL track `validated_with_indirect` count for assertions validated when including INDIRECT sources.

D. `RollupMetrics.finalize()` SHALL compute `indirect_referenced_pct` by including INDIRECT contributions alongside DIRECT, EXPLICIT, and INFERRED sources.

E. The coverage annotator SHALL emit INDIRECT contributions for all *Assertion* labels when a TEST edge has empty `assertion_targets`.

F. When a whole-requirement test has passing results, the annotator SHALL count all assertions as validated for indirect mode.

G. A leaf *Assertion* SHALL be defined as any *Assertion* that has no `Refines:` child pointing at it. Leaf assertions can occur at any level or place in the hierarchy.

H. When a requirement declares `Satisfies: X`, the graph builder SHALL clone the template's REQ subtree with composite IDs (`declaring_id::original_id`), creating INSTANCE nodes linked to the declaring requirement via a SATISFIES edge. Coverage SHALL be computed through the standard coverage mechanism operating on the cloned nodes.

I. 100% coverage of a template instance SHALL be achieved when every leaf *Assertion* in the cloned template subtree (excluding N/A assertions) has at least one `Implements:` reference.

J. A `Refines:` relationship SHALL NOT count as coverage in itself, but coverage of its child assertions SHALL propagate upward. An *Assertion* with `Refines:` children SHALL have fractional coverage equal to the proportion of its covered leaf descendants.

K. The system SHALL report coverage gaps on template instance nodes through the standard coverage mechanisms. Instance nodes are normal graph nodes and participate in existing health checks.

## Rationale

Whole-requirement tests (e.g., `test_implements_req_d00087` with no *Assertion* suffix) currently contribute zero *Assertion* coverage. Adding INDIRECT as a separate source allows a "progress indicator" view alongside strict *Traceability*, following the same pattern as INFERRED coverage for requirement-to-requirement relationships.

## Changelog

- 2026-03-30 | e9b5c3f1 | - | Michael Lewis (michael@anspar.org) | Auto-fix: canonicalize term forms

*End* *Indirect Coverage Source* | **Hash**: e9b5c3f1
---

## REQ-d00070: Indirect Coverage Toggle Display

**Level**: dev | **Status**: Active | **Implements**: REQ-p00006

The interactive trace view SHALL provide a toggle to switch between strict and indirect coverage display modes.

## Assertions

A. `TreeRow` SHALL include a `coverage_indirect` attribute computed from `indirect_referenced_pct` using the same thresholds as strict coverage (0=none, <100=partial, 100=full).

B. The template SHALL render a `data-coverage-indirect` attribute on each requirement row.

C. The template SHALL include a toggle control in the filter bar area to switch between strict and indirect coverage views.

D. The default display SHALL show strict coverage (toggle OFF).

E. The `has_failures` warning indicator SHALL display regardless of toggle state.

## Rationale

Users need both a strict *Traceability* view (only *Assertion*-targeted tests count) and a progress indicator view (whole-requirement tests cover all assertions). A toggle lets users switch between modes without regenerating the trace.

## Changelog

- 2026-03-30 | 3e5b1766 | - | Michael Lewis (michael@anspar.org) | Auto-fix: canonicalize term forms

*End* *Indirect Coverage Toggle Display* | **Hash**: 3e5b1766
---

## REQ-d00071: Unified Root vs Orphan Classification

**Level**: dev | **Status**: Active | **Implements**: REQ-o00050, REQ-p00002

The graph builder SHALL distinguish between root nodes and orphan nodes using a unified classification based on meaningful children.

## Assertions

A. The graph builder SHALL classify a parentless node as a root only when it has at least one child whose kind is not a satellite kind.

B. The graph builder SHALL classify a parentless node as an orphan when it has no children whose kind is not a satellite kind.

C. Satellite node kinds SHALL be configurable via `[graph].satellite_kinds` in `.elspais.toml`, defaulting to *Assertion* and TEST_RESULT.

D. USER_JOURNEY nodes SHALL follow the same root vs orphan classification rules as REQUIREMENT nodes.

## Rationale

Currently, all parentless REQUIREMENTs and all USER_JOURNEYs are unconditionally treated as roots, even when disconnected from the rest of the graph. A PRD with only assertions but no OPS/DEV implementations is effectively orphaned — it anchors no subgraph. Unifying the classification rule across all node kinds simplifies the logic and produces more accurate orphan detection.

## Changelog

- 2026-03-30 | 4bd239f1 | - | Michael Lewis (michael@anspar.org) | Auto-fix: canonicalize term forms

*End* *Unified Root vs Orphan Classification* | **Hash**: 4bd239f1
---

## REQ-d00072: Link Suggestion Core Engine

**Level**: dev | **Status**: Active | **Implements**: REQ-o00065

The `graph/link_suggest.py` module SHALL implement the link suggestion scoring pipeline using existing graph analysis building blocks.

## Assertions

A. The suggestion engine SHALL orchestrate all heuristics and return deduplicated suggestions sorted by confidence descending, supporting optional file path and limit filters.

B. The suggestion engine SHALL extract meaningful keywords from test node metadata (function name, class name, file path, docstring), filter stopwords and short tokens, and produce a query string for *Assertion* matching.

C. Deduplication SHALL merge suggestions for the same (test, requirement) pair, keeping the highest confidence and combining reasons.

## Rationale

The core engine composes existing building blocks into a scoring pipeline. Each heuristic reuses proven code rather than reimplementing analysis logic.

## Changelog

- 2026-03-30 | 95f09aea | - | Michael Lewis (michael@anspar.org) | Auto-fix: canonicalize term forms

*End* *Link Suggestion Core Engine* | **Hash**: 95f09aea
---

## REQ-d00215: Keyword Extraction Annotator

**Level**: dev | **Status**: Active | **Implements**: REQ-o00051

## Assertions

A. The keyword extractor SHALL tokenize text into lowercase words, filtering stopwords, short words (fewer than 3 characters), and punctuation, returning a deduplicated list.

B. The keyword annotator SHALL extract keywords from a node's title, body, and *Assertion* text, storing them in the node's keyword field.

C. The keyword annotator SHALL operate on all node kinds with textual content, not only requirements.

D. Keyword search SHALL return nodes matching given keywords with case-insensitive comparison.

E. Keyword collection SHALL return a sorted, deduplicated list of all keywords across the graph.

## Changelog

- 2026-03-30 | ebe57660 | - | Michael Lewis (michael@anspar.org) | Auto-fix: canonicalize term forms

*End* *Keyword Extraction Annotator* | **Hash**: ebe57660

## REQ-d00216: TraceGraph Deep Clone

**Level**: dev | **Status**: Active | **Implements**: REQ-p00050

## Assertions

A. The graph clone operation SHALL create a fully independent deep copy such that mutations to the clone do not affect the original.

B. The clone SHALL preserve all node data including IDs, content fields, and metrics.

C. The clone SHALL preserve all edges including parent-child relationships and edge kinds.

D. The clone SHALL preserve the root set, maintaining iteration equivalence with the original.

E. The clone SHALL preserve graph-level metadata such as repository root.

F. The clone SHALL handle DAG structures with multiple parents without infinite recursion.

## Changelog

- 2026-04-23 | a007d5ed | - | Developer (dev@example.com) | Auto-fix: add missing changelog section

*End* *TraceGraph Deep Clone* | **Hash**: a007d5ed
