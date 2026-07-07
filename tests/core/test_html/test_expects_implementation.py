# Verifies: REQ-d00258-L
"""Coverage badges always render; `Implemented` gap severity gated by
``status_expects_implementation`` (REQ-d00258).

Phase-3 behavior change: ``compute_coverage_tiers`` and
``compute_assertion_coverage_states`` no longer suppress (return empty/``{}``)
for coverage-excluded statuses. Badges ALWAYS render. The only status-sensitive
projection that remains is the ``Implemented`` dimension's gap severity: a
``missing`` implemented tier is a REAL (red) gap only when the requirement's
status expects implementation; otherwise it renders NEUTRAL grey (``info``
severity), exactly like an N/A dimension.
"""

from elspais.graph.metrics import CoverageDimension, RollupMetrics
from elspais.html.generator import (
    _severity_color,
    compute_assertion_coverage_states,
    compute_coverage_tiers,
)


def _req_with_rollup(rollup, *, labels=("A", "B"), status="Active"):
    """Build a requirement with the given assertion labels + rollup + status."""
    from tests.core.graph_test_helpers import build_graph, make_requirement

    assertions = [{"label": lbl, "text": f"SHALL {lbl}"} for lbl in labels]
    graph = build_graph(
        make_requirement("REQ-p00001", title="Test Req", status=status, assertions=assertions),
    )
    node = graph.find_by_id("REQ-p00001")
    node.set_metric("rollup_metrics", rollup)
    return node


def _uncovered_rollup(n=2):
    """A rollup with assertions but ZERO coverage on every dimension."""
    return RollupMetrics(total_assertions=n)


# The color a NEUTRAL (grey) badge resolves to: the same "info" severity color
# an N/A dimension already renders. Semantic, not a hard-coded hue.
GREY = _severity_color("info")
RED = _severity_color("error")
GREEN = _severity_color("ok")


class TestImplementedGapSeverityGated:
    """REQ-d00258: the Implemented `missing` gap is red only when the status
    expects implementation, else neutral grey -- and badges always render."""

    # (A) Draft (default role -> does NOT expect implementation), 0 implemented.
    # Verifies: REQ-d00258
    def test_REQ_d00258_draft_zero_implemented_renders_grey_not_red(self):
        node = _req_with_rollup(_uncovered_rollup(), status="Draft")
        tiers = compute_coverage_tiers(node)

        # Badges are NO LONGER suppressed for a coverage-excluded status.
        assert tiers != {}
        assert tiers["impl_tier"] == "missing"
        # A missing impl on a status that does not expect implementation is a
        # NEUTRAL grey gap, not an empty payload and not a red gap.
        assert tiers["impl_color"] == GREY
        assert tiers["impl_color"] != ""
        assert tiers["impl_color"] != RED

    # Verifies: REQ-d00258
    def test_REQ_d00258_draft_zero_implemented_assertion_states_nonempty(self):
        node = _req_with_rollup(_uncovered_rollup(), status="Draft")
        states = compute_assertion_coverage_states(node)

        # Per-assertion standings compute for a Draft too (no suppression).
        assert states != {}
        assert set(states) == {"A", "B"}
        assert states["A"]["implemented"] == "missing"

    # (B) Active (expects implementation by default), 0 implemented -> RED.
    # Verifies: REQ-d00258
    def test_REQ_d00258_active_zero_implemented_renders_red(self):
        node = _req_with_rollup(_uncovered_rollup(), status="Active")
        tiers = compute_coverage_tiers(node)

        assert tiers["impl_tier"] == "missing"
        assert tiers["impl_color"] == RED

    # (C) Draft with explicit expects_implementation=true -> RED.
    # Verifies: REQ-d00258
    def test_REQ_d00258_draft_expects_implementation_true_renders_red(self):
        node = _req_with_rollup(_uncovered_rollup(), status="Draft")
        config = {"statuses": {"Draft": {"expects_implementation": True}}}
        tiers = compute_coverage_tiers(node, config)

        assert tiers["impl_tier"] == "missing"
        # The status now EXPECTS implementation, so its absence is a real red gap.
        assert tiers["impl_color"] == RED

    # (D) A non-expecting Draft still surfaces REAL coverage on other dimensions
    # (badges are not suppressed): impl stays neutral grey while an absolute
    # dimension with genuine coverage renders green.
    # Verifies: REQ-d00258
    def test_REQ_d00258_draft_grey_impl_coexists_with_real_green_coverage(self):
        rollup = RollupMetrics(
            total_assertions=2,
            # Implemented is empty -> missing -> neutral grey for a Draft.
            implemented=CoverageDimension(total=2),
            # UAT coverage is an ABSOLUTE dimension: fully covered -> green.
            uat_coverage=CoverageDimension(
                total=2,
                direct=2,
                indirect=2,
                direct_pct_by_label={"A": 1.0, "B": 1.0},
                indirect_pct_by_label={"A": 1.0, "B": 1.0},
            ),
        )
        node = _req_with_rollup(rollup, status="Draft")
        tiers = compute_coverage_tiers(node)

        assert tiers != {}
        # Impl missing on a non-expecting status -> neutral grey (not red).
        assert tiers["impl_tier"] == "missing"
        assert tiers["impl_color"] == GREY
        # Real coverage on the UAT dimension is surfaced, not suppressed.
        assert tiers["uat_cov_tier"] == "full"
        assert tiers["uat_cov_color"] == GREEN


class TestExcludedStatusNoLongerSuppressed:
    """The old blanket suppression for coverage-excluded statuses is removed:
    Deprecated (retired role, does not expect implementation) still renders."""

    # Verifies: REQ-d00258
    def test_REQ_d00258_deprecated_tiers_render_grey_impl(self):
        node = _req_with_rollup(_uncovered_rollup(), status="Deprecated")
        tiers = compute_coverage_tiers(node)

        assert tiers != {}
        assert tiers["impl_tier"] == "missing"
        assert tiers["impl_color"] == GREY

    # Verifies: REQ-d00258
    def test_REQ_d00258_deprecated_assertion_states_render(self):
        node = _req_with_rollup(_uncovered_rollup(), status="Deprecated")
        states = compute_assertion_coverage_states(node)

        assert states != {}
        assert set(states) == {"A", "B"}
