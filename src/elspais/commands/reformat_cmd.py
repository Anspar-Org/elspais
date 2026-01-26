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

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional

from elspais.config.loader import find_config_file, get_spec_directories, load_config
from elspais.core.loader import load_requirements_from_directories, load_requirements_from_repo
from elspais.core.patterns import PatternConfig, PatternValidator
from elspais.core.rules import RuleEngine, RulesConfig

if TYPE_CHECKING:
    from elspais.core.graph import TraceGraph, TraceNode


def run(args: argparse.Namespace) -> int:
    """Run the reformat-with-claude command.

    This command reformats requirements from the old Acceptance Criteria format
    to the new Assertions format using Claude AI.
    """
    from elspais.core.graph import NodeKind
    from elspais.core.graph_builder import TraceGraphBuilder
    from elspais.core.patterns import normalize_req_id
    from elspais.reformat import (
        assemble_new_format,
        normalize_line_breaks,
        reformat_requirement,
        validate_reformatted_content,
    )

    print("elspais reformat-with-claude")
    print()

    # Handle line-breaks-only mode
    if args.line_breaks_only:
        return run_line_breaks_only(args)

    # Configuration
    start_req = args.start_req
    max_depth = args.depth
    dry_run = args.dry_run
    backup = args.backup
    force = args.force
    fix_line_breaks = args.fix_line_breaks
    verbose = getattr(args, "verbose", False)
    mode = getattr(args, "mode", "combined")

    print("Options:")
    print(f"  Start REQ:       {start_req or 'All PRD requirements'}")
    print(f"  Max depth:       {max_depth or 'Unlimited'}")
    print(f"  Mode:            {mode}")
    print(f"  Dry run:         {dry_run}")
    print(f"  Backup:          {backup}")
    print(f"  Force reformat:  {force}")
    print(f"  Fix line breaks: {fix_line_breaks}")
    print()

    if dry_run:
        print("DRY RUN MODE - no changes will be made")
        print()

    # Create cached validator for ID normalization
    config_path = find_config_file(Path.cwd())
    config = load_config(config_path) if config_path else {}
    pattern_config = PatternConfig.from_dict(config.get("patterns", {}))
    validator = PatternValidator(pattern_config)

    # Determine local base path for filtering (only modify local files)
    local_base_path = config_path.parent if config_path else Path.cwd()

    # Build requirement graph (including cross-repo if mode allows)
    print("Loading requirements and building hierarchy...", end=" ", flush=True)
    graph = _build_requirement_graph(config_path, local_base_path, mode)
    if graph is None:
        print("FAILED")
        print("Error: Could not load requirements. Run 'elspais validate' first.", file=sys.stderr)
        return 1

    # Count requirement nodes
    req_count = sum(1 for _ in graph.nodes_by_kind(NodeKind.REQUIREMENT))
    print(f"found {req_count} requirements")

    # Determine which requirements to process
    if start_req:
        # Normalize and validate start requirement
        print(f"Normalizing {start_req}...", end=" ", flush=True)
        start_req = normalize_req_id(start_req, validator)
        print(f"-> {start_req}", flush=True)
        start_node = graph.find_by_id(start_req)
        if start_node is None:
            print(f"Error: Requirement {start_req} not found", file=sys.stderr)
            return 1

        print(f"Traversing from {start_req}...", flush=True)
        req_nodes = _traverse_requirements(start_node, max_depth, NodeKind)
        print("Traversal complete", flush=True)
    else:
        # Process all PRD requirements first, then their descendants
        prd_nodes = [
            n for n in graph.nodes_by_kind(NodeKind.REQUIREMENT)
            if n.requirement and n.requirement.level.upper() == "PRD"
        ]
        prd_nodes.sort(key=lambda n: n.id)

        print(f"Processing {len(prd_nodes)} PRD requirements and their descendants...")
        req_nodes: List[TraceNode] = []
        seen: set[str] = set()
        for prd_node in prd_nodes:
            for node in _traverse_requirements(prd_node, max_depth, NodeKind):
                if node.id not in seen:
                    req_nodes.append(node)
                    seen.add(node.id)

    print(f"Found {len(req_nodes)} requirements to process", flush=True)

    # Run validation to identify requirements with acceptance_criteria issues
    print("Running validation to identify old format...", end=" ", flush=True)
    needs_reformat_ids = _get_requirements_needing_reformat(config, local_base_path)
    print(f"found {len(needs_reformat_ids)} with old format", flush=True)
    print(flush=True)

    # Filter to only requirements that need reformatting (unless --force)
    if not force:
        req_nodes = [n for n in req_nodes if n.id in needs_reformat_ids]
        print(f"Filtered to {len(req_nodes)} requirements needing reformat")
        print(flush=True)

    # Process each requirement
    reformatted = 0
    skipped = 0
    errors = 0
    line_break_fixes = 0

    for i, node in enumerate(req_nodes):
        if i % 10 == 0 and i > 0:
            print(f"Processing {i}/{len(req_nodes)}...", flush=True)

        req = node.requirement
        if req is None:
            continue

        file_path_str = str(req.file_path) if req.file_path else ""

        # Skip non-local files (from core/associated repos)
        if not _is_local_file(file_path_str, local_base_path):
            skipped += 1
            continue

        print(f"[PROC] {node.id}: {node.label[:50]}...")

        # Call Claude to reformat
        result, success, error_msg = reformat_requirement(node, verbose=verbose)

        if not success:
            print(f"  ERROR: {error_msg}")
            errors += 1
            continue

        # Validate the result
        rationale = result.get("rationale", "")
        assertions = result.get("assertions", [])

        is_valid, warnings = validate_reformatted_content(node, rationale, assertions)

        if warnings:
            for warning in warnings:
                print(f"  WARNING: {warning}")

        if not is_valid:
            print("  INVALID: Skipping due to validation errors")
            errors += 1
            continue

        # Assemble the new format
        new_content = assemble_new_format(
            req_id=node.id,
            title=node.label,
            level=req.level,
            status=req.status,
            implements=list(req.implements),
            rationale=rationale,
            assertions=assertions,
        )

        # Optionally normalize line breaks
        if fix_line_breaks:
            new_content = normalize_line_breaks(new_content)
            line_break_fixes += 1

        if dry_run:
            print(f"  Would write to: {file_path_str}")
            print(f"  Assertions: {len(assertions)}")
            reformatted += 1
        else:
            # Write the reformatted content
            try:
                file_path = Path(file_path_str)

                if backup:
                    backup_path = file_path.with_suffix(file_path.suffix + ".bak")
                    shutil.copy2(file_path, backup_path)
                    print(f"  Backup: {backup_path}")

                # Read the entire file
                content = file_path.read_text()

                # Find and replace this requirement's content
                # The requirement starts with its header and ends before the next
                # requirement or end of file
                updated_content = _replace_requirement_content(
                    content, node.id, node.label, new_content
                )

                if updated_content:
                    file_path.write_text(updated_content)
                    print(f"  Written: {file_path}")
                    reformatted += 1
                else:
                    print("  ERROR: Could not locate requirement in file")
                    errors += 1

            except Exception as e:
                print(f"  ERROR: {e}")
                errors += 1

    # Summary
    print()
    print("=" * 60)
    print("Summary:")
    print(f"  Reformatted: {reformatted}")
    print(f"  Skipped:     {skipped}")
    print(f"  Errors:      {errors}")
    if fix_line_breaks:
        print(f"  Line breaks: {line_break_fixes} files normalized")

    return 0 if errors == 0 else 1


def _replace_requirement_content(
    file_content: str, req_id: str, title: str, new_content: str
) -> Optional[str]:
    """
    Replace a requirement's content in a file.

    Finds the requirement by its header pattern and replaces everything
    up to the footer line.

    Args:
        file_content: Full file content
        req_id: Requirement ID (e.g., 'REQ-d00027')
        title: Requirement title
        new_content: New requirement content

    Returns:
        Updated file content, or None if requirement not found
    """
    import re

    # Pattern to match the requirement header
    # # REQ-d00027: Title
    header_pattern = rf"^# {re.escape(req_id)}:\s*"

    # Pattern to match the footer
    # *End* *Title* | **Hash**: xxxxxxxx
    footer_pattern = rf"^\*End\*\s+\*{re.escape(title)}\*\s+\|\s+\*\*Hash\*\*:\s*[a-fA-F0-9]+"

    lines = file_content.split("\n")
    result_lines = []
    in_requirement = False
    found = False

    i = 0
    while i < len(lines):
        line = lines[i]

        if not in_requirement:
            # Check if this line starts the requirement
            if re.match(header_pattern, line, re.IGNORECASE):
                in_requirement = True
                found = True
                # Insert new content (without trailing newline, we'll add it)
                new_lines = new_content.rstrip("\n").split("\n")
                result_lines.extend(new_lines)
                i += 1
                continue
            else:
                result_lines.append(line)
                i += 1
        else:
            # We're inside the requirement, skip until we find the footer
            if re.match(footer_pattern, line, re.IGNORECASE):
                # Found the footer, we've already added the new content
                # with its own footer, so skip this old footer
                in_requirement = False
                i += 1
                # Skip any trailing blank lines after the footer
                while i < len(lines) and lines[i].strip() == "":
                    i += 1
            else:
                # Skip this line (part of old requirement)
                i += 1

    if not found:
        return None

    return "\n".join(result_lines)


def run_line_breaks_only(args: argparse.Namespace) -> int:
    """Run line break normalization only."""
    from elspais.core.graph import NodeKind
    from elspais.reformat import (
        detect_line_break_issues,
        normalize_line_breaks,
    )

    dry_run = args.dry_run
    backup = args.backup

    print("Line break normalization mode")
    print(f"  Dry run: {dry_run}")
    print(f"  Backup:  {backup}")
    print()

    # Build requirement graph
    print("Loading requirements...", end=" ", flush=True)
    config_path = find_config_file(Path.cwd())
    local_base_path = config_path.parent if config_path else Path.cwd()
    graph = _build_requirement_graph(config_path, local_base_path, "combined")
    if graph is None:
        print("FAILED")
        print("Error: Could not load requirements.", file=sys.stderr)
        return 1

    req_count = sum(1 for _ in graph.nodes_by_kind(NodeKind.REQUIREMENT))
    print(f"found {req_count} requirements")

    # Group by file
    files_to_process: Dict[str, List[str]] = {}
    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        if node.requirement and node.requirement.file_path:
            file_path_str = str(node.requirement.file_path)
            if file_path_str not in files_to_process:
                files_to_process[file_path_str] = []
            files_to_process[file_path_str].append(node.id)

    print(f"Processing {len(files_to_process)} files...")
    print()

    fixed = 0
    unchanged = 0
    errors = 0

    for file_path_str, _req_ids in sorted(files_to_process.items()):
        file_path = Path(file_path_str)

        try:
            content = file_path.read_text()
            issues = detect_line_break_issues(content)

            if not issues:
                unchanged += 1
                continue

            print(f"[FIX] {file_path}")
            for issue in issues:
                print(f"  - {issue}")

            if dry_run:
                fixed += 1
                continue

            # Apply fixes
            fixed_content = normalize_line_breaks(content)

            if backup:
                backup_path = file_path.with_suffix(file_path.suffix + ".bak")
                shutil.copy2(file_path, backup_path)

            file_path.write_text(fixed_content)
            fixed += 1

        except Exception as e:
            print(f"[ERR] {file_path}: {e}")
            errors += 1

    print()
    print("=" * 60)
    print("Summary:")
    print(f"  Fixed:     {fixed}")
    print(f"  Unchanged: {unchanged}")
    print(f"  Errors:    {errors}")

    return 0 if errors == 0 else 1


def _get_requirements_needing_reformat(config: dict, base_path: Path) -> set:
    """Run validation to identify requirements with old format.

    Args:
        config: Configuration dictionary
        base_path: Base path of the local repository

    Returns:
        Set of requirement IDs that have format.acceptance_criteria violations
    """
    # Get local spec directories only
    spec_dirs = get_spec_directories(None, config, base_path)
    if not spec_dirs:
        return set()

    # Parse local requirements
    try:
        requirements = load_requirements_from_directories(spec_dirs, config)
    except Exception:
        return set()

    # Run validation
    rules_config = RulesConfig.from_dict(config.get("rules", {}))
    engine = RuleEngine(rules_config)
    violations = engine.validate(requirements)

    # Filter to acceptance_criteria violations
    return {v.requirement_id for v in violations if v.rule_name == "format.acceptance_criteria"}


def _is_local_file(file_path: str, base_path: Path) -> bool:
    """Check if file is in the local repo (not core/associated).

    Args:
        file_path: Path to the file (string)
        base_path: Base path of the local repository

    Returns:
        True if file is within the local repo, False otherwise
    """
    try:
        Path(file_path).resolve().relative_to(base_path.resolve())
        return True
    except ValueError:
        return False


def _build_requirement_graph(
    config_path: Optional[Path],
    base_path: Path,
    mode: str = "combined",
) -> Optional[TraceGraph]:
    """Build requirement graph using TraceGraphBuilder.

    Args:
        config_path: Path to .elspais.toml config file
        base_path: Base path for resolving relative directories
        mode: Which repos to include:
            - "combined" (default): Load local + core/associated repo requirements
            - "core-only": Load only core/associated repo requirements
            - "local-only": Load only local requirements

    Returns:
        TraceGraph with requirement hierarchy, or None on failure
    """
    from elspais.core.graph_builder import TraceGraphBuilder

    if config_path is None:
        config_path = find_config_file(base_path)

    if config_path is None:
        print("Warning: No .elspais.toml found", file=sys.stderr)
        return None

    try:
        config = load_config(config_path)
    except Exception as e:
        print(f"Warning: Failed to load config: {e}", file=sys.stderr)
        return None

    all_requirements: Dict[str, any] = {}

    # Load local requirements (unless core-only mode)
    if mode in ("combined", "local-only"):
        spec_dirs = get_spec_directories(None, config, base_path)
        if spec_dirs:
            try:
                local_reqs = load_requirements_from_directories(spec_dirs, config)
                all_requirements.update(local_reqs)
            except Exception as e:
                print(f"Warning: Failed to parse local requirements: {e}", file=sys.stderr)

    # Load core/associated repo requirements (unless local-only mode)
    if mode in ("combined", "core-only"):
        core_path = config.get("core", {}).get("path")
        if core_path:
            repo_reqs = load_requirements_from_repo(Path(core_path), config)
            for req_id, req in repo_reqs.items():
                # Don't overwrite local requirements with same ID
                if req_id not in all_requirements:
                    all_requirements[req_id] = req

    if not all_requirements:
        print("Warning: No requirements found", file=sys.stderr)
        return None

    # Build graph
    repo_root = config_path.parent if config_path else Path.cwd()
    builder = TraceGraphBuilder(repo_root=repo_root)
    builder.add_requirements(all_requirements)
    return builder.build()


def _traverse_requirements(
    start_node: TraceNode,
    max_depth: Optional[int],
    NodeKind: type,
) -> List[TraceNode]:
    """Traverse hierarchy from start_node downward using BFS.

    Args:
        start_node: Starting TraceNode
        max_depth: Maximum depth to traverse (None = unlimited)
        NodeKind: NodeKind enum class (passed to avoid import in inner function)

    Returns:
        List of TraceNode objects in traversal order (requirements only)
    """
    from collections import deque

    visited: List[TraceNode] = []
    queue: deque[tuple[TraceNode, int]] = deque([(start_node, 0)])
    seen: set[str] = set()

    while queue:
        node, depth = queue.popleft()

        if node.id in seen:
            continue

        # Depth limit check (depth 0 is the start node)
        if max_depth is not None and depth > max_depth:
            continue

        seen.add(node.id)

        # Only include requirement nodes
        if node.kind != NodeKind.REQUIREMENT:
            continue

        visited.append(node)

        # Add children to queue (only requirement children for traversal)
        for child in node.children:
            if child.id not in seen and child.kind == NodeKind.REQUIREMENT:
                queue.append((child, depth + 1))

    return visited
