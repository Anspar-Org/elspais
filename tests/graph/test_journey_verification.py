# Implements: REQ-d00131-B
"""Tests for journey-id recognition inside Verifies: reference lines.

These tests confirm that JOURNEY_REF_PATTERN matches JNY-... targets
(whole journeys and addressable steps), and that _extract_ids collects
them without breaking existing REQ-id extraction.
"""
from __future__ import annotations

import pytest

from elspais.graph.parsers.lark.transformers.reference import ReferenceTransformer
from elspais.graph.parsers.patterns import JOURNEY_REF_PATTERN
from elspais.utilities.patterns import IdPatternConfig, IdResolver

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def resolver():
    """Minimal IdResolver using standard REQ namespace."""
    config = IdPatternConfig.from_dict(
        {
            "project": {"namespace": "REQ"},
            "id-patterns": {
                "canonical": "{namespace}-{type.letter}{component}",
                "aliases": {"short": "{type.letter}{component}"},
                "types": {
                    "prd": {"level": 1, "aliases": {"letter": "p"}},
                    "ops": {"level": 2, "aliases": {"letter": "o"}},
                    "dev": {"level": 3, "aliases": {"letter": "d"}},
                },
                "component": {"style": "numeric", "digits": 5, "leading_zeros": True},
                "assertions": {"label_style": "uppercase", "max_count": 26},
            },
        }
    )
    return IdResolver(config)


@pytest.fixture()
def extractor(resolver):
    """ReferenceTransformer instance for calling _extract_ids."""
    return ReferenceTransformer(resolver, "test_ref")


# ---------------------------------------------------------------------------
# Pattern unit tests
# ---------------------------------------------------------------------------


# Verifies: REQ-d00255
def test_journey_ref_pattern_matches_whole_journey():
    assert JOURNEY_REF_PATTERN.fullmatch("JNY-OQ-Login-01")


# Verifies: REQ-d00256
def test_journey_ref_pattern_matches_step():
    assert JOURNEY_REF_PATTERN.fullmatch("JNY-OQ-Login-01/step-2")


def test_journey_ref_pattern_rejects_req_id():
    assert not JOURNEY_REF_PATTERN.fullmatch("REQ-p00001-A")


def test_journey_ref_pattern_rejects_bare_jny_no_number():
    # Must have -<number> suffix to be a valid JNY id
    assert not JOURNEY_REF_PATTERN.fullmatch("JNY-Login")


# ---------------------------------------------------------------------------
# _extract_ids integration tests
# ---------------------------------------------------------------------------


# Verifies: REQ-d00255
def test_extract_ids_journey_only(extractor):
    """Verifies: JNY-OQ-Login-01 yields the whole-journey id."""
    ids = extractor._extract_ids("Verifies: JNY-OQ-Login-01")
    assert "JNY-OQ-Login-01" in ids


# Verifies: REQ-d00256
def test_extract_ids_journey_step(extractor):
    """Verifies: JNY-OQ-Login-01/step-2 yields the step id with suffix."""
    ids = extractor._extract_ids("Verifies: JNY-OQ-Login-01/step-2")
    assert "JNY-OQ-Login-01/step-2" in ids


def test_extract_ids_req_still_works(extractor):
    """Existing REQ-p00001-A extraction is unaffected (no regression)."""
    ids = extractor._extract_ids("Verifies: REQ-p00001-A")
    assert "REQ-p00001-A" in ids


def test_extract_ids_mixed_line(extractor):
    """Mixed line yields both REQ and JNY ids."""
    ids = extractor._extract_ids("Verifies: REQ-p00001-A, JNY-OQ-Login-01/step-2")
    assert "REQ-p00001-A" in ids
    assert "JNY-OQ-Login-01/step-2" in ids
