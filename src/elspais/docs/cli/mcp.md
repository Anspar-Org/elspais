# MCP SERVER

Model Context Protocol (MCP) server for AI-driven requirements management.

## Overview

The elspais MCP server exposes the requirements graph to AI assistants,
enabling intelligent requirement navigation, search, and analysis without
manual CLI usage.

**Quick setup (Claude Code + Claude Desktop):**

  $ elspais mcp install --global --desktop

**Or Claude Code only:**

  $ elspais mcp install --global

**Starting the server manually:**

  $ elspais mcp serve

## Available Tools

### Graph Status & Control

**get_graph_status()**

Get current graph health and statistics.

  Returns:
    root_count        Number of root requirements
    node_counts       Count by node kind (requirement, assertion, code, test)
    total_nodes       Total nodes in graph
    has_orphans       Whether orphaned nodes exist
    has_broken_references  Whether broken references exist

  Example response:
    {
      "root_count": 3,
      "node_counts": {"requirement": 45, "assertion": 120, "code": 30},
      "total_nodes": 195,
      "has_orphans": false,
      "has_broken_references": false
    }

**refresh_graph(full, path, force, if_tip_mutation_id)**

Force rebuild the graph from spec files.

  Parameters:
    full (bool)              Accepted for compatibility; every rebuild is
                             full, as no cache is retained between builds
    path (str)               Switch to a different project directory first
    force (bool)             If true, discard unsaved mutations and refresh
    if_tip_mutation_id (str) The mutation-log tip; required when force=true
                             (see Concurrency Control below)

  Returns:
    success       Whether rebuild succeeded
    message       Status message
    node_count    New total node count

A configuration that cannot be parsed publishes nothing: `success` is false,
`message` begins `CONFIG ERROR:`, and the graph already being served stays
live.

### Requirement Search & Navigation

**search(query, field, regex, limit)**

Search requirements by ID, title, or content.

  Parameters:
    query (str)     Search string or regex pattern
    field (str)     Field to search: 'id', 'title', 'body', or 'all' (default)
    regex (bool)    If true, treat query as regex pattern (default: false)
    limit (int)     Maximum results to return (default: 50)

  Returns:
    List of matching requirement summaries with id, title, level, status.

  Multi-term query syntax:
    - Space-separated terms: AND by default
    - `OR` keyword: match either side
    - `"quoted phrases"`: exact phrase match
    - `-term`: exclude results containing term
    - `=term`: exact keyword match
    - Parenthesized grouping: `(auth OR login) -deprecated`

  Examples:
    search("authentication")           # Find auth-related requirements
    search("auth OR login")            # Find either term
    search("REQ-p", field="id")        # Find PRD-level by ID prefix
    search(".*security.*", regex=true) # Regex search in all fields

**get_requirement(req_id)**

Get full details for a single requirement.

  Parameters:
    req_id (str)    The requirement ID (e.g., 'REQ-p00001')

  Returns:
    id              Requirement ID
    title           Requirement title
    level           Config type key (e.g., prd, ops, dev)
    status          Draft, Active, Deprecated, etc.
    hash            Content hash for change detection
    version         Concurrency token — pass as if_version to mutations
    file_version    Containing FILE's token (None for INSTANCE/unlinked)
    assertions      List of assertion objects {id, label, text}
    children        Child requirements (summaries)
    parents         Parent requirements (summaries)

  Example:
    get_requirement("REQ-p00001")

**get_hierarchy(req_id)**

Get requirement hierarchy (ancestors and children).

  Parameters:
    req_id (str)    The requirement ID

  Returns:
    id              The queried requirement ID
    ancestors       All ancestor requirements (walks to roots)
    children        Direct child requirements

  Use this to understand where a requirement sits in the hierarchy
  and what depends on it.

### Workspace Context

**get_workspace_info(detail="default")**

Get information about the current workspace/repository. The `detail`
parameter selects a use-case-specific profile that returns additional
context relevant to the task at hand.

  Args:
    detail          Profile to return (default: "default"):
      - "default"     Basic project info, version, available_details
      - "testing"     ID patterns, assertion format, test configuration
      - "code-refs"   Code directories, comment styles, reference keywords
      - "coverage"    Coverage stats, level counts, associate list
      - "retrofit"    Full patterns, hierarchy rules, code + test config
      - "manager"     Health flags, coverage stats, change metrics
      - "worktree"    Associate paths, ID patterns, hierarchy rules
      - "all"         Everything from all profiles combined

  Returns (always present):
    repo_path          Absolute path to repository root
    project_name       Project name from config or directory name
    elspais_version    Installed elspais version
    config_file        Path to .elspais.toml (if exists)
    detail             Which profile was used
    available_details  Map of valid detail values to descriptions
    config_summary     Key configuration values:
      - prefix           Requirement ID prefix
      - spec_directories Where spec files live
      - testing_enabled  Whether test scanning is on
      - project_type     'core' or 'associated'
      - local_config     Whether .elspais.local.toml exists

  The MCP server automatically detects git worktrees and resolves
  associate paths from the canonical repository root.

**get_project_summary()**

Get summary statistics for the project.

  Returns:
    requirements_by_level   Count by config type key (e.g., prd/ops/dev)
    coverage                Coverage tier counts (requirement-level,
                             "implemented" dimension):
      - total             Requirements counted (excluded statuses omitted)
      - full_coverage     Requirements with full coverage
      - partial_coverage  Requirements with partial coverage
      - no_coverage       Requirements with no coverage
      - failing           Requirements with failing coverage
    coverage_by_level       Per-level assertion coverage stats, identical in
                             shape to the `elspais summary` CLI's `levels`
                             list (level, total, with_code_refs,
                             with_test_refs, with_passing, total_assertions,
                             implemented_assertions, implemented_direct,
                             tested_assertions, tested_direct,
                             tested_passed, tested_failed,
                             tested_awaiting, passing_assertions,
                             passing_direct). The three tested_* counts
                             are the Tested breakdown and account for
                             every tested assertion.
    changes                 Git change metrics:
      - uncommitted       Modified spec files
      - branch_changed    Changed vs main branch
    total_nodes            Total nodes in graph
    orphan_count           Requirements without parents
    broken_reference_count References to non-existent requirements

## Concurrency Control

One daemon serves several writers at once (MCP agents and the viewer GUI),
so every `mutate_*` tool requires an `if_version` token — the target's
`version` from your last read — and returns the new `version` on success.
Thread the returned token into your next mutation of the same node.
Deletions return the version of the surviving container that absorbed the
change: the parent requirement for an assertion or section
(`mutate_delete_assertion`, `mutate_delete_remainder`), the containing
FILE for a whole requirement (`mutate_delete_requirement`).
`mutate_add_requirement` accepts an optional `file_id` to place the new
requirement into a chosen file; when given, `if_version` guards that FILE.
`mutate_move_node_to_file` creates a missing destination file itself
(path validated against the scanning config, guards run first); pass
`if_target_version=""` for a destination the move creates.

A stale token is rejected with `version_conflict`, carrying
`current_version` and `current_state`: reconcile your intent against
`current_state` before retrying — never retry blind. Undo, save, forced
refresh, and `restore_from_safety_branch` require the mutation-log tip
(`if_mutation_id` / `if_tip_mutation_id`); `""` means "nothing pending".
The viewer's `/api/mutate/*` HTTP routes enforce the same guards,
returning HTTP 409 with the identical rejection body, and its history
routes `/api/save`, `/api/revert`, and `/api/reload` require
`if_tip_mutation_id` in the JSON body.

Full protocol: `elspais docs concurrency` (or the MCP `docs("concurrency")`
and `faq("concurrency")` tools).

## Client Configuration

### Automatic (recommended)

```bash
# Claude Code (all projects) + Claude Desktop
elspais mcp install --global --desktop

# Claude Code only (current project)
elspais mcp install

# Remove registration
elspais mcp uninstall --desktop
```

### Cursor

Add to Cursor's MCP settings:

```json
{
  "elspais": {
    "command": "elspais",
    "args": ["mcp", "serve"]
  }
}
```

## Transport Options

  stdio (default)   Standard input/output, best for local tools
  sse               Server-sent events, for HTTP clients
  streamable-http   HTTP streaming, for web clients

  $ elspais mcp serve --transport stdio
  $ elspais mcp serve --transport sse

## Typical Workflows

### Understanding a Requirement

1. `get_requirement("REQ-p00001")` - Get full details
2. `get_hierarchy("REQ-p00001")` - See where it fits
3. Check assertions for testable criteria

### Finding Related Requirements

1. `search("authentication")` - Find by keyword
2. `get_hierarchy(result_id)` - Navigate relationships
3. Follow children to see implementations

### Project Health Check

1. `get_graph_status()` - Check for orphans/broken refs
2. `get_project_summary()` - Review coverage stats
3. Address requirements with `coverage: none`

### After Editing Spec Files

1. `refresh_graph()` - Rebuild after changes
2. `get_graph_status()` - Verify graph health

## Configuration Notes

The exact requirement ID syntax (prefixes, patterns) and hierarchy rules are
**configurable per project** via `.elspais.toml`. Different projects may use:

- Different ID prefixes (e.g., `REQ-`, `SPEC-`, `FR-`)
- Different level types (PRD/OPS/DEV or custom)
- Different hierarchy rules for "implements" relationships

Use `get_workspace_info()` to see the current project's configuration, or
`get_workspace_info(detail="all")` to see everything including ID patterns,
hierarchy rules, and associate repositories.

## Architecture Notes

The MCP server is a **pure interface layer** that consumes the TraceGraph
directly without creating intermediate data structures. This ensures:

- Single source of truth (the graph)
- No data duplication or caching issues
- Consistent results across all tools
- Efficient memory usage

All tools use the iterator-only API (`iter_children()`, `iter_parents()` on
`GraphNode`, `nodes_by_kind()` on `TraceGraph`) to prevent accidental list
materialization on large graphs.
