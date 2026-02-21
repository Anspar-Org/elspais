# Implements: REQ-p00005-C
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
