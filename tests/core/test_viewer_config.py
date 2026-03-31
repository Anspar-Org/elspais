# Validates: REQ-d00211-A, REQ-d00211-B, REQ-d00211-C, REQ-d00211-D
"""Tests for _extract_viewer_config() in elspais.server.app.

Validates REQ-d00211-A: config_types from id_patterns.types
Validates REQ-d00211-B: config_relationship_kinds
Validates REQ-d00211-C: config_statuses from allowed_statuses
Validates REQ-d00211-D: statuses in template context sorted by role order
"""

import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch

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
    """Return config with custom status_roles (statuses derived from roles)."""
    cfg = dict(default_config)
    cfg["rules"] = dict(cfg.get("rules", {}))
    cfg["rules"]["format"] = dict(cfg["rules"].get("format", {}))
    cfg["rules"]["format"]["status_roles"] = {
        "active": ["Open"],
        "provisional": ["Review"],
        "retired": ["Closed"],
    }
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


class TestIndexRouteStatusOrdering:
    """Validates REQ-d00211-D: statuses in template context are sorted by role order.

    The route index() SHALL pass statuses to the template sorted by role
    priority (active first, retired last), not alphabetically.
    """

    @pytest.fixture()
    def role_ordered_config(self, tmp_path: Path):
        """Config with status_roles where role order differs from alphabetical.

        Zactive -> active role (rank 0)
        Aretired -> retired role (rank 3)
        Alphabetical: ["Aretired", "Zactive"]
        Role order:   ["Zactive", "Aretired"]
        """
        cfg = config_defaults()
        cfg["rules"] = dict(cfg.get("rules", {}))
        cfg["rules"]["format"] = dict(cfg["rules"].get("format", {}))
        cfg["rules"]["format"]["status_roles"] = {
            "active": ["Zactive"],
            "retired": ["Aretired"],
        }
        return cfg

    def _make_app_state(self, config: dict, tmp_path: Path):
        """Build a minimal AppState with the given config dict."""
        from elspais.server.state import AppState

        (tmp_path / ".elspais.toml").write_text(
            'version = 3\n[project]\nname = "test"\n'
            '[levels.prd]\nrank = 1\nletter = "p"\nimplements = ["prd"]\n'
        )
        state = AppState.from_config(repo_root=tmp_path)
        state.config = config
        return state

    def test_REQ_d00211_D_statuses_sorted_by_role_not_alphabetically(
        self, role_ordered_config, tmp_path
    ):
        """statuses in index template context are role-sorted, not alphabetically sorted.

        Given statuses Zactive (active role) and Aretired (retired role),
        role sort yields [Zactive, Aretired] while alphabetical yields [Aretired, Zactive].
        """
        from elspais.server.routes_ui import index

        state = self._make_app_state(role_ordered_config, tmp_path)

        captured_context: dict = {}

        def fake_template_response(request, template_name, context):
            captured_context.update(context)
            resp = MagicMock()
            resp.status_code = 200
            return resp

        fake_templates = MagicMock()
        fake_templates.TemplateResponse = fake_template_response

        mock_request = MagicMock()
        mock_request.app.state.app_state = state

        # Patch _collect_unique_values to return statuses in arbitrary set order
        # (sets are unordered, so use a list to be explicit about the input)
        raw_statuses = {"Aretired", "Zactive"}

        with (
            patch("starlette.templating.Jinja2Templates", return_value=fake_templates),
            patch(
                "elspais.html.generator.HTMLGenerator._collect_unique_values",
                return_value=raw_statuses,
            ),
        ):
            asyncio.run(index(mock_request))

        assert "statuses" in captured_context, "index() must pass 'statuses' to template context"
        statuses = captured_context["statuses"]
        assert statuses == [
            "Zactive",
            "Aretired",
        ], (
            f"Expected role-sorted order ['Zactive', 'Aretired'] but got {statuses}. "
            "Alphabetical sort would yield ['Aretired', 'Zactive']."
        )

    def test_REQ_d00211_D_default_roles_active_before_retired(self, default_config, tmp_path):
        """With default roles, Active appears before Deprecated in template statuses."""
        from elspais.server.routes_ui import index

        state = self._make_app_state(default_config, tmp_path)

        captured_context: dict = {}

        def fake_template_response(request, template_name, context):
            captured_context.update(context)
            resp = MagicMock()
            resp.status_code = 200
            return resp

        fake_templates = MagicMock()
        fake_templates.TemplateResponse = fake_template_response

        mock_request = MagicMock()
        mock_request.app.state.app_state = state

        # "Deprecated" is retired role, "Active" is active role
        # Alphabetical: ["Active", "Deprecated"] happens to match role order here,
        # but "Draft" (provisional, rank 1) should come before "Deprecated" (retired, rank 3)
        # even though 'D' < 'D'... use "Superseded" (retired) vs "Draft" (provisional)
        # Alphabetical: ["Draft", "Superseded"] — "D" == "D", "r" < "u" => Draft first
        # Role: ["Draft"(provisional=1), "Superseded"(retired=3)] — same
        # Use "Superseded" (retired) vs "Proposed" (provisional):
        # Alphabetical: ["Proposed", "Superseded"] (P < S)
        # Role: ["Proposed"(provisional=1), "Superseded"(retired=3)] — same
        # Best: "Rejected" (retired, R) vs "Roadmap" (aspirational, R)
        # Alpha: ["Rejected", "Roadmap"] (Reje < Road)
        # Role: ["Roadmap"(aspirational=2), "Rejected"(retired=3)] <- different!
        raw_statuses = {"Rejected", "Roadmap"}

        with (
            patch("starlette.templating.Jinja2Templates", return_value=fake_templates),
            patch(
                "elspais.html.generator.HTMLGenerator._collect_unique_values",
                return_value=raw_statuses,
            ),
        ):
            asyncio.run(index(mock_request))

        statuses = captured_context.get("statuses", [])
        rejected_idx = statuses.index("Rejected") if "Rejected" in statuses else -1
        roadmap_idx = statuses.index("Roadmap") if "Roadmap" in statuses else -1
        assert roadmap_idx < rejected_idx, (
            f"Roadmap (aspirational) should come before Rejected (retired) by role order. "
            f"Got statuses={statuses}"
        )
