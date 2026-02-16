# Implements: REQ-p00080-B, REQ-p00080-C, REQ-p00080-D, REQ-p00080-E
"""Markdown assembler for PDF compilation.

Reads from the traceability graph and produces a structured Markdown document
suitable for Pandoc conversion to PDF.
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


class MarkdownAssembler:
    """Assembles structured Markdown from the traceability graph.

    Groups requirements by level (PRD/OPS/DEV), orders files by graph depth,
    and generates a topic index.
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
                nodes = file_groups[file_path]
                file_stem = Path(file_path).stem
                parts.append(f"## {file_stem}")
                parts.append("")

                for node in nodes:
                    parts.extend(self._render_requirement(node))

        # Topic index
        index_section = self._build_topic_index(file_groups)
        if index_section:
            parts.append("# Topic Index")
            parts.append("")
            parts.extend(index_section)

        return "\n".join(parts)

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
    # Requirement rendering
    # ------------------------------------------------------------------

    def _render_requirement(self, node: GraphNode) -> list[str]:
        """Render a single requirement as Markdown lines.

        Includes page break, heading, metadata line, body sections, and assertions.
        """
        lines: list[str] = []

        # Page break before each requirement
        lines.append("\\newpage")
        lines.append("")

        # Requirement heading with anchor
        req_id = node.id
        title = node.get_label()
        lines.append(f"### {req_id}: {title} {{#{req_id}}}")
        lines.append("")

        # Metadata line
        level = (node.level or "?").upper()
        status = node.status or "?"
        lines.append(f"**Level**: {level} | **Status**: {status}")
        lines.append("")

        # Render children in document order (REMAINDER sections + ASSERTION nodes)
        for child in node.iter_children():
            if child.kind == NodeKind.REMAINDER:
                heading = child.get_field("heading", "")
                text = child.get_field("text", "")
                if heading:
                    lines.append(f"#### {heading}")
                    lines.append("")
                if text:
                    lines.append(text.rstrip())
                    lines.append("")
            elif child.kind == NodeKind.ASSERTION:
                label = child.get_field("label", "")
                text = child.get_label()
                lines.append(f"{label}. {text}")
                lines.append("")

        return lines

    # ------------------------------------------------------------------
    # Topic index
    # ------------------------------------------------------------------

    def _build_topic_index(self, file_groups: dict[str, list[GraphNode]]) -> list[str]:
        """Build an alphabetized topic index.

        Topic sources:
        1. Filename words (strip level prefix, split on '-')
        2. File-level Topics: lines from REMAINDER nodes
        3. Requirement-level Topics: lines from REMAINDER children

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

            # Source 2: file-level REMAINDER nodes with Topics: lines
            file_topics = self._topics_from_file_remainders(file_path)
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

    def _topics_from_file_remainders(self, file_path: str) -> list[str]:
        """Extract topics from file-level REMAINDER nodes containing Topics: lines."""
        topics: list[str] = []
        for node in self._graph.nodes_by_kind(NodeKind.REMAINDER):
            if not node.source or node.source.path != file_path:
                continue
            # Only consider file-level remainders (no parent that is a REQUIREMENT)
            is_file_level = True
            for parent in node.iter_parents():
                if parent.kind == NodeKind.REQUIREMENT:
                    is_file_level = False
                    break
            if not is_file_level:
                continue
            topics.extend(self._extract_topics_line(node))
        return topics

    @staticmethod
    def _topics_from_requirement_remainders(req_node: GraphNode) -> list[str]:
        """Extract topics from REMAINDER children of a requirement node."""
        topics: list[str] = []
        for child in req_node.iter_children():
            if child.kind == NodeKind.REMAINDER:
                topics.extend(MarkdownAssembler._extract_topics_line(child))
        return topics

    @staticmethod
    def _extract_topics_line(node: GraphNode) -> list[str]:
        """Extract topics from a REMAINDER node's text matching 'Topics: ...' pattern."""
        text = node.get_field("text", "") or ""
        topics: list[str] = []
        for line in text.split("\n"):
            match = re.match(r"Topics:\s*(.+)", line, re.IGNORECASE)
            if match:
                raw = match.group(1)
                for t in raw.split(","):
                    t = t.strip()
                    if t:
                        topics.append(t)
        return topics
