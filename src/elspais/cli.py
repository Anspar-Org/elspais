"""
elspais.cli - Command-line interface.

Main entry point for the elspais CLI tool.
"""

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from elspais import __version__
from elspais.commands import (
    analyze,
    changed,
    config_cmd,
    edit,
    example_cmd,
    hash_cmd,
    index,
    init,
    reformat_cmd,
    rules_cmd,
    trace,
    validate,
)


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser."""
    parser = argparse.ArgumentParser(
        prog="elspais",
        description="Requirements validation and traceability tools (L-Space)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  elspais validate              # Validate all requirements
  elspais validate --fix        # Auto-fix fixable issues
  elspais trace --format html   # Generate HTML traceability matrix
  elspais trace --view          # Interactive HTML view
  elspais hash update           # Update all requirement hashes
  elspais changed               # Show uncommitted spec changes
  elspais analyze hierarchy     # Show requirement hierarchy tree

Configuration:
  elspais init                  # Create .elspais.toml in current directory
  elspais config path           # Show config file location
  elspais config show           # View all settings
  elspais config --help         # Configuration guide with examples

Documentation:
  elspais example               # Quick requirement format reference
  elspais example --full        # Full specification document
  elspais completion            # Shell tab-completion setup

For detailed command help: elspais <command> --help
        """,
    )

    # Global options
    parser.add_argument(
        "--version",
        action="version",
        version=f"elspais {__version__}",
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="Path to configuration file",
        metavar="PATH",
    )
    parser.add_argument(
        "--spec-dir",
        type=Path,
        help="Override spec directory",
        metavar="PATH",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Verbose output",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Suppress non-error output",
    )

    # Subcommands
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # validate command
    validate_parser = subparsers.add_parser(
        "validate",
        help="Validate requirements format, links, and hashes",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  elspais validate                      # Validate all requirements
  elspais validate --fix                # Auto-fix hashes and formatting
  elspais validate --skip-rule hash.*   # Skip all hash rules
  elspais validate -j                   # Output JSON for tooling
  elspais validate --mode core          # Exclude associated repo specs

Common rules to skip:
  hash.missing     Hash footer is missing
  hash.mismatch    Hash doesn't match content
  hierarchy.*      All hierarchy rules
  format.*         All format rules
""",
    )
    validate_parser.add_argument(
        "--fix",
        action="store_true",
        help="Auto-fix fixable issues",
    )
    validate_parser.add_argument(
        "--core-repo",
        type=Path,
        help="Path to core repository (for associated repo validation)",
        metavar="PATH",
    )
    validate_parser.add_argument(
        "--skip-rule",
        action="append",
        help="Skip validation rules (can be repeated, e.g., hash.*, format.*)",
        metavar="RULE",
    )
    validate_parser.add_argument(
        "-j",
        "--json",
        action="store_true",
        help="Output requirements as JSON (hht_diary compatible format)",
    )
    validate_parser.add_argument(
        "--tests",
        action="store_true",
        help="Force test scanning even if disabled in config",
    )
    validate_parser.add_argument(
        "--no-tests",
        action="store_true",
        help="Skip test scanning",
    )
    validate_parser.add_argument(
        "--mode",
        choices=["core", "combined"],
        default="combined",
        help="Scope: core (this repo only), combined (include sponsor repos)",
    )

    # trace command
    trace_parser = subparsers.add_parser(
        "trace",
        help="Generate traceability matrix",
    )
    trace_parser.add_argument(
        "--format",
        choices=["markdown", "html", "csv", "both"],
        default="both",
        help="Output format: markdown, html, csv, or both (markdown + csv)",
    )
    trace_parser.add_argument(
        "--output",
        type=Path,
        help="Output file path",
        metavar="PATH",
    )
    # trace-view enhanced options (requires elspais[trace-view])
    trace_parser.add_argument(
        "--view",
        action="store_true",
        help="Generate interactive HTML traceability view (requires trace-view extra)",
    )
    trace_parser.add_argument(
        "--embed-content",
        action="store_true",
        help="Embed full requirement markdown in HTML for offline viewing",
    )
    trace_parser.add_argument(
        "--edit-mode",
        action="store_true",
        help="Enable in-browser editing of implements and status fields",
    )
    trace_parser.add_argument(
        "--review-mode",
        action="store_true",
        help="Enable collaborative review with comments and flags",
    )
    trace_parser.add_argument(
        "--server",
        action="store_true",
        help="Start review server (requires trace-review extra)",
    )
    trace_parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port for review server (default: 8080)",
    )
    trace_parser.add_argument(
        "--mode",
        choices=["core", "sponsor", "combined"],
        default="core",
        help="Report mode: core, sponsor, or combined (default: core)",
    )
    trace_parser.add_argument(
        "--sponsor",
        help="Sponsor name for sponsor-specific reports",
        metavar="NAME",
    )
    # Graph-based trace options
    trace_parser.add_argument(
        "--graph",
        action="store_true",
        help="Use unified traceability graph (includes assertions as nodes)",
    )
    trace_parser.add_argument(
        "--graph-json",
        action="store_true",
        help="Output graph structure as JSON",
    )
    trace_parser.add_argument(
        "--report",
        metavar="NAME",
        help="Report preset to use (minimal, standard, full, or custom)",
    )
    trace_parser.add_argument(
        "--depth",
        metavar="LEVEL",
        help=(
            "Maximum graph depth to display. Can be a number (0=roots, 1=children, ...) "
            "or a named level: requirements (1), assertions (2), implementation (3), "
            "full (unlimited)"
        ),
    )

    # hash command
    hash_parser = subparsers.add_parser(
        "hash",
        help="Manage requirement hashes (verify, update)",
    )
    hash_subparsers = hash_parser.add_subparsers(dest="hash_action")

    hash_subparsers.add_parser(
        "verify",
        help="Verify hashes without changes",
    )

    hash_update = hash_subparsers.add_parser(
        "update",
        help="Update hashes",
    )
    hash_update.add_argument(
        "req_id",
        nargs="?",
        help="Specific requirement ID to update",
    )
    hash_update.add_argument(
        "--dry-run",
        action="store_true",
        help="Show changes without applying",
    )

    # index command
    index_parser = subparsers.add_parser(
        "index",
        help="Manage INDEX.md file (validate, regenerate)",
    )
    index_subparsers = index_parser.add_subparsers(dest="index_action")

    index_subparsers.add_parser(
        "validate",
        help="Validate INDEX.md accuracy",
    )
    index_subparsers.add_parser(
        "regenerate",
        help="Regenerate INDEX.md from scratch",
    )

    # analyze command
    analyze_parser = subparsers.add_parser(
        "analyze",
        help="Analyze requirement hierarchy (hierarchy, orphans, coverage)",
    )
    analyze_subparsers = analyze_parser.add_subparsers(dest="analyze_action")

    analyze_subparsers.add_parser(
        "hierarchy",
        help="Show requirement hierarchy tree",
    )
    analyze_subparsers.add_parser(
        "orphans",
        help="Find requirements with no parent (missing or invalid Implements)",
    )
    analyze_subparsers.add_parser(
        "coverage",
        help="Implementation coverage report",
    )

    # changed command
    changed_parser = subparsers.add_parser(
        "changed",
        help="Detect git changes to spec files",
    )
    changed_parser.add_argument(
        "--base-branch",
        default="main",
        help="Base branch for comparison (default: main)",
        metavar="BRANCH",
    )
    changed_parser.add_argument(
        "-j",
        "--json",
        action="store_true",
        help="Output as JSON",
    )
    changed_parser.add_argument(
        "-a",
        "--all",
        action="store_true",
        help="Include all changed files (not just spec)",
    )

    # version command
    version_parser = subparsers.add_parser(
        "version",
        help="Show version and check for updates",
    )
    version_parser.add_argument(
        "check",
        nargs="?",
        help="Check for updates (not yet implemented)",
    )

    # init command
    init_parser = subparsers.add_parser(
        "init",
        help="Create .elspais.toml configuration",
    )
    init_parser.add_argument(
        "--type",
        choices=["core", "associated"],
        help="Repository type",
    )
    init_parser.add_argument(
        "--associated-prefix",
        help="Associated repo prefix (e.g., CAL)",
        metavar="PREFIX",
    )
    init_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing configuration",
    )
    init_parser.add_argument(
        "--template",
        action="store_true",
        help="Create an example requirement file in spec/",
    )

    # example command
    example_parser = subparsers.add_parser(
        "example",
        help="Display requirement format examples and templates",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Subcommands:
  elspais example             Quick reference (default)
  elspais example requirement Full requirement template with all sections
  elspais example journey     User journey template
  elspais example assertion   Assertion rules and examples
  elspais example ids         Show ID patterns from current config
  elspais example --full      Display spec/requirements-spec.md (if exists)
""",
    )
    example_parser.add_argument(
        "example_type",
        nargs="?",
        choices=["requirement", "journey", "assertion", "ids"],
        help="Example type to display",
    )
    example_parser.add_argument(
        "--full",
        action="store_true",
        help="Display the full requirements specification file",
    )

    # edit command
    edit_parser = subparsers.add_parser(
        "edit",
        help="Edit requirements in-place (implements, status, move)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  elspais edit --req-id REQ-d00001 --status Draft
  elspais edit --req-id REQ-d00001 --implements REQ-p00001,REQ-p00002
  elspais edit --req-id REQ-d00001 --move-to roadmap/future.md
  elspais edit --from-json edits.json

JSON batch format:
  [{"req_id": "...", "status": "...", "implements": [...]}]
""",
    )
    edit_parser.add_argument(
        "--req-id",
        help="Requirement ID to edit",
        metavar="ID",
    )
    edit_parser.add_argument(
        "--implements",
        help="New Implements value (comma-separated, empty string to clear)",
        metavar="REFS",
    )
    edit_parser.add_argument(
        "--status",
        help="New Status value",
        metavar="STATUS",
    )
    edit_parser.add_argument(
        "--move-to",
        help="Move requirement to file (relative to spec dir)",
        metavar="FILE",
    )
    edit_parser.add_argument(
        "--from-json",
        help="Batch edit from JSON file (- for stdin)",
        metavar="FILE",
    )
    edit_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show changes without applying",
    )
    edit_parser.add_argument(
        "--validate-refs",
        action="store_true",
        help="Validate that implements references exist",
    )

    # config command
    config_parser = subparsers.add_parser(
        "config",
        help="View and modify configuration (show, get, set, ...)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Configuration File:
  elspais looks for .elspais.toml in the current directory or parent directories.
  Create one with: elspais init

  Location: elspais config path
  View all: elspais config show

Quick Start (.elspais.toml):
  [project]
  name = "my-project"
  spec_dir = "spec"              # Where requirement files live

  [patterns]
  prefix = "REQ"                 # Requirement ID prefix
  separator = "-"                # ID separator (REQ-p00001)

  [rules]
  strict_mode = false            # Strict implements semantics

  [rules.hierarchy]
  allowed = ["dev -> ops, prd", "ops -> prd"]

Common Commands:
  elspais config show            # View current config
  elspais config get patterns.prefix
  elspais config set project.name "MyApp"
  elspais config path            # Show config file location

Full Documentation:
  See docs/configuration.md for all options.
""",
    )
    config_subparsers = config_parser.add_subparsers(dest="config_action")

    # config show
    config_show = config_subparsers.add_parser(
        "show",
        help="Show current configuration",
    )
    config_show.add_argument(
        "--section",
        help="Show only a specific section (e.g., 'patterns', 'rules.format')",
        metavar="SECTION",
    )
    config_show.add_argument(
        "-j",
        "--json",
        action="store_true",
        help="Output as JSON",
    )

    # config get
    config_get = config_subparsers.add_parser(
        "get",
        help="Get a configuration value",
    )
    config_get.add_argument(
        "key",
        help="Configuration key (dot-notation, e.g., 'patterns.prefix')",
    )
    config_get.add_argument(
        "-j",
        "--json",
        action="store_true",
        help="Output as JSON",
    )

    # config set
    config_set = config_subparsers.add_parser(
        "set",
        help="Set a configuration value",
    )
    config_set.add_argument(
        "key",
        help="Configuration key (dot-notation, e.g., 'patterns.prefix')",
    )
    config_set.add_argument(
        "value",
        help="Value to set (auto-detected: bool, number, JSON array/object, string)",
    )

    # config unset
    config_unset = config_subparsers.add_parser(
        "unset",
        help="Remove a configuration key",
    )
    config_unset.add_argument(
        "key",
        help="Configuration key to remove",
    )

    # config add
    config_add = config_subparsers.add_parser(
        "add",
        help="Add a value to an array configuration",
    )
    config_add.add_argument(
        "key",
        help="Configuration key for array (e.g., 'directories.code')",
    )
    config_add.add_argument(
        "value",
        help="Value to add to the array",
    )

    # config remove
    config_remove = config_subparsers.add_parser(
        "remove",
        help="Remove a value from an array configuration",
    )
    config_remove.add_argument(
        "key",
        help="Configuration key for array (e.g., 'directories.code')",
    )
    config_remove.add_argument(
        "value",
        help="Value to remove from the array",
    )

    # config path
    config_subparsers.add_parser(
        "path",
        help="Show path to configuration file",
    )

    # rules command
    rules_parser = subparsers.add_parser(
        "rules",
        help="View and manage content rules (list, show)",
    )
    rules_subparsers = rules_parser.add_subparsers(dest="rules_action")

    # rules list
    rules_subparsers.add_parser(
        "list",
        help="List configured content rules",
    )

    # rules show
    rules_show = rules_subparsers.add_parser(
        "show",
        help="Show content of a content rule file",
    )
    rules_show.add_argument(
        "file",
        help="Content rule file name (e.g., 'AI-AGENT.md')",
    )

    # reformat-with-claude command
    reformat_parser = subparsers.add_parser(
        "reformat-with-claude",
        help="Reformat requirements using AI (Acceptance Criteria -> Assertions)",
    )
    reformat_parser.add_argument(
        "--start-req",
        help="Starting requirement ID (default: all PRD requirements)",
        metavar="ID",
    )
    reformat_parser.add_argument(
        "--depth",
        type=int,
        help="Maximum traversal depth (default: unlimited)",
    )
    reformat_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without applying",
    )
    reformat_parser.add_argument(
        "--backup",
        action="store_true",
        help="Create .bak files before editing",
    )
    reformat_parser.add_argument(
        "--force",
        action="store_true",
        help="Reformat even if already in new format",
    )
    reformat_parser.add_argument(
        "--fix-line-breaks",
        action="store_true",
        help="Normalize line breaks (remove extra blank lines)",
    )
    reformat_parser.add_argument(
        "--line-breaks-only",
        action="store_true",
        help="Only fix line breaks, skip AI-based reformatting",
    )
    reformat_parser.add_argument(
        "--mode",
        choices=["combined", "core-only", "local-only"],
        default="combined",
        help="Which repos to include in hierarchy (default: combined)",
    )

    # docs command - comprehensive user documentation
    docs_parser = subparsers.add_parser(
        "docs",
        help="Read the user guide (topics: quickstart, format, hierarchy, ...)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Available Topics:
  quickstart   Getting started with elspais (default)
  format       Requirement file format and structure
  hierarchy    PRD → OPS → DEV levels and implements
  assertions   Writing testable assertions with SHALL
  traceability Linking requirements to code and tests
  validation   Running validation and fixing issues
  git          Change detection and git integration
  config       Configuration file reference
  all          Show complete documentation

Examples:
  elspais docs                  # Quick start guide
  elspais docs format           # Requirement format reference
  elspais docs all              # Complete documentation
  elspais docs all | less       # Page through docs
""",
    )
    docs_parser.add_argument(
        "topic",
        nargs="?",
        default="quickstart",
        choices=["quickstart", "format", "hierarchy", "assertions",
                 "traceability", "validation", "git", "config", "all"],
        help="Documentation topic (default: quickstart)",
    )
    docs_parser.add_argument(
        "--plain",
        action="store_true",
        help="Plain text output (no ANSI colors)",
    )

    # completion command - shell tab-completion setup
    completion_parser = subparsers.add_parser(
        "completion",
        help="Generate shell tab-completion scripts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Shell Completion Setup:

  First, install the completion extra:
    pip install elspais[completion]

  Bash (add to ~/.bashrc):
    eval "$(register-python-argcomplete elspais)"

  Zsh (add to ~/.zshrc):
    autoload -U bashcompinit
    bashcompinit
    eval "$(register-python-argcomplete elspais)"

  Fish (add to ~/.config/fish/config.fish):
    register-python-argcomplete --shell fish elspais | source

  Tcsh (add to ~/.tcshrc):
    eval `register-python-argcomplete --shell tcsh elspais`

  Global activation (for all argcomplete-enabled tools):
    activate-global-python-argcomplete

After adding the appropriate line, restart your shell or source the config file.
""",
    )
    completion_parser.add_argument(
        "--shell",
        choices=["bash", "zsh", "fish", "tcsh"],
        help="Generate script for specific shell",
    )

    # mcp command
    mcp_parser = subparsers.add_parser(
        "mcp",
        help="MCP server commands (requires elspais[mcp])",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Claude Code Configuration:
  Add to ~/.claude/claude_desktop_config.json:

    {
      "mcpServers": {
        "elspais": {
          "command": "elspais",
          "args": ["mcp", "serve"],
          "cwd": "/path/to/your/project"
        }
      }
    }

  Set "cwd" to the directory containing your .elspais.toml config.

Resources:
  requirements://all           List all requirements
  requirements://{id}          Get requirement details
  requirements://level/{level} Filter by PRD/OPS/DEV
  content-rules://list         List content rules
  content-rules://{file}       Get content rule content
  config://current             Current configuration

Tools:
  validate          Run validation rules
  parse_requirement Parse requirement text
  search            Search requirements by pattern
  get_requirement   Get requirement details
  analyze           Analyze hierarchy/orphans/coverage
""",
    )
    mcp_subparsers = mcp_parser.add_subparsers(dest="mcp_action")

    # mcp serve
    mcp_serve = mcp_subparsers.add_parser(
        "serve",
        help="Start MCP server",
    )
    mcp_serve.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        default="stdio",
        help="Transport type (default: stdio)",
    )

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """
    Main entry point for the CLI.

    Args:
        argv: Command line arguments (defaults to sys.argv[1:])

    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    parser = create_parser()

    # Enable shell tab-completion if argcomplete is installed
    # Install with: pip install elspais[completion]
    # Then activate: eval "$(register-python-argcomplete elspais)"
    try:
        import argcomplete

        argcomplete.autocomplete(parser)
    except ImportError:
        pass

    args = parser.parse_args(argv)

    # Handle no command
    if not args.command:
        parser.print_help()
        return 0

    try:
        # Dispatch to command handlers
        if args.command == "validate":
            return validate.run(args)
        elif args.command == "trace":
            return trace.run(args)
        elif args.command == "hash":
            return hash_cmd.run(args)
        elif args.command == "index":
            return index.run(args)
        elif args.command == "analyze":
            return analyze.run(args)
        elif args.command == "changed":
            return changed.run(args)
        elif args.command == "version":
            return version_command(args)
        elif args.command == "init":
            return init.run(args)
        elif args.command == "example":
            return example_cmd.run(args)
        elif args.command == "edit":
            return edit.run(args)
        elif args.command == "config":
            return config_cmd.run(args)
        elif args.command == "rules":
            return rules_cmd.run(args)
        elif args.command == "reformat-with-claude":
            return reformat_cmd.run(args)
        elif args.command == "docs":
            return docs_command(args)
        elif args.command == "completion":
            return completion_command(args)
        elif args.command == "mcp":
            return mcp_command(args)
        else:
            parser.print_help()
            return 1

    except KeyboardInterrupt:
        print("\nOperation cancelled.", file=sys.stderr)
        return 130
    except Exception as e:
        if args.verbose:
            raise
        print(f"Error: {e}", file=sys.stderr)
        return 1


def docs_command(args: argparse.Namespace) -> int:
    """Handle docs command - display user documentation."""
    topic = args.topic
    use_color = not args.plain and sys.stdout.isatty()

    # ANSI color codes
    BOLD = "\033[1m" if use_color else ""
    CYAN = "\033[36m" if use_color else ""
    GREEN = "\033[32m" if use_color else ""
    YELLOW = "\033[33m" if use_color else ""
    RESET = "\033[0m" if use_color else ""
    DIM = "\033[2m" if use_color else ""

    def heading(text: str) -> str:
        return f"\n{BOLD}{CYAN}{'═' * 60}{RESET}\n{BOLD}{text}{RESET}\n{BOLD}{CYAN}{'═' * 60}{RESET}\n"

    def subheading(text: str) -> str:
        return f"\n{BOLD}{GREEN}{text}{RESET}\n{DIM}{'─' * 40}{RESET}\n"

    docs = {}

    docs["quickstart"] = f"""{heading("ELSPAIS QUICK START GUIDE")}

{BOLD}elspais{RESET} validates requirements and traces them through code to tests.
Requirements live as Markdown files in your {CYAN}spec/{RESET} directory.

{subheading("1. Initialize Your Project")}

  {GREEN}${RESET} elspais init              {DIM}# Creates .elspais.toml{RESET}
  {GREEN}${RESET} elspais init --template   {DIM}# Also creates example requirement{RESET}

{subheading("2. Write Your First Requirement")}

Create {CYAN}spec/prd-auth.md{RESET}:

  {DIM}# REQ-p00001: User Authentication{RESET}
  {DIM}{RESET}
  {DIM}**Level**: PRD | **Status**: Active{RESET}
  {DIM}{RESET}
  {DIM}**Purpose:** Enable secure user login.{RESET}
  {DIM}{RESET}
  {DIM}## Assertions{RESET}
  {DIM}{RESET}
  {DIM}A. The system SHALL authenticate users via email and password.{RESET}
  {DIM}B. The system SHALL lock accounts after 5 failed login attempts.{RESET}
  {DIM}{RESET}
  {DIM}*End* *User Authentication* | **Hash**: 00000000{RESET}

{subheading("3. Validate and Update Hashes")}

  {GREEN}${RESET} elspais validate     {DIM}# Check format, links, hierarchy{RESET}
  {GREEN}${RESET} elspais hash update  {DIM}# Compute content hashes{RESET}

{subheading("4. Create Implementing Requirements")}

DEV requirements implement PRD requirements:

  {DIM}# REQ-d00001: Password Hashing{RESET}
  {DIM}{RESET}
  {DIM}**Level**: DEV | **Status**: Active | **Implements**: REQ-p00001-A{RESET}
  {DIM}{RESET}
  {DIM}## Assertions{RESET}
  {DIM}{RESET}
  {DIM}A. The system SHALL use bcrypt with cost factor 12.{RESET}

{subheading("5. Generate Traceability Report")}

  {GREEN}${RESET} elspais trace --view   {DIM}# Interactive HTML tree{RESET}
  {GREEN}${RESET} elspais trace --format html -o trace.html{RESET}

{subheading("Next Steps")}

  {GREEN}${RESET} elspais docs format      {DIM}# Full format reference{RESET}
  {GREEN}${RESET} elspais docs hierarchy   {DIM}# Learn about PRD/OPS/DEV{RESET}
  {GREEN}${RESET} elspais docs all         {DIM}# Complete documentation{RESET}
"""

    docs["format"] = f"""{heading("REQUIREMENT FORMAT REFERENCE")}

{subheading("File Structure")}

Requirements are Markdown files in {CYAN}spec/{RESET}. Each file can contain
one or more requirements separated by {CYAN}---{RESET} (horizontal rule).

Naming convention: {CYAN}spec/<level>-<topic>.md{RESET}
  Examples: {DIM}spec/prd-auth.md, spec/dev-api.md{RESET}

{subheading("Requirement Structure")}

  {CYAN}# REQ-p00001: Human-Readable Title{RESET}

  {CYAN}**Level**: PRD | **Status**: Active | **Implements**: none{RESET}

  {CYAN}**Purpose:** One-line description of why this requirement exists.{RESET}

  {CYAN}## Assertions{RESET}

  {CYAN}A. The system SHALL do something specific and testable.{RESET}
  {CYAN}B. The system SHALL NOT do something prohibited.{RESET}

  {CYAN}*End* *Human-Readable Title* | **Hash**: a1b2c3d4{RESET}

{subheading("ID Format")}

  {BOLD}REQ-<type><number>{RESET}

  Types:
    {GREEN}p{RESET} = PRD (Product)     e.g., REQ-p00001
    {GREEN}o{RESET} = OPS (Operations)  e.g., REQ-o00001
    {GREEN}d{RESET} = DEV (Development) e.g., REQ-d00001

  The shorthand {GREEN}p00001{RESET} can be used in displays (without REQ- prefix).

{subheading("Header Line Fields")}

  {BOLD}Level{RESET}:      PRD, OPS, or DEV (determines hierarchy position)
  {BOLD}Status{RESET}:     Active, Draft, Deprecated, or Proposed
  {BOLD}Implements{RESET}: Parent requirement ID(s), comma-separated
  {BOLD}Refines{RESET}:    Parent ID when adding detail without claiming coverage

{subheading("Hash")}

The 8-character hash is computed from the requirement body content.
When content changes, the hash changes, triggering review.

  {GREEN}${RESET} elspais hash update   {DIM}# Recompute all hashes{RESET}
  {GREEN}${RESET} elspais hash verify   {DIM}# Check for stale hashes{RESET}

{subheading("Multiple Requirements Per File")}

Separate requirements with a horizontal rule:

  {DIM}# REQ-p00001: First Requirement{RESET}
  {DIM}...{RESET}
  {DIM}*End* *First Requirement* | **Hash**: ...\n{RESET}
  {DIM}---{RESET}
  {DIM}# REQ-p00002: Second Requirement{RESET}
  {DIM}...{RESET}
"""

    docs["hierarchy"] = f"""{heading("REQUIREMENT HIERARCHY")}

{subheading("The Three Levels")}

elspais enforces a {BOLD}PRD → OPS → DEV{RESET} hierarchy:

  {BOLD}PRD (Product){RESET}    - Business needs, user outcomes
                     "What the product must achieve"

  {BOLD}OPS (Operations){RESET} - Operational constraints, compliance
                     "How the system must behave operationally"

  {BOLD}DEV (Development){RESET} - Technical specifications
                     "How we implement it technically"

{subheading("Implements Relationships")}

Lower levels {BOLD}implement{RESET} higher levels:

  DEV → OPS   {DIM}(DEV implements OPS){RESET}
  DEV → PRD   {DIM}(DEV implements PRD){RESET}
  OPS → PRD   {DIM}(OPS implements PRD){RESET}

{YELLOW}Never{RESET} the reverse: PRD cannot implement DEV.

Example chain:

  {GREEN}REQ-p00001{RESET}: Users can reset passwords (PRD)
       ↑
  {GREEN}REQ-o00001{RESET}: Reset tokens expire in 1 hour (OPS)
       ↑           Implements: REQ-p00001
  {GREEN}REQ-d00001{RESET}: Tokens use HMAC-SHA256 (DEV)
                   Implements: REQ-o00001

{subheading("Implements vs Refines")}

  {BOLD}Implements{RESET} - Claims to satisfy the parent requirement
               Coverage rolls up in traceability reports

  {BOLD}Refines{RESET}    - Adds detail to parent without claiming satisfaction
               No coverage rollup; just shows relationship

Use {CYAN}Refines{RESET} when you're adding constraints but the parent still
needs its own implementation.

{subheading("Assertion-Specific Implementation")}

Implement specific assertions, not the whole requirement:

  {DIM}**Implements**: REQ-p00001-A{RESET}    {DIM}# Just assertion A{RESET}
  {DIM}**Implements**: REQ-p00001-A-B{RESET}  {DIM}# Assertions A and B{RESET}

This gives precise traceability coverage.

{subheading("Viewing the Hierarchy")}

  {GREEN}${RESET} elspais analyze hierarchy  {DIM}# ASCII tree view{RESET}
  {GREEN}${RESET} elspais trace --view       {DIM}# Interactive HTML{RESET}
"""

    docs["assertions"] = f"""{heading("WRITING ASSERTIONS")}

{subheading("What is an Assertion?")}

An assertion is a single, testable statement about system behavior.
Each assertion:
  • Uses {BOLD}SHALL{RESET} or {BOLD}SHALL NOT{RESET} (normative language)
  • Is labeled A, B, C, etc.
  • Can be independently verified by a test

{subheading("Assertion Format")}

  {CYAN}## Assertions{RESET}

  {CYAN}A. The system SHALL authenticate users via email and password.{RESET}
  {CYAN}B. The system SHALL lock accounts after 5 failed attempts.{RESET}
  {CYAN}C. The system SHALL NOT store passwords in plain text.{RESET}

{subheading("Normative Keywords")}

  {BOLD}SHALL{RESET}         Absolute requirement (must be implemented)
  {BOLD}SHALL NOT{RESET}     Absolute prohibition (must never happen)
  {BOLD}SHOULD{RESET}        Recommended but not required
  {BOLD}SHOULD NOT{RESET}    Not recommended but not prohibited
  {BOLD}MAY{RESET}           Optional behavior

Most assertions use {BOLD}SHALL{RESET} or {BOLD}SHALL NOT{RESET}.

{subheading("Good vs Bad Assertions")}

{GREEN}Good{RESET} (testable, specific):
  A. The system SHALL respond to API requests within 200ms.
  B. The system SHALL encrypt data at rest using AES-256.

{YELLOW}Bad{RESET} (vague, untestable):
  A. The system should be fast.
  B. The system must be secure.

{subheading("Referencing Assertions")}

In implementing requirements:
  {DIM}**Implements**: REQ-p00001-A{RESET}

In code comments:
  {DIM}# Implements: REQ-p00001-A{RESET}

In tests:
  {DIM}def test_login():{RESET}
  {DIM}    \"\"\"REQ-p00001-A: Verify email/password auth\"\"\"{RESET}

{subheading("Removed Assertions")}

If you remove an assertion, keep a placeholder to maintain letter sequence:

  {DIM}A. The system SHALL do X.{RESET}
  {DIM}B. [Removed - superseded by REQ-d00005]{RESET}
  {DIM}C. The system SHALL do Z.{RESET}
"""

    docs["traceability"] = f"""{heading("TRACEABILITY")}

{subheading("What is Traceability?")}

Traceability connects requirements to their implementations and tests:

  {BOLD}Requirement{RESET} → {BOLD}Assertion{RESET} → {BOLD}Code{RESET} → {BOLD}Test{RESET} → {BOLD}Result{RESET}

This answers: "How do we know this requirement is satisfied?"

{subheading("Marking Code as Implementing")}

In Python, JavaScript, Go, etc., use comments:

  {DIM}# Implements: REQ-d00001-A{RESET}
  {DIM}def hash_password(plain: str) -> str:{RESET}
  {DIM}    ...{RESET}

Or:
  {DIM}// Implements: REQ-d00001{RESET}
  {DIM}function hashPassword(plain) {{ ... }}{RESET}

{subheading("Marking Tests as Validating")}

Reference requirement IDs in test docstrings or names:

  {DIM}def test_password_uses_bcrypt():{RESET}
  {DIM}    \"\"\"REQ-d00001-A: Verify bcrypt with cost 12\"\"\"{RESET}
  {DIM}    ...{RESET}

Or in test names:
  {DIM}def test_REQ_d00001_A_bcrypt_cost():{RESET}

{subheading("Generating Reports")}

  {GREEN}${RESET} elspais trace --view         {DIM}# Interactive HTML tree{RESET}
  {GREEN}${RESET} elspais trace --format html  {DIM}# Basic HTML matrix{RESET}
  {GREEN}${RESET} elspais trace --format csv   {DIM}# Spreadsheet export{RESET}
  {GREEN}${RESET} elspais trace --graph        {DIM}# Full requirement→code→test graph{RESET}

{subheading("Coverage Indicators")}

In trace view:
  {BOLD}○{RESET} None    - No code implements this assertion
  {BOLD}◐{RESET} Partial - Some assertions have implementations
  {BOLD}●{RESET} Full    - All assertions have implementations
  {BOLD}⚡{RESET} Failure - Test failures detected

{subheading("Understanding the Graph")}

  {GREEN}${RESET} elspais trace --graph-json  {DIM}# Export as JSON{RESET}

The graph shows:
  • Requirements and their assertions
  • Which code files implement which assertions
  • Which tests validate which requirements
  • Test pass/fail status from JUnit/pytest results
"""

    docs["validation"] = f"""{heading("VALIDATION")}

{subheading("Running Validation")}

  {GREEN}${RESET} elspais validate          {DIM}# Check all rules{RESET}
  {GREEN}${RESET} elspais validate --fix    {DIM}# Auto-fix what's fixable{RESET}
  {GREEN}${RESET} elspais validate -v       {DIM}# Verbose output{RESET}

{subheading("What Gets Validated")}

  {BOLD}Format{RESET}      - Header line structure, hash presence
  {BOLD}Hierarchy{RESET}   - Implements relationships follow level rules
  {BOLD}Links{RESET}       - Referenced requirements exist
  {BOLD}Hashes{RESET}      - Content matches stored hash
  {BOLD}IDs{RESET}         - No duplicate requirement IDs

{subheading("Common Validation Errors")}

  {YELLOW}Missing hash{RESET}
    Fix: {GREEN}elspais hash update{RESET}

  {YELLOW}Stale hash{RESET} (content changed)
    Fix: {GREEN}elspais hash update{RESET} after reviewing changes

  {YELLOW}Broken link{RESET} (implements non-existent requirement)
    Fix: Correct the ID or create the missing requirement

  {YELLOW}Hierarchy violation{RESET} (PRD implements DEV)
    Fix: Reverse the relationship or change levels

{subheading("Suppressing Warnings")}

For expected issues, add inline suppression:

  {DIM}# elspais: expected-broken-links 2{RESET}
  {DIM}**Implements**: REQ-future-001, REQ-future-002{RESET}

{subheading("CI Integration")}

Add to your CI pipeline:

  {DIM}# .github/workflows/validate.yml{RESET}
  {DIM}steps:{RESET}
  {DIM}  - uses: actions/checkout@v4{RESET}
  {DIM}  - run: pip install elspais{RESET}
  {DIM}  - run: elspais validate{RESET}
"""

    docs["git"] = f"""{heading("GIT INTEGRATION")}

{subheading("Detecting Changes")}

  {GREEN}${RESET} elspais changed            {DIM}# Show all spec changes{RESET}
  {GREEN}${RESET} elspais changed --staged   {DIM}# Only staged changes{RESET}
  {GREEN}${RESET} elspais changed --hash     {DIM}# Only hash mismatches{RESET}

{subheading("What 'Changed' Detects")}

  {BOLD}Uncommitted{RESET} - Modified/untracked spec files
  {BOLD}Hash mismatch{RESET} - Content changed but hash not updated
  {BOLD}Moved{RESET} - Requirement relocated to different file
  {BOLD}vs Main{RESET} - Changes compared to main/master branch

{subheading("In Trace View")}

The interactive trace view ({CYAN}elspais trace --view{RESET}) shows:

  {YELLOW}◆{RESET} Changed vs main branch (diamond indicator)
  Filter buttons: {DIM}[Uncommitted] [Changed vs Main]{RESET}

{subheading("Pre-Commit Hook Example")}

  {DIM}#!/bin/sh{RESET}
  {DIM}# .git/hooks/pre-commit{RESET}
  {DIM}elspais validate || exit 1{RESET}
  {DIM}elspais hash verify || echo "Warning: stale hashes"{RESET}

{subheading("Workflow")}

1. Edit requirements
2. {GREEN}elspais validate{RESET} - Check format
3. {GREEN}elspais hash update{RESET} - Update hashes
4. {GREEN}elspais changed{RESET} - Review what changed
5. Commit with message referencing requirement IDs
"""

    docs["config"] = f"""{heading("CONFIGURATION")}

{subheading("Configuration File")}

elspais looks for {CYAN}.elspais.toml{RESET} in the current directory
or parent directories.

  {GREEN}${RESET} elspais init          {DIM}# Create default config{RESET}
  {GREEN}${RESET} elspais config path   {DIM}# Show config location{RESET}
  {GREEN}${RESET} elspais config show   {DIM}# View all settings{RESET}

{subheading("Basic Configuration")}

{CYAN}.elspais.toml{RESET}:

  {DIM}[project]{RESET}
  {DIM}name = "my-project"{RESET}
  {DIM}spec_dir = "spec"          # Requirement file location{RESET}

  {DIM}[patterns]{RESET}
  {DIM}prefix = "REQ"             # ID prefix (REQ-p00001){RESET}
  {DIM}separator = "-"            # ID separator{RESET}

  {DIM}[rules]{RESET}
  {DIM}strict_mode = false        # Strict implements semantics{RESET}

  {DIM}[rules.hierarchy]{RESET}
  {DIM}allowed = [{RESET}
  {DIM}    "dev -> ops, prd",     # DEV can implement OPS or PRD{RESET}
  {DIM}    "ops -> prd"           # OPS can implement PRD{RESET}
  {DIM}]{RESET}

{subheading("Config Commands")}

  {GREEN}${RESET} elspais config get patterns.prefix
  {GREEN}${RESET} elspais config set project.name "NewName"
  {GREEN}${RESET} elspais config unset rules.strict_mode

{subheading("Skip Directories")}

Exclude directories from scanning:

  {DIM}[project]{RESET}
  {DIM}skip_dirs = ["spec/archive", "spec/drafts"]{RESET}

{subheading("Multi-Repository")}

For associated/sponsor repositories:

  {DIM}[associated]{RESET}
  {DIM}prefix = "TTN"             # Their ID prefix{RESET}
  {DIM}repo_path = "../titan-spec"{RESET}
"""

    # Combine all topics for 'all'
    all_content = ""
    for topic_name in ["quickstart", "format", "hierarchy", "assertions",
                       "traceability", "validation", "git", "config"]:
        all_content += docs[topic_name] + "\n"
    docs["all"] = all_content

    # Display requested topic
    if topic in docs:
        print(docs[topic])
    else:
        print(f"Unknown topic: {topic}", file=sys.stderr)
        return 1

    return 0


def completion_command(args: argparse.Namespace) -> int:
    """Handle completion command - generate shell completion scripts."""
    try:
        import argcomplete
    except ImportError:
        print("Error: argcomplete not installed.", file=sys.stderr)
        print("Install with: pip install elspais[completion]", file=sys.stderr)
        return 1

    shell = args.shell

    if shell:
        # Generate script for specific shell
        import subprocess

        shell_flag = f"--shell={shell}" if shell in ("fish", "tcsh") else ""
        cmd = ["register-python-argcomplete"]
        if shell_flag:
            cmd.append(shell_flag)
        cmd.append("elspais")

        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                print(result.stdout)
            else:
                print(f"Error generating completion script: {result.stderr}", file=sys.stderr)
                return 1
        except FileNotFoundError:
            print("Error: register-python-argcomplete not found.", file=sys.stderr)
            print("Make sure argcomplete is properly installed.", file=sys.stderr)
            return 1
    else:
        # Show setup instructions
        print("""
Shell Completion Setup for elspais
===================================

Bash (add to ~/.bashrc):
  eval "$(register-python-argcomplete elspais)"

Zsh (add to ~/.zshrc):
  autoload -U bashcompinit
  bashcompinit
  eval "$(register-python-argcomplete elspais)"

Fish (add to ~/.config/fish/config.fish):
  register-python-argcomplete --shell fish elspais | source

Tcsh (add to ~/.tcshrc):
  eval `register-python-argcomplete --shell tcsh elspais`

Generate script for a specific shell:
  elspais completion --shell bash
  elspais completion --shell zsh
  elspais completion --shell fish
  elspais completion --shell tcsh

After adding the line, restart your shell or source the config file.
""")

    return 0


def version_command(args: argparse.Namespace) -> int:
    """Handle version command."""
    print(f"elspais {__version__}")

    if args.check:
        print("Checking for updates...")
        # TODO: Implement update check
        print("Update check not yet implemented.")

    return 0


def mcp_command(args: argparse.Namespace) -> int:
    """Handle MCP server commands."""
    try:
        from elspais.mcp.server import run_server
    except ImportError:
        print("Error: MCP dependencies not installed.", file=sys.stderr)
        print("Install with: pip install elspais[mcp]", file=sys.stderr)
        return 1

    if args.mcp_action == "serve":
        working_dir = Path.cwd()
        if hasattr(args, "spec_dir") and args.spec_dir:
            working_dir = args.spec_dir.parent

        print("Starting elspais MCP server...")
        print(f"Working directory: {working_dir}")
        print(f"Transport: {args.transport}")

        try:
            run_server(working_dir=working_dir, transport=args.transport)
        except KeyboardInterrupt:
            print("\nServer stopped.")
        return 0
    else:
        print("Usage: elspais mcp serve")
        return 1


if __name__ == "__main__":
    sys.exit(main())
