"""Tests for associates config functions.

Validates REQ-d00202-A: Read associate definitions from config.
Validates REQ-d00202-B: Path is required, git is optional.
Validates REQ-d00202-C: Missing or empty associates section returns empty dict.
Validates REQ-d00202-D: Transitive associates raise FederationError.
"""

import pytest

from elspais.config import get_associates_config, validate_no_transitive_associates
from elspais.graph.federated import FederationError


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


class TestTransitiveAssociateDetection:
    """Validates REQ-d00202-D: transitive associates are a hard error."""

    def test_REQ_d00202_D_associate_with_associates_raises(self):
        """Associate declaring its own associates raises FederationError."""
        associate_config = {
            "associates": {
                "sub-module": {"path": "../sub-module"},
            }
        }

        with pytest.raises(FederationError, match="declares its own associates"):
            validate_no_transitive_associates("core", associate_config)

    def test_REQ_d00202_D_associate_without_associates_ok(self):
        """Associate without [associates] section passes validation."""
        associate_config = {
            "spec": {"directories": ["spec"]},
        }

        # Should not raise
        validate_no_transitive_associates("core", associate_config)
