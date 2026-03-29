# Implements: REQ-d00235-B
"""Comment management CLI commands."""
from __future__ import annotations

import argparse
from pathlib import Path


def run(args: argparse.Namespace) -> int:
    """Dispatch comments subcommands."""
    action = getattr(args, "comments_action", None)
    if action == "compact":
        return _compact(args)
    print("Usage: elspais comments compact")
    return 1


def _compact(args: argparse.Namespace) -> int:
    """Compact comment JSONL files: strip resolved, collapse promotes."""
    from elspais.graph.comment_store import compact_file

    repo_root = getattr(args, "git_root", None) or Path.cwd()
    comments_dir = repo_root / ".elspais" / "comments"

    if not comments_dir.exists():
        print("No .elspais/comments/ directory found.")
        return 0

    files = sorted(comments_dir.glob("**/*.json"))
    if not files:
        print("No comment files found.")
        return 0

    total_removed = 0
    files_compacted = 0
    for path in files:
        removed = compact_file(path)
        if removed > 0:
            files_compacted += 1
            total_removed += removed
            if not getattr(args, "quiet", False):
                print(f"  {path.relative_to(repo_root)}: {removed} events removed")

    if total_removed == 0:
        print("All comment files are already compact.")
    else:
        print(f"Compacted {files_compacted} file(s), {total_removed} event(s) removed.")
    return 0
