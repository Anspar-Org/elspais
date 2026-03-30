"""Tests for TermsConfig, TermsSeverityConfig, and FormatConfig models.

Validates REQ-d00212-L: TermsConfig SHALL have output_dir, markup_styles
(default ["*", "**"]), exclude_files (default []), and nested
severity: TermsSeverityConfig. TermsSeverityConfig SHALL define 6 severity
fields.

Validates REQ-d00212-M: FormatConfig SHALL include no_traceability_severity.
"""

import pytest
from pydantic import ValidationError

from elspais.config import schema as _schema

ElspaisConfig = _schema.ElspaisConfig
TermsConfig = _schema.TermsConfig


class TestTermsSeverityConfig:
    """Validates REQ-d00212-L: TermsSeverityConfig model with 6 severity fields."""

    def test_REQ_d00212_L_terms_severity_config_defaults(self):
        """TermsSeverityConfig() has correct 6 defaults."""
        TermsSeverityConfig = _schema.TermsSeverityConfig
        sc = TermsSeverityConfig()
        assert sc.duplicate == "error"
        assert sc.undefined == "warning"
        assert sc.unmarked == "warning"
        assert sc.unused == "warning"
        assert sc.bad_definition == "error"
        assert sc.collection_empty == "warning"

    def test_REQ_d00212_L_terms_severity_config_strict(self):
        """TermsSeverityConfig rejects unknown fields (extra='forbid')."""
        TermsSeverityConfig = _schema.TermsSeverityConfig
        with pytest.raises(ValidationError, match="extra"):
            TermsSeverityConfig(bogus="nope")  # type: ignore[call-arg]


class TestTermsConfig:
    """Validates REQ-d00212-L: TermsConfig restructured model."""

    def test_REQ_d00212_L_terms_config_nested_severity(self):
        """TermsConfig().severity is a TermsSeverityConfig instance."""
        TermsSeverityConfig = _schema.TermsSeverityConfig
        tc = TermsConfig()
        assert isinstance(tc.severity, TermsSeverityConfig)

    def test_REQ_d00212_L_terms_config_markup_styles_default(self):
        """TermsConfig().markup_styles defaults to ["*", "**"]."""
        tc = TermsConfig()
        assert tc.markup_styles == ["*", "**"]

    def test_REQ_d00212_L_terms_config_exclude_files_default(self):
        """TermsConfig().exclude_files defaults to []."""
        tc = TermsConfig()
        assert tc.exclude_files == []

    def test_REQ_d00212_L_terms_config_no_flat_severity(self):
        """TermsConfig does NOT have flat duplicate_severity etc."""
        tc = TermsConfig()
        assert not hasattr(tc, "duplicate_severity")
        assert not hasattr(tc, "undefined_severity")
        assert not hasattr(tc, "unmarked_severity")

    def test_REQ_d00212_L_elspais_config_terms_field(self):
        """ElspaisConfig().terms has the new nested structure."""
        TermsSeverityConfig = _schema.TermsSeverityConfig
        cfg = ElspaisConfig()
        assert hasattr(cfg, "terms")
        assert isinstance(cfg.terms, TermsConfig)
        assert isinstance(cfg.terms.severity, TermsSeverityConfig)
        assert cfg.terms.markup_styles == ["*", "**"]
        assert cfg.terms.exclude_files == []


class TestFormatConfig:
    """Validates REQ-d00212-M: FormatConfig no_traceability_severity field."""

    def test_REQ_d00212_M_no_traceability_severity_default(self):
        """FormatConfig().no_traceability_severity defaults to None."""
        fc = _schema.FormatConfig()
        assert fc.no_traceability_severity is None

    def test_REQ_d00212_M_no_traceability_severity_accepts_values(self):
        """FormatConfig accepts warning/error/off for no_traceability_severity."""
        for val in ("warning", "error", "off"):
            fc = _schema.FormatConfig(no_traceability_severity=val)
            assert fc.no_traceability_severity == val
