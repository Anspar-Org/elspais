"""
elspais.commands.index - INDEX.md management command.

FUNCTIONALITY (to be reimplemented using Graph):
- `elspais index validate` - Validate INDEX.md accuracy
  - Compares requirement IDs in INDEX.md vs parsed requirements
  - Reports missing IDs (in specs but not in INDEX.md)
  - Reports extra IDs (in INDEX.md but not in specs)

- `elspais index regenerate` - Regenerate INDEX.md from requirements
  - Groups requirements by level (PRD, OPS, DEV)
  - Generates markdown table with ID, Title, File, Hash
  - Writes to spec/INDEX.md (or configured location)

INDEX.MD FORMAT:
```
# Requirements Index
## Product Requirements (PRD)
| ID | Title | File | Hash |
|---|---|---|---|
| REQ-p00001 | Example | file.md | abc12345 |
...
```

GRAPH INTEGRATION:
- Receives TraceGraph from CLI dispatcher
- Iterates all requirement nodes for ID list
- Uses node.requirement for title, file_path, hash
- Groups by node.requirement.level
"""

import argparse


def run(args: argparse.Namespace) -> int:
    """Run the index command.

    This command requires reimplementation using the graph-based system.
    """
    print("Error: 'index' command not yet implemented with graph-based system")
    print()
    print("Planned subcommands:")
    print("  validate   - Validate INDEX.md accuracy")
    print("  regenerate - Regenerate INDEX.md from requirements")
    return 1
