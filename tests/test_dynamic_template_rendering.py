"""Integration tests: templates render with arbitrary level/namespace/status sets."""

# Verifies: REQ-d00211, REQ-p00006-A, REQ-p00006-B

from __future__ import annotations

import pytest

from elspais.config.schema import ElspaisConfig
from elspais.server.routes_ui import build_levels, build_namespaces, build_statuses


@pytest.fixture
def jinja_env():
    """Jinja environment matching the one used by HTMLGenerator."""
    pytest.importorskip("jinja2")
    from jinja2 import Environment, PackageLoader, select_autoescape

    return Environment(
        loader=PackageLoader("elspais.html", "templates"),
        autoescape=select_autoescape(["html", "xml"]),
    )


@pytest.fixture
def typed_5_level_config():
    return ElspaisConfig.model_validate(
        {
            "levels": {
                "prd": {"rank": 1, "letter": "p", "display_name": "Product", "implements": ["prd"]},
                "ops": {
                    "rank": 2,
                    "letter": "o",
                    "display_name": "Operations",
                    "implements": ["ops", "prd"],
                },
                "dev": {
                    "rank": 3,
                    "letter": "d",
                    "display_name": "Development",
                    "implements": ["dev", "ops", "prd"],
                },
                "gui": {
                    "rank": 4,
                    "letter": "g",
                    "display_name": "GUI",
                    "implements": ["gui", "dev"],
                    "color": "#7c3aed",
                },
                "infra": {
                    "rank": 5,
                    "letter": "i",
                    "display_name": "Infra",
                    "implements": ["infra"],
                },
            },
            "project": {"namespace": "CAL", "name": "Callisto"},
            "associates": {"diary": {"path": "../d", "namespace": "DIARY"}},
            "rules": {"format": {"status_roles": {"active": ["Active", "Legacy"]}}},
            "statuses": {"Active": {"color": "#198754"}},
        }
    )


def test_header_template_emits_one_badge_per_level(jinja_env, typed_5_level_config):
    levels = build_levels(typed_5_level_config)
    namespaces = build_namespaces(typed_5_level_config)
    tmpl = jinja_env.get_template("partials/_header.html.j2")
    html = tmpl.render(
        levels=levels,
        namespaces=namespaces,
        statuses=[],
        version="0.0.0",
        repo_name="test",
        mode="view",
        catalog=type("C", (), {"themes": []})(),
    )
    # All five level keys present with stat-level-{key} ID
    for key in ("prd", "ops", "dev", "gui", "infra"):
        assert f'id="stat-level-{key}"' in html, f"missing badge for {key}"
        assert f"{key.upper()}:" in html
    # No literal "Core:" anywhere
    assert "Core:" not in html
    # Local namespace label appears
    assert "Callisto:" in html


def test_status_badges_css_emits_selector_per_status(jinja_env, typed_5_level_config):
    statuses = build_statuses(typed_5_level_config)
    tmpl = jinja_env.get_template("partials/css/_status-badges.css.j2")
    css = tmpl.render(statuses=statuses)
    assert ".status-badge.active" in css
    assert ".status-badge.legacy" in css


def test_status_badges_css_uses_configured_color(jinja_env, typed_5_level_config):
    statuses = build_statuses(typed_5_level_config)
    tmpl = jinja_env.get_template("partials/css/_status-badges.css.j2")
    css = tmpl.render(statuses=statuses)
    # Active was configured with #198754
    active_block_idx = css.lower().index(".status-badge.active")
    next_brace = css.index("}", active_block_idx)
    block = css[active_block_idx:next_brace]
    assert "#198754" in block


def test_nav_tree_js_injects_levels_and_namespaces(jinja_env, typed_5_level_config):
    levels = build_levels(typed_5_level_config)
    namespaces = build_namespaces(typed_5_level_config)
    tmpl = jinja_env.get_template("partials/js/_nav-tree.js.j2")
    js = tmpl.render(levels=levels, namespaces=namespaces, statuses=[], config_types=[])
    assert "var LEVELS = " in js
    assert "var NAMESPACES = " in js
    # 'gui' key should appear in the injected JSON
    assert '"gui"' in js
    # local namespace CAL and associate DIARY should appear
    assert '"CAL"' in js
    assert '"DIARY"' in js
    # Legacy 'CORE' literal must be gone from the live check
    assert "!== 'CORE'" not in js


def test_header_namespace_badge_uses_local_label(jinja_env, typed_5_level_config):
    namespaces = build_namespaces(typed_5_level_config)
    tmpl = jinja_env.get_template("partials/_header.html.j2")
    html = tmpl.render(
        levels=build_levels(typed_5_level_config),
        namespaces=namespaces,
        statuses=[],
        version="0.0.0",
        repo_name="test",
        mode="view",
        catalog=type("C", (), {"themes": []})(),
    )
    # is_local entry's label is "Callisto" (from project.name)
    assert "Callisto:" in html
    # data-namespace attribute set to the local namespace code
    assert 'data-namespace="CAL"' in html
