"""The e2e tier's two passes must split it, and `serial` must stay serial.

`.githooks/run-e2e-tier` runs the e2e tests not marked `serial` in parallel
and the `serial` ones afterwards with no other test process alive. Two
properties make that split hold: the passes' marker expressions select every
e2e test exactly once, and `tests/conftest.py` fails a `serial` test that an
xdist worker runs rather than letting it race the rest.
"""

import re
from pathlib import Path

import pytest
from _pytest.mark.expression import Expression

from tests import conftest as tests_conftest

_RUNNER = Path(__file__).resolve().parent.parent / ".githooks" / "run-e2e-tier"


class FakeItem:
    """Enough of a pytest Item for `pytest_runtest_setup` to judge."""

    def __init__(self, markers: set[str]) -> None:
        self._markers = markers
        self.keywords = dict.fromkeys(markers, True)
        self.parent = type("Parent", (), {})()

    def get_closest_marker(self, name):
        return object() if name in self._markers else None


def _pass_expressions() -> list[str]:
    """The `-m` expression each pytest invocation in the runner passes."""
    text = _RUNNER.read_text()
    found = re.findall(r'^pytest tests/ -m "([^"]+)"', text, flags=re.MULTILINE)
    if len(found) != 2:
        pytest.fail(f"expected two pytest passes in {_RUNNER}, found {found!r}")
    return found


@pytest.mark.parametrize(
    "markers",
    [
        {"e2e"},
        {"e2e", "serial"},
        {"e2e", "browser"},
        {"e2e", "browser", "serial"},
        {"e2e", "incremental"},
    ],
)
def test_every_e2e_test_runs_in_exactly_one_pass(markers):
    selected_by = [
        expr
        for expr in _pass_expressions()
        if Expression.compile(expr).evaluate(lambda name: name in markers)
    ]
    assert len(selected_by) == 1, f"{sorted(markers)} selected by {selected_by}"


def test_the_parallel_pass_selects_no_serial_test():
    parallel = [expr for expr in _pass_expressions() if "not serial" in expr]
    assert len(parallel) == 1
    assert not Expression.compile(parallel[0]).evaluate(lambda name: name in {"e2e", "serial"})


def test_a_serial_test_fails_on_an_xdist_worker(monkeypatch):
    monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw0")

    with pytest.raises(pytest.fail.Exception) as excinfo:
        tests_conftest.pytest_runtest_setup(FakeItem({"e2e", "serial"}))

    assert "serial" in str(excinfo.value)
    assert "-n" in str(excinfo.value)


def test_a_serial_test_runs_without_xdist(monkeypatch):
    monkeypatch.delenv("PYTEST_XDIST_WORKER", raising=False)

    tests_conftest.pytest_runtest_setup(FakeItem({"e2e", "serial"}))


def test_an_ordinary_test_runs_on_an_xdist_worker(monkeypatch):
    monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw0")

    tests_conftest.pytest_runtest_setup(FakeItem({"e2e"}))
