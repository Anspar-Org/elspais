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


# Implements: REQ-d00217-B
def _repo_name_for(graph: FederatedGraph, node_id: str) -> str | None:
    """Return the owning repo's name for a node ID, or None if unknown.

    Uses ``FederatedGraph.repo_for(node_id).name`` directly. REQ/JNY IDs are
    forbidden from colliding cross-repo, so this lookup is unambiguous (unlike
    a FILE-node-based lookup, since two repos may share a relative path).

    For backward compat with callers passing a bare ``TraceGraph`` (legacy
    code paths and tests), returns ``"root"`` if the graph has no
    ``repo_for`` method.
    """
    if not hasattr(graph, "repo_for"):
        return "root"
    try:
        return graph.repo_for(node_id).name
    except KeyError:
        return None


def _repo_spec_dirs(graph: FederatedGraph, repo_name: str, fallback: list[Path]) -> list[Path]:
    """Return the absolute spec directory paths for a repo.

    Reads ``[scanning.spec].directories`` from the repo's config when
    available; falls back to ``fallback`` (the caller's spec_dirs) for
    bare-TraceGraph callers or repos with no config.
    """
    if hasattr(graph, "iter_repos"):
        for entry in graph.iter_repos():
            if entry.name != repo_name or entry.config is None:
                continue
            scanning = entry.config.get("scanning", {})
            spec_cfg = scanning.get("spec", {}) if isinstance(scanning, dict) else {}
            dirs = spec_cfg.get("directories") if isinstance(spec_cfg, dict) else None
            if dirs:
                return [Path(d) if Path(d).is_absolute() else entry.repo_root / d for d in dirs]
            return [entry.repo_root / "spec"]
    return fallback


def _classify_node(node: object, spec_dirs: list[Path]) -> Path | None:
    """Return the most-specific spec directory containing the node's source.

    Within-repo classifier used for per-spec-dir subsection labels. Repo
    attribution itself is handled separately by ``_repo_name_for`` so this
    function only resolves the *secondary* dimension (which spec dir within
    the already-attributed repo).
    """
    fn = node.file_node() if hasattr(node, "file_node") else None
    if fn is None:
        return None
    abs_path = fn.get_field("absolute_path")
    if not abs_path:
        return None
    source_path = Path(abs_path)
    for spec_dir in sorted(spec_dirs, key=lambda p: len(p.resolve().parts), reverse=True):
        try:
            source_path.relative_to(spec_dir.resolve())
            return spec_dir
        except ValueError:
            continue
    return None


def _resolve_repo_info(
    graph: FederatedGraph, repo_name: str, fallback_dir: Path | None = None
) -> _SpecDirInfo:
    """Resolve label and level ordering for a repo by name.

    Reads the repo's config from FederatedGraph for level rank/display name.
    Falls back to scanning ``fallback_dir`` for a `.elspais.toml` when the
    graph is a bare TraceGraph (legacy caller) and config isn't otherwise
    accessible.
    """
    from elspais.config.schema import ElspaisConfig

    label = repo_name
    level_order: dict[str, int] = {}
    level_names: dict[str, str] = {}

    config = None
    if hasattr(graph, "iter_repos"):
        for entry in graph.iter_repos():
            if entry.name == repo_name and entry.config is not None:
                config = entry.config
                break

    if config is None and fallback_dir is not None:
        # Legacy fallback: walk up from spec dir to find .elspais.toml
        from elspais.config import get_config

        current = fallback_dir.resolve()
        while current != current.parent:
            cfg_file = current / ".elspais.toml"
            if cfg_file.exists():
                config = get_config(cfg_file, current)
                break
            current = current.parent

    if config is not None:
        schema_fields = {f.alias or name for name, f in ElspaisConfig.model_fields.items()} | set(
            ElspaisConfig.model_fields.keys()
        )
        filtered = {k: v for k, v in config.items() if k in schema_fields}
        assoc = filtered.get("associates")
        if isinstance(assoc, dict) and "paths" in assoc:
            filtered.pop("associates", None)
        try:
            typed_config = ElspaisConfig.model_validate(filtered)
            for level_key, level_cfg in typed_config.levels.items():
                level_order[level_key] = level_cfg.rank
                display = (level_cfg.display_name or level_key).upper()
                level_names[level_key] = display
        except Exception:
            pass

    return _SpecDirInfo(label=label, level_order=level_order, level_names=level_names)


def _build_index_content(
    graph: FederatedGraph, spec_dirs: list[Path]
) -> tuple[Path, str, int, int]:
    """Render INDEX.md content without writing.

    Returns (output_path, content, req_count, jny_count).

    Buckets nodes by ``(repo_name, spec_dir)``: repo attribution comes from
    ``FederatedGraph.repo_for()`` (fixes Bug 3 for foreign-repo nodes) and
    spec_dir comes from a within-repo path classifier (preserves per-dir
    subsections for projects with multiple spec dirs in a single repo).
    Nodes whose repo cannot be determined bucket under ``(UNATTRIBUTED, None)``.
    """
    # Implements: REQ-d00217-B
    from collections import defaultdict

    UNATTRIBUTED = "__unattributed__"

    Bucket = tuple[str, Path | None]

    reqs_by_bucket: dict[Bucket, list] = defaultdict(list)
    jnys_by_bucket: dict[Bucket, list] = defaultdict(list)
    repo_dirs_cache: dict[str, list[Path]] = {}

    def _bucket_for(node: object) -> Bucket:
        repo_name = _repo_name_for(graph, node.id) or UNATTRIBUTED
        if repo_name == UNATTRIBUTED:
            return (UNATTRIBUTED, None)
        if repo_name not in repo_dirs_cache:
            repo_dirs_cache[repo_name] = _repo_spec_dirs(graph, repo_name, spec_dirs)
        sd = _classify_node(node, repo_dirs_cache[repo_name])
        return (repo_name, sd)

    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        reqs_by_bucket[_bucket_for(node)].append(node)
    for node in graph.nodes_by_kind(NodeKind.USER_JOURNEY):
        jnys_by_bucket[_bucket_for(node)].append(node)

    # Order buckets: each repo in iter_repos() construction order, within
    # each repo its spec_dirs in the order returned by _repo_spec_dirs;
    # then any (repo, None) leftovers; then UNATTRIBUTED.
    active_buckets: list[Bucket] = []

    def _add_repo_buckets(repo_name: str, repo_dirs: list[Path]) -> None:
        seen: set[Bucket] = set()
        for sd in repo_dirs:
            b: Bucket = (repo_name, sd)
            if b in seen:
                continue
            if reqs_by_bucket.get(b) or jnys_by_bucket.get(b):
                active_buckets.append(b)
                seen.add(b)
        # Any (repo, None) — files that didn't match any of repo's spec_dirs.
        b_none: Bucket = (repo_name, None)
        if (reqs_by_bucket.get(b_none) or jnys_by_bucket.get(b_none)) and b_none not in seen:
            active_buckets.append(b_none)

    if hasattr(graph, "iter_repos"):
        for entry in graph.iter_repos():
            dirs = _repo_spec_dirs(graph, entry.name, spec_dirs)
            _add_repo_buckets(entry.name, dirs)
    else:
        _add_repo_buckets("root", spec_dirs)

    unatt_bucket: Bucket = (UNATTRIBUTED, None)
    if reqs_by_bucket.get(unatt_bucket) or jnys_by_bucket.get(unatt_bucket):
        active_buckets.append(unatt_bucket)

    # Resolve display info per bucket.
    bucket_info: dict[Bucket, _SpecDirInfo] = {}
    for b in active_buckets:
        repo_name, sd = b
        if repo_name == UNATTRIBUTED:
            bucket_info[b] = _SpecDirInfo(
                label="Unattributed",
                level_order={},
                level_names={},
            )
        elif sd is not None:
            bucket_info[b] = _resolve_spec_dir_info(sd)
        else:
            # Repo with no per-dir classification — label by repo name and
            # source level info from repo config.
            bucket_info[b] = _resolve_repo_info(
                graph, repo_name, spec_dirs[0] if spec_dirs else None
            )

    reqs_by_level_bucket: dict[str, dict[Bucket, list]] = defaultdict(lambda: defaultdict(list))
    for b in active_buckets:
        for node in reqs_by_bucket.get(b, []):
            level = node.level or ""
            reqs_by_level_bucket[level][b].append(node)

    first_info = (
        bucket_info[active_buckets[0]]
        if active_buckets
        else _SpecDirInfo(
            label="",
            level_order={},
            level_names={},
        )
    )
    all_levels = sorted(
        reqs_by_level_bucket.keys(),
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

        buckets_with_level = [b for b in active_buckets if reqs_by_level_bucket[level].get(b)]
        multi_bucket = len(buckets_with_level) > 1

        for b in buckets_with_level:
            info = bucket_info[b]
            nodes = reqs_by_level_bucket[level][b]

            if multi_bucket:
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
    all_jnys = [(b, jnys_by_bucket.get(b, [])) for b in active_buckets if jnys_by_bucket.get(b)]
    if all_jnys:
        lines.append("## User Journeys")
        lines.append("")

        multi_bucket = len(all_jnys) > 1
        for b, jnys in all_jnys:
            info = bucket_info[b]
            if multi_bucket:
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

    output_path = spec_dirs[0] / "INDEX.md" if spec_dirs else Path("spec/INDEX.md")
    content = "\n".join(lines)
    return output_path, content, req_count, jny_count


def _regenerate_index(
    graph: FederatedGraph, spec_dirs: list[Path], args: argparse.Namespace
) -> int:
    """Regenerate INDEX.md from graph requirements."""
    # Use git root (threaded from CLI) for relative paths
    repo_root = getattr(args, "git_root", None)
    if repo_root is None:
        print("Cannot generate INDEX.md: not in a git repository.", file=sys.stderr)
        return 1

    output_path, content, req_count, jny_count = _build_index_content(graph, spec_dirs)

    if output_path.exists():
        output_path.chmod(0o644)
    output_path.write_text(content, encoding="utf-8")
    output_path.chmod(0o444)

    print(f"Generated {output_path} ({req_count} requirements, {jny_count} journeys)")
    return 0
