# Implements: REQ-int-d00008 (Reformat Command)
"""
elspais.commands.reformat_cmd - Reformat requirements using AI.

Transforms requirements from old format (Acceptance Criteria) to new format
(labeled Assertions). Also provides line break normalization.

REQ-int-d00008-A: Format transformation SHALL be available via
                  `elspais reformat-with-claude`.
REQ-int-d00008-B: The command SHALL support --dry-run, --backup, --start-req flags.
REQ-int-d00008-C: Line break normalization SHALL be included.
"""

import argparse
import sys
from pathlib import Path


def run(args: argparse.Namespace) -> int:
    """Run the reformat-with-claude command.

    This command reformats requirements from the old Acceptance Criteria format
    to the new Assertions format using Claude AI.
    """
    # TODO: Full implementation pending - Phase 6 of integration
    print("elspais reformat-with-claude")
    print()

    if args.line_breaks_only:
        return run_line_breaks_only(args)

    # Check for required components
    try:
        from elspais.reformat import (
            get_all_requirements,
            build_hierarchy,
            traverse_top_down,
            needs_reformatting,
            reformat_requirement,
        )
    except ImportError:
        print("Error: Reformat module not yet fully ported.", file=sys.stderr)
        print("This feature is under development.", file=sys.stderr)
        return 1

    # Configuration
    start_req = args.start_req
    depth = args.depth
    dry_run = args.dry_run
    backup = args.backup
    force = args.force

    print(f"Options:")
    print(f"  Start REQ:     {start_req or 'All PRD requirements'}")
    print(f"  Max depth:     {depth or 'Unlimited'}")
    print(f"  Dry run:       {dry_run}")
    print(f"  Backup:        {backup}")
    print(f"  Force:         {force}")
    print()

    if dry_run:
        print("DRY RUN MODE - no changes will be made")
        print()

    # Placeholder for actual implementation
    print("Feature under development. Full implementation pending.")
    return 0


def run_line_breaks_only(args: argparse.Namespace) -> int:
    """Run line break normalization only."""
    try:
        from elspais.reformat import normalize_line_breaks, detect_line_break_issues
    except ImportError:
        print("Error: Line break module not yet fully ported.", file=sys.stderr)
        print("This feature is under development.", file=sys.stderr)
        return 1

    dry_run = args.dry_run
    backup = args.backup

    print("Line break normalization mode")
    print(f"  Dry run: {dry_run}")
    print(f"  Backup:  {backup}")
    print()

    if dry_run:
        print("DRY RUN MODE - no changes will be made")
        print()

    # Placeholder for actual implementation
    print("Feature under development. Full implementation pending.")
    return 0
