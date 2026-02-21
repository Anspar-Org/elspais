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
