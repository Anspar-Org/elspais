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
from elspais.graph.parsers.results.coverage_sqlite import CoverageSqliteParser
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
    # Implements: REQ-d00254-O
    # The origin this format's line numbers count from. Declared here, where
    # the format is known, rather than left to each project to discover: the
    # `line` attribute pytest writes into JUnit XML counts from zero, while
    # the tool numbers source lines from one. A target may override it for a
    # producer that departs from its format's convention.
    line_base: int = 1
    # Implements: REQ-d00284-A
    # How this format's results name the test that produced them, where they
    # name no source file. Declared here, where the format is known, and
    # overridable per target -- the same arrangement REQ-d00254-O makes for the
    # origin a producer counts lines from. A format is not always a convention:
    # JUnit XML carries Java class names, Python module paths and JavaScript
    # spec basenames alike, so what stands here is the prevailing convention
    # among the producers that write it, and a producer departing from that
    # says so on its target.
    classname: str = "python-module"
    # Implements: REQ-d00286-E
    # What this format is, in the one sentence the published table of reporters
    # prints. It is declared beside the registration so the table and the
    # registry cannot name different sets: a format registered without a
    # sentence here is refused when the table is rendered, rather than reaching
    # a reader as an empty cell.
    description: str = ""


REPORTER_REGISTRY: dict[str, ReporterSpec] = {}


def register_reporter(spec: ReporterSpec) -> None:
    REPORTER_REGISTRY[spec.name] = spec


def get_reporter(name: str) -> ReporterSpec:
    if name not in REPORTER_REGISTRY:
        raise KeyError(f"Unknown reporter '{name}'. Known: {sorted(REPORTER_REGISTRY)}")
    return REPORTER_REGISTRY[name]


def _register_builtins() -> None:
    from elspais.graph.parsers.results.flutter_machine import FlutterMachineParser

    register_reporter(
        ReporterSpec(
            "flutter-machine",
            "stdout",
            "results",
            FlutterMachineParser,
            description=(
                "Parses the `flutter test --machine` JSON-line protocol from the command's "
                'stdout. Carries the real `suite.path` and test line, so `match = "source"` '
                "binds each result to the test that produced it."
            ),
        )
    )
    register_reporter(
        ReporterSpec(
            "junit",
            "file",
            "results",
            JUnitXMLParser,
            line_base=0,
            description=(
                "Parses JUnit XML result files matched by the `results` glob. Honours an "
                "optional per-`<testcase>` `file` attribute (a real source path) and `line` "
                'attribute, so `match = "source"` can bind to a scanned test node.'
            ),
        )
    )
    register_reporter(
        ReporterSpec(
            "pytest-json",
            "file",
            "results",
            PytestJSONParser,
            description=(
                "Parses the report pytest's `--json-report` writes, matched by the `results` glob."
            ),
        )
    )
    register_reporter(
        ReporterSpec(
            "lcov",
            "file",
            "coverage",
            LcovParser,
            description=(
                "Parses an LCOV report -- the `lcov.info` that `flutter test --coverage` and "
                "most language toolchains write -- into per-file line coverage."
            ),
        )
    )
    register_reporter(
        ReporterSpec(
            "coverage-json",
            "file",
            "coverage",
            CoverageJsonParser,
            description=(
                "Parses the JSON report `coverage json` (coverage.py) writes, in either its "
                "aggregate or its per-context form, into per-file line coverage."
            ),
        )
    )
    register_reporter(
        ReporterSpec(
            "coverage-sqlite",
            "file",
            "coverage",
            CoverageSqliteParser,
            description=(
                "Reads coverage.py's own `.coverage` SQLite data file through coverage.py's "
                "public API, so per-test contexts are read compactly rather than through a "
                "JSON expansion of them. Needs the `coverage` package (`elspais[coverage]`) "
                "importable, and degrades to unattributed coverage where it is not."
            ),
        )
    )


_register_builtins()
