# Verifies: REQ-d00258-K
"""Per-relationship status-word map is the single source for coverage labels.

REQ-d00258 (per-relationship status word): the label shown on a coverage
badge/button is defined per RELATIONSHIP, resolved to an internal dimension key,
and overridable via ``[rules.coverage.status_words]``.
"""

from __future__ import annotations

import pytest

from elspais.config.status_words import (
    RELATIONSHIP_TO_DIMENSION,
    get_status_words,
)


class TestDefaultStatusWords:
    """REQ-d00258-B display vocabulary with no config override."""

    @pytest.mark.parametrize(
        ("dim_key", "expected"),
        [
            ("implemented", "Implemented"),
            ("tested", "Tested"),
            ("verified", "Passing"),
            ("uat_coverage", "UAT Covered"),
            ("uat_verified", "UAT Passed"),
        ],
    )
    def test_default_label_for_each_dimension(self, dim_key: str, expected: str) -> None:
        assert get_status_words(None)[dim_key] == expected

    def test_empty_config_matches_defaults(self) -> None:
        assert get_status_words({}) == get_status_words(None)


class TestRelationshipMapping:
    """RELATIONSHIP_TO_DIMENSION documents the edge -> dimension link."""

    @pytest.mark.parametrize(
        ("relationship", "dim_key"),
        [
            ("implements", "implemented"),
            ("verifies", "tested"),
            ("yields", "verified"),
            ("validates", "uat_coverage"),
            ("validated", "uat_verified"),
        ],
    )
    def test_relationship_resolves_to_dimension(self, relationship: str, dim_key: str) -> None:
        assert RELATIONSHIP_TO_DIMENSION[relationship] == dim_key


class TestStatusWordOverrides:
    """A [rules.coverage.status_words] override changes the resolved label."""

    def test_override_by_relationship_key_changes_dimension_label(self) -> None:
        config = {"rules": {"coverage": {"status_words": {"verifies": "Exercised"}}}}
        words = get_status_words(config)
        assert words["tested"] == "Exercised"
        # Other dimensions keep their defaults.
        assert words["implemented"] == "Implemented"
        assert words["verified"] == "Passing"

    def test_override_uses_relationship_names_not_dimension_keys(self) -> None:
        # A dimension key ("tested") is NOT a valid override key; only the
        # relationship name ("verifies") is. Using the dimension key is ignored.
        config = {"rules": {"coverage": {"status_words": {"tested": "Wrong"}}}}
        assert get_status_words(config)["tested"] == "Tested"

    def test_unknown_relationship_key_ignored(self) -> None:
        config = {"rules": {"coverage": {"status_words": {"bogus": "Nope"}}}}
        assert get_status_words(config) == get_status_words(None)

    def test_case_insensitive_relationship_key(self) -> None:
        config = {"rules": {"coverage": {"status_words": {"Implements": "Built"}}}}
        assert get_status_words(config)["implemented"] == "Built"

    def test_non_string_override_value_ignored(self) -> None:
        config = {"rules": {"coverage": {"status_words": {"implements": 123}}}}
        assert get_status_words(config)["implemented"] == "Implemented"

    def test_empty_string_override_ignored(self) -> None:
        config = {"rules": {"coverage": {"status_words": {"implements": ""}}}}
        assert get_status_words(config)["implemented"] == "Implemented"


class TestStatusWordsReachRenderedTip:
    """The override is the SINGLE source for the requirement-badge tip label.

    Proves ``compute_coverage_tiers`` reads its dimension label from
    ``get_status_words(config)`` -- a config override changes the rendered tip
    text, and a default config still yields the REQ-d00258-B word.
    """

    def _req(self):
        from elspais.graph.metrics import CoverageDimension, RollupMetrics
        from tests.core.graph_test_helpers import build_graph, make_requirement

        graph = build_graph(
            make_requirement(
                "REQ-p00001",
                title="T",
                status="Active",
                assertions=[{"label": "A", "text": "SHALL A"}],
            )
        )
        node = graph.find_by_id("REQ-p00001")
        node.set_metric(
            "rollup_metrics",
            RollupMetrics(
                total_assertions=1,
                implemented=CoverageDimension(total=1),
            ),
        )
        return node

    def test_default_config_renders_implemented_label_in_tip(self) -> None:
        from elspais.html.generator import compute_coverage_tiers

        tiers = compute_coverage_tiers(self._req(), None)
        assert tiers["impl_tip"].startswith("Implemented:")

    def test_override_config_renders_overridden_label_in_tip(self) -> None:
        from elspais.html.generator import compute_coverage_tiers

        config = {"rules": {"coverage": {"status_words": {"implements": "Built"}}}}
        tiers = compute_coverage_tiers(self._req(), config)
        assert tiers["impl_tip"].startswith("Built:")
