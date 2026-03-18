# CLI COMMANDS REFERENCE

Complete reference for all elspais commands.

## Global Options

These options work with all commands:

  `-v, --verbose`    Verbose output with details
  `-q, --quiet`      Suppress non-error output
  `--config PATH`    Path to configuration file
  `--spec-dir PATH`  Override spec directory

## health

Run health checks across configuration, spec files, code, and tests.

  $ elspais health                     # Run all checks
  $ elspais health --spec              # Spec file checks
  $ elspais health --code              # Code reference checks
  $ elspais health --tests             # Test mapping checks
  $ elspais health --format json       # JSON output

To auto-fix issues, use: `elspais fix`

**Options:**

  `--spec`         Run spec file checks only
  `--code`         Run code reference checks only
  `--tests`        Run test mapping checks only
  `--format {text,markdown,json,junit,sarif}`  Output format (default: text)
  `--lenient`      Allow warnings without affecting exit code
  `--skip-passing-details`     Hide details for passing checks (default)
  `--include-passing-details`  Show full details for passing checks
  `-v, --verbose`  Show additional details

## fix

Auto-fix spec file issues (hashes, formatting).

  $ elspais fix                   # Fix all issues
  $ elspais fix --dry-run         # Preview fixes without applying
  $ elspais fix REQ-p00001        # Fix hash for a specific requirement
  $ elspais fix -m "Clarify auth" # Provide changelog reason

**Options:**

  `REQ_ID`        Specific requirement ID to fix (hash only)
  `--dry-run`     Show what would be fixed without making changes
  `-m, --message` Changelog reason for Active requirement hash updates
  `--mode {core,combined,associate}`  Scope of fix (default: combined)

## trace

Generate traceability matrix and reports.

  $ elspais trace                        # Markdown table (default)
  $ elspais trace --format html          # Basic HTML matrix
  $ elspais trace --format csv           # Spreadsheet export
  $ elspais trace --preset full          # All columns

**Options:**

  `--format {text,markdown,html,json,csv}`  Output format (default: markdown)
  `--preset {minimal,standard,full}`        Column preset
  `--body`               Show requirement body text
  `--assertions`         Show individual assertions
  `--tests`              Show test references
  `--output PATH`        Output file path

## viewer

Interactive traceability viewer (live server or static HTML).

  $ elspais viewer                  # Start server and open browser
  $ elspais viewer --static         # Generate static HTML file
  $ elspais viewer --server         # Start server without opening browser
  $ elspais viewer --path /my/repo  # Specify repository root

**Options:**

  `--static`          Generate static HTML file instead of live server
  `--server`          Start server without opening browser
  `--port PORT`       Server port (default: 5001)
  `--embed-content`   Embed full markdown in HTML for offline viewing
  `--path DIR`        Path to repository root (default: auto-detect)

## graph

Export the traceability graph structure as JSON.

  $ elspais graph                   # Print to stdout
  $ elspais graph -o graph.json     # Write to file

## pdf

Compile spec files into a PDF document.

  $ elspais pdf                              # Generate spec-output.pdf
  $ elspais pdf --output review.pdf          # Custom output path
  $ elspais pdf --title "My Project Specs"   # Custom title
  $ elspais pdf --overview                   # PRD-only stakeholder overview
  $ elspais pdf --overview --max-depth 2     # Overview with depth limit

**Options:**

  `--output PATH`       Output PDF file path (default: spec-output.pdf)
  `--engine ENGINE`     PDF engine: xelatex (default), lualatex, pdflatex
  `--template PATH`     Custom pandoc LaTeX template
  `--title TITLE`       Document title
  `--cover PATH`        Markdown file for custom cover page
  `--overview`          Generate stakeholder overview (PRD only, no OPS/DEV)
  `--max-depth N`       Max graph depth for core PRDs in overview mode

**Prerequisites:**

- pandoc: <https://pandoc.org/installing.html>
- xelatex: Install TeX Live, MiKTeX, or MacTeX

**Overview Mode:**

Generates a lighter document for stakeholders:
- Only PRD-level requirements from all repos
- No OPS or DEV requirements
- Default title: "Product Requirements Overview"
- `--max-depth` limits core PRD depth (associates always fully included)

## summary

Generate coverage summary reports.

  $ elspais summary                 # Coverage summary
  $ elspais summary --format json   # JSON output

**Options:**

  `--format {text,markdown,json,csv}`  Output format (default: text)

## changed

Detect git changes to spec files.

  $ elspais changed                       # Show all spec changes
  $ elspais changed --format json         # Output as JSON
  $ elspais changed -a                    # Include non-spec files

**Options:**

  `--base-branch BRANCH`  Base branch for comparison (default: main)
  `--format {text,json}`  Output format (default: text)
  `-a, --all`             Include all changed files, not just spec

**What's Detected:**

  Uncommitted changes (modified/new spec files)
  Changes vs main/master branch
  Moved requirements (relocated to different file)

## analysis

Analyze foundational requirement importance using graph metrics.

  $ elspais analysis                          # Default analysis
  $ elspais analysis -n 5 --show foundations  # Top 5 foundations only
  $ elspais analysis --format json            # JSON output

**Options:**

  `-n, --top N`         Number of top results per section (default: 10)
  `--weights W1,W2,W3,W4`  Centrality, fan-in, neighborhood, uncovered weights
  `--format {table,json}`  Output format (default: table)
  `--show {foundations,leaves,all}`  Which sections (default: all)
  `--level {prd,ops,dev}`  Filter by requirement level
  `--include-code`      Include CODE nodes in analysis graph

## edit

Edit requirements in-place.

  $ elspais edit REQ-d00001 --status Draft
  $ elspais edit REQ-d00001 --implements REQ-p00001,REQ-p00002
  $ elspais edit REQ-d00001 --move-to roadmap/future.md
  $ elspais edit --from-json edits.json

**Options:**

  `REQ_ID`              Requirement ID to edit (positional)
  `--implements REFS`   New Implements (comma-separated, "" to clear)
  `--status STATUS`     New Status value
  `--move-to FILE`      Move to file (relative to spec dir)
  `--from-json FILE`    Batch edit from JSON (- for stdin)
  `--dry-run`           Show changes without applying
  `--validate-refs`     Validate implements references exist

**Batch JSON Format:**

```json
[
  {"req_id": "REQ-d00001", "status": "Draft"},
  {"req_id": "REQ-d00002", "implements": ["REQ-p00001"]}
]
```

## config

View and modify configuration.

  $ elspais config show           # View all settings
  $ elspais config get patterns.prefix
  $ elspais config set project.name "MyApp"
  $ elspais config path           # Show config file location

**Subcommands:**

  `show [--section] [--format {text,json}]`  Show current configuration
  `get KEY [--format {text,json}]`           Get value (dot-notation: patterns.prefix)
  `set KEY VALUE`          Set value (auto-detects type)
  `unset KEY`              Remove a key
  `add KEY VALUE`          Add value to array
  `remove KEY VALUE`       Remove value from array
  `path`                   Show config file location

## init

Create .elspais.toml configuration.

  $ elspais init                  # Create default config
  $ elspais init --template       # Also create example requirement

**Options:**

  `--type {core,associated}`   Repository type
  `--associated-prefix PREFIX` Prefix for associated repo
  `--force`                    Overwrite existing configuration
  `--template`                 Create example requirement in spec/

## example

Display requirement format examples.

  $ elspais example               # Quick format reference
  $ elspais example --full        # Full specification document
  $ elspais example journey       # User journey template

**Arguments:**

  `requirement`  Full requirement template (default)
  `journey`      User journey template
  `assertion`    Assertion rules and examples
  `ids`          Show ID patterns from current config

**Options:**

  `--full`   Display full requirements specification file

## rules

View and manage content rules.

  $ elspais rules list            # List configured rules
  $ elspais rules show myfile.md  # Show rule file content

**Subcommands:**

  `list`        List configured content rules
  `show FILE`   Show content of a rule file

## docs

Read the user guide.

  $ elspais docs                  # Quickstart guide
  $ elspais docs config           # Configuration reference
  $ elspais docs all              # Complete documentation

**Arguments:**

  `quickstart`     Getting started guide (default)
  `format`         Requirement file format
  `hierarchy`      PRD/OPS/DEV levels
  `assertions`     Writing testable assertions
  `traceability`   Linking to code and tests
  `linking`        Code and test linking details
  `validation`     Running validation
  `git`            Change detection
  `config`         Configuration reference
  `commands`       This CLI reference
  `health`         Health check details
  `mcp`            MCP server for AI integration
  `all`            All topics concatenated

**Options:**

  `--plain`      Plain text output (no ANSI colors)
  `--no-pager`   Disable paging (print to stdout)

## version

Show version information.

  $ elspais version               # Show current version
  $ elspais --version             # Alternative

## doctor

Diagnose your elspais environment and installation.

  $ elspais doctor                # Quick setup check
  $ elspais doctor -v             # Detailed output
  $ elspais doctor --format json  # JSON output for CI

**What it checks:**

  Configuration file exists, syntax, required fields
  ID pattern placeholders and spec directory paths
  Git worktree detection and canonical root
  Associate paths and configurations
  Local configuration (.elspais.local.toml)

**Options:**

  `--format {text,json}`  Output format (default: text)
  `-v, --verbose`         Show detailed information for each check

## associate

Manage links to associated repositories.

  $ elspais associate /path/to/repo    # Link a specific associate
  $ elspais associate --all            # Auto-discover and link all
  $ elspais associate --list           # Show linked associates
  $ elspais associate --unlink NAME    # Remove a link

**Options:**

  `--all`            Auto-discover and link all associates
  `--list`           Show status of linked associates
  `--unlink NAME`    Remove a linked associate (matches name, path, or prefix code)

**Notes:**

  Links are stored in `.elspais.local.toml` (gitignored, not shared)
  Validates target has `project.type = "associated"` in its config
  Accepts a path or a name (searches sibling directories)
  Worktree-safe: resolves relative paths from canonical repo root

## link

Link suggestion tools for connecting tests to requirements.

  $ elspais link suggest                    # Suggest links for unlinked tests
  $ elspais link suggest --file test_auth.py  # Suggest for specific file
  $ elspais link suggest --apply            # Auto-apply suggestions

**Options:**

  `--file PATH`          Suggest for a specific file only
  `--format {text,json}` Output format (default: text)
  `--min-confidence {high,medium,low}`  Minimum confidence threshold
  `--limit N`            Maximum suggestions (default: 50)
  `--apply`              Auto-apply suggested links
  `--dry-run`            Show what would be applied without changes

## mcp

MCP (Model Context Protocol) server commands.

  $ elspais mcp install --global --desktop   # One-time setup
  $ elspais mcp serve                        # Start MCP server

**Note:** Requires `elspais[mcp]` extra.

**Subcommands:**

  `serve`      Start MCP server
  `install`    Register with Claude Code and/or Claude Desktop
  `uninstall`  Remove registration

**Options for install/uninstall:**

  `--global`   Claude Code: user scope (all projects) instead of current project
  `--desktop`  Also write to Claude Desktop config

**Options for serve:**

  `--transport {stdio,sse,streamable-http}`  Transport type (default: stdio)

## install / uninstall

Manage local development installations.

  $ elspais install local                # Install from local source
  $ elspais install local --tool uv      # Use uv instead of pipx
  $ elspais uninstall local              # Revert to PyPI version

**Options:**

  `--path PATH`    Source path for local install
  `--extras EXTRAS` Extra dependencies to include
  `--tool {pipx,uv}` Installation tool to use
