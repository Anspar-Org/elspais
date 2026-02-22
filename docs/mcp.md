# MCP Server Guide

This document provides comprehensive documentation for the elspais MCP (Model Context Protocol) server, which exposes requirements management functionality to AI agents.

## Table of Contents

- [Quick Start](#quick-start)
- [Tool Categories](#tool-categories)
- [Resources](#resources)
- [Common Workflows](#common-workflows)
- [Safety Patterns](#safety-patterns)
- [Tool Reference](#tool-reference)

## Quick Start

### Installation

```bash
# Register with Claude Code (all projects) and Claude Desktop
elspais mcp install --global --desktop

# Or Claude Code only (current project)
elspais mcp install

# Enable tab-completion (optional)
elspais completion --install
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
| `validate()` | Validate all requirements against format and hierarchy rules |
| `search()` | Search requirements by query pattern in specified fields |
| `get_requirement()` | Get complete details for a single requirement by ID |
| `analyze()` | Analyze requirement structure (hierarchy, orphans, coverage) |
| `parse_requirement()` | Parse requirement text and extract structured data |

### Graph Tools

Tools for navigating the traceability graph:

| Tool | Description |
|------|-------------|
| `get_graph_status()` | Check graph cache state, staleness, and node counts |
| `refresh_graph()` | Force rebuild of traceability graph from spec files |
| `get_hierarchy()` | Get ancestors and children for a requirement |
| `get_traceability_path()` | Full traceability tree from requirement to tests |
| `get_coverage_breakdown()` | Per-assertion coverage with implementing code and tests |
| `list_by_criteria()` | Filter requirements by level, status, or coverage |
| `show_requirement_context()` | Complete requirement context for auditor review |

### Mutation Tools

Tools that modify spec files:

| Tool | Description |
|------|-------------|
| `change_reference_type()` | Switch between Implements and Refines references |
| `specialize_reference()` | Convert REQ→REQ to REQ→Assertion reference |
| `move_requirement()` | Move requirement between spec files |

### File Operations

Tools for spec file management:

| Tool | Description |
|------|-------------|
| `prepare_file_deletion()` | Analyze file before deletion (check requirements, content) |
| `delete_spec_file()` | Delete spec file with safety checks |

### AI Tools

Tools for AI-assisted transformations:

| Tool | Description |
|------|-------------|
| `get_node_as_json()` | Full node serialization for AI processing |
| `transform_with_ai()` | AI-assisted requirement transformation with git safety |
| `restore_from_safety_branch()` | Restore repository from safety branch |
| `list_safety_branches()` | List all safety branches created by elspais |

### Annotation Tools

Session-scoped metadata that doesn't modify files:

| Tool | Description |
|------|-------------|
| `add_annotation()` | Add key-value annotation to a node |
| `get_annotations()` | Get all annotations for a node |
| `add_tag()` | Add lightweight tag to a node |
| `remove_tag()` | Remove tag from a node |
| `list_tagged()` | Get all nodes with a specific tag |
| `list_all_tags()` | Get all unique tags in use |
| `nodes_with_annotation()` | Find nodes with specific annotation key/value |
| `clear_annotations()` | Clear annotations for node or entire session |
| `annotation_stats()` | Get statistics about annotation store |

## Resources

Resources provide read-only data access via URI patterns:

### Requirements

| URI | Description |
|-----|-------------|
| `requirements://all` | List all requirements with summary info |
| `requirements://{req_id}` | Full details for specific requirement |
| `requirements://level/{level}` | Requirements filtered by level (PRD, OPS, DEV) |

### Content Rules

| URI | Description |
|-----|-------------|
| `content-rules://list` | List all configured content rule files |
| `content-rules://{filename}` | Content of specific rule file |

### Configuration

| URI | Description |
|-----|-------------|
| `config://current` | Current elspais configuration |

### Graph

| URI | Description |
|-----|-------------|
| `graph://status` | Graph cache state, staleness, node counts |
| `graph://validation` | Warnings and errors from last graph build |

### Traceability

| URI | Description |
|-----|-------------|
| `traceability://{req_id}` | Full tree path from requirement to tests |
| `coverage://{req_id}` | Per-assertion coverage breakdown |
| `hierarchy://{req_id}/ancestors` | Parent chain up to root |
| `hierarchy://{req_id}/descendants` | All children recursively |

## Common Workflows

### 1. Auditor Review Session

Systematic review of requirements and their coverage:

```
1. validate()                           # Check for format/hierarchy issues
2. list_by_criteria(has_gaps=True)      # Find requirements with coverage gaps
3. get_coverage_breakdown(req_id)       # Examine specific gaps
4. get_traceability_path(req_id)        # Trace to implementing tests
5. show_requirement_context(req_id)     # Full requirement for detailed review
6. add_tag(req_id, "needs-review")      # Mark for follow-up
```

### 2. Requirement Refactoring

Reorganizing requirements across files:

```
1. get_requirement(req_id)              # Understand current state
2. get_hierarchy(req_id)                # Check relationships
3. move_requirement(req_id, target)     # Move to new location
4. refresh_graph()                      # Rebuild traceability
5. validate()                           # Verify no broken links
```

### 3. Coverage Gap Investigation

Understanding why assertions lack coverage:

```
1. get_coverage_breakdown(req_id)       # See which assertions are uncovered
2. show_requirement_context(req_id)     # Read assertion text
3. get_traceability_path(req_id)        # See what IS covered
4. search("assertion text")             # Find related tests
```

### 4. Reference Type Correction

Fixing Implements vs Refines relationships:

```
1. get_requirement(source_id)           # Check current references
2. get_coverage_breakdown(target_id)    # Understand coverage impact
3. change_reference_type(source, target, "refines")  # Switch type
4. refresh_graph()                      # Rebuild with new semantics
```

### 5. AI-Assisted Transformation

Using Claude to reformat requirements:

```
1. get_node_as_json(req_id)             # Get full node data
2. transform_with_ai(req_id, prompt,    # Apply transformation
     save_branch=True, dry_run=True)    # Preview first
3. transform_with_ai(req_id, prompt,    # Apply for real
     save_branch=True, dry_run=False)
4. # If issues: restore_from_safety_branch(branch_name)
```

### 6. Hierarchy Cleanup

Finding and fixing orphaned requirements:

```
1. analyze("orphans")                   # Find orphans
2. get_hierarchy(orphan_id)             # Understand context
3. search("likely parent keywords")     # Find suitable parent
4. # Use change_reference_type() or edit spec file manually
```

## Safety Patterns

### Always Prepare Before Deletion

```python
# WRONG: Delete without checking
delete_spec_file(file_path, force=True)

# RIGHT: Analyze first
result = prepare_file_deletion(file_path)
if result["can_delete"]:
    delete_spec_file(file_path)
else:
    # Move requirements first with move_requirement()
```

### Use Git Safety for AI Transforms

```python
# WRONG: Transform without safety branch
transform_with_ai(req_id, prompt, save_branch=False)

# RIGHT: Always create safety branch
result = transform_with_ai(req_id, prompt, save_branch=True)
# If problems:
restore_from_safety_branch(result["safety_branch"])
```

### Preview with Dry Run

```python
# Preview transformation
preview = transform_with_ai(req_id, prompt, dry_run=True)
# Review preview["after_text"]

# Then apply
transform_with_ai(req_id, prompt, dry_run=False)
```

### Refresh Graph After Mutations

```python
# After any mutation tool
move_requirement(req_id, target)
refresh_graph()  # Graph cache is stale

# Or check staleness
status = get_graph_status()
if status["is_stale"]:
    refresh_graph()
```

## Tool Reference

### validate

Validate all requirements in the workspace.

**Parameters:**
- `skip_rules` (list[str], optional): Rule names to skip

**Returns:**
```json
{
  "valid": true,
  "errors": [],
  "warnings": [],
  "summary": "0 errors, 2 warnings in 45 requirements"
}
```

### search

Search requirements by pattern.

**Parameters:**
- `query` (str): Search query string
- `field` (str): "all", "id", "title", "body", "assertions"
- `regex` (bool): Treat query as regex pattern

**Returns:**
```json
{
  "count": 3,
  "query": "authentication",
  "field": "all",
  "requirements": [...]
}
```

### get_requirement

Get complete details for a single requirement.

**Parameters:**
- `req_id` (str): Requirement ID (e.g., "REQ-p00001")

**Returns:** Full requirement data including body, assertions, implements, location.

### get_traceability_path

Get full traceability from requirement to tests.

**Parameters:**
- `req_id` (str): Requirement ID
- `max_depth` (int): Maximum traversal depth (default: 99)

**Returns:**
```json
{
  "tree": {
    "id": "REQ-p00001",
    "kind": "requirement",
    "children": {
      "assertion": [...],
      "code": [...],
      "test": [...]
    }
  },
  "summary": {
    "total_assertions": 5,
    "covered_assertions": 3,
    "coverage_pct": 60.0,
    "total_tests": 8,
    "passed_tests": 8,
    "pass_rate_pct": 100.0
  }
}
```

### get_coverage_breakdown

Get per-assertion coverage details.

**Parameters:**
- `req_id` (str): Requirement ID

**Returns:**
```json
{
  "id": "REQ-p00001",
  "assertions": [
    {
      "id": "REQ-p00001-A",
      "label": "A. The system SHALL...",
      "covered": true,
      "coverage_source": "direct",
      "implementing_code": [...],
      "validating_tests": [...]
    }
  ],
  "gaps": ["REQ-p00001-C", "REQ-p00001-D"],
  "summary": {
    "total_assertions": 5,
    "covered_assertions": 3,
    "coverage_pct": 60.0,
    "direct_covered": 2,
    "explicit_covered": 1,
    "inferred_covered": 0
  }
}
```

### change_reference_type

Change a reference from Implements to Refines or vice versa.

**Parameters:**
- `source_id` (str): Requirement containing the reference
- `target_id` (str): Referenced requirement to change
- `new_type` (str): "implements" or "refines"

**Returns:**
```json
{
  "success": true,
  "source_id": "REQ-d00001",
  "target_id": "REQ-p00001",
  "old_type": "implements",
  "new_type": "refines",
  "file_path": "spec/dev-requirements.md"
}
```

### move_requirement

Move requirement between spec files.

**Parameters:**
- `req_id` (str): Requirement ID to move
- `target_file` (str): Destination file path (relative to workspace)
- `position` (str): "start", "end", or "after"
- `after_id` (str, optional): Requirement ID to insert after (required if position="after")

**Returns:**
```json
{
  "success": true,
  "req_id": "REQ-d00001",
  "source_file": "spec/old.md",
  "target_file": "spec/new.md",
  "position": "end"
}
```

### transform_with_ai

Transform a requirement using Claude.

**Parameters:**
- `node_id` (str): Requirement ID to transform
- `prompt` (str): Transformation instructions
- `output_mode` (str): "replace" (markdown) or "operations" (JSON)
- `save_branch` (bool): Create git safety branch before changes
- `dry_run` (bool): Preview without applying

**Returns:**
```json
{
  "success": true,
  "node_id": "REQ-d00001",
  "dry_run": false,
  "safety_branch": "elspais-safety-20240115-143022",
  "before_text": "...",
  "after_text": "...",
  "file_path": "spec/requirements.md"
}
```

## See Also

- [CLI Commands Reference](commands.md)
- [Configuration Reference](configuration.md)
- [Traceability Features](trace-view.md)
