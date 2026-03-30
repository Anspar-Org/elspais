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
        filtered.pop("associates", None)
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

    # Implements: REQ-d00225-B
    # Generate glossary and term index if terms are defined
    _fix_terms(args, dry_run)

    if dry_run:
        return 0

    # Re-validate to get the true exit code after fixes are applied
    recheck = _make_validate_args(args)
    recheck.fix = False
    recheck.quiet = True
    return validate.run(recheck)


_REASON_LABELS: dict[str, str] = {
    "non_canonical_term": "canonicalize term forms",
    "duplicate_refs": "deduplicate Implements/Refines references",
    "stale_hash": "update hash",
    "fix_single": "fix requirement",
}


def _add_autofix_changelog_entries(
    graph,  # noqa: ANN001 — FederatedGraph
    dirty_nodes: list,
    config: dict[str, Any],
) -> int:
    """Add changelog entries for auto-fixed requirements.

    For each dirty Active requirement (when changelog is enabled),
    adds a changelog entry with an auto-generated reason describing
    the fix.  Returns the number of entries added.
    """
    from datetime import date

    typed_config = _validate_config(config)
    if not typed_config.changelog.hash_current:
        return 0

    from elspais.commands.validate import compute_hash_for_node
    from elspais.utilities.git import get_author_info

    id_source = typed_config.changelog.id_source
    try:
        author = get_author_info(id_source)
    except ValueError:
        return 0

    hash_mode = getattr(graph, "hash_mode", "full-text")
    added = 0

    for node in dirty_nodes:
        status = (node.get_field("status") or "").lower()
        if status != "active":
            continue

        reasons = node.get_field("parse_dirty_reasons") or []
        if not reasons:
            continue

        # Build a human-readable reason from dirty reasons
        parts = [_REASON_LABELS.get(r, r) for r in reasons if r != "stale_hash"]
        if not parts:
            parts = ["update hash"]
        reason = "Auto-fix: " + ", ".join(parts)

        # Hash reflects what render_save will produce
        computed = compute_hash_for_node(node, hash_mode) or "N/A"

        entry = {
            "date": date.today().isoformat(),
            "hash": computed,
            "change_order": "-",
            "author_name": author["name"],
            "author_id": author["id"],
            "reason": reason,
        }
        graph.add_changelog_entry(node.id, entry)
        added += 1

    return added


def _fix_parse_dirty(args: argparse.Namespace, dry_run: bool) -> None:
    """Rewrite files that contain parse-dirty requirements.

    Uses render_save() so the rendered output is canonical: one Implements/
    Refines line, deduplicated refs, recomputed hash, canonical term forms.
    Adds changelog entries for Active requirements when changelog is enabled.
    """
    from elspais.config import get_config
    from elspais.graph import NodeKind
    from elspais.graph.factory import build_graph
    from elspais.graph.render import render_save

    spec_dir = getattr(args, "spec_dir", None)
    config_path = getattr(args, "config", None)
    repo_root = getattr(args, "git_root", None) or Path.cwd()

    config = get_config(config_path)
    graph = build_graph(
        spec_dirs=[spec_dir] if spec_dir else None,
        config_path=config_path,
        repo_root=repo_root,
        scan_code=False,
        scan_tests=False,
    )

    dirty_nodes = [
        node
        for node in graph.nodes_by_kind(NodeKind.REQUIREMENT)
        if node.get_field("parse_dirty")
        and any(r != "stale_hash" for r in (node.get_field("parse_dirty_reasons") or []))
    ]
    if not dirty_nodes:
        return

    if dry_run:
        for node in dirty_nodes:
            reasons = node.get_field("parse_dirty_reasons") or []
            print(f"Would rewrite {node.id}: {', '.join(reasons)}")
        return

    # Add auto-fix changelog entries before render_save
    _add_autofix_changelog_entries(graph, dirty_nodes, config)

    result = render_save(graph, repo_root=repo_root)
    for file_path in result.get("written", []):
        print(f"Rewrote {file_path}")


def _make_validate_args(args: argparse.Namespace) -> argparse.Namespace:
    """Build a validate-compatible args namespace from fix args."""
    return argparse.Namespace(
        # Shared CLI args
        spec_dir=getattr(args, "spec_dir", None),
        config=getattr(args, "config", None),
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
    """Fix a single requirement via the render pipeline.

    Builds the graph (which canonicalizes terms and marks dirty nodes),
    then uses render_save to re-render the file containing the target
    requirement.  This ensures canonical term forms, correct hashes,
    and deduplicated references — all through one render path.
    """
    from datetime import date

    from elspais.commands.validate import compute_hash_for_node
    from elspais.config import get_config
    from elspais.graph import NodeKind
    from elspais.graph.factory import build_graph
    from elspais.graph.render import render_save

    spec_dir = getattr(args, "spec_dir", None)
    config_path = getattr(args, "config", None)
    dry_run = getattr(args, "dry_run", False)
    message = getattr(args, "message", None)
    repo_root = Path(spec_dir).parent if spec_dir else Path.cwd()

    config = get_config(config_path)
    typed_config = _validate_config(config)
    changelog_enforce = typed_config.changelog.hash_current

    graph = build_graph(
        spec_dirs=[spec_dir] if spec_dir else None,
        config_path=config_path,
        repo_root=repo_root,
        scan_code=False,
        scan_tests=False,
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
    stored = node.hash

    _fn = node.file_node()
    if _fn is None:
        print(f"Error: No source file for {req_id}", file=sys.stderr)
        return 1

    # Check if the node's file is already dirty (e.g. from term canonicalization)
    is_dirty = node.get_field("parse_dirty") or False
    dirty_reasons = node.get_field("parse_dirty_reasons") or []
    # Hash changed if computed differs from stored.  N/A sentinel for no assertions.
    effective_hash = computed or "N/A"
    hash_changed = stored != effective_hash
    status = (node.status or "").lower()
    is_active = status == "active"

    # Any change (dirty or hash mismatch) warrants a changelog entry
    something_to_fix = is_dirty or hash_changed
    # Also check for missing changelog section on Active reqs
    existing_changelog = node.get_field("changelog") or []
    needs_new_section = is_active and changelog_enforce and not existing_changelog

    if not something_to_fix and not needs_new_section:
        print(f"{req_id} is already up to date")
        return 0

    if dry_run:
        changes = []
        if hash_changed:
            changes.append(f"hash {stored or '(none)'} -> {effective_hash}")
        for r in dirty_reasons:
            if r != "stale_hash":
                changes.append(_REASON_LABELS.get(r, r))
        if needs_new_section and not something_to_fix:
            changes.append("add missing changelog section")
        print(f"Would fix {req_id}: {', '.join(changes) or 'no changes'}")
        return 0

    # Add changelog entry when changelog is enabled for Active reqs
    if is_active and changelog_enforce:
        # Use explicit message if provided, otherwise auto-generate
        if message:
            reason = message
        elif something_to_fix:
            parts = [_REASON_LABELS.get(r, r) for r in dirty_reasons if r != "stale_hash"]
            if hash_changed and not parts:
                parts = ["update hash"]
            reason = "Auto-fix: " + ", ".join(parts) if parts else "Auto-fix: update hash"
        else:
            reason = "Adding missing Changelog section"

        from elspais.utilities.git import get_author_info

        id_source = typed_config.changelog.id_source
        try:
            author = get_author_info(id_source)
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

        cl_entry = {
            "date": date.today().isoformat(),
            "hash": effective_hash,
            "change_order": "-",
            "author_name": author["name"],
            "author_id": author["id"],
            "reason": reason,
        }
        graph.add_changelog_entry(req_id, cl_entry)

    # Always mark the target node dirty so render_save picks up its file.
    # "fix_single" overrides the stale_hash filter in _find_dirty_files.
    node._content["parse_dirty"] = True
    node._content.setdefault("parse_dirty_reasons", [])
    if "fix_single" not in node._content["parse_dirty_reasons"]:
        node._content["parse_dirty_reasons"].append("fix_single")

    result = render_save(graph, repo_root=repo_root)
    if result.get("errors"):
        for err in result["errors"]:
            print(f"Error: {err}", file=sys.stderr)
        return 1

    saved = result.get("saved_count", 0)
    if saved > 0:
        rel = _fn.get_field("relative_path") or req_id
        print(f"Fixed {req_id} in {rel}")
    else:
        print(f"{req_id} is already up to date")
    return 0


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

    config = get_config(config_path)
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
    )

    _regenerate_index(graph, all_spec_dirs, args)


# Implements: REQ-d00225-B
def _fix_terms(args: argparse.Namespace, dry_run: bool) -> None:
    """Generate glossary and term index if terms are defined."""
    from elspais.config import get_config
    from elspais.graph.factory import build_graph

    config_path = getattr(args, "config", None)
    spec_dir = getattr(args, "spec_dir", None)
    config = get_config(config_path)
    terms_config = config.get("terms", {})
    output_dir = terms_config.get("output_dir", "spec/_generated")

    graph = build_graph(
        spec_dirs=[spec_dir] if spec_dir else None,
        config_path=config_path,
        scan_code=False,
        scan_tests=False,
    )

    # Get terms from the graph
    td = None
    if hasattr(graph, "_terms"):
        td = graph._terms
    else:
        # FederatedGraph — check root repo
        for entry in graph._repos.values():
            if entry.graph and hasattr(entry.graph, "_terms"):
                td = entry.graph._terms
                break

    if td is None or len(td) == 0:
        return

    if dry_run:
        print(f"Would generate glossary and term index in {output_dir}")
        return

    from elspais.commands.glossary_cmd import write_term_outputs

    generated = write_term_outputs(td, output_dir)
    for path in generated:
        print(f"Generated: {path}")
