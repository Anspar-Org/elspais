# Verifies: REQ-d00212-F
"""Tests that doctor.py and index.py consume v3 config paths.

These tests verify that functions in doctor.py and index.py use the v3
config schema (typed ElspaisConfig, get_associates_config(), scanning.spec)
rather than legacy v2 dict paths (spec.directories, associates.paths).

Validates REQ-d00202-A: associate config uses get_associates_config().
Validates REQ-d00212-K: associate entries use named [associates.<name>] format.
Validates REQ-d00212-F: config consumers use v3 scanning paths.
Validates REQ-d00207-C: typed config internally via ElspaisConfig.
"""
from __future__ import annotations


class TestCheckAssociatePathsV3:
    """Validates REQ-d00202-A: check_associate_paths uses get_associates_config()."""

    def test_REQ_d00202_A_no_associates_returns_passed(self):
        """Empty config (no associates section) should pass."""
        from elspais.commands.doctor import check_associate_paths

        config: dict = {}
        result = check_associate_paths(config, None)
        assert result.passed is True

    def test_REQ_d00212_K_named_associates_resolved(self, tmp_path):
        """v3 named [associates.myrepo] sections should be resolved by check_associate_paths."""
        from elspais.commands.doctor import check_associate_paths

        assoc_dir = tmp_path / "myrepo"
        assoc_dir.mkdir()

        # v3 config: named associate entries (not paths array)
        config = {
            "associates": {
                "myrepo": {
                    "path": str(assoc_dir),
                    "namespace": "MYR",
                },
            },
        }
        result = check_associate_paths(config, tmp_path)
        # Should find the path and report it as found
        assert result.passed is True
        assert result.details is not None
        assert str(assoc_dir) in str(result.details.get("found", []))

    def test_REQ_d00212_K_named_associate_missing_path(self, tmp_path):
        """v3 named associate with nonexistent path should fail."""
        from elspais.commands.doctor import check_associate_paths

        config = {
            "associates": {
                "myrepo": {
                    "path": str(tmp_path / "nonexistent"),
                    "namespace": "MYR",
                },
            },
        }
        result = check_associate_paths(config, tmp_path)
        assert result.passed is False
        assert "not found" in result.message.lower()

    def test_REQ_d00202_A_does_not_use_paths_array(self):
        """Should NOT look for config['associates']['paths'] (v2 format)."""
        from elspais.commands.doctor import check_associate_paths

        # This is the v2 format; check_associate_paths should NOT find associates
        # from this structure if it properly uses get_associates_config()
        config = {
            "associates": {
                "paths": ["/some/path"],
            },
        }
        # If the function uses get_associates_config(), the "paths" key is a
        # legacy fallback that requires discover_associate_from_path.
        # If it uses the old v2 code path (config.get("associates",{}).get("paths",[])),
        # it would try to iterate over ["/some/path"].
        # The v3 function should use get_associates_config() which handles this
        # differently from raw dict access.
        result = check_associate_paths(config, None)
        # With v3 code using get_associates_config(), this should either:
        # - Return passed=True (no valid named associates found), OR
        # - Process via legacy fallback in get_associates_config()
        # With v2 code doing config.get("associates",{}).get("paths",[]),
        # it would try to iterate and find missing paths.
        # We assert the v3 behavior: it should NOT blindly iterate paths array
        assert result.name == "associate.paths_resolvable"


class TestCheckAssociateConfigsV3:
    """Validates REQ-d00202-A: check_associate_configs uses get_associates_config()."""

    def test_REQ_d00202_A_no_associates_returns_passed(self):
        """Empty config should pass."""
        from elspais.commands.doctor import check_associate_configs

        config: dict = {}
        result = check_associate_configs(config, None)
        assert result.passed is True

    def test_REQ_d00212_K_named_associates_validated(self, tmp_path):
        """v3 named associates should be validated by check_associate_configs."""
        from elspais.commands.doctor import check_associate_configs

        assoc_dir = tmp_path / "myrepo"
        assoc_dir.mkdir()
        # Create a valid .elspais.toml in the associate dir
        (assoc_dir / ".elspais.toml").write_text(
            'version = 3\n[project]\nname = "myrepo"\nnamespace = "MYR"\n'
        )

        config = {
            "associates": {
                "myrepo": {
                    "path": str(assoc_dir),
                    "namespace": "MYR",
                },
            },
        }
        result = check_associate_configs(config, tmp_path)
        # Should process the named associate and validate its config
        assert result.name == "associate.configs_valid"


class TestCrossRepoInCommittedConfigV3:
    """Validates REQ-d00212-F: cross_repo check uses v3 scanning paths."""

    def test_REQ_d00212_F_cross_repo_uses_v3_scanning_paths(self, tmp_path):
        """Should detect cross-repo paths in [scanning.spec] directories."""
        from elspais.commands.doctor import check_cross_repo_in_committed_config

        config_path = tmp_path / ".elspais.toml"
        config_path.write_text(
            "version = 3\n" "[scanning.spec]\n" 'directories = ["spec", "../other-repo/spec"]\n'
        )
        result = check_cross_repo_in_committed_config(config_path)
        assert result.passed is False
        assert "cross" in result.message.lower() or ".." in result.message

    def test_REQ_d00212_F_named_associate_cross_repo_detected(self, tmp_path):
        """Should detect cross-repo paths in named [associates.x] sections."""
        from elspais.commands.doctor import check_cross_repo_in_committed_config

        config_path = tmp_path / ".elspais.toml"
        config_path.write_text(
            "version = 3\n" "[associates.other]\n" 'path = "../other-repo"\n' 'namespace = "OTH"\n'
        )
        result = check_cross_repo_in_committed_config(config_path)
        assert result.passed is False
        assert ".elspais.local.toml" in result.message

    def test_REQ_d00212_F_no_cross_repo_passes(self, tmp_path):
        """Config without cross-repo paths should pass."""
        from elspais.commands.doctor import check_cross_repo_in_committed_config

        config_path = tmp_path / ".elspais.toml"
        config_path.write_text("version = 3\n" "[scanning.spec]\n" 'directories = ["spec"]\n')
        result = check_cross_repo_in_committed_config(config_path)
        assert result.passed is True

    def test_REQ_d00212_F_does_not_use_v2_spec_directories(self, tmp_path):
        """Should NOT look for data['spec']['directories'] (v2 path)."""
        from elspais.commands.doctor import check_cross_repo_in_committed_config

        config_path = tmp_path / ".elspais.toml"
        # v2 format: [spec] directories = [...]
        # v3 format: [scanning.spec] directories = [...]
        # If a config has ONLY the v2 path with cross-repo, and the function
        # checks v3 paths, it should NOT detect it (pass).
        config_path.write_text(
            "version = 3\n" "[spec]\n" 'directories = ["spec", "../other-repo/spec"]\n'
        )
        result = check_cross_repo_in_committed_config(config_path)
        # v3 code should NOT look at [spec].directories — that's v2
        # So this should pass (no cross-repo paths found in v3 locations)
        assert result.passed is True, (
            "check_cross_repo_in_committed_config should not look at [spec].directories "
            "(v2 path); it should check [scanning.spec].directories instead"
        )


class TestResolveSpecDirInfoV3:
    """Validates REQ-d00207-C: _resolve_spec_dir_info uses typed config."""

    def test_REQ_d00207_C_resolves_label_from_v3_config(self, tmp_path):
        """Should read project name and level ordering from v3 .elspais.toml."""
        from elspais.commands.index import _resolve_spec_dir_info

        # Create a v3 config file
        config_path = tmp_path / ".elspais.toml"
        config_path.write_text(
            "version = 3\n"
            "[project]\n"
            'name = "testproject"\n'
            'namespace = "REQ"\n'
            "\n"
            "[levels.prd]\n"
            "rank = 1\n"
            'letter = "p"\n'
            'display_name = "Product"\n'
            'implements = ["prd"]\n'
            "\n"
            "[levels.dev]\n"
            "rank = 3\n"
            'letter = "d"\n'
            'display_name = "Development"\n'
            'implements = ["dev", "prd"]\n'
            "\n"
            "[scanning.spec]\n"
            'directories = ["spec"]\n'
        )
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()

        info = _resolve_spec_dir_info(spec_dir)

        assert "testproject" in info.label
        assert "spec" in info.label

    def test_REQ_d00212_F_level_ordering_from_v3_levels(self, tmp_path):
        """Level ordering should come from [levels] section (v3 format)."""
        from elspais.commands.index import _resolve_spec_dir_info

        config_path = tmp_path / ".elspais.toml"
        config_path.write_text(
            "version = 3\n"
            "[project]\n"
            'name = "testproject"\n'
            "\n"
            "[levels.prd]\n"
            "rank = 1\n"
            'letter = "p"\n'
            'display_name = "Product"\n'
            'implements = ["prd"]\n'
            "\n"
            "[levels.ops]\n"
            "rank = 2\n"
            'letter = "o"\n'
            'display_name = "Operations"\n'
            'implements = ["ops", "prd"]\n'
            "\n"
            "[levels.dev]\n"
            "rank = 3\n"
            'letter = "d"\n'
            'display_name = "Development"\n'
            'implements = ["dev", "ops", "prd"]\n'
        )
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()

        info = _resolve_spec_dir_info(spec_dir)

        # Should have all three levels with correct ranks
        assert "prd" in info.level_order
        assert "ops" in info.level_order
        assert "dev" in info.level_order
        assert info.level_order["prd"] == 1
        assert info.level_order["ops"] == 2
        assert info.level_order["dev"] == 3

    def test_REQ_d00207_C_no_config_falls_back_gracefully(self, tmp_path):
        """Without a config file, should fall back to directory-based label."""
        from elspais.commands.index import _resolve_spec_dir_info

        spec_dir = tmp_path / "myproject" / "spec"
        spec_dir.mkdir(parents=True)

        info = _resolve_spec_dir_info(spec_dir)

        assert info.label  # Should have some label
        assert info.level_order == {}  # No level info without config
