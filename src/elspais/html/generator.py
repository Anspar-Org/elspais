"""HTML Generator for traceability reports.

This module generates interactive HTML traceability matrices from TraceGraph.
Works standalone without external dependencies for basic output.
"""

from __future__ import annotations

import html
import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from elspais.graph.builder import TraceGraph
    from elspais.graph.GraphNode import GraphNode


class HTMLGenerator:
    """Generates interactive HTML traceability matrix from TraceGraph.

    Args:
        graph: The TraceGraph containing all requirement data.
        base_path: Relative path from output file to repo root.
        version: Version number for display.
    """

    def __init__(
        self,
        graph: TraceGraph,
        base_path: str = "",
        version: int = 1,
    ) -> None:
        self.graph = graph
        self.base_path = base_path
        self.version = version

    def generate(self, embed_content: bool = False) -> str:
        """Generate the complete HTML report.

        Args:
            embed_content: If True, embed full requirement content as JSON.

        Returns:
            Complete HTML document as string.
        """
        from elspais.graph import NodeKind

        # Collect requirements
        requirements = list(self.graph.nodes_by_kind(NodeKind.REQUIREMENT))
        requirements.sort(key=lambda n: n.id)

        # Generate table rows
        rows_html = self._generate_rows(requirements)

        # Generate embedded data if requested
        embedded_data = ""
        if embed_content:
            embedded_data = self._generate_embedded_data(requirements)

        # Assemble HTML
        html_content = self._render_template(
            rows_html=rows_html,
            embedded_data=embedded_data,
            embed_content=embed_content,
            req_count=len(requirements),
        )

        return html_content

    def _generate_rows(self, requirements: list[GraphNode]) -> str:
        """Generate HTML table rows for requirements."""
        from elspais.graph.relations import EdgeKind

        rows = []
        for node in requirements:
            req_id = html.escape(node.id)
            level = html.escape(node.content.get("level", ""))
            title = html.escape(node.label or "")
            status = html.escape(node.content.get("status", ""))

            # Get implements (from incoming edges)
            implements = []
            for edge in node.incoming_edges:
                if edge.kind == EdgeKind.IMPLEMENTS:
                    implements.append(edge.source.id)

            impl_html = ", ".join(html.escape(i) for i in implements) if implements else "-"

            # Get file info
            file_path = node.source.path if node.source else ""
            line = node.source.line if node.source else 0

            # Status class
            status_class = status.lower() if status else ""

            rows.append(f"""
        <tr class="requirement-row level-{level.lower()} status-{status_class}"
            data-id="{req_id}"
            data-level="{level}"
            data-status="{status}">
            <td class="id-cell">
                <span class="req-id">{req_id}</span>
            </td>
            <td class="level-cell level-{level.lower()}">{level}</td>
            <td class="title-cell">{title}</td>
            <td class="status-cell status-{status_class}">{status}</td>
            <td class="implements-cell">{impl_html}</td>
            <td class="file-cell">
                <a href="{html.escape(file_path)}#L{line}" class="file-link">
                    {html.escape(file_path)}:{line}
                </a>
            </td>
        </tr>""")

        return "\n".join(rows)

    def _generate_embedded_data(self, requirements: list[GraphNode]) -> str:
        """Generate embedded JSON data for requirements."""
        data = {}
        for node in requirements:
            data[node.id] = {
                "id": node.id,
                "label": node.label,
                "level": node.content.get("level"),
                "status": node.content.get("status"),
                "hash": node.content.get("hash"),
                "source": {
                    "path": node.source.path if node.source else None,
                    "line": node.source.line if node.source else None,
                },
            }

        json_str = json.dumps(data, indent=2)
        return f"""
    <script type="application/json" id="requirement-content">
{json_str}
    </script>"""

    def _render_template(
        self,
        rows_html: str,
        embedded_data: str,
        embed_content: bool,
        req_count: int,
    ) -> str:
        """Render the complete HTML template."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Traceability Matrix</title>
    <style>
{self._get_styles()}
    </style>
</head>
<body>
    <header class="header">
        <h1>Traceability Matrix</h1>
        <div class="header-meta">
            <span class="version">v{self.version}</span>
            <span class="timestamp">{timestamp}</span>
            <span class="count">{req_count} requirements</span>
        </div>
    </header>

    <main class="main-content">
        <div class="table-container">
            <table class="trace-table">
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Level</th>
                        <th>Title</th>
                        <th>Status</th>
                        <th>Implements</th>
                        <th>Source</th>
                    </tr>
                </thead>
                <tbody>
{rows_html}
                </tbody>
            </table>
        </div>
    </main>

    <footer class="footer">
        <p>Generated by elspais</p>
    </footer>
{embedded_data}
    <script>
{self._get_scripts()}
    </script>
</body>
</html>"""

    def _get_styles(self) -> str:
        """Return CSS styles for the report."""
        return """
        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.5;
            color: #333;
            background: #f5f5f5;
        }

        .header {
            background: #2c3e50;
            color: white;
            padding: 1rem 2rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .header h1 {
            font-size: 1.5rem;
            font-weight: 500;
        }

        .header-meta {
            display: flex;
            gap: 1rem;
            font-size: 0.875rem;
            opacity: 0.8;
        }

        .main-content {
            padding: 2rem;
        }

        .table-container {
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            overflow-x: auto;
        }

        .trace-table {
            width: 100%;
            border-collapse: collapse;
        }

        .trace-table th,
        .trace-table td {
            padding: 0.75rem 1rem;
            text-align: left;
            border-bottom: 1px solid #e9ecef;
        }

        .trace-table th {
            background: #f8f9fa;
            font-weight: 600;
            color: #495057;
            position: sticky;
            top: 0;
        }

        .trace-table tr:hover {
            background: #f8f9fa;
        }

        .req-id {
            font-family: 'Monaco', 'Menlo', monospace;
            font-size: 0.875rem;
            color: #0066cc;
        }

        .level-cell {
            font-weight: 600;
        }

        .level-prd { color: #8e44ad; }
        .level-ops { color: #2980b9; }
        .level-dev { color: #27ae60; }

        .status-active { color: #27ae60; }
        .status-deprecated { color: #e74c3c; }
        .status-draft { color: #f39c12; }

        .file-link {
            color: #6c757d;
            text-decoration: none;
            font-size: 0.875rem;
        }

        .file-link:hover {
            color: #0066cc;
            text-decoration: underline;
        }

        .footer {
            text-align: center;
            padding: 1rem;
            color: #6c757d;
            font-size: 0.875rem;
        }
"""

    def _get_scripts(self) -> str:
        """Return JavaScript for interactivity."""
        return """
        // Basic interactivity
        document.addEventListener('DOMContentLoaded', function() {
            // Click handler for rows
            document.querySelectorAll('.requirement-row').forEach(function(row) {
                row.addEventListener('click', function() {
                    var id = this.dataset.id;
                    console.log('Selected:', id);

                    // Toggle selected state
                    document.querySelectorAll('.requirement-row').forEach(function(r) {
                        r.classList.remove('selected');
                    });
                    this.classList.add('selected');
                });
            });
        });
"""


__all__ = ["HTMLGenerator"]
