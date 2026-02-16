# Implements: REQ-p00080-B, REQ-p00080-C, REQ-p00080-D, REQ-p00080-E
"""Markdown assembler for PDF compilation.

Uses the graph for file ordering metadata (level, depth), then reads the
source spec files directly to preserve all content faithfully.
"""
from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

from elspais.graph.builder import TraceGraph
from elspais.graph.GraphNode import GraphNode, NodeKind

# Level display names and sort order
_LEVEL_ORDER = {"PRD": 0, "OPS": 1, "DEV": 2}
_LEVEL_HEADINGS = {
    "PRD": "Product Requirements",
    "OPS": "Operational Requirements",
    "DEV": "Development Requirements",
}

# Prefixes stripped for topic extraction
_LEVEL_PREFIXES = re.compile(r"^(?:prd|ops|dev|\d+)-?", re.IGNORECASE)

# Matches requirement heading lines at any heading level: # REQ-xxx or ## REQ-xxx
_REQ_HEADING_RE = re.compile(r"^(#{1,3})\s+(REQ-\S+)")

# Matches footer lines: *End* *Title* | **Hash**: ...
_FOOTER_RE = re.compile(r"^\*End\*")


class MarkdownAssembler:
    """Assembles structured Markdown from spec files.

    Uses the graph only for metadata: which files contain requirements,
    what level they belong to, and how to order them by graph depth.
    Content comes directly from the source spec files.
    """

    def __init__(self, graph: TraceGraph, title: str = "Requirements Specification") -> None:
        self._graph = graph
        self._title = title

    def assemble(self) -> str:
        """Assemble the complete Markdown document.

        Returns:
            Structured Markdown string ready for Pandoc.
        """
        parts: list[str] = []

        # YAML metadata header for Pandoc
        parts.append("---")
        parts.append(f'title: "{self._title}"')
        parts.append("toc: true")
        parts.append("toc-depth: 3")
        parts.append("---")
        parts.append("")

        # Group requirements by file, then partition by level
        file_groups = self._group_by_file()
        level_buckets = self._partition_by_level(file_groups)

        # Emit each level group
        for level in ("PRD", "OPS", "DEV"):
            files = level_buckets.get(level, [])
            if not files:
                continue
            heading = _LEVEL_HEADINGS.get(level, level)
            parts.append(f"# {heading}")
            parts.append("")

            # Sort files within level by graph depth, then alphabetically
            sorted_files = self._sort_files_by_depth(files, file_groups)

            for file_path in sorted_files:
                parts.extend(self._render_file(file_path))

        # Topic index
        index_section = self._build_topic_index(file_groups)
        if index_section:
            parts.append("# Topic Index")
            parts.append("")
            parts.extend(index_section)

        return "\n".join(parts)

    # ------------------------------------------------------------------
    # File rendering — reads source files directly
    # ------------------------------------------------------------------

    def _render_file(self, file_path: str) -> list[str]:
        """Render a spec file's content with adjusted heading levels.

        Reads the file directly. Detects the heading level used for requirements
        in this file (e.g., `#` or `##`), then adjusts all headings so that:
        - File title → `##`
        - Requirement headings → `###` with anchor and page break
        - Sub-sections within requirements → `####`
        - `---` separators and `*End*` footer lines → stripped
        """
        resolved = self._resolve_path(file_path)
        if not resolved or not resolved.exists():
            return []

        source = resolved.read_text(encoding="utf-8")
        source_lines = source.split("\n")

        # Detect the heading level used for requirements in this file
        req_level = self._detect_req_heading_level(source_lines)
        in_requirement = False

        lines: list[str] = []
        for line in source_lines:
            # Strip horizontal rules (requirement separators)
            if line.strip() == "---":
                continue

            # Strip footer lines
            if _FOOTER_RE.match(line.strip()):
                in_requirement = False
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
                in_requirement = True
                continue

            # Other headings
            if line.startswith("#"):
                level = len(line) - len(line.lstrip("#"))
                text = line.lstrip("#").lstrip()
                if not in_requirement or level < req_level:
                    # Pre-requirement or file-level heading
                    lines.append(f"## {text}")
                else:
                    # Sub-section within a requirement (any level at or below req)
                    lines.append(f"#### {text}")
                continue

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

    def _resolve_path(self, file_path: str) -> Path | None:
        """Resolve a source path to an absolute Path."""
        p = Path(file_path)
        if p.is_absolute() and p.exists():
            return p
        # Try relative to repo root
        candidate = self._graph.repo_root / file_path
        if candidate.exists():
            return candidate
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
        for node in self._graph.nodes_by_kind(NodeKind.REQUIREMENT):
            if node.source and node.source.path:
                groups[node.source.path].append(node)

        # Sort nodes within each file by source line (document order)
        for path in groups:
            groups[path].sort(key=lambda n: n.source.line if n.source else 0)

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

    @staticmethod
    def _min_level_for_nodes(nodes: list[GraphNode]) -> str | None:
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
                if level_upper in _LEVEL_ORDER:
                    order = _LEVEL_ORDER[level_upper]
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

        Depth 0 = root node (no parents).
        """
        depth = 0
        visited: set[str] = {node.id}
        frontier = [node]
        while frontier:
            next_frontier: list[GraphNode] = []
            for n in frontier:
                for parent in n.iter_parents():
                    if parent.id not in visited:
                        visited.add(parent.id)
                        next_frontier.append(parent)
            if next_frontier:
                depth += 1
                frontier = next_frontier
            else:
                break
        return depth

    # ------------------------------------------------------------------
    # Topic index
    # ------------------------------------------------------------------

    def _build_topic_index(self, file_groups: dict[str, list[GraphNode]]) -> list[str]:
        """Build an alphabetized topic index.

        Topic sources:
        1. Filename words (strip level prefix, split on '-')
        2. File-level Topics: lines (scanned from source file)
        3. Requirement-level Topics: lines (from REMAINDER children in graph)

        Returns:
            List of Markdown lines for the index section.
        """
        # topic → set of (req_id, req_title)
        index: dict[str, set[tuple[str, str]]] = defaultdict(set)

        for file_path, nodes in file_groups.items():
            # Source 1: filename words
            filename_topics = self._topics_from_filename(file_path)
            for topic in filename_topics:
                for node in nodes:
                    index[topic].add((node.id, node.get_label()))

            # Source 2: file-level Topics: lines (scan file directly)
            file_topics = self._topics_from_file(file_path)
            for topic in file_topics:
                for node in nodes:
                    index[topic].add((node.id, node.get_label()))

            # Source 3: requirement-level REMAINDER children with Topics: lines
            for node in nodes:
                req_topics = self._topics_from_requirement_remainders(node)
                for topic in req_topics:
                    index[topic].add((node.id, node.get_label()))

        if not index:
            return []

        # Render as alphabetized list
        lines: list[str] = []
        for topic in sorted(index.keys(), key=str.lower):
            entries = sorted(index[topic], key=lambda e: e[0])
            refs = ", ".join(f"[{req_id}](#{req_id})" for req_id, _title in entries)
            lines.append(f"**{topic}**: {refs}")
            lines.append("")

        return lines

    @staticmethod
    def _topics_from_filename(file_path: str) -> list[str]:
        """Extract topics from a filename by stripping level prefix and splitting on '-'.

        Examples:
            'prd-pdf-generation.md' → ['pdf', 'generation']
            'ops-cicd.md' → ['cicd']
            '07-graph-architecture.md' → ['graph', 'architecture']
        """
        stem = Path(file_path).stem
        # Strip level prefix (prd-, ops-, dev-, numeric prefixes like 07-)
        cleaned = _LEVEL_PREFIXES.sub("", stem)
        if not cleaned:
            return []
        words = [w for w in cleaned.split("-") if w]
        return words

    def _topics_from_file(self, file_path: str) -> list[str]:
        """Extract Topics: lines from the pre-requirement section of a file."""
        resolved = self._resolve_path(file_path)
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
