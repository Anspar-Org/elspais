"""Tests for TermsConfig model (REQ-d00212-L).

Validates REQ-d00212-L: TermsConfig model with defined-terms configuration
fields and its inclusion in ElspaisConfig.
"""

import pytest
from pydantic import ValidationError

from elspais.config import schema as _schema

ElspaisConfig = _schema.ElspaisConfig
TermsConfig = _schema.TermsConfig


class TestTermsConfig:
    """Validates REQ-d00212-L: TermsConfig model and ElspaisConfig integration."""

    def test_REQ_d00212_L_terms_config_defaults(self):
        """TermsConfig() has correct default values for all fields."""
        tc = TermsConfig()
        assert tc.output_dir == "spec/_generated"
        assert tc.duplicate_severity == "error"
        assert tc.undefined_severity == "warning"
        assert tc.unmarked_severity == "warning"

    def test_REQ_d00212_L_elspais_config_has_terms(self):
        """ElspaisConfig() has a terms field of type TermsConfig."""
        cfg = ElspaisConfig()
        assert hasattr(cfg, "terms")
        assert isinstance(cfg.terms, TermsConfig)

    def test_REQ_d00212_L_toml_with_terms_validates(self):
        """A TOML-style dict with [terms] section validates via ElspaisConfig."""
        data = {
            "terms": {
                "output_dir": "docs/_terms",
                "duplicate_severity": "warning",
            }
        }
        cfg = ElspaisConfig(**data)
        assert cfg.terms.output_dir == "docs/_terms"
        assert cfg.terms.duplicate_severity == "warning"
        # Unset fields keep defaults
        assert cfg.terms.undefined_severity == "warning"
        assert cfg.terms.unmarked_severity == "warning"

    def test_REQ_d00212_L_terms_config_rejects_unknown(self):
        """TermsConfig rejects unknown fields (extra='forbid')."""
        with pytest.raises(ValidationError, match="extra"):
            TermsConfig(bogus="nope")  # type: ignore[call-arg]

    def test_REQ_d00212_L_terms_config_custom_values(self):
        """TermsConfig accepts custom values for all fields."""
        tc = TermsConfig(
            output_dir="custom/path",
            duplicate_severity="warning",
            undefined_severity="error",
            unmarked_severity="info",
        )
        assert tc.output_dir == "custom/path"
        assert tc.duplicate_severity == "warning"
        assert tc.undefined_severity == "error"
        assert tc.unmarked_severity == "info"
