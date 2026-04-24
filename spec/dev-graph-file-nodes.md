# Graph FILE Node Development Requirements

## REQ-d00126: FILE Node Data Model

**Level**: dev | **Status**: Active | **Implements**: REQ-p00050

The graph data model SHALL support FILE nodes and file-aware edge kinds for representing source file structure in the *Traceability* graph.

## Assertions

A. `NodeKind` enum SHALL include a `FILE` value with string representation `"file"`.

B. A `FileType` enum SHALL exist alongside `NodeKind` with values: `SPEC`, `JOURNEY`, `CODE`, `TEST`, `RESULT`.

C. `EdgeKind` enum SHALL include `STRUCTURES`, `DEFINES`, and `YIELDS` values for file-aware structural edges.

D. `STRUCTURES`, `DEFINES`, and `YIELDS` edge kinds SHALL NOT contribute to coverage (i.e., `contributes_to_coverage()` returns `False`).

E. `Edge` dataclass SHALL have a `metadata: dict[str, Any]` field defaulting to an empty dict, excluded from `__eq__` and `__hash__` comparisons.

## Rationale

FILE nodes are the foundation for representing source files as first-class graph participants. The new edge kinds (STRUCTURES, DEFINES, YIELDS) enable domain-internal hierarchy, virtual node provenance, and test-result linking. Edge metadata carries mutable annotations (line ranges, render order) without affecting edge identity.

## Changelog

- 2026-03-30 | 664d3990 | - | Michael Lewis (michael@anspar.org) | Auto-fix: canonicalize term forms

*End* *FILE Node Data Model* | **Hash**: 664d3990
---

## REQ-d00127: GraphNode API: Filtered Traversal and Edge-Only Relationships

**Level**: dev | **Status**: Active | **Implements**: REQ-p00050

GraphNode SHALL use edge-only relationships (via `link()`) and support filtered traversal by edge kind, eliminating the edge-less `add_child()` mechanism.

## Assertions

A. `GraphNode` SHALL NOT have an `add_child()` method. All parent-child relationships SHALL be created via `link()` with a typed `EdgeKind`.

B. `GraphNode.remove_child()` SHALL be renamed to `unlink()`, retaining identical behavior: severs all edges between two nodes and removes cache entries.

C. `iter_children()`, `iter_parents()`, `walk()`, and `ancestors()` SHALL accept an optional `edge_kinds` parameter. When provided, only nodes reachable via the specified edge kinds are returned. When `None` (default), all nodes are returned (backwards compatible).

D. `GraphNode.file_node()` SHALL walk incoming edges upward to find the nearest ancestor with `kind == NodeKind.FILE`, returning `None` if no FILE ancestor exists.

E. TEST_RESULT nodes SHALL be linked from TEST nodes via `EdgeKind.YIELDS` (TEST -> TEST_RESULT direction), not via `EdgeKind.CONTAINS`.

## Rationale

Eliminating `add_child()` ensures every relationship in the graph has a typed edge, enabling filtered traversal. The `file_node()` convenience method provides efficient navigation to FILE ancestors. Renaming `remove_child()` to `unlink()` creates API symmetry with `link()`. The YIELDS edge kind correctly models the TEST->TEST_RESULT relationship.

## Changelog

- 2026-04-23 | 12964863 | - | Developer (dev@example.com) | Auto-fix: add missing changelog section

*End* *GraphNode API: Filtered Traversal and Edge-Only Relationships* | **Hash**: 12964863
---

## REQ-d00128: FILE Node Creation in Build Pipeline

**Level**: dev | **Status**: Active | **Implements**: REQ-p00050

The build pipeline SHALL create FILE nodes for every scanned file and wire CONTAINS edges from FILE to top-level content nodes, with RemainderParser mandatory for text-based file types.

## Assertions

A. `factory.py` SHALL create a FILE node with ID `file:<repo-relative-path>` for every scanned file before parsing its content.

B. FILE node content fields SHALL include: `file_type` (FileType enum), `absolute_path` (str), `relative_path` (str), `repo` (str or None), `git_branch` (str or None), `git_commit` (str or None).

C. `git_branch` and `git_commit` SHALL be captured once per repository, not per file.

D. `GraphBuilder.add_parsed_content()` SHALL accept an optional `file_node` parameter and wire CONTAINS edges from the FILE node to top-level content nodes (REQUIREMENT, USER_JOURNEY, file-level REMAINDER, CODE, TEST).

E. CONTAINS edge metadata SHALL include `start_line` (int), `end_line` (int or None), and `render_order` (float, sequential from 0.0).

F. *Assertion* and requirement-level REMAINDER nodes SHALL NOT receive CONTAINS edges from FILE; they are reached via STRUCTURES edges from their parent REQUIREMENT.

G. RemainderParser SHALL be mandatory for SPEC, JOURNEY, CODE, and TEST file types, ensuring every line is claimed by some parser.

H. RemainderParser SHALL NOT be registered for RESULT file types.

I. FILE nodes SHALL be additive: existing graph behavior (*Traceability*, coverage, root/orphan detection) SHALL remain unaffected.

J. Template instantiation (`_instantiate_satisfies_templates()`) SHALL create DEFINES edges from the declaring requirement's FILE node to each INSTANCE node in the cloned subtree.

K. INSTANCE nodes SHALL NOT have CONTAINS edges. They are virtual nodes not physically present in any file.

L. `file_node()` SHALL return None for INSTANCE nodes. To find the originating file, navigate via the INSTANCE edge to the original node and call `file_node()` on it.

## Rationale

FILE nodes make source files first-class graph participants. Creating them in factory.py (which knows the file path and type) rather than the deserializer maintains separation of concerns. CONTAINS edges with line-range metadata enable file-level operations. RemainderParser ensures complete line coverage for text-based files. DEFINES edges from FILE to INSTANCE nodes establish provenance for virtual nodes created by template instantiation.

## Changelog

- 2026-03-30 | 7742f15f | - | Michael Lewis (michael@anspar.org) | Auto-fix: canonicalize term forms

*End* *FILE Node Creation in Build Pipeline* | **Hash**: 7742f15f
---

## REQ-d00129: SourceLocation Removal and Consumer Migration

**Level**: dev | **Status**: Active | **Implements**: REQ-p00050

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

## Changelog

- 2026-04-23 | 8bd81196 | - | Developer (dev@example.com) | Auto-fix: add missing changelog section

*End* *SourceLocation Removal and Consumer Migration* | **Hash**: 8bd81196
---

## REQ-d00130: Parameterized Root Iteration and Kind-Based Index Query

**Level**: dev | **Status**: Active | **Implements**: REQ-p00050

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

## Changelog

- 2026-04-23 | f56f8527 | - | Developer (dev@example.com) | Auto-fix: add missing changelog section

*End* *Parameterized Root Iteration and Kind-Based Index Query* | **Hash**: f56f8527
---

## REQ-d00131: Render Protocol for Graph Nodes

**Level**: dev | **Status**: Active | **Implements**: REQ-p00050

Each domain NodeKind SHALL have a render function that produces its text representation. Walking a FILE node's CONTAINS children in render_order and concatenating their rendered output SHALL produce the file's content.

## Assertions

A. Each `NodeKind` SHALL have a `render()` function that returns its text representation as a string, dispatched by kind.

B. `REQUIREMENT` render SHALL produce the full requirement block: header line (`## REQ-xxx: Title`), metadata line, body text, `## Assertions` heading with *Assertion* lines from STRUCTURES children, non-normative sections from STRUCTURES children, and `*End*` marker with hash.

C. `ASSERTION` nodes SHALL be rendered by their parent REQUIREMENT's render function, not independently. Calling render on an *Assertion* directly SHALL raise `ValueError`.

D. `REMAINDER` render SHALL return its raw text verbatim, preserving all whitespace and content exactly as parsed.

E. `USER_JOURNEY` render SHALL produce the full journey block including header, actor/goal fields, body, and end marker.

F. `CODE` render SHALL produce the `# Implements:` comment line(s) as originally parsed.

G. `TEST` render SHALL produce the `# Tests:` or `# Validates:` comment line(s) as originally parsed.

H. `TEST_RESULT` render SHALL raise `ValueError` as test results are read-only and not rendered back to disk.

I. Rendering a FILE node SHALL walk its CONTAINS children sorted by `render_order` edge metadata, call render on each, and concatenate the results with appropriate line separators to produce the complete file content.

J. Requirement hash computation SHALL use order-independent *Assertion* hashing: compute each *Assertion*'s normalized text hash individually, sort the hashes lexicographically, then hash the sorted collection into the requirement's final hash.

## Rationale

The render protocol is the inverse of parsing: each node kind knows how to serialize itself back to text. This enables the graph to reconstruct files from its internal state, which is the foundation for render-based persistence. Order-independent *Assertion* hashing ensures that *Assertion* reordering does not trigger false change-detection flags.

## Changelog

- 2026-03-30 | c004c62e | - | Michael Lewis (michael@anspar.org) | Auto-fix: canonicalize term forms

*End* *Render Protocol for Graph Nodes* | **Hash**: c004c62e
---

## REQ-d00132: Render-Based Save Operation

**Level**: dev | **Status**: Active | **Implements**: REQ-p00050

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

## Changelog

- 2026-04-23 | 7043f7af | - | Developer (dev@example.com) | Auto-fix: add missing changelog section

*End* *Render-Based Save Operation* | **Hash**: 7043f7af
---

## REQ-d00134: Comprehensive Mutation Round-Trip Scenario Test

**Level**: dev | **Status**: Active | **Implements**: REQ-d00132

The system SHALL pass a comprehensive end-to-end scenario test that exercises all mutation types through the Flask API layer, saves to disk, reloads, and verifies round-trip fidelity.

## Assertions

A. The scenario test SHALL exercise at least 50 mutation operations across all mutation types (status, title, *Assertion* CRUD, edge CRUD, requirement CRUD, undo) in a single deterministic run.

B. The scenario test SHALL build a starting fixture with at least 6 requirements across all three levels (PRD, OPS, DEV) with proper hierarchy and assertions.

C. The scenario test SHALL verify intermediate graph state at multiple checkpoints during the mutation sequence, not just at the end.

D. The scenario test SHALL save to disk via the Flask API, then reload from saved files and verify that the reloaded graph matches expected state for all surviving requirements, assertions, and edges.

E. The scenario test SHALL perform a second round of mutations after reload and verify a second save-reload cycle produces correct results.

F. The scenario test SHALL exercise undo operations at various points and verify that undone mutations are properly reverted in the final saved state.

## Rationale

A single large scenario test that exercises the full mutation API in a realistic sequence provides confidence that mutation operations compose correctly and that the render-save-reload pipeline is faithful. This complements the existing per-mutation-type unit tests with a holistic integration test.

## Changelog

- 2026-03-30 | be52daed | - | Michael Lewis (michael@anspar.org) | Auto-fix: canonicalize term forms

*End* *Comprehensive Mutation Round-Trip Scenario Test* | **Hash**: be52daed
---
