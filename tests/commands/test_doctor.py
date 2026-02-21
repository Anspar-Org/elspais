# Implements: REQ-p00005-E
"""Tests for elspais doctor command.

Validates REQ-p00005-E: clear config errors for invalid associate paths.
Validates REQ-p00001-A: CLI validation of requirement documents.
"""
from __future__ import annotations


class TestDoctorConfigChecks:
    """Validates REQ-p00001-A: config checks produce lay-person messages."""

    def test_REQ_p00001_A_config_exists_found(self, tmp_path):
        from elspais.commands.doctor import check_config_exists

        config_path = tmp_path / ".elspais.toml"
        config_path.write_text('[patterns]\nid_template = "{prefix}-{type}{id}"')
        result = check_config_exists(config_path, tmp_path)
        assert result.passed is True
        assert result.category == "config"

    def test_REQ_p00001_A_config_exists_not_found(self, tmp_path):
        from elspais.commands.doctor import check_config_exists

        result = check_config_exists(None, tmp_path)
        assert result.passed is True
        assert "defaults" in result.message.lower() or "no config" in result.message.lower()

    def test_REQ_p00001_A_config_syntax_valid(self, tmp_path):
        from elspais.commands.doctor import check_config_syntax

        config_path = tmp_path / ".elspais.toml"
        config_path.write_text('[patterns]\nid_template = "REQ-{type}{id}"')
        result = check_config_syntax(config_path, tmp_path)
        assert result.passed is True

    def test_REQ_p00001_A_config_syntax_invalid(self, tmp_path):
        from elspais.commands.doctor import check_config_syntax

        config_path = tmp_path / ".elspais.toml"
        config_path.write_text("invalid [[ toml content")
        result = check_config_syntax(config_path, tmp_path)
        assert result.passed is False
        assert "formatting error" in result.message.lower()

    def test_REQ_p00001_A_run_config_checks_returns_list(self, tmp_path):
        from elspais.commands.doctor import run_config_checks
        from elspais.config import ConfigLoader

        config = ConfigLoader.from_dict(
            {
                "patterns": {"id_template": "{prefix}-{type}{id}", "types": {"prd": {"level": 1}}},
                "spec": {"directories": ["spec"]},
                "rules": {"hierarchy": {}},
            }
        )
        results = run_config_checks(None, config, tmp_path)
        assert isinstance(results, list)
        assert all(r.category == "config" for r in results)


class TestDoctorWorktreeCheck:
    """Validates REQ-p00005-E: worktree environment detection."""

    def test_REQ_p00005_E_normal_repo(self, tmp_path):
        from elspais.commands.doctor import check_worktree_status

        git_root = tmp_path
        canonical_root = tmp_path  # same = not a worktree
        result = check_worktree_status(git_root, canonical_root)
        assert result.passed is True
        assert result.severity == "info"
        assert "worktree" not in result.message.lower() or "not" in result.message.lower()

    def test_REQ_p00005_E_in_worktree(self, tmp_path):
        from elspais.commands.doctor import check_worktree_status

        git_root = tmp_path / "worktrees" / "feature-x"
        canonical_root = tmp_path / "main-repo"
        result = check_worktree_status(git_root, canonical_root)
        assert result.passed is True
        assert result.severity == "info"
        assert "worktree" in result.message.lower()
        assert str(canonical_root) in result.message

    def test_REQ_p00005_E_no_git(self):
        from elspais.commands.doctor import check_worktree_status

        result = check_worktree_status(None, None)
        assert result.passed is True
        assert result.severity == "info"


class TestDoctorAssociateChecks:
    """Validates REQ-p00005-E: clear errors for invalid associate paths."""

    def test_REQ_p00005_E_no_associates_configured(self):
        from elspais.commands.doctor import check_associate_paths

        config = {}
        result = check_associate_paths(config, None)
        assert result.passed is True

    def test_REQ_p00005_E_associate_path_exists(self, tmp_path):
        from elspais.commands.doctor import check_associate_paths

        assoc_dir = tmp_path / "callisto"
        assoc_dir.mkdir()
        (assoc_dir / ".elspais.toml").write_text(
            '[project]\ntype = "associated"\n[associated]\nprefix = "CAL"'
        )
        config = {"associates": {"paths": [str(assoc_dir)]}}
        result = check_associate_paths(config, None)
        assert result.passed is True

    def test_REQ_p00005_E_associate_path_missing(self, tmp_path):
        from elspais.commands.doctor import check_associate_paths

        config = {"associates": {"paths": [str(tmp_path / "nonexistent")]}}
        result = check_associate_paths(config, None)
        assert result.passed is False
        assert "not found" in result.message.lower()

    def test_REQ_p00005_E_associate_invalid_config(self, tmp_path):
        from elspais.commands.doctor import check_associate_configs

        assoc_dir = tmp_path / "callisto"
        assoc_dir.mkdir()
        # No .elspais.toml = invalid
        config = {"associates": {"paths": [str(assoc_dir)]}}
        result = check_associate_configs(config, None)
        assert result.passed is False
        assert "invalid" in result.message.lower() or "configuration" in result.message.lower()


class TestDoctorLocalConfigCheck:
    """Validates REQ-p00001-A: local config file presence check."""

    def test_REQ_p00001_A_local_toml_exists(self, tmp_path):
        from elspais.commands.doctor import check_local_toml_exists

        (tmp_path / ".elspais.local.toml").write_text("[local]")
        result = check_local_toml_exists(tmp_path)
        assert result.passed is True

    def test_REQ_p00001_A_local_toml_missing(self, tmp_path):
        from elspais.commands.doctor import check_local_toml_exists

        result = check_local_toml_exists(tmp_path)
        assert result.passed is True  # info, not error
        assert result.severity == "info"
        assert ".elspais.local.toml" in result.message


class TestDoctorCrossRepoCheck:
    """Validates REQ-p00005-E: warn about cross-repo paths in committed config."""

    def test_REQ_p00005_E_no_cross_repo_paths(self, tmp_path):
        from elspais.commands.doctor import check_cross_repo_in_committed_config

        config_path = tmp_path / ".elspais.toml"
        config_path.write_text('[spec]\ndirectories = ["spec"]')
        result = check_cross_repo_in_committed_config(config_path)
        assert result.passed is True

    def test_REQ_p00005_E_cross_repo_path_in_committed(self, tmp_path):
        from elspais.commands.doctor import check_cross_repo_in_committed_config

        config_path = tmp_path / ".elspais.toml"
        config_path.write_text('[spec]\ndirectories = ["spec", "../../callisto/spec"]')
        result = check_cross_repo_in_committed_config(config_path)
        assert result.passed is False
        assert ".elspais.local.toml" in result.message
