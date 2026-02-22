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

**refresh_graph(full)**

Force rebuild the graph from spec files.

  Parameters:
    full (bool)   If true, clear all caches before rebuild

  Returns:
    success       Whether rebuild succeeded
    message       Status message
    node_count    New total node count

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

  Examples:
    search("authentication")           # Find auth-related requirements
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
    coverage                Coverage statistics:
      - full              Requirements with full coverage
      - partial           Requirements with partial coverage
      - none              Requirements with no coverage
    changes                 Git change metrics:
      - uncommitted       Modified spec files
      - branch_changed    Changed vs main branch
    total_nodes            Total nodes in graph
    orphan_count           Requirements without parents
    broken_reference_count References to non-existent requirements

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

All tools use the iterator-only API (`iter_children()`, `iter_parents()`,
`nodes_by_kind()`) to prevent accidental list materialization on large graphs.
