# Verifies: REQ-d00254-E
"""Reporter registry: format name -> parser and kind (test-ingestion)."""

import pytest

from elspais.graph.parsers.results.registry import REPORTER_REGISTRY, get_reporter


def test_flutter_machine_is_results():
    spec = get_reporter("flutter-machine")
    assert spec.kind == "results"
    assert spec.parser_factory() is not None


def test_junit_is_results():
    spec = get_reporter("junit")
    assert spec.kind == "results"


def test_lcov_is_coverage():
    spec = get_reporter("lcov")
    assert spec.kind == "coverage"


def test_unknown_reporter_raises():
    with pytest.raises(KeyError):
        get_reporter("does-not-exist")


def test_builtins_registered():
    for name in ("flutter-machine", "junit", "pytest-json", "lcov", "coverage-json"):
        assert name in REPORTER_REGISTRY


def test_coverage_json_is_coverage():
    # Verifies: REQ-d00254-E
    # coverage-json is backed by CoverageJsonParser (coverage.py `coverage json` output)
    spec = get_reporter("coverage-json")
    assert spec.kind == "coverage"


def test_coverage_xml_is_not_registered():
    # The old misnaming "coverage-xml" must be gone; no silent footgun
    with pytest.raises(KeyError):
        get_reporter("coverage-xml")
