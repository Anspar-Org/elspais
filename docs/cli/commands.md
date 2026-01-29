# CLI COMMANDS REFERENCE

Complete reference for all elspais commands.

## Global Options

These options work with all commands:

  `-v, --verbose`    Verbose output with details
  `-q, --quiet`      Suppress non-error output
  `--config PATH`    Path to configuration file
  `--spec-dir PATH`  Override spec directory

## validate

Validate requirements format, links, hashes, and hierarchy.

  $ elspais validate              # Check all rules
  $ elspais validate --fix        # Auto-fix fixable issues
  $ elspais validate -j           # Output JSON for tooling

**Options:**

  `--fix`               Auto-fix hashes and formatting issues
  `--skip-rule RULE`    Skip validation rules (repeatable)
  `--core-repo PATH`    Path to core repo (associated repo validation)
  `-j, --json`          Output requirements as JSON
  `--tests`             Force test scanning
  `--no-tests`          Skip test scanning
  `--mode {core,combined}`  Scope: this repo or include sponsors

**Skip Rule Patterns:**

  `hash.*`        All hash rules
  `hash.missing`  Hash footer is missing
  `hash.mismatch` Hash doesn't match content
  `hierarchy.*`   All hierarchy rules
  `format.*`      All format rules

## trace

Generate traceability matrix and reports.

  $ elspais trace --view          # Interactive HTML view
  $ elspais trace --format html   # Basic HTML matrix
  $ elspais trace --graph-json    # Export graph as JSON

**Options:**

  `--format {markdown,html,csv,both}`  Output format (default: both)
  `--output PATH`          Output file path
  `--view`                 Interactive HTML traceability tree
  `--embed-content`        Embed full markdown in HTML for offline
  `--graph`                Use unified traceability graph
  `--graph-json`           Output graph structure as JSON
  `--report NAME`          Report preset (minimal, standard, full)
  `--depth LEVEL`          Max graph depth (0=roots, 1=children, ...)
  `--mode {core,sponsor,combined}`  Report scope
  `--sponsor NAME`         Sponsor name for filtered reports

**Depth Levels:**

  `0` or `requirements`    Show only requirements
  `1` or `assertions`      Include assertions
  `2` or `implementation`  Include code references
  `full`                   Unlimited depth

**Planned Options (not yet implemented):**

  `--edit-mode`    In-browser editing of implements/status
  `--review-mode`  Collaborative review with comments
  `--server`       Start review server
  `--port PORT`    Port for review server

## hash

Manage requirement content hashes.

  $ elspais hash verify           # Check without changes
  $ elspais hash update           # Update all hashes
  $ elspais hash update REQ-p00001  # Update specific

**Subcommands:**

  `verify`            Verify hashes without modifying files
  `update [REQ_ID]`   Update hashes (optionally for one requirement)

**Options for update:**

  `--dry-run`   Show changes without applying

## analyze

Analyze requirement hierarchy and coverage.

  $ elspais analyze hierarchy     # Tree view of requirements
  $ elspais analyze orphans       # Find parentless requirements
  $ elspais analyze coverage      # Implementation coverage report

**Subcommands:**

  `hierarchy`   Show requirement hierarchy tree
  `orphans`     Find requirements with no parent
  `coverage`    Implementation coverage report

## changed

Detect git changes to spec files.

  $ elspais changed               # Show all spec changes
  $ elspais changed -j            # Output as JSON
  $ elspais changed -a            # Include non-spec files

**Options:**

  `--base-branch BRANCH`  Base branch for comparison (default: main)
  `-j, --json`            Output as JSON
  `-a, --all`             Include all changed files, not just spec

**What's Detected:**

  Uncommitted changes (modified/new spec files)
  Changes vs main/master branch
  Moved requirements (relocated to different file)

## index

Manage INDEX.md file.

  $ elspais index validate       # Check accuracy
  $ elspais index regenerate     # Rebuild from scratch

**Subcommands:**

  `validate`     Validate INDEX.md matches actual requirements
  `regenerate`   Regenerate INDEX.md from current spec files

## edit

Edit requirements in-place.

  $ elspais edit --req-id REQ-d00001 --status Draft
  $ elspais edit --req-id REQ-d00001 --implements REQ-p00001,REQ-p00002
  $ elspais edit --req-id REQ-d00001 --move-to roadmap/future.md
  $ elspais edit --from-json edits.json

**Options:**

  `--req-id ID`         Requirement ID to edit
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

  `show [--section] [-j]`  Show current configuration
  `get KEY [-j]`           Get value (dot-notation: patterns.prefix)
  `set KEY VALUE`          Set value (auto-detects type)
  `unset KEY`              Remove a key
  `add KEY VALUE`          Add value to array
  `remove KEY VALUE`       Remove value from array
  `path`                   Show config file location

**Examples:**

  $ elspais config get rules.strict_mode
  $ elspais config set rules.strict_mode true
  $ elspais config add directories.code src/lib
  $ elspais config unset associated.prefix

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
  `validation`     Running validation
  `git`            Change detection
  `config`         Configuration reference
  `commands`       This CLI reference
  `mcp`            MCP server for AI integration
  `all`            All topics concatenated

**Options:**

  `--plain`      Plain text output (no ANSI colors)
  `--no-pager`   Disable paging (print to stdout)

## completion

Generate shell tab-completion scripts.

  $ elspais completion            # Instructions
  $ elspais completion --shell bash > ~/.elspais-complete.bash

**Options:**

  `--shell {bash,zsh,fish,tcsh}`  Generate for specific shell

**Setup:**

Bash: `source <(elspais completion --shell bash)`
Zsh:  Add to ~/.zshrc: `eval "$(elspais completion --shell zsh)"`
Fish: `elspais completion --shell fish | source`

## version

Show version information.

  $ elspais version               # Show current version
  $ elspais --version             # Alternative

## mcp

MCP (Model Context Protocol) server commands.

  $ elspais mcp serve             # Start MCP server

**Note:** Requires `elspais[mcp]` extra:

  $ pip install 'elspais[mcp]'

**Subcommands:**

  `serve`   Start MCP server

**Options for serve:**

  `--transport {stdio,sse,streamable-http}`  Transport type (default: stdio)
