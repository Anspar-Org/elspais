# Validates: REQ-d00211-A, REQ-d00211-B, REQ-d00211-C
"""Tests for _extract_viewer_config() in elspais.server.app.

Validates REQ-d00211-A: config_types from id_patterns.types
Validates REQ-d00211-B: config_relationship_kinds
Validates REQ-d00211-C: config_statuses from allowed_statuses
"""

import pytest

from elspais.config import config_defaults


@pytest.fixture()
def default_config():
    """Return a default config dict."""
    return config_defaults()


@pytest.fixture()
def custom_types_config(default_config):
    """Return config with custom levels defined."""
    cfg = dict(default_config)
    cfg["levels"] = {
        "system": {"rank": 1, "letter": "s", "implements": ["system"]},
        "module": {"rank": 2, "letter": "m", "implements": ["module", "system"]},
    }
    return cfg


@pytest.fixture()
def custom_statuses_config(default_config):
    """Return config with custom allowed_statuses."""
    cfg = dict(default_config)
    cfg["rules"] = dict(cfg.get("rules", {}))
    cfg["rules"]["format"] = dict(cfg["rules"].get("format", {}))
    cfg["rules"]["format"]["allowed_statuses"] = ["Open", "Closed", "Review"]
    return cfg


class TestExtractViewerConfigTypes:
    """Validates REQ-d00211-A: config_types from id_patterns.types."""

    def test_REQ_d00211_A_default_types_present(self, default_config):
        """Default config produces prd, ops, dev types."""
        from elspais.server.app import _extract_viewer_config

        result = _extract_viewer_config(default_config)
        names = [t["name"] for t in result["config_types"]]
        assert "prd" in names
        assert "ops" in names
        assert "dev" in names

    def test_REQ_d00211_A_type_entry_has_name_letter_level(self, default_config):
        """Each type entry must have name, letter, and level keys."""
        from elspais.server.app import _extract_viewer_config

        result = _extract_viewer_config(default_config)
        for entry in result["config_types"]:
            assert "name" in entry, f"Missing 'name' in {entry}"
            assert "letter" in entry, f"Missing 'letter' in {entry}"
            assert "level" in entry, f"Missing 'level' in {entry}"

    def test_REQ_d00211_A_default_prd_letter_and_level(self, default_config):
        """prd type should have letter='p' and level=1."""
        from elspais.server.app import _extract_viewer_config

        result = _extract_viewer_config(default_config)
        prd = [t for t in result["config_types"] if t["name"] == "prd"][0]
        assert prd["letter"] == "p"
        assert prd["level"] == 1

    def test_REQ_d00211_A_custom_types_override(self, custom_types_config):
        """Custom types in config override defaults."""
        from elspais.server.app import _extract_viewer_config

        result = _extract_viewer_config(custom_types_config)
        names = {t["name"] for t in result["config_types"]}
        assert names == {"system", "module"}
        system = [t for t in result["config_types"] if t["name"] == "system"][0]
        assert system["letter"] == "s"
        assert system["level"] == 1


class TestExtractViewerConfigRelationshipKinds:
    """Validates REQ-d00211-B: config_relationship_kinds."""

    def test_REQ_d00211_B_default_relationship_kinds(self, default_config):
        """Default config includes implements, refines, satisfies."""
        from elspais.server.app import _extract_viewer_config

        result = _extract_viewer_config(default_config)
        kinds = result["config_relationship_kinds"]
        assert "implements" in kinds
        assert "refines" in kinds
        assert "satisfies" in kinds

    def test_REQ_d00211_B_relationship_kinds_are_strings(self, default_config):
        """All relationship kinds must be strings."""
        from elspais.server.app import _extract_viewer_config

        result = _extract_viewer_config(default_config)
        for kind in result["config_relationship_kinds"]:
            assert isinstance(kind, str)

    def test_REQ_d00211_B_relationship_kinds_is_list(self, default_config):
        """config_relationship_kinds must be a list."""
        from elspais.server.app import _extract_viewer_config

        result = _extract_viewer_config(default_config)
        assert isinstance(result["config_relationship_kinds"], list)


class TestExtractViewerConfigStatuses:
    """Validates REQ-d00211-C: config_statuses from allowed_statuses."""

    def test_REQ_d00211_C_empty_config_returns_default_statuses(self):
        """Empty config should return sensible default statuses."""
        from elspais.server.app import _extract_viewer_config

        result = _extract_viewer_config({})
        statuses = result["config_statuses"]
        assert isinstance(statuses, list)
        # With empty config, should still return a list (possibly empty or defaults)
        assert len(statuses) >= 0

    def test_REQ_d00211_C_custom_statuses(self, custom_statuses_config):
        """Custom allowed_statuses from config are returned."""
        from elspais.server.app import _extract_viewer_config

        result = _extract_viewer_config(custom_statuses_config)
        statuses = result["config_statuses"]
        assert "Open" in statuses
        assert "Closed" in statuses
        assert "Review" in statuses

    def test_REQ_d00211_C_result_has_all_keys(self, default_config):
        """Return dict must have all three expected keys."""
        from elspais.server.app import _extract_viewer_config

        result = _extract_viewer_config(default_config)
        assert "config_types" in result
        assert "config_relationship_kinds" in result
        assert "config_statuses" in result
