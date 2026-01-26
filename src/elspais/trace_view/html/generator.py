"""
HTML Generator for trace-view.

This module contains all HTML, CSS, and JavaScript generation for the
interactive traceability matrix report. Uses TraceGraph as the single
source of truth - no separate data structures.

Contains:
- HTMLGenerator class with all HTML rendering methods
- CSS styles for the interactive report
- JavaScript for interactivity (expand/collapse, side panel, code viewer)
- Modal dialogs (legend, file picker)
- Edit mode functionality
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from jinja2 import Environment, FileSystemLoader, select_autoescape

from elspais.core.annotators import (
    collect_topics,
    count_by_level,
    count_by_repo,
    count_implementation_files,
    get_implementation_status,
)
from elspais.core.graph import NodeKind, TraceGraph, TraceNode


class HTMLGenerator:
    """Generates interactive HTML traceability matrix from TraceGraph.

    This class consumes the unified TraceGraph directly - no separate
    data structures or coverage calculations.

    Args:
        graph: The TraceGraph containing all requirement data
        base_path: Relative path from output file to repo root (for links)
        mode: Report mode ('core', 'sponsor', 'combined')
        sponsor: Sponsor name if in sponsor mode
        version: Version number for display
        repo_root: Repository root path for absolute links
    """

    def __init__(
        self,
        graph: TraceGraph,
        base_path: str = "",
        mode: str = "core",
        sponsor: Optional[str] = None,
        version: int = 18,
        repo_root: Optional[Path] = None,
    ):
        self.graph = graph
        self._base_path = base_path
        self.mode = mode
        self.sponsor = sponsor
        self.VERSION = version
        self.repo_root = repo_root
        # Instance tracking for flat list building
        self._instance_counter = 0
        self._visited_node_ids: Set[str] = set()

        # Jinja2 template environment
        template_dir = Path(__file__).parent / "templates"
        self.env = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=select_autoescape(["html", "xml"]),
            trim_blocks=True,
            lstrip_blocks=True,
        )

        # Register custom filters for templates
        self.env.filters["status_class"] = lambda s: s.lower() if s else ""
        self.env.filters["level_class"] = lambda s: s.lower() if s else ""

    def generate(
        self, embed_content: bool = False, edit_mode: bool = False, review_mode: bool = False
    ) -> str:
        """Generate the complete HTML report using Jinja2 templates.

        Args:
            embed_content: If True, embed full requirement content as JSON
            edit_mode: If True, include edit mode UI elements
            review_mode: If True, include review mode UI and scripts

        Returns:
            Complete HTML document as string

        Raises:
            jinja2.TemplateError: If template rendering fails
        """
        context = self._build_render_context(embed_content, edit_mode, review_mode)
        template = self.env.get_template("base.html")
        return template.render(**context)

    def _load_css(self) -> str:
        """Load CSS content from external stylesheet."""
        css_path = Path(__file__).parent / "templates" / "partials" / "styles.css"
        if css_path.exists():
            return css_path.read_text()
        return ""

    def _load_js(self) -> str:
        """Load JavaScript content from external script file."""
        js_path = Path(__file__).parent / "templates" / "partials" / "scripts.js"
        if js_path.exists():
            return js_path.read_text()
        return ""

    def _load_review_css(self) -> str:
        """Load review system CSS."""
        css_path = Path(__file__).parent / "templates" / "partials" / "review-styles.css"
        if css_path.exists():
            return css_path.read_text()
        return ""

    def _load_review_js(self) -> str:
        """Load review system JavaScript modules."""
        review_dir = Path(__file__).parent / "templates" / "partials" / "review"
        if not review_dir.exists():
            return ""

        # Load modules in dependency order
        module_order = [
            "review-data.js",
            "review-position.js",
            "review-line-numbers.js",
            "review-comments.js",
            "review-status.js",
            "review-packages.js",
            "review-sync.js",
            "review-help.js",
            "review-resize.js",
            "review-init.js",
        ]

        js_parts = []
        for module_name in module_order:
            module_path = review_dir / module_name
            if module_path.exists():
                js_parts.append(f"// === {module_name} ===")
                js_parts.append(module_path.read_text())

        return "\n".join(js_parts)

    def _build_render_context(
        self, embed_content: bool = False, edit_mode: bool = False, review_mode: bool = False
    ) -> dict:
        """Build the template render context."""
        # Use composable aggregate functions from annotators module
        by_level = count_by_level(self.graph)
        by_repo = count_by_repo(self.graph)
        sorted_topics = collect_topics(self.graph)

        # Build requirements HTML
        requirements_html = self._generate_requirements_html(embed_content, edit_mode)

        # Build JSON data for embedded mode
        req_json_data = ""
        if embed_content:
            req_json_data = self._generate_req_json_data()

        return {
            # Configuration flags
            "embed_content": embed_content,
            "edit_mode": edit_mode,
            "review_mode": review_mode,
            "version": self.VERSION,
            # Statistics
            "stats": {
                "prd": {"active": by_level["active"]["PRD"], "all": by_level["all"]["PRD"]},
                "ops": {"active": by_level["active"]["OPS"], "all": by_level["all"]["OPS"]},
                "dev": {"active": by_level["active"]["DEV"], "all": by_level["all"]["DEV"]},
                "impl_files": count_implementation_files(self.graph),
            },
            # Repo prefix stats
            "repo_stats": by_repo,
            # Requirements data
            "topics": sorted_topics,
            "requirements_html": requirements_html,
            "req_json_data": req_json_data,
            # Asset content
            "css": self._load_css(),
            "js": self._load_js(),
            # Review mode assets
            "review_css": self._load_review_css() if review_mode else "",
            "review_js": self._load_review_js() if review_mode else "",
            "review_json_data": self._generate_review_json_data() if review_mode else "",
            # Metadata
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "repo_root": str(self.repo_root) if self.repo_root else "",
        }

    def _generate_requirements_html(
        self, embed_content: bool = False, edit_mode: bool = False
    ) -> str:
        """Generate the HTML for all requirements."""
        flat_list = self._build_flat_requirement_list()

        html_parts = []
        for item_data in flat_list:
            html_parts.append(
                self._format_item_flat_html(
                    item_data, embed_content=embed_content, edit_mode=edit_mode
                )
            )

        return "\n".join(html_parts)

    def _generate_legend_html(self) -> str:
        """Generate HTML legend section"""
        return """
        <div style="background: #f8f9fa; padding: 15px; border-radius: 4px; margin: 20px 0;">
            <h2 style="margin-top: 0;">Legend</h2>
            <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 15px;">
                <div>
                    <h3 style="font-size: 13px; margin-bottom: 8px;">Requirement Status:</h3>
                    <ul style="list-style: none; padding: 0; font-size: 12px;">
                        <li style="margin: 4px 0;">✅ Active requirement</li>
                        <li style="margin: 4px 0;">🚧 Draft requirement</li>
                        <li style="margin: 4px 0;">⚠️ Deprecated requirement</li>
                        <li style="margin: 4px 0;"><span style="color: #28a745; \
font-weight: bold;">+</span> NEW (in untracked file)</li>
                        <li style="margin: 4px 0;"><span style="color: #fd7e14; \
font-weight: bold;">*</span> MODIFIED (content changed)</li>
                        <li style="margin: 4px 0;">🗺️ Roadmap - hidden by default</li>
                    </ul>
                </div>
                <div>
                    <h3 style="font-size: 13px; margin-bottom: 8px;">Traceability:</h3>
                    <ul style="list-style: none; padding: 0; font-size: 12px;">
                        <li style="margin: 4px 0;">🔗 Has implementation file(s)</li>
                        <li style="margin: 4px 0;">○ No implementation found</li>
                    </ul>
                </div>
                <div>
                    <h3 style="font-size: 13px; margin-bottom: 8px;">Implementation Coverage:</h3>
                    <ul style="list-style: none; padding: 0; font-size: 12px;">
                        <li style="margin: 4px 0;">● Full coverage</li>
                        <li style="margin: 4px 0;">◐ Partial coverage</li>
                        <li style="margin: 4px 0;">○ Unimplemented</li>
                    </ul>
                </div>
            </div>
            <div style="margin-top: 10px;">
                <h3 style="font-size: 13px; margin-bottom: 8px;">Interactive Controls:</h3>
                <ul style="list-style: none; padding: 0; font-size: 12px;">
                    <li style="margin: 4px 0;">▼ Expandable (has child requirements)</li>
                    <li style="margin: 4px 0;">▶ Collapsed (click to expand)</li>
                </ul>
            </div>
        </div>
"""

    def _generate_req_json_data(self) -> str:
        """Generate JSON data containing all requirement content for embedded mode"""
        req_data = {}
        for node in self.graph.all_nodes():
            if node.kind != NodeKind.REQUIREMENT:
                continue
            req = node.requirement
            if not req:
                continue

            req_id = node.id
            is_roadmap = node.metrics.get("is_roadmap", False)
            external_spec_path = node.metrics.get("external_spec_path")
            is_conflict = node.metrics.get("is_conflict", False)
            conflict_with = node.metrics.get("conflict_with")
            is_cycle = node.metrics.get("is_cycle", False)
            cycle_path = node.metrics.get("cycle_path")
            repo_prefix = node.metrics.get("repo_prefix")
            display_filename = node.metrics.get("display_filename", "")

            # Determine file path URL
            if external_spec_path:
                file_path_url = f"file://{external_spec_path}"
            else:
                spec_subpath = "spec/roadmap" if is_roadmap else "spec"
                file_name = node.metrics.get("file_name", f"{display_filename}.md")
                file_path_url = f"{self._base_path}{spec_subpath}/{file_name}"

            req_data[req_id] = {
                "title": req.title,
                "status": req.status,
                "level": req.level,
                "body": req.body.strip(),
                "rationale": req.rationale.strip() if req.rationale else "",
                "file": display_filename,
                "filePath": file_path_url,
                "line": node.source.line if node.source else 0,
                "implements": list(req.implements) if req.implements else [],
                "isRoadmap": is_roadmap,
                "isConflict": is_conflict,
                "conflictWith": conflict_with,
                "isCycle": is_cycle,
                "cyclePath": cycle_path,
                "isExternal": external_spec_path is not None,
                "repoPrefix": repo_prefix,
            }
        json_str = json.dumps(req_data, indent=2)
        json_str = json_str.replace("</script>", "<\\/script>")
        return json_str

    def _generate_review_json_data(self) -> str:
        """Generate JSON data for review mode initialization."""
        review_data = {
            "threads": {},
            "flags": {},
            "requests": {},
            "config": {
                "approvalRules": {
                    "Draft->Active": ["product_owner", "tech_lead"],
                    "Active->Deprecated": ["product_owner"],
                    "Draft->Deprecated": ["product_owner"],
                },
                "pushOnComment": True,
                "autoFetchOnOpen": True,
            },
        }

        # Load existing review data from .reviews/ directory
        if self.repo_root:
            reviews_dir = self.repo_root / ".reviews" / "reqs"
            if reviews_dir.exists():
                for req_dir in reviews_dir.iterdir():
                    if req_dir.is_dir():
                        req_id = req_dir.name
                        # Load threads
                        threads_file = req_dir / "threads.json"
                        if threads_file.exists():
                            try:
                                with open(threads_file) as f:
                                    threads_data = json.load(f)
                                    if "threads" in threads_data:
                                        review_data["threads"][req_id] = threads_data["threads"]
                            except (OSError, json.JSONDecodeError) as e:
                                print(
                                    f"Warning: Could not load {threads_file}: {e}", file=sys.stderr
                                )

                        # Load flags
                        flag_file = req_dir / "flag.json"
                        if flag_file.exists():
                            try:
                                with open(flag_file) as f:
                                    flag_data = json.load(f)
                                    review_data["flags"][req_id] = flag_data
                            except (OSError, json.JSONDecodeError) as e:
                                print(f"Warning: Could not load {flag_file}: {e}", file=sys.stderr)

                        # Load status requests
                        status_file = req_dir / "status.json"
                        if status_file.exists():
                            try:
                                with open(status_file) as f:
                                    status_data = json.load(f)
                                    if "requests" in status_data:
                                        review_data["requests"][req_id] = status_data["requests"]
                            except (OSError, json.JSONDecodeError) as e:
                                print(
                                    f"Warning: Could not load {status_file}: {e}", file=sys.stderr
                                )

        json_str = json.dumps(review_data, indent=2)
        json_str = json_str.replace("</script>", "<\\/script>")
        return json_str

    def _build_flat_requirement_list(self) -> List[dict]:
        """Build a flat list of requirements with hierarchy information.

        Uses graph.roots and node.children for traversal - no re-computation.
        """
        flat_list = []
        self._instance_counter = 0
        self._visited_node_ids = set()

        # Start with root nodes from graph
        for root in self.graph.roots:
            if root.kind == NodeKind.REQUIREMENT:
                self._add_node_and_children(
                    root, flat_list, indent=0, parent_instance_id="", ancestor_path=[]
                )

        # Add any orphaned requirements not reachable from roots
        all_req_nodes = {n.id for n in self.graph.all_nodes() if n.kind == NodeKind.REQUIREMENT}
        orphaned_ids = all_req_nodes - self._visited_node_ids

        if orphaned_ids:
            orphaned_nodes = [self.graph.find_by_id(nid) for nid in orphaned_ids]
            orphaned_nodes = [n for n in orphaned_nodes if n]  # Filter None
            orphaned_nodes.sort(key=lambda n: n.id)
            for orphan in orphaned_nodes:
                self._add_node_and_children(
                    orphan,
                    flat_list,
                    indent=0,
                    parent_instance_id="",
                    ancestor_path=[],
                    is_orphan=True,
                )

        return flat_list

    def _get_children_with_assertion_info(
        self, node: TraceNode
    ) -> List[Tuple[TraceNode, List[str]]]:
        """Get child requirement nodes with their assertion labels.

        Finds requirements that are children of this node in two ways:
        1. Direct REQUIREMENT children (implements the requirement directly)
        2. REQUIREMENT children of ASSERTION children (implements specific assertions)

        Returns:
            List of (child_node, assertion_labels) tuples.
        """
        import re

        # Track children we've seen to avoid duplicates
        seen_children: Dict[str, List[str]] = {}
        parent_id = node.id

        # 1. Get direct REQUIREMENT children
        for child in node.children:
            if child.kind != NodeKind.REQUIREMENT:
                continue

            child_req = child.requirement
            if not child_req:
                continue

            assertion_labels: List[str] = []

            for impl_ref in child_req.implements:
                if impl_ref == parent_id:
                    # Direct implementation of parent
                    pass  # No assertion labels
                elif impl_ref.startswith(parent_id + "-"):
                    # Implements specific assertion(s) via multi-assertion syntax
                    suffix = impl_ref[len(parent_id) + 1:]
                    labels = suffix.split("-")
                    labels = [lbl for lbl in labels if re.match(r"^[A-Z]$", lbl)]
                    if labels:
                        assertion_labels.extend(labels)

            if child.id not in seen_children:
                seen_children[child.id] = []
            seen_children[child.id].extend(assertion_labels)

        # 2. Get REQUIREMENT children via ASSERTION children
        # When a child implements REQ-p00001-A, it's linked to the assertion node
        for child in node.children:
            if child.kind != NodeKind.ASSERTION:
                continue

            # Extract assertion label from assertion node ID
            assertion_label = child.id.split("-")[-1] if "-" in child.id else ""

            # Find REQUIREMENT children of this assertion
            for assertion_child in child.children:
                if assertion_child.kind != NodeKind.REQUIREMENT:
                    continue

                child_req = assertion_child.requirement
                if not child_req:
                    continue

                if assertion_child.id not in seen_children:
                    seen_children[assertion_child.id] = []

                # Add the assertion label this child implements
                if assertion_label and re.match(r"^[A-Z]$", assertion_label):
                    seen_children[assertion_child.id].append(assertion_label)

        # Build result list
        children_with_assertions: List[Tuple[TraceNode, List[str]]] = []
        for child_id, labels in seen_children.items():
            child_node = self.graph.find_by_id(child_id)
            if child_node:
                unique_labels = sorted(set(labels))
                children_with_assertions.append((child_node, unique_labels))

        # Sort by node ID
        children_with_assertions.sort(key=lambda x: x[0].id)
        return children_with_assertions

    def _add_node_and_children(
        self,
        node: TraceNode,
        flat_list: List[dict],
        indent: int,
        parent_instance_id: str,
        ancestor_path: list[str],
        is_orphan: bool = False,
        assertion_labels: List[str] = None,
    ):
        """Recursively add node and its children to flat list.

        Uses node.children from graph - no re-computation of hierarchy.
        """
        if assertion_labels is None:
            assertion_labels = []

        # Cycle detection
        if node.id in ancestor_path:
            cycle_path = ancestor_path + [node.id]
            cycle_str = " -> ".join(cycle_path)
            print(f"⚠️  CYCLE DETECTED in flat list build: {cycle_str}", file=sys.stderr)
            return

        # Track visited
        self._visited_node_ids.add(node.id)

        # Generate unique instance ID
        instance_id = f"inst_{self._instance_counter}"
        self._instance_counter += 1

        # Get children from graph
        children_with_assertions = self._get_children_with_assertion_info(node)

        # Get implementation files from metrics
        impl_files = node.metrics.get("implementation_files", [])

        # Check if has children
        has_children = len(children_with_assertions) > 0 or len(impl_files) > 0

        # Add this node
        flat_list.append(
            {
                "node": node,
                "indent": indent,
                "instance_id": instance_id,
                "parent_instance_id": parent_instance_id,
                "has_children": has_children,
                "item_type": "requirement",
                "assertion_labels": assertion_labels,
            }
        )

        # Add implementation files as child items
        for file_path, line_num in impl_files:
            impl_instance_id = f"inst_{self._instance_counter}"
            self._instance_counter += 1
            flat_list.append(
                {
                    "file_path": file_path,
                    "line_num": line_num,
                    "indent": indent + 1,
                    "instance_id": impl_instance_id,
                    "parent_instance_id": instance_id,
                    "has_children": False,
                    "item_type": "implementation",
                }
            )

        # Recursively add child requirements
        current_path = ancestor_path + [node.id]
        for child, child_assertion_labels in children_with_assertions:
            self._add_node_and_children(
                child,
                flat_list,
                indent + 1,
                instance_id,
                current_path,
                assertion_labels=child_assertion_labels,
            )

    def _format_item_flat_html(
        self, item_data: dict, embed_content: bool = False, edit_mode: bool = False
    ) -> str:
        """Format a single item as flat HTML row."""
        item_type = item_data.get("item_type", "requirement")

        if item_type == "implementation":
            return self._format_impl_file_html(item_data, embed_content, edit_mode)
        else:
            return self._format_req_html(item_data, embed_content, edit_mode)

    def _format_impl_file_html(
        self, item_data: dict, embed_content: bool = False, edit_mode: bool = False
    ) -> str:
        """Format an implementation file as a child row"""
        file_path = item_data["file_path"]
        line_num = item_data["line_num"]
        indent = item_data["indent"]
        instance_id = item_data["instance_id"]
        parent_instance_id = item_data["parent_instance_id"]

        # Create link or onclick handler
        if embed_content:
            file_url = f"{self._base_path}{file_path}"
            file_link = (
                f'<a href="#" onclick="openCodeViewer(\'{file_url}\', {line_num}); '
                f'return false;" style="color: #0066cc;">{file_path}:{line_num}</a>'
            )
        else:
            link = f"{self._base_path}{file_path}#L{line_num}"
            file_link = f'<a href="{link}" style="color: #0066cc;">{file_path}:{line_num}</a>'

        # Add VS Code link
        if self.repo_root:
            abs_file_path = self.repo_root / file_path
            vscode_url = f"vscode://file/{abs_file_path}:{line_num}"
            vscode_link = f'<a href="{vscode_url}" title="Open in VS Code" class="vscode-link">🔧</a>'
            file_link = f"{file_link}{vscode_link}"

        edit_column = '<div class="req-destination edit-mode-column"></div>' if edit_mode else ""

        html = f"""
        <div class="req-item impl-file" data-instance-id="{instance_id}" \
data-indent="{indent}" data-parent-instance-id="{parent_instance_id}">
            <div class="req-header-container">
                <span class="collapse-icon"></span>
                <div class="req-content">
                    <div class="req-id" style="color: #6c757d;">📄</div>
                    <div class="req-header" style="font-family: 'Consolas', 'Monaco', \
monospace; font-size: 12px;">{file_link}</div>
                    <div class="req-level"></div>
                    <div class="req-badges"></div>
                    <div class="req-coverage"></div>
                    <div class="req-status"></div>
                    <div class="req-location"></div>
                    {edit_column}
                </div>
            </div>
        </div>
"""
        return html

    def _format_req_html(
        self, req_data: dict, embed_content: bool = False, edit_mode: bool = False
    ) -> str:
        """Format a single requirement node as flat HTML row."""
        node = req_data["node"]
        req = node.requirement
        indent = req_data["indent"]
        instance_id = req_data["instance_id"]
        parent_instance_id = req_data["parent_instance_id"]
        has_children = req_data["has_children"]
        assertion_labels = req_data.get("assertion_labels", [])

        if not req:
            return ""

        status_class = req.status.lower()
        level_class = req.level.lower()

        # Collapse icon
        collapse_icon = "▼" if has_children else "●"

        # Assertion indicator
        assertion_indicator = ""
        if assertion_labels:
            labels_str = ",".join(assertion_labels)
            assertion_indicator = f'<span class="assertion-indicator" title="Implements assertion(s) {labels_str}">({labels_str})</span>'

        # Implementation coverage status from graph metrics
        impl_status = get_implementation_status(node)
        if impl_status == "Full":
            coverage_icon = "●"
            coverage_title = "Full implementation coverage"
        elif impl_status == "Partial":
            coverage_icon = "◐"
            coverage_title = "Partial implementation coverage"
        else:
            coverage_icon = "○"
            coverage_title = "Unimplemented"

        # Test status from metrics
        test_badge = ""
        total_tests = node.metrics.get("total_tests", 0)
        passed_tests = node.metrics.get("passed_tests", 0)
        failed_tests = node.metrics.get("failed_tests", 0)

        if total_tests > 0:
            if failed_tests > 0:
                test_badge = (
                    f'<span class="test-badge test-failed" '
                    f'title="{total_tests} tests, some failed">❌ {total_tests}</span>'
                )
            else:
                test_badge = (
                    f'<span class="test-badge test-passed" '
                    f'title="{passed_tests} tests passed">✅ {total_tests}</span>'
                )
        else:
            test_badge = (
                '<span class="test-badge test-not-tested" '
                'title="No tests implemented">⚡</span>'
            )

        # Extract topic from filename
        topic = ""
        if req.file_path:
            topic = (
                req.file_path.stem.split("-", 1)[1]
                if "-" in req.file_path.stem
                else req.file_path.stem
            )

        # Get display info from node metrics
        display_filename = node.metrics.get("display_filename", "")
        is_roadmap = node.metrics.get("is_roadmap", False)
        external_spec_path = node.metrics.get("external_spec_path")
        repo_prefix = node.metrics.get("repo_prefix", "CORE")
        file_name = node.metrics.get("file_name", f"{display_filename}.md")
        line_number = node.source.line if node.source else 0

        # Create spec URL
        if external_spec_path:
            spec_url = f"file://{external_spec_path}"
        else:
            spec_subpath = "spec/roadmap" if is_roadmap else "spec"
            spec_url = f"{self._base_path}{spec_subpath}/{file_name}"

        # Display filename with repo prefix
        file_stem = req.file_path.stem if req.file_path else display_filename
        display_filename_full = f"{repo_prefix}/{file_stem}" if repo_prefix and repo_prefix != "CORE" else file_stem

        # Display ID (strip __conflict suffix)
        display_id = node.id
        if "__conflict" in node.id:
            display_id = node.id.replace("__conflict", "")

        if embed_content:
            req_link = (
                f'<a href="#" onclick="event.stopPropagation(); '
                f"openReqPanel('{node.id}'); return false;\" "
                f'style="color: inherit; text-decoration: none; cursor: pointer;">'
                f"{display_id}</a>"
            )
            file_line_link = f'<span style="color: inherit;">{display_filename_full}</span>'
        else:
            req_link = (
                f'<a href="{spec_url}#{node.id}" '
                f'style="color: inherit; text-decoration: none;">{display_id}</a>'
            )
            file_line_link = (
                f'<a href="{spec_url}#L{line_number}" '
                f'style="color: inherit; text-decoration: none;">{display_filename_full}</a>'
            )

        # Git status indicators from metrics
        is_moved = node.metrics.get("is_moved", False)
        is_new = node.metrics.get("is_new", False)
        is_modified = node.metrics.get("is_modified", False)
        is_uncommitted = node.metrics.get("is_uncommitted", False)
        is_branch_changed = node.metrics.get("is_branch_changed", False)

        status_suffix = ""
        status_suffix_class = ""
        status_title = ""

        is_new_not_moved = is_new and not is_moved

        if is_moved and is_modified:
            status_suffix = "↝◆"
            status_suffix_class = "status-moved-modified"
            status_title = "MOVED and MODIFIED"
        elif is_moved:
            status_suffix = "↝"
            status_suffix_class = "status-moved"
            status_title = "MOVED from another file"
        elif is_new_not_moved:
            status_suffix = "★"
            status_suffix_class = "status-new"
            status_title = "NEW requirement"
        elif is_modified:
            status_suffix = "◆"
            status_suffix_class = "status-modified"
            status_title = "MODIFIED content"

        # Data attributes
        is_root = len(node.parents) == 0
        is_root_attr = 'data-is-root="true"' if is_root else 'data-is-root="false"'
        uncommitted_attr = 'data-uncommitted="true"' if is_uncommitted else 'data-uncommitted="false"'
        branch_attr = 'data-branch-changed="true"' if is_branch_changed else 'data-branch-changed="false"'
        has_children_attr = 'data-has-children="true"' if has_children else 'data-has-children="false"'

        # Test status attribute
        test_status_value = "not-tested"
        if total_tests > 0:
            if failed_tests > 0:
                test_status_value = "failed"
            else:
                test_status_value = "tested"
        test_status_attr = f'data-test-status="{test_status_value}"'

        # Coverage attribute
        coverage_value = "none"
        if impl_status == "Full":
            coverage_value = "full"
        elif impl_status == "Partial":
            coverage_value = "partial"
        coverage_attr = f'data-coverage="{coverage_value}"'

        # Roadmap attribute
        roadmap_attr = 'data-roadmap="true"' if is_roadmap else 'data-roadmap="false"'

        # Edit mode buttons
        edit_buttons = ""
        if edit_mode and req.file_path:
            req_id = node.id
            file_name_edit = req.file_path.name
            if is_roadmap:
                from_roadmap_btn = (
                    f'<button class="edit-btn from-roadmap" '
                    f"onclick=\"addPendingMove('{req_id}', '{file_name_edit}', 'from-roadmap')\" "
                    f'title="Move out of roadmap">↩ From Roadmap</button>'
                )
                move_file_btn = (
                    f'<button class="edit-btn move-file" '
                    f"onclick=\"showMoveToFile('{req_id}', '{file_name_edit}')\" "
                    f'title="Move to different file">📁 Move</button>'
                )
                edit_buttons = (
                    f'<span class="edit-actions" onclick="event.stopPropagation();">'
                    f"{from_roadmap_btn}{move_file_btn}</span>"
                )
            else:
                to_roadmap_btn = (
                    f'<button class="edit-btn to-roadmap" '
                    f"onclick=\"addPendingMove('{req_id}', '{file_name_edit}', 'to-roadmap')\" "
                    f'title="Move to roadmap">🗺️ To Roadmap</button>'
                )
                move_file_btn = (
                    f'<button class="edit-btn move-file" '
                    f"onclick=\"showMoveToFile('{req_id}', '{file_name_edit}')\" "
                    f'title="Move to different file">📁 Move</button>'
                )
                edit_buttons = (
                    f'<span class="edit-actions" onclick="event.stopPropagation();">'
                    f"{to_roadmap_btn}{move_file_btn}</span>"
                )

        # Roadmap/conflict/cycle icons
        roadmap_icon = '<span class="roadmap-icon" title="In roadmap">🛤️</span>' if is_roadmap else ""

        is_conflict = node.metrics.get("is_conflict", False)
        conflict_with = node.metrics.get("conflict_with")
        conflict_icon = (
            f'<span class="conflict-icon" title="Conflicts with {conflict_with}">⚠️</span>'
            if is_conflict
            else ""
        )
        conflict_attr = (
            f'data-conflict="true" data-conflict-with="{conflict_with}"'
            if is_conflict
            else 'data-conflict="false"'
        )

        is_cycle = node.metrics.get("is_cycle", False)
        cycle_path = node.metrics.get("cycle_path", "")
        cycle_icon = (
            f'<span class="cycle-icon" title="Cycle: {cycle_path}">🔄</span>'
            if is_cycle
            else ""
        )
        cycle_attr = (
            f'data-cycle="true" data-cycle-path="{cycle_path}"'
            if is_cycle
            else 'data-cycle="false"'
        )

        item_class = "conflict-item" if is_conflict else ("cycle-item" if is_cycle else "")

        # Build data attributes
        deprecated_class = status_class if req.status == "Deprecated" else ""
        data_attrs = (
            f'data-req-id="{node.id}" data-instance-id="{instance_id}" '
            f'data-level="{req.level}" data-indent="{indent}" '
            f'data-parent-instance-id="{parent_instance_id}" data-topic="{topic}" '
            f'data-status="{req.status}" data-title="{req.title.lower()}" '
            f'data-file="{file_name}" data-repo="{repo_prefix}" '
            f"{is_root_attr} {uncommitted_attr} {branch_attr} {has_children_attr} "
            f"{test_status_attr} {coverage_attr} {roadmap_attr} {conflict_attr} {cycle_attr}"
        )

        # Status badges HTML
        status_badges_html = (
            f'<span class="status-badge status-{status_class}">{req.status}</span>'
            f'<span class="status-suffix {status_suffix_class}" '
            f'title="{status_title}">{status_suffix}</span>'
        )

        # Edit mode column
        edit_column_html = ""
        if edit_mode:
            edit_column_html = (
                f'<div class="req-destination edit-mode-column" data-req-id="{node.id}">'
                f'{edit_buttons}<span class="dest-text"></span></div>'
            )

        # Build HTML
        html = f"""
        <div class="req-item {level_class} {deprecated_class} {item_class}" {data_attrs}>
            <div class="req-header-container" onclick="toggleRequirement(this)">
                {assertion_indicator}<span class="collapse-icon">{collapse_icon}</span>
                <div class="req-content">
                    <div class="req-id">{conflict_icon}{cycle_icon}{req_link}{roadmap_icon}</div>
                    <div class="req-header">{req.title}</div>
                    <div class="req-level">{req.level}</div>
                    <div class="req-badges">
                        {status_badges_html}
                    </div>
                    <div class="req-coverage" title="{coverage_title}">{coverage_icon}</div>
                    <div class="req-status">{test_badge}</div>
                    <div class="req-location">{file_line_link}</div>
                    {edit_column_html}
                </div>
            </div>
        </div>
"""
        return html
