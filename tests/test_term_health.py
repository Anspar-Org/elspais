"""Tests for term-related health checks.

# Implements: REQ-d00223, REQ-d00240, REQ-d00241

Validates REQ-d00223-A+B+C+D: term health check functions report
duplicates, undefined terms, unmarked usage, and respect severity "off".

Validates REQ-d00240-A+B+C+D: unused terms, bad definitions,
empty collection terms, and updated run_term_checks aggregator.

Validates REQ-d00241-A: check_no_traceability reports code/test files
with no traceability markers.
"""

from __future__ import annotations

from elspais.commands.health import (
    HealthCheck,
    check_no_traceability,
    check_term_bad_definition,
    check_term_collection_empty,
    check_term_duplicates,
    check_term_unused,
    check_undefined_terms,
    check_unmarked_usage,
    run_term_checks,
)
from elspais.graph.terms import TermDictionary, TermEntry, TermRef


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


# =========================================================================
# REQ-d00240: New term health checks
# =========================================================================


class TestCheckTermUnused:
    """Validates REQ-d00240-A: unused term detection."""

    # Implements: REQ-d00240-A
    def test_REQ_d00240_A_unused_term_fails(self):
        """A term with 0 references produces a failing finding."""
        entries = [
            TermEntry(
                term="Orphan Term",
                definition="A term nobody references.",
                defined_in="REQ-p00001",
                defined_at_line=5,
                namespace="REQ",
                references=[],
            ),
        ]

        result = check_term_unused(entries)

        assert isinstance(result, HealthCheck)
        assert result.name == "terms.unused"
        assert result.passed is False
        assert result.severity == "warning"
        assert len(result.findings) == 1
        assert "Orphan Term" in result.findings[0].message

    # Implements: REQ-d00240-A
    def test_REQ_d00240_A_used_term_passes(self):
        """A term with references produces no finding."""
        entries = [
            TermEntry(
                term="Active Term",
                definition="A term that is used.",
                defined_in="REQ-p00001",
                defined_at_line=5,
                namespace="REQ",
                references=[
                    TermRef(
                        node_id="REQ-d00010",
                        namespace="REQ",
                        marked=True,
                        line=12,
                    ),
                ],
            ),
        ]

        result = check_term_unused(entries)

        assert isinstance(result, HealthCheck)
        assert result.name == "terms.unused"
        assert result.passed is True
        assert len(result.findings) == 0

    # Implements: REQ-d00240-A
    def test_REQ_d00240_A_severity_off_skips(self):
        """severity='off' returns passed/info even with unused terms."""
        entries = [
            TermEntry(
                term="Orphan Term",
                definition="A term nobody references.",
                defined_in="REQ-p00001",
                references=[],
            ),
        ]

        result = check_term_unused(entries, severity="off")

        assert result.passed is True
        assert result.severity == "info"


class TestCheckTermBadDefinition:
    """Validates REQ-d00240-B: bad definition detection."""

    # Implements: REQ-d00240-B
    def test_REQ_d00240_B_empty_definition_fails(self):
        """A term with an empty definition produces a failing finding."""
        entries = [
            TermEntry(
                term="Empty Def",
                definition="",
                defined_in="REQ-p00001",
                defined_at_line=5,
                namespace="REQ",
            ),
        ]

        result = check_term_bad_definition(entries)

        assert isinstance(result, HealthCheck)
        assert result.name == "terms.bad_definition"
        assert result.passed is False
        assert result.severity == "error"
        assert len(result.findings) == 1
        assert "Empty Def" in result.findings[0].message

    # Implements: REQ-d00240-B
    def test_REQ_d00240_B_short_definition_fails(self):
        """A term with a <10 char definition produces a failing finding."""
        entries = [
            TermEntry(
                term="Short Def",
                definition="Brief",  # 5 chars, < 10
                defined_in="REQ-p00001",
                defined_at_line=10,
                namespace="REQ",
            ),
        ]

        result = check_term_bad_definition(entries)

        assert isinstance(result, HealthCheck)
        assert result.name == "terms.bad_definition"
        assert result.passed is False
        assert len(result.findings) == 1
        assert "Short Def" in result.findings[0].message

    # Implements: REQ-d00240-B
    def test_REQ_d00240_B_adequate_definition_passes(self):
        """A term with an adequate definition (>=10 chars) passes."""
        entries = [
            TermEntry(
                term="Good Term",
                definition="A well-defined term with sufficient detail.",
                defined_in="REQ-p00001",
                defined_at_line=5,
                namespace="REQ",
            ),
        ]

        result = check_term_bad_definition(entries)

        assert isinstance(result, HealthCheck)
        assert result.name == "terms.bad_definition"
        assert result.passed is True
        assert len(result.findings) == 0

    # Implements: REQ-d00240-B
    def test_REQ_d00240_B_severity_off_skips(self):
        """severity='off' returns passed/info even with bad definitions."""
        entries = [
            TermEntry(
                term="Empty Def",
                definition="",
                defined_in="REQ-p00001",
            ),
        ]

        result = check_term_bad_definition(entries, severity="off")

        assert result.passed is True
        assert result.severity == "info"


class TestCheckTermCollectionEmpty:
    """Validates REQ-d00240-C: empty collection term detection."""

    # Implements: REQ-d00240-C
    def test_REQ_d00240_C_empty_collection_fails(self):
        """A collection term with 0 references produces a failing finding."""
        entries = [
            TermEntry(
                term="Glossary Section",
                definition="A grouping term for related concepts.",
                collection=True,
                defined_in="REQ-p00001",
                defined_at_line=5,
                namespace="REQ",
                references=[],
            ),
        ]

        result = check_term_collection_empty(entries)

        assert isinstance(result, HealthCheck)
        assert result.name == "terms.collection_empty"
        assert result.passed is False
        assert result.severity == "warning"
        assert len(result.findings) == 1
        assert "Glossary Section" in result.findings[0].message

    # Implements: REQ-d00240-C
    def test_REQ_d00240_C_collection_with_refs_passes(self):
        """A collection term with references passes."""
        entries = [
            TermEntry(
                term="Glossary Section",
                definition="A grouping term for related concepts.",
                collection=True,
                defined_in="REQ-p00001",
                defined_at_line=5,
                namespace="REQ",
                references=[
                    TermRef(
                        node_id="REQ-d00020",
                        namespace="REQ",
                        marked=True,
                        line=30,
                    ),
                ],
            ),
        ]

        result = check_term_collection_empty(entries)

        assert isinstance(result, HealthCheck)
        assert result.name == "terms.collection_empty"
        assert result.passed is True
        assert len(result.findings) == 0

    # Implements: REQ-d00240-C
    def test_REQ_d00240_C_non_collection_ignored(self):
        """A non-collection term with 0 references is not reported."""
        entries = [
            TermEntry(
                term="Regular Term",
                definition="Just a normal term with no references.",
                collection=False,
                defined_in="REQ-p00001",
                defined_at_line=5,
                namespace="REQ",
                references=[],
            ),
        ]

        result = check_term_collection_empty(entries)

        assert isinstance(result, HealthCheck)
        assert result.name == "terms.collection_empty"
        assert result.passed is True
        assert len(result.findings) == 0

    # Implements: REQ-d00240-C
    def test_REQ_d00240_C_severity_off_skips(self):
        """severity='off' returns passed/info even with empty collections."""
        entries = [
            TermEntry(
                term="Glossary Section",
                definition="A grouping term.",
                collection=True,
                defined_in="REQ-p00001",
                references=[],
            ),
        ]

        result = check_term_collection_empty(entries, severity="off")

        assert result.passed is True
        assert result.severity == "info"


class _FakeGraph:
    """Minimal stand-in for FederatedGraph with term-related attributes."""

    def __init__(
        self,
        terms: TermDictionary | None = None,
        term_duplicates: list[tuple] | None = None,
    ) -> None:
        self._terms = terms or TermDictionary()
        self._term_duplicates = term_duplicates or []


class TestRunTermChecks:
    """Validates REQ-d00223-E and REQ-d00240-D: run_term_checks aggregator."""

    # Implements: REQ-d00223-E
    def test_REQ_d00223_E_run_term_checks_returns_list(self):
        """run_term_checks returns a list of HealthCheck objects."""
        config = {
            "terms": {
                "severity": {
                    "duplicate": "error",
                    "undefined": "warning",
                    "unmarked": "warning",
                    "unused": "warning",
                    "bad_definition": "error",
                    "collection_empty": "warning",
                },
            },
        }
        graph = _FakeGraph()

        result = run_term_checks(graph, config)

        assert isinstance(result, list)
        for check in result:
            assert isinstance(check, HealthCheck)

    # Implements: REQ-d00223-E
    def test_REQ_d00223_E_run_term_checks_reads_severity_from_config(self):
        """run_term_checks passes severity values from config to sub-checks."""
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
        config = {
            "terms": {
                "severity": {
                    "duplicate": "warning",
                    "undefined": "error",
                    "unmarked": "error",
                    "unused": "warning",
                    "bad_definition": "error",
                    "collection_empty": "warning",
                },
            },
        }
        graph = _FakeGraph(term_duplicates=[(entry_a, entry_b)])

        result = run_term_checks(graph, config)

        # The duplicate check should use "warning" severity from config
        dup_check = [c for c in result if "duplicate" in c.name.lower()]
        assert len(dup_check) == 1
        assert dup_check[0].severity == "warning"

    # Implements: REQ-d00223-E
    def test_REQ_d00223_E_run_term_checks_off_severity_skips(self):
        """severity='off' produces passed/info checks for all six."""
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
        config = {
            "terms": {
                "severity": {
                    "duplicate": "off",
                    "undefined": "off",
                    "unmarked": "off",
                    "unused": "off",
                    "bad_definition": "off",
                    "collection_empty": "off",
                },
            },
        }
        graph = _FakeGraph(term_duplicates=[(entry_a, entry_b)])

        result = run_term_checks(graph, config)

        for check in result:
            assert check.passed is True
            assert check.severity == "info"

    # Implements: REQ-d00223-E
    def test_REQ_d00223_E_run_term_checks_extracts_duplicates(self):
        """run_term_checks passes graph._term_duplicates to check_term_duplicates."""
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
        config = {
            "terms": {
                "severity": {
                    "duplicate": "error",
                    "undefined": "warning",
                    "unmarked": "warning",
                    "unused": "warning",
                    "bad_definition": "error",
                    "collection_empty": "warning",
                },
            },
        }
        graph = _FakeGraph(term_duplicates=[(entry_a, entry_b)])

        result = run_term_checks(graph, config)

        dup_check = [c for c in result if "duplicate" in c.name.lower()]
        assert len(dup_check) == 1
        assert dup_check[0].passed is False
        assert len(dup_check[0].findings) > 0

    # Implements: REQ-d00223-E
    def test_REQ_d00223_E_run_term_checks_empty_graph(self):
        """Empty graph (no terms, no duplicates) produces all-passed checks."""
        config = {
            "terms": {
                "severity": {
                    "duplicate": "error",
                    "undefined": "warning",
                    "unmarked": "warning",
                    "unused": "warning",
                    "bad_definition": "error",
                    "collection_empty": "warning",
                },
            },
        }
        graph = _FakeGraph()

        result = run_term_checks(graph, config)

        for check in result:
            assert check.passed is True

    # Implements: REQ-d00240-D
    def test_REQ_d00240_D_run_term_checks_returns_six_checks(self):
        """run_term_checks returns all 6 HealthCheck items."""
        config = {
            "terms": {
                "severity": {
                    "duplicate": "error",
                    "undefined": "warning",
                    "unmarked": "warning",
                    "unused": "warning",
                    "bad_definition": "error",
                    "collection_empty": "warning",
                },
            },
        }
        graph = _FakeGraph()

        result = run_term_checks(graph, config)

        assert len(result) == 6
        names = {check.name for check in result}
        assert names == {
            "terms.duplicates",
            "terms.undefined",
            "terms.unmarked",
            "terms.unused",
            "terms.bad_definition",
            "terms.collection_empty",
        }


# =========================================================================
# REQ-d00241: No-traceability health check
# =========================================================================


class TestCheckNoTraceability:
    """Validates REQ-d00241-A: code/test files with no traceability markers."""

    # Implements: REQ-d00241
    def test_REQ_d00241_A_unlinked_files_fails(self):
        """Files with no traceability markers produce a failing check."""
        unlinked = ["src/utils/helper.py", "tests/test_smoke.py"]

        result = check_no_traceability(unlinked)

        assert isinstance(result, HealthCheck)
        assert result.passed is False
        assert result.severity == "warning"
        assert len(result.findings) == 2
        assert any("helper.py" in f.message for f in result.findings)
        assert any("test_smoke.py" in f.message for f in result.findings)

    # Implements: REQ-d00241
    def test_REQ_d00241_A_empty_list_passes(self):
        """Empty unlinked list produces a passing check."""
        result = check_no_traceability([])

        assert isinstance(result, HealthCheck)
        assert result.passed is True
        assert len(result.findings) == 0

    # Implements: REQ-d00241
    def test_REQ_d00241_A_severity_off_skips(self):
        """severity='off' returns passed/info even with unlinked files."""
        unlinked = ["src/utils/helper.py"]

        result = check_no_traceability(unlinked, severity="off")

        assert result.passed is True
        assert result.severity == "info"


# =========================================================================
# REQ-d00223-F: Wrong-marking vs plain unmarked distinction
# =========================================================================


class TestUnmarkedWrongMarking:
    """Validates REQ-d00223-F: distinct messages for wrong-marking."""

    # Implements: REQ-d00223-F
    def test_REQ_d00223_F_wrong_marking_distinct_message(self):
        """Wrong-marking items get a distinct message mentioning the delimiter."""
        unmarked = [
            {
                "term": "Electronic Record",
                "node_id": "REQ-d00045",
                "line": 12,
                "wrong_marking": "__",
            },
        ]

        result = check_unmarked_usage(unmarked)

        assert result.passed is False
        assert len(result.findings) == 1
        msg = result.findings[0].message
        assert "Wrong markup" in msg or "wrong markup" in msg.lower()
        assert "__" in msg

    # Implements: REQ-d00223-F
    def test_REQ_d00223_F_plain_unmarked_standard_message(self):
        """Plain unmarked items get the standard message."""
        unmarked = [
            {
                "term": "Electronic Record",
                "node_id": "REQ-d00045",
                "line": 12,
            },
        ]

        result = check_unmarked_usage(unmarked)

        assert result.passed is False
        assert len(result.findings) == 1
        msg = result.findings[0].message
        assert "Unmarked usage" in msg
        assert "Wrong markup" not in msg

    # Implements: REQ-d00223-F
    def test_REQ_d00223_F_mixed_items_distinct_messages(self):
        """Mix of wrong-marking and plain unmarked produces distinct messages."""
        unmarked = [
            {
                "term": "Widget",
                "node_id": "REQ-d00010",
                "line": 5,
                "wrong_marking": "_",
            },
            {
                "term": "Gadget",
                "node_id": "REQ-d00020",
                "line": 10,
            },
        ]

        result = check_unmarked_usage(unmarked)

        assert result.passed is False
        assert len(result.findings) == 2
        wrong_msgs = [f.message for f in result.findings if "Wrong markup" in f.message]
        plain_msgs = [f.message for f in result.findings if "Unmarked usage" in f.message]
        assert len(wrong_msgs) == 1
        assert len(plain_msgs) == 1
