# Verifies: REQ-d00132-A, REQ-d00231-E
"""Tests that MCP ``save_mutations`` reports a failure when changelog author
cannot be resolved for an Active mutation.

Validates REQ-d00132-A (render-based save reports errors rather than
silently dropping data) and REQ-d00231-E (author identity resolved
server-side, never from client input).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from elspais.config import get_config
from elspais.graph import NodeKind
from elspais.graph.factory import build_graph
from elspais.mcp.server import _add_changelog_for_active_mutations


def _make_project(tmp_path: Path) -> tuple[Path, Path]:
    """Create a minimal project with an Active requirement."""
    config_path = tmp_path / ".elspais.toml"
    config_path.write_text(
        'version = 3\n[project]\nname = "test"\nnamespace = "REQ"\n'
        "[scanning.spec]\n"
        'directories = ["spec"]\n'
        "[changelog]\n"
        "hash_current = true\n"
    )
    spec_dir = tmp_path / "spec"
    spec_dir.mkdir()
    req_file = spec_dir / "requirements.md"
    req_file.write_text(
        "# REQ-d00001: Test Req\n"
        "\n"
        "**Level**: DEV | **Status**: Active | **Implements**: -\n"
        "\n"
        "## Assertions\n"
        "\n"
        "A. The system SHALL do X.\n"
        "\n"
        "*End* *Test Req* | **Hash**: 00000000\n"
        "---\n"
    )
    return tmp_path, config_path


class TestSaveMutationsFailsWhenAuthorMissing:
    """``_add_changelog_for_active_mutations`` must surface an error
    (instead of silently dropping the changelog entry) when the configured
    changelog author identity is unresolvable for an Active mutation.
    """

    def test_save_mutations_returns_error_when_author_unresolvable(self, tmp_path: Path):
        from elspais.utilities.changelog_author import AuthorResolutionError

        project, config_path = _make_project(tmp_path)
        graph = build_graph(
            spec_dirs=[project / "spec"],
            config_path=config_path,
            repo_root=project,
            scan_code=False,
            scan_tests=False,
        )

        # Mutate an Active requirement so save_mutations would need a
        # changelog entry.
        node = next(n for n in graph.nodes_by_kind(NodeKind.REQUIREMENT) if n.id == "REQ-d00001")
        graph.update_title(node.id, "Updated Title")

        config = get_config(config_path)

        spec_file = project / "spec" / "requirements.md"
        before = spec_file.read_text()

        with patch(
            "elspais.utilities.changelog_author.resolve_changelog_author",
            side_effect=AuthorResolutionError(missing=["author_name"]),
        ):
            result = _add_changelog_for_active_mutations(graph, project, config, "Updated title")

        # _add_changelog_for_active_mutations must now return a dict that
        # the save_mutations caller can propagate as success=False.
        assert isinstance(
            result, dict
        ), f"Expected dict result on author failure, got: {type(result).__name__}"
        assert (
            result.get("success") is False
        ), f"Expected success=False on author resolution failure. Got: {result!r}"
        error_msg = result.get("error", "") or ""
        assert (
            "author_name" in error_msg
        ), f"Error message should name the missing field. Got: {error_msg!r}"

        # No changelog section should have been added on disk.
        after = spec_file.read_text()
        assert "## Changelog" not in after, (
            "Spec file should not have gained a Changelog section when the " "author lookup failed."
        )
        assert after == before, "Spec file content should be unchanged on failure"
