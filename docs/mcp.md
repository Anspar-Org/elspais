# MCP Server Guide

This document provides comprehensive documentation for the elspais MCP (Model Context Protocol) server, which exposes requirements management functionality to AI agents.

The server registers far more tools than the selection described below, and it
registers no MCP resources at all. For the complete, current list ask the
server itself — every MCP client can enumerate its tools, and
`agent_instructions()` returns the project's authoring guidance.

## Table of Contents

- [Quick Start](#quick-start)
- [Tool Categories](#tool-categories)
- [Safety Patterns](#safety-patterns)
- [Tool Reference](#tool-reference)

## Quick Start

### Installation

```bash
# Register with Claude Code (all projects) and Claude Desktop
elspais mcp install --global --desktop

# Or Claude Code only (current project)
elspais mcp install

```

### Running the Server Manually

```bash
# Default stdio transport
elspais mcp serve

# SSE transport (for web clients)
elspais mcp serve --transport sse
```

## Tool Categories

### Workspace Context

| Tool | Description |
|------|-------------|
| `get_workspace_info(detail=...)` | Project info with use-case profiles (see below) |
| `get_project_summary()` | Coverage stats, level counts, change metrics |
| `get_changed_requirements()` | Requirements with uncommitted or branch changes |

The `detail` parameter on `get_workspace_info` selects a use-case profile:
`"default"`, `"testing"`, `"code-refs"`, `"coverage"`, `"retrofit"`,
`"manager"`, `"worktree"`, or `"all"`. The default response includes an
`available_details` field describing each profile.

### Read-Only Tools

These tools query data without modifying files:

| Tool | Description |
|------|-------------|
| `search()` | Search requirements by query pattern in specified fields |
| `get_requirement()` | Get complete details for a single requirement by ID |

### Graph Tools

Tools for navigating the traceability graph:

| Tool | Description |
|------|-------------|
| `get_graph_status()` | Check graph cache state, staleness, and node counts |
| `refresh_graph()` | Force rebuild of traceability graph from spec files |
| `get_hierarchy()` | Get ancestors and children for a requirement |

### Mutation Tools

Tools that modify spec files:

| Tool | Description |
|------|-------------|
| `change_reference_type()` | Switch between Implements and Refines references |
| `move_requirement()` | Move requirement between spec files |

### Safety Branch Tools

Tools for git-based recovery:

| Tool | Description |
|------|-------------|
| `restore_from_safety_branch()` | Restore repository from safety branch |
| `list_safety_branches()` | List all safety branches created by elspais |

## Safety Patterns

### Check Graph Staleness

`change_reference_type()` and `move_requirement()` rebuild the graph themselves
after a successful write. To find out whether the spec files on disk have moved
ahead of the loaded graph — because something outside this server edited them:

```python
status = get_graph_status()
if status["is_stale"]:
    refresh_graph()
```

## Tool Reference

### search

Search requirements by pattern.

**Parameters:**
- `query` (str): Search query string
- `field` (str): "all", "id", "title", "body", "assertions"
- `regex` (bool): Treat query as regex pattern
- `limit` (int): Maximum number of results (default 50)

**Returns:** A ranked list of matching requirements.

### get_requirement

Get complete details for a single requirement.

**Parameters:**
- `req_id` (str): Requirement ID (e.g., "REQ-p00001")

**Returns:** id, title, level, status, hash, body, source location, assertions,
parent/child requirements, and coverage metrics.

### change_reference_type

Change a reference from Implements to Refines or vice versa.

**Parameters:**
- `req_id` (str): Requirement containing the reference
- `target_id` (str): Referenced requirement, in rendered ref form (e.g. `p00003`)
- `new_type` (str): "IMPLEMENTS" or "REFINES"
- `if_version` (str): The version of `req_id` from your last read. Required.
- `save_branch` (bool): Create a safety branch before modifying

**Returns:** `success`, the requirement's new `version`, and `safety_branch`
when one was created. On failure, `success: false` with an `error` message; a
stale `if_version` is rejected as a `version_conflict`.

### move_requirement

Move requirement between spec files.

**Parameters:**
- `req_id` (str): Requirement ID to move
- `target_file` (str): Destination file path (relative to workspace)
- `if_version` (str): The version of `req_id` from your last read. Required.
- `save_branch` (bool): Create a safety branch before modifying

**Returns:** `success`, `source_file`, `dest_file`, `source_empty`, and the
requirement's `version`. On failure, `success: false` with an `error` message;
a stale `if_version` is rejected as a `version_conflict`.

## See Also

- [Configuration Reference](configuration.md)
