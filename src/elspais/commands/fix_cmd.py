# Implements: REQ-p00004-A
"""
elspais.commands.fix_cmd - Auto-fix spec file issues.

Delegates to ``validate.run()`` with ``fix=True``.  For targeted
single-requirement hash updates, uses shared utilities directly.
``validate`` only reports issues; ``fix`` only fixes them.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from elspais.config.schema import ElspaisConfig

_SCHEMA_FIELDS = {f.alias or name for name, f in ElspaisConfig.model_fields.items()} | set(
    ElspaisConfig.model_fields.keys()
)


def _validate_config(config: dict[str, Any]) -> ElspaisConfig:
    """Validate a config dict into ElspaisConfig, stripping non-schema keys."""
    filtered = {k: v for k, v in config.items() if k in _SCHEMA_FIELDS}
    assoc = filtered.get("associates")
    if isinstance(assoc, dict) and "paths" in assoc:
        del filtered["associates"]
    proj = filtered.get("project", {})
    if isinstance(proj, dict) and proj.get("type") == "associated":
        if "core" not in filtered or not filtered["core"]:
            filtered["core"] = {"path": "."}
    return ElspaisConfig.model_validate(filtered)


def run(args: argparse.Namespace) -> int:
    """Run the fix command.

    - fix (no req_id): validate --fix for all fixable issues
    - fix REQ-xxx:     targeted hash update for a single requirement
    """
    target_req_id = getattr(args, "req_id", None)

    if target_req_id:
        return _fix_single(args, target_req_id)

    from elspais.commands import validate

    dry_run = getattr(args, "dry_run", False)

    # Fix parse-dirty nodes (e.g. duplicate refs) via render_save before
    # running validate, so hash mismatches caused by dirty nodes are resolved
    # in one pass rather than two.
    _fix_parse_dirty(args, dry_run)

    validate.run(_make_validate_args(args))

    # Fix stale INDEX.md if present
    _fix_index(args, dry_run)

    if dry_run:
        return 0

    # Re-validate to get the true exit code after fixes are applied
    recheck = _make_validate_args(args)
    recheck.fix = False
    recheck.quiet = True
    return validate.run(recheck)


def _fix_parse_dirty(args: argparse.Namespace, dry_run: bool) -> None:
    """Rewrite files that contain parse-dirty requirements (e.g. duplicate refs).

    Uses render_save() so the rendered output is canonical: one Implements/
    Refines line, deduplicated refs, recomputed hash.
    """
    from elspais.graph import NodeKind
    from elspais.graph.factory import build_graph
    from elspais.graph.render import render_save

    spec_dir = getattr(args, "spec_dir", None)
    config_path = getattr(args, "config", None)
    canonical_root = getattr(args, "canonical_root", None)
    repo_root = getattr(args, "git_root", None) or Path.cwd()

    graph = build_graph(
        spec_dirs=[spec_dir] if spec_dir else None,
        config_path=config_path,
        repo_root=repo_root,
        scan_code=False,
        scan_tests=False,
        canonical_root=canonical_root,
    )

    dirty_nodes = [
        node for node in graph.nodes_by_kind(NodeKind.REQUIREMENT) if node.get_field("parse_dirty")
    ]
    if not dirty_nodes:
        return

    if dry_run:
        for node in dirty_nodes:
            reasons = node.get_field("parse_dirty_reasons") or []
            print(f"Would rewrite {node.id}: {', '.join(reasons)}")
        return

    result = render_save(graph, repo_root=repo_root)
    for file_path in result.get("written", []):
        print(f"Rewrote {file_path} (duplicate refs removed)")


def _make_validate_args(args: argparse.Namespace) -> argparse.Namespace:
    """Build a validate-compatible args namespace from fix args."""
    return argparse.Namespace(
        # Shared CLI args
        spec_dir=getattr(args, "spec_dir", None),
        config=getattr(args, "config", None),
        canonical_root=getattr(args, "canonical_root", None),
        quiet=getattr(args, "quiet", False),
        verbose=getattr(args, "verbose", False),
        # Validate mode
        mode=getattr(args, "mode", "combined"),
        json=False,
        export=False,
        skip_rule=None,
        # Fix mode — always on
        fix=True,
        dry_run=getattr(args, "dry_run", False),
    )


def _fix_single(args: argparse.Namespace, req_id: str) -> int:
    """Fix hash for a single requirement using shared utilities."""
    from datetime import date

    from elspais.commands.validate import compute_hash_for_node
    from elspais.config import get_config
    from elspais.graph import NodeKind
    from elspais.graph.factory import build_graph
    from elspais.utilities.spec_writer import add_changelog_entry, update_hash_in_file

    spec_dir = getattr(args, "spec_dir", None)
    config_path = getattr(args, "config", None)
    canonical_root = getattr(args, "canonical_root", None)
    dry_run = getattr(args, "dry_run", False)
    message = getattr(args, "message", None)
    repo_root = Path(spec_dir).parent if spec_dir else Path.cwd()

    config = get_config(config_path, overrides=getattr(args, "config_overrides", None))
    typed_config = _validate_config(config)
    changelog_enforce = typed_config.changelog.enforce

    graph = build_graph(
        spec_dirs=[spec_dir] if spec_dir else None,
        config_path=config_path,
        repo_root=repo_root,
        scan_code=False,
        scan_tests=False,
        canonical_root=canonical_root,
    )

    hash_mode = getattr(graph, "hash_mode", "full-text")

    # Find the target node
    node = None
    for n in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        if n.id == req_id:
            node = n
            break

    if node is None:
        print(f"Error: Requirement {req_id} not found", file=sys.stderr)
        return 1

    computed = compute_hash_for_node(node, hash_mode)
    if not computed:
        print(f"No hashable content for {req_id}")
        return 0

    stored = node.hash
    status = (node.status or "").lower()
    is_active = status == "active"

    # Implements: REQ-d00129-D
    _fn = node.file_node()
    if _fn is None:
        print(f"Error: No source file for {req_id}", file=sys.stderr)
        return 1

    file_path = repo_root / _fn.get_field("relative_path")

    # If hash is current, check for missing Changelog section on Active reqs
    if stored == computed:
        if is_active and changelog_enforce:
            return _ensure_changelog_section(file_path, req_id, computed, config, dry_run)
        print(f"{req_id} hash is already up to date")
        return 0

    # Hash mismatch — need to update
    if is_active and changelog_enforce:
        # Require a changelog message for Active requirements
        if message is None:
            if sys.stdin.isatty():
                message = input(f"Changelog reason for {req_id}: ").strip()
            if not message:
                print(
                    f"Error: Active requirement {req_id} requires a changelog"
                    ' message (-m "reason")',
                    file=sys.stderr,
                )
                return 1

        # Resolve author info
        from elspais.utilities.git import get_author_info

        id_source = typed_config.changelog.id_source
        try:
            author = get_author_info(id_source)
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

        if dry_run:
            print(f"Would update {req_id}: {stored or '(none)'} -> {computed}")
            return 0

        # Add changelog entry before updating hash
        change_order = "-"
        entry = {
            "date": date.today().isoformat(),
            "hash": computed,
            "change_order": change_order,
            "author_name": author["name"],
            "author_id": author["id"],
            "reason": message,
        }
        cl_error = add_changelog_entry(file_path, req_id, entry)
        if cl_error:
            print(f"Error adding changelog: {cl_error}", file=sys.stderr)
            return 1

    else:
        # Draft/Deprecated — update hash silently
        if dry_run:
            print(f"Would update {req_id}: {stored or '(none)'} -> {computed}")
            return 0

    error = update_hash_in_file(file_path=file_path, req_id=req_id, new_hash=computed)
    if error is None:
        print(f"Updated {req_id}: {stored or '(none)'} -> {computed}")
        return 0
    else:
        print(f"Error: {error}", file=sys.stderr)
        return 1


def _ensure_changelog_section(
    file_path: Path,
    req_id: str,
    current_hash: str,
    config: dict,
    dry_run: bool,
) -> int:
    """Add missing ## Changelog section to an Active requirement.

    Returns 0 on success or if section already exists.
    """
    from datetime import date

    content = file_path.read_text(encoding="utf-8")

    # Check if this requirement block already has a ## Changelog section
    from elspais.utilities.patterns import find_req_header as _find_req_header

    header_match = _find_req_header(content, req_id)
    if not header_match:
        return 0

    start_pos = header_match.end()
    # Find end marker
    from elspais.utilities.spec_writer import _find_end_marker

    end_match = _find_end_marker(content, start_pos)
    if not end_match:
        return 0

    block = content[start_pos : end_match.start()]
    import re

    if re.search(r"^## Changelog\s*$", block, re.MULTILINE):
        print(f"{req_id} hash is already up to date")
        return 0

    if dry_run:
        print(f"Would add missing Changelog section to {req_id}")
        return 0

    # Auto-add with default message
    from elspais.utilities.git import get_author_info
    from elspais.utilities.spec_writer import add_changelog_entry

    _tc = _validate_config(config)
    id_source = _tc.changelog.id_source
    try:
        author = get_author_info(id_source)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    entry = {
        "date": date.today().isoformat(),
        "hash": current_hash,
        "change_order": "-",
        "author_name": author["name"],
        "author_id": author["id"],
        "reason": "Adding missing Changelog section",
    }
    cl_error = add_changelog_entry(file_path, req_id, entry)
    if cl_error:
        print(f"Error: {cl_error}", file=sys.stderr)
        return 1

    print(
        f"INFO: Added missing Changelog section to {req_id}",
        file=sys.stderr,
    )
    return 0


def _fix_index(args: argparse.Namespace, dry_run: bool) -> None:
    """Regenerate INDEX.md from current graph state."""
    from elspais.commands.index import _regenerate_index
    from elspais.config import get_config, get_spec_directories
    from elspais.graph.factory import build_graph

    spec_dir = getattr(args, "spec_dir", None)
    config_path = getattr(args, "config", None)
    canonical_root = getattr(args, "canonical_root", None)

    config = get_config(config_path, overrides=getattr(args, "config_overrides", None))
    spec_dirs = get_spec_directories(spec_dir, config)

    if not spec_dirs:
        return

    if dry_run:
        print("Would regenerate INDEX.md")
        return

    all_spec_dirs = list(spec_dirs)

    graph = build_graph(
        spec_dirs=[spec_dir] if spec_dir else None,
        config_path=config_path,
        scan_code=False,
        scan_tests=False,
        canonical_root=canonical_root,
    )

    _regenerate_index(graph, all_spec_dirs, args)
