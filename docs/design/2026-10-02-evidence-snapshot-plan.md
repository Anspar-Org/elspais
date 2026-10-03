# Evidence Snapshot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** elspais writes, reads back and verifies an *Evidence Snapshot*: the normalized results of one test run of one tree, committed with the change it describes, with a byte-stable traceability report rendered from it.

**Architecture:** One new module, `src/elspais/utilities/evidence.py`, owns the snapshot: the tree digest, the derivation from a built graph, the four files' byte form, loading, and comparison. A new command module `src/elspais/commands/evidence_cmd.py` holds `evidence write` and `evidence verify`. The build reads a snapshot back through a reporter registered in the existing reporter registry, so every snapshot result goes through the same ingestion and binding as any other result. The report is `trace --format markdown` with an evidence detail block, so there is one renderer.

**Tech Stack:** Python 3.10+, Pydantic v2 (config schema), tyro (CLI), pytest. No new dependency.

**Spec:** `docs/design/2026-10-02-evidence-snapshot-design.md` (approved). Read it before any task.

## Global Constraints

- Branch: `TOOL-123-evidence-snapshot`, stacked on `TOOL-123-record-terms` (which is stacked on PR #152). Rebase onto it before Task 1. Commit tags: `[TOOL-123]`.
- The spec precedes the code: Task 1 lands the requirements; every later task cites them with `# Implements:` / `# Verifies:`.
- Defined Term: *Evidence Snapshot*. Never call it a "record". Use *Result Fingerprint*, *Result Record* as the glossary defines them.
- Byte stability: every file the snapshot holds except `timings.jsonl` is a pure function of (tree, results' outcomes, declared facts, spec). No timestamps, durations, absolute paths, machine names, invocation ids or failure messages in them.
- No name is a JSON key beside a digest (secret-scanner rule, as for the *Result Fingerprint*).
- JSON output: `json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))` for `.jsonl` lines; `indent=1, sort_keys=True` plus a trailing newline for `snapshot.json`. Files end with exactly one `\n`.
- Paths in the snapshot are repo-relative POSIX paths.
- Exit codes: 0 success/agreement, 1 difference (verify) or failed target, 2 refusal or usage error.
- Identifier and coverage rules from CLAUDE.md hold: no new identifier regex, no second coverage computation, one renderer per report, no `|| true`, durable prose states the present, no counts in docs.
- Tests: written by a sub-agent (CLAUDE.md Workflow). While iterating, run narrowed tests only: `.venv/bin/python -m pytest <files> --no-cov -q -p no:cacheprovider`. One pytest process per worktree at a time. The full unit tier runs only inside the commit hook.
- Commits: the hook takes several minutes, so commit at the three milestones marked **Commit** (after Tasks 5, 8 and 10), not after each task. Stage every touched file first. Never `--no-verify`.
- Version: bump `pyproject.toml` patch version once per commit. Add `CHANGELOG.md` `[Unreleased]` entries in Task 10.

## Review Focus

Task order for execution: 1, 2, 3, 4, 5, 11, 12, 6, 7, 8, 9, 10. Tasks 11 and 12 come before the snapshot is derived, because the snapshot depends on results that match.

1. A selected target with zero results (all its tests skipped by a tag, or the suite empty) -- `evidence write` must still write the target into `targets` and write no result lines for it; verify must agree on a re-run. (Task 6)
2. A snapshot directory that exists but is missing one of the compared files, or holds a malformed line -- read-back and verify must refuse naming the file and line, never treat it as an empty snapshot. (Tasks 5, 7)
3. Uncommitted or untracked changes when `evidence write` runs -- the tree digest then names a tree CI will not see; `write` must say so on stderr (still writing), and verify in CI must report the digest mismatch. (Tasks 2, 6)
4. The same test run twice with the same outcome (two runners of one shared scenario) -- both lines kept, sorted stably, and verify must count them, not deduplicate them. (Tasks 3, 7)
5. A target whose own results exist AND the snapshot holds lines for it -- the build must read only the target's own results (no double ingestion). (Task 5)

---

### Task 1: Requirements and the Defined Term

**Files:**
- Modify: `spec/dev-graph-core.md` (new requirement after REQ-d00321's file position is irrelevant -- append it after REQ-d00294)
- Modify: `spec/dev-cli.md` (REQ-d00249: one new assertion)
- Modify: `spec/glossary.md`
- Generated: `spec/INDEX.md`, `spec/_generated/*` (via `elspais fix`)

**Interfaces:** Produces REQ-d00322 assertion letters A-N and REQ-d00249-L, cited by every later task.

- [x] **Step 1: Add the Defined Term to `spec/glossary.md`** (same format as the existing entries):

```markdown
Evidence Snapshot
: The normalized results of one test run of one tree, bound to that tree by its digest and stored in the repository with the traceability report derived from them.
```

- [x] **Step 2: Add REQ-d00322 to `spec/dev-graph-core.md`.** Use the existing requirement layout (header, Level/Status/Implements line, preamble, `### Assertions`, `### Rationale`, `### Changelog`, `*End*` line with `**Hash**: 00000000`; `elspais fix` sets the hash).

```markdown
## REQ-d00322: Evidence Snapshot

**Level**: dev | **Status**: Draft | **Implements**: REQ-o00051

A project stores the results of its test suites with each change, and a reader verifies that those results describe that change.

### Assertions

A. The system SHALL write an *Evidence Snapshot* from the results of a selection of test targets.

B. The system SHALL refuse to write an *Evidence Snapshot* while a selected target's results are absent, stale or in progress, and SHALL name each such target.

C. An *Evidence Snapshot* SHALL hold, for each result, the target, the file and line that declare the test, the test name, the file that executed it where that file differs, the outcome, and the skip reason where one is given.

D. An *Evidence Snapshot* SHALL hold the digest of the tree its results describe, each selected target with the digest of its inputs, and the facts the project declared about the run.

E. Two *Evidence Snapshots* written from runs of the same tree with the same outcomes and the same declared facts SHALL be identical, byte for byte, apart from the file that holds durations and printed output.

F. An *Evidence Snapshot* SHALL hold the traceability report, rendered from the *Evidence Snapshot* and the specification alone.

G. For each assertion, the traceability report SHALL name the code that implements it, the tests that verify it, and each test's outcome, by repository-relative file and line.

H. The system SHALL compare an *Evidence Snapshot* with one derived from the current results and SHALL report each test whose outcome differs, each result present on one side only, a tree digest that differs, a declared fact that differs, and a traceability report that differs.

I. The comparison SHALL return a non-zero exit code when any difference exists, and 0 when none exists.

J. Where a target has no results of its own, the system SHALL read that target's results from the *Evidence Snapshot* the project names, and SHALL tag them carried.

K. Where an *Evidence Snapshot*'s tree digest differs from the digest of the current tree, the system SHALL report the *Evidence Snapshot* as stale.

L. Where a federation member names an *Evidence Snapshot* and holds no results of its own, the system SHALL read that member's results from that member's *Evidence Snapshot*, judged against that member's tree.

M. The system SHALL keep each result's duration and printed output beside the *Evidence Snapshot*, and SHALL exclude them from the comparison.

N. No name SHALL appear as a JSON key beside a digest in an *Evidence Snapshot*.

### Rationale

An *Evidence Snapshot* lets a reader cite a commit's test results without running the suites, and lets CI confirm that the results committed with a change describe that change. H is the primary use: a new run is compared with the committed snapshot, test by test.

C excludes durations, timestamps, absolute paths, invocation identifiers and failure messages because each varies between runs of an unchanged tree. E depends on that exclusion. M keeps the measurements a timing guard prints, so they are not lost, and keeps them out of the comparison, so a measurement never fails a verification.

D binds the results to a tree. The digest covers every file git tracks or has staged, apart from the snapshot itself, so a snapshot written over uncommitted work does not match the commit CI checks out.

J and L make the snapshot the source of a member's results in a federation, where a member checkout has run nothing. K stops a snapshot of another tree from reading as current.

N follows the rule the *Result Fingerprint* follows: a secret scanner reads a secret-like key beside a long hexadecimal value as a leaked credential.

### Changelog

- 2026-10-02 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-123: an Evidence Snapshot records a tree's test results and is verified against a new run

*End* *Evidence Snapshot* | **Hash**: 00000000
```

- [x] **Step 3: Add REQ-d00249-L to `spec/dev-cli.md`** after K, with one Rationale paragraph, and a changelog line `TOOL-123: a run executes a federation member's target only where the selection names it (L)`:

```markdown
L. A run that executes targets SHALL execute a federation member's target only where the selection names that member's namespace and the target, and SHALL execute it with that member's configuration, repository root and output area.
```

Rationale paragraph: `L keeps a run inside the repository that asked for it unless the reader names another member. Running a member's target executes a command that the member's configuration declares, so the reader names it explicitly.`

- [x] **Step 3a: Add the assertions the two fixes in Tasks 11 and 12 implement.** Use the next free letter of each requirement (read the requirement first; never reuse a retired letter), with one Rationale paragraph and one changelog line each:

  - REQ-d00311 (Test Result Freshness): `The *Result Fingerprint* SHALL record the root of the tree that its run executed in.`
  - REQ-d00311 (Test Result Freshness), beside the assertion above; REQ-d00254 uses every letter its label style admits: `Where a results artifact records an absolute path under the root that the target's *Result Fingerprint* records, the system SHALL read that path relative to that root.` Rationale: a tree that moves after its tests ran keeps its results; reading such a path against the new root alone matches no test, and the results then read as fresh while crediting nothing.
  - REQ-d00283 (Test Target Groups): `The system SHALL report a target that the run expects, and whose run is in progress, as a target with missing results.` Rationale: a job that died leaves a *Result Fingerprint* with no end; its results are unread, so a gate that expects the target must fail rather than pass over it.

  Record each assigned letter in this plan's Tasks 11 and 12 before moving on. Assigned: REQ-d00311-P (the root recorded), REQ-d00311-P (a path read relative to that root), REQ-d00283-R (an expected run in progress reads as missing results).

- [x] **Step 4: Regenerate and check**

Run: `PATH="$PWD/.venv/bin:$PATH" elspais fix && PATH="$PWD/.venv/bin:$PATH" elspais --spec-dir spec checks --spec`
Expected: `HEALTHY`. Read the diff: `elspais fix` italicizes *Evidence Snapshot* in prose; confirm it did not italicize an unrelated use.

---

### Task 2: Tree digest

**Files:**
- Create: `src/elspais/utilities/evidence.py`
- Test: `tests/utilities/test_evidence_tree.py`

**Interfaces:**
- Produces: `tree_digest(repo_root: Path, exclude: str) -> TreeDigest`; `@dataclass(frozen=True) class TreeDigest: digest: str; uncommitted: tuple[str, ...]` (`uncommitted` lists tracked files that differ from HEAD plus untracked files git does not ignore, for the stderr warning).

- [x] **Step 1: Write the failing tests** (sub-agent). Cases, each in a `tmp_path` git repo made with `subprocess.run(["git", ...])`:
  - same tree -> same digest twice;
  - editing a tracked file changes the digest;
  - a file under `exclude` (e.g. `test-evidence/results.jsonl`) does not change the digest;
  - a staged new file changes the digest; an untracked unignored file does NOT change the digest but appears in `uncommitted`;
  - a gitignored file changes nothing and is not listed;
  - the digest does not depend on the absolute location (copy the repo to another tmp dir -> same digest).

```python
# Verifies: REQ-d00322-D
def test_digest_ignores_the_snapshot_directory(tmp_path):
    repo = _git_repo(tmp_path, {"a.txt": "x", "test-evidence/results.jsonl": "1"})
    before = tree_digest(repo, exclude="test-evidence").digest
    (repo / "test-evidence/results.jsonl").write_text("2")
    assert tree_digest(repo, exclude="test-evidence").digest == before
```

- [x] **Step 2: Run them to see them fail** -- `ImportError`.

- [x] **Step 3: Implement**

```python
# Implements: REQ-d00322-D
"""The *Evidence Snapshot*: the normalized results of one test run of one tree."""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TreeDigest:
    digest: str
    uncommitted: tuple[str, ...]


def _git(repo_root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo_root, check=True, capture_output=True, text=True
    ).stdout


def tree_digest(repo_root: Path, exclude: str) -> TreeDigest:
    """SHA-256 over (path, content digest) of every tracked or staged file.

    The files under *exclude* are left out, because the snapshot cannot
    describe itself. A checkout of the commit and the working tree that
    wrote it then compute the same digest.
    """
    prefix = exclude.rstrip("/") + "/"
    paths = sorted(
        p for p in _git(repo_root, "ls-files", "-z", "--cached").split("\0")
        if p and not p.startswith(prefix)
    )
    h = hashlib.sha256()
    for rel in paths:
        file = repo_root / rel
        if not file.is_file():
            continue  # staged deletion: absent from the tree being described
        h.update(rel.encode("utf-8") + b"\0")
        h.update(hashlib.sha256(file.read_bytes()).hexdigest().encode() + b"\n")
    dirty = _git(repo_root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    uncommitted = tuple(
        sorted(e[3:] for e in dirty.split("\0") if e and not e[3:].startswith(prefix))
    )
    return TreeDigest(digest=h.hexdigest(), uncommitted=uncommitted)
```

- [x] **Step 4: Run the tests** -- PASS.

---

### Task 3: The snapshot model and its byte form

**Files:**
- Modify: `src/elspais/utilities/evidence.py`
- Test: `tests/utilities/test_evidence_model.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class ResultLine: target: str; file: str; line: int | None; name: str; runner: str | None; outcome: str; skip_reason: str | None` with `key() -> tuple` (sort key: target, file, line or -1, name, runner or "", outcome) and `to_json() -> dict` (omits `None` values).
  - `@dataclass(frozen=True) class Timing: target, file, line, name, runner, duration: float, output: str`.
  - `@dataclass(frozen=True) class Snapshot: results: tuple[ResultLine, ...]; tree: str; targets: tuple[tuple[str, str], ...]; facts: tuple[tuple[str, str], ...]; elspais: str; timings: tuple[Timing, ...]; report: str`
  - `SNAPSHOT_FILES = ("results.jsonl", "snapshot.json", "TRACEABILITY.md")`, `TIMINGS_FILE = "timings.jsonl"`
  - `render_files(snapshot: Snapshot) -> dict[str, str]` (file name -> exact text)
  - `load_snapshot(directory: Path) -> Snapshot` raising `SnapshotUnreadable(path, line, reason)`.
  - `parse_facts(pairs: list[str]) -> tuple[tuple[str, str], ...]` raising `ValueError` on a pair without `=` or a repeated name.

- [x] **Step 1: Write the failing tests** (sub-agent): round trip `load_snapshot(write(render_files(s))) == s` minus timings ordering; sorting is stable and keeps duplicate lines; `snapshot.json` has `targets` as a list of `{"digest", "target"}` objects (Review Focus N: assert no key of any object in `snapshot.json` is a target name); a missing compared file and a malformed line each raise `SnapshotUnreadable` naming file and line; `render_files` output ends with one newline per file; `parse_facts(["a=1", "a=2"])` raises.

```python
# Verifies: REQ-d00322-C, REQ-d00322-E
def test_two_identical_runs_render_identical_bytes():
    a = _snapshot(results=[_line("t", "x_test.dart", 3, "n", "passed")] * 2)
    b = _snapshot(results=[_line("t", "x_test.dart", 3, "n", "passed")] * 2)
    fa, fb = render_files(a), render_files(b)
    assert {k: v for k, v in fa.items() if k != TIMINGS_FILE} == {
        k: v for k, v in fb.items() if k != TIMINGS_FILE
    }
    assert fa["results.jsonl"].count("\n") == 2
```

- [x] **Step 2: Run -- FAIL.**

- [x] **Step 3: Implement** in `evidence.py`:

```python
import json
from typing import Any

SNAPSHOT_FILES = ("results.jsonl", "snapshot.json", "TRACEABILITY.md")
TIMINGS_FILE = "timings.jsonl"
_LINE_JSON = {"sort_keys": True, "ensure_ascii": False, "separators": (",", ":")}


class SnapshotUnreadable(Exception):
    def __init__(self, path: Path, line: int | None, reason: str) -> None:
        where = f"{path}:{line}" if line else str(path)
        super().__init__(f"{where}: {reason}")
        self.path, self.line, self.reason = path, line, reason


@dataclass(frozen=True)
class ResultLine:
    target: str
    file: str
    line: int | None
    name: str
    runner: str | None
    outcome: str
    skip_reason: str | None = None

    def key(self) -> tuple[Any, ...]:
        return (self.target, self.file, self.line or -1, self.name, self.runner or "", self.outcome)

    def to_json(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass(frozen=True)
class Timing:
    target: str
    file: str
    line: int | None
    name: str
    runner: str | None
    duration: float
    output: str


@dataclass(frozen=True)
class Snapshot:
    results: tuple[ResultLine, ...]
    tree: str
    targets: tuple[tuple[str, str], ...]   # (target, inputs digest), sorted
    facts: tuple[tuple[str, str], ...]     # (name, value), sorted
    elspais: str
    timings: tuple[Timing, ...]
    report: str


def render_files(s: Snapshot) -> dict[str, str]:
    results = "".join(
        json.dumps(r.to_json(), **_LINE_JSON) + "\n" for r in sorted(s.results, key=ResultLine.key)
    )
    meta = {
        "elspais": s.elspais,
        "facts": [{"name": n, "value": v} for n, v in s.facts],
        "targets": [{"digest": d, "target": t} for t, d in s.targets],
        "tree": s.tree,
    }
    timings = "".join(
        json.dumps({k: v for k, v in t.__dict__.items() if v is not None}, **_LINE_JSON) + "\n"
        for t in sorted(s.timings, key=lambda t: (t.target, t.file, t.line or -1, t.name, t.runner or ""))
    )
    report = s.report if s.report.endswith("\n") else s.report + "\n"
    return {
        "results.jsonl": results,
        "snapshot.json": json.dumps(meta, indent=1, sort_keys=True) + "\n",
        TIMINGS_FILE: timings,
        "TRACEABILITY.md": report,
    }
```

`facts` is stored as a list of `{name, value}` objects, so no project-chosen name is ever a key (REQ-d00322-N). Implement `load_snapshot` reading the three compared files (and `timings.jsonl` if present), raising `SnapshotUnreadable` for a missing file or a line that is not a JSON object with the required keys (`target`, `file`, `name`, `outcome`; `outcome` in `passed|failed|skipped`). Implement `parse_facts`.

- [x] **Step 4: Run -- PASS.**

---

### Task 4: Durations and printed output from `flutter-machine`

**Files:**
- Modify: `src/elspais/graph/parsers/results/flutter_machine.py`
- Modify: `src/elspais/graph/factory.py` (`parsed_data` dict in `_ingest_target_results`, ~:462)
- Modify: `src/elspais/graph/builder.py` (`_add_test_result` `_content`, ~:5624)
- Test: `tests/core/test_flutter_machine_parser.py`

**Interfaces:** Produces RESULT field `output: str | None` and a real `duration` (seconds) for `flutter-machine` results.

- [x] **Step 1: Write failing tests** (sub-agent): a stream with `testStart` at `time` 100, a `print` event `{"type":"print","testID":1,"message":"ratio 0.9x","messageType":"print"}`, `testDone` at `time` 1600 -> record `duration == 1.5`, `output == "ratio 0.9x"`; two prints join with `\n`; a test with no print has `output` absent/None; a print for an unknown testID is ignored. A graph-level test asserts the RESULT node's `output` field.

- [x] **Step 2: Run -- FAIL.**

- [x] **Step 3: Implement.** In `parse()`:

```python
            elif etype == "testStart":
                ...
                tests[t.get("id")] = {..., "started": ev.get("time")}
            # Implements: REQ-d00322-M
            elif etype == "print":
                meta = tests.get(ev.get("testID"))
                if meta is not None:
                    meta.setdefault("output", []).append(str(ev.get("message", "")))
```

In the `testDone` record: `"duration": _seconds(meta.get("started"), ev.get("time"))` with `def _seconds(start, end) -> float: return round((end - start) / 1000, 3) if isinstance(start, int) and isinstance(end, int) else 0.0`, and `"output": "\n".join(meta["output"]) if meta.get("output") else None`. Add `"output": rec.get("output")` to `parsed_data` and `"output": data.get("output")` to the RESULT `_content` (with `# Implements: REQ-d00322-M`).

- [x] **Step 4: Run -- PASS** (also rerun `tests/core/test_parsers/test_flutter_machine_parser.py`; update its expected key set to include `output` if it asserts the exact set).

---

### Task 5: The `evidence` setting and reading a snapshot back

**Files:**
- Modify: `src/elspais/config/schema.py` (`TestScanningConfig`, beside `output_root` :790)
- Regenerate: `src/elspais/config/elspais-schema.json` (`elspais config schema --output src/elspais/config/elspais-schema.json`)
- Modify: `src/elspais/commands/init.py` (`_FIELD_COMMENTS`, beside `"scanning.test.output_root"` :252)
- Modify: `docs/configuration.md` (beside the `output_root` prose :284-292)
- Create: `src/elspais/graph/parsers/results/evidence_snapshot.py`
- Modify: `src/elspais/graph/parsers/results/registry.py` (register reporter `evidence-snapshot`, channel `file`, kind `results`, `line_base=1`)
- Modify: `src/elspais/graph/factory.py` (`_ingest_target_results` gains `reporter: str | None = None`; the two `reason="absent"` branches ~:1582 and ~:1596; `build_graph`/`_build_repository` gain `evidence_only: bool = False`)
- Test: `tests/core/test_evidence_readback.py`

**Interfaces:**
- Consumes: `load_snapshot`, `ResultLine` (Task 3).
- Produces: config `scanning.test.evidence: str = ""`; `build_graph(..., evidence_only: bool = False)`; RESULT nodes from a snapshot carry `carried=True`, `result_file="<evidence dir>/results.jsonl"`, `result_line=<line number in results.jsonl>`.

- [x] **Step 1: Write failing tests** (sub-agent), each on a `tmp_path` project with a spec, a Dart-style test file declaring a `test(` with `// Verifies:` (reuse the project-building helper in `tests/core/test_target_ingestion.py` that builds the shared-scenario project), a `flutter-machine` target, and a committed snapshot directory:
  - no `.results/<target>/` -> the RESULT nodes come from the snapshot, are `carried`, bind to the declared TEST (`match_scope == "test"`), and the assertion reads Passing;
  - the target HAS its own results -> nothing is read from the snapshot (Review Focus 5: count RESULT nodes);
  - `evidence_only=True` with own results present -> only snapshot results;
  - a malformed `results.jsonl` line -> an ingestion fault naming the file and line (`tests.ingestion_fault`), not an empty read (Review Focus 2);
  - `evidence` set to `../x` or an absolute path -> config validation error, same wording style as `output_root`.

- [x] **Step 2: Run -- FAIL.**

- [x] **Step 3: Implement.**

Schema (copy `_check_output_root`'s checks; empty string means "no snapshot"):

```python
    evidence: str = ""
    """Repo-relative directory holding the project's *Evidence Snapshot*. Empty: none."""

    # Implements: REQ-d00322-J
    @field_validator("evidence")
    @classmethod
    def _check_evidence(cls, v: str) -> str:
        if not v:
            return v
        norm = posixpath.normpath(v)
        if posixpath.isabs(norm) or norm in (".", "..") or norm.startswith("../"):
            raise ValueError(
                f"scanning.test.evidence must name a directory inside the repository, "
                f"not {v!r}"
            )
        return norm
```

Reporter parser (`evidence_snapshot.py`). The factory hands it only the lines of one target, each carrying an added `"_line"` key (its 1-based line number in `results.jsonl`). The parser maps each JSON line to a record:

```python
# Implements: REQ-d00322-J
class EvidenceSnapshotParser(DiagnosticRecorder):
    def parse(self, content: str, source_path: str = "") -> list[dict[str, Any]]:
        self._start_diagnostics()
        records = []
        for number, text in enumerate(content.splitlines(), start=1):
            if not text.strip():
                continue
            try:
                row = json.loads(text)
            except ValueError:
                self._record_diagnostic(source_path, f"line {number} is not JSON")
                continue
            records.append({
                "ordinal": int(row["_line"]),          # set by the factory: line in results.jsonl
                "name": row["name"], "classname": "",
                "status": row["outcome"], "duration": 0.0,
                "message": row.get("skip_reason"),
                "source_path": row["file"], "line": row.get("line"),
                "root_line": None, "root_path": None,
                "runner_path": row.get("runner"), "test_id": None,
                "result_file": source_path or None, "result_line": int(row["_line"]),
            })
        return records
```

Factory: load the snapshot once per repository build when `typed_config.scanning.test.evidence` is set (`load_snapshot(repo_root / evidence)`; on `SnapshotUnreadable`, `builder.record_ingestion_fault(path=<repo-rel file>, stage="results", cause=str(exc), target="")` and read nothing). Group its lines by target, re-serialised one per line with an added `"_line"` (the 1-based line number in `results.jsonl`). In each of the two `reason="absent"` branches, and for every target when `evidence_only` is true, if the snapshot holds lines for `target.name`:

```python
                    # Implements: REQ-d00322-J+L
                    # A target with no results of its own reads the project's
                    # Evidence Snapshot, tagged carried.
                    _ingest_target_results(
                        builder, target, snapshot_lines[target.name], repo_root,
                        f"{evidence_dir}/results.jsonl",
                        namespace=typed_config.project.namespace, carried=True,
                        scanned_tests=target_tests, reporter="evidence-snapshot",
                    )
                    continue
```

In `_ingest_target_results`, use `get_reporter(reporter or target.reporter)`. Note `make_result_id(namespace, result_file, ordinal)` then spells `result:<ns>:<evidence dir>/results.jsonl:<line>`, unique and stable. Since `source_path` in snapshot lines is already repo-relative, the existing normalisation keeps it as-is.

Docs: `docs/configuration.md` gets a commented `# evidence = "test-evidence"` with two lines of explanation beside `output_root`; `init.py` gets `"scanning.test.evidence": "Directory of the Evidence Snapshot that evidence write fills and builds read when a target has no results"`. Regenerate the schema JSON.

- [x] **Step 4: Run -- PASS** (plus `tests/core/test_json_schema.py`, `tests/core/test_target_ingestion.py`).

- [ ] **Step 5: Commit** (milestone 1: Tasks 1-5). Bump the patch version. Message `[TOOL-123] Hold an Evidence Snapshot and read results back from it`.

---

### Task 6: Deriving a snapshot from a graph, and the report

**Files:**
- Modify: `src/elspais/utilities/evidence.py` (`derive_snapshot`)
- Modify: `src/elspais/graph/aggregation.py` (receives `iter_assertion_coverage`, moved from `mcp/server.py:154`)
- Modify: `src/elspais/mcp/server.py` (import it from `graph.aggregation`; delete the private copy)
- Modify: `src/elspais/commands/trace.py` (`format_markdown` detail block, `REPORT_PRESETS`, `ReportPreset.include_code_refs` wired)
- Test: `tests/utilities/test_evidence_derive.py`, `tests/commands/test_trace_evidence_detail.py`

**Interfaces:**
- Produces: `iter_assertion_coverage(req_node, kind_filter, *, edge_kinds=None, direct_only=False)` in `graph/aggregation.py` (same body as today); `location_of(node) -> str` in `graph/aggregation.py` returning `"<repo-relative path>:<line>"` from `node.file_node().get_field("relative_path")` and `node.get_field("parse_line")`; `derive_snapshot(graph, repo_root: Path, config: ElspaisConfig, targets: list[str], facts, report: str) -> Snapshot`; trace preset `"evidence"`.

- [x] **Step 1: Write failing tests** (sub-agent):
  - `derive_snapshot` over a built tmp project yields one `ResultLine` per RESULT node of the selected targets (outcome from `status`: `passed|failed|skipped`; `error` maps to `failed`), `runner` only where `runner_file != source_file`, `skip_reason` from `message` for skipped results only, failure messages excluded; `targets` holds every selected target even with zero results (Review Focus 1), digest = `manifest_digest(compute_manifest(...))`;
  - `trace --format markdown --preset evidence` over a project whose test ids carry absolute paths prints no absolute path (assert `str(tmp_path)` not in output) and prints, per assertion, `Code:` lines `- path:line` and `Tests:` lines `- path:line name -- passed`;
  - two renders of the same graph are identical;
  - a selected result that binds to no test, or whose file lies outside the repository, makes `derive_snapshot` raise `SnapshotRefused` naming the target, file and line.

- [x] **Step 2: Run -- FAIL.**

- [x] **Step 3: Implement.**

Move `_iter_assertion_coverage` verbatim to `graph/aggregation.py` as `iter_assertion_coverage` (keep its `# Implements: REQ-d00066-B, REQ-d00066-D`), and import it in `mcp/server.py` under the old private name's call sites. Add:

```python
# Implements: REQ-d00322-G
def location_of(node: GraphNode) -> str:
    """A node's place as a reader finds it: repo-relative path and line."""
    file = node.file_node()
    rel = file.get_field("relative_path") if file else ""
    line = node.get_field("parse_line")
    return f"{rel}:{line}" if line else rel
```

Trace: add preset `"evidence"` = `standard`'s values with `include_assertions=True, include_code_refs=True, include_test_refs=True`. In `format_markdown`, when `preset.name == "evidence"`, replace the `Test Refs` block with one `<details><summary>Evidence</summary>` block per requirement listing, for each assertion label in sorted order, `**A**` then `Code:` (`- {location_of(code)}` for each CODE from `iter_assertion_coverage(req, NodeKind.CODE, edge_kinds={EdgeKind.IMPLEMENTS})`, sorted, deduplicated) and `Tests:` (`- {location_of(test)} {name} -- {outcomes}` where `outcomes` is the sorted, comma-joined statuses of the test's RESULT children, or `awaiting a result`). The rest of `format_markdown` is unchanged. `--preset evidence` is accepted by `trace` like the other presets.

`derive_snapshot` raises `SnapshotRefused(reasons: list[str])` where any selected RESULT has `match_scope` other than `test` or `step` (it names no test), or a `source_file` that is absolute or starts with `..` (it lies outside the repository). Each reason names the target, the file and the line. Such a result would carry a machine-specific path into the snapshot and break byte stability (REQ-d00322-E). `evidence write` and `evidence verify` print the reasons and exit 2. `derive_snapshot` walks `graph.nodes_by_kind(NodeKind.RESULT)` (federated: only the host repository's entry -- `graph.iter_repos()` first entry), keeps those whose `target` is selected, builds `ResultLine`/`Timing`, reads facts as given, `tree=tree_digest(repo_root, exclude=config.scanning.test.evidence).digest`, `elspais=elspais.__version__`, `targets` from `fingerprint.compute_manifest` per selected target.

- [x] **Step 4: Run -- PASS** (plus the MCP tests touching `_iter_assertion_coverage`: `grep -rln iter_assertion_coverage tests`).

---

### Task 7: Comparing two snapshots

**Files:**
- Modify: `src/elspais/utilities/evidence.py`
- Test: `tests/utilities/test_evidence_compare.py`

**Interfaces:**
- Produces: `@dataclass(frozen=True) class Difference: kind: str; detail: str` with kinds `outcome`, `only_committed`, `only_current`, `tree`, `fact`, `target`, `report`; `compare(committed: Snapshot, current: Snapshot) -> list[Difference]`.

- [x] **Step 1: Write failing tests** (sub-agent): equal snapshots -> `[]`; one test passed->failed -> one `outcome` difference naming `file:line name (runner)`; a duplicate line on one side only -> one `only_committed`/`only_current` (multiset, Review Focus 4); tree differs -> `tree`; a fact differs -> `fact`; a target's input digest differs -> `target`; report text differs -> `report`; timings differences -> nothing.

- [x] **Step 2: Run -- FAIL.**

- [x] **Step 3: Implement** with `collections.Counter` over `ResultLine` minus `outcome` as identity: identity = `(target, file, line, name, runner)`; for each identity compare the sorted outcome lists; equal counts with different outcomes -> `outcome`; extra items -> `only_*`. Order the returned list by kind then detail.

- [x] **Step 4: Run -- PASS.**

---

### Task 8: `elspais evidence write` and `elspais evidence verify`

**Files:**
- Create: `src/elspais/commands/evidence_cmd.py`
- Modify: `src/elspais/commands/args.py` (`EvidenceWriteArgs`, `EvidenceVerifyArgs`, `EvidenceAction`, `EvidenceArgs`; `Command` union; `COMMAND_GROUPS["evidence"] = "Reports"`)
- Modify: `src/elspais/cli.py` (import, `_CMD_MAP`, nested-action block like `FingerprintArgs` :220, dispatch)
- Modify: `tests/core/test_cli_args.py` (expected set + count)
- Modify: `src/elspais/docs/cli/commands.md` (`## evidence` section; then `python -m elspais.utilities.doc_tables`)
- Test: `tests/test_evidence_cmd.py`

**Interfaces:**
- Consumes: Tasks 2-7; `executable_selection`, `run_configured_targets` (`commands/test_runner.py`); `fingerprint.judge`.
- Modifies: `executable_selection(config, selected, *, require_command: bool = True)` -- the existing "at least one selected target has a command" refusal applies only when `require_command` is true. Existing callers keep the default.
- Produces: `evidence_cmd.run(args) -> int`.

Args:

```python
@dataclasses.dataclass
class EvidenceWriteArgs:
    """Write the Evidence Snapshot from the selected targets' current results."""

    targets: Annotated[list[list[str]], tyro.conf.UseAppendAction] = dataclasses.field(default_factory=list)
    """Targets or groups to include, as `checks --run-tests --targets` reads them."""

    fact: Annotated[list[list[str]], tyro.conf.UseAppendAction] = dataclasses.field(default_factory=list)
    """NAME=VALUE facts about the run, e.g. backends=vm,postgres (repeatable)."""


@dataclasses.dataclass
class EvidenceVerifyArgs:
    """Compare the committed Evidence Snapshot with one derived from the current results."""

    targets: Annotated[list[list[str]], tyro.conf.UseAppendAction] = dataclasses.field(default_factory=list)
    fact: Annotated[list[list[str]], tyro.conf.UseAppendAction] = dataclasses.field(default_factory=list)
    run: bool = False
    """Execute the selected targets first, as `elspais test` does."""
```

- [x] **Step 1: Write failing tests** (sub-agent), through `main([...])` in a tmp git repo with a stub target whose command writes a `flutter-machine` stream into `$ELSPAIS_TARGET_OUTPUT`:
  - no `evidence` setting -> exit 2 naming `scanning.test.evidence`;
  - a target with no `command` whose fresh results were copied into its output area (with their *Result Fingerprint*) -> `evidence write` accepts it; `evidence verify --run` refuses it as having no command;
  - `evidence write` before any run -> exit 2 naming the target as absent; after a run that changed an input mid-way -> exit 2 naming it stale (REQ-d00322-B);
  - `elspais test` then `evidence write --fact backends=vm` -> exit 0, the four files exist, `TRACEABILITY.md` contains the evidence block, a second write is byte-identical (REQ-d00322-E);
  - untracked file present -> write still exits 0 and stderr names the file (Review Focus 3);
  - commit, then `evidence verify --fact backends=vm` -> exit 0; change the stub to fail, `evidence verify --run --fact backends=vm` -> exit 1 and stdout names the test with `passed -> failed`; `--fact backends=other` -> exit 1 naming the fact (REQ-d00322-H+I);
  - edit a source file after commit -> verify reports `tree`.

- [x] **Step 2: Run -- FAIL.**

- [x] **Step 3: Implement** `evidence_cmd.run`:

```python
# Implements: REQ-d00322-A+B+F+H+I
def run(args: argparse.Namespace) -> int:
    repo_root = find_git_root() or Path.cwd()
    config = validate_config(get_config(getattr(args, "config", None), start_path=Path.cwd()))
    directory = config.scanning.test.evidence
    if not directory:
        print("error: set scanning.test.evidence to the directory that holds the "
              "Evidence Snapshot, e.g. evidence = \"test-evidence\"", file=sys.stderr)
        return 2
    try:
        # write and verify read results a CI job may have copied in, so a
        # selected target needs no command; verify --run executes, so it does.
        only = executable_selection(
            config, list(flag_values(args, "targets")),
            require_command=args.evidence_action == "verify" and args.run,
        )
        facts = parse_facts(list(flag_values(args, "fact")))
    except (SelectionRefused, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    selected = sorted(t.name for t in config.scanning.test.targets
                      if t.reporter and (only is None or t.name in only))
    if args.evidence_action == "verify" and args.run:
        results, _ = run_configured_targets(config, repo_root, only=set(selected))
        if any(not r.succeeded for r in results):
            print("note: a target failed; comparing its results", file=sys.stderr)
    unfit = [(n, v) for n in selected if (v := judge(repo_root, config, n)).state != "fresh"]
    if unfit:
        for name, verdict in unfit:
            print(f"error: target {name} results are {verdict.state}"
                  f"{' (' + verdict.reason + ')' if verdict.reason else ''}", file=sys.stderr)
        return 2
    current = _derive(repo_root, config, selected, facts)
    if args.evidence_action == "write":
        _write(repo_root / directory, current)
        return 0
    try:
        committed = load_snapshot(repo_root / directory)
    except SnapshotUnreadable as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    differences = compare(committed, current)
    for d in differences:
        print(f"{d.kind}: {d.detail}")
    print("Evidence Snapshot matches the current results" if not differences
          else f"Evidence Snapshot differs from the current results")
    return 1 if differences else 0
```

`_derive` builds the graph once from own results (`build_graph(config=..., repo_root=repo_root, fresh_targets=set(selected))`), derives the snapshot without a report, renders its files into a temporary directory inside the scratch of the process (`tempfile.TemporaryDirectory()`), builds again with `evidence_only=True` reading that rendered snapshot (pass the directory through a `config` copy whose `scanning.test.evidence` points at it -- `tree_digest` still excludes the real directory), renders `render_trace(graph, config, TraceRequest(...), "markdown", REPORT_PRESETS["evidence"])`, and returns the snapshot with `report` set. Print the `tree_digest(...).uncommitted` warning on stderr when non-empty. `_write` writes `render_files` output with `write_text(..., encoding="utf-8", newline="\n")`, creating the directory.

Wire the args/cli exactly like `FingerprintArgs` (nested `EvidenceAction = Annotated[EvidenceWriteArgs, tyro.conf.subcommand("write")] | Annotated[EvidenceVerifyArgs, tyro.conf.subcommand("verify")]`, `ns.evidence_action`). Add the `## evidence` section to `commands.md` (usage lines, both subcommands, exit codes), regenerate tables, update `test_cli_args.py` (add `EvidenceArgs`, count +1).

- [x] **Step 4: Run -- PASS** (plus `tests/core/test_cli_args.py tests/core/test_doc_tables.py`).

- [ ] **Step 5: Commit** (milestone 2: Tasks 6-8). Bump the patch version. Message `[TOOL-123] Write and verify an Evidence Snapshot, with an evidence trace report`.

---

### Task 9: Snapshot staleness, and federation members

**Files:**
- Modify: `src/elspais/commands/health.py` (`check_test_results_stale` :3965)
- Modify: `src/elspais/commands/test_runner.py` (`executable_selection` accepts `NAMESPACE:NAME`; new `member_runs`)
- Modify: `src/elspais/commands/_targets.py` (`_federation_members` keeping `repo_root`)
- Modify: `src/elspais/commands/test_cmd.py`, `src/elspais/commands/health.py` (`run`), `src/elspais/commands/evidence_cmd.py` (call `member_runs`)
- Test: `tests/test_evidence_federation.py`

**Interfaces:**
- Produces: `@dataclass(frozen=True) class TargetRun: namespace: str; config: ElspaisConfig; repo_root: Path; only: set[str]`; `plan_target_runs(config, repo_root, selected: list[str]) -> list[TargetRun]` (in `test_runner.py`; raises `SelectionRefused`). Bare names and groups resolve in the root as today (`executable_selection`); a `NS:NAME` (target or group) resolves through `plan_federation` against that member's validated config, keeping `PlannedRepo.repo_root`; an unknown namespace or name is refused with the same wording `resolve_expected_targets` uses.

- [x] **Step 1: Write failing tests** (sub-agent), with a root and one associate in `tmp_path` (`[associates.lib] path = "../lib", namespace = "LIB"` -- copy the setup in `tests/config/test_federation_config.py`):
  - `elspais test --targets LIB:unit` runs the associate's command with `cwd` under the associate, writes `lib/.results/unit/`, and does not run any root target; `elspais test` (bare) never runs `LIB:unit` (REQ-d00249-L);
  - the associate has a committed snapshot and no `.results` -> the root's federated graph reads the associate's results from it, carried (REQ-d00322-L);
  - the associate's snapshot tree digest no longer matches the associate's tree -> `tests.results_stale` has a finding naming the associate and the snapshot directory (REQ-d00322-K); matching digest -> no finding.

- [x] **Step 2: Run -- FAIL.**

- [x] **Step 3: Implement.** In `check_test_results_stale`, for each `entry` in `graph.iter_repos()` whose validated config sets `scanning.test.evidence` and whose graph holds a RESULT with `result_file` under that directory, compute `tree_digest(entry.repo_root, exclude=...)` and compare with `load_snapshot(...).tree`; on a mismatch add `HealthFinding(message=f"Evidence Snapshot {directory} describes another tree", repo=entry.name, file_path=f"{directory}/snapshot.json")`. Implement `plan_target_runs` and make `test_cmd.run`, `health.run` (`--run-tests`) and `evidence verify --run` loop over its `TargetRun`s calling `run_configured_targets(run.config, run.repo_root, only=run.only)`. `unrecorded_targets` is checked per run.

- [x] **Step 4: Run -- PASS** (plus `tests/test_test_runner.py`, `tests/test_health_expectation.py`).

---

### Task 11: Results keep matching when the tree moves

**Files:**
- Modify: `src/elspais/utilities/fingerprint.py` (`start_run` writes `"root": str(repo_root.resolve())`)
- Modify: `src/elspais/graph/factory.py` (`_ingest_target_results`'s `_repo_relative_or_kept`; the caller passes the target's recorded root)
- Test: `tests/core/test_target_ingestion.py`, `tests/test_result_freshness.py`

**Interfaces:**
- Produces: the *Result Fingerprint* key `root`; `_ingest_target_results(..., recorded_root: Path | None = None)`.

- [x] **Step 1: Write failing tests** (sub-agent): run a stub `flutter-machine` target (absolute `file://` URLs and `suite.path` under the project), then copy the whole project, `.results/` included, to another `tmp_path` directory and build there. The results bind to their tests (`match_scope == "test"`), `tests.unmatched_results` passes, Passing is unchanged. A fingerprint without `root` (written by hand) keeps today's behaviour. A path under neither root stays absolute and unmatched.
- [x] **Step 2: Run -- FAIL.**
- [x] **Step 3: Implement.** In `start_run`, add `"root"` to the fingerprint (`# Implements: REQ-d00311-P`). In the factory's results branch, read `read_fingerprint(area)` once per target and pass `Path(fp["root"])` when present. In `_repo_relative_or_kept`, try the current root first, then the recorded root (`# Implements: REQ-d00311-P`):

```python
    def _repo_relative_or_kept(raw: str | None) -> str | None:
        if not raw or not os.path.isabs(raw):
            return raw
        for root in (repo_root_resolved, recorded_root):
            if root is None:
                continue
            try:
                return str(Path(raw).resolve(strict=False).relative_to(root))
            except ValueError:
                continue
        return raw
```

  Note that `Path.resolve()` on a path that no longer exists returns it unchanged on POSIX, so the recorded-root comparison works on the moved tree.
- [x] **Step 4: Run -- PASS** (plus `tests/test_result_freshness.py`, `tests/test_health_expectation.py`).

### Task 12: An expected target whose run is in progress fails the gate

**Files:**
- Modify: `src/elspais/commands/health.py` (the check that reports missing results of executed or expected targets: `tests.ingestion_fault`, REQ-d00283-R+S)
- Test: `tests/test_health_expectation.py`

- [x] **Step 1: Write failing tests** (sub-agent): a target folder whose *Result Fingerprint* has no `finished_at`; `checks --expect <target>` reports `tests.ingestion_fault` failed, naming the target and saying its run is in progress; without `--expect` (and not executed) it stays `tests.run_in_progress` information as today.
- [x] **Step 2: Run -- FAIL.**
- [x] **Step 3: Implement.** Where the check walks expected and executed targets, treat an `UnreadArtifact` with `reason="running"` for an expected target as missing results (`# Implements: REQ-d00283-R`), with the message `target <name>: results unread because its run is in progress (started <started_at>)`.
- [x] **Step 4: Run -- PASS.**

### Task 10: Documentation, changelog, version

**Files:**
- Modify: `src/elspais/docs/cli/test-targets.md` (new section `## Evidence Snapshot`: what it holds, `evidence write`, `evidence verify [--run]`, reading back, staleness, federation, the CI recipe from the design's "consumer's workflow")
- Modify: `src/elspais/docs/cli/commands.md` (already has `## evidence`; link the topic)
- Modify: `CHANGELOG.md` (`[Unreleased]` `### Added`: one entry for the snapshot and its commands citing REQ-d00322; one for member target runs citing REQ-d00249-L; one `### Changed` for the `flutter-machine` duration/output)
- Modify: `pyproject.toml` (patch bump)
- Modify: CLAUDE.md (one bullet under the "No Duplicate Library Functions" list: "Evidence Snapshot: only `utilities/evidence.py` (`tree_digest`, `derive_snapshot`, `render_files`, `load_snapshot`, `compare`) ... Do NOT read or write `test-evidence/` files anywhere else."; and note `iter_assertion_coverage` now lives in `graph/aggregation.py`)

- [x] **Step 1: Write the docs.** Deterministic Syntax style; no counts; present tense.
- [x] **Step 2: Check** `markdownlint --config .markdownlint.json <changed .md>`, `.venv/bin/python -m elspais.utilities.doc_tables`, `.venv/bin/ruff check src tests`, `.venv/bin/ruff format --check src tests`, `PATH="$PWD/.venv/bin:$PATH" elspais fix`, `elspais --spec-dir spec checks --spec`.
- [ ] **Step 3: Commit** (milestone 3: Tasks 9-10). Message `[TOOL-123] Read a member's Evidence Snapshot, run a named member's targets, and document the snapshot`.
- [ ] **Step 4: e2e verdict and push** via the `push` skill; then open the PR against `TOOL-123-record-terms` with `/hht-devkit:pr-create`.
