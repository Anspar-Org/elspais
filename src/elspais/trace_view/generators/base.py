# Implements: REQ-tv-p00001 (TraceViewGenerator)
"""
elspais.trace_view.generators.base - Base generator for trace-view.

Provides the main TraceViewGenerator class that orchestrates
requirement parsing, graph building, and output generation.

All outputs consume the unified TraceGraph - no separate data structures.
"""

from pathlib import Path
from typing import Dict, List, Optional

from elspais.config.defaults import DEFAULT_CONFIG
from elspais.config.loader import find_config_file, get_spec_directories, load_config
from elspais.core.git import GitChangeInfo, get_git_changes
from elspais.core.graph import NodeKind, TraceGraph, TraceNode
from elspais.core.graph_builder import TraceGraphBuilder
from elspais.core.loader import load_requirements_from_directories
from elspais.trace_view.generators.csv import generate_csv, generate_planning_csv
from elspais.trace_view.generators.markdown import generate_markdown_from_graph


class TraceViewGenerator:
    """Generates traceability matrices using the unified TraceGraph.

    This is the main entry point for generating traceability reports.
    All outputs consume the TraceGraph directly - no separate data structures.

    Args:
        spec_dir: Path to the spec directory containing requirement files
        impl_dirs: List of directories to scan for implementation references
        sponsor: Sponsor name for sponsor-specific reports
        mode: Report mode ('core', 'sponsor', 'combined')
        repo_root: Repository root path for relative path calculation
        associated_repos: List of associated repo dicts for multi-repo scanning
        config: Optional pre-loaded configuration dict
    """

    # Version number - increment with each change
    VERSION = 18

    def __init__(
        self,
        spec_dir: Optional[Path] = None,
        impl_dirs: Optional[List[Path]] = None,
        sponsor: Optional[str] = None,
        mode: str = "core",
        repo_root: Optional[Path] = None,
        associated_repos: Optional[list] = None,
        config: Optional[dict] = None,
    ):
        self.spec_dir = spec_dir
        self.impl_dirs = impl_dirs or []
        self.sponsor = sponsor
        self.mode = mode
        self.repo_root = repo_root or (spec_dir.parent if spec_dir else Path.cwd())
        self.associated_repos = associated_repos or []
        self._base_path = ""
        self._config = config
        self._git_info: Optional[GitChangeInfo] = None
        self._graph: Optional[TraceGraph] = None
        self._builder: Optional[TraceGraphBuilder] = None

    def generate(
        self,
        format: str = "markdown",
        output_file: Optional[Path] = None,
        embed_content: bool = False,
        edit_mode: bool = False,
        review_mode: bool = False,
        quiet: bool = False,
    ) -> str:
        """Generate traceability matrix in specified format.

        Args:
            format: Output format ('markdown', 'html', 'csv')
            output_file: Path to write output (default: traceability_matrix.{ext})
            embed_content: If True, embed full requirement content in HTML
            edit_mode: If True, include edit mode UI in HTML output
            review_mode: If True, include review mode UI in HTML output
            quiet: If True, suppress progress messages

        Returns:
            The generated content as a string
        """
        # Initialize git state
        self._init_git_state(quiet)

        # Build the graph (ONE data structure for everything)
        if not quiet:
            print("Building traceability graph...")
        self._build_graph(quiet)

        if not self._graph:
            if not quiet:
                print("Warning: No requirements found")
            return ""

        req_count = sum(1 for n in self._graph.all_nodes() if n.kind == NodeKind.REQUIREMENT)
        if not quiet:
            print(f"Found {req_count} requirements")

        # Scan implementation files and add to graph
        if self.impl_dirs:
            if not quiet:
                print("Scanning implementation files...")
            self._scan_implementations(quiet)

        if not quiet:
            print(f"Generating {format.upper()} traceability matrix...")

        # Determine output path and extension
        if format == "html":
            ext = ".html"
        elif format == "csv":
            ext = ".csv"
        else:
            ext = ".md"

        if output_file is None:
            output_file = Path(f"traceability_matrix{ext}")

        # Calculate relative path for links
        self._calculate_base_path(output_file)

        # Generate content
        if format == "html":
            from elspais.trace_view.html import HTMLGenerator

            html_gen = HTMLGenerator(
                graph=self._graph,
                base_path=self._base_path,
                mode=self.mode,
                sponsor=self.sponsor,
                version=self.VERSION,
                repo_root=self.repo_root,
            )
            content = html_gen.generate(
                embed_content=embed_content, edit_mode=edit_mode, review_mode=review_mode
            )
        elif format == "csv":
            content = generate_csv(self._graph)
        else:
            content = generate_markdown_from_graph(self._graph, self._base_path)

        # Write output file
        output_file.write_text(content)
        if not quiet:
            print(f"Traceability matrix written to: {output_file}")

        return content

    def _init_git_state(self, quiet: bool = False):
        """Initialize git state for requirement status detection."""
        try:
            self._git_info = get_git_changes(self.repo_root)

            # Report uncommitted changes
            if not quiet and self._git_info.uncommitted_files:
                spec_uncommitted = [
                    f for f in self._git_info.uncommitted_files if f.startswith("spec/")
                ]
                if spec_uncommitted:
                    print(f"Uncommitted spec files: {len(spec_uncommitted)}")

            # Report branch changes vs main
            if not quiet and self._git_info.branch_changed_files:
                spec_branch = [f for f in self._git_info.branch_changed_files if f.startswith("spec/")]
                if spec_branch:
                    print(f"Spec files changed vs main: {len(spec_branch)}")

        except Exception as e:
            # Git state is optional - continue without it
            if not quiet:
                print(f"Warning: Could not get git state: {e}")
            self._git_info = None

    def _build_graph(self, quiet: bool = False):
        """Build the unified TraceGraph from requirements.

        The graph is THE data structure - all outputs consume it.
        """
        # Load config if not provided
        if self._config is None:
            config_path = find_config_file(self.repo_root)
            if config_path and config_path.exists():
                self._config = load_config(config_path)
            else:
                self._config = DEFAULT_CONFIG

        # Get spec directories
        spec_dirs = get_spec_directories(self.spec_dir, self._config)
        if not spec_dirs:
            return

        # Parse requirements using elspais parser
        requirements = load_requirements_from_directories(spec_dirs, self._config)

        if not requirements:
            return

        # Report conflicts and roadmap
        roadmap_count = 0
        conflict_count = 0
        for req_id, req in requirements.items():
            if getattr(req, "is_roadmap", False) or "roadmap" in str(req.file_path).lower():
                roadmap_count += 1
            if getattr(req, "is_conflict", False):
                conflict_count += 1
                if not quiet:
                    conflict_with = getattr(req, "conflict_with", "unknown")
                    print(f"   Warning: Conflict: {req_id} conflicts with {conflict_with}")

        if not quiet:
            if roadmap_count > 0:
                print(f"   Found {roadmap_count} roadmap requirements")
            if conflict_count > 0:
                print(f"   Found {conflict_count} conflicts")

        # Build graph
        self._builder = TraceGraphBuilder(repo_root=self.repo_root)
        self._builder.add_requirements(requirements)
        self._graph, validation = self._builder.build_and_validate()

        # Handle cycles - annotate them rather than mutating requirements
        cycle_members = set()
        for error in validation.errors:
            if error.startswith("Cycle detected:"):
                path_str = error.replace("Cycle detected:", "").strip()
                parts = [p.strip() for p in path_str.split("->")]
                cycle_members.update(parts)

        cycle_count = 0
        for req_id in cycle_members:
            node = self._graph.find_by_id(req_id)
            if node:
                node.metrics["is_cycle"] = True
                node.metrics["cycle_path"] = " -> ".join(cycle_members)
                cycle_count += 1

        if not quiet and cycle_count > 0:
            print(f"   Warning: {cycle_count} requirements in dependency cycles")

        # Annotate nodes using composable annotator functions
        self._annotate_graph_nodes()

        # Compute coverage metrics
        self._builder.compute_metrics(self._graph)

    def _annotate_graph_nodes(self):
        """Apply annotator functions to graph nodes.

        Uses the iterator pattern: graph provides nodes, we apply annotators.
        """
        from elspais.core.annotators import annotate_display_info, annotate_git_state
        from elspais.core.graph import NodeKind

        for node in self._graph.all_nodes():
            if node.kind == NodeKind.REQUIREMENT:
                annotate_git_state(node, self._git_info)
                annotate_display_info(node)

    def _scan_implementations(self, quiet: bool = False):
        """Scan implementation files and annotate findings to graph nodes."""
        from elspais.trace_view.scanning import scan_implementations_to_graph

        scan_implementations_to_graph(
            self._graph,
            self.impl_dirs,
            self.repo_root,
            self.mode,
            self.sponsor,
            quiet=quiet,
        )

    def _calculate_base_path(self, output_file: Path):
        """Calculate relative path from output file location to repo root."""
        try:
            output_dir = output_file.resolve().parent
            repo_root = self.repo_root.resolve()

            try:
                rel_path = output_dir.relative_to(repo_root)
                depth = len(rel_path.parts)
                if depth == 0:
                    self._base_path = ""
                else:
                    self._base_path = "../" * depth
            except ValueError:
                self._base_path = f"file://{repo_root}/"
        except Exception:
            self._base_path = "../"

    def generate_planning_csv(self) -> str:
        """Generate planning CSV with actionable requirements."""
        if not self._graph:
            return ""
        return generate_planning_csv(self._graph)

    def generate_coverage_report(self) -> str:
        """Generate coverage report showing implementation status."""
        if not self._graph:
            return ""
        return _generate_coverage_report_from_graph(self._graph)


def _generate_coverage_report_from_graph(graph: TraceGraph) -> str:
    """Generate text-based coverage report from graph metrics.

    Args:
        graph: The TraceGraph with computed metrics

    Returns:
        Formatted text report
    """
    lines = []
    lines.append("=== Coverage Report ===")

    # Count requirements
    req_nodes = [n for n in graph.all_nodes() if n.kind == NodeKind.REQUIREMENT]
    lines.append(f"Total Requirements: {len(req_nodes)}")
    lines.append("")

    # Count by level
    by_level: Dict[str, int] = {"PRD": 0, "OPS": 0, "DEV": 0}
    implemented_by_level: Dict[str, int] = {"PRD": 0, "OPS": 0, "DEV": 0}

    for node in req_nodes:
        req = node.requirement
        if not req:
            continue
        level = req.level
        by_level[level] = by_level.get(level, 0) + 1

        coverage_pct = node.metrics.get("coverage_pct", 0)
        if coverage_pct > 0:
            implemented_by_level[level] = implemented_by_level.get(level, 0) + 1

    lines.append("By Level:")
    for level in ["PRD", "OPS", "DEV"]:
        total = by_level[level]
        implemented = implemented_by_level[level]
        percentage = (implemented / total * 100) if total > 0 else 0
        lines.append(f"  {level}: {total} ({percentage:.0f}% implemented)")

    lines.append("")

    # Count by implementation status
    status_counts = {"Full": 0, "Partial": 0, "Unimplemented": 0}
    for node in req_nodes:
        coverage_pct = node.metrics.get("coverage_pct", 0)
        if coverage_pct >= 100:
            status_counts["Full"] += 1
        elif coverage_pct > 0:
            status_counts["Partial"] += 1
        else:
            status_counts["Unimplemented"] += 1

    lines.append("By Status:")
    lines.append(f"  Full: {status_counts['Full']}")
    lines.append(f"  Partial: {status_counts['Partial']}")
    lines.append(f"  Unimplemented: {status_counts['Unimplemented']}")

    return "\n".join(lines)
