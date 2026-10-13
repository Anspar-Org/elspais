"""The structural Python diff, and the rule file's path globs (pure functions)."""

from __future__ import annotations

import pytest

from tools.tia.config import glob_to_regex, path_matches
from tools.tia.pyimpact import FILE, FUNCTION, MODULE, analyze_python_change

BASE = """import functools


class Plain:
    def a(self):
        return 1


class Child(Base):
    def a(self):
        return 2


def f(x):
    y = x + 1
    return y


@functools.cache
def memo(x):
    return x * 2


def target():
    return 0
"""

F_SPAN = (14, 16)  # f's def line to last line in BASE


def _edit(old: str, new: str):
    def apply(text: str) -> str:
        assert old in text, old
        return text.replace(old, new, 1)

    return apply


def analyze(new_text: str | None, *, path="src/pkg/m.py", old_text: str | None = BASE, refs=()):
    return analyze_python_change(
        path,
        None if old_text is None else old_text.encode(),
        None if new_text is None else new_text.encode(),
        memoizing={"cache", "lru_cache"},
        referenced_names=set(refs),
    )


def test_base_span_matches_source():
    lines = BASE.splitlines()
    assert lines[F_SPAN[0] - 1].startswith("def f(")
    assert lines[F_SPAN[1] - 1].strip() == "return y"


@pytest.mark.parametrize(
    "edit, path, scope, detail",
    [
        (_edit("y = x + 1", "y = x + 2"), "src/pkg/m.py", FUNCTION, "f changed"),
        (_edit("def f(x):", "def f(x, z=0):"), "src/pkg/m.py", FUNCTION, "f changed"),
        (
            _edit("    y = x + 1\n", "    y = x + 1\n    # a note\n"),
            "src/pkg/m.py",
            FUNCTION,
            "text-only",
        ),
        (
            _edit("def target():", "@functools.wraps(len)\ndef target():"),
            "src/pkg/m.py",
            MODULE,
            "decorators of target changed",
        ),
        (
            _edit("class Child(Base):", "class Child(Base, Mixin):"),
            "src/pkg/m.py",
            MODULE,
            "bases of class Child changed",
        ),
        (
            _edit(
                "        return 1\n", "        return 1\n\n    def fresh(self):\n        return 3\n"
            ),
            "src/pkg/m.py",
            FILE,
            "method Plain.fresh added",
        ),
        (
            _edit(
                "        return 2\n", "        return 2\n\n    def fresh(self):\n        return 3\n"
            ),
            "src/pkg/m.py",
            MODULE,
            "method Child.fresh added",
        ),
        (
            _edit(
                "        return 1\n",
                "        return 1\n\n    def __len__(self):\n        return 3\n",
            ),
            "src/pkg/m.py",
            MODULE,
            "method Plain.__len__ added",
        ),
        (_edit("return x * 2", "return x * 3"), "src/pkg/m.py", MODULE, "memoized function memo"),
        (_edit("def f(x):", "def f(x:"), "src/pkg/m.py", MODULE, "does not parse"),
        (_edit("def f(x):", "def g(x):"), "src/pkg/m.py", MODULE, "function f removed"),
        (lambda t: "import os\n" + t, "src/pkg/m.py", FILE, "import added"),
        (lambda t: "import os\n" + t, "src/pkg/__init__.py", MODULE, "statements changed"),
        (_edit("import functools", "import functools\nLIMIT = 3"), "src/pkg/m.py", MODULE, ""),
        (lambda t: t + "\n\ndef newcomer():\n    return 1\n", "src/pkg/m.py", FILE, "added"),
    ],
    ids=[
        "body",
        "signature",
        "comment-in-function",
        "decorator",
        "class-bases",
        "method-on-baseless-class",
        "method-on-class-with-bases",
        "dunder-method",
        "memoized-body",
        "syntax-error",
        "renamed-function",
        "added-import",
        "added-import-in-init",
        "module-constant",
        "new-function",
    ],
)
def test_change_scope(edit, path, scope, detail):
    res = analyze(edit(BASE), path=path)
    assert res.scope == scope
    assert any(detail in i.detail for i in res.impacts if i.scope == scope)


@pytest.mark.parametrize(
    "edit",
    [
        _edit("y = x + 1", "y = x + 2"),
        _edit("    y = x + 1\n", "    y = x + 1\n    # a note\n"),
        lambda t: "# header\n" * 7 + t.replace("y = x + 1", "y = x + 2"),
    ],
    ids=["body", "comment", "body-after-insertion"],
)
def test_function_impact_is_in_baseline_coordinates(edit):
    res = analyze(edit(BASE))
    fn = [i for i in res.impacts if i.scope == FUNCTION]
    assert [(i.unit, i.lines) for i in fn] == [("f", F_SPAN)]
    assert res.scope == FUNCTION


def test_comment_appended_at_end_of_function_is_text_only_edit():
    res = analyze(BASE.replace("    return y\n", "    return y\n    # trailing note\n"))
    assert [(i.unit, i.lines) for i in res.impacts] == [("f", F_SPAN)]


def test_comment_outside_functions_has_no_impact():
    res = analyze("# header\n# more\n" + BASE)
    assert res.impacts == []
    assert res.scope is None


def test_new_function_under_a_referenced_name_is_module_scope():
    res = analyze(BASE + "\n\ndef handler():\n    return 1\n", refs={"handler"})
    assert res.scope == MODULE


@pytest.mark.parametrize(
    "old, new, scope",
    [(None, "x = 1\n", FILE), (BASE, None, MODULE)],
    ids=["new-module", "deleted-module"],
)
def test_added_or_deleted_module(old, new, scope):
    assert analyze(new, old_text=old).scope == scope


def test_unchanged_source_has_no_impact():
    res = analyze(BASE)
    assert res.impacts == []
    assert res.hunks == []


# -- path globs ------------------------------------------------------------------


@pytest.mark.parametrize(
    "pattern, path, matches",
    [
        ("tools/tia/**", "tools/tia/selector.py", True),
        ("tools/tia/**", "tools/tia/sub/deep.py", True),
        ("tools/tia/**", "tools/other.py", False),
        ("**/conftest.py", "conftest.py", True),
        ("**/conftest.py", "tests/a/b/conftest.py", True),
        ("**/conftest.py", "tests/a/b/not_conftest.py", False),
        ("a/**/b.txt", "a/b.txt", True),
        ("a/**/b.txt", "a/x/y/b.txt", True),
        ("*.py", "setup.py", True),
        ("*.py", "pkg/setup.py", False),
        ("tests/*.py", "tests/test_x.py", True),
        ("tests/*.py", "tests/sub/test_x.py", False),
        ("requirements*.txt", "requirements-dev.txt", True),
        ("requirements*.txt", "docs/requirements.txt", False),
        ("conftest.py", "conftest.py", True),
        ("conftest.py", "tests/conftest.py", False),
        ("Pipfile*", "Pipfile.lock", True),
        ("file?.txt", "file1.txt", True),
        ("file?.txt", "file/.txt", False),
        ("a.b", "axb", False),
    ],
)
def test_glob_to_regex(pattern, path, matches):
    assert bool(glob_to_regex(pattern).match(path)) is matches


def test_path_matches_any_pattern():
    assert path_matches("uv.lock", ["setup.py", "uv.lock"])
    assert not path_matches("tests/uv.lock", ["setup.py", "uv.lock"])
    assert not path_matches("anything", [])


def test_glob_character_class_is_fnmatch_style():
    assert glob_to_regex("requirements[0-9].txt").match("requirements3.txt")
