# Verifies: REQ-p00005-C
"""Tests for environment variable override enhancements in config.

Validates REQ-p00005-C: JSON list values via env vars (e.g., ELSPAIS_ASSOCIATES_PATHS).
Validates REQ-p00005-E: Boolean and malformed JSON produce clear errors.
"""
from __future__ import annotations


class TestTryParseEnvValue:
    """Validates REQ-p00005-C: _try_parse_env_value correctly parses typed values."""

    def test_REQ_p00005_C_json_list_parsed(self):
        """JSON array string is parsed into a Python list."""
        from elspais.config import _try_parse_env_value

        result = _try_parse_env_value('["/path/to/repo1", "/path/to/repo2"]')
        assert result == ["/path/to/repo1", "/path/to/repo2"]

    def test_REQ_p00005_C_json_object_parsed(self):
        """JSON object string is parsed into a Python dict."""
        from elspais.config import _try_parse_env_value

        result = _try_parse_env_value('{"key": "value"}')
        assert result == {"key": "value"}

    def test_REQ_p00005_C_boolean_true_parsed(self):
        """'true' (case-insensitive) is parsed as Python True."""
        from elspais.config import _try_parse_env_value

        assert _try_parse_env_value("true") is True
        assert _try_parse_env_value("True") is True
        assert _try_parse_env_value("TRUE") is True

    def test_REQ_p00005_C_boolean_false_parsed(self):
        """'false' (case-insensitive) is parsed as Python False."""
        from elspais.config import _try_parse_env_value

        assert _try_parse_env_value("false") is False
        assert _try_parse_env_value("False") is False
        assert _try_parse_env_value("FALSE") is False

    def test_REQ_p00005_C_plain_string_passthrough(self):
        """Plain strings are returned as-is."""
        from elspais.config import _try_parse_env_value

        assert _try_parse_env_value("hello") == "hello"
        assert _try_parse_env_value("REQ") == "REQ"

    def test_REQ_p00005_E_malformed_json_returns_string(self):
        """Malformed JSON starting with [ or { falls back to string."""
        from elspais.config import _try_parse_env_value

        result = _try_parse_env_value("[not valid json")
        assert result == "[not valid json"

    def test_REQ_p00005_C_empty_list_parsed(self):
        """Empty JSON array is parsed correctly."""
        from elspais.config import _try_parse_env_value

        assert _try_parse_env_value("[]") == []


class TestApplyEnvOverridesWithParsing:
    """Validates REQ-p00005-C: _apply_env_overrides uses _try_parse_env_value."""

    def test_REQ_p00005_C_env_var_sets_list(self, monkeypatch):
        """ELSPAIS_ASSOCIATES_PATHS='["/repo"]' sets associates.paths to list."""
        from elspais.config import _apply_env_overrides

        monkeypatch.setenv("ELSPAIS_ASSOCIATES_PATHS", '["/path/to/repo"]')
        config = {"associates": {}}
        result = _apply_env_overrides(config)
        assert result["associates"]["paths"] == ["/path/to/repo"]

    def test_REQ_p00005_C_env_var_sets_boolean(self, monkeypatch):
        """ELSPAIS_TESTING_ENABLED=true sets testing.enabled to True."""
        from elspais.config import _apply_env_overrides

        monkeypatch.setenv("ELSPAIS_TESTING_ENABLED", "true")
        config = {"testing": {"enabled": False}}
        result = _apply_env_overrides(config)
        assert result["testing"]["enabled"] is True

    def test_REQ_p00005_C_env_var_sets_string(self, monkeypatch):
        """ELSPAIS_PATTERNS_PREFIX=MYREQ sets patterns.prefix to 'MYREQ'."""
        from elspais.config import _apply_env_overrides

        monkeypatch.setenv("ELSPAIS_PATTERNS_PREFIX", "MYREQ")
        config = {"patterns": {"prefix": "REQ"}}
        result = _apply_env_overrides(config)
        assert result["patterns"]["prefix"] == "MYREQ"

    def test_REQ_p00005_C_env_var_creates_nested_key(self, monkeypatch):
        """Env var creates nested structure if needed."""
        from elspais.config import _apply_env_overrides

        monkeypatch.setenv("ELSPAIS_ASSOCIATES_PATHS", '["/repo"]')
        config = {}
        result = _apply_env_overrides(config)
        assert result["associates"]["paths"] == ["/repo"]

    def test_REQ_p00005_C_double_underscore_is_literal_underscore(self, monkeypatch):
        """Double underscore (__) maps to literal underscore in key name."""
        from elspais.config import _apply_env_overrides

        monkeypatch.setenv("ELSPAIS_VALIDATION_STRICT__HIERARCHY", "false")
        config = {"validation": {}}
        result = _apply_env_overrides(config)
        assert result["validation"]["strict_hierarchy"] is False

    def test_REQ_p00005_C_double_underscore_does_not_create_empty_key(self, monkeypatch):
        """ELSPAIS_ASSOCIATES__PATHS uses __ as literal underscore, not empty segment."""
        from elspais.config import _apply_env_overrides

        monkeypatch.setenv("ELSPAIS_ASSOCIATES__PATHS", '["/repo"]')
        config = {}
        result = _apply_env_overrides(config)
        # __ is a literal underscore, so the key is "associates_paths" (flat)
        assert "associates_paths" in result
        assert result["associates_paths"] == ["/repo"]
        # Must NOT create an empty-string section key (the old bug)
        assert "" not in result


class TestReservedEnvVarsSkipped:
    """Validates REQ-p00005-C: tool-reserved env vars (e.g. ELSPAIS_VERSION)
    must NOT be consumed as config overrides.

    Regression: ELSPAIS_VERSION is used by utilities/version_check.py to pin the
    minimum elspais CLI version (often set in downstream pre-commit hooks).
    Treating it as a config override collided with the config's top-level
    integer `version` field (schema format version), producing a misleading
    Pydantic validation error against ``.elspais.toml``.
    """

    def test_REQ_p00005_C_elspais_version_not_applied_as_override(self, monkeypatch):
        """ELSPAIS_VERSION env var does NOT override config['version']."""
        from elspais.config import _apply_env_overrides

        monkeypatch.setenv("ELSPAIS_VERSION", "0.112.13")
        config = {"version": 4}
        result = _apply_env_overrides(config)
        # Must preserve the int schema version, not overwrite with version-string.
        assert result["version"] == 4
        assert isinstance(result["version"], int)

    def test_REQ_p00005_C_non_reserved_override_still_applies(self, monkeypatch):
        """Non-reserved ELSPAIS_* vars are still applied (guard against over-reservation)."""
        from elspais.config import _apply_env_overrides

        monkeypatch.setenv("ELSPAIS_PATTERNS_PREFIX", "MYREQ")
        config = {"patterns": {"prefix": "REQ"}}
        result = _apply_env_overrides(config)
        assert result["patterns"]["prefix"] == "MYREQ"

    def test_REQ_p00005_C_reserved_and_regular_env_vars_together(self, monkeypatch):
        """With both set: version stays intact AND non-reserved override still applies."""
        from elspais.config import _apply_env_overrides

        monkeypatch.setenv("ELSPAIS_VERSION", "0.112.13")
        monkeypatch.setenv("ELSPAIS_PATTERNS_PREFIX", "MYREQ")
        config = {"version": 4, "patterns": {"prefix": "REQ"}}
        result = _apply_env_overrides(config)
        assert result["version"] == 4
        assert isinstance(result["version"], int)
        assert result["patterns"]["prefix"] == "MYREQ"

    def test_REQ_p00005_C_load_config_survives_elspais_version_env(self, monkeypatch, tmp_path):
        """End-to-end: load_config() must not fail Pydantic validation when
        ELSPAIS_VERSION is set in the environment. This is the exact user-facing
        scenario: a pre-commit hook sets ELSPAIS_VERSION=0.112.13, and elspais
        is invoked against a project whose .elspais.toml declares `version = 4`.
        Before the fix, this raised:
            invalid literal for int() with base 10: '0.112.13'
        """
        from elspais.config import load_config

        config_path = tmp_path / ".elspais.toml"
        config_path.write_text(
            "version = 4\n" "\n" "[scanning.spec]\n" 'directories = ["spec"]\n',
            encoding="utf-8",
        )

        monkeypatch.setenv("ELSPAIS_VERSION", "0.112.13")

        # Should not raise.
        config = load_config(config_path)
        assert config["version"] == 4
        assert isinstance(config["version"], int)
