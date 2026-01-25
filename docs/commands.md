# CLI Commands Reference

This document provides comprehensive documentation for all elspais CLI commands.

## Table of Contents

- [validate](#validate)
- [trace](#trace)
- [hash](#hash)
- [reformat-with-claude](#reformat-with-claude)
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
| `--fix` | Automatically fix fixable issues |
| `--mode {core,combined}` | Validation mode: `core` scans only local specs, `combined` includes sponsor/associated repo specs (default: `combined`) |
| `--core-repo PATH` | Path to core repository for associated repo validation |

### Examples

```bash
# Basic validation
elspais validate

# Verbose output
elspais validate -v

# Auto-fix fixable issues
elspais validate --fix

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

## hash

Manage requirement hashes for change detection.

### Usage

```bash
elspais hash {verify,update} [ID]
```

### Subcommands

#### verify

Verify that requirement hashes match their content.

```bash
# Verify all requirements
elspais hash verify

# Verify specific requirement
elspais hash verify REQ-d00027
```

#### update

Update requirement hashes to match current content.

```bash
# Update all requirements
elspais hash update

# Update specific requirement
elspais hash update REQ-d00027
```

### Exit Codes

- `0`: All hashes valid (verify) or successfully updated (update)
- `1`: Hash mismatches found (verify) or update failures (update)

## reformat-with-claude

Transform requirements from legacy "Acceptance Criteria" format to the modern "Assertions" format using Claude AI. This command uses the Claude CLI to intelligently reformat requirements while preserving semantic meaning.

### Usage

```bash
elspais reformat-with-claude [OPTIONS]
```

### Options

| Option | Description |
|--------|-------------|
| `--start-req ID` | Starting requirement ID (default: all PRD requirements) |
| `--depth N` | Maximum traversal depth (default: unlimited) |
| `--dry-run` | Preview changes without modifying files |
| `--backup` | Create `.bak` files before editing |
| `--force` | Reformat even if already in new format |
| `--fix-line-breaks` | Normalize line breaks (remove extra blank lines) |
| `--line-breaks-only` | Only fix line breaks, skip AI-based reformatting |
| `--mode {combined,core-only,local-only}` | Which repos to include in hierarchy (default: `combined`) |
| `--verbose` | Show detailed progress and Claude API interactions |

### Mode Options

The `--mode` flag controls which repositories are included when building the requirement hierarchy for traversal:

- **`combined`** (default): Load both local and core/associated repository requirements. Use this when working in an associated repository that implements requirements from a core repository. This ensures proper hierarchy traversal where DEV requirements that implement core PRDs are included as children during traversal.

- **`core-only`**: Load only core/associated repository requirements. Useful when you want to analyze or reformat requirements from the core repository perspective only.

- **`local-only`**: Load only local requirements. Use this when working on a standalone repository or when you want to ignore cross-repository dependencies.

### How It Works

1. **Format Detection**: The command uses validation rules to identify requirements with `format.acceptance_criteria` violations (old format)

2. **Hierarchy Building**: Builds a complete dependency graph including cross-repository relationships (when mode is `combined`)

3. **Traversal**: Starting from specified requirement (or all PRD requirements), traverses the hierarchy depth-first

4. **AI Transformation**: For each requirement needing reformatting:
   - Extracts existing content using format detection
   - Sends to Claude CLI with structured prompt and JSON schema
   - Validates transformed output
   - Assembles new format with proper structure

5. **File Modification**: Updates requirement files in-place, preserving other requirements in the same file

### Format Transformation

Converts from legacy format:

```markdown
**Acceptance Criteria**:
- The system does X
- The system provides Y
- Must support Z
```

To modern format:

```markdown
## Assertions

A. The system SHALL do X.
B. The system SHALL provide Y.
C. The system SHALL support Z.
```

### Examples

```bash
# Preview changes (dry run)
elspais reformat-with-claude --dry-run

# Reformat with backups
elspais reformat-with-claude --backup

# Start from specific requirement
elspais reformat-with-claude --start-req REQ-p00010

# Reformat with cross-repo hierarchy (associated repo implementing core requirements)
elspais reformat-with-claude --mode combined

# Reformat only local requirements (ignore core dependencies)
elspais reformat-with-claude --mode local-only

# Limit traversal depth
elspais reformat-with-claude --start-req REQ-p00001 --depth 2

# Force reformat even if already in new format
elspais reformat-with-claude --force

# Only fix line breaks (no AI transformation)
elspais reformat-with-claude --line-breaks-only

# Verbose output to see Claude interactions
elspais reformat-with-claude --verbose
```

### Cross-Repository Hierarchy Support

When working in an associated repository that implements requirements from a core repository:

**Scenario**: You have:

- Core repo with `REQ-p00001` (PRD requirement)
- Associated repo with `REQ-d00027` that implements `REQ-p00001`

**Setup**: In your associated repo's `.elspais.toml`:

```toml
[project]
type = "associated"

[associated]
prefix = "CAL"

[core]
path = "../core-repo"
```

**Usage**:

```bash
# Reformat starting from core PRD, including associated DEV requirements
elspais reformat-with-claude --start-req REQ-p00001 --mode combined
```

This will:

1. Load requirements from both repositories
2. Build complete hierarchy graph with cross-repo links
3. Traverse from `REQ-p00001` → `REQ-d00027` and any other children
4. Only modify files in the local (associated) repository

### Performance Optimization

The command uses validation to pre-filter requirements before processing:

1. Runs `RuleEngine` validation to identify requirements with `format.acceptance_criteria` violations
2. Only processes requirements that actually use old format
3. Significantly reduces processing time (example: 322 → 9 requirements in test repo)

### Requirements

- **Claude CLI**: Must have `claude` command available in PATH
- **Configuration**: Claude CLI must be configured with API key
- **Format**: Requirements must be parseable by elspais parser

### Exit Codes

- `0`: All requirements successfully reformatted (or dry run completed)
- `1`: Errors occurred during reformatting

### Related Documentation

- [AI-Assisted Reformatting](trace-view.md#requirement-reformatting)
- [Configuration](configuration.md)
- [Multi-Repository Support](multi-repo.md)

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

See main README for MCP resources and tools.

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
