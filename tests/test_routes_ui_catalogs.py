"""Tests for viewer config catalog builders (levels, namespaces, statuses)."""

# Verifies: REQ-d00211

from __future__ import annotations

from elspais.config.schema import ElspaisConfig
from elspais.server.routes_ui import (
    _extract_viewer_config,
    build_levels,
    build_namespaces,
    build_statuses,
    local_namespace_from_config,
)


def _typed(cfg: dict) -> ElspaisConfig:
    return ElspaisConfig.model_validate(cfg)


def test_build_levels_sorts_by_rank():
    typed = _typed(
        {
            "levels": {
                "dev": {"rank": 3, "letter": "d", "implements": ["dev"]},
                "prd": {"rank": 1, "letter": "p", "implements": ["prd"]},
                "ops": {"rank": 2, "letter": "o", "implements": ["ops"]},
            }
        }
    )
    out = build_levels(typed)
    assert [entry["key"] for entry in out] == ["prd", "ops", "dev"]
    for entry in out:
        assert entry["bg"].startswith("#") and len(entry["bg"]) == 7


def test_build_levels_uses_configured_color():
    typed = _typed(
        {
            "levels": {
                "gui": {
                    "rank": 4,
                    "letter": "g",
                    "implements": ["gui"],
                    "color": "#7c3aed",
                }
            }
        }
    )
    out = build_levels(typed)
    assert out[0]["bg"] == "#7c3aed"


def test_build_namespaces_local_first():
    typed = _typed(
        {
            "project": {"namespace": "CAL", "name": "Callisto"},
            "associates": {
                "diary": {"path": "../d", "namespace": "DIARY"},
                "phoenix": {"path": "../p", "namespace": "PHX"},
            },
        }
    )
    out = build_namespaces(typed)
    assert out[0]["is_local"] is True
    assert out[0]["code"] == "CAL"
    assert [n["code"] for n in out] == ["CAL", "DIARY", "PHX"]
    assert sum(1 for n in out if n["is_local"]) == 1


def test_load_config_replaces_default_levels_when_user_provides_levels(tmp_path):
    """Regression: a user config with uppercase [levels.PRD] must not coexist
    with the lowercase default [levels.prd] in the merged config."""
    from elspais.config import load_config

    cfg_path = tmp_path / ".elspais.toml"
    cfg_path.write_text(
        "version = 4\n"
        '[project]\nname = "test"\nnamespace = "DIARY"\n'
        '[levels.PRD]\nrank = 1\nletter = "p"\nimplements = ["PRD"]\n'
        '[levels.DEV]\nrank = 2\nletter = "d"\nimplements = ["DEV", "PRD"]\n'
    )
    cfg = load_config(cfg_path)
    assert set(cfg["levels"].keys()) == {
        "PRD",
        "DEV",
    }, f"Expected only user-defined levels; got {list(cfg['levels'].keys())}"


def test_build_namespaces_label_is_namespace_code():
    typed = _typed({"project": {"namespace": "CAL", "name": "Callisto"}})
    out = build_namespaces(typed)
    # Label is the namespace code (used for header badge). The friendly project
    # name is exposed separately so a single project_name can be rendered
    # elsewhere (e.g. the page title).
    assert out[0]["label"] == "CAL"
    assert out[0]["project_name"] == "Callisto"


def test_build_statuses_uses_configured_color_for_named_status():
    typed = _typed(
        {
            "rules": {"format": {"status_roles": {"active": ["Active"]}}},
            "statuses": {"Active": {"color": "#198754"}},
        }
    )
    out = build_statuses(typed)
    assert out[0]["key"] == "Active"
    assert out[0]["bg"] == "#198754"


def test_build_statuses_falls_back_for_unconfigured():
    typed = _typed({"rules": {"format": {"status_roles": {"retired": ["Legacy"]}}}})
    out = build_statuses(typed)
    assert out[0]["key"] == "Legacy"
    # Hashed fallback color; check format only
    assert out[0]["bg"].startswith("#") and len(out[0]["bg"]) == 7


def test_build_statuses_respects_candidate_order():
    typed = _typed({"rules": {"format": {"status_roles": {"active": ["A", "B"]}}}})
    out = build_statuses(typed, candidates=["B", "A"])
    assert [s["key"] for s in out] == ["B", "A"]


def test_extract_viewer_config_returns_lists():
    cfg = {
        "project": {"namespace": "CAL"},
        "levels": {"prd": {"rank": 1, "letter": "p", "implements": ["prd"]}},
    }
    out = _extract_viewer_config(cfg)
    assert "levels" in out
    assert "namespaces" in out
    # statuses is intentionally omitted from this helper; the index route
    # populates it from graph data with role-sorted candidates.
    assert "statuses" not in out


def test_local_namespace_from_config():
    assert local_namespace_from_config({"project": {"namespace": "CAL"}}) == "CAL"
    assert local_namespace_from_config({}) == "REQ"  # default


def test_extract_viewer_config_tolerates_invalid():
    out = _extract_viewer_config({"levels": "not a dict"})
    assert isinstance(out["levels"], list)


def test_build_namespaces_includes_tint():
    typed = _typed(
        {
            "project": {"namespace": "CAL", "color": "#1b3a5c"},
            "associates": {"diary": {"path": "../d", "namespace": "DIARY"}},
        }
    )
    out = build_namespaces(typed)
    for entry in out:
        assert "tint" in entry, f"missing tint on {entry['code']}"
        assert entry["tint"].startswith("rgba("), entry["tint"]
    # Configured local color produces a tint derived from that hex
    assert out[0]["tint"] == "rgba(27, 58, 92, 0.12)"
