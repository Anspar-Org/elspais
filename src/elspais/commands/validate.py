# Implements: REQ-int-d00003 (CLI Extension)
"""
elspais.commands.validate - Validate requirements format and relationships.

Uses the graph-based system for validation. Commands only work with graph data.
Supports --fix to auto-fix certain issues (hashes, status).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

from elspais.graph import NodeKind


def _compute_hash_for_node(node, hash_mode: str) -> str | None:
    """Compute the content hash for a requirement node.

    Supports two modes (per spec/requirements-spec.md Hash Definition):
    - full-text: hash every line between header and footer (body_text)
    - normalized-text: hash normalized assertion text only

    Args:
        node: The requirement GraphNode.
        hash_mode: Hash calculation mode ("full-text" or "normalized-text").

    Returns:
        Computed hash string, or None if no hashable content.
    """
    from elspais.utilities.hasher import calculate_hash, compute_normalized_hash

    if hash_mode == "normalized-text":
        assertions = []
        for child in node.iter_children():
            if child.kind == NodeKind.ASSERTION:
                label = child.get_field("label", "")
                text = child.get_label() or ""
                if label and text:
                    assertions.append((label, text))
        if not assertions:
            return None
        return compute_normalized_hash(assertions)
    else:
        body = node.get_field("body_text", "")
        if not body:
            return None
        return calculate_hash(body)


def run(args: argparse.Namespace) -> int:
    """Run the validate command.

    Uses graph factory to build TraceGraph, then validates requirements.
    Supports --fix to auto-fix certain issues.
    """
    from elspais.graph.factory import build_graph

    spec_dir = getattr(args, "spec_dir", None)
    config_path = getattr(args, "config", None)
    fix_mode = getattr(args, "fix", False)
    dry_run = getattr(args, "dry_run", False)
    mode = getattr(args, "mode", "combined")

    # Get repo root from spec_dir or cwd
    repo_root = Path(spec_dir).parent if spec_dir else Path.cwd()

    scan_sponsors = mode != "core"

    canonical_root = getattr(args, "canonical_root", None)
    graph = build_graph(
        spec_dirs=[spec_dir] if spec_dir else None,
        config_path=config_path,
        repo_root=repo_root,
        scan_sponsors=scan_sponsors,
        canonical_root=canonical_root,
    )

    # Handle --export mode (early return, not validation)
    if getattr(args, "export", False):
        export_dict: dict[str, dict] = {}
        for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
            assertions = []
            for child in node.iter_children():
                if child.kind == NodeKind.ASSERTION:
                    assertions.append(
                        {
                            "label": child.get_field("label", ""),
                            "text": child.get_label() or "",
                        }
                    )
            export_dict[node.id] = {
                "title": node.get_label() or "",
                "level": node.get_field("level", ""),
                "status": node.get_field("status", ""),
                "hash": node.get_field("hash", ""),
                "file": node.source.path if node.source else "",
                "line": node.source.line if node.source else 0,
                "assertions": assertions,
            }
        print(json.dumps(export_dict, indent=2))
        return 0

    # Collect validation issues
    errors = []
    warnings = []
    fixable = []  # Issues that can be auto-fixed

    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        # Implements: REQ-p00002-B
        # Check for orphan requirements (no parents except roots)
        if node.parent_count() == 0 and node.level not in ("PRD", "prd"):
            warnings.append(
                {
                    "rule": "hierarchy.orphan",
                    "id": node.id,
                    "message": f"Requirement {node.id} has no parent (orphan)",
                }
            )

        # Implements: REQ-p00002-C
        # Check for hash presence and correctness
        hash_mode = getattr(graph, "hash_mode", "full-text")
        computed_hash = _compute_hash_for_node(node, hash_mode)
        stored_hash = node.hash

        if computed_hash:
            if not stored_hash:
                # Missing hash - fixable
                issue = {
                    "rule": "hash.missing",
                    "id": node.id,
                    "message": f"Requirement {node.id} is missing a hash",
                    "fixable": True,
                    "fix_type": "hash",
                    "computed_hash": computed_hash,
                    "file": str(repo_root / node.source.path) if node.source else None,
                }
                warnings.append(issue)
                if issue["file"]:
                    fixable.append(issue)
            elif stored_hash != computed_hash:
                # Hash mismatch - fixable
                issue = {
                    "rule": "hash.mismatch",
                    "id": node.id,
                    "message": f"Requirement {node.id} hash mismatch: "
                    f"stored={stored_hash} computed={computed_hash}",
                    "fixable": True,
                    "fix_type": "hash",
                    "computed_hash": computed_hash,
                    "file": str(repo_root / node.source.path) if node.source else None,
                }
                warnings.append(issue)
                if issue["file"]:
                    fixable.append(issue)
        elif not stored_hash:
            # No hashable content and no hash
            warnings.append(
                {
                    "rule": "hash.missing",
                    "id": node.id,
                    "message": f"Requirement {node.id} is missing a hash",
                }
            )

    # Check assertion line spacing per source file
    checked_files: set[str] = set()
    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        if not node.source or not node.source.path:
            continue
        file_path = node.source.path
        if file_path in checked_files:
            continue
        checked_files.add(file_path)
        resolved = repo_root / file_path
        if not resolved.exists():
            continue
        spacing_issues = _check_assertion_spacing(resolved)
        for line_num in spacing_issues:
            issue = {
                "rule": "format.assertion_spacing",
                "id": file_path,
                "message": (
                    f"{file_path}:{line_num}: Consecutive assertion lines "
                    f"need blank line separation"
                ),
                "fixable": True,
                "fix_type": "assertion_spacing",
                "file": str(resolved),
            }
            warnings.append(issue)
            fixable.append(issue)

        list_issues = _check_list_spacing(resolved)
        for line_num in list_issues:
            issue = {
                "rule": "format.list_spacing",
                "id": file_path,
                "message": (
                    f"{file_path}:{line_num}: List item needs blank line "
                    f"before it for proper Markdown rendering"
                ),
                "fixable": True,
                "fix_type": "list_spacing",
                "file": str(resolved),
            }
            warnings.append(issue)
            fixable.append(issue)

    # Filter by skip rules
    skip_rules = getattr(args, "skip_rule", None) or []
    if skip_rules:
        import fnmatch

        errors = [e for e in errors if not any(fnmatch.fnmatch(e["rule"], p) for p in skip_rules)]
        warnings = [
            w for w in warnings if not any(fnmatch.fnmatch(w["rule"], p) for p in skip_rules)
        ]
        fixable = [f for f in fixable if not any(fnmatch.fnmatch(f["rule"], p) for p in skip_rules)]

    # Handle --fix mode
    fixed_count = 0
    if fix_mode and fixable:
        fixed_count = _apply_fixes(fixable, dry_run)

    # Count requirements
    req_count = sum(1 for _ in graph.nodes_by_kind(NodeKind.REQUIREMENT))

    # Output results
    if getattr(args, "json", False):
        result = {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "requirements_count": req_count,
            "fixed_count": fixed_count if fix_mode else 0,
        }
        print(json.dumps(result, indent=2))
    else:
        if not getattr(args, "quiet", False):
            print(f"Validated {req_count} requirements")

        # Show fix results
        if fix_mode:
            if dry_run:
                if fixable:
                    print(f"Would fix {len(fixable)} issue(s):")
                    for f in fixable:
                        print(f"  {f['id']}: {f['rule']}")
                else:
                    print("No fixable issues found.")
            else:
                if fixed_count > 0:
                    print(f"Fixed {fixed_count} issue(s)")

        for err in errors:
            print(f"ERROR [{err['rule']}] {err['id']}: {err['message']}", file=sys.stderr)

        # Only show unfixed warnings
        unfixed_warnings = [w for w in warnings if not w.get("fixable") or not fix_mode]
        for warn in unfixed_warnings:
            print(
                f"WARNING [{warn['rule']}] {warn['id']}: {warn['message']}",
                file=sys.stderr,
            )

        if errors:
            print(
                f"\n{len(errors)} errors, {len(unfixed_warnings)} warnings",
                file=sys.stderr,
            )
        elif unfixed_warnings:
            print(f"\n{len(unfixed_warnings)} warnings", file=sys.stderr)

    return 1 if errors else 0


_ASSERTION_LINE_RE = re.compile(r"^[A-Z]\. ")


def _check_assertion_spacing(file_path: Path) -> list[int]:
    """Check for consecutive assertion lines with no blank line between them.

    Returns list of 1-indexed line numbers where a second assertion
    immediately follows a previous assertion with no separating blank line.
    """
    lines = file_path.read_text(encoding="utf-8").split("\n")
    issues: list[int] = []
    for i in range(len(lines) - 1):
        if _ASSERTION_LINE_RE.match(lines[i]) and _ASSERTION_LINE_RE.match(lines[i + 1]):
            issues.append(i + 2)  # 1-indexed, report the second line
    return issues


def _fix_assertion_spacing(file_path: Path) -> int:
    """Insert blank lines between consecutive assertion lines.

    Returns number of blank lines inserted.
    """
    lines = file_path.read_text(encoding="utf-8").split("\n")
    result: list[str] = []
    inserted = 0
    for i, line in enumerate(lines):
        result.append(line)
        if (
            _ASSERTION_LINE_RE.match(line)
            and i + 1 < len(lines)
            and _ASSERTION_LINE_RE.match(lines[i + 1])
        ):
            result.append("")
            inserted += 1
    if inserted:
        file_path.write_text("\n".join(result), encoding="utf-8")
    return inserted


_LIST_ITEM_RE = re.compile(r"^\s*- ")


def _check_list_spacing(file_path: Path) -> list[int]:
    """Check for list items that immediately follow a non-blank, non-list line.

    Pandoc requires a blank line before the first list item to render it as a
    proper list. Without it, the list items are appended as inline text.

    Returns list of 1-indexed line numbers where a list item needs a preceding blank line.
    """
    lines = file_path.read_text(encoding="utf-8").split("\n")
    issues: list[int] = []
    for i in range(1, len(lines)):
        if (
            _LIST_ITEM_RE.match(lines[i])
            and lines[i - 1].strip()
            and not _LIST_ITEM_RE.match(lines[i - 1])
        ):
            issues.append(i + 1)  # 1-indexed
    return issues


def _fix_list_spacing(file_path: Path) -> int:
    """Insert blank lines before list items that follow non-blank, non-list lines.

    Returns number of blank lines inserted.
    """
    lines = file_path.read_text(encoding="utf-8").split("\n")
    result: list[str] = []
    inserted = 0
    for i, line in enumerate(lines):
        if (
            _LIST_ITEM_RE.match(line)
            and i > 0
            and result
            and result[-1].strip()
            and not _LIST_ITEM_RE.match(result[-1])
        ):
            result.append("")
            inserted += 1
        result.append(line)
    if inserted:
        file_path.write_text("\n".join(result), encoding="utf-8")
    return inserted


def _apply_fixes(fixable: list[dict], dry_run: bool) -> int:
    """Apply fixes to spec files.

    Args:
        fixable: List of fixable issues with fix metadata.
        dry_run: If True, don't actually modify files.

    Returns:
        Number of issues fixed.
    """
    if dry_run:
        return 0

    from elspais.mcp.file_mutations import add_status_to_file, update_hash_in_file

    fixed = 0
    spacing_fixed_files: set[str] = set()
    for issue in fixable:
        fix_type = issue.get("fix_type")
        file_path = issue.get("file")

        if not file_path:
            continue

        if fix_type == "hash":
            # Fix hash (missing or mismatch)
            error = update_hash_in_file(
                file_path=Path(file_path),
                req_id=issue["id"],
                new_hash=issue["computed_hash"],
            )
            if error is None:
                fixed += 1
            else:
                print(f"Warning: {error}", file=sys.stderr)

        elif fix_type == "status":
            # Add missing status
            error = add_status_to_file(
                file_path=Path(file_path),
                req_id=issue["id"],
                status=issue.get("status", "Active"),
            )
            if error is None:
                fixed += 1
            else:
                print(f"Warning: {error}", file=sys.stderr)

        elif fix_type == "assertion_spacing":
            # Fix consecutive assertion lines — deduplicate per file
            if file_path not in spacing_fixed_files:
                spacing_fixed_files.add(file_path)
                inserted = _fix_assertion_spacing(Path(file_path))
                fixed += inserted

        elif fix_type == "list_spacing":
            # Fix list items missing preceding blank line — deduplicate per file
            if file_path not in spacing_fixed_files:
                spacing_fixed_files.add(file_path)
                inserted = _fix_list_spacing(Path(file_path))
                fixed += inserted

    return fixed
