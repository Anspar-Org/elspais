# Implements: REQ-p00006-B
# Implements: REQ-o00051-A, REQ-o00051-B, REQ-o00051-C, REQ-o00051-D
# Implements: REQ-o00051-E, REQ-o00051-F
# Implements: REQ-d00050-A, REQ-d00050-B, REQ-d00050-C, REQ-d00050-D, REQ-d00050-E
# Implements: REQ-d00051-A, REQ-d00051-B, REQ-d00051-C, REQ-d00051-D
# Implements: REQ-d00051-E, REQ-d00051-F
# Implements: REQ-d00055-A, REQ-d00055-B, REQ-d00055-C, REQ-d00055-D, REQ-d00055-E
# Implements: REQ-d00069-B, REQ-d00069-D
"""Node annotation functions for TraceGraph.

These are pure functions that annotate individual GraphNode instances.
The graph provides iterators (graph.all_nodes(), graph.nodes_by_kind()),
and the caller applies annotators to nodes as needed.

Usage:
    from elspais.graph.annotators import annotate_git_state, annotate_display_info
    from elspais.graph import NodeKind

    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        annotate_git_state(node, git_info)
        annotate_display_info(node)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from elspais.graph import NodeKind
    from elspais.graph.builder import TraceGraph
    from elspais.graph.GraphNode import GraphNode
    from elspais.utilities.git import GitChangeInfo


def annotate_git_state(node: GraphNode, git_info: GitChangeInfo | None) -> None:
    """Annotate a node with git state information.

    This is a pure function that mutates node.metrics in place.
    Only operates on REQUIREMENT nodes.

    Git metrics added to node.metrics:
    - is_uncommitted: True if file has uncommitted changes
    - is_untracked: True if file is not tracked by git (new file)
    - is_branch_changed: True if file differs from main branch
    - is_moved: True if requirement moved from a different file
    - is_modified: True if file is modified (but tracked)
    - is_new: True if in an untracked file (convenience alias)

    Args:
        node: The node to annotate.
        git_info: Git change information, or None if git unavailable.
    """
    from elspais.graph import NodeKind

    if node.kind != NodeKind.REQUIREMENT:
        return

    # Get file path relative to repo
    file_path = node.source.path if node.source else ""

    # Default all git states to False
    is_uncommitted = False
    is_untracked = False
    is_branch_changed = False
    is_moved = False
    is_modified = False

    if git_info:
        # Check if file has uncommitted changes
        is_untracked = file_path in git_info.untracked_files
        is_modified = file_path in git_info.modified_files
        is_uncommitted = is_untracked or is_modified

        # Check if file changed vs main branch
        is_branch_changed = file_path in git_info.branch_changed_files

        # Check if requirement was moved
        # Extract short ID from node ID (e.g., 'p00001' from 'REQ-p00001')
        req_id = node.id
        if "-" in req_id:
            short_id = req_id.rsplit("-", 1)[-1]
            # Handle assertion IDs like REQ-p00001-A
            if len(short_id) == 1 and short_id.isalpha():
                # This is an assertion, get the parent ID
                parts = req_id.split("-")
                if len(parts) >= 2:
                    short_id = parts[-2]
        else:
            short_id = req_id

        committed_path = git_info.committed_req_locations.get(short_id)
        if committed_path and committed_path != file_path:
            is_moved = True

    # is_new means it's in an untracked file (truly new, not moved)
    is_new = is_untracked

    # Annotate node metrics
    node.set_metric("is_uncommitted", is_uncommitted)
    node.set_metric("is_untracked", is_untracked)
    node.set_metric("is_branch_changed", is_branch_changed)
    node.set_metric("is_moved", is_moved)
    node.set_metric("is_modified", is_modified)
    node.set_metric("is_new", is_new)


def annotate_display_info(node: GraphNode) -> None:
    """Annotate a node with display-friendly information.

    This is a pure function that mutates node.metrics in place.
    Only operates on REQUIREMENT nodes.

    Display metrics added to node.metrics:
    - is_roadmap: True if in spec/roadmap/ directory
    - is_conflict: True if has duplicate ID conflict
    - conflict_with: ID of conflicting requirement (if conflict)
    - display_filename: Filename stem for display
    - file_name: Full filename
    - repo_prefix: Repo prefix for multi-repo setups (e.g., "CORE", "CAL")
    - external_spec_path: Path for associated repo specs

    Args:
        node: The node to annotate.
    """
    from elspais.graph import NodeKind

    if node.kind != NodeKind.REQUIREMENT:
        return

    # Get file path relative to repo
    file_path = node.source.path if node.source else ""

    # Roadmap detection from path
    is_roadmap = "roadmap" in file_path.lower()
    node.set_metric("is_roadmap", is_roadmap)

    # Conflict detection from content
    is_conflict = node.get_field("is_conflict", False)
    conflict_with = node.get_field("conflict_with")
    node.set_metric("is_conflict", is_conflict)
    if conflict_with:
        node.set_metric("conflict_with", conflict_with)

    # Store display-friendly file info
    if file_path:
        path = Path(file_path)
        node.set_metric("display_filename", path.stem)
        node.set_metric("file_name", path.name)
    else:
        node.set_metric("display_filename", "")
        node.set_metric("file_name", "")

    # Repo prefix for multi-repo setups
    repo_prefix = node.get_field("repo_prefix")
    node.set_metric("repo_prefix", repo_prefix or "CORE")

    # External spec path for associated repos
    external_spec_path = node.get_field("external_spec_path")
    if external_spec_path:
        node.set_metric("external_spec_path", str(external_spec_path))


def annotate_implementation_files(
    node: GraphNode,
    implementation_files: list[tuple[str, int]],
) -> None:
    """Annotate a node with implementation file references.

    Args:
        node: The node to annotate.
        implementation_files: List of (file_path, line_number) tuples.
    """
    from elspais.graph import NodeKind

    if node.kind != NodeKind.REQUIREMENT:
        return

    # Store implementation files in metrics
    existing = node.get_metric("implementation_files", [])
    existing.extend(implementation_files)
    node.set_metric("implementation_files", existing)


# =============================================================================
# Graph Aggregate Functions
# =============================================================================
# These functions compute aggregate statistics from an annotated graph.
# They follow the composable pattern: take a graph, return computed values.


def count_by_level(graph: TraceGraph) -> dict[str, dict[str, int]]:
    """Count requirements by level, with and without deprecated.

    Args:
        graph: The TraceGraph to aggregate.

    Returns:
        Dict with 'active' (excludes Deprecated) and 'all' (includes Deprecated) counts
        by level (PRD, OPS, DEV).
    """
    from elspais.graph import NodeKind

    counts: dict[str, dict[str, int]] = {
        "active": {"PRD": 0, "OPS": 0, "DEV": 0},
        "all": {"PRD": 0, "OPS": 0, "DEV": 0},
    }
    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        level = node.get_field("level", "")
        status = node.get_field("status", "Active")
        if level:
            counts["all"][level] = counts["all"].get(level, 0) + 1
            if status != "Deprecated":
                counts["active"][level] = counts["active"].get(level, 0) + 1
    return counts


def group_by_level(graph: TraceGraph) -> dict[str, list[GraphNode]]:
    """Group requirements by level.

    Args:
        graph: The TraceGraph to query.

    Returns:
        Dict mapping level (PRD, OPS, DEV, other) to list of requirement nodes.
    """
    from elspais.graph import NodeKind

    groups: dict[str, list[GraphNode]] = {"PRD": [], "OPS": [], "DEV": [], "other": []}
    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        level = (node.get_field("level") or "").upper()
        if level in groups:
            groups[level].append(node)
        else:
            groups["other"].append(node)
    return groups


def count_by_repo(graph: TraceGraph) -> dict[str, dict[str, int]]:
    """Count requirements by repo prefix (CORE, CAL, TTN, etc.).

    Args:
        graph: The TraceGraph to aggregate.

    Returns:
        Dict mapping repo prefix to {'active': count, 'all': count}.
        CORE is used for core repo requirements (no prefix).
    """
    from elspais.graph import NodeKind

    repo_counts: dict[str, dict[str, int]] = {}

    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):

        prefix = node.get_metric("repo_prefix", "CORE")
        status = node.get_field("status", "Active")

        if prefix not in repo_counts:
            repo_counts[prefix] = {"active": 0, "all": 0}

        repo_counts[prefix]["all"] += 1
        if status != "Deprecated":
            repo_counts[prefix]["active"] += 1

    return repo_counts


def count_implementation_files(graph: TraceGraph) -> int:
    """Count total implementation files across all requirements.

    Args:
        graph: The TraceGraph to aggregate.

    Returns:
        Total count of implementation file references.
    """
    from elspais.graph import NodeKind

    total = 0
    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        impl_files = node.get_metric("implementation_files", [])
        total += len(impl_files)
    return total


def collect_topics(graph: TraceGraph) -> list[str]:
    """Collect unique topics from requirement file names.

    Args:
        graph: The TraceGraph to scan.

    Returns:
        Sorted list of unique topic names extracted from file stems.
    """
    from elspais.graph import NodeKind

    all_topics: set[str] = set()
    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        if node.source and node.source.path:
            stem = Path(node.source.path).stem
            topic = stem.split("-", 1)[1] if "-" in stem else stem
            all_topics.add(topic)
    return sorted(all_topics)


def get_implementation_status(node: GraphNode) -> str:
    """Get implementation status for a requirement node.

    Args:
        node: The GraphNode to check.

    Returns:
        'Full': coverage_pct >= 100
        'Partial': coverage_pct > 0
        'Unimplemented': coverage_pct == 0
    """
    coverage_pct = node.get_metric("coverage_pct", 0)
    if coverage_pct >= 100:
        return "Full"
    elif coverage_pct > 0:
        return "Partial"
    else:
        return "Unimplemented"


def count_by_coverage(graph: TraceGraph) -> dict[str, int]:
    """Count requirements by coverage level.

    Args:
        graph: The TraceGraph to aggregate.

    Returns:
        Dict with 'total', 'full_coverage', 'partial_coverage', 'no_coverage' counts.
    """
    from elspais.graph import NodeKind

    counts: dict[str, int] = {
        "total": 0,
        "full_coverage": 0,
        "partial_coverage": 0,
        "no_coverage": 0,
    }

    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):

        counts["total"] += 1
        coverage_pct = node.get_metric("coverage_pct", 0)

        if coverage_pct >= 100:
            counts["full_coverage"] += 1
        elif coverage_pct > 0:
            counts["partial_coverage"] += 1
        else:
            counts["no_coverage"] += 1

    return counts


def count_with_code_refs(graph: TraceGraph) -> dict[str, int]:
    """Count requirements that have at least one CODE reference.

    A requirement has CODE coverage if:
    - It has a CODE child directly, OR
    - One of its ASSERTION children has a CODE child

    Args:
        graph: The TraceGraph to query.

    Returns:
        Dict with 'total_requirements', 'with_code_refs', 'coverage_percent'.
    """
    from elspais.graph import NodeKind

    total = 0
    covered_req_ids: set[str] = set()

    for node in graph.nodes_by_kind(NodeKind.CODE):
        for parent in node.iter_parents():
            if parent.kind == NodeKind.REQUIREMENT:
                covered_req_ids.add(parent.id)
            elif parent.kind == NodeKind.ASSERTION:
                # Get the parent requirement of the assertion
                for grandparent in parent.iter_parents():
                    if grandparent.kind == NodeKind.REQUIREMENT:
                        covered_req_ids.add(grandparent.id)

    for _ in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        total += 1

    pct = (len(covered_req_ids) / total * 100) if total > 0 else 0.0
    return {
        "total_requirements": total,
        "with_code_refs": len(covered_req_ids),
        "coverage_percent": round(pct, 1),
    }


def count_by_git_status(graph: TraceGraph) -> dict[str, int]:
    """Count requirements by git change status.

    Args:
        graph: The TraceGraph to aggregate.

    Returns:
        Dict with 'uncommitted' and 'branch_changed' counts.
    """
    from elspais.graph import NodeKind

    counts: dict[str, int] = {
        "uncommitted": 0,
        "branch_changed": 0,
    }

    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):

        if node.get_metric("is_uncommitted", False):
            counts["uncommitted"] += 1
        if node.get_metric("is_branch_changed", False):
            counts["branch_changed"] += 1

    return counts


def annotate_coverage(graph: TraceGraph) -> None:
    """Compute and store coverage metrics for all requirement nodes.

    This function traverses the graph once to compute RollupMetrics for
    each REQUIREMENT node. Metrics are stored in node._metrics as:
    - "rollup_metrics": The full RollupMetrics object
    - "coverage_pct": Coverage percentage (for convenience)

    Coverage is determined by outgoing edges from REQUIREMENT nodes:
    - The builder links TEST/CODE/REQ as children of the parent REQ
    - Edges have assertion_targets when they target specific assertions
    - VALIDATES to TEST with assertion_targets → DIRECT coverage
    - IMPLEMENTS to CODE with assertion_targets → DIRECT coverage
    - IMPLEMENTS to CODE → VALIDATES to TEST → INDIRECT coverage (transitive)
    - IMPLEMENTS to REQ with assertion_targets → EXPLICIT coverage
    - IMPLEMENTS to REQ without assertion_targets → INFERRED coverage

    REFINES edges do NOT contribute to coverage (EdgeKind.contributes_to_coverage()).

    Test-specific metrics:
    - direct_tested: Assertions with TEST nodes (not CODE)
    - validated: Assertions with passing TEST_RESULTs
    - has_failures: Any TEST_RESULT is failed/error

    Args:
        graph: The TraceGraph to annotate.
    """
    from elspais.graph import NodeKind
    from elspais.graph.metrics import (
        CoverageContribution,
        CoverageSource,
        RollupMetrics,
    )
    from elspais.graph.relations import EdgeKind

    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):

        metrics = RollupMetrics()

        # Collect assertion children
        assertion_labels: list[str] = []

        for child in node.iter_children():
            if child.kind == NodeKind.ASSERTION:
                label = child.get_field("label", "")
                if label:
                    assertion_labels.append(label)

        metrics.total_assertions = len(assertion_labels)

        # Track TEST-specific metrics
        tested_labels: set[str] = set()  # Assertions with TEST coverage
        validated_labels: set[str] = set()  # Assertions with passing tests
        has_failures = False
        test_nodes_for_result_lookup: list[tuple[GraphNode, list[str] | None]] = []

        # Check outgoing edges from this requirement
        # The builder links TEST/CODE/REQ as children of parent REQ with assertion_targets
        for edge in node.iter_outgoing_edges():
            if not edge.kind.contributes_to_coverage():
                # REFINES doesn't count
                continue

            target_node = edge.target
            target_kind = target_node.kind

            if target_kind == NodeKind.TEST:
                # TEST validates assertion(s) → DIRECT coverage
                if edge.assertion_targets:
                    for label in edge.assertion_targets:
                        if label in assertion_labels:
                            metrics.add_contribution(
                                CoverageContribution(
                                    source_id=target_node.id,
                                    source_type=CoverageSource.DIRECT,
                                    assertion_label=label,
                                )
                            )
                            tested_labels.add(label)
                else:
                    # Whole-req test (no assertion targets) → INDIRECT for all assertions
                    for label in assertion_labels:
                        metrics.add_contribution(
                            CoverageContribution(
                                source_id=target_node.id,
                                source_type=CoverageSource.INDIRECT,
                                assertion_label=label,
                            )
                        )

                # Track this TEST node for result lookup later
                test_nodes_for_result_lookup.append((target_node, edge.assertion_targets))

            elif target_kind == NodeKind.CODE:
                # CODE implements assertion(s) → DIRECT coverage
                if edge.assertion_targets:
                    for label in edge.assertion_targets:
                        if label in assertion_labels:
                            metrics.add_contribution(
                                CoverageContribution(
                                    source_id=target_node.id,
                                    source_type=CoverageSource.DIRECT,
                                    assertion_label=label,
                                )
                            )

                # Transitive: CODE → TEST → TEST_RESULT (indirect test coverage)
                # Check if this CODE node has TEST children via VALIDATES edges
                for code_edge in target_node.iter_outgoing_edges():
                    if (
                        code_edge.kind == EdgeKind.VALIDATES
                        and code_edge.target.kind == NodeKind.TEST
                    ):
                        transitive_test = code_edge.target
                        # Credit assertions the CODE implements with INDIRECT coverage
                        code_assertion_targets = edge.assertion_targets
                        if code_assertion_targets:
                            for label in code_assertion_targets:
                                if label in assertion_labels:
                                    metrics.add_contribution(
                                        CoverageContribution(
                                            source_id=transitive_test.id,
                                            source_type=CoverageSource.INDIRECT,
                                            assertion_label=label,
                                        )
                                    )
                        else:
                            # CODE without assertion targets → all assertions
                            for label in assertion_labels:
                                metrics.add_contribution(
                                    CoverageContribution(
                                        source_id=transitive_test.id,
                                        source_type=CoverageSource.INDIRECT,
                                        assertion_label=label,
                                    )
                                )

                        # Track for TEST_RESULT lookup (use CODE's assertion_targets)
                        test_nodes_for_result_lookup.append((transitive_test, None))

            elif target_kind == NodeKind.REQUIREMENT:
                # Child REQ implements this REQ
                if edge.assertion_targets:
                    # Explicit: REQ implements specific assertions
                    for label in edge.assertion_targets:
                        if label in assertion_labels:
                            metrics.add_contribution(
                                CoverageContribution(
                                    source_id=target_node.id,
                                    source_type=CoverageSource.EXPLICIT,
                                    assertion_label=label,
                                )
                            )
                else:
                    # Inferred: REQ implements parent REQ (all assertions)
                    for label in assertion_labels:
                        metrics.add_contribution(
                            CoverageContribution(
                                source_id=target_node.id,
                                source_type=CoverageSource.INFERRED,
                                assertion_label=label,
                            )
                        )

        # Process TEST children to find TEST_RESULT nodes
        validated_indirect_labels: set[str] = set()
        for test_node, assertion_targets in test_nodes_for_result_lookup:
            for result in test_node.iter_children():
                if result.kind == NodeKind.TEST_RESULT:
                    status = (result.get_field("status", "") or "").lower()
                    if status in ("passed", "pass", "success"):
                        if assertion_targets:
                            # Assertion-targeted test: mark specific assertions
                            for label in assertion_targets:
                                if label in assertion_labels:
                                    validated_labels.add(label)
                        else:
                            # Whole-req test: mark all assertions as indirect-validated
                            for label in assertion_labels:
                                validated_indirect_labels.add(label)
                    elif status in ("failed", "fail", "failure", "error"):
                        has_failures = True

        # Set test-specific metrics before finalize
        metrics.direct_tested = len(tested_labels)
        metrics.validated = len(validated_labels)
        metrics.validated_with_indirect = len(validated_labels | validated_indirect_labels)
        metrics.has_failures = has_failures

        # Finalize metrics (computes aggregate coverage counts)
        metrics.finalize()

        # Store in node metrics
        node.set_metric("rollup_metrics", metrics)
        node.set_metric("coverage_pct", metrics.coverage_pct)


# =============================================================================
# Keyword Extraction (Phase 4)
# =============================================================================
# These functions extract and search keywords from requirement text.
# Keywords are stored in node._content["keywords"] as a list of strings.


# Default stopwords - common words filtered from keywords.
# NOTE: Normative keywords (shall, must, should, may, required) are NOT included
# as they have semantic meaning for requirements (RFC 2119).
DEFAULT_STOPWORDS = frozenset(
    [
        # Articles and determiners
        "a",
        "an",
        "the",
        "this",
        "that",
        "these",
        "those",
        # Pronouns
        "i",
        "you",
        "he",
        "she",
        "it",
        "we",
        "they",
        "me",
        "him",
        "her",
        "us",
        "them",
        # Prepositions
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "with",
        "by",
        "from",
        "up",
        "about",
        "into",
        "through",
        "during",
        "before",
        "after",
        "above",
        "below",
        "between",
        # Conjunctions
        "and",
        "or",
        "but",
        "nor",
        "so",
        "yet",
        "both",
        "either",
        "neither",
        # Auxiliary verbs (excluding normative: shall, must, should, may)
        "is",
        "am",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "having",
        "do",
        "does",
        "did",
        "doing",
        "will",
        "would",
        "could",
        "might",
        "can",
        # Common verbs
        "get",
        "got",
        "make",
        "made",
        "let",
        # Other common words
        "not",
        "if",
        "when",
        "where",
        "how",
        "what",
        "which",
        "who",
        "whom",
        "whose",
        "all",
        "each",
        "every",
        "any",
        "some",
        "no",
        "none",
        "other",
        "such",
        "only",
        "own",
        "same",
        "than",
        "too",
        "very",
    ]
)

# Alias for backward compatibility
STOPWORDS = DEFAULT_STOPWORDS


@dataclass
class KeywordsConfig:
    """Configuration for keyword extraction."""

    stopwords: frozenset[str]
    min_length: int = 3

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> KeywordsConfig:
        """Create config from dictionary.

        Args:
            data: Dict with optional 'stopwords' list and 'min_length' int.

        Returns:
            KeywordsConfig instance.
        """
        stopwords_list = data.get("stopwords")
        if stopwords_list is not None:
            stopwords = frozenset(stopwords_list)
        else:
            stopwords = DEFAULT_STOPWORDS

        return cls(
            stopwords=stopwords,
            min_length=data.get("min_length", 3),
        )


def extract_keywords(
    text: str,
    config: KeywordsConfig | None = None,
) -> list[str]:
    """Extract keywords from text.

    Extracts meaningful words by:
    - Lowercasing all text
    - Removing punctuation (except hyphens within words)
    - Filtering stopwords
    - Filtering words shorter than min_length
    - Deduplicating results

    Args:
        text: Input text to extract keywords from.
        config: Optional KeywordsConfig for custom stopwords/min_length.

    Returns:
        List of unique keywords in lowercase.
    """
    import re

    if not text:
        return []

    # Use provided config or defaults
    cfg = config or KeywordsConfig(stopwords=DEFAULT_STOPWORDS, min_length=3)

    # Lowercase and split into words
    text = text.lower()

    # Replace punctuation (except hyphens between letters) with spaces
    # Keep alphanumeric and hyphens
    text = re.sub(r"[^\w\s-]", " ", text)

    # Split on whitespace
    words = text.split()

    # Filter and deduplicate
    seen: set[str] = set()
    keywords: list[str] = []

    for word in words:
        # Strip leading/trailing hyphens
        word = word.strip("-")

        # Skip short words
        if len(word) < cfg.min_length:
            continue

        # Skip stopwords
        if word in cfg.stopwords:
            continue

        # Deduplicate
        if word not in seen:
            seen.add(word)
            keywords.append(word)

    return keywords


def annotate_keywords(
    graph: TraceGraph,
    config: KeywordsConfig | None = None,
) -> None:
    """Extract and store keywords for all nodes with text content.

    Keywords are extracted based on node kind:
    - REQUIREMENT: title + child assertion text
    - ASSERTION: SHALL statement (label)
    - USER_JOURNEY: title + actor + goal + description
    - REMAINDER: label + raw_text
    - Others (CODE, TEST, TEST_RESULT): label only

    Keywords are stored in node._content["keywords"] as a list.

    Args:
        graph: The TraceGraph to annotate.
        config: Optional KeywordsConfig for custom stopwords/min_length.
    """
    from elspais.graph import NodeKind

    for node in graph.all_nodes():
        text_parts: list[str] = []

        # Get label (all nodes have this)
        label = node.get_label()
        if label:
            text_parts.append(label)

        # Add kind-specific text
        if node.kind == NodeKind.REQUIREMENT:
            # Include child assertion text
            for child in node.iter_children():
                if child.kind == NodeKind.ASSERTION:
                    child_text = child.get_label()
                    if child_text:
                        text_parts.append(child_text)

        elif node.kind == NodeKind.USER_JOURNEY:
            # Include actor, goal, description
            for field in ["actor", "goal", "description"]:
                value = node.get_field(field)
                if value:
                    text_parts.append(value)

        elif node.kind == NodeKind.REMAINDER:
            # Include raw text
            raw = node.get_field("raw_text")
            if raw:
                text_parts.append(raw)

        # Extract and store keywords
        combined_text = " ".join(text_parts)
        keywords = extract_keywords(combined_text, config)
        node.set_field("keywords", keywords)


def find_by_keywords(
    graph: TraceGraph,
    keywords: list[str],
    match_all: bool = True,
    kind: NodeKind | None = None,
) -> list[GraphNode]:
    """Find nodes containing specified keywords.

    Args:
        graph: The TraceGraph to search.
        keywords: List of keywords to search for.
        match_all: If True, node must contain ALL keywords (AND).
                   If False, node must contain ANY keyword (OR).
        kind: NodeKind to filter by, or None to search all nodes.

    Returns:
        List of matching GraphNode objects.
    """
    # Normalize search keywords to lowercase
    search_keywords = {k.lower() for k in keywords}

    results: list[GraphNode] = []

    # Choose iterator based on kind parameter
    if kind is not None:
        nodes = graph.nodes_by_kind(kind)
    else:
        nodes = graph.all_nodes()

    for node in nodes:
        node_keywords = set(node.get_field("keywords", []))

        if match_all:
            # All keywords must be present
            if search_keywords.issubset(node_keywords):
                results.append(node)
        else:
            # Any keyword must be present
            if search_keywords & node_keywords:
                results.append(node)

    return results


def collect_all_keywords(
    graph: TraceGraph,
    kind: NodeKind | None = None,
) -> list[str]:
    """Collect all unique keywords from annotated nodes.

    Args:
        graph: The TraceGraph to scan.
        kind: NodeKind to filter by, or None to collect from all nodes.

    Returns:
        Sorted list of all unique keywords across matching nodes.
    """
    all_keywords: set[str] = set()

    # Choose iterator based on kind parameter
    if kind is not None:
        nodes = graph.nodes_by_kind(kind)
    else:
        nodes = graph.all_nodes()

    for node in nodes:
        node_keywords = node.get_field("keywords", [])
        all_keywords.update(node_keywords)

    return sorted(all_keywords)


__all__ = [
    "annotate_git_state",
    "annotate_display_info",
    "annotate_implementation_files",
    "count_by_level",
    "group_by_level",
    "count_by_repo",
    "count_by_coverage",
    "count_with_code_refs",
    "count_by_git_status",
    "count_implementation_files",
    "collect_topics",
    "get_implementation_status",
    "annotate_coverage",
    # Keyword extraction
    "DEFAULT_STOPWORDS",
    "STOPWORDS",
    "KeywordsConfig",
    "extract_keywords",
    "annotate_keywords",
    "find_by_keywords",
    "collect_all_keywords",
]
