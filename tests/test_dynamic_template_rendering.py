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
    # Local namespace label is the namespace code, not the project name
    assert "CAL:" in html
    assert "Callisto:" not in html


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


def test_nav_tree_status_filtergroup_emits_valid_js(jinja_env, typed_5_level_config):
    """Regression: the status FilterGroup must emit `{key: '<lower>', label: '<title>'}`
    objects, not the Python repr of the status dict (which crashes the page with
    `SyntaxError: Unexpected identifier 'key'`)."""
    from elspais.server.routes_ui import build_levels, build_statuses

    levels = build_levels(typed_5_level_config)
    statuses = build_statuses(typed_5_level_config)
    tmpl = jinja_env.get_template("partials/js/_nav-tree.js.j2")
    js = tmpl.render(
        levels=levels,
        namespaces=[],
        statuses=statuses,
        config_types=[],
        default_hidden_statuses=[],
    )
    # The buttons array entries must look like `{key: '<lower>', label: '<label>'}`
    assert "{key: 'active', label: 'Active'}" in js
    assert "{key: 'legacy', label: 'Legacy'}" in js
    # And the broken Python-repr stringification must not appear
    assert "'key': 'active'" not in js
    assert "'bg':" not in js


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
    # Local namespace badge shows the namespace code, not the project name
    assert "CAL:" in html
    # data-namespace attribute set to the local namespace code
    assert 'data-namespace="CAL"' in html


def test_toolbar_emits_tree_display_mode_select(jinja_env, typed_5_level_config):
    """The toolbar must render a six-option <select id='tree-display-mode'>
    so users can pick the nav-tree row layout."""
    levels = build_levels(typed_5_level_config)
    namespaces = build_namespaces(typed_5_level_config)
    statuses = build_statuses(typed_5_level_config)
    tmpl = jinja_env.get_template("partials/_toolbar.html.j2")
    html = tmpl.render(
        levels=levels,
        namespaces=namespaces,
        statuses=statuses,
        default_hidden_statuses=[],
    )
    assert 'id="tree-display-mode"' in html
    for value in ("compact", "title-only", "id-only", "full", "ns-bg"):
        assert f'value="{value}"' in html, f"missing option value '{value}'"
    # "Level at end" is now a separate checkbox toggle, not a display-mode option.
    assert 'value="level-last"' not in html, "level-last should be a toggle, not a mode"
    assert 'id="toggle-level-at-end"' in html, "missing 'Level at end' checkbox"


def test_term_card_skips_references_when_not_indexed(jinja_env, typed_5_level_config):
    """Term cards for non-indexed terms must omit the References section.
    Mirrors the term scanner's behaviour: `Indexed: false` suppresses
    plain-word reference collection upstream; the card view follows suit."""
    tmpl = jinja_env.get_template("partials/js/_card-stack.js.j2")
    js = tmpl.render(
        levels=build_levels(typed_5_level_config),
        namespaces=build_namespaces(typed_5_level_config),
        statuses=build_statuses(typed_5_level_config),
    )
    # The conditional short-circuit + early return is present.
    assert "data.indexed === false" in js, "missing the indexed=false guard"
    # The early return closes both wrapping divs (req-card-body + req-card).
    assert "html += '</div></div>';" in js


def test_nav_tree_row_template_emits_dual_id_and_sliver(jinja_env, typed_5_level_config):
    """Each requirement row must include both id spans + the ns sliver placeholder,
    plus per-mode title= / data-ns / --row-ns-tint plumbing. CSS toggles which
    pieces are visible per mode."""
    levels = build_levels(typed_5_level_config)
    namespaces = build_namespaces(typed_5_level_config)
    tmpl = jinja_env.get_template("partials/js/_nav-tree.js.j2")
    js = tmpl.render(levels=levels, namespaces=namespaces, statuses=[], config_types=[])
    # Both id spans present
    assert "nav-tree-id-full" in js
    assert "nav-tree-id-component" in js
    # Server-provided fields consumed
    assert "row.component" in js
    assert "row.ns_bg" in js
    assert "row.ns_tint" in js
    # Sliver element rendered
    assert "nav-tree-ns-sliver" in js
    # Per-row data-ns attribute
    assert "data-ns" in js
    # Per-row --row-ns-tint CSS custom property
    assert "--row-ns-tint" in js
    # Legacy single `<span class="nav-tree-id">` no longer used for requirement rows
    # (journey-row block is allowed to keep it; requirement rows must not).
    # We check there's no `'<span class="nav-tree-id">' + shortId` pattern left.
    assert "shortId" not in js
    assert "flshortId" not in js
