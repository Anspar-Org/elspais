# Verifies: REQ-d00254-G, REQ-d00258-W
"""Tests for CoverageSqliteParser (coverage.py native `.coverage` DB).

Builds a tiny *real* `.coverage` SQLite data file by driving coverage.py's
own API against a throwaway module, with two fake per-test contexts (mirrors
pytest-cov's `--cov-context=test` dynamic-context switching), then asserts
the parser's output matches the shape `CoverageJsonParser` produces for
equivalent data.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

coverage = pytest.importorskip("coverage")

from elspais.graph.parsers.results.coverage_sqlite import (  # noqa: E402
    CoverageSqliteParser,
    create_parser,
)

_SQLITE_MAGIC = b"SQLite format 3\x00"


def _write_module(mod_path: Path) -> None:
    mod_path.parent.mkdir(parents=True, exist_ok=True)
    mod_path.write_text(
        "def add(a, b):\n    return a + b\n\n\ndef sub(a, b):\n    return a - b\n",
        encoding="utf-8",
    )


def _record_coverage(mod_path: Path, cov_path: Path) -> None:
    """Run `mod_path` under coverage.py with two fake per-test contexts.

    `add()` executes under context 1, `sub()` executes under context 2 --
    mirrors pytest-cov's nodeid-shaped `|run` dynamic contexts so
    `_normalize_run_context` in annotators.py can parse them.
    """
    cov = coverage.Coverage(data_file=str(cov_path), source=[str(mod_path.parent)])
    cov.start()
    try:
        spec = importlib.util.spec_from_file_location("cov_sqlite_fixture_mod", str(mod_path))
        mod = importlib.util.module_from_spec(spec)
        cov.switch_context("tests/test_mod.py::test_add|run")
        spec.loader.exec_module(mod)
        mod.add(1, 2)
        cov.switch_context("tests/test_mod.py::test_sub|run")
        mod.sub(5, 3)
    finally:
        cov.stop()
    cov.save()


@pytest.fixture
def cov_fixture(tmp_path: Path) -> tuple[Path, Path]:
    """Returns (mod_path, cov_path) for a tiny real `.coverage` DB."""
    mod_path = tmp_path / "mod.py"
    cov_path = tmp_path / ".coverage"
    _write_module(mod_path)
    _record_coverage(mod_path, cov_path)
    return mod_path, cov_path


class TestParserIdentity:
    def test_create_parser_returns_instance(self) -> None:
        assert isinstance(create_parser(), CoverageSqliteParser)

    def test_declares_binary(self) -> None:
        assert CoverageSqliteParser.binary is True


class TestParse:
    def test_produces_same_shape_as_coverage_json(self, cov_fixture: tuple[Path, Path]) -> None:
        mod_path, cov_path = cov_fixture
        results = CoverageSqliteParser().parse("", str(cov_path))

        assert str(mod_path) in results
        data = results[str(mod_path)]
        # Every key a coverage_json consumer reads must be present, so the
        # two are interchangeable downstream. This parser carries one more:
        # only it re-analyses source, so only it can find that a file's total
        # is unknown (REQ-d00254-Q). An extra key no consumer reads costs
        # them nothing; a missing one would break them.
        assert set(data.keys()) >= {
            "line_coverage",
            "executable_lines",
            "covered_lines",
            "contexts",
        }
        assert data["source_analysed"] is True
        assert isinstance(data["line_coverage"], dict)
        assert isinstance(data["executable_lines"], int)
        assert isinstance(data["covered_lines"], int)

        # `return a + b` is line 2, `return a - b` is line 6.
        assert data["line_coverage"].get(2) == 1
        assert data["line_coverage"].get(6) == 1
        assert data["executable_lines"] >= 2
        assert data["covered_lines"] >= 2

    def test_per_test_contexts_attribute_distinct_lines(
        self, cov_fixture: tuple[Path, Path]
    ) -> None:
        """The two fake tests exercised disjoint lines -- contexts must
        distinguish them (this is the whole point of per-test attribution)."""
        mod_path, cov_path = cov_fixture
        results = CoverageSqliteParser().parse("", str(cov_path))
        contexts = results[str(mod_path)]["contexts"]

        assert contexts is not None
        add_line_ctxs = set(contexts.get(2, []))
        sub_line_ctxs = set(contexts.get(6, []))

        assert any("test_add" in c for c in add_line_ctxs)
        assert any("test_sub" in c for c in sub_line_ctxs)
        # Disjoint: test_add's context must not appear on sub's line and vice versa.
        assert not any("test_sub" in c for c in add_line_ctxs)
        assert not any("test_add" in c for c in sub_line_ctxs)

    def test_missing_lines_marked_zero(self, tmp_path: Path) -> None:
        """A statement never executed under any context is recorded as 0."""
        mod_path = tmp_path / "partial.py"
        mod_path.write_text(
            "def covered():\n    return 1\n\n\ndef uncovered():\n    return 2\n",
            encoding="utf-8",
        )
        cov_path = tmp_path / ".coverage"
        cov = coverage.Coverage(data_file=str(cov_path), source=[str(tmp_path)])
        cov.start()
        spec = importlib.util.spec_from_file_location("cov_sqlite_partial_mod", str(mod_path))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.covered()
        cov.stop()
        cov.save()

        results = CoverageSqliteParser().parse("", str(cov_path))
        data = results[str(mod_path)]
        assert data["line_coverage"].get(2) == 1
        assert data["line_coverage"].get(6) == 0
        assert data["covered_lines"] < data["executable_lines"]

    def test_returns_empty_dict_for_unreadable_file(self, tmp_path: Path) -> None:
        bogus = tmp_path / ".coverage"
        bogus.write_bytes(_SQLITE_MAGIC + b"not really a coverage db")
        assert CoverageSqliteParser().parse("", str(bogus)) == {}

    def test_wanted_files_rejection_never_materializes_contexts(
        self, cov_fixture: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A measured file rejected by `wanted_files` gets line_coverage but
        its per-line context lists are NEVER materialized -- coverage.py's
        contexts_by_lineno() must not even be called for it (the contexts
        map is the suite-scaled part of the data)."""
        mod_path, cov_path = cov_fixture

        queried: list[str] = []
        orig = coverage.CoverageData.contexts_by_lineno

        def _spy(self, filename):
            queried.append(filename)
            return orig(self, filename)

        monkeypatch.setattr(coverage.CoverageData, "contexts_by_lineno", _spy)

        results = CoverageSqliteParser().parse("", str(cov_path), wanted_files=lambda f: False)

        assert queried == [], "contexts_by_lineno must not be called for rejected files"
        data = results[str(mod_path)]
        assert data["contexts"] is None
        # Non-context data is still emitted for rejected files.
        assert data["line_coverage"].get(2) == 1
        assert data["executable_lines"] >= 2

    def test_wanted_files_acceptance_materializes_contexts(
        self, cov_fixture: tuple[Path, Path]
    ) -> None:
        """A measured file accepted by `wanted_files` gets the same contexts
        as an unfiltered parse; the predicate receives coverage.py's recorded
        (absolute) path so callers can resolve it against the graph."""
        mod_path, cov_path = cov_fixture

        seen: list[str] = []

        def _accept(f: str) -> bool:
            seen.append(f)
            return True

        filtered = CoverageSqliteParser().parse("", str(cov_path), wanted_files=_accept)
        unfiltered = CoverageSqliteParser().parse("", str(cov_path))

        assert str(mod_path) in seen
        assert filtered[str(mod_path)]["contexts"] == unfiltered[str(mod_path)]["contexts"]
        assert filtered[str(mod_path)]["contexts"] is not None

    def test_missing_coverage_package_degrades_to_empty_dict(
        self, cov_fixture: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When `coverage` is not importable, parse() returns {} rather
        than raising -- code_tested.immediate_direct stays 0, no crash."""
        import builtins

        _, cov_path = cov_fixture
        real_import = builtins.__import__

        def _fake_import(name, *args, **kwargs):
            if name == "coverage":
                raise ImportError("simulated missing dependency")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _fake_import)
        assert CoverageSqliteParser().parse("", str(cov_path)) == {}


# A module whose statements span several lines. On every supported Python the
# tracer reports a line event for a continuation line of some of them and none
# for the line the statement starts on (the bare parenthesised expression, the
# ``del``), so a statement is covered only where its executed lines are
# translated to its first line.
_MULTI_LINE_SOURCE = """\
def build(x, pair):
    table = {
        "a": x,
        "b": pair,
    }
    if (
        x
        and pair
    ):
        x = x + 1
    (
        table.get
    )
    del (
        table
    )
    return x


def unused(y):
    pair = (
        y,
        y * 2,
    )
    return pair


def skipped():  # pragma: no cover
    return 0
"""

_IMPORT_CONTEXT = "tests/test_multi.py::test_import|run"
_BUILD_CONTEXT = "tests/test_multi.py::test_build|run"


@pytest.fixture
def multi_line_fixture(tmp_path: Path) -> tuple[Path, Path]:
    """Returns (mod_path, cov_path) for a `.coverage` DB over multi-line statements.

    The module is imported under one context and `build()` runs under another;
    `unused()` never runs and `skipped()` is excluded.
    """
    mod_path = tmp_path / "multi.py"
    mod_path.write_text(_MULTI_LINE_SOURCE, encoding="utf-8")
    cov_path = tmp_path / ".coverage"
    cov = coverage.Coverage(data_file=str(cov_path), source=[str(tmp_path)])
    cov.start()
    try:
        spec = importlib.util.spec_from_file_location("cov_sqlite_multi_mod", str(mod_path))
        mod = importlib.util.module_from_spec(spec)
        cov.switch_context(_IMPORT_CONTEXT)
        spec.loader.exec_module(mod)
        cov.switch_context(_BUILD_CONTEXT)
        mod.build(1, (2, 3))
    finally:
        cov.stop()
    cov.save()
    return mod_path, cov_path


def _analysis_oracle(mod_path: Path, cov_path: Path) -> tuple[set[int], set[int], set[int]]:
    """coverage.py's own (statements, missing, raw executed lines) for the file."""
    cov = coverage.Coverage(data_file=str(cov_path), config_file=False)
    cov.load()
    _, statements, _excluded, missing, _ = cov.analysis2(str(mod_path))
    raw = set(cov.get_data().lines(str(mod_path)) or [])
    return set(statements), set(missing), raw


_WANTED = [
    pytest.param(None, id="all-files"),
    pytest.param(lambda f: False, id="file-rejected"),
]


class TestMultiLineStatements:
    def test_fixture_needs_line_translation(self, multi_line_fixture: tuple[Path, Path]) -> None:
        """Some covered statement has no line event of its own and some
        traced line is no statement, so the parser can match coverage.py
        only by translating executed lines to their statements."""
        mod_path, cov_path = multi_line_fixture
        statements, missing, raw = _analysis_oracle(mod_path, cov_path)

        assert (statements - missing) - raw, "a covered statement must be untraced"
        assert raw - statements, "a traced line must lie inside a statement"
        assert missing, "the fixture must hold an unexecuted statement"

    @pytest.mark.parametrize("wanted_files", _WANTED)
    def test_line_figures_match_coverage_analysis(
        self, multi_line_fixture: tuple[Path, Path], wanted_files
    ) -> None:
        """line_coverage, executable_lines and covered_lines equal what
        coverage.py's own analysis reports, whether or not the file's
        contexts are read."""
        mod_path, cov_path = multi_line_fixture
        statements, missing, _raw = _analysis_oracle(mod_path, cov_path)

        results = CoverageSqliteParser().parse("", str(cov_path), wanted_files=wanted_files)
        data = results[str(mod_path)]

        assert data["source_analysed"] is True
        assert data["line_coverage"] == {ln: 0 if ln in missing else 1 for ln in statements}
        assert data["executable_lines"] == len(statements)
        assert data["covered_lines"] == len(statements - missing)

    def test_rejected_file_carries_no_contexts(self, multi_line_fixture: tuple[Path, Path]) -> None:
        mod_path, cov_path = multi_line_fixture
        results = CoverageSqliteParser().parse("", str(cov_path), wanted_files=lambda f: False)
        assert results[str(mod_path)]["contexts"] is None

    def test_accepted_file_names_the_context_of_each_executed_line(
        self, multi_line_fixture: tuple[Path, Path]
    ) -> None:
        """Every traced line is attributed, lines inside `build()` to the
        test that called it and every other line to the import."""
        mod_path, cov_path = multi_line_fixture
        _statements, _missing, raw = _analysis_oracle(mod_path, cov_path)
        build_body = range(2, 18)

        results = CoverageSqliteParser().parse("", str(cov_path), wanted_files=lambda f: True)
        contexts = results[str(mod_path)]["contexts"]

        assert contexts is not None
        assert set(contexts) == raw
        for line, names in contexts.items():
            expected = _BUILD_CONTEXT if line in build_body else _IMPORT_CONTEXT
            assert names == [expected], f"line {line}"
