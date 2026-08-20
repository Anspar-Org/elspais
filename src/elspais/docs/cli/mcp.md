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

## Two Ways To Connect, and Which To Prefer

`elspais mcp install` registers an **http** connection by default. Prefer
it. Over http the client talks to the same daemon the CLI and the viewer
use, so all three see one graph -- a change made through MCP is visible
to `elspais` commands immediately, and vice versa. It also survives the
daemon being replaced: an http client reconnects to the same address,
where a stdio server is a process the client owns and nothing restarts
once it exits.

Installed for one project (the default), the registration names this
working tree's address outright and there is nothing to arrange -- just
launch the client. Each working tree keeps its own address, so parallel
sessions in different worktrees do not collide, and the address is held
for that tree even while nothing is serving it: restart the daemon, or
stop and start it, and the same address answers.

Installed with `--global`, one registration serves every project, so it
cannot name any single tree's address. It names a variable instead, and
the shell that launches the client supplies it:

  $ eval "$(elspais mcp env)"
  $ claude

`elspais mcp env` starts the daemon for the working tree you are in if
none is running, then prints `export ELSPAIS_MCP_URL=...` for the shell
to apply. (It prints rather than exports because no process can set a
variable in the shell that started it.)

If a tree's reserved address is ever taken by something else, the daemon
says so and serves elsewhere; re-running `elspais mcp install` records
the new address.

Running `elspais mcp install` again replaces whatever is registered, so
switching between the two is one command either way.

Use **stdio** (`elspais mcp install --transport stdio`) for a client that
cannot speak http. A stdio server holds its own private graph: mutations
made through it are not visible to the CLI or the viewer until they are
saved to disk, and it goes on answering from the elspais it loaded at
startup for as long as the session lasts. If elspais is reinstalled
beneath it -- which, in a tree elspais is installed from, is what editing
a file amounts to -- it says so and asks to be reconnected. See
`docs("concurrency")` for what it reports and why.

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
    coverage        Coverage figures, when the requirement carries a rollup
                    (null otherwise):
                    `total_assertions`, plus `implemented_total_covered` and
                    `implemented_total_pct` — both the per-*Assertion* total
                    of REQ-d00069-N, each assertion counted once at the
                    greatest of its four measures. These two keys replaced
                    `covered_assertions` and `referenced_pct`, which were
                    named for a claim the total does not make (that a
                    citation had named the assertions). To read what a
                    citation named, ask `get_test_coverage` or
                    `get_uncovered_assertions`, which answer on the
                    immediate-direct measure.

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
                             tested_passed, tested_failed, tested_awaiting).
                             The three tested_* counts are the Tested
                             breakdown and account for every tested
                             assertion. Per dimension (implemented, tested,
                             passing, uat_covered, uat_passed) the payload
                             carries `<dim>_total_covered` -- the
                             REQ-d00069-N per-*Assertion* total the CLI now
                             headlines -- plus the four REQ-d00069-L measures
                             behind it: `<dim>_immediate_direct`,
                             `<dim>_immediate_indirect`, `<dim>_rolled_direct`,
                             `<dim>_rolled_indirect`.
    changes                 Git change metrics:
      - uncommitted       Modified spec files
      - branch_changed    Changed vs main branch
    total_nodes            Total nodes in graph
    orphan_count           Requirements without parents
    broken_reference_count References to non-existent requirements

**get_test_coverage(req_id)** / **get_uncovered_assertions(req_id?, source?)**

These two answer "what is left to do", so they read one measure: a citation
NAMED the assertion and the evidence is attached to it (REQ-d00258-M). Neither
whole-requirement evidence (a blanket `Verifies:`, which names no assertion)
nor coverage conducted up a `Refines:` chain (written against the refining
requirement) closes a gap, however much of either the requirement carries.
This is deliberately stricter than the figures `get_project_summary` and the
viewer headline, which count each assertion at the greatest of the four
measures.

  Each entry of `uncovered_detail` carries:
    id           Assertion node ID
    label        Assertion label (get_uncovered_assertions only)
    fraction     Its coverage on the measure the verdict was taken on;
                  0 means nothing names it, 0 < f < 1 means partial
                  evidence, and a listed gap can never read 1
    measures     Keyed by dimension -- always just `tested` from
                  get_test_coverage, and one entry per axis `source` asked
                  about (`tested`, `uat_coverage`) from
                  get_uncovered_assertions. Each holds the four measures of
                  REQ-d00069-L behind the verdict:
                  immediate_direct, immediate_indirect, rolled_direct,
                  rolled_indirect. This is where whole-requirement and
                  conducted evidence stays visible.

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
