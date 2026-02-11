# Validates REQ-CUR879-G, REQ-CUR879-H, REQ-CUR879-I
"""Tests for elspais validate --export and --json flags (CUR-879)."""

import argparse
import json
import os
import subprocess

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
B. The system SHALL do something else.

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


class TestValidateExport:
    """Tests for validate --export flag."""

    def test_REQ_CUR879_G_export_outputs_requirement_dict(self, spec_repo, capsys):
        """REQ-CUR879-G: --export outputs requirements as JSON dict keyed by ID."""
        from elspais.commands.validate import run

        args = argparse.Namespace(
            spec_dir=spec_repo / "spec",
            config=spec_repo / ".elspais.toml",
            export=True,
            fix=False,
            dry_run=False,
            skip_rule=None,
            json=False,
            quiet=False,
            mode="combined",
        )

        result = run(args)

        assert result == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)

        # Should be a dict keyed by requirement ID
        assert isinstance(data, dict)
        assert "REQ-p00001" in data

        # Should have expected fields
        req = data["REQ-p00001"]
        assert "title" in req
        assert "level" in req
        assert "status" in req
        assert "assertions" in req

    def test_REQ_CUR879_H_export_includes_hash_and_file(self, spec_repo, capsys):
        """REQ-CUR879-H: --export includes hash and file path."""
        from elspais.commands.validate import run

        args = argparse.Namespace(
            spec_dir=spec_repo / "spec",
            config=spec_repo / ".elspais.toml",
            export=True,
            fix=False,
            dry_run=False,
            skip_rule=None,
            json=False,
            quiet=False,
            mode="combined",
        )

        result = run(args)

        assert result == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        req = data["REQ-p00001"]

        assert "hash" in req
        assert "file" in req
        assert "prd-test.md" in req["file"]


class TestValidateJsonStillWorks:
    """Tests that --json still outputs validation results."""

    def test_REQ_CUR879_I_json_still_outputs_validation_results(self, spec_repo, capsys):
        """REQ-CUR879-I: --json outputs validation results, not export format."""
        from elspais.commands.validate import run

        args = argparse.Namespace(
            spec_dir=spec_repo / "spec",
            config=spec_repo / ".elspais.toml",
            export=False,
            fix=False,
            dry_run=False,
            skip_rule=None,
            json=True,
            quiet=False,
            mode="combined",
        )

        result = run(args)

        assert result == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)

        # Should be validation results format (not a dict keyed by ID)
        assert isinstance(data, dict)
        assert "valid" in data
        assert "errors" in data
        assert "warnings" in data
        assert "requirements_count" in data
