# MCP Operations Requirements

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

## REQ-o00065: Agent-Assisted Link Suggestion

**Level**: ops | **Status**: Active | **Implements**: REQ-p00050

The system SHALL provide an agent-assisted link suggestion engine that analyzes unlinked graph nodes and proposes requirement associations using scoring heuristics.

## Assertions

A. The suggestion engine SHALL identify unlinked TEST nodes (those without REQUIREMENT parents via VERIFIES edges) as suggestion candidates.

B. The suggestion engine SHALL score suggestions using multiple heuristics: import chain analysis, function name matching, file path proximity, and keyword overlap.

C. Each suggestion SHALL include a source node, target requirement, confidence score (0.0-1.0), confidence band (high/medium/low), and human-readable reason.

D. The suggestion engine SHALL be exposed through both CLI (`elspais link suggest`) and MCP tools (`suggest_links`).

E. The suggestion engine SHALL operate read-only on the graph, producing suggestions without modifying graph state.

F. The suggestion engine SHALL support applying suggestions by inserting `# Implements:` comments into source files.

## Rationale

Teams need to not just see what's unlinked but act on it efficiently. Combining existing building blocks (import analyzer, test-code linker, keyword search) into a scoring pipeline enables AI agents and humans to close traceability gaps systematically.

*End* *Agent-Assisted Link Suggestion* | **Hash**: 17851ae2
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
