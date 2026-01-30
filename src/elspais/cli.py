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
    health,
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
        help="Auto-fix issues that can be corrected programmatically (hashes, status)",
    )
    validate_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be fixed without making changes (use with --fix)",
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
    # NOTE: --tests, --no-tests, --mode removed (dead code - never implemented)

    # health command
    health_parser = subparsers.add_parser(
        "health",
        help="Check repository and configuration health",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  elspais health              # Run all health checks
  elspais health --config     # Check config only
  elspais health --spec       # Check spec files only
  elspais health --code       # Check code references only
  elspais health --tests      # Check test mappings only
  elspais health -j           # Output JSON for tooling
  elspais health -v           # Verbose output with details

Checks performed:
  CONFIG: TOML syntax, required fields, pattern tokens, hierarchy rules, paths
  SPEC:   File parsing, duplicate IDs, reference resolution, orphans
  CODE:   Code→REQ reference validation, coverage statistics
  TESTS:  Test→REQ mappings, result status, coverage statistics
""",
    )
    health_parser.add_argument(
        "--config",
        dest="config_only",
        action="store_true",
        help="Run configuration checks only",
    )
    health_parser.add_argument(
        "--spec",
        dest="spec_only",
        action="store_true",
        help="Run spec file checks only",
    )
    health_parser.add_argument(
        "--code",
        dest="code_only",
        action="store_true",
        help="Run code reference checks only",
    )
    health_parser.add_argument(
        "--tests",
        dest="tests_only",
        action="store_true",
        help="Run test mapping checks only",
    )
    health_parser.add_argument(
        "-j",
        "--json",
        action="store_true",
        help="Output as JSON",
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
    # NOTE: --port, --mode, --sponsor, --graph removed (dead code - never implemented)
    # Graph-based trace options
    trace_parser.add_argument(
        "--graph-json",
        action="store_true",
        help="Output graph structure as JSON",
    )
    trace_parser.add_argument(
        "--report",
        choices=["minimal", "standard", "full"],
        help="Report preset to use (default: standard)",
    )
    # NOTE: --depth removed (dead code - never implemented)

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

    # reformat-with-claude command (NOT YET IMPLEMENTED - placeholder for future feature)
    subparsers.add_parser(
        "reformat-with-claude",
        help="[NOT IMPLEMENTED] Reformat requirements using AI (Acceptance Criteria -> Assertions)",
    )
    # NOTE: All arguments removed - command not yet implemented
    # See src/elspais/commands/reformat_cmd.py for planned features

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
  mcp          MCP server for AI integration
  all          Show complete documentation

Examples:
  elspais docs                  # Quick start guide
  elspais docs format           # Requirement format reference
  elspais docs all              # Complete documentation
  elspais docs all --no-pager   # Disable pager
""",
    )
    docs_parser.add_argument(
        "topic",
        nargs="?",
        default="quickstart",
        choices=[
            "quickstart",
            "format",
            "hierarchy",
            "assertions",
            "traceability",
            "validation",
            "git",
            "config",
            "commands",
            "health",
            "mcp",
            "all",
        ],
        help="Documentation topic (default: quickstart)",
    )
    docs_parser.add_argument(
        "--plain",
        action="store_true",
        help="Plain text output (no ANSI colors)",
    )
    docs_parser.add_argument(
        "--no-pager",
        action="store_true",
        help="Disable paging (print directly to stdout)",
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

    # Auto-detect git repository root and change to it
    # This ensures elspais works the same from any subdirectory
    import os

    from elspais.config import find_git_root

    original_cwd = Path.cwd()
    git_root = find_git_root(original_cwd)

    if git_root and git_root != original_cwd:
        os.chdir(git_root)
        if args.verbose:
            print(f"Working from repository root: {git_root}", file=sys.stderr)
    elif not git_root and args.verbose:
        print("Warning: Not in a git repository", file=sys.stderr)

    try:
        # Dispatch to command handlers
        if args.command == "validate":
            return validate.run(args)
        elif args.command == "health":
            return health.run(args)
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
    """Handle docs command - display user documentation from markdown files."""
    import pydoc

    from elspais.utilities.docs_loader import load_all_topics, load_topic
    from elspais.utilities.md_renderer import render_markdown

    topic = args.topic
    use_pager = not args.no_pager and sys.stdout.isatty()
    use_color = not args.plain and sys.stdout.isatty()

    # Load content from markdown files
    if topic == "all":
        content = load_all_topics()
    else:
        content = load_topic(topic)

    if content is None:
        print(f"Error: Documentation not found for topic '{topic}'", file=sys.stderr)
        print("Documentation files may not be installed correctly.", file=sys.stderr)
        return 1

    # Render markdown to ANSI and display
    output = render_markdown(content, use_color=use_color)

    if use_pager:
        pydoc.pager(output)
    else:
        print(output)

    return 0


def completion_command(args: argparse.Namespace) -> int:
    """Handle completion command - generate shell completion scripts."""
    import importlib.util

    if importlib.util.find_spec("argcomplete") is None:
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
        print(
            """
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
"""
        )

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
