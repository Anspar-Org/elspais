# Verifies: REQ-d00254-E
"""Reporter registry: format name -> parser + channel (test-ingestion)."""

import pytest

from elspais.graph.parsers.results.registry import REPORTER_REGISTRY, get_reporter


def test_flutter_machine_is_stdout_results():
    spec = get_reporter("flutter-machine")
    assert spec.channel == "stdout"
    assert spec.kind == "results"
    assert spec.parser_factory() is not None


def test_junit_is_file_results():
    spec = get_reporter("junit")
    assert spec.channel == "file"
    assert spec.kind == "results"


def test_lcov_is_file_coverage():
    spec = get_reporter("lcov")
    assert spec.channel == "file"
    assert spec.kind == "coverage"


def test_unknown_reporter_raises():
    with pytest.raises(KeyError):
        get_reporter("does-not-exist")


def test_builtins_registered():
    for name in ("flutter-machine", "junit", "pytest-json", "lcov", "coverage-xml"):
        assert name in REPORTER_REGISTRY
