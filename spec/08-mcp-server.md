# MCP Server Specification

This document specifies the Model Context Protocol (MCP) server that exposes elspais functionality to AI agents. The MCP server is a pure interface layer that consumes the unified TraceGraph.

---

## REQ-p00060: MCP Server for AI-Driven Requirements Management

**Level**: prd | **Status**: Active | **Implements**: REQ-p00050

The elspais system SHALL provide an MCP server that enables AI agents to query, navigate, and mutate requirements through the unified TraceGraph.

## Assertions

A. The MCP server SHALL expose TraceGraph data through standardized MCP tools.

B. The MCP server SHALL consume TraceGraph directly without creating intermediate data structures, per REQ-p00050-B.

C. The MCP server SHALL provide read-only query tools for requirement discovery and navigation.

D. The MCP server SHALL provide mutation tools for AI-assisted requirement management.

E. The MCP server SHALL support undo operations for all graph mutations.

## Rationale

AI agents need programmatic access to requirements data for tasks like coverage analysis, requirement drafting, and traceability verification. The MCP protocol provides a standardized interface that works with multiple AI platforms.

*End* *MCP Server for AI-Driven Requirements Management* | **Hash**: 3ebc237a

---

## REQ-o00060: MCP Core Query Tools

**Level**: ops | **Status**: Active | **Implements**: REQ-p00060

The MCP server SHALL provide core query tools for graph inspection and requirement lookup.

## Assertions

A. `get_graph_status()` SHALL return graph staleness state, node counts by kind, and last refresh timestamp.

B. `refresh_graph(full)` SHALL force graph rebuild, with `full=True` clearing all caches.

C. `search(query, field, regex, limit)` SHALL search requirements by ID, title, body, or keyword content, supporting multi-term AND/OR queries with relevance scoring.

D. `get_requirement(req_id)` SHALL return full requirement details including assertions and relationships.

E. `get_hierarchy(req_id)` SHALL return ancestors and children for navigation.

F. All query tools SHALL read directly from TraceGraph nodes using the iterator-only API.

## Rationale

Core query tools enable AI agents to discover and explore requirements without modifying the graph. These are safe, read-only operations.

*End* *MCP Core Query Tools* | **Hash**: 73c31134

---

## REQ-o00061: MCP Workspace Context Tools

**Level**: ops | **Status**: Active | **Implements**: REQ-p00060

The MCP server SHALL provide workspace context tools that describe the current repository and project.

## Assertions

A. `get_workspace_info()` SHALL return repository path, project name, and configuration summary.

B. `get_project_summary()` SHALL return requirement counts by level, coverage statistics, and change metrics.

C. Workspace tools SHALL use graph aggregate functions from the annotators module, not recompute statistics.

D. Configuration data SHALL be read from the unified config system, not parsed separately.

## Rationale

AI agents need context about the workspace they're operating in to provide relevant assistance. Workspace tools answer "what repo am I serving?" and "what's the state of this project?"

*End* *MCP Workspace Context Tools* | **Hash**: 0aa9dff4

---

## REQ-o00062: MCP Graph Mutation Tools

**Level**: ops | **Status**: Active | **Implements**: REQ-p00060

The MCP server SHALL provide mutation tools for in-memory graph modifications with full undo support.

## Assertions

A. Node mutations SHALL include: rename, update_title, change_status, add_requirement, delete_requirement.

B. Assertion mutations SHALL include: add_assertion, update_assertion, delete_assertion, rename_assertion.

C. Edge mutations SHALL include: add_edge, change_edge_kind, change_edge_targets, delete_edge, fix_broken_reference.

D. All mutations SHALL delegate to TraceGraph mutation methods, not implement mutation logic directly.

E. All mutations SHALL return a MutationEntry for audit and undo.

F. Destructive operations (delete_*) SHALL require explicit `confirm=True` parameter.

G. `undo_last_mutation()` and `undo_to_mutation(id)` SHALL reverse mutations using graph.undo_last() and graph.undo_to().

## Rationale

In-memory mutations enable AI agents to draft requirement changes that can be reviewed before persisting. The undo system provides safety for exploratory editing.

*End* *MCP Graph Mutation Tools* | **Hash**: 064271fb

---

## REQ-o00063: MCP File Mutation Tools

**Level**: ops | **Status**: Active | **Implements**: REQ-p00060

The MCP server SHALL provide file mutation tools that persist changes to spec files on disk.

## Assertions

A. `change_reference_type(req_id, target_id, new_type)` SHALL modify Implements/Refines relationships in spec files.

B. `move_requirement(req_id, target_file)` SHALL relocate a requirement between spec files.

C. `transform_with_ai(req_id, prompt, save_branch)` SHALL use AI to rewrite requirement content.

D. File mutations SHALL create git safety branches when `save_branch=True`.

E. `restore_from_safety_branch(branch_name)` SHALL revert file changes from a safety branch.

F. After file mutations, `refresh_graph()` SHALL be called to synchronize the in-memory graph.

G. `modify_title(req_id, new_title)` SHALL modify a requirement's title text in its spec file.

H. `modify_assertion_text(req_id, label, new_text)` SHALL modify the text of an existing assertion in its spec file.

I. `add_assertion(req_id, label, text)` SHALL add a new assertion to a requirement in its spec file.

## Rationale

File mutations persist changes to the authoritative spec files. Git safety branches provide rollback capability for destructive operations.

*End* *MCP File Mutation Tools* | **Hash**: dee88649

---

## REQ-d00060: Graph Status Tool Implementation

**Level**: dev | **Status**: Active | **Implements**: REQ-o00060-A

The `get_graph_status()` tool SHALL report graph state using direct graph inspection.

## Assertions

A. SHALL return `is_stale` boolean from graph metadata, not recomputed.

B. SHALL return `node_counts` by calling `graph.nodes_by_kind()` for each NodeKind.

C. SHALL return `last_refresh` timestamp from graph metadata.

D. SHALL return `root_count` using `graph.root_count()`.

E. SHALL NOT iterate the full graph to count nodes when kind-specific counts suffice.

## Rationale

Graph status provides a quick health check without expensive traversal operations.

*End* *Graph Status Tool Implementation* | **Hash**: 4e2277cc

---

## REQ-d00061: Requirement Search Tool Implementation

**Level**: dev | **Status**: Active | **Implements**: REQ-o00060-C

The `search()` tool SHALL find requirements using graph iteration with filtering.

## Assertions

A. SHALL iterate `graph.nodes_by_kind(NodeKind.REQUIREMENT)` for requirement search.

B. SHALL support `field` parameter: "id", "title", "body", "keywords", or "all" (default).

C. SHALL support `regex=True` for regular expression matching.

D. SHALL return serialized requirement summaries, not full node objects.

E. SHALL limit results to prevent unbounded response sizes.

F. SHALL support multi-term AND queries where space-separated terms must all match in any searched field.

G. SHALL support `OR` operator for disjunctive matching between terms (e.g., `auth OR password`).

H. SHALL support parenthesized grouping `(...)` for explicit query precedence.

I. SHALL support quoted phrases `"..."` for exact contiguous substring matching.

J. SHALL support `-term` prefix for exclusion (nodes matching the term are filtered out).

K. SHALL support `=term` prefix for exact keyword set matching (vs default substring matching).

L. SHALL score results by field match quality (ID > title > keyword > body) and sort by relevance score descending.

M. SHALL include a `score` field in search results when multi-term scoring is applied.

## Rationale

Search enables AI agents to discover requirements by content without knowing exact IDs. Multi-term queries with AND/OR/NOT support, relevance scoring, and exact keyword matching allow both human users and AI agents to efficiently find requirements using natural search patterns like synonym lists or multi-concept queries.

*End* *Requirement Search Tool Implementation* | **Hash**: 0183195b

---

## REQ-d00062: Requirement Detail Tool Implementation

**Level**: dev | **Status**: Active | **Implements**: REQ-o00060-D

The `get_requirement()` tool SHALL return full requirement details from a single graph lookup.

## Assertions

A. SHALL use `graph.get_node(req_id)` for O(1) lookup.

B. SHALL return node fields: id, title, level, status, hash, body.

C. SHALL return assertions by iterating `node.iter_children()` filtered by NodeKind.ASSERTION.

D. SHALL return relationships by iterating `node.iter_outgoing_edges()`.

E. SHALL return metrics from `node.metrics` dict without recomputation.

F. SHALL return 404-equivalent error for non-existent requirements.

## Rationale

Single-requirement lookup is the most common operation. O(1) access via graph index is essential.

*End* *Requirement Detail Tool Implementation* | **Hash**: 51985ec1

---

## REQ-d00063: Hierarchy Navigation Tool Implementation

**Level**: dev | **Status**: Active | **Implements**: REQ-o00060-E

The `get_hierarchy()` tool SHALL return ancestors and children for tree navigation.

## Assertions

A. SHALL return `ancestors` by walking `node.iter_parents()` recursively to roots.

B. SHALL return `children` by iterating `node.iter_children()`.

C. SHALL return `siblings` by finding parent's other children.

D. SHALL include node summaries (id, title, level) not full details.

E. SHALL handle DAG structure where nodes may have multiple parents.

## Rationale

Hierarchy navigation enables AI agents to understand requirement context and relationships.

*End* *Hierarchy Navigation Tool Implementation* | **Hash**: 2b1d284b

---

## REQ-d00064: Serializer Functions

**Level**: dev | **Status**: Active | **Implements**: REQ-p00060-B

Serializer functions SHALL convert GraphNode data to JSON-safe dictionaries.

## Assertions

A. Summary serialization SHALL return id, title, level, status only.

B. Full serialization SHALL return all fields including body, assertions, edges.

C. Serializers SHALL read from `node.get_field()` and `node.metrics`, not access internal attributes.

D. Serializers SHALL handle missing fields gracefully with sensible defaults.

E. Serializers SHALL NOT trigger graph traversal beyond the single node being serialized.

## Rationale

Serializers provide the boundary between graph internals and MCP responses. They ensure consistent, safe data extraction.

*End* *Serializer Functions* | **Hash**: 8d56d937

---

## REQ-d00065: Mutation Tool Delegation

**Level**: dev | **Status**: Active | **Implements**: REQ-o00062-D

MCP mutation tools SHALL delegate to TraceGraph mutation methods.

## Assertions

A. Node rename mutations SHALL delegate to the graph's rename method.

B. Requirement creation mutations SHALL delegate to the graph's add method.

C. `mutate_delete_requirement(id, confirm)` SHALL call `graph.delete_requirement(id)` only if `confirm=True`.

D. Mutation tools SHALL NOT implement mutation logic - only parameter validation and delegation.

E. Mutation tools SHALL return the MutationEntry from the graph method for audit trail.

## Rationale

Delegation ensures mutation logic lives in one place (TraceGraph) and MCP is purely an interface layer.

*End* *Mutation Tool Delegation* | **Hash**: 5d1f7627

---

## REQ-o00064: MCP Test Coverage Analysis Tools

**Level**: ops | **Status**: Active | **Implements**: REQ-p00060

The MCP server SHALL provide test coverage analysis tools for identifying test-requirement relationships and coverage gaps.

## Assertions

A. `get_test_coverage(req_id)` SHALL return TEST nodes that reference the requirement and their TEST_RESULT nodes.

B. `get_uncovered_assertions(req_id=None)` SHALL identify assertions with no TEST node references.

C. `find_assertions_by_keywords(keywords, match_all)` SHALL search assertion text for keyword matches.

D. Coverage tools SHALL consume graph edges directly without caching or recomputation.

E. Coverage tools SHALL support filtering by requirement ID or scanning all requirements.

## Rationale

AI agents performing requirement analysis need to understand test coverage and identify gaps. These tools enable systematic coverage improvement workflows like those in Phase 7 of the master plan.

*End* *MCP Test Coverage Analysis Tools* | **Hash**: 82d8f37e

---

## REQ-d00066: Test Coverage Tool Implementation

**Level**: dev | **Status**: Active | **Implements**: REQ-o00064-A

The `get_test_coverage()` tool SHALL return test coverage information for a requirement.

## Assertions

A. SHALL accept `req_id` parameter identifying the target requirement.

B. SHALL return TEST nodes by finding nodes of kind TEST with edges pointing to the requirement.

C. SHALL return TEST_RESULT nodes linked to each TEST node.

D. SHALL identify covered assertions by examining edge `assertion_targets` attributes.

E. SHALL return uncovered assertions as those with no incoming TEST edges.

F. SHALL return coverage summary: total assertions, covered count, coverage percentage.

G. SHALL use `graph.nodes_by_kind(NodeKind.TEST)` and iterate edges, not traverse full graph.

## Rationale

Test coverage per requirement enables targeted test writing and gap analysis.

*End* *Test Coverage Tool Implementation* | **Hash**: 6ac6b51f

---

## REQ-d00067: Uncovered Assertions Tool Implementation

**Level**: dev | **Status**: Active | **Implements**: REQ-o00064-B

The `get_uncovered_assertions()` tool SHALL find assertions lacking test coverage.

## Assertions

A. SHALL accept optional `req_id` parameter; when None, scan all requirements.

B. SHALL iterate assertions using `graph.nodes_by_kind(NodeKind.ASSERTION)`.

C. SHALL check each assertion for incoming edges from TEST nodes.

D. SHALL return assertion details: id, text, label, parent requirement context.

E. SHALL return parent requirement id and title for context.

F. SHALL limit results to prevent unbounded response sizes.

## Rationale

Finding uncovered assertions enables systematic test coverage improvement across the project.

*End* *Uncovered Assertions Tool Implementation* | **Hash**: 7044d63d

---

## REQ-d00068: Assertion Keyword Search Tool Implementation

**Level**: dev | **Status**: Active | **Implements**: REQ-o00064-C

The `find_assertions_by_keywords()` tool SHALL search assertion text for keyword matches.

## Assertions

A. SHALL accept `keywords` list parameter with search terms.

B. SHALL accept `match_all` boolean; True requires all keywords, False requires any keyword.

C. SHALL search assertion text (the SHALL statement content) for keyword matches.

D. SHALL return assertion id, text, label, and parent requirement context.

E. SHALL perform case-insensitive matching by default.

F. SHALL complement `find_by_keywords()` which searches requirement titles, not assertion text.

## Rationale

Assertion keyword search enables AI agents to find assertions related to specific concepts when linking tests to requirements.

*End* *Assertion Keyword Search Tool Implementation* | **Hash**: c9d5ad87

---

## REQ-d00074: MCP Link Suggestion Tools

**Level**: dev | **Status**: Active | **Implements**: REQ-o00064, REQ-o00065-D

The MCP server SHALL provide link suggestion tools that expose the suggestion engine to AI agents.

## Assertions

A. `suggest_links(file_path?, limit?)` SHALL return structured link suggestions from the core engine, including source node, target requirement, confidence, and reason.

B. `apply_link(file_path, line, requirement_id)` SHALL insert a `# Implements:` comment at the specified file location and refresh the graph afterward.

C. Link suggestion tools SHALL consume the graph read-only via the core engine, not implement analysis logic directly.

D. `apply_link()` SHALL validate that the target requirement exists in the graph before modifying files.

## Rationale

MCP exposure enables AI agents to discover and apply link suggestions during coding sessions, completing the workflow: discover gaps -> get suggestions -> apply links.

*End* *MCP Link Suggestion Tools* | **Hash**: e438ff5e

---

## REQ-o00067: MCP Subtree Extraction Tool

**Level**: ops | **Status**: Active | **Implements**: REQ-p00060

The MCP server SHALL provide a subtree extraction tool for scoped subgraph retrieval.

## Assertions

A. `get_subtree(root_id, depth, include_kinds, format)` SHALL extract a subgraph rooted at a given node using BFS traversal.

B. The subtree tool SHALL support depth limiting where `depth=0` means unlimited and `depth=N` limits to N levels from root.

C. The subtree tool SHALL support kind filtering via `include_kinds` parameter with conservative defaults per root kind.

D. The subtree tool SHALL support three output formats: `markdown`, `flat`, and `nested`.

E. The subtree tool SHALL deduplicate nodes in DAG structures using a visited set.

F. The subtree tool SHALL include coverage summary statistics for requirement nodes.

## Rationale

LLM agents need scoped requirement subsets for sub-agent consumption. Extracting a subtree avoids context pollution from the full graph.

*End* *MCP Subtree Extraction Tool* | **Hash**: ab29e315

---

## REQ-o00068: MCP Cursor Protocol

**Level**: ops | **Status**: Active | **Implements**: REQ-p00060

The MCP server SHALL provide a general-purpose cursor protocol for incremental iteration over read query results.

## Assertions

A. `open_cursor(query, params, batch_size)` SHALL materialize query results and return the first item with metadata.

B. `cursor_next(count)` SHALL return the next `count` items and advance the cursor position.

C. `cursor_info()` SHALL return cursor position, total count, and remaining count without advancing.

D. The cursor protocol SHALL support a single active cursor, with opening a new cursor auto-closing the previous.

E. The cursor protocol SHALL support `batch_size` semantics: `-1` for assertions as first-class items, `0` for nodes with inline assertions, `1` for nodes with children previews.

F. The cursor protocol SHALL support query types: `subtree`, `search`, `hierarchy`, `query_nodes`, `test_coverage`, `uncovered_assertions`, `scoped_search`.

## Rationale

LLMs benefit from incremental exploration of results, deciding when to stop rather than receiving everything at once. A cursor protocol enables this without modifying existing read tools.

*End* *MCP Cursor Protocol* | **Hash**: 743877c3

---

## REQ-d00075: Subtree Extraction Implementation

**Level**: dev | **Status**: Active | **Implements**: REQ-o00067

The subtree extraction tool SHALL be implemented as MCP-layer helpers that consume the graph iterator API.

## Assertions

A. Subtree collection SHALL perform BFS traversal with depth tracking and a visited set for DAG deduplication.

B. Coverage summaries SHALL include total, covered, and percentage values, reusing existing coverage computation.

C. Markdown format SHALL render indented headings with assertion bullets and coverage stats.

D. Flat format SHALL return root_id, nodes, edges, and stats as a JSON-safe structure.

E. Nested format SHALL return recursive JSON with `children` arrays.

F. Conservative kind defaults SHALL include `REQUIREMENT` + `ASSERTION` for requirement roots, and `USER_JOURNEY` for journey roots.

G. The implementation SHALL NOT modify Graph, GraphTrace, or GraphBuilder structures.

## Rationale

BFS with depth tracking and kind filtering provides the flexible subtree extraction that `GraphNode.walk()` alone cannot deliver, while staying in the MCP layer.

*End* *Subtree Extraction Implementation* | **Hash**: 769a6d75

---

## REQ-d00076: Cursor Protocol Implementation

**Level**: dev | **Status**: Active | **Implements**: REQ-o00068

The cursor protocol SHALL be implemented as a `CursorState` dataclass with three MCP tool wrappers.

## Assertions

A. The cursor SHALL track query, params, batch_size, materialized items, and position.

B. Cursor materialization SHALL dispatch to existing query helpers and reshape results based on batch_size.

C. Only one cursor SHALL be active at a time; opening a new cursor SHALL discard the previous.

D. `open_cursor` SHALL return the first item, total count, and query metadata.

E. `cursor_next` SHALL return items at `[position:position+count]` and advance position, returning empty list at end.

F. `cursor_info` SHALL be read-only, returning `{position, total, remaining, query, batch_size}`.

G. The implementation SHALL reuse existing serializers: `_serialize_requirement_summary()`, `_serialize_assertion()`, `_serialize_node_summary()`.

## Rationale

A single-cursor model with materialized items provides simple, predictable iteration that fits the single-LLM-session model without complex streaming or concurrent cursor management.

*End* *Cursor Protocol Implementation* | **Hash**: 997facb6

---

## REQ-o00069: MCP Minimize Requirement Set Tool

**Level**: ops | **Status**: Active | **Implements**: REQ-p00060

The MCP server SHALL provide a `minimize_requirement_set` tool that prunes a set of requirement IDs to their most-specific members by removing ancestors already covered by more-specific descendants.

## Assertions

A. `minimize_requirement_set(req_ids, edge_kinds)` SHALL accept a list of requirement IDs and an optional edge kinds filter defaulting to "implements,refines".

B. The tool SHALL return a minimal set containing only requirements that are not ancestors of other requirements in the input set.

C. The tool SHALL return pruned requirements with metadata indicating which input member(s) supersede each pruned item.

D. The tool SHALL report unknown IDs separately in a `not_found` list without failing the operation.

E. The tool SHALL follow IMPLEMENTS and REFINES edges when determining ancestor relationships, configurable via the `edge_kinds` parameter.

## Rationale

Agents listing requirements for a ticket often include both specific leaf requirements and their broad ancestors, creating noise. This tool enables automated pruning to the most-specific set.

*End* *MCP Minimize Requirement Set Tool* | **Hash**: c667abd2

---

## REQ-d00077: Minimize Requirement Set Implementation

**Level**: dev | **Status**: Active | **Implements**: REQ-o00069

The `minimize_requirement_set` tool SHALL be implemented as a helper function with ancestor walking and set pruning.

## Assertions

A. The minimizer SHALL resolve each ID via the graph index, separating found and not_found IDs.

B. For each found requirement, the minimizer SHALL walk up the hierarchy via the specified edge kinds, collecting transitive ancestor IDs.

C. A requirement R SHALL be pruned if another requirement C in the input set has R in its ancestor set.

D. For each pruned requirement, the helper SHALL record which set member(s) supersede it in a `superseded_by` field.

E. The helper SHALL return `{minimal_set, pruned, not_found, stats}` with serialized requirement summaries.

F. The MCP tool wrapper SHALL delegate to the helper, performing only parameter parsing and edge_kinds string-to-set conversion.

## Rationale

Separating the helper from the tool wrapper enables reuse by `discover_requirements` which chains scoped_search with minimize.

*End* *Minimize Requirement Set Implementation* | **Hash**: 15572ed9

---

## REQ-o00070: MCP Scoped Search Tool

**Level**: ops | **Status**: Active | **Implements**: REQ-p00060

The MCP server SHALL provide a `scoped_search` tool that restricts keyword search to descendants or ancestors of a scope node.

## Assertions

A. `scoped_search(query, scope_id, direction, field, regex, include_assertions, limit)` SHALL accept a query string, scope node ID, and direction ("descendants" or "ancestors").

B. The tool SHALL restrict search results to nodes reachable from the scope node in the specified direction, including the scope node itself.

C. When `include_assertions=True`, the tool SHALL also match against assertion text and include `matched_assertions` metadata on matching parent requirements.

D. The tool SHALL return an error when the scope_id is not found in the graph.

E. The tool SHALL reuse `_matches_query()` for field/regex matching logic, maintaining a single code path per REQ-p00050-D.

## Rationale

Agents exploring requirements for a ticket need to search within a relevant subgraph rather than the entire graph, which produces too many unrelated matches.

*End* *MCP Scoped Search Tool* | **Hash**: e1cb96d9

---

## REQ-d00078: Scoped Search Implementation

**Level**: dev | **Status**: Active | **Implements**: REQ-o00070

The `scoped_search` tool SHALL be implemented using scope collection and reusable matching helpers.

## Assertions

A. Scope collection SHALL return a set of node IDs reachable from scope_id: BFS for "descendants", recursive walk for "ancestors".

B. The scope set SHALL include scope_id itself and use a visited set to prevent cycles in DAG structures.

C. Scoped search SHALL iterate only REQUIREMENT nodes within the scope set, reusing the standard matching logic.

D. When `include_assertions=True`, the helper SHALL check assertion text of each in-scope requirement and attach `matched_assertions` metadata when assertions match.

E. The helper SHALL return serialized results in the same format as `_search()`, plus `scope_id` and `direction` metadata.

F. The MCP tool wrapper SHALL delegate to the helper, performing only parameter validation.

## Rationale

Separating scope collection from search logic enables reuse of `_collect_scope_ids` by other tools and the cursor protocol.

*End* *Scoped Search Implementation* | **Hash**: b41ea5f2

---

## REQ-o00071: MCP Discover Requirements Tool

**Level**: ops | **Status**: Active | **Implements**: REQ-p00060

The MCP server SHALL provide a `discover_requirements` tool that chains scoped search with ancestor pruning to return only the most-specific matches within a subgraph.

## Assertions

A. `discover_requirements(query, scope_id, direction, field, regex, include_assertions, limit, edge_kinds)` SHALL accept scoped search parameters plus an edge_kinds filter for ancestor pruning.

B. The tool SHALL chain `scoped_search` results through `minimize_requirement_set` to remove ancestors already covered by more-specific descendants in the result set.

C. The tool SHALL return results in scoped_search format containing only the minimal set, plus pruned items with `superseded_by` metadata.

D. The tool SHALL pass through all results unchanged when no ancestor relationships exist between matches.

## Rationale

Agents won't compose scoped_search + minimize_requirement_set unprompted. A single wrapper tool is the most discoverable interface for finding the most-specific requirements within a subgraph.

*End* *MCP Discover Requirements Tool* | **Hash**: fea647ee

---

## REQ-d00079: Discover Requirements Implementation

**Level**: dev | **Status**: Active | **Implements**: REQ-o00071

The `discover_requirements` tool SHALL be implemented by chaining existing `_scoped_search` and `_minimize_requirement_set` helpers.

## Assertions

A. Discovery SHALL chain scoped search to get candidate results, then pass them through the minimizer.

B. The helper SHALL return `{results, pruned, stats}` where results contains only minimal-set items in scoped_search summary format.

C. The helper SHALL preserve `matched_assertions` metadata from scoped_search on items that remain in the minimal set.

D. The MCP tool wrapper SHALL delegate to the helper, performing only edge_kinds string parsing.

## Rationale

Chaining existing helpers avoids duplicating search or pruning logic and maintains the single-code-path principle.

*End* *Discover Requirements Implementation* | **Hash**: b5683277

---

## REQ-d00133: MCP FILE Node Integration

**Level**: dev | **Status**: Active | **Implements**: REQ-d00060, REQ-d00061, REQ-o00067

MCP tools SHALL be aware of FILE nodes without exposing them where they do not belong.

## Assertions

A. Subtree extraction starting from a FILE node SHALL walk CONTAINS edges, producing the file's physical contents view.

B. Subtree extraction starting from a REQUIREMENT node SHALL walk domain edges (IMPLEMENTS, REFINES, STRUCTURES), producing the requirement's traceability view.

C. `_SUBTREE_KIND_DEFAULTS` SHALL include a `NodeKind.FILE` entry that maps to `{NodeKind.REQUIREMENT, NodeKind.ASSERTION, NodeKind.REMAINDER}` for FILE root traversal.

D. `_search()` SHALL NOT return FILE nodes in search results for requirement queries.

E. `_get_graph_status()` SHALL include FILE node counts in its `node_counts` dict (already satisfied by iterating all NodeKind values).

F. MCP serialization of requirement and assertion nodes SHALL produce identical `file` and `line` fields as before the FILE node migration, using `file_node()` and `parse_line`.

## Rationale

FILE nodes are structural infrastructure. They enhance the graph's completeness but should not pollute requirement-focused query results. Filtered traversal via edge_kinds ensures `get_subtree()` produces the right view depending on the starting node's kind.

*End* *MCP FILE Node Integration* | **Hash**: 73606d1d

---

## REQ-d00205: MCP Federation Support

**Level**: dev | **Status**: Active | **Implements**: REQ-d00200, REQ-o00061

The MCP server SHALL leverage FederatedGraph's per-repo config access for federation-aware operation.

## Assertions

A. `get_workspace_info()` SHALL include federation details when multiple repos are present: repo names, paths, error states, and git origins from `iter_repos()`.

B. `refresh_graph()` SHALL sync `_state["config"]` with the rebuilt federation's root repo config to prevent config staleness.

C. Node-specific config operations (assertion target normalization, edge mutation config) SHALL use `graph.config_for(node_id)` instead of global `_state["config"]`.

D. Global operations (workspace info, agent instructions, project summary) SHALL continue to use root repo config from `_state["config"]`.

## Rationale

Without federation-aware config access, all MCP operations use the root repo's config regardless of which repo a node belongs to. Per-repo config access ensures correct ID pattern resolution and changelog settings for multi-repo operations. Federation info in workspace queries helps AI agents understand the multi-repo topology.

*End* *MCP Federation Support* | **Hash**: ccc0ca12

---

## Architecture Diagram

```text
┌─────────────────────────────────────────────────────────────────────┐
│                        MCP SERVER LAYER                              │
│                                                                      │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐     │
│  │  Query Tools    │  │ Workspace Tools │  │ Mutation Tools  │     │
│  │  - get_status   │  │ - workspace_info│  │ - mutate_*      │     │
│  │  - search       │  │ - project_summary│ │ - undo_*        │     │
│  │  - get_req      │  └────────┬────────┘  └────────┬────────┘     │
│  │  - get_hierarchy│           │                    │              │
│  └────────┬────────┘           │                    │              │
│           │                    │                    │              │
│           ▼                    ▼                    ▼              │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                     SERIALIZERS                              │   │
│  │  serialize_requirement_summary()  serialize_requirement_full()│   │
│  │  serialize_mutation_entry()       serialize_edge()           │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                │ Direct consumption (REQ-p00050-B)
                                │ No intermediate data structures
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        TRACE GRAPH                                   │
│                                                                      │
│  Iterator API:                    Mutation API:                      │
│  - iter_roots()                   - rename_node()                    │
│  - nodes_by_kind()                - add_requirement()                │
│  - get_node()                     - delete_requirement()             │
│  - node.iter_children()           - undo_last() / undo_to()          │
│  - node.iter_parents()                                               │
│  - node.get_field()                                                  │
│  - node.metrics                                                      │
└─────────────────────────────────────────────────────────────────────┘
```text

## Anti-Patterns to Avoid

1. **Caching graph data in MCP server**

   ```python
   # BAD: Caching requirements
   self._requirements_cache = {n.id: n for n in graph.nodes_by_kind(REQUIREMENT)}

   # GOOD: Query graph directly each time
   node = ctx.graph.get_node(req_id)
   ```

2. **Implementing mutation logic in MCP tools**

   ```python
   # BAD: Mutation logic in MCP
   def mutate_rename(old_id, new_id):
       node = graph.get_node(old_id)
       node._id = new_id  # Direct mutation!

   # GOOD: Delegate to graph
   def mutate_rename(old_id, new_id):
       return graph.rename_node(old_id, new_id)
   ```

3. **Recomputing statistics**

   ```python
   # BAD: Counting in MCP
   count = sum(1 for n in graph.all_nodes() if n.level == "PRD")

   # GOOD: Use aggregate functions
   from elspais.graph.annotators import count_by_level
   counts = count_by_level(graph)
   ```
