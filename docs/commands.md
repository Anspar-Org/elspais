# CLI Commands Reference

This document provides comprehensive documentation for all elspais CLI commands.

## Table of Contents

- [validate](#validate)
- [fix](#fix)
- [trace](#trace)
- [changed](#changed)
- [analyze](#analyze)
- [edit](#edit)
- [config](#config)
- [rules](#rules)
- [index](#index)
- [init](#init)
- [mcp](#mcp)
- [version](#version)

## validate

Validate requirements format, links, and hashes.

### Usage

```bash
elspais validate [OPTIONS]
```

### Options

| Option | Description |
|--------|-------------|
| `-v, --verbose` | Show detailed validation output |
| `--export` | Export requirements as JSON dict keyed by ID |
| `--mode {core,combined}` | Validation mode: `core` scans only local specs, `combined` includes sponsor/associated repo specs (default: `combined`) |
| `--core-repo PATH` | Path to core repository for associated repo validation |

### Examples

```bash
# Basic validation
elspais validate

# Verbose output
elspais validate -v

# Validate only core/local requirements (exclude sponsors)
elspais validate --mode core

# Associated repo: validate with core linking
elspais validate --core-repo ../core-repo
```

### Exit Codes

- `0`: All validations passed
- `1`: Validation failures found

## trace

Generate traceability matrices in various formats.

### Usage

```bash
elspais trace [OPTIONS]
```

### Options

| Option | Description |
|--------|-------------|
| `--format {markdown,html,csv}` | Output format (default: markdown and html) |
| `-o, --output FILE` | Output file path |
| `--mode {core,combined}` | Include sponsor specs (default: combined) |
| `--sponsor NAME` | Filter to specific sponsor |
| `--view` | Generate interactive HTML view (requires `jinja2`) |
| `--embed-content` | Embed full requirement content in HTML |
| `--edit-mode` | Enable client-side editing features |
| `--review-mode` | Enable collaborative review annotations |
| `--server` | Start Flask review server (requires `flask`) |
| `--port PORT` | Server port (default: 8080) |

### Examples

```bash
# Generate markdown and HTML matrices
elspais trace

# Generate only HTML
elspais trace --format html -o matrix.html

# Generate CSV for spreadsheet import
elspais trace --format csv -o trace.csv

# Generate interactive trace-view HTML (requires elspais[trace-view])
elspais trace --view -o trace.html

# Start review server (requires elspais[trace-review])
elspais trace --server --port 8080
```

See [docs/trace-view.md](trace-view.md) for enhanced traceability features.

## fix

Auto-fix spec file issues (hashes, formatting).

### Usage

```bash
elspais fix [REQ_ID] [OPTIONS]
```

### Options

| Option | Description |
|--------|-------------|
| `REQ_ID` | Specific requirement ID to fix (hash only) |
| `--dry-run` | Show what would be fixed without making changes |

### Examples

```bash
# Fix all issues
elspais fix

# Preview fixes without applying
elspais fix --dry-run

# Fix hash for a specific requirement
elspais fix REQ-p00001
```

### Exit Codes

- `0`: All fixes applied successfully
- `1`: Fix failures encountered

## changed

Detect git changes to spec files and track requirement modifications.

### Usage

```bash
elspais changed [OPTIONS]
```

### Options

| Option | Description |
|--------|-------------|
| `--json` | Output changes as JSON |
| `--all` | Include all changed files, not just spec/ |
| `--base-branch BRANCH` | Compare vs different branch (default: main/master) |

### Examples

```bash
# Show uncommitted changes to spec files
elspais changed

# JSON output for programmatic use
elspais changed --json

# Include all files
elspais changed --all

# Compare vs develop branch
elspais changed --base-branch develop
```

### Output

The command reports:

- Modified spec files (uncommitted changes)
- Files changed vs base branch
- Requirements moved between files

## analyze

Analyze requirement hierarchy, coverage, and relationships.

### Usage

```bash
elspais analyze {hierarchy,orphans,coverage} [OPTIONS]
```

### Subcommands

#### hierarchy

Display requirement hierarchy as a tree.

```bash
elspais analyze hierarchy
```

#### orphans

Find requirements without parent (implements) links.

```bash
elspais analyze orphans
```

#### coverage

Generate implementation coverage report.

```bash
elspais analyze coverage
```

### Options

| Option | Description |
|--------|-------------|
| `--format {text,json}` | Output format |
| `--level {prd,ops,dev}` | Filter by requirement level |

## edit

Edit requirements in-place (status, implements, move).

### Usage

```bash
elspais edit {status,implements,move} [OPTIONS]
```

### Subcommands

#### status

Change requirement status.

```bash
# Set status to Deprecated
elspais edit status REQ-d00027 --status Deprecated
```

#### implements

Modify implements relationships.

```bash
# Add parent link
elspais edit implements REQ-d00027 --add REQ-p00001

# Remove parent link
elspais edit implements REQ-d00027 --remove REQ-p00001
```

#### move

Move requirement to different file.

```bash
# Move requirement
elspais edit move REQ-d00027 --to spec/new-location.md
```

## config

View and modify configuration settings.

### Usage

```bash
elspais config {get,set,add,remove,path} [OPTIONS]
```

### Subcommands

#### get

Get configuration value.

```bash
# Get single value
elspais config get project.name

# Get all config
elspais config get
```

#### set

Set configuration value.

```bash
elspais config set project.name "my-project"
elspais config set patterns.prefix "REQ"
```

#### add

Add value to array configuration.

```bash
elspais config add directories.code "apps"
```

#### remove

Remove value from array configuration.

```bash
elspais config remove directories.code "apps"
```

#### path

Show path to configuration file.

```bash
elspais config path
```

## rules

View and manage content rules (AI agent guidance).

### Usage

```bash
elspais rules {list,show} [OPTIONS]
```

### Subcommands

#### list

List configured content rules.

```bash
elspais rules list
```

#### show

Show content of a content rule file.

```bash
elspais rules show AI-AGENT.md
```

### Examples

```bash
# Configure content rules
elspais config add rules.content_rules "spec/AI-AGENT.md"

# List configured rules
elspais rules list

# View a specific rule
elspais rules show AI-AGENT.md
```

## index

Validate or regenerate INDEX.md files.

### Usage

```bash
elspais index {validate,generate} [OPTIONS]
```

### Subcommands

#### validate

Validate that INDEX.md is up-to-date.

```bash
elspais index validate
```

#### generate

Generate or update INDEX.md.

```bash
elspais index generate
```

## init

Create `.elspais.toml` configuration file.

### Usage

```bash
elspais init [OPTIONS]
```

### Options

| Option | Description |
|--------|-------------|
| `--type {core,associated}` | Repository type |
| `--associated-prefix PREFIX` | Prefix for associated repository |

### Examples

```bash
# Create default configuration
elspais init

# Create core repository config
elspais init --type core

# Create associated repository config
elspais init --type associated --associated-prefix CAL
```

## mcp

MCP (Model Context Protocol) server commands.

### Usage

```bash
elspais mcp serve [OPTIONS]
```

### Options

| Option | Description |
|--------|-------------|
| `--transport {stdio,sse}` | Transport type (default: stdio) |
| `--cwd PATH` | Working directory for finding .elspais.toml |

### Requirements

```bash
pip install elspais[mcp]
```

### Configuration

Add to Claude Desktop config (`~/.config/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "elspais": {
      "command": "elspais",
      "args": ["mcp", "serve"],
      "cwd": "/path/to/your/project"
    }
  }
}
```

For Claude Code, add to your project's `.mcp.json`:

```json
{
  "mcpServers": {
    "elspais": {
      "command": "elspais",
      "args": ["mcp", "serve"]
    }
  }
}
```

### Tool Categories

The MCP server exposes ~40 tools organized into categories:

- **Read-Only**: `validate()`, `search()`, `get_requirement()`, `analyze()`
- **Graph**: `get_graph_status()`, `get_hierarchy()`, `get_traceability_path()`, `get_coverage_breakdown()`
- **Mutation**: `change_reference_type()`, `specialize_reference()`, `move_requirement()`
- **File Ops**: `prepare_file_deletion()`, `delete_spec_file()`
- **AI Tools**: `get_node_as_json()`, `transform_with_ai()`
- **Annotations**: `add_annotation()`, `add_tag()`, `list_tagged()`

See [MCP Server Guide](mcp.md) for comprehensive documentation including:
- Complete tool reference
- Resource URI patterns
- Common workflows
- Safety patterns

## version

Show version and check for updates.

### Usage

```bash
elspais version
```

### Output

Displays:

- Current installed version
- Python version
- Platform information

## Global Options

These options work with all commands:

| Option | Description |
|--------|-------------|
| `--config PATH` | Path to config file |
| `--spec-dir PATH` | Override spec directory |
| `-v, --verbose` | Verbose output |
| `-q, --quiet` | Suppress non-error output |
| `--version` | Show version |
| `--help` | Show help |

## Exit Codes

All commands follow these conventions:

- `0`: Success
- `1`: Validation/operation failures
- `2`: Configuration/usage errors

## See Also

- [Configuration Reference](configuration.md)
- [Validation Rules](rules.md)
- [Multi-Repository Support](multi-repo.md)
- [Trace-View Features](trace-view.md)
- [Pattern Configuration](patterns.md)
- [MCP Server Guide](mcp.md)
