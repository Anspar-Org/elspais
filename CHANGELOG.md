# Changelog

All notable changes to elspais will be documented in this file.

## [0.31.0] - 2026-01-28

### Added
- **MCP Mutator Tools**: The MCP server now exposes TraceGraph mutation methods for AI-driven requirement management:
  - **Node Mutations**: `mutate_rename_node()`, `mutate_update_title()`, `mutate_change_status()`, `mutate_add_requirement()`, `mutate_delete_requirement(confirm=True)`
  - **Assertion Mutations**: `mutate_add_assertion()`, `mutate_update_assertion()`, `mutate_delete_assertion(confirm=True)`, `mutate_rename_assertion()`
  - **Edge Mutations**: `mutate_add_edge()`, `mutate_change_edge_kind()`, `mutate_delete_edge(confirm=True)`, `mutate_fix_broken_reference()`
  - **Undo Operations**: `undo_last_mutation()` and `undo_to_mutation(mutation_id)` for reverting graph changes
  - **Inspection Tools**: `get_mutation_log(limit)`, `get_orphaned_nodes()`, `get_broken_references()` for graph state inspection
- **Safety Checks**: Destructive mutation operations (`mutate_delete_*`) require explicit `confirm=True` parameter to prevent accidental data loss
- **Mutation Serialization**: New `serialize_mutation_entry()` and `serialize_broken_reference()` functions in MCP serializers

## [0.30.0] - 2026-01-28

### Added
- **Edge Mutation API**: TraceGraph now supports edge (relationship) mutations:
  - `add_edge(source_id, target_id, edge_kind, assertion_targets)` - Adds new edge, creates BrokenReference if target doesn't exist
  - `change_edge_kind(source_id, target_id, new_kind)` - Changes edge type (IMPLEMENTS -> REFINES)
  - `delete_edge(source_id, target_id)` - Removes edge, marks source as orphan if no other parents
  - `fix_broken_reference(source_id, old_target_id, new_target_id)` - Redirects broken reference to new target
- **Orphan Management**: Edge mutations automatically update `_orphaned_ids` set when parent relationships change
- **Broken Reference Tracking**: `add_edge` to non-existent target creates BrokenReference; `fix_broken_reference` can redirect these

## [0.29.0] - 2026-01-28

### Added
- **Assertion Mutation API**: TraceGraph now supports assertion-specific mutations:
  - `rename_assertion(old_id, new_label)` - Renames assertion label (e.g., A -> D), updates edges
  - `update_assertion(assertion_id, new_text)` - Updates assertion text
  - `add_assertion(req_id, label, text)` - Adds new assertion to requirement
  - `delete_assertion(assertion_id, compact=True)` - Deletes assertion with optional compaction
- **Assertion Compaction**: When deleting middle assertion (e.g., B from [A,B,C,D]), subsequent labels shift down (C->B, D->C) and all edge references update automatically
- **Hash Recomputation**: All assertion mutations recompute parent requirement hash via `_recompute_requirement_hash()`

## [0.28.0] - 2026-01-28

### Added
- **Node Mutation API**: TraceGraph now supports CRUD operations with full undo:
  - `rename_node(old_id, new_id)` - Renames node and its assertion children
  - `update_title(node_id, new_title)` - Updates requirement title
  - `change_status(node_id, new_status)` - Changes requirement status
  - `add_requirement(...)` - Creates new requirement with optional parent link
  - `delete_requirement(node_id)` - Deletes requirement, tracks in `_deleted_nodes`
- **Mutation Logging**: All mutations log `MutationEntry` to `graph.mutation_log` for audit
- **Undo Support**: `graph.undo_last()` and `graph.undo_to(mutation_id)` for reverting changes
- **GraphNode.set_id()**: Mutable node IDs for rename operations
- **GraphNode.remove_child()**: Removes child node with bidirectional link cleanup

## [0.27.0] - 2026-01-27

### Fixed
- **trace --view**: Fixed Assoc (Associated) toggle - now uses HIDE semantic consistent with PRD/OPS/DEV badges
- **trace --view**: Fixed Core toggle - clicking now hides core (non-associated) requirements with proper styling
- **trace --view**: Added tree collapse/expand state persistence via cookies - tree state now survives page refresh
- **trace --view**: Children implementing multiple assertions now show single row with combined badges [A][B][C]
- **trace --report**: Implemented report presets that were previously ignored

### Changed
- **CLI**: Removed 19 dead arguments that were defined but never implemented:
  - `validate`: --fix, --core-repo, --tests, --no-tests, --mode
  - `trace`: --port, --mode, --sponsor, --graph, --depth
  - `reformat-with-claude`: Simplified to placeholder stub (entire command not yet implemented)
- **CLI**: `trace --report` now uses `choices` for tab completion - shows `{minimal,standard,full}` in help
  - `--report minimal`: ID, Title, Status only (quick overview)
  - `--report standard`: ID, Title, Level, Status, Implements (default)
  - `--report full`: All fields including Body, Assertions, Hash, Code/Test refs

- **trace --view**: Version badge now shows actual elspais version (e.g., "v0.27.0") instead of hardcoded "v1"

- **trace --view**: Replaced confusing "Files" filter with "Tests" filter
  - Shows TEST nodes in tree hierarchy (with 🧪 icon)
  - Badge displays count of test nodes instead of file count
  - Clicking badge shows test rows that validate requirements

## [0.26.0] - Previous

- Multiline block comment support for code/test references
- Various bug fixes and improvements
