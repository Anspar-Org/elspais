"""Tests for get_associates_config() function.

Validates REQ-d00202-A: Read associate definitions from config.
Validates REQ-d00202-B: Path is required, git is optional.
Validates REQ-d00202-C: Missing or empty associates section returns empty dict.
"""

from elspais.config import get_associates_config


class TestGetAssociatesConfig:
    """Validates REQ-d00202-A, REQ-d00202-B, REQ-d00202-C."""

    def test_REQ_d00202_A_reads_associates_config(self):
        """Config with two associates returns both with paths and git fields."""
        config = {
            "associates": {
                "core": {"path": "../core", "git": "git@github.com:org/core.git"},
                "module-a": {"path": "../module-a", "git": "https://github.com/org/module-a.git"},
            }
        }

        result = get_associates_config(config)

        assert len(result) == 2
        assert result["core"]["path"] == "../core"
        assert result["core"]["git"] == "git@github.com:org/core.git"
        assert result["module-a"]["path"] == "../module-a"
        assert result["module-a"]["git"] == "https://github.com/org/module-a.git"

    def test_REQ_d00202_B_path_required_git_optional(self):
        """When git is not provided, it defaults to None."""
        config = {
            "associates": {
                "module-a": {"path": "../module-a"},
            }
        }

        result = get_associates_config(config)

        assert result["module-a"]["path"] == "../module-a"
        assert result["module-a"]["git"] is None

    def test_REQ_d00202_C_no_associates_returns_empty(self):
        """Config with no associates section returns empty dict."""
        config = {"patterns": {"prefix": "REQ"}}

        result = get_associates_config(config)

        assert result == {}

    def test_REQ_d00202_C_empty_associates_returns_empty(self):
        """Config with empty associates section returns empty dict."""
        config = {"associates": {}}

        result = get_associates_config(config)

        assert result == {}
