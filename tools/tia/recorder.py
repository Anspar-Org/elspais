"""pytest plugin recording the per-test facts line coverage cannot see.

Loaded with ``-p tools.tia.recorder``; inert unless ``TIA_RECORD_DIR`` names a
directory. pytest-cov's ``--cov-context=test`` already records which test ran
each production line. That attribution has three blind spots this plugin
closes, so the selector can be conservative about them:

1. Shared fixtures. A session/module/class-scoped fixture runs once, inside
   the *setup* phase of the first test that requests it, so its lines are
   credited to that one test. Every later user depends on the same code. We
   record, per test, which shared fixtures it depends on and which ones were
   actually executed (or finalized) during its setup (teardown) phase; the
   selector expands a setup/teardown hit to every user of those fixtures.

2. Files read as data. Fixture projects, docs, templates and the repository's
   own sources are read, not executed. An audit hook records the files each
   test opens and the directories it lists inside the repository.

3. Subprocesses. Code run in a child process is not attributed to the test.
   Tests spawning a Python/elspais process are recorded so the selector can
   treat them as opaque.

Each process (xdist controller or worker) writes one shard,
``tia-shard-<worker>.json``. ``python -m tools.tia baseline build`` merges the
shards with the run's ``.coverage`` into a baseline.

The plugin must never break the run it observes: every hook body is guarded
and an internal failure is recorded in the shard, which then makes the
baseline invalid rather than silently incomplete.
"""

from __future__ import annotations

import inspect
import json
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path

import pytest

ENV_DIR = "TIA_RECORD_DIR"

#: Audit events the hook reacts to; everything else returns at the first line.
_EVENTS = frozenset({"open", "os.listdir", "os.scandir", "subprocess.Popen", "os.posix_spawn"})

#: Repository-relative path prefixes whose reads are never evidence of a data
#: dependency (tool caches, virtualenvs, our own output).
_EXCLUDED_PARTS = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        ".results",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        "htmlcov",
        ".tox",
    }
)

_IMPORT_FRAMES = (
    "<frozen importlib._bootstrap_external>",
    "<frozen importlib._bootstrap>",
    "<frozen zipimport>",
)


def _git(root: str, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, check=True
    ).stdout


def git_identity(root: str) -> dict:
    """The tree the run is testing: the index tree plus the worktree overlay.

    ``tree`` is ``git write-tree`` (the index). Files whose worktree content
    differs from it -- unstaged edits, deletions, untracked files -- are
    ``dirty``; each one's content is stored as a blob (``hash-object -w``) so
    the selector can later diff against exactly what was tested.
    """
    ident: dict = {"commit": None, "tree": None, "dirty": {}, "error": None}
    try:
        ident["commit"] = _git(root, "rev-parse", "HEAD").strip()
        ident["tree"] = _git(root, "write-tree").strip()
        changed = _git(root, "diff", "--name-only", "--no-renames", "-z").split("\0")
        untracked = _git(root, "ls-files", "--others", "--exclude-standard", "-z").split("\0")
        # An embedded repository (a nested clone, an agent's git worktree) is
        # listed as one "dir/" entry that git never descends into: it is not
        # part of this tree, so it is not part of what the run tested.
        for rel in sorted({p for p in changed + untracked if p and not p.endswith("/")}):
            full = os.path.join(root, rel)
            if os.path.islink(full):
                from .gitio import hash_symlink

                ident["dirty"][rel] = hash_symlink(root, rel, write=True)
            elif os.path.isfile(full):
                ident["dirty"][rel] = _git(
                    root, "hash-object", "-w", "--no-filters", "--", rel
                ).strip()
            else:
                ident["dirty"][rel] = None  # deleted in the worktree
    except Exception as exc:  # noqa: BLE001 - recorded, makes the baseline invalid
        ident["error"] = f"{type(exc).__name__}: {exc}"
    return ident


# Installers, which a venv and a container image each seed with their own
# releases. requirements/dev.lock pins none of them, and no test imports them.
INSTALLER_DISTRIBUTIONS = frozenset({"pip", "setuptools", "wheel"})


def environment_fingerprint() -> dict:
    """The interpreter and the installed distributions a test run could depend on.

    A baseline is accepted only by an environment with the same fingerprint.
    Python is compared as major.minor, because a CI image and a developer's
    venv carry different patch releases of one minor version. Every installed
    distribution is compared at its exact version, except this project and
    INSTALLER_DISTRIBUTIONS. `make setup` and CI both install under
    requirements/dev.lock, so on one minor version their fingerprints match.
    """
    from importlib import metadata

    excluded = INSTALLER_DISTRIBUTIONS | {"elspais", ""}
    dists = sorted(
        {
            f"{(d.metadata['Name'] or '').lower()}=={d.version}"
            for d in metadata.distributions()
            if (d.metadata["Name"] or "").lower() not in excluded
        }
    )
    return {
        "python": ".".join(str(v) for v in sys.version_info[:2]),
        "implementation": sys.implementation.name,
        "platform": sys.platform,
        "distributions": dists,
    }


class Recorder:
    def __init__(self, config: pytest.Config, out_dir: str) -> None:
        self.config = config
        self.out_dir = out_dir
        self.root = os.path.realpath(str(config.rootpath))
        wi = getattr(config, "workerinput", None)
        self.worker = wi["workerid"] if wi else "main"
        self.is_controller = wi is None
        self.current: str | None = None  # "<nodeid>|<phase>" or "collect:<nodeid>"
        self.phase_test: str | None = None
        self.tests: dict[str, dict] = {}
        self.attrib: dict[str, dict[str, set]] = {}  # bucket -> {"reads","lists","spawns"}
        self.items: list[str] = []
        self.errors: list[str] = []
        self.started = time.time()
        self.identity_start = git_identity(self.root) if self.is_controller else None
        self._in_hook = False
        self.loop_started = False
        self.fixture_stack: list[str] = []
        self.repo_fixtures: set[str] = set()
        self.external_fixtures: set[str] = set()
        sys.addaudithook(self._audit)

    # -- attribution ---------------------------------------------------
    def _bucket(self) -> dict[str, set] | None:
        key = self.current
        if self.fixture_stack:
            key = "fixture:" + self.fixture_stack[-1]
        elif key is None:
            # Before the test loop: configuration and plugin start-up, which
            # the selector treats as global. After it starts, a read outside
            # any test or collection is reporting (coverage reads every source
            # file to write its report), and is evidence of nothing.
            if self.loop_started:
                return None
            key = "session"
        b = self.attrib.get(key)
        if b is None:
            b = self.attrib[key] = {
                "reads": set(),
                "lists": set(),
                "spawns": set(),
                "writes": set(),
            }
        return b

    def _rel(self, path) -> str | None:
        if isinstance(path, int) or path is None:
            return None
        try:
            p = os.fsdecode(path)
        except Exception:  # noqa: BLE001
            return None
        if not os.path.isabs(p):
            try:
                p = os.path.join(os.getcwd(), p)
            except OSError:
                return None
        p = os.path.normpath(p)
        root = self.root
        if p != root and not p.startswith(root + os.sep):
            real = os.path.realpath(p)
            if real != root and not real.startswith(root + os.sep):
                return None
            p = real
        rel = os.path.relpath(p, root)
        parts = rel.split(os.sep)
        if any(part in _EXCLUDED_PARTS for part in parts) or parts[0].startswith(".coverage"):
            return None
        return "." if rel == "." else rel.replace(os.sep, "/")

    @staticmethod
    def _from_import_machinery() -> bool:
        f = sys._getframe(2)
        for _ in range(6):
            if f is None:
                return False
            if f.f_code.co_filename in _IMPORT_FRAMES:
                return True
            f = f.f_back
        return False

    def _audit(self, event: str, args: tuple) -> None:
        if event not in _EVENTS or self._in_hook:
            return
        self._in_hook = True
        try:
            if event == "open":
                rel = self._rel(args[0])
                if rel is None or self._from_import_machinery():
                    return
                mode = args[1] if len(args) > 1 else "r"
                flags = args[2] if len(args) > 2 else 0
                writing = (isinstance(mode, str) and any(c in mode for c in "wax+")) or (
                    mode is None and isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR)
                )
                bucket = self._bucket()
                if bucket is not None:
                    bucket["writes" if writing else "reads"].add(rel)
            elif event in ("os.listdir", "os.scandir"):
                target = args[0] if args else None
                rel = self._rel("." if target is None else target)
                if rel is None or self._from_import_machinery():
                    return
                bucket = self._bucket()
                if bucket is not None:
                    bucket["lists"].add(rel)
            else:  # subprocess.Popen / os.posix_spawn
                argv = args[1] if len(args) > 1 else None
                if isinstance(argv, (str, bytes)):
                    argv = [os.fsdecode(argv).split()[0]] if argv.strip() else []
                prog = os.fsdecode(args[0]) if args and args[0] else None
                if argv:
                    prog = os.fsdecode(argv[0]) if not prog else prog
                    tail = [os.fsdecode(a) for a in list(argv)[1:4] if isinstance(a, (str, bytes))]
                else:
                    tail = []
                if prog:
                    name = os.path.basename(prog)
                    if name.startswith("python") and len(tail) >= 2 and tail[0] == "-m":
                        name = f"{name} -m {tail[1]}"
                    bucket = self._bucket()
                    if bucket is not None:
                        bucket["spawns"].add(name)
        except Exception:  # noqa: BLE001
            if len(self.errors) < 20:
                self.errors.append("audit: " + traceback.format_exc(limit=3))
        finally:
            self._in_hook = False

    # -- pytest hooks ----------------------------------------------------
    @pytest.hookimpl(wrapper=True, tryfirst=True)
    def pytest_runtestloop(self, session):
        self.loop_started = True
        return (yield)

    @pytest.hookimpl(wrapper=True)
    def pytest_make_collect_report(self, collector):
        prev = self.current
        self.current = f"collect:{collector.nodeid}"
        try:
            return (yield)
        finally:
            self.current = prev

    @pytest.hookimpl(trylast=True)
    def pytest_collection_finish(self, session):
        self.current = None
        try:
            self.items = [i.nodeid for i in session.items]
            for item in session.items:
                self.tests.setdefault(item.nodeid, self._new_test(item))
        except Exception:  # noqa: BLE001
            self.errors.append("collection: " + traceback.format_exc(limit=3))

    def _new_test(self, item) -> dict:
        shared = []
        try:
            n2d = item._fixtureinfo.name2fixturedefs
            for name in item.fixturenames:
                defs = n2d.get(name)
                if defs and defs[-1].scope != "function":
                    shared.append(_fixture_key(defs[-1]))
        except Exception:  # noqa: BLE001
            self.errors.append("fixtures: " + traceback.format_exc(limit=3))
        return {
            "file": str(item.path.relative_to(self.config.rootpath)).replace(os.sep, "/")
            if item.path.is_relative_to(self.config.rootpath)
            else str(item.path),
            "cls": item.cls.__qualname__ if getattr(item, "cls", None) else None,
            "shared_fixtures": sorted(set(shared)),
            "setup_executed": [],
            "teardown_finalized": [],
            "outcome": None,
            "duration": 0.0,
        }

    def _phase(self, item, phase: str):
        self.current = f"{item.nodeid}|{phase}"
        self.phase_test = item.nodeid
        if item.nodeid not in self.tests:
            self.tests[item.nodeid] = self._new_test(item)

    @pytest.hookimpl(wrapper=True, tryfirst=True)
    def pytest_runtest_setup(self, item):
        self._phase(item, "setup")
        return (yield)

    @pytest.hookimpl(wrapper=True, tryfirst=True)
    def pytest_runtest_call(self, item):
        self._phase(item, "run")
        return (yield)

    @pytest.hookimpl(wrapper=True, tryfirst=True)
    def pytest_runtest_teardown(self, item, nextitem):
        self._phase(item, "teardown")
        try:
            return (yield)
        finally:
            self.current = None

    @pytest.hookimpl(wrapper=True)
    def pytest_fixture_setup(self, fixturedef, request):
        try:
            if (
                fixturedef.scope != "function"
                and self.phase_test
                and self.current
                and self.current.endswith("|setup")
            ):
                lst = self.tests[self.phase_test]["setup_executed"]
                self._repo_fixture(fixturedef)
                key = _fixture_key(fixturedef)
                if key not in lst:
                    lst.append(key)
        except Exception:  # noqa: BLE001
            self.errors.append("fixture_setup: " + traceback.format_exc(limit=3))
        # While a shared fixture defined in this repository runs, what it reads,
        # lists and spawns is its own, not the test's that happened to set it up
        # first: the selector then selects exactly that fixture's users.
        pushed = fixturedef.scope != "function" and self._repo_fixture(fixturedef)
        if pushed:
            self.fixture_stack.append(_fixture_key(fixturedef))
        try:
            return (yield)
        finally:
            if pushed:
                self.fixture_stack.pop()

    def _repo_fixture(self, fixturedef) -> bool:
        """Is this fixture defined in the repository (not pytest or a plugin)?

        Decided by where its function is defined: a `baseid` cannot tell, as
        a root-level conftest.py and a plugin both have an empty one.
        """
        key = _fixture_key(fixturedef)
        if key in self.repo_fixtures:
            return True
        if key in self.external_fixtures:
            return False
        func = inspect.unwrap(getattr(fixturedef, "func", None) or (lambda: None))
        code = getattr(func, "__code__", None)
        rel = self._rel(code.co_filename) if code is not None else None
        repo = rel is not None and rel != "."
        (self.repo_fixtures if repo else self.external_fixtures).add(key)
        return repo

    def pytest_fixture_post_finalizer(self, fixturedef, request):
        try:
            if (
                fixturedef.scope != "function"
                and self.phase_test
                and self.current
                and self.current.endswith("|teardown")
                and getattr(fixturedef, "cached_result", 1)
            ):
                lst = self.tests[self.phase_test]["teardown_finalized"]
                key = _fixture_key(fixturedef)
                if key not in lst:
                    lst.append(key)
        except Exception:  # noqa: BLE001
            self.errors.append("fixture_finalize: " + traceback.format_exc(limit=3))

    def pytest_runtest_logreport(self, report):
        try:
            t = self.tests.get(report.nodeid)
            if t is None:
                return
            t["duration"] += float(getattr(report, "duration", 0.0) or 0.0)
            if hasattr(report, "wasxfail"):
                out = "xfailed" if report.skipped else "xpassed"
            else:
                out = report.outcome
            t.setdefault("phases", {})[report.when] = out
            t["outcome"] = final_outcome(t["phases"])
        except Exception:  # noqa: BLE001
            self.errors.append("logreport: " + traceback.format_exc(limit=3))

    @pytest.hookimpl(trylast=True)
    def pytest_sessionfinish(self, session, exitstatus):
        self.current = None
        try:
            self._write(exitstatus)
        except Exception:  # noqa: BLE001
            sys.stderr.write("tia recorder: could not write shard:\n" + traceback.format_exc())

    def _write(self, exitstatus) -> None:
        os.makedirs(self.out_dir, exist_ok=True)
        shard = {
            "worker": self.worker,
            "controller": self.is_controller,
            "pid": os.getpid(),
            "exitstatus": int(exitstatus),
            "started": self.started,
            "finished": time.time(),
            "root": self.root,
            "argv": list(self.config.invocation_params.args),
            "markexpr": self.config.getoption("markexpr", ""),
            "items": self.items,
            "tests": self.tests,
            "attribution": {
                k: {kk: sorted(vv) for kk, vv in v.items() if vv} for k, v in self.attrib.items()
            },
            "errors": self.errors,
            "external_fixtures": sorted(self.external_fixtures),
        }
        if self.is_controller:
            shard["identity_start"] = self.identity_start
            shard["identity_end"] = git_identity(self.root)
            shard["environment"] = environment_fingerprint()
        path = os.path.join(self.out_dir, f"tia-shard-{self.worker}.json")
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(shard, fh, sort_keys=True)
        os.replace(tmp, path)


def final_outcome(phases: dict) -> str:
    """One outcome from the per-phase outcomes pytest reported."""
    if phases.get("call") == "failed":
        return "failed"
    if "failed" in phases.values():
        return "error"
    if phases.get("call") in ("xfailed", "xpassed"):
        return phases["call"]
    if "skipped" in phases.values():
        return "skipped"
    if phases.get("call") == "passed":
        return "passed"
    return "not-run"


def _fixture_key(fixturedef) -> str:
    return f"{fixturedef.scope}:{fixturedef.baseid}::{fixturedef.argname}"


def pytest_configure(config: pytest.Config) -> None:
    out = os.environ.get(ENV_DIR)
    if not out:
        return
    config.pluginmanager.register(Recorder(config, str(Path(out).resolve())), "tia-recorder")
