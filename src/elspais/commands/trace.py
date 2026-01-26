# Implements: REQ-int-d00003 (CLI Extension)
"""
elspais.commands.trace - Generate traceability matrix command.

FUNCTIONALITY (to be reimplemented using Graph):
- `elspais trace` - Generate traceability matrix
  - Supports multiple output formats: markdown, csv, html, json
  - --format flag to select output format (default: markdown)
  - --output flag to write to file instead of stdout
  - --view flag for interactive HTML generation using HTMLGenerator
  - --embed-content flag to embed requirement content in HTML
  - --quiet flag to suppress status messages

OUTPUT FORMATS:
- markdown: Table with ID, Title, Level, Status, Implements columns
- csv: Same columns, comma-separated with proper escaping
- html: Basic styled HTML table
- json: Full requirement data including body, assertions, hash, file_path

INTERACTIVE VIEW (--view):
- Uses elspais.html.HTMLGenerator
- Generates interactive HTML with collapsible hierarchy
- Default output: traceability_view.html

GRAPH INTEGRATION:
- Receives TraceGraph from CLI dispatcher
- Iterates graph.roots for matrix generation
- Accesses node.requirement for requirement data
- JSON format includes full Requirement attributes
"""

import argparse


def run(args: argparse.Namespace) -> int:
    """Run the trace command.

    This command requires reimplementation using the graph-based system.
    """
    print("Error: 'trace' command not yet implemented with graph-based system")
    print()
    print("Planned features:")
    print("  --format markdown|csv|html|json")
    print("  --output FILE")
    print("  --view (interactive HTML)")
    print("  --embed-content")
    return 1
