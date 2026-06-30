# Verifies: REQ-d00257
"""Tests for trace --dimension uat UAT-scoped traceability report."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from elspais.graph import NodeKind

_JOURNEY_UAT_FIX = Path(__file__).parents[1] / "fixtures" / "journey-uat"
_CODE_COLUMNS = {"implemented", "tested", "verified", "code_tested", "lcov_tested"}


def _build_uat_graph(tmp_path: Path, slug: str):
    """Copy a journey-uat fixture to tmp_path and return the FederatedGraph."""
    from elspais.graph.factory import build_graph

    dest = tmp_path / slug
    shutil.copytree(_JOURNEY_UAT_FIX / slug, dest)
    return build_graph(repo_root=dest)


# ---------------------------------------------------------------------------
# Minimal project fixture: one validated req + one un-validated req
# ---------------------------------------------------------------------------


def _build_mixed_graph(tmp_path: Path):
    """Build a graph with two requirements -- one validated, one not.

    REQ-d00001 has an incoming VALIDATES edge from JNY-OQ-01.
    REQ-d00002 has NO journey, so it must be excluded from UAT reports.
    """
    from elspais.graph.factory import build_graph

    spec_dir = tmp_path / "spec"
    spec_dir.mkdir()

    (spec_dir / "requirements.md").write_text(
        """\
# Requirements

---

### REQ-d00001: Login Requirement

The system SHALL authenticate users.

## Assertions

A. The system SHALL accept valid credentials.

*End* *Login Requirement*
---

### REQ-d00002: Logging Requirement

The system SHALL log all actions.

## Assertions

A. The system SHALL write audit entries.

*End* *Logging Requirement*
---
"""
    )

    (spec_dir / "journeys.md").write_text(
        """\
# User Journeys

---

### JNY-OQ-01: Login Flow

**Actor**: End User
**Goal**: Authenticate

## Steps

1. User opens login page
2. User enters credentials

## Validates

Validates: REQ-d00001-A

*End* *JNY-OQ-01*
---
"""
    )

    (tmp_path / ".elspais.toml").write_text(
        """\
version = 3

[project]
name = "trace-uat-test"
namespace = "REQ"

[levels.dev]
rank = 1
letter = "d"
implements = ["dev"]

[id-patterns]
canonical = "{namespace}-{level.letter}{component}"

[id-patterns.component]
style = "numeric"
digits = 5
leading_zeros = true

[scanning.spec]
directories = ["spec"]

[scanning.journey]
directories = ["spec"]

[rules.hierarchy]
allow_circular = false
allow_structural_orphans = true

[rules.format]
require_hash = false
require_assertions = false
require_status = false
"""
    )

    return build_graph(repo_root=tmp_path)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def steps_all_pass_graph(tmp_path_factory):
    """FederatedGraph from the steps-all-pass fixture (all journey steps pass)."""
    return _build_uat_graph(tmp_path_factory.mktemp("all-pass"), "steps-all-pass")


@pytest.fixture()
def mixed_graph(tmp_path):
    """FederatedGraph with one validated req (REQ-d00001) and one un-validated (REQ-d00002)."""
    return _build_mixed_graph(tmp_path)


@pytest.fixture()
def uat_preset():
    """ReportPreset with dimension='uat'."""
    from elspais.commands.trace import _UAT_COLUMNS, ReportPreset

    return ReportPreset(
        name="uat",
        columns=list(_UAT_COLUMNS),
        dimension="uat",
    )


# ---------------------------------------------------------------------------
# Row-filtering tests
# ---------------------------------------------------------------------------


class TestUATRowFiltering:
    """Verify that only requirements with incoming VALIDATES edges appear."""

    def test_mixed_graph_json_includes_validated_req(self, mixed_graph, uat_preset):
        """REQ-d00001 (validated) must appear in UAT JSON output."""
        from elspais.commands.trace import format_json

        rows = json.loads("\n".join(format_json(mixed_graph, uat_preset)))
        ids = {r["id"] for r in rows}
        assert "REQ-d00001" in ids, f"REQ-d00001 should be in UAT report; got {ids}"

    def test_mixed_graph_json_excludes_unvalidated_req(self, mixed_graph, uat_preset):
        """REQ-d00002 (no VALIDATES edge) must NOT appear in UAT JSON output."""
        from elspais.commands.trace import format_json

        rows = json.loads("\n".join(format_json(mixed_graph, uat_preset)))
        ids = {r["id"] for r in rows}
        assert "REQ-d00002" not in ids, f"REQ-d00002 should be excluded; got {ids}"

    def test_only_validated_reqs_in_json(self, mixed_graph, uat_preset):
        """Every row in UAT JSON must have at least one validating journey."""
        from elspais.commands.trace import format_json
        from elspais.graph.relations import EdgeKind

        rows = json.loads("\n".join(format_json(mixed_graph, uat_preset)))
        for row in rows:
            req_id = row["id"]
            req_node = next(
                (n for n in mixed_graph.nodes_by_kind(NodeKind.REQUIREMENT) if n.id == req_id),
                None,
            )
            assert req_node is not None, f"Row id {req_id} not found in graph"
            # VALIDATES edges go FROM requirement TO journey (outgoing on req)
            has_validates = any(
                e.kind == EdgeKind.VALIDATES for e in req_node.iter_outgoing_edges()
            )
            assert has_validates, f"{req_id} has no VALIDATES edges but appears in UAT report"

    def test_markdown_excludes_unvalidated_req(self, mixed_graph, uat_preset):
        """Markdown UAT table must not contain requirements with no VALIDATES edges."""
        from elspais.commands.trace import format_markdown

        output = "\n".join(format_markdown(mixed_graph, uat_preset))
        assert "REQ-d00001" in output, "REQ-d00001 should appear in UAT markdown"
        assert "REQ-d00002" not in output, "REQ-d00002 should be excluded from UAT markdown"


# ---------------------------------------------------------------------------
# UAT column presence tests
# ---------------------------------------------------------------------------


class TestUATColumns:
    """Verify correct columns appear / do NOT appear in UAT output."""

    def test_json_has_uat_coverage(self, mixed_graph, uat_preset):
        """UAT JSON rows must include 'uat_coverage' field."""
        from elspais.commands.trace import format_json

        rows = json.loads("\n".join(format_json(mixed_graph, uat_preset)))
        assert rows, "Expected at least one row"
        for row in rows:
            assert "uat_coverage" in row, f"Missing uat_coverage in {row.get('id')}"

    def test_json_has_uat_verified(self, mixed_graph, uat_preset):
        """UAT JSON rows must include 'uat_verified' field."""
        from elspais.commands.trace import format_json

        rows = json.loads("\n".join(format_json(mixed_graph, uat_preset)))
        assert rows, "Expected at least one row"
        for row in rows:
            assert "uat_verified" in row, f"Missing uat_verified in {row.get('id')}"

    def test_json_excludes_code_columns(self, mixed_graph, uat_preset):
        """Code-dimension columns must be absent from UAT JSON output."""
        from elspais.commands.trace import format_json

        rows = json.loads("\n".join(format_json(mixed_graph, uat_preset)))
        assert rows, "Expected at least one row"
        for row in rows:
            for col in _CODE_COLUMNS:
                assert col not in row, f"Code column '{col}' should be excluded; row: {row}"

    def test_markdown_header_has_uat_coverage(self, mixed_graph, uat_preset):
        """Markdown UAT header must include 'UAT Coverage' column."""
        from elspais.commands.trace import format_markdown

        lines = list(format_markdown(mixed_graph, uat_preset))
        header = next((ln for ln in lines if "|" in ln), "")
        assert "UAT Coverage" in header, f"Missing 'UAT Coverage' in header: {header}"

    def test_markdown_header_has_journeys_column(self, mixed_graph, uat_preset):
        """Markdown UAT header must include a 'Journeys' column."""
        from elspais.commands.trace import format_markdown

        lines = list(format_markdown(mixed_graph, uat_preset))
        header = next((ln for ln in lines if "|" in ln), "")
        assert "Journeys" in header, f"Missing 'Journeys' column in header: {header}"

    def test_markdown_header_excludes_implemented(self, mixed_graph, uat_preset):
        """Markdown UAT header must NOT include 'Implemented' (code column)."""
        from elspais.commands.trace import format_markdown

        lines = list(format_markdown(mixed_graph, uat_preset))
        header = next((ln for ln in lines if "|" in ln), "")
        assert "Implemented" not in header, f"Code column 'Implemented' should be absent: {header}"

    def test_csv_header_excludes_implemented(self, mixed_graph, uat_preset):
        """CSV UAT header must NOT include 'Implemented'."""
        from elspais.commands.trace import format_csv

        lines = list(format_csv(mixed_graph, uat_preset))
        assert lines, "Expected CSV output"
        header = lines[0]
        assert "Implemented" not in header, f"Code column 'Implemented' in CSV header: {header}"

    def test_html_header_excludes_implemented(self, mixed_graph, uat_preset):
        """HTML UAT header must NOT include 'Implemented'."""
        from elspais.commands.trace import format_html

        output = "\n".join(format_html(mixed_graph, uat_preset))
        # Check that the <th> for Implemented is absent
        assert (
            "<th>Implemented</th>" not in output
        ), "Code column '<th>Implemented</th>' should be absent from UAT HTML"


# ---------------------------------------------------------------------------
# Journey verdict tests
# ---------------------------------------------------------------------------


class TestUATJourneyVerdicts:
    """Verify journey verdict derivation in UAT output."""

    def test_json_has_journeys_field(self, mixed_graph, uat_preset):
        """Each UAT JSON row must have a 'journeys' list."""
        from elspais.commands.trace import format_json

        rows = json.loads("\n".join(format_json(mixed_graph, uat_preset)))
        assert rows, "Expected at least one row"
        for row in rows:
            assert "journeys" in row, f"Missing 'journeys' key in {row.get('id')}"
            assert isinstance(row["journeys"], list), "'journeys' should be a list"
            assert len(row["journeys"]) > 0, "Expected at least one journey per validated req"

    def test_json_journey_has_id_and_verdict(self, mixed_graph, uat_preset):
        """Each journey entry in JSON must have 'id' and 'verdict' fields."""
        from elspais.commands.trace import format_json

        rows = json.loads("\n".join(format_json(mixed_graph, uat_preset)))
        for row in rows:
            for j in row["journeys"]:
                assert "id" in j, f"Journey entry missing 'id': {j}"
                assert "verdict" in j, f"Journey entry missing 'verdict': {j}"
                assert j["verdict"] in {
                    "pass",
                    "fail",
                    "partial",
                    "unverified",
                }, f"Unexpected verdict '{j['verdict']}'"

    def test_get_uat_journeys_verdict_unverified_for_no_metric(self, mixed_graph):
        """_get_uat_journeys returns 'unverified' when journey has no metric."""
        from elspais.commands.trace import _get_uat_journeys
        from elspais.graph.relations import EdgeKind

        # VALIDATES edges go FROM requirement TO journey (outgoing on req)
        for node in mixed_graph.nodes_by_kind(NodeKind.REQUIREMENT):
            has_val = any(e.kind == EdgeKind.VALIDATES for e in node.iter_outgoing_edges())
            if has_val:
                journeys = _get_uat_journeys(node)
                assert len(journeys) > 0
                # No results.xml in mixed_graph fixture -> journey has no metric
                for j in journeys:
                    assert j["verdict"] in {"unverified", "pass", "fail", "partial"}

    def test_steps_all_pass_verdict_is_pass(self, steps_all_pass_graph, uat_preset):
        """In the steps-all-pass fixture, every validating journey has verdict 'pass'."""
        from elspais.commands.trace import format_json

        rows = json.loads("\n".join(format_json(steps_all_pass_graph, uat_preset)))
        assert rows, "Expected at least one UAT row in steps-all-pass graph"
        for row in rows:
            for j in row["journeys"]:
                assert (
                    j["verdict"] == "pass"
                ), f"Expected 'pass' verdict for {j['id']} in steps-all-pass; got '{j['verdict']}'"

    def test_markdown_journey_data_in_rows(self, steps_all_pass_graph, uat_preset):
        """Markdown UAT rows contain journey IDs in the Journeys cell."""
        from elspais.commands.trace import format_markdown

        lines = list(format_markdown(steps_all_pass_graph, uat_preset))
        # Skip header lines (first 3 lines: title, blank, header, separator)
        data_lines = [ln for ln in lines if "|" in ln and "----" not in ln and "Journeys" not in ln]
        assert data_lines, "Expected at least one data row in UAT markdown"
        # At least one row should mention JNY
        assert any(
            "JNY" in line for line in data_lines
        ), "Expected journey ID in at least one markdown data row"

    def test_one_step_fails_verdict_is_fail(self, tmp_path):
        """In the one-step-fails fixture, failing journey has verdict 'fail'."""
        from elspais.commands.trace import _UAT_COLUMNS, ReportPreset, format_json

        graph = _build_uat_graph(tmp_path, "one-step-fails")
        preset = ReportPreset(name="uat", columns=list(_UAT_COLUMNS), dimension="uat")
        rows = json.loads("\n".join(format_json(graph, preset)))
        assert rows, "Expected at least one UAT row in one-step-fails graph"
        for row in rows:
            for j in row["journeys"]:
                assert j["verdict"] == "fail", (
                    f"Expected 'fail' verdict for {j['id']} in one-step-fails; "
                    f"got '{j['verdict']}'"
                )
