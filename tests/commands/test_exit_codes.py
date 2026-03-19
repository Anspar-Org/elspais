"""Tests for REQ-d00080: Diagnostic Command Exit Code Contract."""

import argparse


class TestDoctorExitCodes:
    """REQ-d00080-A: doctor SHALL exit non-zero on [!!] findings."""

    def test_REQ_d00080_A_invalid_project_type_exits_nonzero(self, tmp_path, monkeypatch):
        """doctor exits 1 when project.type is invalid."""
        from elspais.commands.doctor import run

        monkeypatch.chdir(tmp_path)
        config = tmp_path / ".elspais.toml"
        config.write_text(
            '[project]\ntype = "bogus"\n'
            '[patterns]\nid_template = "{prefix}-{type}{id}"\n'
            "[patterns.types.prd]\nlevel = 1\n"
            '[spec]\ndirectories = ["spec"]\n'
            "[rules]\nhierarchy = {}\n"
        )
        (tmp_path / "spec").mkdir()

        args = argparse.Namespace(
            config=str(config),
            json=False,
            verbose=False,
            canonical_root=None,
        )
        result = run(args)
        assert result == 1

    def test_REQ_d00080_A_missing_required_fields_exits_nonzero(self, tmp_path, monkeypatch):
        """doctor exits 1 when required config fields are missing."""
        from elspais.commands.doctor import run

        monkeypatch.chdir(tmp_path)
        config = tmp_path / ".elspais.toml"
        # Explicitly empty required sections to override defaults
        config.write_text(
            '[project]\nname = "test"\n'
            '[patterns]\nid_template = "{prefix}-{type}{id}"\n'
            "[patterns.types]\n"
            "[spec]\ndirectories = []\n"
            "[rules]\nhierarchy = {}\n"
        )
        (tmp_path / "spec").mkdir()

        args = argparse.Namespace(
            config=str(config),
            json=False,
            verbose=False,
            canonical_root=None,
        )
        result = run(args)
        assert result == 1

    def test_REQ_d00080_A_missing_associate_path_exits_nonzero(self, tmp_path, monkeypatch):
        """doctor exits 1 when configured associate path doesn't exist."""
        from elspais.commands.doctor import run

        monkeypatch.chdir(tmp_path)
        config = tmp_path / ".elspais.toml"
        config.write_text(
            '[patterns]\nid_template = "{prefix}-{type}{id}"\n'
            "[patterns.types.prd]\nlevel = 1\n"
            '[spec]\ndirectories = ["spec"]\n'
            "[rules]\nhierarchy = {}\n"
        )
        local_config = tmp_path / ".elspais.local.toml"
        local_config.write_text('[associates]\npaths = ["/nonexistent/sponsor"]\n')
        (tmp_path / "spec").mkdir()

        args = argparse.Namespace(
            config=str(config),
            json=False,
            verbose=False,
            canonical_root=tmp_path,
        )
        result = run(args)
        assert result == 1

    def test_REQ_d00080_A_healthy_config_exits_zero(self, tmp_path, monkeypatch):
        """doctor exits 0 on a well-configured project."""
        from elspais.commands.doctor import run

        monkeypatch.chdir(tmp_path)
        config = tmp_path / ".elspais.toml"
        config.write_text(
            '[patterns]\nid_template = "{prefix}-{type}{id}"\n'
            "[patterns.types.prd]\nlevel = 1\n"
            '[spec]\ndirectories = ["spec"]\n'
            "[rules]\nhierarchy = {}\n"
        )
        (tmp_path / "spec").mkdir()

        args = argparse.Namespace(
            config=str(config),
            json=False,
            verbose=False,
            canonical_root=None,
        )
        result = run(args)
        assert result == 0


class TestValidateExitCodes:
    """REQ-d00080-B: validate SHALL exit non-zero on zero requirements."""

    def test_REQ_d00080_B_zero_requirements_exits_nonzero(self, tmp_path, monkeypatch):
        """validate exits 1 when spec dir is configured but has zero requirements."""
        from elspais.commands.validate import run

        monkeypatch.chdir(tmp_path)
        config = tmp_path / ".elspais.toml"
        config.write_text(
            '[patterns]\nid_template = "{prefix}-{type}{id}"\n'
            "[patterns.types.prd]\nlevel = 1\n"
            '[spec]\ndirectories = ["spec"]\n'
            "[rules]\nhierarchy = {}\n"
        )
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        # Create an empty spec file (no requirements)
        (spec_dir / "empty.md").write_text("# No requirements here\n")

        args = argparse.Namespace(
            spec_dir=None,
            config=str(config),
            fix=False,
            dry_run=False,
            skip_rule=None,
            json=False,
            quiet=False,
            export=False,
            mode="core",
            canonical_root=None,
        )
        result = run(args)
        assert result == 1

    def test_REQ_d00080_B_zero_requirements_json_reports_error(self, tmp_path, monkeypatch, capsys):
        """validate JSON output includes zero-requirements error."""
        import json as json_mod

        from elspais.commands.validate import run

        monkeypatch.chdir(tmp_path)
        config = tmp_path / ".elspais.toml"
        config.write_text(
            '[patterns]\nid_template = "{prefix}-{type}{id}"\n'
            "[patterns.types.prd]\nlevel = 1\n"
            '[spec]\ndirectories = ["spec"]\n'
            "[rules]\nhierarchy = {}\n"
        )
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        (spec_dir / "empty.md").write_text("# No requirements here\n")

        args = argparse.Namespace(
            spec_dir=None,
            config=str(config),
            fix=False,
            dry_run=False,
            skip_rule=None,
            json=True,
            quiet=False,
            export=False,
            mode="core",
            canonical_root=None,
        )
        result = run(args)
        assert result == 1
        captured = capsys.readouterr()
        data = json_mod.loads(captured.out)
        assert data["valid"] is False
        assert any(e["rule"] == "config.no_requirements" for e in data["errors"])


class TestDoctorAssociatedSection:
    """REQ-d00080-D: doctor SHALL validate [associated] section for associated projects."""

    def test_REQ_d00080_D_missing_associated_section_exits_nonzero(self, tmp_path, monkeypatch):
        """doctor exits 1 when project.type=associated but [associated] section missing."""
        from elspais.commands.doctor import run

        monkeypatch.chdir(tmp_path)
        config = tmp_path / ".elspais.toml"
        config.write_text(
            '[project]\ntype = "associated"\n'
            '[patterns]\nid_template = "{prefix}-{type}{id}"\n'
            "[patterns.types.prd]\nlevel = 1\n"
            '[spec]\ndirectories = ["spec"]\n'
            "[rules]\nhierarchy = {}\n"
        )
        (tmp_path / "spec").mkdir()

        args = argparse.Namespace(
            config=str(config),
            json=False,
            verbose=False,
            canonical_root=None,
        )
        result = run(args)
        assert result == 1

    def test_REQ_d00080_D_empty_prefix_exits_nonzero(self, tmp_path, monkeypatch):
        """doctor exits 1 when [associated] section has empty prefix."""
        from elspais.commands.doctor import run

        monkeypatch.chdir(tmp_path)
        config = tmp_path / ".elspais.toml"
        config.write_text(
            '[project]\ntype = "associated"\n'
            '[associated]\nprefix = ""\n'
            '[patterns]\nid_template = "{prefix}-{type}{id}"\n'
            "[patterns.types.prd]\nlevel = 1\n"
            '[spec]\ndirectories = ["spec"]\n'
            "[rules]\nhierarchy = {}\n"
        )
        (tmp_path / "spec").mkdir()

        args = argparse.Namespace(
            config=str(config),
            json=False,
            verbose=False,
            canonical_root=None,
        )
        result = run(args)
        assert result == 1

    def test_REQ_d00080_D_check_function_valid(self):
        """check_config_associated_section passes with valid config."""
        from elspais.commands.doctor import check_config_associated_section

        raw = {
            "project": {"type": "associated"},
            "associated": {"prefix": "CAL"},
        }
        check = check_config_associated_section(raw)
        assert check.passed is True

    def test_REQ_d00080_D_check_function_missing_section(self):
        """check_config_associated_section fails with missing section."""
        from elspais.commands.doctor import check_config_associated_section

        raw = {"project": {"type": "associated"}}
        check = check_config_associated_section(raw)
        assert check.passed is False
        assert check.severity == "error"

    def test_REQ_d00080_D_check_function_empty_prefix(self):
        """check_config_associated_section fails with empty prefix."""
        from elspais.commands.doctor import check_config_associated_section

        raw = {
            "project": {"type": "associated"},
            "associated": {"prefix": ""},
        }
        check = check_config_associated_section(raw)
        assert check.passed is False

    def test_REQ_d00080_D_check_function_non_associated_skips(self):
        """check_config_associated_section passes for non-associated projects."""
        from elspais.commands.doctor import check_config_associated_section

        raw = {"project": {"type": "core"}}
        check = check_config_associated_section(raw)
        assert check.passed is True


class TestValidateAssociateCount:
    """REQ-d00080-E: validate SHALL exit non-zero when associates produce zero requirements."""

    def test_REQ_d00080_E_missing_associate_path_exits_nonzero(self, tmp_path, monkeypatch):
        """validate exits 1 when a configured associate path doesn't exist."""
        from elspais.commands.validate import run

        monkeypatch.chdir(tmp_path)
        config = tmp_path / ".elspais.toml"
        config.write_text(
            '[patterns]\nid_template = "{prefix}-{type}{id}"\n'
            "[patterns.types.prd]\nlevel = 1\n"
            '[spec]\ndirectories = ["spec"]\n'
            "[rules]\nhierarchy = {}\n"
        )
        local_config = tmp_path / ".elspais.local.toml"
        local_config.write_text('[associates]\npaths = ["/nonexistent/sponsor"]\n')
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        # Add a valid requirement so this isn't the zero-req check
        (spec_dir / "reqs.md").write_text(
            "# REQ-p00001: Test Requirement\n\n"
            "**Level**: PRD | **Status**: Active\n\n"
            "A. Some assertion.\n\n"
            "*End* *Test Requirement* | **Hash**: 00000000\n"
        )

        args = argparse.Namespace(
            spec_dir=None,
            config=str(config),
            fix=False,
            dry_run=False,
            skip_rule=None,
            json=False,
            quiet=False,
            export=False,
            mode="combined",
            canonical_root=tmp_path,
        )
        result = run(args)
        assert result == 1

    def test_REQ_d00080_E_empty_associate_spec_dir_exits_nonzero(self, tmp_path, monkeypatch):
        """validate exits 1 when associate has empty spec directory (zero requirements)."""
        from elspais.commands.validate import run

        monkeypatch.chdir(tmp_path)
        # Set up core project config
        config = tmp_path / ".elspais.toml"
        config.write_text(
            '[patterns]\nid_template = "{prefix}-{type}{id}"\n'
            "[patterns.types.prd]\nlevel = 1\n"
            '[spec]\ndirectories = ["spec"]\n'
            "[rules]\nhierarchy = {}\n"
        )
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        (spec_dir / "reqs.md").write_text(
            "# REQ-p00001: Test Requirement\n\n"
            "**Level**: PRD | **Status**: Active\n\n"
            "A. Some assertion.\n\n"
            "*End* *Test Requirement* | **Hash**: 00000000\n"
        )

        # Set up associate with valid config but empty spec directory
        assoc_dir = tmp_path / "associate"
        assoc_dir.mkdir()
        assoc_config = assoc_dir / ".elspais.toml"
        assoc_config.write_text(
            '[project]\nname = "test-assoc"\ntype = "associated"\n'
            '[associated]\nprefix = "ASC"\n'
            f'[core]\npath = "{tmp_path}"\n'
            '[patterns]\nid_template = "{prefix}-{type}{id}"\n'
            "[patterns.types.prd]\nlevel = 1\n"
            '[spec]\ndirectories = ["spec"]\n'
            "[rules]\nhierarchy = {}\n"
        )
        assoc_spec = assoc_dir / "spec"
        assoc_spec.mkdir()
        # Empty spec dir — no .md files

        local_config = tmp_path / ".elspais.local.toml"
        local_config.write_text(f'[associates]\npaths = ["{assoc_dir}"]\n')

        args = argparse.Namespace(
            spec_dir=None,
            config=str(config),
            fix=False,
            dry_run=False,
            skip_rule=None,
            json=False,
            quiet=False,
            export=False,
            mode="combined",
            canonical_root=tmp_path,
        )
        result = run(args)
        assert result == 1
