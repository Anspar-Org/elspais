# Implements: REQ-tv-p00001 (TraceViewGenerator)
"""
elspais.trace_view.generators.base - Base generator for trace-view.

Provides the main TraceViewGenerator class that orchestrates
requirement parsing, implementation scanning, and output generation.
"""

from pathlib import Path
from typing import Dict, List, Optional

from elspais.config.defaults import DEFAULT_CONFIG
from elspais.config.loader import find_config_file, get_spec_directories, load_config
from elspais.core.git import get_git_changes
from elspais.core.hierarchy import detect_cycles
from elspais.core.parser import RequirementParser
from elspais.core.patterns import PatternConfig
from elspais.trace_view.coverage import (
    calculate_coverage,
    generate_coverage_report,
    get_implementation_status,
)
from elspais.trace_view.generators.csv import generate_csv, generate_planning_csv
from elspais.trace_view.generators.markdown import generate_markdown
from elspais.trace_view.models import GitChangeInfo as TVGitChangeInfo
from elspais.trace_view.models import TraceViewRequirement
from elspais.trace_view.scanning import scan_implementation_files


class TraceViewGenerator:
    """Generates traceability matrices.

    This is the main entry point for generating traceability reports.
    Supports multiple output formats: markdown, html, csv.

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
    VERSION = 17

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
        self.requirements: Dict[str, TraceViewRequirement] = {}
        self.impl_dirs = impl_dirs or []
        self.sponsor = sponsor
        self.mode = mode
        self.repo_root = repo_root or (spec_dir.parent if spec_dir else Path.cwd())
        self.associated_repos = associated_repos or []
        self._base_path = ""
        self._config = config
        self._git_info: Optional[TVGitChangeInfo] = None

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

        # Parse requirements
        if not quiet:
            print("Scanning for requirements...")
        self._parse_requirements(quiet)

        if not self.requirements:
            if not quiet:
                print("Warning: No requirements found")
            return ""

        if not quiet:
            print(f"Found {len(self.requirements)} requirements")

        # Pre-detect cycles and mark affected requirements
        self._detect_and_mark_cycles(quiet)

        # Scan implementation files
        if self.impl_dirs:
            if not quiet:
                print("Scanning implementation files...")
            scan_implementation_files(
                self.requirements,
                self.impl_dirs,
                self.repo_root,
                self.mode,
                self.sponsor,
                quiet=quiet,
            )

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
                requirements=self.requirements,
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
            content = generate_csv(self.requirements)
        else:
            content = generate_markdown(self.requirements, self._base_path)

        # Write output file
        output_file.write_text(content)
        if not quiet:
            print(f"Traceability matrix written to: {output_file}")

        return content

    def _init_git_state(self, quiet: bool = False):
        """Initialize git state for requirement status detection."""
        try:
            git_changes = get_git_changes(self.repo_root)

            # Convert to trace_view GitChangeInfo
            self._git_info = TVGitChangeInfo(
                uncommitted_files=git_changes.uncommitted_files,
                untracked_files=git_changes.untracked_files,
                branch_changed_files=git_changes.branch_changed_files,
                committed_req_locations=git_changes.committed_req_locations,
            )

            # Report uncommitted changes
            if not quiet and git_changes.uncommitted_files:
                spec_uncommitted = [
                    f for f in git_changes.uncommitted_files if f.startswith("spec/")
                ]
                if spec_uncommitted:
                    print(f"Uncommitted spec files: {len(spec_uncommitted)}")

            # Report branch changes vs main
            if not quiet and git_changes.branch_changed_files:
                spec_branch = [f for f in git_changes.branch_changed_files if f.startswith("spec/")]
                if spec_branch:
                    print(f"Spec files changed vs main: {len(spec_branch)}")

        except Exception as e:
            # Git state is optional - continue without it
            if not quiet:
                print(f"Warning: Could not get git state: {e}")
            self._git_info = None

    def _parse_requirements(self, quiet: bool = False):
        """Parse all requirements using elspais parser directly."""
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
        pattern_config = PatternConfig.from_dict(self._config.get("patterns", {}))
        spec_config = self._config.get("spec", {})
        no_reference_values = spec_config.get("no_reference_values")
        skip_files = spec_config.get("skip_files", [])

        parser = RequirementParser(pattern_config, no_reference_values=no_reference_values)
        parse_result = parser.parse_directories(spec_dirs, skip_files=skip_files)

        roadmap_count = 0
        conflict_count = 0
        cycle_count = 0

        for req_id, core_req in parse_result.items():
            # Wrap in TraceViewRequirement
            tv_req = TraceViewRequirement.from_core(core_req, git_info=self._git_info)

            if tv_req.is_roadmap:
                roadmap_count += 1
            if tv_req.is_conflict:
                conflict_count += 1
                if not quiet:
                    print(f"   Warning: Conflict: {req_id} conflicts with {tv_req.conflict_with}")

            # Store by short ID (without REQ- prefix)
            self.requirements[tv_req.id] = tv_req

        if not quiet:
            if roadmap_count > 0:
                print(f"   Found {roadmap_count} roadmap requirements")
            if conflict_count > 0:
                print(f"   Found {conflict_count} conflicts")
            if cycle_count > 0:
                print(f"   Found {cycle_count} requirements in dependency cycles")

    def _detect_and_mark_cycles(self, quiet: bool = False):
        """Detect and mark requirements that are part of dependency cycles.

        Uses centralized detect_cycles() from core.hierarchy for cycle detection,
        then marks affected requirements locally.
        """
        # Build dict of core requirements for cycle detection
        core_requirements = {req_id: req.core for req_id, req in self.requirements.items()}

        # Use centralized cycle detection (pure function - no mutation)
        cycle_info = detect_cycles(core_requirements)

        # Clear implements for cycle members so they appear as orphaned
        cycle_count = 0
        for req_id in cycle_info.cycle_members:
            if req_id in self.requirements:
                req = self.requirements[req_id]
                if req.implements:
                    # Modify the underlying core requirement
                    req.core.implements = []
                    cycle_count += 1

        if not quiet and cycle_count > 0:
            print(
                f"   Warning: {cycle_count} requirements marked as cyclic (shown as orphaned items)"
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

        def get_status(req_id):
            return get_implementation_status(self.requirements, req_id)

        def calc_coverage(req_id):
            return calculate_coverage(self.requirements, req_id)

        return generate_planning_csv(self.requirements, get_status, calc_coverage)

    def generate_coverage_report(self) -> str:
        """Generate coverage report showing implementation status."""
        return generate_coverage_report(self.requirements)
