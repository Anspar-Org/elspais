"""
elspais.mcp.reconstructor - Lossless file reconstruction from graph data.

STUB: File reconstruction not yet implemented.

The original implementation used FileNode with file regions for lossless
reconstruction. This needs to be re-implemented using the graph structure.

Provides FileReconstructor class for reconstructing spec files from
graph data, enabling round-trip verification.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from elspais.graph import NodeKind
from elspais.graph.builder import TraceGraph

if TYPE_CHECKING:
    from elspais.graph import GraphNode


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

    STUB: File reconstruction not yet implemented in the graph system.

    The original implementation used FileNode (with regions and requirement
    order) plus requirement data to reassemble the original file content.
    This needs to be re-implemented using the graph structure.
    """

    def __init__(self, graph: TraceGraph):
        """Initialize reconstructor with graph.

        Args:
            graph: TraceGraph containing requirements
        """
        self.graph = graph

    def reconstruct_file(self, file_path: str) -> ReconstructionResult:
        """Reconstruct a file from graph data.

        STUB: Not yet implemented in the graph system.

        Args:
            file_path: Relative path to file

        Returns:
            ReconstructionResult indicating not implemented
        """
        return ReconstructionResult(
            success=False,
            content="",
            message=f"File reconstruction not yet implemented in the graph system: {file_path}",
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

        STUB: Not yet implemented in the graph system.

        Args:
            file_path: Relative path to file
            original_path: Absolute path to original file (optional)

        Returns:
            ReconstructionResult indicating not implemented
        """
        return ReconstructionResult(
            success=False,
            content="",
            message=f"File reconstruction not yet implemented in the graph system: {file_path}",
        )

    def diff_reconstruction(
        self,
        file_path: str,
        original_path: Optional[Path] = None,
    ) -> str:
        """Generate diff between original and reconstructed.

        STUB: Not yet implemented in the graph system.

        Args:
            file_path: Relative path to file
            original_path: Absolute path to original file (optional)

        Returns:
            Error message indicating not implemented
        """
        return f"File reconstruction not yet implemented in the graph system: {file_path}"
