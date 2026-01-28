# MASTER_PLAN.md - elspais Enhancement Queue

This file contains a prioritized queue of enhancement issues. See CLAUDE.md for workflow.

---

## Bugs

- [x] trace --view: Assoc (Associated) toggle is broken
  - Fixed: Changed from "SHOW ONLY" to "HIDE" semantic (consistent with PRD/OPS/DEV)
  - Now clicking Assoc badge hides associated requirements

- [x] trace --view: Core toggle doesn't work
  - Fixed: Added Core filter with HIDE semantic
  - Clicking Core badge now hides core (non-associated) requirements
  - Added CSS active state styling for consistency

- [x] trace --view: State persistence with cookies
  - Fixed: Now saves/restores tree collapse/expand state via collapsedNodes array in cookie
  - Fixed initialization order to check for saved state before applying defaults
  - All GUI state now persists: filters, toggles, dropdowns, tabs, and tree state

- [x] GraphNode.label encapsulation incomplete
  - Fixed: Refactored all `.label` usages to `get_label()` and `.label =` to `set_label()`
  - Updated: mcp/server.py (11), mcp/serializers.py (5), mcp/context.py (1), html/generator.py (4), validation/format.py (2)
  - Updated test files: test_builder.py, test_mutations.py, test_graph_node.py
  - All 494 tests pass

---

## Quick Wins

- [x] elspais should check if it is in a git repo and always run as if in the root
  - Already implemented: `find_git_root()` in `config/__init__.py` (see CLAUDE.md 7b)

- [x] CLI implementation audit: Check all CLI arguments are fully implemented
  - Found and removed 19 dead arguments across 3 commands:
    - validate: 5 dead args (--fix, --core-repo, --tests, --no-tests, --mode)
    - trace: 5 dead args (--port, --mode, --sponsor, --graph, --depth)
    - reformat-with-claude: 8 dead args (entire command not implemented - simplified to stub)
  - Kept properly-stubbed features (trace --edit-mode, --review-mode, --server)

- [x] CLI argument consistency: Standardize argument format
  - CLI was already consistent with standard conventions (--flags for options, no -- for subcommands)
  - Fixed: `--report` now uses `choices=["minimal", "standard", "full"]` for tab completion
  - The `{minimal,standard,full}` is now shown in help and enables shell autocomplete

- [x] trace --view: Simplify assertion display to show only REQ A → REQ B relationships
  - Fixed: Aggregate assertion targets per child before building tree rows
  - Now shows single entry with combined badges [A][B][C] instead of duplicates

---

---

## TraceGraph Detection and Mutation API

### Summary
Augment `TraceGraph` with:
1. **Detection** - Orphaned nodes and broken references (captured at build time)
2. **Mutation API** - Full CRUD operations with undo support and mutation logging

### Key Files
- `src/elspais/graph/builder.py` - TraceGraph and GraphBuilder classes (mutations added here)
- `src/elspais/graph/GraphNode.py` - GraphNode class (for understanding structure)
- `src/elspais/graph/mutations.py` - NEW: MutationEntry, MutationLog, BrokenReference dataclasses

### Design Decision
**Mutations live on TraceGraph directly** - `graph.rename_node()`, `graph.add_edge()`, etc.
This provides the simplest API while keeping all graph state in one place.

---

---

---

## [x] Quick Fix: Encapsulate `label` attribute

**COMPLETE** - All files now use accessor methods.

- [x] `GraphNode._label` renamed, `get_label()`/`set_label()` methods added
- [x] Refactored ~25 usages across 8 files to use accessor methods

---

## All Phases Complete! 🎉

The TraceGraph Detection and Mutation API implementation is complete. See OLD_PLAN.md for completed phases:
- Phase 1: Detection (Orphan/Broken Reference Detection)
- Phase 2: Mutation Infrastructure (MutationEntry, MutationLog, Undo)
- Phase 3: Node Mutations (rename, update, add, delete requirements)
- Phase 4: Assertion Mutations (rename, update, add, delete assertions)
- Phase 5: Edge Mutations (add, change, delete edges, fix broken refs)
- MCP Mutator Capabilities (19 MCP tools for AI-driven management)
