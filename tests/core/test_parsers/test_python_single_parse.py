"""A Python file's content is parsed once per file dispatch.

A dispatch asks the parser several questions about one source -- the line
context (or the tests a file holds), and the lines interior to a string
literal -- and every answer is read from the one reading ``read_python``
makes.  Parsing the same content again per question was most of what a build
spent in ``ast``, so these tests count the parses one dispatch makes.

Deliberately uncited: how often the parser is asked answers to no assertion
in the estate.  The behaviour the readings carry -- what a citation binds to,
which lines are quoted -- is established, and cited, where it is specified.
"""

from __future__ import annotations

import ast

import pytest

from elspais.graph.parsers.lark import FileDispatcher
from tests.core.graph_test_helpers import grammar_for

SOURCE = '''\
import pytest


def helper():
    return """
    # Verifies: REQ-d00002-A
    """


class TestWidget:
    # Verifies: REQ-d00001-A
    @pytest.mark.parametrize("x", [1])
    def test_renders(self, x):
        assert helper()


# Verifies: REQ-d00001-B
def build():
    return 1
'''


@pytest.fixture
def parse_calls(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Every source handed to ``ast.parse`` while the test runs.

    Building a dispatcher's grammar evaluates literals through ``ast`` too, so
    a test counts the parses of the content it dispatched, not every call.
    """
    calls: list[str] = []
    real_parse = ast.parse

    def counting_parse(source, *args, **kwargs):
        calls.append(source)
        return real_parse(source, *args, **kwargs)

    monkeypatch.setattr(ast, "parse", counting_parse)
    return calls


def _references(parsed: list) -> list[tuple[int, str]]:
    """(line, referenced id) for every citation the dispatch read."""
    found = []
    for content in parsed:
        data = content.parsed_data or {}
        for ref in data.get("verifies", []) + data.get("implements", []):
            found.append((content.start_line, ref))
    return sorted(found)


@pytest.mark.parametrize("kind", ["test", "code"])
def test_one_dispatch_parses_a_python_file_once(kind: str, parse_calls: list[str]) -> None:
    dispatcher = FileDispatcher(grammar_for("REQ"))
    dispatch = dispatcher.dispatch_test if kind == "test" else dispatcher.dispatch_code

    parsed = dispatch(SOURCE, "tests/test_widget.py")

    parses = parse_calls.count(SOURCE)
    assert parses == 1, (
        f"dispatch_{kind} parsed the file {parses} times; every pre-scan "
        "must read the one parse the dispatch made"
    )
    # The one reading still answers every question: the citations outside the
    # literal are read, and the one written inside the literal is not.
    refs = [ref for _line, ref in _references(parsed)]
    assert "REQ-d00002-A" not in refs, "a citation inside a string literal was read"
    assert {"REQ-d00001-A", "REQ-d00001-B"} <= set(refs), refs


def test_a_dispatch_of_a_file_that_does_not_parse_asks_once(parse_calls: list[str]) -> None:
    """A file the parser refuses is refused once, and the scan falls back to text."""
    source = "# Verifies: REQ-d00001-A\ndef test_broken(:\n    pass\n"
    dispatcher = FileDispatcher(grammar_for("REQ"))

    parsed = dispatcher.dispatch_test(source, "tests/test_broken.py")

    assert parse_calls.count(source) == 1
    assert [ref for _line, ref in _references(parsed)] == ["REQ-d00001-A"]
