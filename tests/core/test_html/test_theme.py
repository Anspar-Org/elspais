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
        # Spot-check key tokens. Per-status palette entries are removed in
        # favor of per-key dynamic colors (resolved at render time).
        assert "--primary:" in css
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


class TestSeverityCatalog:
    """Test severity colors resolved through the theme catalog (REQ-d00258-D)."""

    # Verifies: REQ-d00258-D
    def test_severity_entries_in_catalog(self):
        from elspais.html.theme import get_catalog

        cat = get_catalog()
        for sev, color in (
            ("ok", "green"),
            ("info", "yellow-green"),
            ("warning", "yellow"),
            ("error", "red"),
        ):
            entry = cat.by_key(f"severity.{sev}")
            assert entry.color_key == color

    # Verifies: REQ-d00258-D
    def test_no_hardcoded_severity_dict(self):
        import elspais.html.generator as g

        assert not hasattr(g, "SEVERITY_TO_COLOR")

    # Verifies: REQ-d00258-D
    def test_tiers_payload_has_bucket(self, canonical_graph, canonical_config):
        from elspais.graph.GraphNode import NodeKind
        from elspais.html.generator import compute_coverage_tiers

        node = next(
            n
            for n in canonical_graph.nodes_by_kind(NodeKind.REQUIREMENT)
            if (n.status or "").upper() == "ACTIVE" and n.get_metric("rollup_metrics")
        )
        tiers = compute_coverage_tiers(node, canonical_config)
        assert tiers["combined_bucket"] in ("full", "partial", "none", "failing")
        assert "verified_tier" in tiers

    def _make_active_node_with_metrics(self, rollup):
        """Build a minimal Active requirement node and attach rollup metrics."""
        from tests.core.graph_test_helpers import build_graph, make_requirement

        graph = build_graph(
            make_requirement("REQ-p00001", title="Test Req", status="Active"),
        )
        node = graph.find_by_id("REQ-p00001")
        node.set_metric("rollup_metrics", rollup)
        return node

    # Verifies: REQ-d00258-D, REQ-d00258-E
    def test_bucket_full_despite_uat_none(self):
        """No-journey project: uat tiers 'none' map to info severity (default
        config) and must NOT drag the bucket below 'full' (design section 2.3)."""
        from elspais.graph.metrics import CoverageDimension, RollupMetrics
        from elspais.html.generator import compute_coverage_tiers

        rollup = RollupMetrics(
            total_assertions=2,
            implemented=CoverageDimension(total=2, direct=2, indirect=2),
            tested=CoverageDimension(total=2, direct=2, indirect=2),
            verified=CoverageDimension(total=2, direct=2, indirect=2),
            uat_coverage=CoverageDimension(total=2, direct=0, indirect=0),
            uat_verified=CoverageDimension(total=2, direct=0, indirect=0),
        )
        node = self._make_active_node_with_metrics(rollup)
        tiers = compute_coverage_tiers(node)

        assert tiers["uat_cov_tier"] == "none"
        assert tiers["combined_bucket"] == "full"

    # Verifies: REQ-d00258-D, REQ-d00258-E
    def test_bucket_none_when_implemented_none(self):
        """implemented tier 'none' maps to error severity -> bucket 'none'."""
        from elspais.graph.metrics import CoverageDimension, RollupMetrics
        from elspais.html.generator import compute_coverage_tiers

        rollup = RollupMetrics(
            total_assertions=2,
            implemented=CoverageDimension(total=2, direct=0, indirect=0),
            tested=CoverageDimension(total=2, direct=2, indirect=2),
            verified=CoverageDimension(total=2, direct=2, indirect=2),
        )
        node = self._make_active_node_with_metrics(rollup)
        tiers = compute_coverage_tiers(node)

        assert tiers["impl_tier"] == "none"
        assert tiers["combined_bucket"] == "none"

    # Verifies: REQ-d00258-D, REQ-d00258-E
    def test_bucket_failing_when_any_dim_fails(self):
        """has_failures on any dimension -> bucket 'failing' (overlay)."""
        from elspais.graph.metrics import CoverageDimension, RollupMetrics
        from elspais.html.generator import compute_coverage_tiers

        rollup = RollupMetrics(
            total_assertions=2,
            implemented=CoverageDimension(total=2, direct=2, indirect=2),
            tested=CoverageDimension(total=2, direct=2, indirect=2),
            verified=CoverageDimension(total=2, direct=1, indirect=1, has_failures=True),
        )
        node = self._make_active_node_with_metrics(rollup)
        tiers = compute_coverage_tiers(node)

        assert tiers["verified_tier"] == "failing"
        assert tiers["combined_bucket"] == "failing"

    # Verifies: REQ-d00258-B
    def test_passing_badge_credits_lcov_only_coverage(self):
        """A requirement fully credited via lcov only (no `Verifies:` refs at
        all) must still show a full "Passing" badge -- the 'verified' slot in
        compute_coverage_tiers is `tested_and_passing(rollup)`, the union of
        `verified` and `lcov_tested` (REQ-d00258-B), not the raw `verified`
        dimension. combined_bucket must not degrade to 'partial' solely
        because the evidence came from line coverage rather than a Verifies:
        reference."""
        from elspais.graph.metrics import CoverageDimension, RollupMetrics
        from elspais.html.generator import compute_coverage_tiers

        rollup = RollupMetrics(
            total_assertions=2,
            implemented=CoverageDimension(total=2, direct=2, indirect=2),
            tested=CoverageDimension(total=2, direct=2, indirect=2),
            # No Verifies: coverage at all on this dimension...
            verified=CoverageDimension(total=2, direct=0, indirect=0),
            # ...but full line-coverage credit via lcov_tested.
            lcov_tested=CoverageDimension(total=2, direct=2, indirect=2),
        )
        node = self._make_active_node_with_metrics(rollup)
        tiers = compute_coverage_tiers(node)

        assert tiers["verified_tier"] == "full-direct"
        assert tiers["combined_bucket"] == "full"
