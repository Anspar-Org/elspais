# Implements: REQ-int-d00008 (Reformat Command)
"""
elspais.commands.reformat_cmd - Reformat requirements using AI.

FUNCTIONALITY (to be reimplemented using Graph):
- `elspais reformat-with-claude` - Transform requirements format using Claude AI
  - Converts old "Acceptance Criteria" format to new "Assertions" format
  - Uses elspais.reformat module for AI calls and content assembly

OPTIONS:
- --start-req REQ_ID: Start from specific requirement (traverse descendants)
- --depth N: Maximum traversal depth
- --dry-run: Preview changes without writing
- --backup: Create .bak files before modifying
- --force: Reformat even if already in new format
- --fix-line-breaks: Normalize line breaks in output
- --line-breaks-only: Only fix line breaks, no format conversion
- --mode core|combined|local-only: Which repos to include

WORKFLOW:
1. Build requirement graph from spec directories
2. Identify requirements needing reformat (via validation)
3. Traverse from start_req or all PRD requirements
4. For each requirement:
   - Call Claude to generate new assertions format
   - Validate the result
   - Replace content in source file (with backup if requested)

GRAPH INTEGRATION:
- Receives TraceGraph from CLI dispatcher
- Uses graph.find_by_id() to locate start requirement
- Uses node.children for BFS traversal
- Uses node.requirement.file_path for file modifications
- Filters by NodeKind.REQUIREMENT
"""

import argparse


def run(args: argparse.Namespace) -> int:
    """Run the reformat-with-claude command.

    This command requires reimplementation using the graph-based system.
    """
    print("Error: 'reformat-with-claude' command not yet implemented with graph-based system")
    print()
    print("Planned features:")
    print("  --start-req REQ_ID")
    print("  --depth N")
    print("  --dry-run")
    print("  --backup")
    print("  --force")
    print("  --fix-line-breaks")
    print("  --line-breaks-only")
    return 1
