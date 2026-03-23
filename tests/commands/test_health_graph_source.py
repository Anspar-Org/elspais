# tests/commands/test_health_graph_source.py
# Implements: REQ-d00010

"""Tests that checks output shows graph source."""

from elspais.commands.health import (
    HealthCheck,
    HealthReport,
    _build_report_data,
    _render_text,
)


def test_render_text_shows_daemon_source():
    """Text output should show daemon source info when present."""
    report = HealthReport()
    report.add(
        HealthCheck(
            name="spec.parseable",
            passed=True,
            message="Parsed 10 requirements",
            category="spec",
        )
    )
    data = _build_report_data(report)
    data.graph_source = "daemon (port 35121, started 2026-03-23T10:19:59)"
    text = _render_text(data)
    assert "daemon" in text
    assert "35121" in text


def test_render_text_no_source_when_local():
    """Text output should show nothing special for local builds."""
    report = HealthReport()
    report.add(
        HealthCheck(
            name="spec.parseable",
            passed=True,
            message="Parsed 10 requirements",
            category="spec",
        )
    )
    data = _build_report_data(report)
    # graph_source is None by default
    text = _render_text(data)
    assert "daemon" not in text


def test_build_report_data_preserves_graph_source():
    """_build_report_data should have graph_source=None by default."""
    report = HealthReport()
    data = _build_report_data(report)
    assert data.graph_source is None
