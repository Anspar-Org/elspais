"""
elspais.cli - Command-line interface.

Main entry point for the elspais CLI tool.
"""

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from elspais import __version__
from elspais.commands import analyze, changed, config_cmd, edit, hash_cmd, index, init, rules_cmd, trace, validate


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser."""
    parser = argparse.ArgumentParser(
        prog="elspais",
        description="Requirements validation and traceability tools (L-Space)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  elspais validate              # Validate all requirements
  elspais trace --format html   # Generate HTML traceability matrix
  elspais hash update           # Update all requirement hashes
  elspais init                  # Create .elspais.toml configuration
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
        "-v", "--verbose",
        action="store_true",
        help="Verbose output",
    )
    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Suppress non-error output",
    )

    # Subcommands
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # validate command
    validate_parser = subparsers.add_parser(
        "validate",
        help="Validate requirements format, links, and hashes",
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
        help="Skip specific validation rules",
        metavar="RULE",
    )
    validate_parser.add_argument(
        "-j", "--json",
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

    # trace command
    trace_parser = subparsers.add_parser(
        "trace",
        help="Generate traceability matrix",
    )
    trace_parser.add_argument(
        "--format",
        choices=["markdown", "html", "csv", "both"],
        default="both",
        help="Output format (default: both)",
    )
    trace_parser.add_argument(
        "--output",
        type=Path,
        help="Output file path",
        metavar="PATH",
    )

    # hash command
    hash_parser = subparsers.add_parser(
        "hash",
        help="Manage requirement hashes",
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
        help="Manage INDEX.md file",
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
        help="Analyze requirement hierarchy",
    )
    analyze_subparsers = analyze_parser.add_subparsers(dest="analyze_action")

    analyze_subparsers.add_parser(
        "hierarchy",
        help="Show requirement hierarchy tree",
    )
    analyze_subparsers.add_parser(
        "orphans",
        help="Find orphaned requirements",
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
        "-j", "--json",
        action="store_true",
        help="Output as JSON",
    )
    changed_parser.add_argument(
        "-a", "--all",
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
        help="Check for updates",
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

    # edit command
    edit_parser = subparsers.add_parser(
        "edit",
        help="Edit requirements in-place (implements, status, move)",
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
        help="View and modify configuration",
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
        "-j", "--json",
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
        "-j", "--json",
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
        help="Value to set (type auto-detected: true/false, numbers, JSON arrays/objects, or string)",
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
        help="View and manage content rules",
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
        elif args.command == "edit":
            return edit.run(args)
        elif args.command == "config":
            return config_cmd.run(args)
        elif args.command == "rules":
            return rules_cmd.run(args)
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

        print(f"Starting elspais MCP server...")
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
