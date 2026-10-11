"""Turn the change since a baseline into a set of tests to run.

The engine is deterministic: the same baseline, rule file and working tree
always produce the same selection, in the same order, with the same reasons.
Every decision that widens the selection to the full suite is recorded as a
*fallback* with a kind and a human-readable detail.

Selection, per changed file (first matching rule in config.toml decides,
otherwise the built-in classification):

  test module (new or modified)     run all of its tests
  conftest.py / __init__.py         every test under that directory
    under a test root
  other Python under a test root    test modules importing it (transitively);
    (helpers)                       unknown importers -> full suite
  production Python                 AST impact (pyimpact) mapped through
                                    baseline coverage; see pyimpact's doc
  anything else (data)              tests recorded reading the file, or
                                    listing its directory (or an ancestor,
                                    for a new file); package data under a
                                    production root also selects tests
                                    covering modules naming it

and independent of the change:

  tests that did not pass in the baseline (their coverage is partial)
  tests that spawn an opaque subprocess, whenever a non-test file changed
  the configured always-run set

Coverage hits in a test's setup/teardown phase are widened to every test
sharing the shared-scope fixtures that phase executed, since only the first
user of a session/module fixture records its lines.
"""

from __future__ import annotations

import ast
import os
import time
from dataclasses import dataclass, field

from . import SCHEMA_VERSION
from .baseline import Baseline, BaselineError, load_baseline
from .config import Config, loads_toml
from .gitio import BaselineTree, FileChange, changed_files, read_current
from .pyimpact import (
    FILE,
    FUNCTION,
    analyze_python_change,
    build_import_graph,
    module_name,
    string_literals,
)


@dataclass
class Fallback:
    kind: str
    detail: str
    path: str | None = None

    def as_dict(self) -> dict:
        d = {"kind": self.kind, "detail": self.detail}
        if self.path:
            d["path"] = self.path
        return d


@dataclass
class ChangedFileReport:
    path: str
    status: str
    category: str
    regions: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    tests_selected: int = 0

    def as_dict(self) -> dict:
        return {
            "path": self.path,
            "status": self.status,
            "category": self.category,
            "regions": self.regions,
            "notes": self.notes,
            "tests_selected": self.tests_selected,
        }


@dataclass
class Selection:
    mode: str  # "test-impact" | "full"
    baseline: dict
    total_tests: int
    tests: dict[str, list[str]]  # baseline nodeid -> reasons
    run_files: list[str]  # test files handed to pytest (file granularity)
    run_nodeids: list[str]  # node ids handed to pytest (test granularity)
    new_test_files: list[str]
    changed: list[ChangedFileReport]
    fallbacks: list[Fallback]
    warnings: list[str]
    granularity: str
    elapsed_selection: float = 0.0
    whole_test_files: list[str] = field(default_factory=list)

    @property
    def selected_count(self) -> int:
        return self.total_tests if self.mode == "full" else len(self.tests)

    def manifest(self) -> dict:
        full = self.mode == "full"
        return {
            "schema": SCHEMA_VERSION,
            "suite": "unit",
            "selection_mode": self.mode,
            "baseline": self.baseline,
            "change": {
                "against": "working tree (tracked + untracked) vs baseline tree",
                "files": [c.as_dict() for c in self.changed],
            },
            "granularity": self.granularity,
            "total_tests": self.total_tests,
            "selected_tests": self.selected_count,
            "skipped_tests": 0 if full else self.total_tests - len(self.tests),
            "new_test_files": self.new_test_files,
            "fallbacks": [f.as_dict() for f in self.fallbacks],
            "warnings": self.warnings,
            "selection_seconds": round(self.elapsed_selection, 3),
            "pytest_targets": ["<full suite>"]
            if full
            else (self.run_files if self.granularity == "file" else self.run_nodeids),
            "tests": [{"test": n, "reasons": r} for n, r in sorted(self.tests.items())]
            if not full
            else [],
        }


class _Collector:
    """Accumulates tests with their reasons; reason lists stay bounded."""

    MAX_REASONS = 6

    def __init__(self) -> None:
        self.tests: dict[str, list[str]] = {}

    def add(self, nodeid: str, reason: str) -> bool:
        lst = self.tests.setdefault(nodeid, [])
        if reason in lst:
            return False
        if len(lst) < self.MAX_REASONS:
            lst.append(reason)
        elif len(lst) == self.MAX_REASONS:
            lst.append("... (more reasons omitted)")
        return True


class Selector:
    def __init__(self, root: str, config: Config, baseline: Baseline):
        self.root = root
        self.cfg = config
        self.base = baseline
        self.tree = BaselineTree(
            root, baseline.identity["tree"], baseline.identity.get("dirty") or {}
        )
        self.tests = baseline.tests
        self.cov = baseline.coverage
        self.out = _Collector()
        self.fallbacks: list[Fallback] = []
        self.reports: list[ChangedFileReport] = []
        self.new_test_files: set[str] = set()
        self.whole_test_files: set[str] = set()  # new or modified: every test runs
        self._import_graph = None
        self._referenced: set[str] | None = None
        self._fixture_users: dict[str, set[str]] | None = None
        self._by_file: dict[str, list[str]] | None = None
        # Fixtures defined by pytest or a plugin (decided by where the fixture
        # function lives). Their setup runs no repository code, so a hit in
        # the setup phase that executed one says nothing about its other
        # users: widening through `tmp_path_factory`, set up by the first
        # `tmp_path` user in each worker, would select nearly every test.
        self.external_fixtures = set(baseline.manifest.get("external_fixtures") or ())

    # -- indexes -----------------------------------------------------------
    @property
    def by_file(self) -> dict[str, list[str]]:
        if self._by_file is None:
            idx: dict[str, list[str]] = {}
            for n, t in self.tests.items():
                idx.setdefault(t["file"], []).append(n)
            self._by_file = idx
        return self._by_file

    @property
    def fixture_users(self) -> dict[str, set[str]]:
        if self._fixture_users is None:
            idx: dict[str, set[str]] = {}
            for n, t in self.tests.items():
                for k in t.get("shared_fixtures") or ():
                    idx.setdefault(k, set()).add(n)
            self._fixture_users = idx
        return self._fixture_users

    def import_graph(self):
        if self._import_graph is None:
            files = []
            for root in self.cfg.import_roots:
                base = os.path.join(self.root, root) if root not in ("", ".") else self.root
                for dp, dns, fns in os.walk(base):
                    dns[:] = [
                        d
                        for d in dns
                        if not d.startswith(".")
                        and d not in ("__pycache__", "node_modules", "build", "dist")
                        and not d.endswith(".egg-info")
                    ]
                    for fn in fns:
                        if fn.endswith(".py"):
                            files.append(
                                os.path.relpath(os.path.join(dp, fn), self.root).replace(
                                    os.sep, "/"
                                )
                            )
            # a deleted module still has importers (that will now break)
            files += [p for p in getattr(self, "_deleted_py", ()) if p not in files]
            self._import_graph = build_import_graph(
                self.root, sorted(set(files)), self.cfg.import_roots
            )
        return self._import_graph

    def referenced_names(self) -> set[str]:
        """String literals in production code (names that may be looked up)."""
        if self._referenced is None:
            names: set[str] = set()
            g = self.import_graph()
            for path in g.module_of:
                if self.cfg.is_production(path):
                    try:
                        with open(os.path.join(self.root, path), "rb") as fh:
                            names |= string_literals(ast.parse(fh.read(), path))
                    except (OSError, SyntaxError, ValueError):
                        pass
            self._referenced = {n for n in names if n.isidentifier()}
        return self._referenced

    # -- primitives ----------------------------------------------------------
    def _full(self, kind: str, detail: str, path: str | None = None) -> None:
        self.fallbacks.append(Fallback(kind, detail, path))

    def _select_hits(self, hits: dict[str, set[str]], reason: str) -> int:
        """Select tests by coverage/read hits, widening setup/teardown hits."""
        n = 0
        for nodeid in sorted(hits):
            phases = hits[nodeid]
            if nodeid not in self.tests:
                continue  # a context for a test no longer in the inventory
            n += self.out.add(nodeid, reason)
            t = self.tests[nodeid]
            shared = set()
            if "setup" in phases:
                shared |= set(t.get("setup_executed") or ())
            if "teardown" in phases:
                shared |= set(t.get("teardown_finalized") or ())
            for key in sorted(shared):
                if key in self.external_fixtures:
                    continue
                fx = key.split("::")[-1]
                for user in sorted(self.fixture_users.get(key, ())):
                    n += self.out.add(
                        user,
                        f"uses shared fixture '{fx}', whose setup ran code "
                        f"affected by the change ({reason})",
                    )
        return n

    def _select_reads(self, buckets, reason: str) -> int:
        """Select by recorded reads/listings.

        A bucket is `<nodeid>|<phase>` (the test's own read) or
        `fixture:<key>` (read while that shared fixture was being set up: its
        users are selected). A setup-phase read outside any shared fixture was
        made by a function-scoped fixture and concerns that test alone; a
        teardown-phase read may come from a shared fixture's finalizer, which
        no hook brackets, so it is widened like a teardown coverage hit.
        """
        n = 0
        hits: dict[str, set[str]] = {}
        for b in sorted(set(buckets)):
            if b.startswith("fixture:"):
                key = b[len("fixture:") :]
                fx = key.split("::")[-1]
                for user in sorted(self.fixture_users.get(key, ())):
                    n += self.out.add(user, f"uses shared fixture '{fx}', whose setup {reason}")
                continue
            nodeid, phase = b.rsplit("|", 1)
            hits.setdefault(nodeid, set()).add("teardown" if phase == "teardown" else "run")
        return n + self._select_hits(hits, reason)

    def _select_test_file(self, path: str, reason: str) -> int:
        self.whole_test_files.add(path)
        n = 0
        for nodeid in self.by_file.get(path, ()):
            n += self.out.add(nodeid, reason)
        if path not in self.by_file:
            self.new_test_files.add(path)
        return n

    def _tests_under(self, directory: str) -> list[str]:
        prefix = "" if directory in ("", ".") else directory.rstrip("/") + "/"
        return [n for n, t in self.tests.items() if t["file"].startswith(prefix)]

    # -- per-category handlers ---------------------------------------------
    def handle_data(self, ch: FileChange, rep: ChangedFileReport) -> None:
        reads = self.base.manifest["data_reads"]
        lists = self.base.manifest["dir_lists"]
        coll = self.base.manifest.get("collection_reads", {})
        if ch.path in self.base.manifest.get("session_reads", []):
            self._full(
                "session-read", "read by pytest before any test ran (configuration)", ch.path
            )
            return
        buckets = list(reads.get(ch.path, ()))
        # A new file (or a deleted one) changes the listing of its directory;
        # a new directory, the listing of its nearest listed ancestor.
        d = os.path.dirname(ch.path) or "."
        while True:
            if d in lists:
                buckets += lists[d]
                break
            if ch.status != "added" or d == ".":
                break
            d = os.path.dirname(d) or "."
        n = self._select_reads(buckets, f"read {ch.path} (or listed its directory) in the baseline")
        for collector in coll.get(ch.path, ()):
            for nodeid in self._tests_under_nodeid(collector):
                n += self.out.add(
                    nodeid, f"{ch.path} is read while collecting {collector or 'the suite'}"
                )
        if self.cfg.is_production(ch.path):
            n += self._package_data(ch, rep)
            if n == 0:
                self._full(
                    "package-data-unknown",
                    "package data no test or module is known to read; impact cannot be determined",
                    ch.path,
                )
        if n == 0:
            rep.notes.append("no test read this file or listed its directory in the baseline")
        rep.tests_selected += n

    def _tests_under_nodeid(self, collector: str) -> list[str]:
        if collector in ("", "."):
            return list(self.tests)
        return [
            n
            for n in self.tests
            if n == collector or n.startswith(collector + "/") or n.startswith(collector + "::")
        ]

    def _package_data(self, ch: FileChange, rep: ChangedFileReport) -> int:
        """Tests covering production modules whose string literals name the
        file (or its directory): loaders that cache, or read in a child."""
        name = os.path.basename(ch.path)
        parent = os.path.basename(os.path.dirname(ch.path))
        n = 0
        g = self.import_graph()
        for path in sorted(g.module_of):
            if not self.cfg.is_production(path):
                continue
            try:
                with open(os.path.join(self.root, path), "rb") as fh:
                    lits = string_literals(ast.parse(fh.read(), path))
            except (OSError, SyntaxError, ValueError):
                continue
            if any(name in s or (parent and s.rstrip("/").endswith(parent)) for s in lits):
                rep.regions.append(f"loaded by {path}")
                n += self._select_hits(self.cov.hits(path), f"covers {path}, which loads {ch.path}")
        return n

    def handle_test_module(self, ch: FileChange, rep: ChangedFileReport) -> None:
        if ch.status == "deleted":
            rep.notes.append("deleted test module; nothing to run")
            return
        kind = "new test" if ch.path not in self.by_file else "modified test"
        rep.tests_selected += self._select_test_file(ch.path, kind)
        # a test module can be imported by others (shared helpers in a test file)
        self._importers_of_test_support(ch, rep, quiet=True)

    def handle_test_package_file(self, ch: FileChange, rep: ChangedFileReport) -> None:
        d = os.path.dirname(ch.path)
        tests = self._tests_under(d)
        n = 0
        for nodeid in tests:
            n += self.out.add(nodeid, f"{ch.path} configures every test under {d}/")
        rep.regions.append(f"directory subtree {d}/")
        rep.tests_selected += n
        # tests new under that directory are found by the pytest run itself
        if ch.status == "added":
            self._full(
                "new-test-package",
                f"new {os.path.basename(ch.path)} changes how {d}/ is collected",
                ch.path,
            )

    def _importers_of_test_support(self, ch, rep, quiet=False) -> int:
        g = self.import_graph()
        mod = module_name(ch.path, self.cfg.import_roots)
        if mod is None:
            return 0
        closure = g.reverse_closure({mod}) - {mod}
        n = 0
        for m in sorted(closure):
            p = g.path_of[m]
            if self.cfg.is_test_module(p):
                n += self._select_test_file(p, f"imports {ch.path}")
            elif os.path.basename(p) in ("conftest.py", "__init__.py") and self.cfg.under(
                p, self.cfg.test_roots
            ):
                d = os.path.dirname(p)
                for nodeid in self._tests_under(d):
                    n += self.out.add(nodeid, f"{p} (configuring {d}/) imports {ch.path}")
        rep.tests_selected += n
        return n

    def handle_test_support(self, ch: FileChange, rep: ChangedFileReport) -> None:
        n = self._importers_of_test_support(ch, rep)
        n += self._select_reads(
            self.base.manifest["data_reads"].get(ch.path, ()), f"read {ch.path}"
        )
        rep.tests_selected += n
        if n == 0 and ch.status != "added":
            self._full(
                "test-support-unknown",
                "no test module is known to import this helper (it may be loaded dynamically)",
                ch.path,
            )

    def handle_production_python(self, ch: FileChange, rep: ChangedFileReport) -> None:
        old = self.tree.read(ch.path)
        new = read_current(self.root, ch.path)
        analysis = analyze_python_change(
            ch.path,
            old,
            new,
            memoizing=set(self.cfg.memoizing_decorators),
            referenced_names=self.referenced_names(),
        )
        for o1, o2, n1, n2 in analysis.hunks:
            if o2 >= o1:
                rep.notes.append(f"hunk {ch.path}:{o1}-{o2} (baseline) -> {n1}-{max(n1, n2)}")
            else:
                rep.notes.append(f"hunk insert after {ch.path}:{o1 - 1} (baseline) -> {n1}-{n2}")
        n = 0
        escalate_file = False
        escalate_module = False
        for imp in analysis.impacts:
            if imp.scope == FUNCTION:
                lo, hi = imp.lines
                rep.regions.append(f"{ch.path}:{lo}-{hi} {imp.detail}")
                hits = self.cov.hits(ch.path, lo, hi)
                if hits:
                    n += self._select_hits(
                        hits, f"covers changed region {ch.path}:{lo}-{hi} ({imp.unit})"
                    )
                else:
                    rep.notes.append(
                        f"{imp.unit}: no baseline test executed it; widened to the file"
                    )
                    escalate_file = True
            elif imp.scope == FILE:
                rep.regions.append(f"{ch.path} (whole file: {imp.detail})")
                escalate_file = True
            else:
                rep.regions.append(f"{ch.path} and its importers ({imp.detail})")
                escalate_module = True
        if escalate_file and not escalate_module:
            if ch.status == "added":
                n += self._new_module(ch, rep)
            else:
                hits = self.cov.hits(ch.path)
                if hits:
                    n += self._select_hits(hits, f"covers {ch.path} (file-level change)")
                else:
                    rep.notes.append(
                        "no baseline test executed this file; widened to its importers"
                    )
                    escalate_module = True
        if escalate_module:
            n += self._module_global(ch, rep)
        # tests that read the source as text
        n += self._select_reads(
            self.base.manifest["data_reads"].get(ch.path, ()), f"read {ch.path} as data"
        )
        rep.tests_selected += n

    def _new_module(self, ch: FileChange, rep: ChangedFileReport) -> int:
        """A module the baseline never saw. Existing tests can reach it only
        through changed code that imports it (selected on its own account) or
        by discovering it in its directory (recorded listings)."""
        lists = self.base.manifest["dir_lists"]
        d = os.path.dirname(ch.path) or "."
        while d not in lists and d != ".":
            d = os.path.dirname(d) or "."  # a new directory: its parent's listing changes
        n = self._select_reads(
            lists.get(d, ()), f"listed {d}/ (may discover the new module {ch.path})"
        )
        g = self.import_graph()
        mod = module_name(ch.path, self.cfg.import_roots)
        importers = sorted(g.importers.get(mod, ())) if mod else []
        unchanged_importers = [m for m in importers if g.path_of[m] not in self._changed_paths]
        if unchanged_importers:
            rep.notes.append("imported by unchanged modules: " + ", ".join(unchanged_importers[:5]))
            n += self._module_global(ch, rep, seed={mod})
        else:
            rep.notes.append(
                "new module: reached only through changed code (selected on its own "
                "account) or directory discovery"
            )
        return n

    def _module_global(self, ch: FileChange, rep: ChangedFileReport, seed=None) -> int:
        g = self.import_graph()
        mod = module_name(ch.path, self.cfg.import_roots)
        if mod is None:
            self._full(
                "unresolvable-module", "cannot name the module to find its importers", ch.path
            )
            return 0
        closure = g.reverse_closure(seed or {mod})
        n = 0
        prod = sorted(m for m in closure if self.cfg.is_production(g.path_of.get(m, "")))
        test_side = sorted(m for m in closure if not self.cfg.is_production(g.path_of.get(m, "")))
        rep.notes.append(
            f"module scope: {len(prod)} production module(s), {len(test_side)} test-side "
            "module(s) import it (transitively)"
        )
        for m in prod:
            p = g.path_of[m]
            n += self._select_hits(
                self.cov.hits(p),
                f"covers {p}, which imports {ch.path}"
                if p != ch.path
                else f"covers {ch.path} (module-level change)",
            )
        for m in test_side:
            p = g.path_of[m]
            if self.cfg.is_test_module(p):
                n += self._select_test_file(p, f"imports {ch.path} (transitively)")
            elif os.path.basename(p) in ("conftest.py", "__init__.py") and self.cfg.under(
                p, self.cfg.test_roots
            ):
                if m in g.reverse_closure(seed or {mod}, toplevel_only=True):
                    d = os.path.dirname(p)
                    for nodeid in self._tests_under(d):
                        n += self.out.add(nodeid, f"{p} imports {ch.path} at import time")
        if n == 0 and ch.status != "added":
            self._full(
                "unmeasured-module",
                "no baseline test executed or imported this module "
                "or any importer; impact cannot be determined",
                ch.path,
            )
        return n

    # -- driver --------------------------------------------------------------
    def categorize(self, path: str) -> tuple[str, object]:
        rule = self.cfg.rule_for(path)
        if rule is not None:
            return rule.action, rule
        if self.cfg.under(path, self.cfg.test_roots) and path.endswith(".py"):
            name = os.path.basename(path)
            if name in ("conftest.py", "__init__.py"):
                return "test-package", None
            if self.cfg.is_test_module(path):
                return "test", None
            return "test-support", None
        if path.endswith(".py") and self.cfg.is_production(path):
            return "production-python", None
        return "data", None

    def run(self, changes: list[FileChange]) -> None:
        self._changed_paths = {c.path for c in changes}
        self._deleted_py = [
            c.path for c in changes if c.status == "deleted" and c.path.endswith(".py")
        ]
        any_non_test = False
        for ch in changes:
            cat, rule = self.categorize(ch.path)
            rep = ChangedFileReport(ch.path, ch.status, cat)
            self.reports.append(rep)
            if cat not in ("test", "ignore"):
                any_non_test = True
            if cat == "full":
                self._full("broad-impact-file", rule.reason or "matched a full-suite rule", ch.path)
            elif cat == "ignore":
                rep.notes.append(rule.reason or "ignored by rule")
            elif cat == "manifest":
                self._manifest(ch, rep, rule)
            elif cat == "test":
                self.handle_test_module(ch, rep)
            elif cat == "test-package":
                self.handle_test_package_file(ch, rep)
            elif cat == "test-support":
                self.handle_test_support(ch, rep)
            elif cat == "production-python":
                self.handle_production_python(ch, rep)
            else:
                self.handle_data(ch, rep)

        if changes:
            for nodeid, t in self.tests.items():
                if t.get("outcome") not in ("passed",):
                    self.out.add(
                        nodeid,
                        f"baseline outcome was '{t.get('outcome')}' "
                        "(coverage incomplete or skip condition may change)",
                    )
        if any_non_test:
            for nodeid, t in self.tests.items():
                opaque = [p for p in t.get("spawns") or () if self.cfg.program_is_opaque(p)]
                if opaque:
                    self.out.add(
                        nodeid,
                        f"spawns {opaque[0]}; code run in the child is not attributed to the test",
                    )
        for spec in self.cfg.always_run:
            for nodeid in self.tests:
                if (
                    nodeid == spec
                    or self.tests[nodeid]["file"] == spec
                    or nodeid.startswith(spec + "::")
                ):
                    self.out.add(nodeid, "configured always-run")

    def _manifest(self, ch: FileChange, rep: ChangedFileReport, rule) -> None:
        old, new = self.tree.read(ch.path), read_current(self.root, ch.path)
        if old is None or new is None:
            self._full("broad-impact-file", f"{rule.reason} (file added or removed)", ch.path)
            return
        try:
            a, b = loads_toml(old.decode()), loads_toml(new.decode())
        except Exception as exc:  # noqa: BLE001
            self._full("broad-impact-file", f"{rule.reason} (does not parse: {exc})", ch.path)
            return
        for key in rule.ignore_keys:
            for doc in (a, b):
                parts = key.split(".")
                cur = doc
                for p in parts[:-1]:
                    cur = cur.get(p, {}) if isinstance(cur, dict) else {}
                if isinstance(cur, dict):
                    cur.pop(parts[-1], None)
        if a != b:
            self._full("broad-impact-file", rule.reason, ch.path)
            return
        rep.notes.append("only " + ", ".join(rule.ignore_keys) + " changed; handled as data")
        rep.category = "manifest (ignored keys only)"
        # pytest reads this file at start-up; that read is configuration, not data
        reads = self.base.manifest["data_reads"].get(ch.path, ())
        rep.tests_selected += self._select_reads(reads, f"read {ch.path} in the baseline")


def baseline_summary(b: Baseline | None, path: str) -> dict:
    if b is None:
        return {"path": path, "usable": False}
    ident = b.identity
    return {
        "path": path,
        "usable": True,
        "commit": ident.get("commit"),
        "tree": ident.get("tree"),
        "dirty_files": sorted(ident.get("dirty") or {}),
        "created": b.manifest.get("created"),
        "environment_hash": b.manifest.get("environment_hash"),
        "tests": len(b.tests),
    }


def select(
    root: str,
    config: Config,
    baseline_path: str,
    *,
    force_full: str | None = None,
    current_env: dict | None = None,
    now: float | None = None,
) -> Selection:
    """The one entry point: never raises for an unusable baseline -- that is a
    full-suite fallback, recorded in the selection."""
    t0 = time.time()
    fallbacks: list[Fallback] = []
    warnings: list[str] = []
    base: Baseline | None = None
    if force_full:
        fallbacks.append(Fallback("forced-full", force_full))
    try:
        base = load_baseline(
            baseline_path,
            root,
            current_env=current_env,
            on_environment_change=config.on_environment_change,
            max_age_days=config.max_baseline_age_days,
            now=now,
        )
        warnings += base.warnings
    except BaselineError as exc:
        fallbacks.append(Fallback(exc.kind, exc.detail))

    if base is None:
        return Selection(
            "full",
            baseline_summary(None, baseline_path),
            0,
            {},
            [],
            [],
            [],
            [],
            fallbacks,
            warnings,
            config.granularity,
            time.time() - t0,
        )

    sel = Selector(root, config, base)
    try:
        changes = changed_files(sel.tree)
        sel.run(changes)
    except Exception as exc:  # noqa: BLE001 - the selector fails open, always
        import traceback

        sel.fallbacks.append(Fallback("selector-error", f"{type(exc).__name__}: {exc}"))
        warnings.append(traceback.format_exc(limit=5))
    fallbacks += sel.fallbacks

    tests = sel.out.tests
    # A test whose file no longer exists cannot be run (its deletion is the
    # change); handing its path to pytest would stop the run.
    selected_files = {base.tests[n]["file"] for n in tests}
    gone = sorted(f for f in selected_files if not os.path.isfile(os.path.join(root, f)))
    for n in [n for n in tests if base.tests[n]["file"] in gone]:
        del tests[n]
    if gone:
        warnings.append(
            f"{len(gone)} selected test file(s) no longer exist: " + ", ".join(gone[:5])
        )
    # granularity expansion
    if config.granularity == "file":
        files = sorted({base.tests[n]["file"] for n in tests} | sel.new_test_files)
        for f in files:
            for nodeid in sel.by_file.get(f, ()):
                if nodeid not in tests:
                    sel.out.add(nodeid, "same test file as a selected test (file granularity)")
        run_files, run_nodeids = files, []
    else:
        # whole classes, so incremental classes keep their steps together
        classes = {
            (base.tests[n]["file"], base.tests[n]["cls"]) for n in tests if base.tests[n]["cls"]
        }
        for n, t in base.tests.items():
            if (t["file"], t["cls"]) in classes and n not in tests:
                sel.out.add(n, "same test class as a selected test")
        run_nodeids = sorted(tests) + sorted(sel.new_test_files)
        run_files = sorted({base.tests[n]["file"] for n in tests} | sel.new_test_files)

    total = len(base.tests)
    mode = "test-impact"
    if fallbacks:
        mode = "full"
    elif total and len(tests) / total >= config.full_suite_threshold:
        fallbacks.append(
            Fallback(
                "selection-near-full",
                f"{len(tests)}/{total} tests selected (>= {config.full_suite_threshold:.0%}); "
                "running the full suite instead",
            )
        )
        mode = "full"
    for rep in sel.reports:
        rep.regions = sorted(set(rep.regions), key=rep.regions.index)
    whole = sorted(f for f in sel.whole_test_files if os.path.isfile(os.path.join(root, f)))
    return Selection(
        mode,
        baseline_summary(base, baseline_path),
        total,
        dict(sorted(tests.items())),
        run_files,
        run_nodeids,
        sorted(sel.new_test_files),
        sel.reports,
        fallbacks,
        warnings,
        config.granularity,
        time.time() - t0,
        whole,
    )
