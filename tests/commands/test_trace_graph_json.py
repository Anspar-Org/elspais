# Validates REQ-CUR879-J
"""Tests for elspais trace --graph-json with git metrics (CUR-879)."""

import argparse
import json
import os
import subprocess
from unittest.mock import patch

import pytest


def _clean_git_env() -> dict[str, str]:
    """Return environment with GIT_DIR/GIT_WORK_TREE removed for test isolation."""
    env = os.environ.copy()
    env.pop("GIT_DIR", None)
    env.pop("GIT_WORK_TREE", None)
    return env


@pytest.fixture
def spec_repo(tmp_path):
    """Create a minimal spec repo with requirements."""
    env = _clean_git_env()

    # Initialize git repo
    subprocess.run(["git", "init"], cwd=tmp_path, env=env, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        check=True,
    )

    # Create elspais config
    config_file = tmp_path / ".elspais.toml"
    config_file.write_text(
        """
[project]
name = "test-project"

[patterns]
prefix = "REQ"
"""
    )

    # Create spec directory with a requirement
    spec_dir = tmp_path / "spec"
    spec_dir.mkdir()

    spec_file = spec_dir / "prd-test.md"
    spec_file.write_text(
        """# Test Requirements

## REQ-p00001: Test Requirement

**Level**: PRD | **Status**: Active | **Implements**: -

Some intro text.

## Assertions

A. The system SHALL do something.

*End* *Test Requirement* | **Hash**: abcd1234

---
""",
        encoding="utf-8",
    )

    # Initial commit
    subprocess.run(["git", "add", "."], cwd=tmp_path, env=env, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        check=True,
    )

    return tmp_path


class TestTraceGraphJsonGitMetrics:
    """Tests for trace --graph-json including git metrics."""

    def test_REQ_CUR879_J_graph_json_includes_git_metrics(self, spec_repo, capsys):
        """REQ-CUR879-J: --graph-json calls annotate_graph_git_state before serialization."""
        from elspais.commands.trace import run
        from elspais.utilities.git import GitChangeInfo

        # Mock git changes - use the absolute path that the parser produces
        spec_file = str(spec_repo / "spec" / "prd-test.md")
        mock_git_info = GitChangeInfo(
            modified_files={spec_file},
            untracked_files=set(),
            branch_changed_files=set(),
        )

        args = argparse.Namespace(
            spec_dir=spec_repo / "spec",
            config=spec_repo / ".elspais.toml",
            graph_json=True,
            output=None,
            view=False,
            format="markdown",
            quiet=False,
            mode="core",
        )

        with patch("elspais.utilities.git.get_git_changes", return_value=mock_git_info):
            result = run(args)

        assert result == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)

        # Find the requirement node in the graph
        assert "nodes" in data
        req_node = None
        for node_id, node_data in data["nodes"].items():
            if node_id == "REQ-p00001":
                req_node = node_data
                break

        assert req_node is not None, "REQ-p00001 not found in graph-json output"

        # Should have metrics with git state
        assert "metrics" in req_node
        metrics = req_node["metrics"]
        assert metrics.get("is_uncommitted") is True
        assert metrics.get("is_modified") is True
