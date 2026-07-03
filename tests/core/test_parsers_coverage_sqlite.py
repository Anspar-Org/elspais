# Verifies: REQ-d00254-G, REQ-d00258-E
"""Tests for CoverageSqliteParser (coverage.py native `.coverage` DB, CUR-1568).

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
        "def add(a, b):\n" "    return a + b\n" "\n" "\n" "def sub(a, b):\n" "    return a - b\n",
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


class TestCanParse:
    def test_sniffs_sqlite_magic_bytes(self, cov_fixture: tuple[Path, Path]) -> None:
        _, cov_path = cov_fixture
        assert CoverageSqliteParser().can_parse(cov_path) is True

    def test_rejects_non_sqlite_file(self, tmp_path: Path) -> None:
        text_file = tmp_path / ".coverage"
        text_file.write_text("not a database", encoding="utf-8")
        assert CoverageSqliteParser().can_parse(text_file) is False

    def test_rejects_missing_file(self, tmp_path: Path) -> None:
        assert CoverageSqliteParser().can_parse(tmp_path / "nope") is False

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
        assert set(data.keys()) == {
            "line_coverage",
            "executable_lines",
            "covered_lines",
            "contexts",
        }
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
            "def covered():\n" "    return 1\n" "\n" "\n" "def uncovered():\n" "    return 2\n",
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

    def test_missing_coverage_package_degrades_to_empty_dict(
        self, cov_fixture: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When `coverage` is not importable, parse() returns {} rather
        than raising -- code_tested.direct stays 0, no crash (CUR-1568)."""
        import builtins

        _, cov_path = cov_fixture
        real_import = builtins.__import__

        def _fake_import(name, *args, **kwargs):
            if name == "coverage":
                raise ImportError("simulated missing dependency")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _fake_import)
        assert CoverageSqliteParser().parse("", str(cov_path)) == {}
