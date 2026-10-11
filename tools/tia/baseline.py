"""The baseline artifact: what a full run of the suite recorded.

A baseline is a directory holding

    baseline.json   identity (tree + dirty overlay), environment, the test
                    inventory with outcomes, durations, shared-fixture use,
                    and the data-read / directory-listing / subprocess
                    attribution the recorder captured
    coverage.db     the run's coverage.py data file, copied verbatim; its
                    per-test contexts (`<nodeid>|setup|run|teardown`) are the
                    test -> production-line map

`build_baseline` makes one from a run directory; `load_baseline` reads one
back and refuses -- with a reason the selector reports as a fallback --
anything it cannot trust.
"""

from __future__ import annotations

import glob
import hashlib
import json
import os
import shutil
import time
from dataclasses import dataclass, field

from . import SCHEMA_VERSION
from .gitio import object_exists

BASELINE_JSON = "baseline.json"
COVERAGE_DB = "coverage.db"


class BaselineError(Exception):
    """The baseline cannot be used; ``kind`` names the fallback."""

    def __init__(self, kind: str, detail: str):
        super().__init__(f"{kind}: {detail}")
        self.kind = kind
        self.detail = detail


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def env_hash(env: dict) -> str:
    return hashlib.sha256(json.dumps(env, sort_keys=True).encode()).hexdigest()[:16]


def tool_hash(tool_dir: str | None = None) -> str:
    tool_dir = tool_dir or os.path.dirname(os.path.abspath(__file__))
    h = hashlib.sha256()
    for p in sorted(
        glob.glob(os.path.join(tool_dir, "*.py")) + [os.path.join(tool_dir, "config.toml")]
    ):
        if os.path.exists(p):
            h.update(os.path.basename(p).encode())
            with open(p, "rb") as fh:
                h.update(fh.read())
    return h.hexdigest()[:16]


# -- building ---------------------------------------------------------------


def build_baseline(run_dir: str, dest: str, coverage_file: str | None = None) -> dict:
    """Merge the recorder shards of one run with its coverage into `dest`."""
    shards = []
    for p in sorted(glob.glob(os.path.join(run_dir, "tia-shard-*.json"))):
        with open(p, encoding="utf-8") as fh:
            shards.append(json.load(fh))
    if not shards:
        raise BaselineError("baseline-missing", f"no recorder shards in {run_dir}")
    ctl = [s for s in shards if s.get("controller")]
    if len(ctl) != 1:
        raise BaselineError("baseline-malformed", f"{len(ctl)} controller shards in {run_dir}")
    ctl = ctl[0]
    coverage_file = coverage_file or os.path.join(run_dir, ".coverage")
    if not os.path.isfile(coverage_file):
        raise BaselineError("coverage-missing", f"no coverage data at {coverage_file}")

    tests: dict[str, dict] = {}
    data_reads: dict[str, set] = {}
    dir_lists: dict[str, set] = {}
    collection_reads: dict[str, set] = {}
    session_reads: set = set()
    spawns: dict[str, set] = {}
    errors: list[str] = []
    for s in shards:
        errors += [f"[{s['worker']}] {e}" for e in s.get("errors", [])]
        for nodeid, t in s["tests"].items():
            if t.get("outcome") in (None, "not-run") and nodeid in tests:
                continue  # collected by this worker, run by another
            if nodeid in tests and tests[nodeid].get("outcome") not in (None, "not-run"):
                if t.get("outcome") not in (None, "not-run"):
                    errors.append(f"test {nodeid} ran in two processes")
                continue
            tests[nodeid] = {
                k: t.get(k)
                for k in (
                    "file",
                    "cls",
                    "outcome",
                    "duration",
                    "shared_fixtures",
                    "setup_executed",
                    "teardown_finalized",
                )
            }
        for bucket, attrib in s.get("attribution", {}).items():
            reads = attrib.get("reads", [])
            lists = attrib.get("lists", [])
            if bucket == "session":
                session_reads.update(reads)
            elif bucket.startswith("collect:"):
                who = bucket[len("collect:") :]
                for r in reads:
                    collection_reads.setdefault(r, set()).add(who)
            else:
                for r in reads:
                    data_reads.setdefault(r, set()).add(bucket)
                for d in lists:
                    dir_lists.setdefault(d, set()).add(bucket)
                nodeid = bucket.rsplit("|", 1)[0]
                for prog in attrib.get("spawns", []):
                    spawns.setdefault(nodeid, set()).add(prog)

    for nodeid, t in tests.items():
        t["outcome"] = t["outcome"] or "not-run"
        t["spawns"] = sorted(spawns.get(nodeid, ()))

    ident_start, ident_end = ctl.get("identity_start") or {}, ctl.get("identity_end") or {}
    consistent = (
        not ident_start.get("error")
        and ident_start.get("tree") == ident_end.get("tree")
        and ident_start.get("dirty") == ident_end.get("dirty")
    )
    os.makedirs(dest, exist_ok=True)
    cov_dest = os.path.join(dest, COVERAGE_DB)
    tmp = cov_dest + ".tmp"
    shutil.copyfile(coverage_file, tmp)
    os.replace(tmp, cov_dest)
    contexts = _context_count(cov_dest)
    manifest = {
        "schema": SCHEMA_VERSION,
        "tool": tool_hash(),
        "created": time.time(),
        "suite": "unit",
        "root": ctl["root"],
        "identity": {
            "commit": ident_start.get("commit"),
            "tree": ident_start.get("tree"),
            "dirty": ident_start.get("dirty") or {},
            "consistent": consistent,
            "error": ident_start.get("error") or ident_end.get("error"),
        },
        "environment": ctl.get("environment"),
        "environment_hash": env_hash(ctl.get("environment") or {}),
        "run": {
            "exitstatus": ctl.get("exitstatus"),
            "markexpr": ctl.get("markexpr"),
            "argv": ctl.get("argv"),
            "workers": sorted(s["worker"] for s in shards if not s.get("controller")),
            "started": ctl.get("started"),
            "finished": ctl.get("finished"),
        },
        "coverage": {"file": COVERAGE_DB, "sha256": sha256_file(cov_dest), "contexts": contexts},
        "tests": dict(sorted(tests.items())),
        "data_reads": {k: sorted(v) for k, v in sorted(data_reads.items())},
        "dir_lists": {k: sorted(v) for k, v in sorted(dir_lists.items())},
        "collection_reads": {k: sorted(v) for k, v in sorted(collection_reads.items())},
        "session_reads": sorted(session_reads),
        "errors": errors,
    }
    tmp = os.path.join(dest, BASELINE_JSON + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=1, sort_keys=False)
    os.replace(tmp, os.path.join(dest, BASELINE_JSON))
    return manifest


def _context_count(db: str) -> int:
    import sqlite3

    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        return con.execute("select count(*) from context").fetchone()[0]
    finally:
        con.close()


# -- loading ----------------------------------------------------------------


@dataclass
class Baseline:
    path: str
    manifest: dict
    coverage: CoverageIndex | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def tests(self) -> dict[str, dict]:
        return self.manifest["tests"]

    @property
    def identity(self) -> dict:
        return self.manifest["identity"]


def load_baseline(
    path: str,
    repo_root: str,
    *,
    current_env: dict | None = None,
    on_environment_change: str = "full",
    max_age_days: float | None = None,
    now: float | None = None,
) -> Baseline:
    """Read and validate a baseline. Raises BaselineError naming the fallback."""
    jpath = os.path.join(path, BASELINE_JSON)
    if not os.path.isfile(jpath):
        raise BaselineError("baseline-missing", f"no {BASELINE_JSON} in {path}")
    try:
        with open(jpath, encoding="utf-8") as fh:
            m = json.load(fh)
    except (OSError, ValueError) as exc:
        raise BaselineError("baseline-malformed", f"{jpath}: {exc}") from exc
    if not isinstance(m, dict) or m.get("schema") != SCHEMA_VERSION:
        raise BaselineError(
            "baseline-stale",
            f"schema {m.get('schema') if isinstance(m, dict) else '?'} != "
            f"{SCHEMA_VERSION} (re-record the baseline)",
        )
    for key in ("identity", "tests", "coverage", "data_reads", "dir_lists", "run"):
        if key not in m:
            raise BaselineError("baseline-malformed", f"missing field {key!r}")
    if not isinstance(m["tests"], dict) or not m["tests"]:
        raise BaselineError("baseline-malformed", "the baseline records no tests")
    if m.get("errors"):
        raise BaselineError("baseline-incomplete", f"recorder errors: {m['errors'][0][:200]}")
    ident = m["identity"]
    if ident.get("error") or not ident.get("tree"):
        raise BaselineError("baseline-identity", f"no usable git identity ({ident.get('error')})")
    if not ident.get("consistent"):
        raise BaselineError(
            "baseline-identity", "the tree changed while the baseline run was in progress"
        )
    exitstatus = m["run"].get("exitstatus")
    if exitstatus not in (0, 1):
        raise BaselineError(
            "baseline-incomplete",
            f"the baseline run ended with pytest exit status {exitstatus} "
            "(interrupted or internal error), not a complete run",
        )
    not_run = [n for n, t in m["tests"].items() if t.get("outcome") == "not-run"]
    if not_run:
        raise BaselineError("baseline-incomplete", f"{len(not_run)} collected tests never ran")
    if not object_exists(repo_root, ident["tree"], "tree"):
        raise BaselineError(
            "baseline-revision-unavailable",
            f"tree {ident['tree']} is not in this repository "
            f"(baseline commit {ident.get('commit')}; fetch it or re-record)",
        )
    for path_, oid in (ident.get("dirty") or {}).items():
        if oid and not object_exists(repo_root, oid, "blob"):
            raise BaselineError(
                "baseline-revision-unavailable", f"blob for dirty file {path_} is gone"
            )
    b = Baseline(path=path, manifest=m)
    now = time.time() if now is None else now
    age_days = (now - float(m.get("created", 0))) / 86400
    if max_age_days is not None and age_days > max_age_days:
        raise BaselineError(
            "baseline-stale", f"baseline is {age_days:.1f} days old (max {max_age_days:g})"
        )
    if m.get("tool") != tool_hash():
        b.warnings.append("baseline was recorded by a different version of tools/tia")
    if current_env is not None and env_hash(current_env) != m.get("environment_hash"):
        diff = _env_diff(m.get("environment") or {}, current_env)
        if on_environment_change == "full":
            raise BaselineError("environment-changed", diff)
        b.warnings.append("environment differs from the baseline: " + diff)
    cov_path = os.path.join(path, m["coverage"].get("file", COVERAGE_DB))
    if not os.path.isfile(cov_path):
        raise BaselineError("coverage-missing", f"{cov_path} not found")
    if sha256_file(cov_path) != m["coverage"].get("sha256"):
        raise BaselineError("coverage-corrupt", f"{cov_path} does not match its recorded checksum")
    try:
        b.coverage = CoverageIndex(cov_path, m["root"], set(m["tests"]))
    except BaselineError:
        raise
    except Exception as exc:  # noqa: BLE001 - any unreadable coverage fails open
        raise BaselineError("coverage-corrupt", f"{type(exc).__name__}: {exc}") from exc
    return b


def _env_diff(old: dict, new: dict) -> str:
    out = []
    for k in ("python", "implementation", "platform"):
        if old.get(k) != new.get(k):
            out.append(f"{k} {old.get(k)} -> {new.get(k)}")
    od, nd = set(old.get("distributions", [])), set(new.get("distributions", []))
    if od != nd:
        changed = sorted({d.split("==")[0] for d in od ^ nd})
        out.append(
            "distributions changed: "
            + ", ".join(changed[:8])
            + (" ..." if len(changed) > 8 else "")
        )
    return "; ".join(out) or "fingerprint differs"


class CoverageIndex:
    """Which test phases executed which production lines, from coverage.py data.

    Read straight from the data file's SQLite tables with coverage.py's
    public ``coverage.numbits`` helpers: asking "which contexts touched lines
    lo..hi of this file" is then one indexed query plus a bitwise test per
    row, instead of decoding every line of the file. The schema version is
    checked; one this code was not written for fails open.
    """

    SUPPORTED_SCHEMAS = (7,)

    def __init__(self, db_path: str, recorded_root: str, known_tests: set[str]):
        import sqlite3

        from coverage.numbits import numbits_any_intersection, nums_to_numbits

        self._any = numbits_any_intersection
        self._to_bits = nums_to_numbits
        try:
            self.con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            version = self.con.execute("select version from coverage_schema").fetchone()[0]
        except sqlite3.Error as exc:
            raise BaselineError("coverage-corrupt", f"not a coverage data file: {exc}") from exc
        if version not in self.SUPPORTED_SCHEMAS:
            raise BaselineError("coverage-corrupt", f"coverage schema {version} is not supported")
        try:
            self.contexts = dict(self.con.execute("select id, context from context"))
            files = dict(self.con.execute("select id, path from file"))
            has_lines = self.con.execute("select count(*) from line_bits").fetchone()[0]
        except sqlite3.Error as exc:
            raise BaselineError("coverage-corrupt", f"unreadable coverage data: {exc}") from exc
        if not files or not has_lines:
            raise BaselineError("coverage-corrupt", "coverage data holds no measured lines")
        mapped = sum(1 for c in self.contexts.values() if c and c.rsplit("|", 1)[0] in known_tests)
        if mapped == 0:
            raise BaselineError(
                "coverage-corrupt",
                "no coverage context names a recorded test (was --cov-context=test used?)",
            )
        self.mapped_contexts = mapped
        self.root = recorded_root.rstrip("/")
        self.by_rel: dict[str, int] = {}
        for fid, f in files.items():
            if f.startswith(self.root + "/"):
                self.by_rel[f[len(self.root) + 1 :]] = fid
        self._split = {
            cid: tuple(c.rsplit("|", 1)) for cid, c in self.contexts.items() if c and "|" in c
        }

    def measured(self, rel: str) -> bool:
        return rel in self.by_rel

    def _rows(self, rel: str):
        fid = self.by_rel.get(rel)
        if fid is None:
            return []
        return self.con.execute(
            "select context_id, numbits from line_bits where file_id = ?", (fid,)
        ).fetchall()

    def hits(self, rel: str, lo: int | None = None, hi: int | None = None) -> dict[str, set[str]]:
        """test nodeid -> phases that executed a line of `rel` in [lo, hi].

        The empty context (code run while modules were imported, before any
        test) is not a test and is left out; import-time effects are handled
        by the module-scope rules instead.
        """
        target = self._to_bits(range(lo, hi + 1)) if lo is not None else None
        out: dict[str, set[str]] = {}
        for cid, bits in self._rows(rel):
            split = self._split.get(cid)
            if split is None:
                continue
            if target is not None and not self._any(bits, target):
                continue
            out.setdefault(split[0], set()).add(split[1])
        return out
