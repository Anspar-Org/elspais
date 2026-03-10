"""Tests for theme.py LegendCatalog."""

import pytest

from elspais.html.theme import LegendCatalog, get_catalog


class TestGetCatalog:
    """Test catalog loading and caching."""

    def test_REQ_p00006_A_returns_legend_catalog(self):
        catalog = get_catalog()
        assert isinstance(catalog, LegendCatalog)

    def test_REQ_p00006_A_caches_result(self):
        a = get_catalog()
        b = get_catalog()
        assert a is b


class TestThemes:
    """Test theme enumeration."""

    def test_REQ_p00006_A_has_light_and_dark(self):
        catalog = get_catalog()
        names = catalog.theme_names()
        assert "light" in names
        assert "dark" in names

    def test_REQ_p00006_A_first_theme_is_default(self):
        catalog = get_catalog()
        assert catalog.themes[0].name == "light"

    def test_REQ_p00006_A_themes_have_labels_and_icons(self):
        catalog = get_catalog()
        for t in catalog.themes:
            assert t.label
            assert t.icon


class TestCatalogEntries:
    """Test catalog entry lookup and joining."""

    def test_REQ_p00006_A_by_key_finds_entry(self):
        catalog = get_catalog()
        entry = catalog.by_key("icons.coverage.full")
        assert entry.label == "Full Coverage"
        assert entry.css_class == "coverage-icon full"

    def test_REQ_p00006_A_by_key_raises_for_missing(self):
        catalog = get_catalog()
        with pytest.raises(KeyError):
            catalog.by_key("nonexistent.key")

    def test_REQ_p00006_A_by_category_returns_entries(self):
        catalog = get_catalog()
        entries = catalog.by_category("badges.status")
        keys = [e.key for e in entries]
        assert "badges.status.draft" in keys
        assert "badges.status.active" in keys

    def test_REQ_p00006_A_entries_have_descriptions(self):
        catalog = get_catalog()
        entry = catalog.by_key("validation_tiers.full-direct")
        assert entry.description
        assert entry.long_description

    def test_REQ_p00006_A_validation_tiers_have_color_key(self):
        catalog = get_catalog()
        entry = catalog.by_key("validation_tiers.full-direct")
        assert entry.color_key == "green"


class TestCSSVariableGeneration:
    """Test CSS custom property output."""

    def test_REQ_p00006_A_generates_root_block(self):
        catalog = get_catalog()
        css = catalog.css_variables()
        assert ":root" in css
        assert "--body-bg:" in css

    def test_REQ_p00006_A_generates_dark_theme_block(self):
        catalog = get_catalog()
        css = catalog.css_variables()
        assert ".theme-dark" in css

    def test_REQ_p00006_A_all_tokens_present(self):
        catalog = get_catalog()
        css = catalog.css_variables()
        # Spot-check key tokens
        assert "--primary:" in css
        assert "--status-active-bg:" in css
        assert "--val-green-bg:" in css


class TestGroupedEntries:
    """Test legend modal grouping."""

    def test_REQ_p00006_A_returns_category_groups(self):
        catalog = get_catalog()
        groups = catalog.grouped_entries()
        cat_names = [name for name, _ in groups]
        assert "Coverage Status" in cat_names or "Coverage" in cat_names
        assert len(groups) >= 5  # at least 5 categories


class TestComputeValidationColorCatalog:
    """Test that compute_validation_color returns descriptions from the catalog."""

    def _make_active_node_with_metrics(self, rollup):
        """Build a minimal Active requirement node and attach rollup metrics."""
        from tests.core.graph_test_helpers import build_graph, make_requirement

        graph = build_graph(
            make_requirement("REQ-p00001", title="Test Req", status="Active"),
        )
        node = graph.find_by_id("REQ-p00001")
        node.set_metric("rollup_metrics", rollup)
        return node

    def test_REQ_p00006_A_green_description_from_catalog(self):
        """Green tier: full direct coverage, all assertions validated, no failures."""
        from elspais.graph.metrics import RollupMetrics
        from elspais.html.generator import compute_validation_color
        from elspais.html.theme import get_catalog

        catalog = get_catalog()
        expected_entry = catalog.by_key("validation_tiers.full-direct")

        rollup = RollupMetrics(
            total_assertions=2,
            coverage_pct=100.0,
            validated=2,
            has_failures=False,
        )
        node = self._make_active_node_with_metrics(rollup)
        css_suffix, description = compute_validation_color(node)

        assert css_suffix == expected_entry.color_key
        assert description == expected_entry.description

    def test_REQ_p00006_A_red_description_from_catalog(self):
        """Red tier: has test failures."""
        from elspais.graph.metrics import RollupMetrics
        from elspais.html.generator import compute_validation_color
        from elspais.html.theme import get_catalog

        catalog = get_catalog()
        expected_entry = catalog.by_key("validation_tiers.failing")

        rollup = RollupMetrics(
            total_assertions=2,
            coverage_pct=50.0,
            validated=1,
            has_failures=True,
        )
        node = self._make_active_node_with_metrics(rollup)
        css_suffix, description = compute_validation_color(node)

        assert css_suffix == expected_entry.color_key
        assert description == expected_entry.description

    def test_REQ_p00006_A_yellow_description_from_catalog(self):
        """Yellow tier: partial coverage, no failures."""
        from elspais.graph.metrics import RollupMetrics
        from elspais.html.generator import compute_validation_color
        from elspais.html.theme import get_catalog

        catalog = get_catalog()
        expected_entry = catalog.by_key("validation_tiers.partial")

        rollup = RollupMetrics(
            total_assertions=3,
            coverage_pct=33.0,
            indirect_coverage_pct=33.0,
            validated=1,
            has_failures=False,
        )
        node = self._make_active_node_with_metrics(rollup)
        css_suffix, description = compute_validation_color(node)

        assert css_suffix == expected_entry.color_key
        assert description == expected_entry.description

    def test_REQ_p00006_A_yellow_green_description_from_catalog(self):
        """Yellow-green tier: full indirect coverage, all validated indirectly."""
        from elspais.graph.metrics import RollupMetrics
        from elspais.html.generator import compute_validation_color
        from elspais.html.theme import get_catalog

        catalog = get_catalog()
        expected_entry = catalog.by_key("validation_tiers.full-indirect")

        rollup = RollupMetrics(
            total_assertions=2,
            coverage_pct=0.0,
            indirect_coverage_pct=100.0,
            validated=0,
            validated_with_indirect=2,
            has_failures=False,
        )
        node = self._make_active_node_with_metrics(rollup)
        css_suffix, description = compute_validation_color(node)

        assert css_suffix == expected_entry.color_key
        assert description == expected_entry.description

    def test_REQ_p00006_A_orange_description_from_catalog(self):
        """Orange tier: assertions exist but zero coverage (anomalous)."""
        from elspais.graph.metrics import RollupMetrics
        from elspais.html.generator import compute_validation_color
        from elspais.html.theme import get_catalog

        catalog = get_catalog()
        expected_entry = catalog.by_key("validation_tiers.anomalous")

        rollup = RollupMetrics(
            total_assertions=2,
            coverage_pct=0.0,
            indirect_coverage_pct=0.0,
            validated=0,
            has_failures=False,
        )
        node = self._make_active_node_with_metrics(rollup)
        css_suffix, description = compute_validation_color(node)

        assert css_suffix == expected_entry.color_key
        assert description == expected_entry.description
