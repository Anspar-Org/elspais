# MCP Tools Development Requirements

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

## Changelog

- 2026-04-23 | 4e2277cc | - | Developer (dev@example.com) | Auto-fix: add missing changelog section

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

## Changelog

- 2026-04-23 | 0183195b | - | Developer (dev@example.com) | Auto-fix: add missing changelog section

*End* *Requirement Search Tool Implementation* | **Hash**: 0183195b
---

## REQ-d00062: Requirement Detail Tool Implementation

**Level**: dev | **Status**: Active | **Implements**: REQ-o00060-D

The `get_requirement()` tool SHALL return full requirement details from a single graph lookup.

## Assertions

A. SHALL use `graph.get_node(req_id)` for O(1) lookup.

B. SHALL return node fields: id, title, level, status, hash, body.

C. SHALL return assertions by iterating `node.iter_children()` filtered by NodeKind.*Assertion*.

D. SHALL return relationships by iterating `node.iter_outgoing_edges()`.

E. SHALL return metrics from `node.metrics` dict without recomputation.

F. SHALL return 404-equivalent error for non-existent requirements.

## Rationale

Single-requirement lookup is the most common operation. O(1) access via graph index is essential.

## Changelog

- 2026-03-30 | 6e01fc33 | - | Michael Lewis (michael@anspar.org) | Auto-fix: canonicalize term forms

*End* *Requirement Detail Tool Implementation* | **Hash**: 6e01fc33
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

## Changelog

- 2026-04-23 | 2b1d284b | - | Developer (dev@example.com) | Auto-fix: add missing changelog section

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

## Changelog

- 2026-04-23 | 8d56d937 | - | Developer (dev@example.com) | Auto-fix: add missing changelog section

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

## Changelog

- 2026-04-23 | 5d1f7627 | - | Developer (dev@example.com) | Auto-fix: add missing changelog section

*End* *Mutation Tool Delegation* | **Hash**: 5d1f7627
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

## Changelog

- 2026-04-23 | 6ac6b51f | - | Developer (dev@example.com) | Auto-fix: add missing changelog section

*End* *Test Coverage Tool Implementation* | **Hash**: 6ac6b51f
---

## REQ-d00067: Uncovered Assertions Tool Implementation

**Level**: dev | **Status**: Active | **Implements**: REQ-o00064-B

The `get_uncovered_assertions()` tool SHALL find assertions lacking test coverage.

## Assertions

A. SHALL accept optional `req_id` parameter; when None, scan all requirements.

B. SHALL iterate assertions using `graph.nodes_by_kind(NodeKind.ASSERTION)`.

C. SHALL check each *Assertion* for incoming edges from TEST nodes.

D. SHALL return *Assertion* details: id, text, label, parent requirement context.

E. SHALL return parent requirement id and title for context.

F. SHALL limit results to prevent unbounded response sizes.

## Rationale

Finding uncovered assertions enables systematic test coverage improvement across the project.

## Changelog

- 2026-03-30 | 4884d7cb | - | Michael Lewis (michael@anspar.org) | Auto-fix: canonicalize term forms

*End* *Uncovered Assertions Tool Implementation* | **Hash**: 4884d7cb
---

## REQ-d00068: Assertion Keyword Search Tool Implementation

**Level**: dev | **Status**: Active | **Implements**: REQ-o00064-C

The `find_assertions_by_keywords()` tool SHALL search *Assertion* text for keyword matches.

## Assertions

A. SHALL accept `keywords` list parameter with search terms.

B. SHALL accept `match_all` boolean; True requires all keywords, False requires any keyword.

C. SHALL search *Assertion* text (the SHALL statement content) for keyword matches.

D. SHALL return *Assertion* id, text, label, and parent requirement context.

E. SHALL perform case-insensitive matching by default.

F. SHALL complement `find_by_keywords()` which searches requirement titles, not *Assertion* text.

## Rationale

*Assertion* keyword search enables AI agents to find assertions related to specific concepts when linking tests to requirements.

## Changelog

- 2026-03-30 | a9b8dff2 | - | Michael Lewis (michael@anspar.org) | Auto-fix: canonicalize term forms

*End* *Assertion Keyword Search Tool Implementation* | **Hash**: a9b8dff2
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

## Changelog

- 2026-04-23 | e438ff5e | - | Developer (dev@example.com) | Auto-fix: add missing changelog section

*End* *MCP Link Suggestion Tools* | **Hash**: e438ff5e
---

## REQ-d00075: Subtree Extraction Implementation

**Level**: dev | **Status**: Active | **Implements**: REQ-o00067

The subtree extraction tool SHALL be implemented as MCP-layer helpers that consume the graph iterator API.

## Assertions

A. Subtree collection SHALL perform BFS traversal with depth tracking and a visited set for DAG deduplication.

B. Coverage summaries SHALL include total, covered, and percentage values, reusing existing coverage computation.

C. Markdown format SHALL render indented headings with *Assertion* bullets and coverage stats.

D. Flat format SHALL return root_id, nodes, edges, and stats as a JSON-safe structure.

E. Nested format SHALL return recursive JSON with `children` arrays.

F. Conservative kind defaults SHALL include `REQUIREMENT` + `ASSERTION` for requirement roots, and `USER_JOURNEY` for journey roots.

G. The implementation SHALL NOT modify Graph, GraphTrace, or GraphBuilder structures.

## Rationale

BFS with depth tracking and kind filtering provides the flexible subtree extraction that `GraphNode.walk()` alone cannot deliver, while staying in the MCP layer.

## Changelog

- 2026-03-30 | 5ba55cf2 | - | Michael Lewis (michael@anspar.org) | Auto-fix: canonicalize term forms

*End* *Subtree Extraction Implementation* | **Hash**: 5ba55cf2
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

## Changelog

- 2026-04-23 | 997facb6 | - | Developer (dev@example.com) | Auto-fix: add missing changelog section

*End* *Cursor Protocol Implementation* | **Hash**: 997facb6
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

## Changelog

- 2026-04-23 | 15572ed9 | - | Developer (dev@example.com) | Auto-fix: add missing changelog section

*End* *Minimize Requirement Set Implementation* | **Hash**: 15572ed9
---

## REQ-d00078: Scoped Search Implementation

**Level**: dev | **Status**: Active | **Implements**: REQ-o00070

The `scoped_search` tool SHALL be implemented using scope collection and reusable matching helpers.

## Assertions

A. Scope collection SHALL return a set of node IDs reachable from scope_id: BFS for "descendants", recursive walk for "ancestors".

B. The scope set SHALL include scope_id itself and use a visited set to prevent cycles in DAG structures.

C. Scoped search SHALL iterate only REQUIREMENT nodes within the scope set, reusing the standard matching logic.

D. When `include_assertions=True`, the helper SHALL check *Assertion* text of each in-scope requirement and attach `matched_assertions` metadata when assertions match.

E. The helper SHALL return serialized results in the same format as `_search()`, plus `scope_id` and `direction` metadata.

F. The MCP tool wrapper SHALL delegate to the helper, performing only parameter validation.

## Rationale

Separating scope collection from search logic enables reuse of `_collect_scope_ids` by other tools and the cursor protocol.

## Changelog

- 2026-03-30 | 27a8b0c4 | - | Michael Lewis (michael@anspar.org) | Auto-fix: canonicalize term forms

*End* *Scoped Search Implementation* | **Hash**: 27a8b0c4
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

## Changelog

- 2026-04-23 | b5683277 | - | Developer (dev@example.com) | Auto-fix: add missing changelog section

*End* *Discover Requirements Implementation* | **Hash**: b5683277
---

## REQ-d00133: MCP FILE Node Integration

**Level**: dev | **Status**: Active | **Implements**: REQ-d00060, REQ-d00061, REQ-o00067

MCP tools SHALL be aware of FILE nodes without exposing them where they do not belong.

## Assertions

A. Subtree extraction starting from a FILE node SHALL walk CONTAINS edges, producing the file's physical contents view.

B. Subtree extraction starting from a REQUIREMENT node SHALL walk domain edges (IMPLEMENTS, REFINES, STRUCTURES), producing the requirement's *Traceability* view.

C. `_SUBTREE_KIND_DEFAULTS` SHALL include a `NodeKind.FILE` entry that maps to `{NodeKind.REQUIREMENT, NodeKind.ASSERTION, NodeKind.REMAINDER}` for FILE root traversal.

D. `_search()` SHALL NOT return FILE nodes in search results for requirement queries.

E. `_get_graph_status()` SHALL include FILE node counts in its `node_counts` dict (already satisfied by iterating all NodeKind values).

F. MCP serialization of requirement and *Assertion* nodes SHALL produce identical `file` and `line` fields as before the FILE node migration, using `file_node()` and `parse_line`.

## Rationale

FILE nodes are structural infrastructure. They enhance the graph's completeness but should not pollute requirement-focused query results. Filtered traversal via edge_kinds ensures `get_subtree()` produces the right view depending on the starting node's kind.

## Changelog

- 2026-03-30 | ae564dae | - | Michael Lewis (michael@anspar.org) | Auto-fix: canonicalize term forms

*End* *MCP FILE Node Integration* | **Hash**: ae564dae
---

## REQ-d00205: MCP Federation Support

**Level**: dev | **Status**: Active | **Implements**: REQ-d00200, REQ-o00061

The MCP server SHALL leverage FederatedGraph's per-repo config access for federation-aware operation.

## Assertions

A. `get_workspace_info()` SHALL include federation details when multiple repos are present: repo names, paths, error states, and git origins from `iter_repos()`.

B. `refresh_graph()` SHALL sync `_state["config"]` with the rebuilt federation's root repo config to prevent config staleness.

C. Node-specific config operations (*Assertion* target normalization, edge mutation config) SHALL use `graph.config_for(node_id)` instead of global `_state["config"]`.

D. Global operations (workspace info, agent instructions, project summary) SHALL continue to use root repo config from `_state["config"]`.

## Rationale

Without federation-aware config access, all MCP operations use the root repo's config regardless of which repo a node belongs to. Per-repo config access ensures correct ID pattern resolution and changelog settings for multi-repo operations. Federation info in workspace queries helps AI agents understand the multi-repo topology.

## Changelog

- 2026-03-30 | 4f16dfc7 | - | Michael Lewis (michael@anspar.org) | Auto-fix: canonicalize term forms

*End* *MCP Federation Support* | **Hash**: 4f16dfc7
---

## REQ-d00214: MCP Server Install/Uninstall CLI Commands

**Level**: dev | **Status**: Active | **Implements**: REQ-p00060

## Assertions

A. The mcp install subcommand SHALL register the elspais MCP server with the Claude CLI, supporting both project-scope and user-scope modes.

B. The mcp uninstall subcommand SHALL remove the elspais MCP server registration from the Claude CLI.

C. Install and uninstall SHALL detect the Claude CLI binary and produce a clear error if not found.

D. Install SHALL detect the elspais binary and produce a clear error if not found.

E. Install SHALL support Claude Desktop configuration with platform-specific config paths (Linux, macOS) and an unsupported-platform error for others.

F. The --desktop flag SHALL write or remove the MCP server entry in the Claude Desktop JSON config file.

G. All operations SHALL produce a clear error when the underlying CLI command fails.

## Changelog

- 2026-04-23 | f1518d2c | - | Developer (dev@example.com) | Auto-fix: add missing changelog section

*End* *MCP Server Install/Uninstall CLI Commands* | **Hash**: f1518d2c
