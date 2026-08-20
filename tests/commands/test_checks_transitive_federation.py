# Verifies: REQ-d00202-D, REQ-d00202-E, REQ-d00202-I, REQ-d00203-B, REQ-d00203-C
"""The health and doctor associate checks report on the whole federation.

Associates carry declarations of their own, so the set of repositories
the tool builds is wider than the set the invoking repository names.
These tests hold the reporting surfaces to that wider set: a repository
reached through a chain is counted when it is healthy and named -- with
its path and the reason -- when it is not.
"""

from __future__ import annotations

from pathlib import Path

from elspais.commands.doctor import check_associate_configs, check_associate_paths
from elspais.commands.health import check_associate_paths as health_check_associate_paths
from elspais.config import load_config
from tests.federation_repos import make_repo


def _chain(tmp_path: Path, *, leaf_config: str | None = None, leaf_path: str = "../leaf") -> Path:
    """Build root -> mid -> leaf and return the root repo."""
    make_repo(tmp_path, "leaf", config_text=leaf_config)
    make_repo(tmp_path, "mid", associates={"leaf": leaf_path})
    return make_repo(tmp_path, "root", associates={"mid": "../mid"})


class TestTransitiveMembersAreReported:
    def test_REQ_d00202_D_doctor_paths_count_the_whole_federation(self, tmp_path):
        root = _chain(tmp_path)
        result = check_associate_paths(load_config(root / ".elspais.toml"), root)

        assert result.passed is True
        found = result.details["found"]
        assert len(found) == 2
        assert str((tmp_path / "leaf").resolve()) in found

    def test_REQ_d00203_B_doctor_configs_validate_the_whole_federation(self, tmp_path):
        root = _chain(tmp_path)
        result = check_associate_configs(load_config(root / ".elspais.toml"), root)

        assert result.passed is True
        assert any(entry.startswith("leaf ") for entry in result.details["valid"])

    def test_REQ_d00202_D_health_paths_count_the_whole_federation(self, tmp_path):
        root = _chain(tmp_path)
        result = health_check_associate_paths(load_config(root / ".elspais.toml"), root)

        assert result.passed is True
        assert "2" in result.message


class TestUnloadableTransitiveMemberIsNamed:
    """A repository the root never names still has to be visible when broken."""

    BROKEN = 'version = 3\n[project\nname = "leaf"\n'

    def test_REQ_d00202_I_doctor_reports_path_and_reason(self, tmp_path):
        root = _chain(tmp_path, leaf_config=self.BROKEN)
        result = check_associate_configs(load_config(root / ".elspais.toml"), root)

        assert result.passed is False
        assert str((tmp_path / "leaf").resolve()) in result.message
        assert "leaf" in result.message
        assert "could not be loaded" in result.message

    def test_REQ_d00202_I_health_reports_path_and_reason(self, tmp_path):
        root = _chain(tmp_path, leaf_config=self.BROKEN)
        result = health_check_associate_paths(load_config(root / ".elspais.toml"), root)

        assert result.passed is False
        messages = [f.message for f in result.findings]
        assert any(
            str((tmp_path / "leaf").resolve()) in m and "could not be loaded" in m for m in messages
        )

    def test_REQ_d00203_C_missing_transitive_path_soft_fails(self, tmp_path):
        root = _chain(tmp_path, leaf_path="../nowhere")
        doctor_result = check_associate_paths(load_config(root / ".elspais.toml"), root)
        health_result = health_check_associate_paths(load_config(root / ".elspais.toml"), root)

        assert doctor_result.passed is False
        assert str((tmp_path / "nowhere").resolve()) in doctor_result.message
        assert health_result.passed is False
        assert any(
            str((tmp_path / "nowhere").resolve()) in f.message for f in health_result.findings
        )


class TestUnresolvableFederationIsReported:
    """A cycle stops the walk; it must not stop the diagnostic."""

    def test_REQ_d00202_E_cycle_becomes_a_finding(self, tmp_path):
        make_repo(tmp_path, "beta", associates={"alpha": "../alpha"})
        root = make_repo(tmp_path, "alpha", associates={"beta": "../beta"})
        config = load_config(root / ".elspais.toml")

        doctor_result = check_associate_paths(config, root)
        health_result = health_check_associate_paths(config, root)

        assert doctor_result.passed is False
        assert "cycle" in doctor_result.message.lower()
        assert health_result.passed is False
        assert any("cycle" in f.message.lower() for f in health_result.findings)
