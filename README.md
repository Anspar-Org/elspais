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
elspais checks

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

# Each shell supplies the daemon's address before launching the client
eval "$(elspais mcp env)"
```

The MCP server provides tools for searching requirements, navigating hierarchies, checking coverage, and drafting mutations — all operating on the live traceability graph.

Mutations use optimistic concurrency: several writers (agents and the viewer GUI) can share one daemon, so every mutation requires a version token from a prior read and stale writes are rejected rather than silently overwriting. See `elspais docs concurrency` for the protocol.

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
namespace = "REQ"

[levels.prd]
rank = 1
letter = "p"
implements = ["prd"]

[levels.ops]
rank = 2
letter = "o"
implements = ["ops", "prd"]

[levels.dev]
rank = 3
letter = "d"
implements = ["dev", "ops", "prd"]

[scanning.spec]
directories = ["spec"]

[scanning.code]
directories = ["src"]

[id-patterns]
canonical = "{namespace}-{level.letter}{component}"

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
elspais checks
```

## CLI Commands

```
elspais checks         Verify requirements traceability and configuration
elspais fix            Auto-fix spec file issues (hashes, formatting)
elspais trace          Generate traceability matrix (markdown, html, csv)
elspais viewer         Start interactive viewer server
elspais doctor         Diagnose environment and installation health
elspais analysis       Analyze foundational requirement importance
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

Run `elspais <command> --help` for detailed usage. See [src/elspais/docs/cli/commands.md](src/elspais/docs/cli/commands.md) for full documentation.

## Development

```bash
git clone https://github.com/anspar/elspais.git
cd elspais
make setup
make test
```

`make setup` builds `.venv`, installs elspais into it, and installs the git
hooks. The hooks and the test targets both run the tools from that
directory, so what they report describes this checkout and not some other
installation of elspais.

Every dependency is installed at the version `requirements/dev.lock` pins, and
CI installs the same, so a test run here and in CI on the same Python minor
version see the same packages. After changing the dependencies in
`pyproject.toml`, run `make lock` and commit the regenerated lock with the
change; CI fails while the lock is out of date. Run `make setup` again when the
lock moves.

Where Claude Code is installed, `make setup` also registers the elspais MCP
server over http. The daemon behind it runs the program that started it, so
start it with this checkout's elspais before launching Claude Code:

```bash
eval "$(.venv/bin/elspais mcp env)"
claude
```

## License

GNU Affero General Public License v3 (AGPL-3.0) — see [LICENSE](LICENSE).

## Links

- [Changelog](CHANGELOG.md)
