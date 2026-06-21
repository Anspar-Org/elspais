"""Reporter registry: maps a `reporter` format name to its parser + channel.

Channel: "stdout" (captured from a runner command's stdout) or "file"
(read from the target's `results`/`coverage` path). Kind: "results"
(produces RESULT records) or "coverage" (annotates FILE line_coverage).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from elspais.graph.parsers.results.coverage_json import CoverageJsonParser
from elspais.graph.parsers.results.junit_xml import JUnitXMLParser
from elspais.graph.parsers.results.lcov import LcovParser
from elspais.graph.parsers.results.pytest_json import PytestJSONParser


# Implements: REQ-d00254-E
@dataclass(frozen=True)
class ReporterSpec:
    name: str
    channel: str  # "stdout" | "file"
    kind: str  # "results" | "coverage"
    parser_factory: Callable[[], Any]


REPORTER_REGISTRY: dict[str, ReporterSpec] = {}


def register_reporter(spec: ReporterSpec) -> None:
    REPORTER_REGISTRY[spec.name] = spec


def get_reporter(name: str) -> ReporterSpec:
    if name not in REPORTER_REGISTRY:
        raise KeyError(f"Unknown reporter '{name}'. Known: {sorted(REPORTER_REGISTRY)}")
    return REPORTER_REGISTRY[name]


def _register_builtins() -> None:
    from elspais.graph.parsers.results.flutter_machine import FlutterMachineParser

    register_reporter(ReporterSpec("flutter-machine", "stdout", "results", FlutterMachineParser))
    register_reporter(ReporterSpec("junit", "file", "results", JUnitXMLParser))
    register_reporter(ReporterSpec("pytest-json", "file", "results", PytestJSONParser))
    register_reporter(ReporterSpec("lcov", "file", "coverage", LcovParser))
    register_reporter(ReporterSpec("coverage-xml", "file", "coverage", CoverageJsonParser))


_register_builtins()
