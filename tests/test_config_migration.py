"""Tests for config migration v3 to v4: flat terms severity fields to nested [terms.severity]."""

import copy
from pathlib import Path


class TestMigrateV3ToV4:
    """Validates REQ-d00212-N: config migration from v3 to v4 for terms severity."""

    # Verifies: REQ-d00212-N
    def test_REQ_d00212_N_current_config_version_is_4(self):
        """CURRENT_CONFIG_VERSION should be 4 after adding this migration."""
        from elspais.config import CURRENT_CONFIG_VERSION

        assert CURRENT_CONFIG_VERSION == 4

    # Verifies: REQ-d00212-N
    def test_REQ_d00212_N_flat_severity_fields_migrated_to_nested(self):
        """Flat *_severity fields in [terms] should move into [terms.severity]."""
        from elspais.config import _migrate_v3_to_v4

        v3_config = {
            "version": 3,
            "terms": {
                "output_dir": "spec/_generated",
                "duplicate_severity": "error",
                "undefined_severity": "warning",
                "unmarked_severity": "warning",
            },
        }

        result = _migrate_v3_to_v4(copy.deepcopy(v3_config))

        assert result["version"] == 4
        assert result["terms"]["output_dir"] == "spec/_generated"
        assert "duplicate_severity" not in result["terms"]
        assert "undefined_severity" not in result["terms"]
        assert "unmarked_severity" not in result["terms"]
        assert result["terms"]["severity"] == {
            "duplicate": "error",
            "undefined": "warning",
            "unmarked": "warning",
        }

    # Verifies: REQ-d00212-N
    def test_REQ_d00212_N_config_without_terms_passes_through(self):
        """Configs without [terms] should pass through with version bumped to 4."""
        from elspais.config import _migrate_v3_to_v4

        v3_config = {"version": 3, "project": {"namespace": "TEST"}}

        result = _migrate_v3_to_v4(copy.deepcopy(v3_config))

        assert result["version"] == 4
        assert "terms" not in result
        assert result["project"]["namespace"] == "TEST"

    # Verifies: REQ-d00212-N
    def test_REQ_d00212_N_existing_severity_dict_not_double_migrated(self):
        """Configs already having [terms.severity] should not be double-migrated."""
        from elspais.config import _migrate_v3_to_v4

        v3_config = {
            "version": 3,
            "terms": {
                "output_dir": "spec/_generated",
                "severity": {
                    "duplicate": "error",
                    "undefined": "error",
                    "unmarked": "error",
                },
            },
        }

        result = _migrate_v3_to_v4(copy.deepcopy(v3_config))

        assert result["version"] == 4
        assert result["terms"]["severity"] == {
            "duplicate": "error",
            "undefined": "error",
            "unmarked": "error",
        }

    # Verifies: REQ-d00212-N
    def test_REQ_d00212_N_partial_severity_fields_migrated(self):
        """Only present *_severity fields should be migrated; missing ones omitted."""
        from elspais.config import _migrate_v3_to_v4

        v3_config = {
            "version": 3,
            "terms": {
                "output_dir": "spec/_generated",
                "duplicate_severity": "error",
            },
        }

        result = _migrate_v3_to_v4(copy.deepcopy(v3_config))

        assert result["version"] == 4
        assert result["terms"]["severity"] == {"duplicate": "error"}
        assert "duplicate_severity" not in result["terms"]
        assert result["terms"]["output_dir"] == "spec/_generated"


class TestLoadConfigV3File:
    """End-to-end: loading a real v3 TOML file (with flat severity fields) via load_config."""

    # Verifies: REQ-d00212-N
    def test_REQ_d00212_N_load_config_accepts_v3_file_with_flat_severity(
        self, tmp_path: Path
    ) -> None:
        """A v3 .elspais.toml with flat *_severity fields must load without validation error.

        Regression: previously `_merge_configs(defaults, user)` injected the defaults'
        nested `severity` dict before the migration ran, tripping the "already migrated"
        guard, so the flat fields survived and Pydantic `extra="forbid"` rejected the
        config. Loading should now succeed and expose the migrated severity values.
        """
        from elspais.config import load_config

        config_path = tmp_path / ".elspais.toml"
        config_path.write_text(
            "version = 3\n"
            "\n"
            "[project]\n"
            'namespace = "REQ"\n'
            'name = "test"\n'
            "\n"
            "[terms]\n"
            'output_dir = "spec/_generated"\n'
            'duplicate_severity = "error"\n'
            'undefined_severity = "warning"\n'
            'unmarked_severity = "warning"\n',
            encoding="utf-8",
        )

        result = load_config(config_path)

        assert result["version"] == 4
        terms = result["terms"]
        assert terms["severity"]["duplicate"] == "error"
        assert terms["severity"]["undefined"] == "warning"
        assert terms["severity"]["unmarked"] == "warning"
        assert "duplicate_severity" not in terms
        assert "undefined_severity" not in terms
        assert "unmarked_severity" not in terms
