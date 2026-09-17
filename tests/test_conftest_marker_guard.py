"""The browser-tier guard must read a marker expression, not search it.

`tests/conftest.py` refuses `pytest -m browser` when playwright is absent,
because the browser module opens with `pytest.importorskip("playwright")` and
the tier would otherwise exit 0 having run nothing. The refusal has to key off
what the expression SELECTS: the project's own default addopts expression
(`not e2e and not browser and not stress`) mentions `browser` while selecting
nothing that carries it, so a substring test refuses an ordinary `pytest` run.
"""

import shlex
import sys
from pathlib import Path

import pytest
import tomllib

from tests import conftest as tests_conftest

_PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


def _selects_marker(expr: str, name: str) -> bool:
    """Reach the helper under test, failing loudly if it is absent."""
    fn = getattr(tests_conftest, "_selects_marker", None)
    if fn is None:
        pytest.fail(
            "tests.conftest._selects_marker is missing — the browser-tier guard "
            "has no way to tell a selecting expression from a mentioning one."
        )
    return fn(expr, name)


def _default_markexpr() -> str:
    """The `-m` expression pytest applies when the command line gives none."""
    addopts = tomllib.loads(_PYPROJECT.read_text())["tool"]["pytest"]["ini_options"]["addopts"]
    tokens = shlex.split(addopts) if isinstance(addopts, str) else list(addopts)
    for index, token in enumerate(tokens):
        if token == "-m":
            return tokens[index + 1]
        if token.startswith("-m") and len(token) > 2:
            return token[2:]
    pytest.fail(f"pyproject addopts carries no -m expression: {addopts!r}")


class FakeConfig:
    """Enough of a pytest Config for `pytest_configure` to run against."""

    def __init__(self, markexpr: str) -> None:
        self._markexpr = markexpr
        self.ini_lines: list[tuple[str, str]] = []

    def getoption(self, name, default=None):
        # The guard may read the option under either spelling; both name the
        # same thing, so the fake answers both and the test stays a test of
        # behaviour rather than of which spelling was chosen.
        if name in ("-m", "markexpr"):
            return self._markexpr
        return default

    def addinivalue_line(self, name: str, value: str) -> None:
        self.ini_lines.append((name, value))


@pytest.mark.parametrize(
    ("expr", "expected"),
    [
        ("not e2e and not browser and not stress", False),
        ("browser", True),
        ("e2e or browser", True),
        ("not browser", False),
        ("", False),
        ("e2e", False),
        ("browser and not e2e", True),
    ],
)
def test_selects_marker_truth_table(expr, expected):
    assert _selects_marker(expr, "browser") is expected


def test_project_default_expression_selects_no_browser_tests():
    """Whatever addopts currently says, a plain run must not select the tier."""
    assert _selects_marker(_default_markexpr(), "browser") is False


def test_malformed_expression_does_not_select():
    """An expression pytest itself would reject selects nothing here."""
    assert _selects_marker("browser and and", "browser") is False


def _hide_playwright(monkeypatch):
    # A None entry makes `import playwright` raise ImportError, which is what
    # the guard branches on.
    monkeypatch.setitem(sys.modules, "playwright", None)


def test_default_tier_is_not_refused_without_playwright(monkeypatch):
    """The CI regression: a plain `pytest` run must configure cleanly."""
    _hide_playwright(monkeypatch)
    config = FakeConfig(_default_markexpr())

    tests_conftest.pytest_configure(config)

    # It ran to completion rather than bailing out: the marker declarations
    # that follow the guard were recorded.
    assert any(
        name == "markers" and value.startswith("incremental:") for name, value in config.ini_lines
    )


def test_browser_tier_is_refused_without_playwright(monkeypatch):
    _hide_playwright(monkeypatch)
    config = FakeConfig("browser")

    with pytest.raises(pytest.UsageError) as excinfo:
        tests_conftest.pytest_configure(config)

    message = str(excinfo.value)
    assert "playwright" in message
    assert "[browser]" in message


def test_browser_tier_is_allowed_when_playwright_is_installed():
    pytest.importorskip("playwright")

    tests_conftest.pytest_configure(FakeConfig("browser"))
