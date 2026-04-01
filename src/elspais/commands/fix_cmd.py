# Implements: REQ-p00004-A
"""
elspais.commands.fix_cmd - Auto-fix spec file issues.

Single-pass pipeline: build graph → detect dirty → changelog entries →
render_save. Handles hash mismatches, spacing canonicalization, term
forms, changelog drift, and missing changelog sections.
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

    Single pipeline: build graph -> detect dirty -> add changelog -> render_save.
    No second graph build, no validate pass.

    - fix (no req_id): fix all fixable issues in one pass
    - fix REQ-xxx:     targeted fix for a single requirement
    """
    target_req_id = getattr(args, "req_id", None)

    if target_req_id:
        return _fix_single(args, target_req_id)

    dry_run = getattr(args, "dry_run", False)

    # Single-pass fix: build graph, detect dirty nodes, add changelog
    # entries, render_save to disk.
    _fix_parse_dirty(args, dry_run)

    # Fix stale INDEX.md if present
    _fix_index(args, dry_run)

    # Implements: REQ-d00225-B
    # Generate glossary and term index if terms are defined
    _fix_terms(args, dry_run)

    return 0


_REASON_LABELS: dict[str, str] = {
    "non_canonical_term": "canonicalize term forms",
    "duplicate_refs": "deduplicate Implements/Refines references",
    "stale_hash": "update hash",
    "hash_mismatch": "update hash",
    "changelog_drift": "sync changelog hash",
    "missing_changelog": "add missing changelog section",
    "assertion_spacing": "fix assertion spacing",
    "list_spacing": "fix list spacing",
    "fix_single": "fix requirement",
}


def _detect_fixable(node, hash_mode: str, changelog_enforce: bool) -> list[str]:  # noqa: ANN001
    """Detect all fixable conditions on a requirement node.

    Returns a list of reason strings describing what needs fixing.
    Empty list means the node is clean.

    Checks:
    - parse_dirty reasons (term canonicalization, spacing, duplicate refs)
    - hash mismatch (computed vs stored End marker hash)
    - changelog hash drift (latest entry hash != stored hash)
    - missing changelog section (Active req with enforcement, no entries)
    """
    from elspais.graph.render import compute_hash_for_node

    reasons: list[str] = []

    # 1. Parse-dirty reasons from builder (excluding stale_hash which is
    #    superseded by our own hash_mismatch check)
    if node.get_field("parse_dirty"):
        for r in node.get_field("parse_dirty_reasons") or []:
            if r != "stale_hash":
                reasons.append(r)

    # 2. Hash mismatch
    stored = node.hash or ""
    computed = compute_hash_for_node(node, hash_mode)
    effective = computed or "N/A"
    if stored and stored != effective:
        reasons.append("hash_mismatch")

    # 3. Changelog checks (Active reqs with changelog enforcement only)
    status = (node.status or "").lower()
    if status == "active" and changelog_enforce:
        changelog = node.get_field("changelog") or []
        if not changelog:
            # Missing changelog section
            reasons.append("missing_changelog")
        else:
            # Changelog hash drift
            latest_hash = changelog[0].get("hash", "")
            if latest_hash and stored and latest_hash != stored:
                reasons.append("changelog_drift")

    return reasons


def _get_author(config: dict[str, Any]) -> dict[str, str] | None:
    """Look up author info from config. Returns None on failure."""
    from elspais.utilities.git import get_author_info

    typed_config = _validate_config(config)
    id_source = typed_config.changelog.id_source
    try:
        return get_author_info(id_source)
    except ValueError:
        return None


def _make_changelog_entry(
    hash_value: str,
    reason: str,
    author: dict[str, str],
) -> dict[str, str]:
    """Create a single changelog entry dict."""
    from datetime import date

    return {
        "date": date.today().isoformat(),
        "hash": hash_value,
        "change_order": "-",
        "author_name": author["name"],
        "author_id": author["id"],
        "reason": reason,
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
    typed_config = _validate_config(config)
    if not typed_config.changelog.hash_current:
        return 0

    from elspais.graph.render import compute_hash_for_node

    author = _get_author(config)
    if author is None:
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

        computed = compute_hash_for_node(node, hash_mode) or "N/A"
        entry = _make_changelog_entry(computed, reason, author)
        graph.add_changelog_entry(node.id, entry)
        added += 1

    return added


def _add_drift_changelog_entries(
    graph,  # noqa: ANN001 — FederatedGraph
    drift_nodes: list,
    config: dict[str, Any],
) -> int:
    """Add changelog entries for requirements with stale changelog hashes.

    When a requirement's most recent changelog hash doesn't match the
    stored End marker hash (e.g. after a format migration), adds a new
    changelog entry with the current hash.  Returns the count added.
    """
    author = _get_author(config)
    if author is None:
        return 0

    added = 0
    for node in drift_nodes:
        stored = node.hash or ""
        entry = _make_changelog_entry(stored, "Auto-fix: sync changelog hash", author)
        graph.add_changelog_entry(node.id, entry)
        # Mark dirty so render_save picks up the file
        node._content["parse_dirty"] = True
        node._content.setdefault("parse_dirty_reasons", [])
        if "changelog_drift" not in node._content["parse_dirty_reasons"]:
            node._content["parse_dirty_reasons"].append("changelog_drift")
        added += 1

    return added


def _fix_parse_dirty(args: argparse.Namespace, dry_run: bool) -> None:
    """Single-pass fix: build graph, detect all fixable issues, render to disk.

    Uses _detect_fixable() for comprehensive detection (parse dirty, hash
    mismatch, changelog drift, missing changelog) and render_save() for
    canonical output.
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

    typed_config = _validate_config(config)
    changelog_enforce = typed_config.changelog.hash_current
    hash_mode = getattr(graph, "hash_mode", "full-text")

    # Detect all fixable issues using the unified detection function
    fixable_nodes: list[tuple[Any, list[str]]] = []  # (node, reasons)
    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        reasons = _detect_fixable(node, hash_mode, changelog_enforce)
        if reasons:
            fixable_nodes.append((node, reasons))

    if not fixable_nodes:
        req_count = sum(1 for _ in graph.nodes_by_kind(NodeKind.REQUIREMENT))
        print(f"Validated {req_count} requirements")
        return

    # Report what will be / was fixed
    prefix = "Would fix" if dry_run else "Fixing"
    for node, reasons in fixable_nodes:
        for r in reasons:
            if r == "non_canonical_term":
                repls = node.get_field("term_replacements") or []
                seen: set[tuple[str, str]] = set()
                for old_form, new_form in repls:
                    if (old_form, new_form) not in seen:
                        seen.add((old_form, new_form))
                        print(f"{prefix} {node.id}: canonicalize term {old_form} -> {new_form}")
            else:
                print(f"{prefix} {node.id}: {_REASON_LABELS.get(r, r)}")

    if dry_run:
        return

    # Separate nodes by fix type for changelog entries
    dirty_nodes = [
        n
        for n, reasons in fixable_nodes
        if any(r not in ("changelog_drift", "missing_changelog") for r in reasons)
    ]
    drift_nodes = [
        n for n, reasons in fixable_nodes if "changelog_drift" in reasons and n not in dirty_nodes
    ]

    # Add auto-fix changelog entries before render_save
    _add_autofix_changelog_entries(graph, dirty_nodes, config)
    _add_drift_changelog_entries(graph, drift_nodes, config)

    # Mark all fixable nodes dirty so render_save picks up their files
    for node, reasons in fixable_nodes:
        node._content["parse_dirty"] = True
        node._content.setdefault("parse_dirty_reasons", [])
        for r in reasons:
            if r not in node._content["parse_dirty_reasons"]:
                node._content["parse_dirty_reasons"].append(r)

    result = render_save(graph, repo_root=repo_root)
    saved = result.get("saved_count", 0)
    if saved:
        files = result.get("files_modified", [])
        for f in files:
            print(f"Rewrote {f}")

    req_count = sum(1 for _ in graph.nodes_by_kind(NodeKind.REQUIREMENT))
    print(f"Validated {req_count} requirements")


def _fix_single(args: argparse.Namespace, req_id: str) -> int:
    """Fix a single requirement via the render pipeline.

    Builds the graph (which canonicalizes terms and marks dirty nodes),
    then uses render_save to re-render the file containing the target
    requirement.  This ensures canonical term forms, correct hashes,
    and deduplicated references — all through one render path.
    """
    from elspais.config import get_config
    from elspais.graph import NodeKind
    from elspais.graph.factory import build_graph
    from elspais.graph.render import compute_hash_for_node, render_save

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

    # Check for changelog hash drift (changelog entry hash != stored hash)
    changelog_hash_drifted = False
    if is_active and changelog_enforce and existing_changelog:
        latest_cl_hash = existing_changelog[0].get("hash", "")
        if latest_cl_hash and stored and latest_cl_hash != stored:
            changelog_hash_drifted = True

    if not something_to_fix and not needs_new_section and not changelog_hash_drifted:
        print(f"{req_id} is already up to date")
        return 0

    if dry_run:
        prefix = "Would fix"
        if hash_changed:
            print(f"{prefix} {req_id}: hash {stored or '(none)'} -> {effective_hash}")
        for r in dirty_reasons:
            if r == "stale_hash":
                continue
            if r == "non_canonical_term":
                repls = node.get_field("term_replacements") or []
                seen: set[tuple[str, str]] = set()
                for old_form, new_form in repls:
                    if (old_form, new_form) not in seen:
                        seen.add((old_form, new_form))
                        print(f"{prefix} {req_id}: canonicalize term {old_form} -> {new_form}")
            else:
                print(f"{prefix} {req_id}: {_REASON_LABELS.get(r, r)}")
        if changelog_hash_drifted and not something_to_fix:
            print(f"{prefix} {req_id}: sync changelog hash")
        if needs_new_section and not something_to_fix and not changelog_hash_drifted:
            print(f"{prefix} {req_id}: add missing changelog section")
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
        elif changelog_hash_drifted:
            reason = "Auto-fix: sync changelog hash"
        else:
            reason = "Adding missing Changelog section"

        author = _get_author(config)
        if author is None:
            print("Error: Could not determine author info", file=sys.stderr)
            return 1

        cl_entry = _make_changelog_entry(effective_hash, reason, author)
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
    from elspais.utilities.spec_writer import add_changelog_entry

    author = _get_author(config)
    if author is None:
        print("Error: Could not determine author info", file=sys.stderr)
        return 1

    entry = _make_changelog_entry(current_hash, "Adding missing Changelog section", author)
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
    if hasattr(graph, "terms"):
        td = graph.terms
    else:
        # FederatedGraph — check root repo
        for entry in graph._repos.values():
            if entry.graph and hasattr(entry.graph, "terms"):
                td = entry.graph.terms
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
