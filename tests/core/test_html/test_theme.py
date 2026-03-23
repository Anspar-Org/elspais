"""Tests for theme.py LegendCatalog."""

import pytest

from elspais.html.theme import LegendCatalog, get_catalog


class TestGetCatalog:
    """Test catalog loading and caching."""

    def test_REQ_p00006_A_returns_legend_catalog(self):
        catalog = get_catalog()
        assert isinstance(catalog, LegendCatalog)
        assert len(catalog.themes) > 0
        assert len(catalog.grouped_entries()) > 0

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
        entry = catalog.by_key("icons.change.unsaved")
        assert entry.label == "Unsaved"
        assert entry.css_class == "change-indicator unsaved"

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
        assert "Change Indicators" in cat_names
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
        """Green tier: full direct coverage on implemented dimension."""
        from elspais.graph.metrics import CoverageDimension, RollupMetrics
        from elspais.html.generator import compute_coverage_tiers
        from elspais.html.theme import get_catalog

        catalog = get_catalog()
        expected_entry = catalog.by_key("validation_tiers.full-direct")

        rollup = RollupMetrics(
            total_assertions=2,
            implemented=CoverageDimension(total=2, direct=2, indirect=2),
            tested=CoverageDimension(total=2, direct=2, indirect=2),
            verified=CoverageDimension(total=2, direct=2, indirect=2),
        )
        node = self._make_active_node_with_metrics(rollup)
        tiers = compute_coverage_tiers(node)

        assert tiers["impl_color"] == expected_entry.color_key

    def test_REQ_p00006_A_red_description_from_catalog(self):
        """Red tier: has test failures on verified dimension."""
        from elspais.graph.metrics import CoverageDimension, RollupMetrics
        from elspais.html.generator import compute_coverage_tiers
        from elspais.html.theme import get_catalog

        catalog = get_catalog()
        expected_entry = catalog.by_key("validation_tiers.failing")

        rollup = RollupMetrics(
            total_assertions=2,
            implemented=CoverageDimension(total=2, direct=1, indirect=1),
            tested=CoverageDimension(total=2, direct=1, indirect=1),
            verified=CoverageDimension(total=2, direct=1, indirect=1, has_failures=True),
        )
        node = self._make_active_node_with_metrics(rollup)
        tiers = compute_coverage_tiers(node)

        assert tiers["verified_color"] == expected_entry.color_key
        assert tiers["combined_color"] == expected_entry.color_key

    def test_REQ_p00006_A_yellow_description_from_catalog(self):
        """Yellow tier: partial coverage on implemented dimension."""
        from elspais.graph.metrics import CoverageDimension, RollupMetrics
        from elspais.html.generator import compute_coverage_tiers
        from elspais.html.theme import get_catalog

        catalog = get_catalog()
        expected_entry = catalog.by_key("validation_tiers.partial")

        rollup = RollupMetrics(
            total_assertions=3,
            implemented=CoverageDimension(total=3, direct=1, indirect=1),
            tested=CoverageDimension(total=3, direct=1, indirect=1),
            verified=CoverageDimension(total=3, direct=1, indirect=1),
        )
        node = self._make_active_node_with_metrics(rollup)
        tiers = compute_coverage_tiers(node)

        assert tiers["impl_color"] == expected_entry.color_key
        assert tiers["combined_color"] == expected_entry.color_key

    def test_REQ_p00006_A_yellow_green_description_from_catalog(self):
        """Yellow-green tier: full indirect coverage on implemented dimension."""
        from elspais.graph.metrics import CoverageDimension, RollupMetrics
        from elspais.html.generator import compute_coverage_tiers
        from elspais.html.theme import get_catalog

        catalog = get_catalog()
        expected_entry = catalog.by_key("validation_tiers.full-indirect")

        rollup = RollupMetrics(
            total_assertions=2,
            implemented=CoverageDimension(total=2, direct=0, indirect=2),
            tested=CoverageDimension(total=2, direct=0, indirect=2),
            verified=CoverageDimension(total=2, direct=0, indirect=2),
        )
        node = self._make_active_node_with_metrics(rollup)
        tiers = compute_coverage_tiers(node)

        assert tiers["impl_color"] == expected_entry.color_key
        assert tiers["combined_color"] == expected_entry.color_key

    def test_REQ_p00006_A_orange_description_from_catalog(self):
        """Orange/anomalous tier: zero coverage maps to error/red on implemented dimension."""
        from elspais.graph.metrics import CoverageDimension, RollupMetrics
        from elspais.html.generator import compute_coverage_tiers
        from elspais.html.theme import get_catalog

        catalog = get_catalog()
        # With the new per-dimension tiers, "none" coverage maps to "error" severity
        # which is "red" color, not the old single-tier "orange"
        expected_entry = catalog.by_key("validation_tiers.failing")

        rollup = RollupMetrics(
            total_assertions=2,
            implemented=CoverageDimension(total=2, direct=0, indirect=0),
            tested=CoverageDimension(total=2, direct=0, indirect=0),
            verified=CoverageDimension(total=2, direct=0, indirect=0),
        )
        node = self._make_active_node_with_metrics(rollup)
        tiers = compute_coverage_tiers(node)

        assert tiers["impl_color"] == expected_entry.color_key
        assert tiers["combined_color"] == expected_entry.color_key
