# Verifies: REQ-p00004-A
"""Tests for MCP save_mutations changelog enforcement."""

from pathlib import Path
from unittest.mock import patch

from elspais.config import get_config
from elspais.graph import NodeKind
from elspais.graph.factory import build_graph
from elspais.mcp.server import (
    _add_changelog_for_active_mutations,
    _get_active_mutated_reqs,
)


def _make_project(tmp_path: Path) -> tuple[Path, Path]:
    """Create a minimal project with an Active requirement."""
    config_path = tmp_path / ".elspais.toml"
    config_path.write_text(
        '[project]\nname = "test"\n'
        "[patterns]\n"
        'prefix = "REQ"\n'
        "[changelog]\n"
        "hash_current = true\n"
    )
    spec_dir = tmp_path / "spec"
    spec_dir.mkdir()
    req_file = spec_dir / "requirements.md"
    req_file.write_text(
        "# REQ-d00001: Test Req\n"
        "\n"
        "**Level**: DEV | **Status**: Active"
        " | **Implements**: -\n"
        "\n"
        "## Assertions\n"
        "\n"
        "A. The system SHALL do X.\n"
        "\n"
        "*End* *Test Req* | **Hash**: 00000000\n"
        "---\n"
    )
    return tmp_path, config_path


MOCK_AUTHOR = {"name": "Test User", "id": "test@test.org"}


class TestMcpChangelogEnforcement:
    """Tests for MCP save_mutations changelog enforcement.

    Validates REQ-p00004-A: changelog message required for Active
    requirement mutations via MCP.
    """

    def test_REQ_p00004_A_detects_active_mutated_reqs(self, tmp_path: Path):
        """Mutating an Active req's title should flag it."""
        project, config_path = _make_project(tmp_path)
        graph = build_graph(
            spec_dirs=[project / "spec"],
            config_path=config_path,
            repo_root=project,
            scan_code=False,
            scan_tests=False,
        )

        # Mutate the title of the Active requirement
        node = next(n for n in graph.nodes_by_kind(NodeKind.REQUIREMENT) if n.id == "REQ-d00001")
        graph.update_title(node.id, "Updated Title")

        active = _get_active_mutated_reqs(graph)
        assert "REQ-d00001" in active

    @patch(
        "elspais.utilities.git.get_author_info",
        return_value=MOCK_AUTHOR,
    )
    def test_REQ_p00004_A_adds_changelog_after_save(self, mock_author, tmp_path: Path):
        """Changelog entry should be added for Active mutations."""
        project, config_path = _make_project(tmp_path)
        graph = build_graph(
            spec_dirs=[project / "spec"],
            config_path=config_path,
            repo_root=project,
            scan_code=False,
            scan_tests=False,
        )

        # Mutate
        graph.update_title("REQ-d00001", "Updated Title")

        config = get_config(config_path)
        _add_changelog_for_active_mutations(graph, project, config, "Updated title")

        content = (project / "spec" / "requirements.md").read_text()
        assert "## Changelog" in content
        assert "Updated title" in content
        assert "Test User" in content
