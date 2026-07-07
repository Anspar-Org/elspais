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
        entry = catalog.by_key("coverage_caveat.indirect")
        assert entry.description
        assert entry.long_description

    def test_REQ_p00006_A_coverage_standing_have_color_key(self):
        catalog = get_catalog()
        entry = catalog.by_key("coverage_standing.full")
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
        # The unified vocabulary collapses full-direct/full-indirect into the
        # single `full` tier -> severity `ok` -> green.
        expected_entry = catalog.by_key("severity.ok")

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
        # A failing tier resolves to error severity -> red in the badge color.
        expected_entry = catalog.by_key("severity.error")

        # A/B both implemented and tested; the Passing dim FAILS on A (within the
        # tested denominator) -> relative 'failing' tier -> red (REQ-d00258-B).
        rollup = RollupMetrics(
            total_assertions=2,
            implemented=CoverageDimension(
                total=2,
                direct=2,
                indirect=2,
                direct_pct_by_label={"A": 1.0, "B": 1.0},
                indirect_pct_by_label={"A": 1.0, "B": 1.0},
            ),
            tested=CoverageDimension(
                total=2,
                direct=2,
                indirect=2,
                direct_pct_by_label={"A": 1.0, "B": 1.0},
                indirect_pct_by_label={"A": 1.0, "B": 1.0},
            ),
            verified=CoverageDimension(
                total=2,
                direct=1,
                indirect=1,
                has_failures=True,
                failing_labels={"A"},
                direct_pct_by_label={"B": 1.0},
                indirect_pct_by_label={"B": 1.0},
            ),
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
        # A partial tier resolves to warning severity -> yellow.
        expected_entry = catalog.by_key("severity.warning")

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

    def test_REQ_d00258_full_indirect_collapses_to_green(self):
        """Under the unified vocabulary (REQ-d00258) a fully-but-indirectly
        covered dimension collapses to the ``full`` tier -> severity ``ok`` ->
        green, NOT the retired yellow-green ``full-indirect`` distinction (which
        now moves to the ~ marker/hover in a later phase)."""
        from elspais.graph.metrics import CoverageDimension, RollupMetrics
        from elspais.html.generator import compute_coverage_tiers
        from elspais.html.theme import get_catalog

        catalog = get_catalog()
        green = catalog.by_key("severity.ok").color_key

        # A/B fully-but-INDIRECTLY covered on every dimension: implemented over
        # all assertions (absolute), tested over implemented labels, verified
        # over tested labels -- each resolves to the ``full`` tier.
        rollup = RollupMetrics(
            total_assertions=2,
            implemented=CoverageDimension(
                total=2,
                direct=0,
                indirect=2,
                indirect_pct_by_label={"A": 1.0, "B": 1.0},
            ),
            tested=CoverageDimension(
                total=2,
                direct=0,
                indirect=2,
                indirect_pct_by_label={"A": 1.0, "B": 1.0},
            ),
            verified=CoverageDimension(
                total=2,
                direct=0,
                indirect=2,
                indirect_pct_by_label={"A": 1.0, "B": 1.0},
            ),
        )
        node = self._make_active_node_with_metrics(rollup)
        tiers = compute_coverage_tiers(node)

        # The fully-but-indirectly-covered dimensions now read the ``full`` tier
        # and resolve to green (ok), no longer the retired yellow-green split.
        for prefix in ("impl", "tested", "verified"):
            assert tiers[f"{prefix}_tier"] == "full"
            assert tiers[f"{prefix}_color"] == green

    def test_REQ_p00006_A_orange_description_from_catalog(self):
        """Orange/anomalous tier: zero coverage maps to error/red on implemented dimension."""
        from elspais.graph.metrics import CoverageDimension, RollupMetrics
        from elspais.html.generator import compute_coverage_tiers
        from elspais.html.theme import get_catalog

        catalog = get_catalog()
        # With the unified vocabulary, "missing" coverage maps to "error" severity
        # which is "red" color, not the old single-tier "orange"
        expected_entry = catalog.by_key("severity.error")

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
    def test_failing_severity_has_own_maroon_color_distinct_from_error(self):
        """The toolbar's "failing" coverage chip resolves through the theme
        catalog like the other severities (CUR-1568), with its own color_key
        so it stays visually distinct from severity.error/"missing"."""
        from elspais.html.theme import get_catalog

        cat = get_catalog()
        failing = cat.by_key("severity.failing")
        error = cat.by_key("severity.error")
        assert failing.color_key == "maroon"
        assert failing.color_key != error.color_key
        assert failing.css_class == "val-maroon"
        assert failing.label == "Failing"

    # Verifies: REQ-d00258-D
    def test_failing_color_tokens_defined_for_both_themes(self):
        """`--val-maroon-bg` must exist in both themes.light.tokens and
        themes.dark.tokens so the toolbar chip stays legible when switching
        themes (not just hardcoded for one)."""
        from elspais.html.theme import get_catalog

        cat = get_catalog()
        theme_names = {t.name for t in cat.themes}
        assert {"light", "dark"} <= theme_names
        for theme in cat.themes:
            assert "val-maroon-bg" in theme.tokens
            assert theme.tokens["val-maroon-bg"].startswith("#")

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
        assert tiers["combined_bucket"] in ("full", "partial", "missing", "failing")
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

        assert tiers["uat_cov_tier"] == "missing"
        assert tiers["combined_bucket"] == "full"

    # Verifies: REQ-d00258-D, REQ-d00258-E
    def test_uat_partial_maps_to_warning_not_info(self):
        """A journey that PARTIALLY validates a requirement must surface a real
        'partial' state: uat 'partial' tier maps to severity 'warning' (yellow),
        not 'info' (yellow-green). UAT 'none' stays 'info' so a journey-less
        requirement is not dragged down (see test_bucket_full_despite_uat_none).
        Colors represent the real state (CUR-1568)."""
        from elspais.graph.metrics import CoverageDimension, RollupMetrics
        from elspais.html.generator import compute_coverage_tiers

        rollup = RollupMetrics(
            total_assertions=2,
            implemented=CoverageDimension(total=2, direct=2, indirect=2),
            tested=CoverageDimension(total=2, direct=2, indirect=2),
            verified=CoverageDimension(total=2, direct=2, indirect=2),
            # A journey validates 1 of 2 assertions -> partial.
            uat_coverage=CoverageDimension(total=2, direct=1, indirect=1),
        )
        node = self._make_active_node_with_metrics(rollup)
        tiers = compute_coverage_tiers(node)

        assert tiers["uat_cov_tier"] == "partial"
        # warning -> yellow (was info -> yellow-green under the old default)
        assert tiers["uat_cov_color"] == "yellow"
        # warning drags the severity-aware bucket to 'partial'
        assert tiers["combined_bucket"] == "partial"

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

        assert tiers["impl_tier"] == "missing"
        assert tiers["combined_bucket"] == "missing"

    # Verifies: REQ-d00258-D, REQ-d00258-E
    def test_bucket_failing_when_any_dim_fails(self):
        """has_failures on any dimension -> bucket 'failing' (overlay)."""
        from elspais.graph.metrics import CoverageDimension, RollupMetrics
        from elspais.html.generator import compute_coverage_tiers

        # A/B implemented+tested; Passing fails on A (within the tested
        # denominator) -> relative 'failing' overlay drives combined bucket.
        rollup = RollupMetrics(
            total_assertions=2,
            implemented=CoverageDimension(
                total=2,
                direct=2,
                indirect=2,
                direct_pct_by_label={"A": 1.0, "B": 1.0},
                indirect_pct_by_label={"A": 1.0, "B": 1.0},
            ),
            tested=CoverageDimension(
                total=2,
                direct=2,
                indirect=2,
                direct_pct_by_label={"A": 1.0, "B": 1.0},
                indirect_pct_by_label={"A": 1.0, "B": 1.0},
            ),
            verified=CoverageDimension(
                total=2,
                direct=1,
                indirect=1,
                has_failures=True,
                failing_labels={"A"},
                direct_pct_by_label={"B": 1.0},
                indirect_pct_by_label={"B": 1.0},
            ),
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
            implemented=CoverageDimension(
                total=2,
                direct=2,
                indirect=2,
                direct_pct_by_label={"A": 1.0, "B": 1.0},
                indirect_pct_by_label={"A": 1.0, "B": 1.0},
            ),
            tested=CoverageDimension(
                total=2,
                direct=2,
                indirect=2,
                direct_pct_by_label={"A": 1.0, "B": 1.0},
                indirect_pct_by_label={"A": 1.0, "B": 1.0},
            ),
            # No Verifies: coverage at all on this dimension...
            verified=CoverageDimension(total=2, direct=0, indirect=0),
            # ...but full line-coverage credit via lcov_tested (label-keyed so
            # tested_and_passing() credits the tested denominator labels).
            lcov_tested=CoverageDimension(
                total=2,
                direct=2,
                indirect=2,
                direct_pct_by_label={"A": 1.0, "B": 1.0},
                indirect_pct_by_label={"A": 1.0, "B": 1.0},
            ),
        )
        node = self._make_active_node_with_metrics(rollup)
        tiers = compute_coverage_tiers(node)

        assert tiers["verified_tier"] == "full"
        assert tiers["combined_bucket"] == "full"

    # Verifies: REQ-d00258-F
    def test_expects_validation_uat_none_is_red_and_drags(self):
        """When the requirement's level expects_validation, a UAT 'none' tier
        resolves to error severity (red) and drags combined_bucket to 'none';
        the tiers payload advertises expects_validation for the JS gate."""
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
        node = self._make_active_node_with_metrics(rollup)  # level PRD
        config = {"levels": {"prd": {"expects_validation": True}}}
        tiers = compute_coverage_tiers(node, config)

        assert tiers["uat_cov_tier"] == "missing"
        assert tiers["uat_cov_color"] == "red"
        assert tiers["expects_validation"] is True
        # error severity on a UAT dim drags the combined bucket to 'none'.
        assert tiers["combined_bucket"] == "missing"

    # Verifies: REQ-d00258-F
    def test_non_expecting_level_uat_none_stays_soft(self):
        """A level that does NOT expect_validation keeps the soft UAT 'none'
        (info, does not drag) -- preserves test_bucket_full_despite_uat_none."""
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
        node = self._make_active_node_with_metrics(rollup)  # level PRD
        # Config where prd does NOT expect validation.
        config = {"levels": {"prd": {"expects_validation": False}}}
        tiers = compute_coverage_tiers(node, config)

        assert tiers["uat_cov_tier"] == "missing"
        assert tiers["expects_validation"] is False
        # soft 'none' -> info -> does not drag the bucket below 'full'.
        assert tiers["combined_bucket"] == "full"


class TestUnifiedSeverityVocabulary:
    """CoverageSeverityConfig and the tier->severity map use the unified
    {full,partial,failing,missing} vocabulary (REQ-d00258). The legacy
    full_direct/full_indirect/none keys are gone; ``missing`` replaces ``none``.
    """

    # Verifies: REQ-d00258-A
    def test_severity_config_default_keys(self):
        """Default severities: full->ok, partial->warning, failing/missing->error."""
        from elspais.config.schema import CoverageSeverityConfig

        cfg = CoverageSeverityConfig()
        assert cfg.full == "ok"
        assert cfg.partial == "warning"
        assert cfg.failing == "error"
        assert cfg.missing == "error"
        assert not hasattr(cfg, "full_direct")
        assert not hasattr(cfg, "none")

    # Verifies: REQ-d00258-A
    def test_uat_severity_softens_missing_to_info(self):
        """UAT dimensions soften a ``missing`` tier to info (journey-less reqs
        are not dragged down by default)."""
        from elspais.config.schema import _uat_severity

        assert _uat_severity().missing == "info"

    # Verifies: REQ-d00258-A
    def test_verified_default_softens_missing_to_warning(self):
        """The 'verified' (Passing) dimension keeps its softening on the new
        key: a ``missing`` tier is a warning, not an error."""
        from elspais.config.schema import CoverageConfig

        assert CoverageConfig().verified.missing == "warning"

    # Verifies: REQ-d00258-A
    def test_tier_to_severity_missing_is_error(self):
        """_tier_to_severity resolves the unified single-word tier directly."""
        from elspais.config.schema import CoverageSeverityConfig
        from elspais.html.generator import _tier_to_severity

        cfg = CoverageSeverityConfig()
        assert _tier_to_severity("missing", cfg) == "error"
        assert _tier_to_severity("full", cfg) == "ok"


class TestStatusRoleGating:
    """compute_coverage_tiers renders coverage badges for EVERY status
    (REQ-d00258, Phase 3). The status no longer blanks the payload; it only
    gates whether a `missing` Implemented tier is a red gap (status expects
    implementation) or neutral grey (it does not). The only remaining empty
    payload is the genuine no-assertions case.

    Regression history: the viewer once gated on ``status != "ACTIVE"`` and
    later on the coverage-excluded set, blanking badges on non-active cards.
    Phase 3 retires that suppression outright (REQ-d00258).
    """

    def _make_node_with_status(self, status, rollup):
        """Build a minimal requirement node with the given status + metrics."""
        from tests.core.graph_test_helpers import build_graph, make_requirement

        graph = build_graph(
            make_requirement("REQ-p00001", title="Test Req", status=status),
        )
        node = graph.find_by_id("REQ-p00001")
        node.set_metric("rollup_metrics", rollup)
        return node

    @staticmethod
    def _full_rollup():
        from elspais.graph.metrics import CoverageDimension, RollupMetrics

        return RollupMetrics(
            total_assertions=2,
            implemented=CoverageDimension(total=2, direct=2, indirect=2),
            tested=CoverageDimension(total=2, direct=2, indirect=2),
            verified=CoverageDimension(total=2, direct=2, indirect=2),
        )

    # Verifies: REQ-d00258-C
    def test_draft_creditable_status_gets_colors(self):
        """A Draft requirement under a config whose status_roles.active includes
        "Draft" is coverage-creditable, so a fully-covered dimension must yield
        a non-empty (green) color -- NOT the old blanked-out empty payload."""
        from elspais.html.generator import compute_coverage_tiers
        from elspais.html.theme import get_catalog

        expected = get_catalog().by_key("severity.ok").color_key
        # active includes Draft: essentially every req is Draft during build-out.
        config = {"rules": {"format": {"status_roles": {"active": ["Active", "Draft"]}}}}
        node = self._make_node_with_status("Draft", self._full_rollup())

        tiers = compute_coverage_tiers(node, config)

        assert tiers["impl_color"] == expected
        assert tiers["impl_color"] != ""
        assert tiers["combined_bucket"] == "full"

    # Verifies: REQ-d00258
    def test_coverage_excluded_status_still_renders_badges(self):
        """Phase 3 (REQ-d00258): a coverage-EXCLUDED status (Deprecated ->
        retired role by default) NO LONGER blanks the payload. A fully-covered
        Deprecated requirement renders its real green coverage; only the
        Implemented gap severity is gated by status (and here impl is full, so
        no gap to gate)."""
        from elspais.html.generator import compute_coverage_tiers

        node = self._make_node_with_status("Deprecated", self._full_rollup())

        tiers = compute_coverage_tiers(node)

        assert tiers["impl_color"] != ""
        assert tiers["combined_bucket"] == "full"

    # Verifies: REQ-d00258
    def test_default_config_active_and_draft_both_render_full_coverage(self):
        """Under default status_roles (no config), a fully-covered requirement
        renders green coverage for BOTH Active and Draft statuses (Phase 3:
        badges always render; suppression retired)."""
        from elspais.html.generator import compute_coverage_tiers

        active = self._make_node_with_status("Active", self._full_rollup())
        draft = self._make_node_with_status("Draft", self._full_rollup())

        assert compute_coverage_tiers(active)["impl_color"] != ""
        assert compute_coverage_tiers(draft)["impl_color"] != ""

    # Verifies: REQ-d00258-C
    def test_creditable_status_with_no_assertions_still_empty(self):
        """The total_assertions==0 empty guard is independent of status gating:
        a creditable req with no assertions still returns empty."""
        from elspais.graph.metrics import RollupMetrics
        from elspais.html.generator import compute_coverage_tiers

        config = {"rules": {"format": {"status_roles": {"active": ["Active", "Draft"]}}}}
        node = self._make_node_with_status("Draft", RollupMetrics(total_assertions=0))

        tiers = compute_coverage_tiers(node, config)

        assert tiers["impl_color"] == ""
        assert tiers["combined_bucket"] == ""
