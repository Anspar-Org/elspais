# Implements: REQ-p00080-B, REQ-p00080-C, REQ-p00080-D, REQ-p00080-E, REQ-p00080-F
"""Markdown assembler for PDF compilation.

Uses the graph for file ordering metadata (level, depth), then reads the
source spec files directly to preserve all content faithfully.
"""
from __future__ import annotations

import logging
import re
import shutil
import subprocess
from collections import defaultdict
from pathlib import Path

from elspais.graph.federated import FederatedGraph
from elspais.graph.GraphNode import GraphNode, NodeKind
from elspais.utilities.patterns import IdResolver, build_resolver


def _build_level_metadata(
    config: dict | None,
) -> tuple[dict[str, int], dict[str, str], re.Pattern[str]]:
    """Return (order, headings, prefix_re) derived from `[levels]` config.

    Order: uppercase level key -> rank.
    Headings: uppercase level key -> display_name + " Requirements" fallback.
    prefix_re: regex matching `<level_key>-` or numeric prefix at filename start.

    Falls back to the schema's default `[levels]` block (via
    `elspais.config.config_defaults()`) when no config is passed, so the
    fallback table is the single source of truth from the pydantic schema.
    """
    from elspais.config import config_defaults

    levels_cfg = (config or {}).get("levels") if config else None
    if not isinstance(levels_cfg, dict) or not levels_cfg:
        levels_cfg = config_defaults().get("levels") or {}

    order: dict[str, int] = {}
    headings: dict[str, str] = {}
    keys: list[str] = []
    for key, entry in levels_cfg.items():
        rank = (entry or {}).get("rank") if isinstance(entry, dict) else None
        if rank is None:
            continue
        upper = key.upper()
        order[upper] = int(rank)
        display = (entry or {}).get("display_name") if isinstance(entry, dict) else None
        headings[upper] = f"{display or key.title()} Requirements"
        keys.append(re.escape(key.lower()))

    if not keys:
        # Final defensive fallback: numeric prefixes only.
        return order, headings, re.compile(r"^\d+-?", re.IGNORECASE)

    alt = "|".join(keys)
    prefix_re = re.compile(rf"^(?:{alt}|\d+)-?", re.IGNORECASE)
    return order, headings, prefix_re


# Matches requirement heading lines at any heading level: # REQ-xxx or ## REQ-xxx
_REQ_HEADING_RE = re.compile(r"^(#{1,3})\s+(REQ-\S+)")

# Matches footer lines: *End* *Title* | **Hash**: ...
_FOOTER_RE = re.compile(r"^\*End\*")

# Matches Markdown image references to .mmd files: ![alt](path.mmd)
_MMD_IMAGE_RE = re.compile(r"(!\[[^\]]*\]\()([^)]+\.mmd)(\))")

log = logging.getLogger(__name__)


class MarkdownAssembler:
    """Assembles structured Markdown from spec files.

    Uses the graph only for metadata: which files contain requirements,
    what level they belong to, and how to order them by graph depth.
    Content comes directly from the source spec files.
    """

    def __init__(
        self,
        graph: FederatedGraph,
        title: str | None = None,
        overview: bool = False,
        max_depth: int | None = None,
        resolver: IdResolver | None = None,
        config: dict | None = None,
    ) -> None:
        self._graph = graph
        self._overview = overview
        self._max_depth = max_depth
        if title:
            self._title = title
        elif overview:
            self._title = "Product Requirements Overview"
        else:
            self._title = "Requirements Specification"
        if resolver is None:
            resolver = build_resolver({})
        self._resolver = resolver
        order, headings, prefix_re = _build_level_metadata(config)
        self._level_order = order
        self._level_headings = headings
        self._level_prefix_re = prefix_re

    def assemble(self) -> str:
        """Assemble the complete Markdown document.

        Returns:
            Structured Markdown string ready for Pandoc.
        """
        parts: list[str] = []

        # YAML metadata header for Pandoc
        from elspais.utilities.report_meta import report_metadata

        meta = report_metadata()
        parts.append("---")
        parts.append(f'title: "{self._title}"')
        parts.append(f'subtitle: "elspais {meta["version"]}, {meta["date"]}, {meta["source"]}"')
        parts.append("toc: true")
        parts.append("toc-depth: 2")
        parts.append("---")
        parts.append("")

        # Group requirements by file, then partition by level
        file_groups = self._group_by_file()
        # Map each file path to its owning repo (root or associate). Files
        # whose nodes span multiple repos are extraordinarily rare; the
        # first node wins (matches _group_by_file's document order).
        # Non-federated graphs (legacy callers passing a bare TraceGraph)
        # surface as an empty owner map; everything renders as root.
        file_owners: dict[str, str] = {}
        repo_for = getattr(self._graph, "repo_for", None)
        if callable(repo_for):
            for fp, nodes in file_groups.items():
                for node in nodes:
                    try:
                        file_owners[fp] = repo_for(node.id).name
                        break
                    except KeyError:
                        continue
        level_buckets = self._partition_by_level(file_groups)

        # Emit each level group
        if self._overview:
            levels_to_emit = ("PRD",)
        else:
            levels_to_emit = ("PRD", "OPS", "DEV")

        for level in levels_to_emit:
            files = level_buckets.get(level, [])
            if not files:
                continue

            # Apply max_depth filter for core files in overview mode
            if self._overview and self._max_depth is not None:
                files = self._filter_by_depth(files, file_groups)

            if not files:
                continue

            heading = self._level_headings.get(level, level)
            parts.append(f"# {heading}")
            parts.append("")

            # Sort files within level by graph depth, then alphabetically
            sorted_files = self._sort_files_by_depth(files, file_groups)

            for file_path in sorted_files:
                owner_root = self._repo_root_for_owner(file_owners.get(file_path))
                parts.extend(self._render_file(file_path, owning_repo_root=owner_root))

        # Topic index — scope to rendered files only in overview mode
        if self._overview:
            rendered_files: set[str] = set()
            for level in levels_to_emit:
                bucket = level_buckets.get(level, [])
                if self._max_depth is not None:
                    bucket = self._filter_by_depth(bucket, file_groups)
                rendered_files.update(bucket)
            index_groups = {k: v for k, v in file_groups.items() if k in rendered_files}
        else:
            index_groups = file_groups
        index_section = self._build_topic_index(index_groups, file_owners=file_owners)
        if index_section:
            parts.append("# Topic Index")
            parts.append("")
            parts.extend(index_section)

        return "\n".join(parts)

    # ------------------------------------------------------------------
    # File rendering — reads source files directly
    # ------------------------------------------------------------------

    def _render_file(self, file_path: str, owning_repo_root: Path | None = None) -> list[str]:
        """Render a spec file's content with adjusted heading levels.

        Reads the file directly. Detects the heading level used for requirements
        in this file (e.g., `#` or `##`), then adjusts all headings so that:
        - File title → `##`
        - Requirement headings → `###` with anchor and page break
        - Sub-sections within requirements → `####`
        - `---` separators and `*End*` footer lines → stripped

        ``owning_repo_root`` anchors path resolution to the file's owning
        associate when supplied (cross-repo PDF rendering).
        """
        resolved = self._resolve_path(file_path, owning_repo_root=owning_repo_root)
        if not resolved or not resolved.exists():
            return []

        source = resolved.read_text(encoding="utf-8")
        # Strip control characters that break LaTeX (keep \n \r \t)
        source = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", source)
        source_lines = source.split("\n")

        seen_file_title = False

        lines: list[str] = ["\\newpage", ""]
        for line in source_lines:
            # Strip horizontal rules (requirement separators)
            if line.strip() == "---":
                continue

            # Requirement heading → \newpage + ### with anchor
            req_match = _REQ_HEADING_RE.match(line)
            if req_match:
                hashes = req_match.group(1)
                req_id = req_match.group(2).rstrip(":")
                rest = line[len(hashes) + 1 :]
                lines.append("\\newpage")
                lines.append("")
                lines.append(f"### {rest} {{#{req_id}}}")
                continue

            # Other headings
            if line.startswith("#"):
                text = line.lstrip("#").lstrip()
                if not seen_file_title:
                    # First heading in the file → section (appears in TOC)
                    lines.append(f"## {text}")
                    seen_file_title = True
                else:
                    # All other non-requirement headings → excluded from TOC
                    lines.append(f"#### {text}")
                continue

            # Replace .mmd image references with .png
            if ".mmd)" in line:
                line = self._resolve_mermaid_images(
                    line, file_path, owning_repo_root=owning_repo_root
                )

            # Ensure blank line before first list item so Pandoc renders as a list
            stripped = line.lstrip()
            if (
                stripped.startswith("- ")
                and lines
                and lines[-1].strip()
                and not lines[-1].lstrip().startswith("- ")
            ):
                lines.append("")

            lines.append(line)

        # Trim trailing blank lines
        while lines and not lines[-1].strip():
            lines.pop()
        lines.append("")

        return lines

    @staticmethod
    def _detect_req_heading_level(source_lines: list[str]) -> int:
        """Detect the Markdown heading level used for requirements in a file.

        Returns the number of '#' characters (1 for `#`, 2 for `##`, etc.).
        Defaults to 1 if no requirement headings found.
        """
        for line in source_lines:
            m = _REQ_HEADING_RE.match(line)
            if m:
                return len(m.group(1))
        return 1

    def _repo_root_for_owner(self, owner_name: str | None) -> Path | None:
        """Look up the on-disk root for a named federated repo, if any."""
        if not owner_name:
            return None
        iter_repos = getattr(self._graph, "iter_repos", None)
        if not callable(iter_repos):
            return None
        for entry in iter_repos():
            if entry.name == owner_name:
                return entry.repo_root
        return None

    def _resolve_path(self, file_path: str, owning_repo_root: Path | None = None) -> Path | None:
        """Resolve a source path to an absolute Path.

        When ``owning_repo_root`` is supplied, the file is resolved
        against that repo root first (the federated case for cross-repo
        files). Falls back to ``self._graph.repo_root`` and then to a
        scan of every repo in ``iter_repos()`` so that cross-repo
        references render even when the caller didn't track ownership.
        """
        p = Path(file_path)
        if p.is_absolute() and p.exists():
            return p
        if owning_repo_root is not None:
            candidate = owning_repo_root / file_path
            if candidate.exists():
                return candidate
        # Try relative to root repo
        candidate = self._graph.repo_root / file_path
        if candidate.exists():
            return candidate
        # Fall back: search every federated repo (cross-repo file with
        # no ownership context — rare in normal callers but needed for
        # mermaid blocks emitted from preamble-style global text).
        iter_repos = getattr(self._graph, "iter_repos", None)
        if callable(iter_repos):
            for entry in iter_repos():
                candidate = entry.repo_root / file_path
                if candidate.exists():
                    return candidate
        return None

    # ------------------------------------------------------------------
    # Mermaid diagram resolution
    # ------------------------------------------------------------------

    def _resolve_mermaid_images(
        self,
        line: str,
        source_file: str,
        owning_repo_root: Path | None = None,
    ) -> str:
        """Replace .mmd image references with .png equivalents.

        For each ![alt](path.mmd) reference:
        1. Look for path.png alongside the .mmd file
        2. If not found, generate it using mmdc (mermaid CLI)
        3. Replace the reference with the absolute .png path

        ``owning_repo_root`` anchors resolution to the source file's
        owning repo when known (federated cross-repo rendering).
        """
        anchor = owning_repo_root if owning_repo_root is not None else self._graph.repo_root

        def _replace_mmd(match: re.Match) -> str:
            prefix = match.group(1)  # ![alt](
            mmd_path = match.group(2)  # relative/path.mmd
            suffix = match.group(3)  # )

            # Resolve .mmd path relative to the source file's directory
            source_dir = Path(source_file).parent
            mmd_resolved = anchor / source_dir / mmd_path
            if not mmd_resolved.exists():
                # Try relative to anchor repo root
                mmd_resolved = anchor / mmd_path
            if not mmd_resolved.exists():
                return match.group(0)  # Leave unchanged

            png_path = mmd_resolved.with_suffix(".png")

            # Use existing .png if available
            if not png_path.exists():
                png_path = self._generate_mermaid_png(mmd_resolved, png_path)
                if png_path is None:
                    return match.group(0)

            return f"{prefix}{png_path}{suffix}"

        return _MMD_IMAGE_RE.sub(_replace_mmd, line)

    @staticmethod
    def _generate_mermaid_png(mmd_path: Path, png_path: Path) -> Path | None:
        """Generate a PNG from a Mermaid .mmd file using mmdc.

        Returns the PNG path on success, None on failure.
        """
        mmdc = shutil.which("mmdc")
        if not mmdc:
            log.warning("mmdc not found, cannot render %s", mmd_path.name)
            return None

        try:
            subprocess.run(
                [mmdc, "-i", str(mmd_path), "-o", str(png_path), "-b", "white"],
                capture_output=True,
                timeout=30,
                check=True,
            )
            return png_path
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            log.warning("Failed to render %s: %s", mmd_path.name, exc)
            return None

    # ------------------------------------------------------------------
    # File grouping
    # ------------------------------------------------------------------

    def _group_by_file(self) -> dict[str, list[GraphNode]]:
        """Group requirement nodes by their source file path.

        Returns:
            Dict mapping file path → list of requirement nodes (document order).
        """
        groups: dict[str, list[GraphNode]] = defaultdict(list)
        # Implements: REQ-d00129-D, REQ-d00129-E
        for node in self._graph.nodes_by_kind(NodeKind.REQUIREMENT):
            _fn = node.file_node()
            _rp = _fn.get_field("relative_path") if _fn else None
            if _rp:
                groups[_rp].append(node)

        # Sort nodes within each file by source line (document order)
        for path in groups:
            groups[path].sort(key=lambda n: n.get_field("parse_line") or 0)

        return dict(groups)

    # ------------------------------------------------------------------
    # Level partitioning
    # ------------------------------------------------------------------

    def _partition_by_level(self, file_groups: dict[str, list[GraphNode]]) -> dict[str, list[str]]:
        """Partition file paths into level buckets (PRD/OPS/DEV).

        Each file is assigned to the level of its highest-level requirement
        (min level_number).

        Returns:
            Dict mapping level name → list of file paths.
        """
        buckets: dict[str, list[str]] = defaultdict(list)
        for path, nodes in file_groups.items():
            min_level = self._min_level_for_nodes(nodes)
            if min_level:
                buckets[min_level].append(path)
        return dict(buckets)

    def _min_level_for_nodes(self, nodes: list[GraphNode]) -> str | None:
        """Return the highest-priority level name among nodes.

        Level values from the graph may be lowercase (prd/ops/dev).
        Returns the canonical uppercase key (PRD/OPS/DEV).
        """
        best_order = float("inf")
        best_level = None
        for node in nodes:
            level = node.level
            if level:
                level_upper = level.upper()
                if level_upper in self._level_order:
                    order = self._level_order[level_upper]
                    if order < best_order:
                        best_order = order
                        best_level = level_upper
        return best_level

    # ------------------------------------------------------------------
    # Graph-depth ordering
    # ------------------------------------------------------------------

    def _sort_files_by_depth(
        self,
        file_paths: list[str],
        file_groups: dict[str, list[GraphNode]],
    ) -> list[str]:
        """Sort files by the minimum graph depth of their requirements.

        Graph depth = fewest ancestor hops to a root node via BFS on iter_parents().
        Files with root requirements (depth 0) sort first.

        Returns:
            Sorted list of file paths.
        """

        def file_sort_key(path: str) -> tuple[int, str]:
            nodes = file_groups.get(path, [])
            min_depth = min(
                (self._node_depth(n) for n in nodes),
                default=999,
            )
            return (min_depth, path)

        return sorted(file_paths, key=file_sort_key)

    @staticmethod
    def _node_depth(node: GraphNode) -> int:
        """Compute the graph depth of a node via BFS on parents.

        Depth 0 = root node (no domain parents).
        FILE parents are excluded from depth calculation since they
        represent structural containment, not domain hierarchy.
        """
        from elspais.graph.GraphNode import NodeKind

        depth = 0
        visited: set[str] = {node.id}
        frontier = [node]
        while frontier:
            next_frontier: list[GraphNode] = []
            for n in frontier:
                for parent in n.iter_parents():
                    if parent.id not in visited and parent.kind != NodeKind.FILE:
                        visited.add(parent.id)
                        next_frontier.append(parent)
            if next_frontier:
                depth += 1
                frontier = next_frontier
            else:
                break
        return depth

    def _is_associated_node(self, node: GraphNode) -> bool:
        """Check if a node belongs to an associated repository.

        Detects associated-repo IDs by checking for an uppercase segment
        after the namespace prefix (e.g., REQ-CAL-p00001 has "CAL" segment).
        """
        import re

        namespace = self._resolver.config.namespace
        prefix = f"{namespace}-"
        if node.id.startswith(prefix):
            after_prefix = node.id[len(prefix) :]
            if re.match(r"^[A-Z]{2,}-[a-z]", after_prefix):
                return True
        return False

    def _filter_by_depth(
        self,
        file_paths: list[str],
        file_groups: dict[str, list[GraphNode]],
    ) -> list[str]:
        """Filter files by max depth, excluding associated-repo files from filtering.

        Associated-repo files (detected via namespace pattern) are always included.
        Core files are included only if their minimum depth < max_depth.
        """
        result: list[str] = []
        for path in file_paths:
            nodes = file_groups.get(path, [])
            if any(self._is_associated_node(n) for n in nodes):
                result.append(path)
                continue
            min_depth = min(
                (self._node_depth(n) for n in nodes),
                default=999,
            )
            if min_depth < self._max_depth:
                result.append(path)
        return result

    # ------------------------------------------------------------------
    # Topic index
    # ------------------------------------------------------------------

    def _build_topic_index(
        self,
        file_groups: dict[str, list[GraphNode]],
        file_owners: dict[str, str] | None = None,
    ) -> list[str]:
        """Build an alphabetized topic index.

        Topic sources:
        1. Filename words (strip level prefix, split on '-')
        2. File-level Topics: lines (scanned from source file)
        3. Requirement-level Topics: lines (from REMAINDER children in graph)

        When ``file_owners`` is supplied, requirement entries belonging
        to an associate repo render with a ``[<repo_name>]`` prefix so
        readers can tell where each cross-repo section originates.

        Returns:
            List of Markdown lines for the index section.
        """
        # topic → set of (req_id, req_title, repo_name)
        index: dict[str, set[tuple[str, str, str]]] = defaultdict(set)
        owners = file_owners or {}

        repo_for = getattr(self._graph, "repo_for", None)

        def _repo_for_node(node: GraphNode, fallback: str) -> str:
            if not callable(repo_for):
                return fallback
            try:
                return repo_for(node.id).name
            except KeyError:
                return fallback

        for file_path, nodes in file_groups.items():
            file_owner = owners.get(file_path, "")
            # Source 1: filename words
            filename_topics = self._topics_from_filename(file_path)
            for topic in filename_topics:
                for node in nodes:
                    index[topic].add((node.id, node.get_label(), _repo_for_node(node, file_owner)))

            # Source 2: file-level Topics: lines (scan file directly)
            file_topics = self._topics_from_file(
                file_path,
                owning_repo_root=self._repo_root_for_owner(file_owner),
            )
            for topic in file_topics:
                for node in nodes:
                    index[topic].add((node.id, node.get_label(), _repo_for_node(node, file_owner)))

            # Source 3: requirement-level REMAINDER children with Topics: lines
            for node in nodes:
                req_topics = self._topics_from_requirement_remainders(node)
                for topic in req_topics:
                    index[topic].add((node.id, node.get_label(), _repo_for_node(node, file_owner)))

        if not index:
            return []

        # Render as alphabetized list
        lines: list[str] = []
        host_name = self._graph.root_repo_name
        for topic in sorted(index.keys(), key=str.lower):
            entries = sorted(index[topic], key=lambda e: e[0])
            parts: list[str] = []
            for req_id, _title, repo_name in entries:
                if repo_name and repo_name != host_name:
                    parts.append(f"[{repo_name}] [{req_id}](#{req_id})")
                else:
                    parts.append(f"[{req_id}](#{req_id})")
            refs = ", ".join(parts)
            lines.append(f"**{topic}**: {refs}")
            lines.append("")

        return lines

    def _topics_from_filename(self, file_path: str) -> list[str]:
        """Extract topics from a filename by stripping level prefix and splitting on '-'.

        Examples:
            'prd-pdf-generation.md' → ['pdf', 'generation']
            'ops-cicd.md' → ['cicd']
            '07-graph-architecture.md' → ['graph', 'architecture']
        """
        stem = Path(file_path).stem
        cleaned = self._level_prefix_re.sub("", stem)
        if not cleaned:
            return []
        words = [w for w in cleaned.split("-") if w]
        return words

    def _topics_from_file(self, file_path: str, owning_repo_root: Path | None = None) -> list[str]:
        """Extract Topics: lines from the pre-requirement section of a file."""
        resolved = self._resolve_path(file_path, owning_repo_root=owning_repo_root)
        if not resolved or not resolved.exists():
            return []
        text = resolved.read_text(encoding="utf-8")
        topics: list[str] = []
        for line in text.split("\n"):
            # Stop at first requirement heading
            if _REQ_HEADING_RE.match(line):
                break
            match = re.match(r"Topics:\s*(.+)", line, re.IGNORECASE)
            if match:
                for t in match.group(1).split(","):
                    t = t.strip()
                    if t:
                        topics.append(t)
        return topics

    @staticmethod
    def _topics_from_requirement_remainders(req_node: GraphNode) -> list[str]:
        """Extract topics from REMAINDER children of a requirement node."""
        topics: list[str] = []
        for child in req_node.iter_children():
            if child.kind == NodeKind.REMAINDER:
                text = child.get_field("text", "") or ""
                for line in text.split("\n"):
                    match = re.match(r"Topics:\s*(.+)", line, re.IGNORECASE)
                    if match:
                        for t in match.group(1).split(","):
                            t = t.strip()
                            if t:
                                topics.append(t)
        return topics
