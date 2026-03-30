"""Tests for REQ-d00080: Diagnostic Command Exit Code Contract."""

import argparse


class TestDoctorExitCodes:
    """REQ-d00080-A: doctor SHALL exit non-zero on [!!] findings."""

    def test_REQ_d00080_A_invalid_config_field_exits_nonzero(self, tmp_path, monkeypatch):
        """doctor exits 1 when config has invalid fields."""
        from elspais.commands.doctor import run

        monkeypatch.chdir(tmp_path)
        config = tmp_path / ".elspais.toml"
        config.write_text('version = 3\n[project]\nbogus_field = "invalid"\n')
        (tmp_path / "spec").mkdir()

        args = argparse.Namespace(
            config=str(config),
            json=False,
            verbose=False,
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
            'version = 3\n[project]\nname = "test"\n' "[scanning.spec]\ndirectories = []\n"
        )
        (tmp_path / "spec").mkdir()

        args = argparse.Namespace(
            config=str(config),
            json=False,
            verbose=False,
        )
        result = run(args)
        assert result == 1

    def test_REQ_d00080_A_missing_associate_path_exits_nonzero(self, tmp_path, monkeypatch):
        """doctor exits 1 when configured associate path doesn't exist."""
        from elspais.commands.doctor import run

        monkeypatch.chdir(tmp_path)
        config = tmp_path / ".elspais.toml"
        config.write_text(
            'version = 3\n[project]\nnamespace = "REQ"\n'
            '[levels.prd]\nrank = 1\nletter = "p"\nimplements = ["prd"]\n'
            '[scanning.spec]\ndirectories = ["spec"]\n'
        )
        local_config = tmp_path / ".elspais.local.toml"
        local_config.write_text(
            '[associates.sponsor]\npath = "/nonexistent/sponsor"\nnamespace = "SPO"\n'
        )
        (tmp_path / "spec").mkdir()

        args = argparse.Namespace(
            config=str(config),
            json=False,
            verbose=False,
        )
        result = run(args)
        assert result == 1

    def test_REQ_d00080_A_healthy_config_exits_zero(self, tmp_path, monkeypatch):
        """doctor exits 0 on a well-configured project."""
        from elspais.commands.doctor import run

        monkeypatch.chdir(tmp_path)
        config = tmp_path / ".elspais.toml"
        config.write_text(
            'version = 3\n[project]\nnamespace = "REQ"\n'
            '[levels.prd]\nrank = 1\nletter = "p"\nimplements = ["prd"]\n'
            "[id-patterns]\n"
            'canonical = "{namespace}-{level.letter}{component}"\n'
            '[scanning.spec]\ndirectories = ["spec"]\n'
        )
        (tmp_path / "spec").mkdir()

        args = argparse.Namespace(
            config=str(config),
            json=False,
            verbose=False,
        )
        result = run(args)
        assert result == 0


class TestDoctorAssociatedSection:
    """REQ-d00080-D: doctor SHALL validate [associated] section for associated projects."""

    def test_REQ_d00080_D_missing_associated_section_exits_nonzero(self, tmp_path, monkeypatch):
        """doctor exits 1 when project.type=associated but [associated] section missing."""
        from elspais.commands.doctor import run

        monkeypatch.chdir(tmp_path)
        config = tmp_path / ".elspais.toml"
        config.write_text(
            'version = 3\n[project]\nnamespace = "REQ"\nbogus_extra = true\n'
            '[scanning.spec]\ndirectories = ["spec"]\n'
        )
        (tmp_path / "spec").mkdir()

        args = argparse.Namespace(
            config=str(config),
            json=False,
            verbose=False,
        )
        result = run(args)
        assert result == 1

    def test_REQ_d00080_D_invalid_config_exits_nonzero(self, tmp_path, monkeypatch):
        """doctor exits 1 when config has schema validation errors."""
        from elspais.commands.doctor import run

        monkeypatch.chdir(tmp_path)
        config = tmp_path / ".elspais.toml"
        config.write_text(
            'version = 3\n[project]\nbogus_field = "invalid"\n'
            '[scanning.spec]\ndirectories = ["spec"]\n'
        )
        (tmp_path / "spec").mkdir()

        args = argparse.Namespace(
            config=str(config),
            json=False,
            verbose=False,
        )
        result = run(args)
        assert result == 1

    def test_REQ_d00080_D_check_function_valid(self):
        """check_config_associated_section passes with valid config."""
        from elspais.commands.doctor import check_config_associated_section

        raw = {
            "version": 3,
            "associates": {"callisto": {"path": "../callisto", "namespace": "CAL"}},
        }
        check = check_config_associated_section(raw)
        assert check.passed is True

    def test_REQ_d00080_D_check_function_no_associates(self):
        """check_config_associated_section passes with no associates."""
        from elspais.commands.doctor import check_config_associated_section

        raw = {"version": 3}
        check = check_config_associated_section(raw)
        assert check.passed is True

    def test_REQ_d00080_D_check_function_non_associated_skips(self):
        """check_config_associated_section passes for projects without associates."""
        from elspais.commands.doctor import check_config_associated_section

        raw = {"version": 3, "project": {"namespace": "REQ"}}
        check = check_config_associated_section(raw)
        assert check.passed is True
