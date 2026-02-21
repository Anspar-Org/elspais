# elspais

> "L-Space is the ultimate library, connecting all libraries everywhere through the sheer weight of accumulated knowledge."
> — Terry Pratchett

**elspais** is a requirements validation and traceability tool that helps teams manage formal requirements across single or multiple repositories. It supports configurable ID patterns, validation rules, and generates traceability matrices.

## Features

- **Minimal Dependencies**: Core CLI requires only `tomlkit` (pure Python, no transitive deps)
- **Configurable ID Patterns**: Support for `REQ-p00001`, `PRD-00001`, `PROJ-123`, named requirements, and custom formats
- **Validation Rules**: Enforce requirement hierarchies (PRD → OPS → DEV) with configurable constraints
- **Multi-Repository**: Link requirements across core and associated repositories
- **Traceability Matrices**: Generate Markdown, HTML, or CSV output
- **Hash-Based Change Detection**: Track requirement changes with SHA-256 hashes
- **Content Rules**: Define semantic validation guidelines for AI agents
- **MCP Server**: Integrate with AI assistants via Model Context Protocol

## Installation

### For End Users

```bash
# Recommended: Isolated installation with pipx
pipx install elspais

# Or standard pip installation
pip install elspais
```

### For Development

```bash
git clone https://github.com/anspar/elspais.git
cd elspais
pip install -e ".[dev]"
```

### For Docker and CI/CD

For faster installation in containerized environments, consider [uv](https://github.com/astral-sh/uv):

```dockerfile
# Example Dockerfile
FROM python:3.11-slim

# Copy uv binary
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install elspais (10-100x faster than pip)
RUN uv pip install --system --no-cache elspais==0.24.3
```

```yaml
# Example GitHub Actions
- name: Install uv
  uses: astral-sh/setup-uv@v2

- name: Install elspais
  run: uv pip install --system elspais==0.24.3
```

**Note:** For regulated/medical software projects, always pin the exact version for reproducibility.

## Quick Start

### Initialize a Repository

```bash
# Create .elspais.toml with default configuration
elspais init

# Or specify repository type
elspais init --type core              # Core repository
elspais init --type associated --associated-prefix CAL  # Associated repo
```

### Validate Requirements

```bash
# Validate all requirements in spec/ directory
elspais validate

# Verbose output
elspais validate -v

# Auto-fix fixable issues (hashes, formatting)
elspais fix
```

### Generate Traceability Matrix

```bash
# Generate both Markdown and HTML
elspais trace

# Generate specific format
elspais trace --format html
elspais trace --format csv

# Custom output location
elspais trace --output docs/traceability.html
```

### Fix Issues

```bash
# Auto-fix all fixable issues (hashes, formatting)
elspais fix

# Preview fixes without applying
elspais fix --dry-run

# Fix specific requirement hash
elspais fix REQ-d00027
```

### Analyze Requirements

```bash
# Show requirement hierarchy tree
elspais analyze hierarchy

# Find orphaned requirements
elspais analyze orphans

# Implementation coverage report
elspais analyze coverage
```

## Configuration

Create `.elspais.toml` in your repository root:

```toml
[project]
name = "my-project"
type = "core"  # "core" | "associated"

[directories]
spec = "spec"
docs = "docs"
code = ["src", "apps", "packages"]

[patterns]
id_template = "{prefix}-{type}{id}"
prefix = "REQ"

[patterns.types]
prd = { id = "p", name = "Product Requirement", level = 1 }
ops = { id = "o", name = "Operations Requirement", level = 2 }
dev = { id = "d", name = "Development Requirement", level = 3 }

[patterns.id_format]
style = "numeric"
digits = 5
leading_zeros = true

[rules.hierarchy]
allowed_implements = [
    "dev -> ops, prd",
    "ops -> prd",
    "prd -> prd",
]
allow_circular = false
allow_orphans = false

[rules.format]
require_hash = true
require_assertions = true
allowed_statuses = ["Active", "Draft", "Deprecated", "Superseded"]
```

See [docs/configuration.md](docs/configuration.md) for full reference.

## Requirement Format

elspais expects requirements in Markdown format:

```markdown
# REQ-d00001: Requirement Title

**Level**: Dev | **Status**: Active | **Implements**: REQ-p00001

## Assertions

A. The system SHALL provide user authentication via email/password.
B. Sessions SHALL expire after 30 minutes of inactivity.

## Rationale

Security requires identity verification.

*End* *Requirement Title* | **Hash**: a1b2c3d4
---
```

Key format elements:
- **Assertions section**: Labeled A-Z, each using SHALL for normative statements
- **One-way traceability**: Children reference parents via `Implements:`
- **Hash footer**: SHA-256 hash for change detection

## ID Pattern Examples

elspais supports multiple ID formats:

| Pattern | Example | Configuration |
|---------|---------|---------------|
| HHT Default | `REQ-p00001` | `id_template = "{prefix}-{type}{id}"` |
| Type-Prefix | `PRD-00001` | `id_template = "{type}-{id}"` |
| Jira-Like | `PROJ-123` | `id_template = "{prefix}-{id}"` |
| Named | `REQ-UserAuth` | `style = "named"` |
| Associated | `REQ-CAL-d00001` | `associated.enabled = true` |

See [docs/patterns.md](docs/patterns.md) for details.

## Multi-Repository Support

For associated repositories that reference a core repository:

```toml
[project]
type = "associated"

[associated]
prefix = "CAL"

[core]
path = "../core-repo"
```

Validate without associated specs:

```bash
elspais validate --mode core
```

## Content Rules

Content rules are markdown files that provide semantic validation guidance for AI agents authoring requirements:

```bash
# Configure content rules
elspais config add rules.content_rules "spec/AI-AGENT.md"

# List configured rules
elspais rules list

# View a specific rule
elspais rules show AI-AGENT.md
```

Content rule files can include YAML frontmatter for metadata:

```markdown
---
title: AI Agent Guidelines
type: guidance
applies_to: [requirements, assertions]
---

# AI Agent Guidelines

- Use SHALL for normative statements
- One assertion per obligation
- No duplication across levels
```

## MCP Server (AI Integration)

elspais includes an MCP (Model Context Protocol) server for AI assistant integration:

```bash
# Install with MCP support
pip install elspais[mcp]

# Start MCP server
elspais mcp serve
```

Configure in Claude Desktop (`claude_desktop_config.json`):

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

### MCP Resources

| Resource | Description |
|----------|-------------|
| `requirements://all` | List all requirements |
| `requirements://{id}` | Get requirement details |
| `requirements://level/{level}` | Filter by PRD/OPS/DEV |
| `content-rules://list` | List content rules |
| `content-rules://{file}` | Get content rule content |
| `config://current` | Current configuration |

### MCP Tools

| Tool | Description |
|------|-------------|
| `get_workspace_info(detail=...)` | Project info with use-case profiles |
| `get_project_summary()` | Coverage stats, level counts, change metrics |
| `search()` | Search requirements by keyword |
| `get_requirement()` | Get requirement details with assertions |
| `get_hierarchy()` | Navigate parent/child relationships |
| `discover_requirements()` | Find most-specific matches in a subgraph |

The `get_workspace_info` tool accepts a `detail` parameter for task-specific
context: `"testing"`, `"code-refs"`, `"coverage"`, `"retrofit"`, `"manager"`,
`"worktree"`, or `"all"`.

## CLI Reference

```
elspais [OPTIONS] COMMAND [ARGS]

Options:
  --config PATH    Path to config file
  --spec-dir PATH  Override spec directory
  -v, --verbose    Verbose output
  -q, --quiet      Suppress non-error output
  --version        Show version
  --help           Show help

Commands:
  validate              Validate requirements format, links, and hashes
  health                Check graph and spec health (orphans, broken links)
  doctor                Diagnose environment and installation setup
  trace                 Generate traceability matrix
  fix                   Auto-fix spec file issues (hashes, formatting)
  index                 Manage INDEX.md file (validate, regenerate)
  analyze               Analyze requirement hierarchy (hierarchy, orphans, coverage)
  changed               Detect git changes to spec files
  version               Show version and check for updates
  init                  Create .elspais.toml configuration
  example               Generate example spec files for getting started
  edit                  Edit requirements in-place (implements, status, move)
  config                View and modify configuration (show, get, set, ...)
  rules                 View and manage content rules (list, show)
  docs                  View built-in documentation by topic
  associate             Manage associate repository links
  link                  Suggest and apply requirement links for test files
  pdf                   Compile spec files to PDF (requires elspais[pdf])
  completion            Generate shell completion scripts
  reformat-with-claude  Reformat requirements using AI (Acceptance Criteria -> Assertions)
  mcp                   MCP server commands (requires elspais[mcp])
  install               Install MCP server for Claude Code / Cursor
  uninstall             Uninstall MCP server registration
```

See [docs/commands.md](docs/commands.md) for comprehensive command documentation.

## Development

```bash
# Clone and install in development mode
git clone https://github.com/anspar/elspais.git
cd elspais
pip install -e ".[dev]"

# Enable git hooks (verifies docs stay in sync before push)
git config core.hooksPath .githooks

# Run tests
pytest

# Run with coverage
pytest --cov=elspais

# Type checking
mypy src/elspais

# Linting
ruff check src/elspais
black --check src/elspais
```

## Version Pinning

For reproducible builds, pin the version in your project:

```bash
# .github/versions.env
ELSPAIS_VERSION=0.24.3
```

```yaml
# GitHub Actions
- name: Install elspais
  run: pip install elspais==${{ env.ELSPAIS_VERSION }}
```

## License

MIT License - see [LICENSE](LICENSE) for details.

## Contributing

Contributions welcome! Please read the contributing guidelines before submitting PRs.

## Links

- [Documentation](https://github.com/anspar/elspais#readme)
- [Issue Tracker](https://github.com/anspar/elspais/issues)
- [Changelog](CHANGELOG.md)
