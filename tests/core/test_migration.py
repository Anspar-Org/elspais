"""Tests for version-gated config migration."""

import pytest


# Verifies: REQ-d00207-B
def test_pre_v2_patterns_section_is_refused(tmp_path):
    """A `[patterns]` section is reported, not quietly ignored.

    It was how identifiers were declared before v2. Nothing reads it now,
    so accepting one would load a configuration whose identifier settings
    silently do not happen -- the reader would get the defaults, and the
    spelling the author configured would simply not occur.
    """
    from elspais.config import load_config

    config = tmp_path / ".elspais.toml"
    config.write_text(
        'version = 3\n[project]\nname = "p"\nnamespace = "REQ"\n\n'
        '[patterns]\nprefix = "PROJ"\n[patterns.types]\nprd = { level = 1, id = "p" }\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r"\[patterns\]"):
        load_config(config)


# Verifies: REQ-d00212-N
def test_v3_terms_severity_is_migrated(tmp_path):
    """The one live migration still fires: flat terms severity nests itself."""
    from elspais.config import load_config

    config = tmp_path / ".elspais.toml"
    config.write_text(
        'version = 3\n[project]\nname = "p"\nnamespace = "REQ"\n\n'
        '[terms]\nduplicate_severity = "warning"\n',
        encoding="utf-8",
    )

    loaded = load_config(config)

    assert loaded["terms"]["severity"]["duplicate"] == "warning"
    assert "duplicate_severity" not in loaded["terms"]
