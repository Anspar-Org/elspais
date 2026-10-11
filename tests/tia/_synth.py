"""Synthetic repositories and baselines for the TIA selector's tests.

Nothing here runs pytest or coverage over the synthetic suite. A baseline is
assembled from recorder-shaped shards and a coverage.py data file written
through coverage's public API, with line numbers taken from the synthetic
sources themselves (so the baseline's coordinates are honest), then handed to
`tools.tia.baseline.build_baseline` exactly as the unit tier would.

Layout of a work directory::

    <work>/repo        the git repository (committed, clean)
    <work>/baseline    the baseline directory (outside the repo, so it is
                       never an untracked change)
"""

from __future__ import annotations

import ast
import copy
import functools
import json
import os
import shutil
import subprocess
from pathlib import Path

from coverage import CoverageData

from tools.tia.baseline import build_baseline
from tools.tia.config import Config, load_config
from tools.tia.recorder import environment_fingerprint, git_identity
from tools.tia.selector import Selection, select

# -- the synthetic repository -------------------------------------------------

FILES: dict[str, str] = {
    "README.md": "# synthetic\n\nNothing reads this.\n",
    "pyproject.toml": (
        '[project]\nname = "pkg"\nversion = "1.0.0"\ndependencies = ["tomlkit>=0.12"]\n'
    ),
    "src/pkg/__init__.py": '"""Synthetic package."""\n',
    "src/pkg/core.py": '''"""Core arithmetic for the synthetic package."""

LIMIT = 10
TEMPLATE = "data/template.txt"


def add(a, b):
    total = a + b
    total = int(total)
    return total


def mul(a, b):
    product = a * b
    return product


def scale(values, factor):
    out = [v * factor for v in values]
    return out


def unused(x):
    doubled = x * 2
    return doubled


class Box:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value
''',
    "src/pkg/util.py": '''"""Helpers built on core."""

from pkg import core


def double(x):
    return core.mul(x, 2)


def capped(x):
    return min(x, core.LIMIT)


def load_plugin():
    try:
        from pkg import plugin
    except ImportError:
        return None
    return plugin.NAME
''',
    "src/pkg/other.py": '''"""An independent module."""


def greet(name):
    return "hello " + name
''',
    "src/pkg/lonely.py": '''"""Nothing imports or executes this module."""


def solo(x):
    return x
''',
    "src/pkg/data/template.txt": "Hello {name}\n",
    "tests/__init__.py": "",
    "tests/conftest.py": """import pytest


@pytest.fixture(scope="session")
def scaled():
    from pkg import core

    return core.scale([1, 2], 3)


@pytest.fixture(scope="session")
def shared_project():
    with open("tests/data/shared.txt") as fh:
        return fh.read()
""",
    "tests/helpers.py": "def three():\n    return 3\n",
    "tests/orphan_helper.py": "def unused_helper():\n    return None\n",
    "tests/test_core.py": """from pkg import core


def test_add():
    assert core.add(1, 2) == 3


def test_mul():
    assert core.mul(2, 3) == 6


class TestBox:
    def test_get(self):
        assert core.Box(4).get() == 4
""",
    "tests/test_util.py": """from pkg import util
from tests import helpers


def test_double():
    assert util.double(helpers.three()) == 6


def test_capped():
    assert util.capped(99) == 10
""",
    "tests/test_data.py": """def test_reads_sample():
    with open("tests/data/sample.txt") as fh:
        assert fh.read()


def test_fixture_user_a(shared_project):
    assert shared_project


def test_fixture_user_b(shared_project):
    assert shared_project
""",
    "tests/test_shared_a.py": "def test_first(scaled):\n    assert scaled == [3, 6]\n",
    "tests/test_shared_b.py": "def test_second(scaled):\n    assert scaled\n",
    "tests/test_other.py": """import os

from pkg import other


def test_other_a():
    assert other.greet("x") == "hello x"


def test_other_b():
    assert "other.py" in os.listdir("src/pkg")
""",
    "tests/data/sample.txt": "sample data\n",
    "tests/data/shared.txt": "shared data\n",
}

CORE = "src/pkg/core.py"
UTIL = "src/pkg/util.py"
OTHER = "src/pkg/other.py"

#: Shared-fixture keys, as `recorder._fixture_key` spells them.
K_PROJECT = "session:tests::shared_project"
K_SCALED = "session:tests::scaled"

# Node ids of the synthetic inventory.
ADD = "tests/test_core.py::test_add"
MUL = "tests/test_core.py::test_mul"
GET = "tests/test_core.py::TestBox::test_get"
DOUBLE = "tests/test_util.py::test_double"
CAPPED = "tests/test_util.py::test_capped"
SAMPLE = "tests/test_data.py::test_reads_sample"
USER_A = "tests/test_data.py::test_fixture_user_a"
USER_B = "tests/test_data.py::test_fixture_user_b"
FIRST = "tests/test_shared_a.py::test_first"
SECOND = "tests/test_shared_b.py::test_second"
OTHER_A = "tests/test_other.py::test_other_a"
OTHER_B = "tests/test_other.py::test_other_b"


def default_tests() -> dict[str, dict]:
    """The baseline inventory: what each test covered, read, listed, spawned.

    ``cover`` maps a phase to (path, qualified function) pairs whose body
    lines the phase executed.
    """

    def t(**kw):
        base = {
            "cls": None,
            "outcome": "passed",
            "shared_fixtures": [],
            "setup_executed": [],
            "teardown_finalized": [],
            "cover": {},
            "reads": {},
            "lists": {},
            "spawns": {},
        }
        base.update(kw)
        return base

    return {
        ADD: t(cover={"run": [(CORE, "add")]}),
        MUL: t(cover={"run": [(CORE, "mul")]}),
        GET: t(cls="TestBox", cover={"run": [(CORE, "Box.__init__"), (CORE, "Box.get")]}),
        DOUBLE: t(cover={"run": [(UTIL, "double"), (CORE, "mul")]}),
        CAPPED: t(cover={"run": [(UTIL, "capped")]}),
        SAMPLE: t(reads={"run": ["tests/data/sample.txt"]}),
        USER_A: t(
            shared_fixtures=[K_PROJECT],
            setup_executed=[K_PROJECT],
            reads={"setup": ["tests/data/shared.txt"]},
        ),
        USER_B: t(shared_fixtures=[K_PROJECT]),
        FIRST: t(
            shared_fixtures=[K_SCALED],
            setup_executed=[K_SCALED],
            cover={"setup": [(CORE, "scale")]},
        ),
        SECOND: t(shared_fixtures=[K_SCALED]),
        OTHER_A: t(cover={"run": [(OTHER, "greet")]}),
        OTHER_B: t(lists={"run": ["src/pkg"]}),
    }


def synth_config(**overrides) -> Config:
    """A Config for the synthetic layout, carrying the production rules."""
    real = load_config()
    kw = {
        "test_roots": ["tests"],
        "production_roots": ["src/pkg"],
        "import_roots": ["src", "."],
        "granularity": "test",
        "full_suite_threshold": real.full_suite_threshold,
        "opaque_programs": list(real.opaque_programs),
        "memoizing_decorators": list(real.memoizing_decorators),
        "max_baseline_age_days": real.max_baseline_age_days,
        "on_environment_change": "full",
        "rules": list(real.rules),
    }
    kw.update(overrides)
    return Config(**kw)


# -- git ---------------------------------------------------------------------


def git_env() -> dict[str, str]:
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_"))
        and k not in ("GIT_CONFIG_COUNT", "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE")
    }
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    return env


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, env=git_env(), capture_output=True, text=True, check=True
    ).stdout


def write(repo: Path, rel: str, text: str) -> None:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def read(repo: Path, rel: str) -> str:
    return (repo / rel).read_text(encoding="utf-8")


def replace(repo: Path, rel: str, old: str, new: str) -> None:
    text = read(repo, rel)
    assert old in text, f"{old!r} not in {rel}"
    write(repo, rel, text.replace(old, new, 1))


def make_repo(repo: Path) -> None:
    repo.mkdir(parents=True)
    git(repo, "init", "-q", "-b", "main")
    for k, v in (
        ("user.name", "tia-tests"),
        ("user.email", "tia@example.invalid"),
        ("commit.gpgsign", "false"),
        ("tag.gpgsign", "false"),
    ):
        git(repo, "config", "--local", k, v)
    for rel, text in FILES.items():
        write(repo, rel, text)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "synthetic")


# -- coordinates -------------------------------------------------------------


def body_lines(source: str, qualname: str) -> list[int]:
    """The lines a call of `qualname` executes: first body line to end."""
    tree = ast.parse(source)
    body = tree.body
    node = None
    for part in qualname.split("."):
        node = next(
            n
            for n in body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            and n.name == part
        )
        body = node.body
    return list(range(node.body[0].lineno, node.end_lineno + 1))


def def_span(source: str, qualname: str) -> tuple[int, int]:
    """The (def line, last line) of a function, as pyimpact keys a unit."""
    tree = ast.parse(source)
    body = tree.body
    node = None
    for part in qualname.split("."):
        node = next(n for n in body if getattr(n, "name", None) == part)
        body = node.body
    start = min([node.lineno] + [d.lineno for d in node.decorator_list])
    return start, node.end_lineno


# -- baselines ---------------------------------------------------------------


@functools.lru_cache(maxsize=1)
def _env_cached() -> str:
    return json.dumps(environment_fingerprint())


def current_env() -> dict:
    return json.loads(_env_cached())


def make_baseline(
    repo: Path,
    dest: Path,
    tests: dict[str, dict] | None = None,
    *,
    shard_overrides: dict | None = None,
    extra_attribution: dict | None = None,
    context_rename=None,
) -> dict:
    """Write shards + coverage for `tests` and build a baseline into `dest`.

    `shard_overrides` is merged into the controller shard (after identity
    and environment are filled in); `extra_attribution` adds attribution
    buckets such as ``session`` or ``collect:<nodeid>``. `context_rename` maps a node id to the
    name its coverage contexts carry (to make contexts name unknown tests).
    """
    tests = copy.deepcopy(default_tests() if tests is None else tests)
    root = os.path.realpath(repo)
    run_dir = Path(str(dest) + "-run")
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True)

    sources: dict[str, str] = {}

    def src(rel: str) -> str:
        if rel not in sources:
            sources[rel] = (Path(root) / rel).read_text(encoding="utf-8")
        return sources[rel]

    cov_path = run_dir / ".coverage"
    data = CoverageData(basename=str(cov_path))
    attribution: dict[str, dict] = {}
    shard_tests: dict[str, dict] = {}
    for nodeid, spec in tests.items():
        phases = {"setup": "passed", "call": spec["outcome"], "teardown": "passed"}
        if spec["outcome"] == "skipped":
            phases = {"setup": "skipped"}
        shard_tests[nodeid] = {
            "file": nodeid.split("::", 1)[0],
            "cls": spec["cls"],
            "shared_fixtures": spec["shared_fixtures"],
            "setup_executed": spec["setup_executed"],
            "teardown_finalized": spec["teardown_finalized"],
            "outcome": spec["outcome"],
            "duration": 0.01,
            "phases": phases,
        }
        ctx_name = (context_rename or {}).get(nodeid, nodeid)
        for phase, pairs in spec["cover"].items():
            data.set_context(f"{ctx_name}|{phase}")
            lines: dict[str, list[int]] = {}
            for rel, qual in pairs:
                lines.setdefault(os.path.join(root, rel), []).extend(body_lines(src(rel), qual))
            data.add_lines(lines)
        for key in ("reads", "lists", "spawns"):
            for phase, items in spec[key].items():
                bucket = attribution.setdefault(f"{nodeid}|{phase}", {})
                bucket.setdefault(key, []).extend(items)
    data.write()
    for bucket, attrib in (extra_attribution or {}).items():
        attribution.setdefault(bucket, {}).update(attrib)

    shard = {
        "worker": "main",
        "controller": True,
        "pid": 1,
        "exitstatus": 1 if any(t["outcome"] == "failed" for t in tests.values()) else 0,
        "started": 0.0,
        "finished": 1.0,
        "root": root,
        "argv": ["tests/"],
        "markexpr": "",
        "items": list(shard_tests),
        "tests": shard_tests,
        "attribution": attribution,
        "errors": [],
        "identity_start": git_identity(root),
        "environment": current_env(),
    }
    shard["identity_end"] = copy.deepcopy(shard["identity_start"])
    shard.update(shard_overrides or {})
    with open(run_dir / "tia-shard-main.json", "w", encoding="utf-8") as fh:
        json.dump(shard, fh)
    return build_baseline(str(run_dir), str(dest), str(cov_path))


def git_identity_of(repo: Path) -> dict:
    return git_identity(os.path.realpath(repo))


def make_template(work: Path) -> None:
    make_repo(work / "repo")
    make_baseline(work / "repo", work / "baseline")


def clone_work(template: Path, dest: Path) -> Path:
    """Copy a template work directory. File times are NOT preserved, so git
    re-reads every file rather than trusting stat data copied from elsewhere."""
    shutil.copytree(template, dest, symlinks=True, copy_function=shutil.copy)
    return dest


# -- selection ---------------------------------------------------------------


def select_now(repo: Path, baseline_dir: Path, config: Config | None = None, **kw) -> Selection:
    kw.setdefault("current_env", current_env())
    return select(str(repo), config or synth_config(), str(baseline_dir), **kw)


def selected(sel: Selection) -> set[str]:
    return set(sel.tests)


def kinds(sel: Selection) -> list[str]:
    return [f.kind for f in sel.fallbacks]


def report_for(sel: Selection, path: str):
    return next(r for r in sel.changed if r.path == path)
