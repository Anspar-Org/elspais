# Implements: REQ-o00065-D, REQ-o00065-F
# Implements: REQ-d00073-A, REQ-d00073-B, REQ-d00073-C, REQ-d00073-D, REQ-d00073-E
"""
elspais.commands.link_suggest - Suggest requirement links for unlinked tests.

Analyzes unlinked TEST nodes and proposes requirement associations using
heuristics (import analysis, function name matching, file path proximity,
keyword overlap). Exposes the link suggestion engine via CLI.

Usage:
    elspais link suggest                          # Scan all unlinked tests
    elspais link suggest --file tests/test_foo.py # Single file
    elspais link suggest --format json            # Machine-readable output
    elspais link suggest --min-confidence high    # Filter by confidence
    elspais link suggest --apply --dry-run        # Preview changes
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def run(args: argparse.Namespace) -> int:
    """Run the link suggest command.

    Args:
        args: Parsed CLI arguments.

    Returns:
        Exit code (0 for success, 1 for failure).
    """
    from elspais.graph.factory import build_graph
    from elspais.graph.link_suggest import suggest_links

    spec_dir = getattr(args, "spec_dir", None)
    config_path = getattr(args, "config", None)
    file_path = getattr(args, "file", None)
    output_format = getattr(args, "format", "text")
    min_confidence = getattr(args, "min_confidence", None)
    do_apply = getattr(args, "apply", False)
    dry_run = getattr(args, "dry_run", False)
    limit = getattr(args, "limit", 50)

    # Build graph
    canonical_root = getattr(args, "canonical_root", None)
    try:
        graph = build_graph(
            spec_dirs=[spec_dir] if spec_dir else None,
            config_path=config_path,
            canonical_root=canonical_root,
        )
    except Exception as e:
        print(f"Error building graph: {e}", file=sys.stderr)
        return 1

    repo_root = graph.repo_root

    # Get suggestions
    suggestions = suggest_links(
        graph,
        repo_root,
        file_path=str(file_path) if file_path else None,
        limit=limit,
    )

    # Filter by confidence band
    if min_confidence:
        suggestions = _filter_by_confidence(suggestions, min_confidence)

    if not suggestions:
        if output_format == "json":
            print(json.dumps([]))
        else:
            print("No link suggestions found.")
        return 0

    # Apply mode
    if do_apply:
        return _apply_suggestions(suggestions, repo_root, dry_run)

    # Output mode
    if output_format == "json":
        _output_json(suggestions)
    else:
        _output_text(suggestions)

    return 0


def _filter_by_confidence(suggestions: list, min_confidence: str) -> list:
    """Filter suggestions by minimum confidence band."""
    from elspais.graph.link_suggest import CONFIDENCE_HIGH, CONFIDENCE_MEDIUM

    thresholds = {
        "high": CONFIDENCE_HIGH,
        "medium": CONFIDENCE_MEDIUM,
        "low": 0.0,
    }
    threshold = thresholds.get(min_confidence, 0.0)
    return [s for s in suggestions if s.confidence >= threshold]


def _output_json(suggestions: list) -> None:
    """Output suggestions as JSON array."""
    print(json.dumps([s.to_dict() for s in suggestions], indent=2))


def _output_text(suggestions: list) -> None:
    """Output suggestions as human-readable text."""
    for s in suggestions:
        band_marker = {
            "high": "+++",
            "medium": "++",
            "low": "+",
        }.get(s.confidence_band, "+")

        print(
            f"SUGGEST [{band_marker}] {s.test_file}::{s.test_label} "
            f"-> {s.requirement_id} ({s.confidence:.2f})"
        )
        for reason in s.reasons:
            print(f"  reason: {reason}")
        print()

    # Summary
    high = sum(1 for s in suggestions if s.confidence_band == "high")
    medium = sum(1 for s in suggestions if s.confidence_band == "medium")
    low = sum(1 for s in suggestions if s.confidence_band == "low")
    print(
        f"Found {len(suggestions)} suggestions: "
        f"{high} high, {medium} medium, {low} low confidence"
    )


def _apply_suggestions(
    suggestions: list,
    repo_root: Path,
    dry_run: bool,
) -> int:
    """Apply link suggestions by inserting # Implements: comments.

    Args:
        suggestions: Suggestions to apply.
        repo_root: Repository root for resolving paths.
        dry_run: If True, preview without modifying files.

    Returns:
        Exit code.
    """
    from elspais.graph.link_suggest import apply_link_to_file

    applied = 0
    errors = 0

    for s in suggestions:
        file_path = repo_root / s.test_file
        # Insert at top of file (line 0)
        result = apply_link_to_file(file_path, 0, s.requirement_id, dry_run=dry_run)

        if result:
            prefix = "[DRY RUN] " if dry_run else ""
            print(f"{prefix}Applied: {s.test_file} <- {result}")
            applied += 1
        else:
            print(f"Error: Could not apply to {s.test_file}", file=sys.stderr)
            errors += 1

    action = "Would apply" if dry_run else "Applied"
    print(f"\n{action} {applied} links ({errors} errors)")
    return 1 if errors > 0 else 0
