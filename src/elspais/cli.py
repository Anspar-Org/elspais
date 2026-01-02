"""
elspais.cli - Command-line interface.

Main entry point for the elspais CLI tool.
"""

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from elspais import __version__
from elspais.commands import analyze, edit, hash_cmd, index, init, trace, validate


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
        elif args.command == "version":
            return version_command(args)
        elif args.command == "init":
            return init.run(args)
        elif args.command == "edit":
            return edit.run(args)
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


if __name__ == "__main__":
    sys.exit(main())
