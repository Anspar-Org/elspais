"""Tests for associates config functions.

Validates REQ-d00202-A: Read associate definitions from config.
Validates REQ-d00202-B: Path is required, namespace is required.
Validates REQ-d00202-C: Missing or empty associates section returns empty dict.
Validates REQ-d00202-D: Transitive associates raise FederationError.
"""

import pytest

from elspais.config import get_associates_config, validate_no_transitive_associates
from elspais.graph.federated import FederationError


class TestGetAssociatesConfig:
    """Validates REQ-d00202-A, REQ-d00202-B, REQ-d00202-C."""

    def test_REQ_d00202_A_reads_associates_config(self):
        """Config with two associates returns both with paths and namespace fields."""
        config = {
            "associates": {
                "core": {"path": "../core", "namespace": "CORE"},
                "module-a": {"path": "../module-a", "namespace": "MODA"},
            }
        }

        result = get_associates_config(config)

        assert len(result) == 2
        assert result["core"]["path"] == "../core"
        assert result["core"]["namespace"] == "CORE"
        assert result["module-a"]["path"] == "../module-a"
        assert result["module-a"]["namespace"] == "MODA"

    def test_REQ_d00202_B_path_and_namespace_required(self):
        """Path and namespace are required fields."""
        config = {
            "associates": {
                "module-a": {"path": "../module-a", "namespace": "MODA"},
            }
        }

        result = get_associates_config(config)

        assert result["module-a"]["path"] == "../module-a"
        assert result["module-a"]["namespace"] == "MODA"

    def test_REQ_d00202_C_no_associates_returns_empty(self):
        """Config with no associates section returns empty dict."""
        config = {"project": {"namespace": "REQ"}}

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
            "scanning": {"spec": {"directories": ["spec"]}},
        }

        # Should not raise
        validate_no_transitive_associates("core", associate_config)
