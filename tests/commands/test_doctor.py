# Verifies: REQ-p00005-E
"""Tests for elspais doctor command.

Validates REQ-p00005-E: clear config errors for invalid associate paths.
Validates REQ-p00001-A: CLI validation of requirement documents.
"""

from __future__ import annotations

import argparse


class TestDoctorConfigChecks:
    """Validates REQ-p00001-A: config checks produce lay-person messages."""

    # Verifies: REQ-p00001-A
    def test_REQ_p00001_A_config_exists_found(self, tmp_path):
        from elspais.commands.doctor import check_config_exists

        config_path = tmp_path / ".elspais.toml"
        config_path.write_text('version = 5\n[project]\nnamespace = "REQ"\n')
        result = check_config_exists(config_path, tmp_path)
        assert result.passed is True
        assert result.category == "config"

    # Verifies: REQ-p00001-A
    def test_REQ_p00001_A_config_exists_not_found(self, tmp_path):
        from elspais.commands.doctor import check_config_exists

        result = check_config_exists(None, tmp_path)
        assert result.passed is True
        assert "defaults" in result.message.lower() or "no config" in result.message.lower()

    # Verifies: REQ-p00001-A
    def test_REQ_p00001_A_config_syntax_valid(self, tmp_path):
        from elspais.commands.doctor import check_config_syntax

        config_path = tmp_path / ".elspais.toml"
        config_path.write_text('version = 5\n[project]\nnamespace = "REQ"\n')
        result = check_config_syntax(config_path, tmp_path)
        assert result.passed is True

    # Verifies: REQ-p00001-A
    def test_REQ_p00001_A_config_syntax_invalid(self, tmp_path):
        from elspais.commands.doctor import check_config_syntax

        config_path = tmp_path / ".elspais.toml"
        config_path.write_text("invalid [[ toml content")
        result = check_config_syntax(config_path, tmp_path)
        assert result.passed is False
        assert "formatting error" in result.message.lower()

    # Verifies: REQ-p00001-A
    def test_REQ_p00001_A_run_config_checks_returns_list(self, tmp_path):
        from elspais.commands.doctor import run_config_checks
        from elspais.config import _merge_configs, config_defaults

        config = _merge_configs(
            config_defaults(),
            {
                "version": 3,
                "levels": {"prd": {"rank": 1, "letter": "p", "implements": ["prd"]}},
                "scanning": {"spec": {"directories": ["spec"]}},
            },
        )
        results = run_config_checks(None, config, tmp_path)
        assert isinstance(results, list)
        assert len(results) >= 5, f"Expected at least 5 config checks, got {len(results)}"
        assert all(r.category == "config" for r in results)
        check_names = {r.name for r in results}
        assert "config.exists" in check_names
        assert "config.syntax" in check_names
        assert "config.required_fields" in check_names


class TestDoctorWorktreeCheck:
    """Validates REQ-p00005-E: worktree environment detection."""

    def test_REQ_p00005_E_normal_repo(self, tmp_path):
        from elspais.commands.doctor import check_worktree_status

        git_root = tmp_path
        result = check_worktree_status(git_root)
        assert result.passed is True
        assert result.severity == "info"
        assert "worktree" not in result.message.lower() or "not" in result.message.lower()

    def test_REQ_p00005_E_in_worktree(self, tmp_path):
        from elspais.commands.doctor import check_worktree_status

        git_root = tmp_path / "worktrees" / "feature-x"
        result = check_worktree_status(git_root)
        assert result.passed is True
        assert result.severity == "info"

    def test_REQ_p00005_E_no_git(self):
        from elspais.commands.doctor import check_worktree_status

        result = check_worktree_status(None)
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
            'version = 5\n[project]\nname = "callisto"\nnamespace = "CAL"\n'
        )
        config = {"associates": {"callisto": {"path": str(assoc_dir), "namespace": "CAL"}}}
        result = check_associate_paths(config, None)
        assert result.passed is True

    def test_REQ_p00005_E_associate_path_missing(self, tmp_path):
        from elspais.commands.doctor import check_associate_paths

        config = {
            "associates": {"callisto": {"path": str(tmp_path / "nonexistent"), "namespace": "CAL"}}
        }
        result = check_associate_paths(config, None)
        assert result.passed is False
        assert "not found" in result.message.lower()

    def test_REQ_p00005_E_associate_invalid_config(self, tmp_path):
        from elspais.commands.doctor import check_associate_configs

        assoc_dir = tmp_path / "callisto"
        assoc_dir.mkdir()
        # No .elspais.toml = invalid
        config = {"associates": {"callisto": {"path": str(assoc_dir), "namespace": "CAL"}}}
        result = check_associate_configs(config, None)
        assert result.passed is False
        assert "invalid" in result.message.lower() or "configuration" in result.message.lower()


class TestDoctorLocalConfigCheck:
    """Validates REQ-p00001-A: local config file presence check."""

    # Verifies: REQ-p00001-A
    def test_REQ_p00001_A_local_toml_exists(self, tmp_path):
        from elspais.commands.doctor import check_local_toml_exists

        (tmp_path / ".elspais.local.toml").write_text("[local]")
        result = check_local_toml_exists(tmp_path)
        assert result.passed is True

    # Verifies: REQ-p00001-A
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
        config_path.write_text('[scanning.spec]\ndirectories = ["spec"]')
        result = check_cross_repo_in_committed_config(config_path)
        assert result.passed is True

    def test_REQ_p00005_E_cross_repo_path_in_committed(self, tmp_path):
        from elspais.commands.doctor import check_cross_repo_in_committed_config

        config_path = tmp_path / ".elspais.toml"
        config_path.write_text('[scanning.spec]\ndirectories = ["spec", "../../callisto/spec"]')
        result = check_cross_repo_in_committed_config(config_path)
        assert result.passed is False
        assert ".elspais.local.toml" in result.message


class TestDoctorRun:
    """Validates REQ-p00001-A: doctor command end-to-end."""

    # Verifies: REQ-p00001-A
    def test_REQ_p00001_A_run_returns_zero_healthy(self, tmp_path, monkeypatch):
        from elspais.commands.doctor import run

        monkeypatch.chdir(tmp_path)
        config_path = tmp_path / ".elspais.toml"
        config_path.write_text(
            'version = 5\n[project]\nname = "test"\nnamespace = "REQ"\n\n'
            '[levels.prd]\nrank = 1\nletter = "p"\nimplements = ["prd"]\n\n'
            "[id-patterns]\n"
            'canonical = "{namespace}-{level.letter}{component}"\n\n'
            "[id-patterns.component]\n"
            'style = "numeric"\ndigits = 5\n\n'
            '[scanning.spec]\ndirectories = ["spec"]\n'
        )
        (tmp_path / "spec").mkdir()

        args = argparse.Namespace(
            config=str(config_path),
            format="text",
            verbose=False,
        )
        result = run(args)
        assert result == 0

    # Verifies: REQ-p00001-A
    def test_REQ_p00001_A_run_json_output(self, tmp_path, monkeypatch, capsys):
        import json as json_mod

        from elspais.commands.doctor import run

        monkeypatch.chdir(tmp_path)
        args = argparse.Namespace(
            config=None,
            format="json",
            verbose=False,
        )
        run(args)
        output = capsys.readouterr().out
        data = json_mod.loads(output)
        assert "checks" in data

    # Verifies: REQ-p00001-A
    def test_REQ_p00001_A_run_nonzero_on_errors(self, tmp_path, monkeypatch):
        from elspais.commands.doctor import run

        monkeypatch.chdir(tmp_path)
        config_path = tmp_path / ".elspais.toml"
        config_path.write_text("invalid [[ toml")

        args = argparse.Namespace(
            config=str(config_path),
            format="text",
            verbose=False,
        )
        result = run(args)
        assert result == 1


class TestMcpAddressCheck:
    """Whether a client launched here would reach this working tree.

    A client that resolves an address once cannot tell an address naming
    another tree from one naming its own with nothing serving it yet:
    both simply fail to connect. Only the tool holds both facts.
    """

    # Verifies: REQ-o00076-M
    def test_REQ_o00076_M_an_address_naming_another_tree_is_reported(self, tmp_path, monkeypatch):
        """Validates REQ-o00076-M: an address carried over from a
        different working tree connects to that tree's process or to
        nothing, and either way the client is not reading the graph it
        is working in. The tool can see the disagreement, so it says so.
        """
        from elspais.commands.doctor import check_mcp_address

        monkeypatch.setenv("ELSPAIS_MCP_URL", "http://127.0.0.1:40689/mcp")
        monkeypatch.setattr("elspais.mcp.daemon.reserved_port", lambda root: 39709)
        monkeypatch.setattr("elspais.mcp.daemon.get_daemon_info", lambda root: None)

        check = check_mcp_address(tmp_path, {})

        assert not check.passed
        assert "40689" in check.message and "39709" in check.message

    # Verifies: REQ-o00076-M
    def test_REQ_o00076_M_an_address_reaching_this_tree_is_not_reported(
        self, tmp_path, monkeypatch
    ):
        """Validates REQ-o00076-M: the report is about disagreement. A
        client pointed at the tree it is working in is the arrangement
        the tool is asking for, and reporting it would train the reader
        to ignore the check.
        """
        from elspais.commands.doctor import check_mcp_address

        monkeypatch.setenv("ELSPAIS_MCP_URL", "http://127.0.0.1:39709/mcp")
        monkeypatch.setattr("elspais.mcp.daemon.reserved_port", lambda root: 39709)
        monkeypatch.setattr("elspais.mcp.daemon.get_daemon_info", lambda root: None)

        assert check_mcp_address(tmp_path, {}).passed

    # Verifies: REQ-o00076-M
    def test_REQ_o00076_M_a_shell_with_no_address_is_not_a_fault(self, tmp_path, monkeypatch):
        """Validates REQ-o00076-M: the assertion is about an address a
        client is configured to use. A shell that runs only the CLI sets
        none and needs none, so there is no disagreement to report.
        """
        from elspais.commands.doctor import check_mcp_address

        monkeypatch.delenv("ELSPAIS_MCP_URL", raising=False)
        monkeypatch.setattr("elspais.mcp.daemon.reserved_port", lambda root: 39709)

        assert check_mcp_address(tmp_path, {}).passed

    # Verifies: REQ-o00076-M
    def test_REQ_o00076_M_an_associate_in_another_tree_is_not_a_disagreement(
        self, tmp_path, monkeypatch
    ):
        """Validates REQ-o00076-M: the report is about where a client
        connects, not about which repositories a tree federates. A tree
        may properly declare an associate living in any other working
        tree, and doing so says nothing about its own clients -- a check
        that conflated the two would fire on a correct configuration.
        """
        from elspais.commands.doctor import check_mcp_address

        monkeypatch.setenv("ELSPAIS_MCP_URL", "http://127.0.0.1:39709/mcp")
        monkeypatch.setattr("elspais.mcp.daemon.reserved_port", lambda root: 39709)
        monkeypatch.setattr("elspais.mcp.daemon.get_daemon_info", lambda root: None)

        elsewhere = tmp_path / "other-repo-worktree"
        elsewhere.mkdir()
        config = {"associates": {"Other": {"path": str(elsewhere), "namespace": "OTHER"}}}

        assert check_mcp_address(tmp_path, config).passed


class TestMcpRegistrationCheck:
    """Whether a registration a client here reads names a fixed address.

    A registration is read in every working tree that shares it. An
    address written into one is the installing tree's answer offered to
    every reader, so it is wrong when written rather than stale later.
    """

    @staticmethod
    def _claude_config(tmp_path, servers=None, projects=None):
        import json

        path = tmp_path / "claude.json"
        path.write_text(json.dumps({"mcpServers": servers or {}, "projects": projects or {}}))
        return path

    # Verifies: REQ-o00076-M
    def test_REQ_o00076_M_a_literal_under_the_main_repo_key_is_reported(
        self, tmp_path, monkeypatch
    ):
        """Validates REQ-o00076-M: this is the condition that hides. A
        worktree reads its main repository's entry, so an address settled
        in one tree is served to every other tree of that repository, and
        the client holding it fails exactly as it would against an
        address nobody serves. The shell variable can be perfectly
        correct while this is wrong, so the check must not be satisfied
        by the variable agreeing.
        """
        from elspais.commands.doctor import check_mcp_registration

        worktree = tmp_path / "wt"
        worktree.mkdir()
        main = tmp_path / "main"
        main.mkdir()
        monkeypatch.setattr("elspais.commands.doctor._main_repo_root", lambda root: main)
        cfg = self._claude_config(
            tmp_path,
            projects={
                str(main): {
                    "mcpServers": {"elspais": {"type": "http", "url": "http://127.0.0.1:40689/mcp"}}
                }
            },
        )

        check = check_mcp_registration(worktree, {}, claude_config=cfg)

        assert not check.passed
        assert "40689" in check.message

    # Verifies: REQ-o00076-M
    def test_REQ_o00076_M_a_registration_naming_a_variable_is_not_reported(
        self, tmp_path, monkeypatch
    ):
        """Validates REQ-o00076-M: an address the reader resolves is the
        arrangement REQ-o00076-L asks for, and reporting it would leave
        no way to satisfy the check. Whether the reader supplies a value
        is a different question, asked elsewhere.
        """
        from elspais.commands.doctor import check_mcp_registration

        monkeypatch.setattr("elspais.commands.doctor._main_repo_root", lambda root: None)
        (tmp_path / ".mcp.json").write_text(
            '{"mcpServers": {"elspais": {"type": "http", "url": "${ELSPAIS_MCP_URL}"}}}'
        )
        cfg = self._claude_config(tmp_path)

        assert check_mcp_registration(tmp_path, {}, claude_config=cfg).passed

    # Verifies: REQ-o00076-M
    def test_REQ_o00076_M_a_command_registration_carries_no_address_to_judge(
        self, tmp_path, monkeypatch
    ):
        """Validates REQ-o00076-M: a stdio registration names a process
        the client starts, not somewhere to connect, so there is no
        address that could name the wrong tree. Reporting it would be
        reporting a different condition under this one's name.
        """
        from elspais.commands.doctor import check_mcp_registration

        monkeypatch.setattr("elspais.commands.doctor._main_repo_root", lambda root: None)
        cfg = self._claude_config(
            tmp_path,
            servers={"elspais": {"type": "stdio", "command": "elspais", "args": ["mcp", "serve"]}},
        )

        assert check_mcp_registration(tmp_path, {}, claude_config=cfg).passed

    # Verifies: REQ-o00076-M
    def test_REQ_o00076_M_every_literal_is_named_not_only_the_winning_one(
        self, tmp_path, monkeypatch
    ):
        """Validates REQ-o00076-M: which scope a client prefers is that
        client's rule and it changes. Every literal is wrong whichever
        wins, and the reader has to correct all of them, so reporting one
        would leave the others to be found later by the same silent
        failure.
        """
        from elspais.commands.doctor import check_mcp_registration

        monkeypatch.setattr("elspais.commands.doctor._main_repo_root", lambda root: None)
        (tmp_path / ".mcp.json").write_text(
            '{"mcpServers": {"elspais": {"type": "http", "url": "http://127.0.0.1:1111/mcp"}}}'
        )
        cfg = self._claude_config(
            tmp_path,
            servers={"elspais": {"type": "http", "url": "http://127.0.0.1:2222/mcp"}},
        )

        check = check_mcp_registration(tmp_path, {}, claude_config=cfg)

        assert not check.passed
        assert "1111" in check.message and "2222" in check.message

    # Verifies: REQ-o00076-M
    def test_REQ_o00076_M_an_absent_client_config_is_not_a_finding(self, tmp_path, monkeypatch):
        """Validates REQ-o00076-M: the condition is a registration that
        names an address, so having no registration at all cannot be it.
        A machine with no client installed must not be told its
        configuration is wrong.
        """
        from elspais.commands.doctor import check_mcp_registration

        monkeypatch.setattr("elspais.commands.doctor._main_repo_root", lambda root: None)

        check = check_mcp_registration(tmp_path, {}, claude_config=tmp_path / "does-not-exist.json")

        assert check.passed
