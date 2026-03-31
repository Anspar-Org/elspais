# Implements: REQ-d00052-G
# Implements: REQ-d00217-A+B+C+D
"""
elspais.commands.index - INDEX.md management command.

Uses graph-based system:
- `elspais index validate` - Validate INDEX.md accuracy
- `elspais index regenerate` - Regenerate INDEX.md from requirements
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from elspais.graph.federated import FederatedGraph

from elspais.graph import NodeKind


def run(args: argparse.Namespace) -> int:
    """Run the index command."""
    from elspais.config import get_config, get_spec_directories
    from elspais.graph.factory import build_graph

    spec_dir = getattr(args, "spec_dir", None)
    config_path = getattr(args, "config", None)

    config = get_config(config_path)
    spec_dirs = get_spec_directories(spec_dir, config)

    all_spec_dirs = list(spec_dirs)

    graph = build_graph(
        config=config,
        spec_dirs=all_spec_dirs if spec_dir else None,
        config_path=config_path,
    )

    action = getattr(args, "index_action", None)

    if action == "validate":
        return _validate_index(graph, all_spec_dirs, args)
    elif action == "regenerate":
        return _regenerate_index(graph, all_spec_dirs, args)
    else:
        print("Usage: elspais index <validate|regenerate>", file=sys.stderr)
        return 1


def _validate_index(graph: FederatedGraph, spec_dirs: list[Path], args: argparse.Namespace) -> int:
    """Validate INDEX.md against graph requirements."""
    # Find INDEX.md
    index_path = None
    for spec_dir in spec_dirs:
        candidate = spec_dir / "INDEX.md"
        if candidate.exists():
            index_path = candidate
            break

    if not index_path:
        print("No INDEX.md found in spec directories.")
        print("Run 'elspais index regenerate' to create one.")
        return 1

    # Parse IDs from INDEX.md
    content = index_path.read_text()
    index_req_ids = set(re.findall(r"REQ-[a-z0-9-]+", content, re.IGNORECASE))
    index_jny_ids = set(re.findall(r"JNY-[A-Za-z0-9-]+", content))

    # Get IDs from graph
    graph_req_ids = {node.id for node in graph.nodes_by_kind(NodeKind.REQUIREMENT)}
    graph_jny_ids = {node.id for node in graph.nodes_by_kind(NodeKind.USER_JOURNEY)}

    # Compare requirements
    missing_reqs = graph_req_ids - index_req_ids
    extra_reqs = index_req_ids - graph_req_ids

    # Compare journeys
    missing_jnys = graph_jny_ids - index_jny_ids
    extra_jnys = index_jny_ids - graph_jny_ids

    has_issues = False

    if missing_reqs:
        print(f"Missing requirements from INDEX.md ({len(missing_reqs)}):")
        for req_id in sorted(missing_reqs):
            print(f"  {req_id}")
        has_issues = True

    if extra_reqs:
        print(f"Extra requirements in INDEX.md ({len(extra_reqs)}):")
        for req_id in sorted(extra_reqs):
            print(f"  {req_id}")
        has_issues = True

    if missing_jnys:
        print(f"Missing journeys from INDEX.md ({len(missing_jnys)}):")
        for jny_id in sorted(missing_jnys):
            print(f"  {jny_id}")
        has_issues = True

    if extra_jnys:
        print(f"Extra journeys in INDEX.md ({len(extra_jnys)}):")
        for jny_id in sorted(extra_jnys):
            print(f"  {jny_id}")
        has_issues = True

    if not has_issues:
        req_n = len(graph_req_ids)
        jny_n = len(graph_jny_ids)
        print(f"INDEX.md is up to date ({req_n} requirements, {jny_n} journeys)")
        return 0

    return 1


def _format_table(headers: list[str], rows: list[list[str]]) -> list[str]:
    """Format a markdown table with properly padded columns.

    Computes max width for each column and pads all cells to align pipes.
    """
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(cell))

    def _pad_row(cells: list[str]) -> str:
        padded = " | ".join(cell.ljust(col_widths[i]) for i, cell in enumerate(cells))
        return f"| {padded} |"

    lines = [_pad_row(headers)]
    lines.append("| " + " | ".join("-" * w for w in col_widths) + " |")
    for row in rows:
        lines.append(_pad_row(row))
    return lines


@dataclass
class _SpecDirInfo:
    """Resolved metadata for a spec directory."""

    label: str  # e.g. "elspais/spec"
    level_order: dict[str, int]  # e.g. {"PRD": 1, "OPS": 2, "DEV": 3}
    level_names: dict[str, str]  # e.g. {"PRD": "Product", "OPS": "Operations"}


def _resolve_spec_dir_info(spec_dir: Path) -> _SpecDirInfo:
    """Resolve label and level ordering for a spec directory.

    Finds the nearest ``.elspais.toml`` above *spec_dir* and reads
    the project name and level definitions via typed config.
    """
    # Implements: REQ-d00212-F, REQ-d00207-C
    from elspais.config import get_config
    from elspais.config.schema import ElspaisConfig

    resolved = spec_dir.resolve()
    current = resolved
    while current != current.parent:
        config_file = current / ".elspais.toml"
        if config_file.exists():
            cfg = get_config(config_file, current)
            # Use typed config for validated access
            schema_fields = {
                f.alias or name for name, f in ElspaisConfig.model_fields.items()
            } | set(ElspaisConfig.model_fields.keys())
            filtered = {k: v for k, v in cfg.items() if k in schema_fields}
            # Strip legacy associates.paths list (v3 expects named entries)
            assoc = filtered.get("associates")
            if isinstance(assoc, dict) and "paths" in assoc:
                filtered.pop("associates", None)
            typed_config = ElspaisConfig.model_validate(filtered)
            project_name = typed_config.project.name or current.name
            try:
                spec_subpath = str(resolved.relative_to(current))
            except ValueError:
                spec_subpath = resolved.name
            label = f"{project_name}/{spec_subpath}"

            # Build level ordering from typed config levels
            level_order: dict[str, int] = {}
            level_names: dict[str, str] = {}
            for level_key, level_cfg in typed_config.levels.items():
                level_order[level_key] = level_cfg.rank
                display = (level_cfg.display_name or level_key).upper()
                level_names[level_key] = display

            return _SpecDirInfo(label=label, level_order=level_order, level_names=level_names)
        current = current.parent

    # No config found — use directory names, no level ordering
    return _SpecDirInfo(
        label=f"{resolved.parent.name}/{resolved.name}",
        level_order={},
        level_names={},
    )


def _classify_node(node: object, spec_dirs: list[Path]) -> Path | None:
    """Return the most-specific spec directory that contains a node's source file.

    Checks deepest paths first so ``spec/regulations/fda`` matches before ``spec``.
    """
    # Implements: REQ-d00129-D
    fn = node.file_node() if hasattr(node, "file_node") else None
    rp = fn.get_field("relative_path") if fn else None
    if not rp:
        return None
    source_path = Path(rp).resolve()
    # Sort deepest-first so nested dirs match before their parents
    for spec_dir in sorted(spec_dirs, key=lambda p: len(p.resolve().parts), reverse=True):
        resolved = spec_dir.resolve()
        try:
            source_path.relative_to(resolved)
            return spec_dir
        except ValueError:
            continue
    return None


def _regenerate_index(
    graph: FederatedGraph, spec_dirs: list[Path], args: argparse.Namespace
) -> int:
    """Regenerate INDEX.md from graph requirements."""
    # Use git root (threaded from CLI) for relative paths
    repo_root = getattr(args, "git_root", None)
    if repo_root is None:
        print("Cannot generate INDEX.md: not in a git repository.", file=sys.stderr)
        return 1

    # Group requirements by spec directory
    from collections import defaultdict

    reqs_by_dir: dict[Path | None, list] = defaultdict(list)
    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        spec_dir = _classify_node(node, spec_dirs)
        reqs_by_dir[spec_dir].append(node)

    jnys_by_dir: dict[Path | None, list] = defaultdict(list)
    for node in graph.nodes_by_kind(NodeKind.USER_JOURNEY):
        spec_dir = _classify_node(node, spec_dirs)
        jnys_by_dir[spec_dir].append(node)

    # Build ordered list of spec dirs that have content
    active_dirs: list[Path] = []
    for sd in spec_dirs:
        if reqs_by_dir.get(sd) or jnys_by_dir.get(sd):
            active_dirs.append(sd)
    # Append None bucket for nodes with unknown source
    if reqs_by_dir.get(None) or jnys_by_dir.get(None):
        active_dirs.append(None)  # type: ignore[arg-type]

    # Resolve info for each spec directory
    dir_info: dict[Path | None, _SpecDirInfo] = {}
    for sd in active_dirs:
        if sd is None:
            dir_info[None] = _SpecDirInfo(
                label="Unknown Source",
                level_order={},
                level_names={},
            )
        else:
            dir_info[sd] = _resolve_spec_dir_info(sd)

    # Build (level, spec_dir) -> [nodes] index
    from collections import defaultdict as _defaultdict

    reqs_by_level_dir: dict[str, dict[Path | None, list]] = _defaultdict(lambda: _defaultdict(list))
    for sd in active_dirs:
        for node in reqs_by_dir.get(sd, []):
            level = node.level or ""
            reqs_by_level_dir[level][sd].append(node)

    # Collect all levels across all dirs, sorted by dependency order.
    # Use the first dir's config for ordering (all dirs in same project
    # share config; for multi-project the ordering is still reasonable).
    first_info = (
        dir_info[active_dirs[0]]
        if active_dirs
        else _SpecDirInfo(
            label="",
            level_order={},
            level_names={},
        )
    )
    all_levels = sorted(
        reqs_by_level_dir.keys(),
        key=lambda lv: first_info.level_order.get(lv, 99),
    )

    # Generate markdown
    lines = [
        "<!-- Auto-generated by: elspais fix -->",
        "<!-- Do not edit manually; changes will be overwritten. -->",
        "<!-- markdownlint-disable MD013 -->",
        "",
        "# Requirements Index",
        "",
    ]

    req_count = 0
    jny_count = 0

    # Requirements: level is the outermost grouping
    for level in all_levels:
        level_display = first_info.level_names.get(level, level.upper())
        lines.append(f"## {level_display}")
        lines.append("")

        dirs_with_level = [sd for sd in active_dirs if reqs_by_level_dir[level].get(sd)]
        multi_dir = len(dirs_with_level) > 1

        for sd in dirs_with_level:
            info = dir_info[sd]
            nodes = reqs_by_level_dir[level][sd]

            if multi_dir:
                lines.append(f"### {info.label}")
                lines.append("")

            headers = ["ID", "Title", "File", "Hash"]
            rows = []
            for node in sorted(nodes, key=lambda n: n.id):
                _fn = node.file_node()
                _rp = _fn.get_field("relative_path") if _fn else None
                filename = Path(_rp).name if _rp else ""
                hash_val = node.hash or ""
                rows.append([node.id, node.get_label(), filename, hash_val])
            lines.extend(_format_table(headers, rows))
            lines.append("")
            req_count += len(nodes)

    # User Journeys: after all requirements
    all_jnys = [(sd, jnys_by_dir.get(sd, [])) for sd in active_dirs if jnys_by_dir.get(sd)]
    if all_jnys:
        lines.append("## User Journeys")
        lines.append("")

        multi_dir = len(all_jnys) > 1
        for sd, jnys in all_jnys:
            info = dir_info[sd]
            if multi_dir:
                lines.append(f"### {info.label}")
                lines.append("")

            headers = ["ID", "Title", "Actor", "File"]
            rows = []
            for node in sorted(jnys, key=lambda n: n.id):
                actor = node.get_field("actor") or ""
                _fn = node.file_node()
                _rp = _fn.get_field("relative_path") if _fn else None
                filename = Path(_rp).name if _rp else ""
                rows.append([node.id, node.get_label(), actor, filename])
            lines.extend(_format_table(headers, rows))
            lines.append("")
            jny_count += len(jnys)

    # Write to first spec dir
    output_path = spec_dirs[0] / "INDEX.md" if spec_dirs else Path("spec/INDEX.md")
    if output_path.exists():
        output_path.chmod(0o644)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    output_path.chmod(0o444)

    print(f"Generated {output_path} ({req_count} requirements, {jny_count} journeys)")
    return 0
