# MCP Server Specification

This document specifies the Model Context Protocol (MCP) server that exposes elspais functionality to AI agents. The MCP server is a pure interface layer that consumes the unified TraceGraph.

---

## REQ-p00060: MCP Server for AI-Driven Requirements Management

**Level**: PRD | **Status**: Active | **Implements**: REQ-p00050

The elspais system SHALL provide an MCP server that enables AI agents to query, navigate, and mutate requirements through the unified TraceGraph.

## Assertions

A. The MCP server SHALL expose TraceGraph data through standardized MCP tools.
B. The MCP server SHALL consume TraceGraph directly without creating intermediate data structures, per REQ-p00050-B.
C. The MCP server SHALL provide read-only query tools for requirement discovery and navigation.
D. The MCP server SHALL provide mutation tools for AI-assisted requirement management.
E. The MCP server SHALL support undo operations for all graph mutations.

## Rationale

AI agents need programmatic access to requirements data for tasks like coverage analysis, requirement drafting, and traceability verification. The MCP protocol provides a standardized interface that works with multiple AI platforms.

*End* *MCP Server for AI-Driven Requirements Management* | **Hash**: ________

---

## REQ-o00060: MCP Core Query Tools

**Level**: OPS | **Status**: Active | **Implements**: REQ-p00060

The MCP server SHALL provide core query tools for graph inspection and requirement lookup.

## Assertions

A. `get_graph_status()` SHALL return graph staleness state, node counts by kind, and last refresh timestamp.
B. `refresh_graph(full)` SHALL force graph rebuild, with `full=True` clearing all caches.
C. `search(query, field, regex)` SHALL search requirements by ID, title, or body content.
D. `get_requirement(req_id)` SHALL return full requirement details including assertions and relationships.
E. `get_hierarchy(req_id)` SHALL return ancestors and children for navigation.
F. All query tools SHALL read directly from TraceGraph nodes using the iterator-only API.

## Rationale

Core query tools enable AI agents to discover and explore requirements without modifying the graph. These are safe, read-only operations.

*End* *MCP Core Query Tools* | **Hash**: ________

---

## REQ-o00061: MCP Workspace Context Tools

**Level**: OPS | **Status**: Active | **Implements**: REQ-p00060

The MCP server SHALL provide workspace context tools that describe the current repository and project.

## Assertions

A. `get_workspace_info()` SHALL return repository path, project name, and configuration summary.
B. `get_project_summary()` SHALL return requirement counts by level, coverage statistics, and change metrics.
C. Workspace tools SHALL use graph aggregate functions from the annotators module, not recompute statistics.
D. Configuration data SHALL be read from the unified config system, not parsed separately.

## Rationale

AI agents need context about the workspace they're operating in to provide relevant assistance. Workspace tools answer "what repo am I serving?" and "what's the state of this project?"

*End* *MCP Workspace Context Tools* | **Hash**: ________

---

## REQ-o00062: MCP Graph Mutation Tools

**Level**: OPS | **Status**: Active | **Implements**: REQ-p00060

The MCP server SHALL provide mutation tools for in-memory graph modifications with full undo support.

## Assertions

A. Node mutations SHALL include: rename, update_title, change_status, add_requirement, delete_requirement.
B. Assertion mutations SHALL include: add_assertion, update_assertion, delete_assertion, rename_assertion.
C. Edge mutations SHALL include: add_edge, change_edge_kind, delete_edge, fix_broken_reference.
D. All mutations SHALL delegate to TraceGraph mutation methods, not implement mutation logic directly.
E. All mutations SHALL return a MutationEntry for audit and undo.
F. Destructive operations (delete_*) SHALL require explicit `confirm=True` parameter.
G. `undo_last_mutation()` and `undo_to_mutation(id)` SHALL reverse mutations using graph.undo_last() and graph.undo_to().

## Rationale

In-memory mutations enable AI agents to draft requirement changes that can be reviewed before persisting. The undo system provides safety for exploratory editing.

*End* *MCP Graph Mutation Tools* | **Hash**: ________

---

## REQ-o00063: MCP File Mutation Tools

**Level**: OPS | **Status**: Active | **Implements**: REQ-p00060

The MCP server SHALL provide file mutation tools that persist changes to spec files on disk.

## Assertions

A. `change_reference_type(req_id, target_id, new_type)` SHALL modify Implements/Refines relationships in spec files.
B. `move_requirement(req_id, target_file)` SHALL relocate a requirement between spec files.
C. `transform_with_ai(req_id, prompt, save_branch)` SHALL use AI to rewrite requirement content.
D. File mutations SHALL create git safety branches when `save_branch=True`.
E. `restore_from_safety_branch(branch_name)` SHALL revert file changes from a safety branch.
F. After file mutations, `refresh_graph()` SHALL be called to synchronize the in-memory graph.

## Rationale

File mutations persist changes to the authoritative spec files. Git safety branches provide rollback capability for destructive operations.

*End* *MCP File Mutation Tools* | **Hash**: ________

---

## REQ-d00060: Graph Status Tool Implementation

**Level**: DEV | **Status**: Active | **Implements**: REQ-o00060-A

The `get_graph_status()` tool SHALL report graph state using direct graph inspection.

## Assertions

A. SHALL return `is_stale` boolean from graph metadata, not recomputed.
B. SHALL return `node_counts` by calling `graph.nodes_by_kind()` for each NodeKind.
C. SHALL return `last_refresh` timestamp from graph metadata.
D. SHALL return `root_count` using `graph.root_count()`.
E. SHALL NOT iterate the full graph to count nodes when kind-specific counts suffice.

## Rationale

Graph status provides a quick health check without expensive traversal operations.

*End* *Graph Status Tool Implementation* | **Hash**: ________

---

## REQ-d00061: Requirement Search Tool Implementation

**Level**: DEV | **Status**: Active | **Implements**: REQ-o00060-C

The `search()` tool SHALL find requirements using graph iteration with filtering.

## Assertions

A. SHALL iterate `graph.nodes_by_kind(NodeKind.REQUIREMENT)` for requirement search.
B. SHALL support `field` parameter: "id", "title", "body", or "all" (default).
C. SHALL support `regex=True` for regular expression matching.
D. SHALL return serialized requirement summaries, not full node objects.
E. SHALL limit results to prevent unbounded response sizes.

## Rationale

Search enables AI agents to discover requirements by content without knowing exact IDs.

*End* *Requirement Search Tool Implementation* | **Hash**: ________

---

## REQ-d00062: Requirement Detail Tool Implementation

**Level**: DEV | **Status**: Active | **Implements**: REQ-o00060-D

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

*End* *Requirement Detail Tool Implementation* | **Hash**: ________

---

## REQ-d00063: Hierarchy Navigation Tool Implementation

**Level**: DEV | **Status**: Active | **Implements**: REQ-o00060-E

The `get_hierarchy()` tool SHALL return ancestors and children for tree navigation.

## Assertions

A. SHALL return `ancestors` by walking `node.iter_parents()` recursively to roots.
B. SHALL return `children` by iterating `node.iter_children()`.
C. SHALL return `siblings` by finding parent's other children.
D. SHALL include node summaries (id, title, level) not full details.
E. SHALL handle DAG structure where nodes may have multiple parents.

## Rationale

Hierarchy navigation enables AI agents to understand requirement context and relationships.

*End* *Hierarchy Navigation Tool Implementation* | **Hash**: ________

---

## REQ-d00064: Serializer Functions

**Level**: DEV | **Status**: Active | **Implements**: REQ-p00060-B

Serializer functions SHALL convert GraphNode data to JSON-safe dictionaries.

## Assertions

A. `serialize_requirement_summary(node)` SHALL return id, title, level, status only.
B. `serialize_requirement_full(node)` SHALL return all fields including body, assertions, edges.
C. Serializers SHALL read from `node.get_field()` and `node.metrics`, not access internal attributes.
D. Serializers SHALL handle missing fields gracefully with sensible defaults.
E. Serializers SHALL NOT trigger graph traversal beyond the single node being serialized.

## Rationale

Serializers provide the boundary between graph internals and MCP responses. They ensure consistent, safe data extraction.

*End* *Serializer Functions* | **Hash**: ________

---

## REQ-d00065: Mutation Tool Delegation

**Level**: DEV | **Status**: Active | **Implements**: REQ-o00062-D

MCP mutation tools SHALL delegate to TraceGraph mutation methods.

## Assertions

A. `mutate_rename_node(old_id, new_id)` SHALL call `graph.rename_node(old_id, new_id)`.
B. `mutate_add_requirement(...)` SHALL call `graph.add_requirement(...)`.
C. `mutate_delete_requirement(id, confirm)` SHALL call `graph.delete_requirement(id)` only if `confirm=True`.
D. Mutation tools SHALL NOT implement mutation logic - only parameter validation and delegation.
E. Mutation tools SHALL return the MutationEntry from the graph method for audit trail.

## Rationale

Delegation ensures mutation logic lives in one place (TraceGraph) and MCP is purely an interface layer.

*End* *Mutation Tool Delegation* | **Hash**: ________

---

## Architecture Diagram

```
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
```

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
