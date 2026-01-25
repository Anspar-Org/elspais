"""
elspais.mcp.reconstructor - Lossless file reconstruction from graph data.

Provides FileReconstructor class for reconstructing spec files from
graph data, enabling round-trip verification.

Supports two modes:
1. Graph-based: Uses FILE and FILE_REGION TraceNodes (when --graph-file enabled)
2. Legacy: Uses _file_index with FileNode metadata (backward compatibility)
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from elspais.core.graph import FileNode, NodeKind, TraceGraph, TraceNode
from elspais.core.models import Requirement


@dataclass
class ReconstructionResult:
    """Result of a file reconstruction operation.

    Attributes:
        success: Whether reconstruction succeeded
        content: Reconstructed file content (if successful)
        message: Error or info message
        original_content: Original content for comparison (if available)
        matches_original: True if reconstructed matches original
    """

    success: bool
    content: str
    message: str
    original_content: Optional[str] = None
    matches_original: Optional[bool] = None


class FileReconstructor:
    """Reconstructs spec files from graph data.

    Uses FileNode (with regions and requirement order) plus requirement
    data to reassemble the original file content.

    The reconstruction algorithm:
    1. Start with preamble region (if any)
    2. For each requirement in order:
       - Render requirement using Requirement object
       - Add inter-requirement region (if any)
    3. Add postamble region (if any)
    """

    def __init__(self, graph: TraceGraph):
        """Initialize reconstructor with graph.

        Args:
            graph: TraceGraph containing file_index and requirements
        """
        self.graph = graph

    def reconstruct_file(self, file_path: str) -> ReconstructionResult:
        """Reconstruct a file from graph data.

        Supports two modes:
        1. Graph-based: Uses FILE TraceNodes (when --graph-file was used)
        2. Legacy: Uses _file_index with FileNode metadata

        Args:
            file_path: Relative path to file (as stored in FileNode)

        Returns:
            ReconstructionResult with reconstructed content
        """
        # Try graph-based reconstruction first (preferred)
        file_node_id = f"file:{file_path}"
        file_trace_node = self.graph.find_by_id(file_node_id)

        if file_trace_node and file_trace_node.kind == NodeKind.FILE:
            return self._reconstruct_from_graph(file_trace_node)

        # Fall back to legacy _file_index approach
        legacy_file_node = self.graph.get_file_node(file_path)
        if legacy_file_node:
            return self._reconstruct_from_file_node(legacy_file_node)

        return ReconstructionResult(
            success=False,
            content="",
            message=f"No file data found for {file_path}",
        )

    def _reconstruct_from_graph(self, file_node: TraceNode) -> ReconstructionResult:
        """Reconstruct file from FILE TraceNode in graph.

        Uses FILE_REGION children and file_info.requirements for reconstruction.

        Args:
            file_node: TraceNode with kind=FILE

        Returns:
            ReconstructionResult with reconstructed content
        """
        if not file_node.file_info:
            return ReconstructionResult(
                success=False,
                content="",
                message="FILE node missing file_info",
            )

        parts = []

        # Get FILE_REGION children sorted by source line
        region_children = [
            child for child in file_node.children
            if child.kind == NodeKind.FILE_REGION
        ]
        region_children.sort(key=lambda n: n.source.line if n.source else 0)

        # Find preamble
        preamble = next(
            (r for r in region_children if r.file_region and r.file_region.region_type == "preamble"),
            None
        )
        if preamble and preamble.file_region:
            parts.append(preamble.file_region.content)

        # Get inter-requirement regions
        inter_regions = [
            r for r in region_children
            if r.file_region and r.file_region.region_type == "inter_requirement"
        ]
        inter_region_idx = 0

        # Add requirements in order with inter-requirement regions
        for req_node in file_node.file_info.requirements:
            if req_node and req_node.requirement:
                req_text = self._render_requirement(req_node.requirement)
                parts.append(req_text)

                # Add inter-requirement region after this requirement (if any)
                if inter_region_idx < len(inter_regions):
                    parts.append(inter_regions[inter_region_idx].file_region.content)
                    inter_region_idx += 1
            else:
                # Requirement not found - use placeholder
                req_id = req_node.id if req_node else "UNKNOWN"
                parts.append(f"# {req_id}: [MISSING REQUIREMENT]\n\n*End* *MISSING* | **Hash**: UNKNOWN\n\n---")

        # Find postamble
        postamble = next(
            (r for r in region_children if r.file_region and r.file_region.region_type == "postamble"),
            None
        )
        if postamble and postamble.file_region:
            parts.append(postamble.file_region.content)

        reconstructed = "\n".join(parts) if parts else ""

        return ReconstructionResult(
            success=True,
            content=reconstructed,
            message="Reconstruction successful (graph-based)",
        )

    def _reconstruct_from_file_node(self, file_node: FileNode) -> ReconstructionResult:
        """Reconstruct file from legacy FileNode in _file_index.

        This is the original reconstruction algorithm for backward compatibility.

        Args:
            file_node: FileNode from graph._file_index

        Returns:
            ReconstructionResult with reconstructed content
        """
        # Build the reconstructed content
        parts = []

        # Add preamble
        preamble = file_node.get_preamble()
        if preamble:
            parts.append(preamble)

        # Add requirements in order with inter-requirement regions
        inter_regions = [r for r in file_node.regions if r.region_type == "inter_requirement"]
        inter_region_idx = 0

        for i, req_id in enumerate(file_node.requirements):
            # Get requirement from graph
            node = self.graph.find_by_id(req_id)
            if node and node.requirement:
                # Render requirement
                req_text = self._render_requirement(node.requirement)
                parts.append(req_text)

                # Add inter-requirement region after this requirement (if any)
                if inter_region_idx < len(inter_regions):
                    parts.append(inter_regions[inter_region_idx].content)
                    inter_region_idx += 1
            else:
                # Requirement not found in graph - use placeholder
                parts.append(f"# {req_id}: [MISSING REQUIREMENT]\n\n*End* *MISSING* | **Hash**: UNKNOWN\n\n---")

        # Add postamble
        postamble = file_node.get_postamble()
        if postamble:
            parts.append(postamble)

        reconstructed = "\n".join(parts) if parts else ""

        return ReconstructionResult(
            success=True,
            content=reconstructed,
            message="Reconstruction successful (legacy)",
        )

    def _render_requirement(self, req: Requirement) -> str:
        """Render a requirement to text.

        Reconstructs the requirement in the standard format.

        Args:
            req: Requirement object

        Returns:
            Rendered requirement text
        """
        lines = []

        # Header line
        lines.append(f"# {req.id}: {req.title}")

        # Metadata line
        implements_str = ", ".join(req.implements) if req.implements else "-"
        refines_str = ", ".join(req.refines) if req.refines else None

        meta_line = f"**Level**: {req.level} | **Status**: {req.status}"
        if refines_str:
            meta_line += f" | **Refines**: {refines_str}"
        meta_line += f" | **Implements**: {implements_str}"
        lines.append("")
        lines.append(meta_line)

        # Body
        if req.body:
            lines.append("")
            lines.append(req.body)

        # Assertions section
        if req.assertions:
            lines.append("")
            lines.append("## Assertions")
            lines.append("")
            for assertion in req.assertions:
                lines.append(f"{assertion.label}. {assertion.text}")

        # Rationale
        if req.rationale:
            lines.append("")
            lines.append("## Rationale")
            lines.append("")
            lines.append(req.rationale)

        # End marker
        hash_str = req.hash if req.hash else "UNKNOWN"
        lines.append("")
        lines.append(f"*End* *{req.title}* | **Hash**: {hash_str}")

        # Separator
        lines.append("")
        lines.append("---")

        return "\n".join(lines)

    def verify_reconstruction(
        self,
        file_path: str,
        original_path: Optional[Path] = None,
    ) -> ReconstructionResult:
        """Verify reconstruction by comparing to original.

        Args:
            file_path: Relative path to file (as stored in FileNode)
            original_path: Absolute path to original file (optional)

        Returns:
            ReconstructionResult with comparison info
        """
        result = self.reconstruct_file(file_path)
        if not result.success:
            return result

        # Get original content
        file_node = self.graph.get_file_node(file_path)
        if file_node and file_node.original_lines is not None:
            original = "\n".join(file_node.original_lines)
        elif original_path and original_path.exists():
            original = original_path.read_text(encoding="utf-8")
        else:
            return ReconstructionResult(
                success=True,
                content=result.content,
                message="Reconstruction successful (no original for comparison)",
                matches_original=None,
            )

        # Compare (normalize line endings)
        reconstructed_normalized = result.content.rstrip()
        original_normalized = original.rstrip()

        matches = reconstructed_normalized == original_normalized

        return ReconstructionResult(
            success=True,
            content=result.content,
            message="Reconstruction matches original" if matches else "Reconstruction differs from original",
            original_content=original,
            matches_original=matches,
        )

    def diff_reconstruction(
        self,
        file_path: str,
        original_path: Optional[Path] = None,
    ) -> str:
        """Generate diff between original and reconstructed.

        Args:
            file_path: Relative path to file
            original_path: Absolute path to original file (optional)

        Returns:
            Unified diff string
        """
        import difflib

        result = self.verify_reconstruction(file_path, original_path)
        if not result.success:
            return f"Error: {result.message}"

        if result.original_content is None:
            return "No original content available for comparison"

        original_lines = result.original_content.splitlines(keepends=True)
        reconstructed_lines = result.content.splitlines(keepends=True)

        diff = difflib.unified_diff(
            original_lines,
            reconstructed_lines,
            fromfile=f"original/{file_path}",
            tofile=f"reconstructed/{file_path}",
        )

        return "".join(diff)
