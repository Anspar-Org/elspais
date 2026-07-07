"""Per-assertion coverage-state projection for the viewer (REQ-d00258-G).

The requirement-level dimension badges are colored by ``compute_coverage_tiers``.
These tests exercise ``compute_assertion_coverage_states``, which projects the
SAME rollup metrics down to per-*Assertion* states so the tiny per-assertion
badges color consistently with the requirement badge on initial render.
"""

from pathlib import Path

import pytest

from elspais.graph.metrics import CoverageDimension, RollupMetrics
from elspais.html.generator import (
    COVERAGE_STANDINGS,
    _severity_color,
    _standing_color,
    compute_assertion_coverage_states,
    compute_coverage_tiers,
    standing_class_map,
)


def _req_with_rollup(rollup, *, labels=("A", "B", "C", "D", "E"), status="Active"):
    """Build an Active requirement with the given assertion labels + rollup."""
    from tests.core.graph_test_helpers import build_graph, make_requirement

    assertions = [{"label": lbl, "text": f"SHALL {lbl}"} for lbl in labels]
    graph = build_graph(
        make_requirement("REQ-p00001", title="Test Req", status=status, assertions=assertions),
    )
    node = graph.find_by_id("REQ-p00001")
    node.set_metric("rollup_metrics", rollup)
    return node


def _spread_rollup():
    """A 5-assertion requirement with a deliberate spread of coverage states.

    These are SYNTHETIC per-label metrics chosen to pin the state->color
    machinery, decoupled from any journey/test-crediting policy:

    A: implemented + tested + passing, all 1.0 (full/green)
    B: tested 1.0 but passing 0.0 with a failure (Passing = failing/red)
    C: uat_coverage 1.0 + uat_verified 1.0 (UAT Covered full, UAT Passed full)
    D: uat_coverage 1.0 + uat_verified 0.5, NO failure (UAT Covered full,
       UAT Passed PARTIAL/yellow -- a partial fraction must read yellow, not grey)
    E: uncovered, all 0.0 (grey/none)
    """
    return RollupMetrics(
        total_assertions=5,
        implemented=CoverageDimension(
            total=5,
            direct=1,
            indirect=1,
            direct_pct_by_label={"A": 1.0},
            indirect_pct_by_label={"A": 1.0},
        ),
        tested=CoverageDimension(
            total=5,
            direct=2,
            indirect=2,
            direct_pct_by_label={"A": 1.0, "B": 1.0},
            indirect_pct_by_label={"A": 1.0, "B": 1.0},
        ),
        # A passes; B failed (not in the passing set) -> has_failures on the dim.
        verified=CoverageDimension(
            total=5,
            direct=1,
            indirect=1,
            has_failures=True,
            direct_pct_by_label={"A": 1.0},
            indirect_pct_by_label={"A": 1.0},
        ),
        uat_coverage=CoverageDimension(
            total=5,
            direct=2,
            indirect=2,
            direct_pct_by_label={"C": 1.0, "D": 1.0},
            indirect_pct_by_label={"C": 1.0, "D": 1.0},
        ),
        # C fully verified (1.0); D partially verified (0.5) with NO failure ->
        # the machinery must project D to "partial"/yellow.
        uat_verified=CoverageDimension(
            total=5,
            direct=1,
            indirect=1.5,
            has_failures=False,
            direct_pct_by_label={"C": 1.0},
            indirect_pct_by_label={"C": 1.0, "D": 0.5},
        ),
    )


class TestAssertionCoverageStates:
    """REQ-d00258-G: per-assertion state projection."""

    def test_REQ_d00258_G_spread_of_states(self):
        node = _req_with_rollup(_spread_rollup())
        states = compute_assertion_coverage_states(node)

        assert states["A"] == {
            "implemented": "full",
            "tested": "full",
            "verified": "full",
            "uat_coverage": "missing",
            "uat_verified": "missing",
        }
        # B: tested but its test failed -> Passing badge is failing.
        assert states["B"]["tested"] == "full"
        assert states["B"]["verified"] == "failing"
        assert states["B"]["implemented"] == "missing"
        # C: validated by a fully-verified journey.
        assert states["C"]["uat_coverage"] == "full"
        assert states["C"]["uat_verified"] == "full"
        # D: fully UAT-covered but only partially verified (0.5) with no failure
        # -> UAT Passed reads PARTIAL (yellow), NOT grey/none.
        assert states["D"]["uat_coverage"] == "full"
        assert states["D"]["uat_verified"] == "partial"
        # E: uncovered on every dimension.
        assert set(states["E"].values()) == {"missing"}

    @pytest.mark.parametrize(
        "frac,has_failures,expected",
        [
            (1.0, False, "full"),  # 100% -> green
            (0.5, False, "partial"),  # 0<f<1, no failure -> yellow
            (0.0, True, "failing"),  # covered-but-failed result -> red
            (0.0, False, "missing"),  # no evidence -> grey
        ],
    )
    def test_REQ_d00258_G_passing_state_machinery(self, frac, has_failures, expected):
        """Pin the Passing/verified state->color machinery with synthetic metrics,
        decoupled from any test/journey-crediting policy. RED requires a covered
        assertion (tested) so a failed result lands on it."""
        rollup = RollupMetrics(
            total_assertions=1,
            tested=CoverageDimension(
                total=1, direct=1, indirect=1, indirect_pct_by_label={"A": 1.0}
            ),
            verified=CoverageDimension(
                total=1,
                has_failures=has_failures,
                indirect_pct_by_label=({"A": frac} if frac > 0 else {}),
            ),
        )
        node = _req_with_rollup(rollup, labels=("A",))
        assert compute_assertion_coverage_states(node)["A"]["verified"] == expected

    @pytest.mark.parametrize(
        "frac,expected",
        [(1.0, "full"), (0.5, "partial"), (0.0, "missing")],
    )
    def test_REQ_d00258_G_uat_verified_partial_is_yellow(self, frac, expected):
        """A partial uat_verified fraction (e.g. once a partial journey credits
        fractionally) must read PARTIAL/yellow, not grey/none."""
        rollup = RollupMetrics(
            total_assertions=1,
            uat_coverage=CoverageDimension(
                total=1, direct=1, indirect=1, indirect_pct_by_label={"A": 1.0}
            ),
            uat_verified=CoverageDimension(
                total=1,
                has_failures=False,
                indirect_pct_by_label=({"A": frac} if frac > 0 else {}),
            ),
        )
        node = _req_with_rollup(rollup, labels=("A",))
        assert compute_assertion_coverage_states(node)["A"]["uat_verified"] == expected

    def test_REQ_d00258_G_partial_implemented_via_blanket_refine(self):
        """A fractional per-assertion implemented value reads as 'partial'."""
        rollup = RollupMetrics(
            total_assertions=2,
            implemented=CoverageDimension(
                total=2,
                direct=0.0,
                indirect=0.5,
                indirect_pct_by_label={"A": 0.5},
            ),
        )
        node = _req_with_rollup(rollup, labels=("A", "B"))
        states = compute_assertion_coverage_states(node)
        assert states["A"]["implemented"] == "partial"
        assert states["B"]["implemented"] == "missing"

    def test_REQ_d00258_G_verified_uses_lcov_union(self):
        """Passing state credits line-coverage evidence via tested_and_passing()."""
        rollup = RollupMetrics(
            total_assertions=1,
            tested=CoverageDimension(
                total=1, direct=1, indirect=1, indirect_pct_by_label={"A": 1.0}
            ),
            verified=CoverageDimension(total=1),  # no result-verified credit
            lcov_tested=CoverageDimension(
                total=1, direct=1, indirect=1, indirect_pct_by_label={"A": 1.0}
            ),
        )
        node = _req_with_rollup(rollup, labels=("A",))
        states = compute_assertion_coverage_states(node)
        assert states["A"]["verified"] == "full"

    def test_REQ_d00258_G_excluded_status_returns_empty(self):
        node = _req_with_rollup(_spread_rollup(), status="Deprecated")
        assert compute_assertion_coverage_states(node) == {}

    def test_REQ_d00258_G_no_rollup_returns_empty(self):
        from tests.core.graph_test_helpers import build_graph, make_requirement

        graph = build_graph(make_requirement("REQ-p00001", status="Active"))
        node = graph.find_by_id("REQ-p00001")
        assert compute_assertion_coverage_states(node) == {}


class TestRequirementAssertionConsistency:
    """REQ-d00258-G: per-assertion states cannot drift from the requirement badge."""

    def test_REQ_d00258_G_all_full_assertions_imply_full_requirement(self):
        rollup = RollupMetrics(
            total_assertions=3,
            implemented=CoverageDimension(
                total=3,
                direct=3,
                indirect=3,
                direct_pct_by_label={"A": 1.0, "B": 1.0, "C": 1.0},
                indirect_pct_by_label={"A": 1.0, "B": 1.0, "C": 1.0},
            ),
        )
        node = _req_with_rollup(rollup, labels=("A", "B", "C"))
        states = compute_assertion_coverage_states(node)
        tiers = compute_coverage_tiers(node)

        # Every assertion full on implemented ...
        assert all(states[lbl]["implemented"] == "full" for lbl in ("A", "B", "C"))
        # ... and the requirement dimension therefore reads a full tier.
        assert tiers["impl_tier"] in ("full-direct", "full-indirect")

    def test_REQ_d00258_G_failing_assertion_implies_requirement_failing(self):
        rollup = _spread_rollup()
        node = _req_with_rollup(rollup)
        states = compute_assertion_coverage_states(node)
        tiers = compute_coverage_tiers(node)

        # An assertion projected as 'failing' ...
        assert any(states[lbl]["verified"] == "failing" for lbl in states)
        # ... corresponds to the requirement Passing badge reading 'failing'.
        assert tiers["verified_tier"] == "failing"

    def test_REQ_d00258_G_full_standing_shares_requirement_full_color(self):
        """A 'full' standing resolves (through the catalog) to the same color the
        requirement full badge uses (severity 'ok'/green) -- the same decoupling
        REQ-d00258-D established for severity, extended to standings."""
        assert _standing_color("full") == _severity_color("ok")  # both green
        # failing -> red, missing -> a distinct neutral key (not a coverage color).
        assert _standing_color("failing") == _severity_color("error")
        assert _standing_color("missing") not in {
            _standing_color("full"),
            _standing_color("partial"),
            _standing_color("failing"),
        }


class TestCoverageStandingCatalog:
    """REQ-d00258-G/D: the standing->color association is catalog-driven, not
    hard-coded in the badge logic."""

    def test_REQ_d00258_G_catalog_maps_every_standing_to_a_color(self):
        from elspais.html.theme import get_catalog

        catalog = get_catalog()
        for standing in COVERAGE_STANDINGS:
            entry = catalog.by_key(f"coverage_standing.{standing}")
            assert entry.color_key  # non-empty configured color
            assert entry.css_class

    def test_REQ_d00258_G_standing_class_map_resolves_from_catalog(self):
        """standing_class_map() returns exactly the catalog's css_class per
        standing -- so changing the catalog changes the rendered class (colors
        are config-driven, not baked in)."""
        from elspais.html.theme import get_catalog

        catalog = get_catalog()
        mapping = standing_class_map()
        assert set(mapping) == set(COVERAGE_STANDINGS)
        for standing in COVERAGE_STANDINGS:
            assert mapping[standing] == catalog.by_key(f"coverage_standing.{standing}").css_class

    def test_REQ_d00258_G_standings_appear_in_legend(self):
        from elspais.html.theme import get_catalog

        groups = dict(get_catalog().grouped_entries())
        assert "Assertion Coverage Standing" in groups
        keys = {e.key.split(".")[-1] for e in groups["Assertion Coverage Standing"]}
        assert keys == set(COVERAGE_STANDINGS)


class TestApiNodePayload:
    """REQ-d00258-G: the /api/node payload carries assertion_coverage_states."""

    @pytest.fixture
    def client(self):
        from starlette.testclient import TestClient

        from elspais.graph.builder import TraceGraph
        from elspais.graph.federated import FederatedGraph
        from elspais.server.app import create_app
        from elspais.server.state import AppState
        from tests.core.graph_test_helpers import build_graph, make_requirement

        graph: TraceGraph = build_graph(
            make_requirement(
                "REQ-p00001",
                title="Test Req",
                status="Active",
                assertions=[{"label": lbl, "text": f"SHALL {lbl}"} for lbl in "ABCDE"],
            ),
        )
        graph.find_by_id("REQ-p00001").set_metric("rollup_metrics", _spread_rollup())
        fed = FederatedGraph.from_single(
            graph, {"project": {"name": "test", "namespace": "REQ"}}, Path("/test/repo")
        )
        state = AppState(
            graph=fed,
            repo_root=Path("/test/repo"),
            config={"project": {"name": "test", "namespace": "REQ"}},
        )
        return TestClient(create_app(state, mount_mcp=False))

    def test_REQ_d00258_G_payload_includes_assertion_states(self, client):
        resp = client.get("/api/node/REQ-p00001")
        assert resp.status_code == 200
        data = resp.json()
        assert "assertion_coverage_states" in data
        acs = data["assertion_coverage_states"]
        assert acs["A"]["verified"] == "full"
        assert acs["B"]["verified"] == "failing"
        assert acs["C"]["uat_coverage"] == "full"
        assert acs["D"]["uat_verified"] == "partial"
        assert set(acs["E"].values()) == {"missing"}
