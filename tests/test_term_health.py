"""Tests for term-related health checks.

Validates REQ-d00223-A+B+C+D: term health check functions report
duplicates, undefined terms, unmarked usage, and respect severity "off".
"""

from __future__ import annotations

from elspais.commands.health import (
    HealthCheck,
    check_term_duplicates,
    check_undefined_terms,
    check_unmarked_usage,
)
from elspais.graph.terms import TermEntry


class TestTermHealthChecks:
    """Validates REQ-d00223-A+B+C+D: term health check functions."""

    # -- REQ-d00223-A: duplicate definitions --------------------------------

    # Implements: REQ-d00223-A
    def test_REQ_d00223_A_duplicates_reported(self):
        """Duplicate term definitions produce a failing check."""
        entry_a = TermEntry(
            term="Electronic Record",
            definition="A record stored electronically.",
            defined_in="REQ-p00010",
            defined_at_line=5,
            namespace="REQ",
        )
        entry_b = TermEntry(
            term="Electronic Record",
            definition="An electronic storage of data.",
            defined_in="REQ-d00042",
            defined_at_line=18,
            namespace="REQ",
        )
        duplicates = [(entry_a, entry_b)]

        result = check_term_duplicates(duplicates)

        assert isinstance(result, HealthCheck)
        assert result.passed is False
        assert result.severity == "error"
        assert len(result.findings) > 0

    # Implements: REQ-d00223-A
    def test_REQ_d00223_A_no_duplicates_passes(self):
        """Empty duplicates list produces a passing check."""
        result = check_term_duplicates([])

        assert isinstance(result, HealthCheck)
        assert result.passed is True

    # -- REQ-d00223-B: undefined terms --------------------------------------

    # Implements: REQ-d00223-B
    def test_REQ_d00223_B_undefined_terms_reported(self):
        """Undefined term tokens produce a failing check."""
        undefined = [
            {"token": "Flowchart", "node_id": "REQ-p00003", "line": 47},
        ]

        result = check_undefined_terms(undefined)

        assert isinstance(result, HealthCheck)
        assert result.passed is False
        assert result.severity == "warning"

    # Implements: REQ-d00223-B
    def test_REQ_d00223_B_no_undefined_passes(self):
        """Empty undefined list produces a passing check."""
        result = check_undefined_terms([])

        assert isinstance(result, HealthCheck)
        assert result.passed is True

    # -- REQ-d00223-C: unmarked usage ---------------------------------------

    # Implements: REQ-d00223-C
    def test_REQ_d00223_C_unmarked_usage_reported(self):
        """Unmarked usage of indexed terms produces a failing check."""
        unmarked = [
            {"term": "Electronic Record", "node_id": "REQ-d00045", "line": 12},
        ]

        result = check_unmarked_usage(unmarked)

        assert isinstance(result, HealthCheck)
        assert result.passed is False
        assert result.severity == "warning"

    # Implements: REQ-d00223-C
    def test_REQ_d00223_C_no_unmarked_passes(self):
        """Empty unmarked list produces a passing check."""
        result = check_unmarked_usage([])

        assert isinstance(result, HealthCheck)
        assert result.passed is True

    # -- REQ-d00223-D: severity "off" skips check --------------------------

    # Implements: REQ-d00223-D
    def test_REQ_d00223_D_off_severity_skips_duplicates(self):
        """severity='off' returns passed info for duplicates check."""
        entry_a = TermEntry(
            term="Widget",
            definition="A thing.",
            defined_in="REQ-p00001",
        )
        entry_b = TermEntry(
            term="Widget",
            definition="Another thing.",
            defined_in="REQ-d00010",
        )

        result = check_term_duplicates([(entry_a, entry_b)], severity="off")

        assert result.passed is True
        assert result.severity == "info"

    # Implements: REQ-d00223-D
    def test_REQ_d00223_D_off_severity_skips_undefined(self):
        """severity='off' returns passed info for undefined terms check."""
        undefined = [
            {"token": "Flowchart", "node_id": "REQ-p00003", "line": 47},
        ]

        result = check_undefined_terms(undefined, severity="off")

        assert result.passed is True
        assert result.severity == "info"

    # Implements: REQ-d00223-D
    def test_REQ_d00223_D_off_severity_skips_unmarked(self):
        """severity='off' returns passed info for unmarked usage check."""
        unmarked = [
            {"term": "Electronic Record", "node_id": "REQ-d00045", "line": 12},
        ]

        result = check_unmarked_usage(unmarked, severity="off")

        assert result.passed is True
        assert result.severity == "info"
