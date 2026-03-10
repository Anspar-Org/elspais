"""E2E tests for viewer git sync feature."""

import os
import subprocess

import pytest

from elspais.utilities.git import (
    commit_and_push_spec_files,
    create_and_switch_branch,
    git_status_summary,
)


@pytest.mark.e2e
class TestViewerGitSyncWorkflow:
    """Full workflow: main -> create branch -> edit -> commit.

    Validates REQ-p00004-C, REQ-p00004-D, REQ-p00004-E:
    """

    def test_REQ_p00004_CDE_full_workflow_no_remote(self, tmp_path):
        """Complete git sync flow without a remote (push skipped)."""
        env = {
            **os.environ,
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@test.com",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@test.com",
        }
        # Init repo on main
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, env=env)
        subprocess.run(
            ["git", "checkout", "-b", "main"], cwd=tmp_path, capture_output=True, env=env
        )
        (tmp_path / "spec").mkdir()
        (tmp_path / "spec" / "prd.md").write_text("# REQ-p00001 Original\n")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True, env=env)
        subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True, env=env)

        # 1: Status shows main + clean
        status = git_status_summary(tmp_path)
        assert status["is_main"] is True
        assert status["dirty_spec_files"] == []

        # 2: Dirty a spec file
        (tmp_path / "spec" / "prd.md").write_text("# REQ-p00001 Modified\n")
        status = git_status_summary(tmp_path)
        assert status["dirty_spec_files"] == ["spec/prd.md"]

        # 3: Create branch (carries dirty files)
        result = create_and_switch_branch(tmp_path, "edit-prd")
        assert result["success"] is True
        assert (tmp_path / "spec" / "prd.md").read_text() == "# REQ-p00001 Modified\n"

        # 4: Verify branch switched
        status = git_status_summary(tmp_path)
        assert status["branch"] == "edit-prd"
        assert status["is_main"] is False

        # 5: Commit (no push)
        result = commit_and_push_spec_files(tmp_path, message="Update PRD", push=False)
        assert result["success"] is True
        assert "spec/prd.md" in result["files_committed"]

        # 6: Status clean after commit
        status = git_status_summary(tmp_path)
        assert status["dirty_spec_files"] == []
