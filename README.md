# elspais

> "L-Space is the ultimate library, connecting all libraries everywhere through the sheer weight of accumulated knowledge."
> — Terry Pratchett

**elspais** is a requirements validation and traceability tool for teams managing formal requirements across one or more repositories. It validates requirement formats, enforces hierarchy rules, tracks changes with content hashes, and generates traceability matrices linking requirements to code and tests.

## Installation

```bash
# Homebrew (macOS/Linux)
brew install anspar-org/anspar/elspais

# pipx (isolated install)
pipx install elspais

# pip
pip install elspais
```

### Optional extras

```bash
pip install elspais[trace-view]    # Static HTML traceability view
pip install elspais[trace-review]  # Interactive viewer server
pip install elspais[mcp]           # MCP server for AI integration
pip install elspais[all]           # Everything
```

## Quick Start

```bash
# Initialize configuration
elspais init

# Validate requirements
elspais validate

# Auto-fix hashes and formatting
elspais fix

# Generate traceability matrix
elspais trace --format html

# Interactive viewer (live server)
elspais viewer

# Built-in documentation
elspais docs
```

## MCP Server (AI Integration)

elspais includes an MCP server for use with Claude Code, Claude Desktop, and other MCP-compatible clients.

```bash
# Install the MCP extra
pip install elspais[mcp]

# Register with Claude Code (all projects) and Claude Desktop
elspais mcp install --global --desktop
```

The MCP server provides tools for searching requirements, navigating hierarchies, checking coverage, and drafting mutations — all operating on the live traceability graph.

## Requirement Format

Requirements are written in Markdown:

```markdown
# REQ-d00001: Requirement Title

**Level**: Dev | **Status**: Active | **Implements**: REQ-p00001

## Assertions

A. The system SHALL provide user authentication via email/password.
B. Sessions SHALL expire after 30 minutes of inactivity.

*End* *Requirement Title* | **Hash**: a1b2c3d4
---
```

- **Hierarchy**: PRD (product) → OPS (operations) → DEV (development)
- **Traceability**: Children reference parents via `Implements:`
- **Assertions**: Labeled A-Z, using SHALL for normative statements
- **Hash footer**: SHA-256 content hash for change detection

## Configuration

Create `.elspais.toml` in your repository root (or run `elspais init`):

```toml
[project]
name = "my-project"
type = "core"

[directories]
spec = "spec"
code = ["src"]

[patterns]
prefix = "REQ"
id_template = "{prefix}-{type}{id}"

[rules.hierarchy]
allowed_implements = ["dev -> ops, prd", "ops -> prd"]

[rules.format]
require_hash = true
require_assertions = true
```

See [docs/configuration.md](docs/configuration.md) for full reference.

## Multi-Repository Support

Link associated repositories that extend a core requirement set:

```bash
elspais init --type associated --associated-prefix CAL
elspais associate ../core-repo
elspais validate --mode combined
```

## CLI Commands

```
elspais validate       Validate requirements format, links, and hashes
elspais fix            Auto-fix spec file issues (hashes, formatting)
elspais trace          Generate traceability matrix (markdown, html, csv)
elspais viewer         Start interactive viewer server
elspais health         Check repository and configuration health
elspais doctor         Diagnose environment and installation health
elspais analyze        Analyze hierarchy, orphans, or coverage
elspais changed        Detect git changes to spec files
elspais edit           Edit requirements in-place
elspais config         View and modify configuration
elspais associate      Manage associate repository links
elspais link suggest   Suggest requirement links for unlinked tests
elspais pdf            Compile spec files into PDF
elspais mcp            MCP server commands
elspais docs           Built-in user guide
elspais example        Requirement format examples
```

Run `elspais <command> --help` for detailed usage. See [docs/cli/commands.md](docs/cli/commands.md) for full documentation.

## Development

```bash
git clone https://github.com/anspar/elspais.git
cd elspais
pip install -e ".[dev]"
pytest
```

## License

GNU Affero General Public License v3 (AGPL-3.0) — see [LICENSE](LICENSE).

## Links

- [Changelog](CHANGELOG.md)
