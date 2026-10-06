"""The *Evidence Snapshot*: the normalized results of one test run of one tree.

This module owns the tree digest that binds a snapshot to a tree, the
snapshot's model, its derivation from a built graph, the byte form of the
files it holds, reading those files back, and comparing two snapshots.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from elspais.utilities.git import list_index_files, list_uncommitted_files

SNAPSHOT_FILES = ("results.jsonl", "snapshot.json", "TRACEABILITY.md")
TIMINGS_FILE = "timings.jsonl"
OUTCOMES = ("passed", "failed", "skipped")
_LINE_JSON: dict[str, Any] = {
    "sort_keys": True,
    "ensure_ascii": False,
    "separators": (",", ":"),
}


@dataclass(frozen=True)
class TreeDigest:
    """The digest of a tree, the files it covers, and the changes no commit holds.

    *paths* names the repo-relative files the digest covers, so a target's
    inputs can be read over the same files.
    """

    digest: str
    uncommitted: tuple[str, ...]
    paths: frozenset[str]


def _under(path: str, prefix: str) -> bool:
    return path.startswith(prefix)


# Implements: REQ-d00322-D
def tree_digest(repo_root: Path, exclude: str) -> TreeDigest:
    """SHA-256 over (path, content digest) of every tracked or staged file.

    The files under *exclude* are left out, because the snapshot cannot
    describe itself. A checkout of the commit and the working tree that
    wrote it then compute the same digest. Content is read from the working
    tree; a symbolic link contributes its target text, as git records it.
    *repo_root* is the root of the repository's working tree. It raises
    when git cannot answer, so neither the digest nor the list of
    uncommitted changes is ever read from silence.
    """
    prefix = exclude.strip("/") + "/"
    h = hashlib.sha256()
    paths = frozenset(p for p in list_index_files(repo_root) if not _under(p, prefix))
    for rel in sorted(paths):
        file = repo_root / rel
        if file.is_symlink():
            content = os.readlink(file).encode("utf-8")
        elif file.is_file():
            content = file.read_bytes()
        else:
            # Deleted in the working tree, or a submodule: nothing of it is here.
            continue
        h.update(rel.encode("utf-8") + b"\0")
        h.update(hashlib.sha256(content).hexdigest().encode("ascii") + b"\n")
    uncommitted = tuple(
        sorted({p for p in list_uncommitted_files(repo_root) if not _under(p, prefix)})
    )
    return TreeDigest(digest=h.hexdigest(), uncommitted=uncommitted, paths=paths)


class SnapshotUnreadable(Exception):
    """A snapshot file is missing or holds something this module did not write."""

    def __init__(self, path: Path, line: int | None, reason: str) -> None:
        where = f"{path}:{line}" if line is not None else str(path)
        super().__init__(f"{where}: {reason}")
        self.path = path
        self.line = line
        self.reason = reason


@dataclass(frozen=True)
class ResultLine:
    """One result an *Evidence Snapshot* holds, as `results.jsonl` states it."""

    target: str
    file: str
    line: int | None
    name: str
    runner: str | None
    outcome: str
    skip_reason: str | None = None

    def key(self) -> tuple[Any, ...]:
        return (
            self.target,
            self.file,
            -1 if self.line is None else self.line,
            self.name,
            self.runner or "",
            self.outcome,
        )

    def to_json(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass(frozen=True)
class Timing:
    """The duration and printed output of one result; never compared."""

    target: str
    file: str
    line: int | None
    name: str
    runner: str | None
    duration: float
    output: str

    def key(self) -> tuple[Any, ...]:
        return (
            self.target,
            self.file,
            -1 if self.line is None else self.line,
            self.name,
            self.runner or "",
        )

    def to_json(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass(frozen=True)
class Snapshot:
    """An *Evidence Snapshot* in memory."""

    results: tuple[ResultLine, ...]
    tree: str
    targets: tuple[tuple[str, str], ...]  # (target, inputs digest)
    facts: tuple[tuple[str, str], ...]  # (name, value)
    elspais: str
    timings: tuple[Timing, ...]
    report: str


def _json_line(obj: dict[str, Any]) -> str:
    return json.dumps(obj, **_LINE_JSON) + "\n"


# Implements: REQ-d00322-C, REQ-d00322-E, REQ-d00322-M, REQ-d00322-N
def render_files(s: Snapshot) -> dict[str, str]:
    """Return each snapshot file's exact text, keyed by file name.

    Every collection is sorted here, so the bytes depend on the snapshot's
    content and never on the order it was assembled in. Identical results
    stay as separate lines, because two runs that agree are still two runs.
    Targets and facts are lists of objects, so no name is ever a JSON key.
    """
    meta = {
        "elspais": s.elspais,
        "facts": [{"name": n, "value": v} for n, v in sorted(s.facts)],
        "targets": [{"digest": d, "target": t} for t, d in sorted(s.targets)],
        "tree": s.tree,
    }
    report = s.report if s.report.endswith("\n") else s.report + "\n"
    return {
        "results.jsonl": "".join(
            _json_line(r.to_json()) for r in sorted(s.results, key=ResultLine.key)
        ),
        "snapshot.json": json.dumps(meta, indent=1, sort_keys=True) + "\n",
        TIMINGS_FILE: "".join(_json_line(t.to_json()) for t in sorted(s.timings, key=Timing.key)),
        "TRACEABILITY.md": report,
    }


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ValueError(f"key {key!r} appears twice")
        out[key] = value
    return out


def _read(path: Path) -> str:
    if not path.is_file():
        raise SnapshotUnreadable(path, None, "the file is missing")
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise SnapshotUnreadable(path, None, f"cannot be read: {exc}") from exc


def _parse_object(path: Path, line: int | None, text: str) -> dict[str, Any]:
    try:
        obj = json.loads(text, object_pairs_hook=_no_duplicate_keys)
    except ValueError as exc:
        raise SnapshotUnreadable(path, line, f"not valid JSON: {exc}") from exc
    if not isinstance(obj, dict):
        raise SnapshotUnreadable(path, line, "not a JSON object")
    return obj


def _check_keys(
    path: Path, line: int | None, obj: dict[str, Any], required: set[str], optional: set[str]
) -> None:
    missing = sorted(required - obj.keys())
    if missing:
        raise SnapshotUnreadable(path, line, f"missing {', '.join(missing)}")
    unknown = sorted(obj.keys() - required - optional)
    if unknown:
        raise SnapshotUnreadable(path, line, f"unknown key {', '.join(unknown)}")


def _expect(path: Path, line: int | None, obj: dict[str, Any], key: str, kinds: tuple) -> Any:
    value = obj.get(key)
    # bool is an int to isinstance; a line number or duration is never one.
    if value is None or isinstance(value, bool) or not isinstance(value, kinds):
        names = " or ".join(k.__name__ for k in kinds)
        raise SnapshotUnreadable(path, line, f"{key} is not a {names}")
    return value


def _optional(path: Path, line: int, obj: dict[str, Any], key: str, kinds: tuple) -> Any:
    return _expect(path, line, obj, key, kinds) if key in obj else None


def split_lines(text: str) -> list[str]:
    """Split a JSON-lines text at its line feeds alone.

    The writer keeps every character a value holds, so a value may hold a
    character `str.splitlines` also reads as a line end. Only a line feed
    ends a line here, and the one ending the last line opens none.
    """
    rows = text.split("\n")
    if rows and rows[-1] == "":
        rows.pop()
    return rows


def _lines(path: Path, text: str) -> list[tuple[int, dict[str, Any]]]:
    out = []
    for number, raw in enumerate(split_lines(text), start=1):
        if not raw.strip():
            raise SnapshotUnreadable(path, number, "blank line")
        out.append((number, _parse_object(path, number, raw)))
    return out


def _result_line(path: Path, number: int, obj: dict[str, Any]) -> ResultLine:
    _check_keys(
        path,
        number,
        obj,
        {"target", "file", "name", "outcome"},
        {"line", "runner", "skip_reason"},
    )
    outcome = _expect(path, number, obj, "outcome", (str,))
    if outcome not in OUTCOMES:
        raise SnapshotUnreadable(
            path, number, f"outcome {outcome!r} is not one of {', '.join(OUTCOMES)}"
        )
    return ResultLine(
        target=_expect(path, number, obj, "target", (str,)),
        file=_expect(path, number, obj, "file", (str,)),
        line=_optional(path, number, obj, "line", (int,)),
        name=_expect(path, number, obj, "name", (str,)),
        runner=_optional(path, number, obj, "runner", (str,)),
        outcome=outcome,
        skip_reason=_optional(path, number, obj, "skip_reason", (str,)),
    )


def _timing(path: Path, number: int, obj: dict[str, Any]) -> Timing:
    _check_keys(
        path,
        number,
        obj,
        {"target", "file", "name", "duration", "output"},
        {"line", "runner"},
    )
    return Timing(
        target=_expect(path, number, obj, "target", (str,)),
        file=_expect(path, number, obj, "file", (str,)),
        line=_optional(path, number, obj, "line", (int,)),
        name=_expect(path, number, obj, "name", (str,)),
        runner=_optional(path, number, obj, "runner", (str,)),
        duration=float(_expect(path, number, obj, "duration", (int, float))),
        output=_expect(path, number, obj, "output", (str,)),
    )


def _pairs(path: Path, meta: dict[str, Any], key: str, first: str, second: str) -> list:
    entries = meta[key]
    if not isinstance(entries, list):
        raise SnapshotUnreadable(path, None, f"{key} is not a list")
    out = []
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {first, second}:
            raise SnapshotUnreadable(
                path, None, f"each entry of {key} must be an object holding {first} and {second}"
            )
        out.append(
            (_expect(path, None, entry, first, (str,)), _expect(path, None, entry, second, (str,)))
        )
    return out


# Implements: REQ-d00322-C, REQ-d00322-D, REQ-d00322-M
def load_snapshot(directory: Path, *, require_report: bool = True) -> Snapshot:
    """Read an *Evidence Snapshot* back from *directory*.

    A missing compared file, or a line this module would not have written,
    raises `SnapshotUnreadable` naming the file and line: an unreadable
    snapshot is never an empty one. `timings.jsonl` is optional, because
    nothing compares it; where it is present it must be well formed.

    With *require_report* false, an absent `TRACEABILITY.md` reads as an
    empty report. Only the build that renders the report asks for this,
    because the report is that build's output and not yet its input.
    """
    results_path = directory / "results.jsonl"
    meta_path = directory / "snapshot.json"
    report_path = directory / "TRACEABILITY.md"
    timings_path = directory / TIMINGS_FILE

    results_text = _read(results_path)
    meta = _parse_object(meta_path, None, _read(meta_path))
    report = _read(report_path) if require_report or report_path.exists() else ""

    results = tuple(
        _result_line(results_path, n, obj) for n, obj in _lines(results_path, results_text)
    )
    _check_keys(meta_path, None, meta, {"elspais", "facts", "targets", "tree"}, set())
    targets = _pairs(meta_path, meta, "targets", "target", "digest")
    facts = _pairs(meta_path, meta, "facts", "name", "value")
    timings: tuple[Timing, ...] = ()
    if timings_path.exists():
        timings = tuple(
            _timing(timings_path, n, obj) for n, obj in _lines(timings_path, _read(timings_path))
        )
    return Snapshot(
        results=results,
        tree=_expect(meta_path, None, meta, "tree", (str,)),
        targets=tuple(targets),
        facts=tuple(facts),
        elspais=_expect(meta_path, None, meta, "elspais", (str,)),
        timings=timings,
        report=report,
    )


# Implements: REQ-d00322-D
def parse_facts(pairs: list[str]) -> tuple[tuple[str, str], ...]:
    """Read `NAME=VALUE` pairs into (name, value) pairs, sorted by name.

    A pair without `=`, an empty name, or a name given twice is refused,
    because a fact the snapshot holds must say one thing.
    """
    facts: dict[str, str] = {}
    for pair in pairs:
        name, sep, value = pair.partition("=")
        name = name.strip()
        if not sep or not name:
            raise ValueError(f"fact {pair!r} is not NAME=VALUE")
        if name in facts:
            raise ValueError(f"fact {name!r} is given twice")
        facts[name] = value
    return tuple(sorted(facts.items()))


class SnapshotRefused(Exception):
    """The selected results cannot be held in an *Evidence Snapshot*.

    Each reason names the target, the file and the line it concerns.
    """

    def __init__(self, reasons: list[str]) -> None:
        super().__init__("; ".join(reasons))
        self.reasons = reasons


# A status a reporter gives, as the outcome a snapshot holds.
_OUTCOME_OF = {"passed": "passed", "failed": "failed", "error": "failed", "skipped": "skipped"}


def _relative(path: str | None) -> bool:
    return bool(path) and not os.path.isabs(path) and not path.startswith("..")


def _declared_at(result: Any) -> tuple[str, int | None] | None:
    """The repo-relative file and line of the test *result* names, or None.

    A read-back binds a snapshot's result to its test by this place. So the
    place is the bound test's own, not the line a reporter gave: a
    `testWidgets` result names a framework line and binds by its root line.
    A step-scope result binds by its step and its file, and keeps both.
    """
    from elspais.graph.annotators import result_names_no_test
    from elspais.graph.GraphNode import NodeKind
    from elspais.graph.relations import EdgeKind

    if result_names_no_test(result):
        return None
    source_file = result.get_field("source_file")
    if result.get_field("match_scope") == "step":
        return source_file, result.get_field("line")
    places: dict[tuple[str, int | None], Any] = {}
    for test in result.iter_parents(edge_kinds={EdgeKind.YIELDS}):
        if test.kind is not NodeKind.TEST:
            continue
        file = test.file_node()
        rel = file.get_field("relative_path") if file else None
        if rel:
            places[(rel, test.get_field("parse_line"))] = test
    for place in (
        (source_file, result.get_field("line")),
        (result.get_field("root_file") or source_file, result.get_field("root_line")),
    ):
        if place in places:
            return place
    # A group holding the test also yields it; one test alone is unambiguous.
    return next(iter(places)) if len(places) == 1 else None


# Implements: REQ-d00322-A+C+D+E+M
def derive_snapshot(
    graph: Any,
    repo_root: Path,
    config: Any,
    targets: list[str],
    facts: tuple[tuple[str, str], ...],
    report: str,
    *,
    tree: TreeDigest | None = None,
    spell: Callable[[str], str] = str,
) -> Snapshot:
    """Derive the *Evidence Snapshot* of the selected *targets* from *graph*.

    Each RESULT of a selected target in this repository becomes one result
    line and one timing. Every selected target is held with the digest of
    its inputs, even where its run produced no result. A target's digest
    covers only the inputs the tree digest covers: a file git does not
    track is absent from a checkout, so it would make two runs of one tree
    disagree (REQ-d00322-E). *tree* is the digest of the repository's tree
    where the caller already has it. *spell* names a target as the reader
    selects it.

    Raises `SnapshotRefused` where a selected result names no test, or a
    file outside the repository: the snapshot could not bind it back, or
    would hold a path from one machine (REQ-d00322-E).
    """
    import elspais
    from elspais.graph.GraphNode import NodeKind
    from elspais.utilities.fingerprint import compute_manifest, manifest_digest

    by_name = {t.name: t for t in config.scanning.test.targets}
    unknown = sorted(set(targets) - set(by_name))
    if unknown:
        raise SnapshotRefused([f"no test target named {spell(name)!r}" for name in unknown])
    selected = set(targets)

    results: list[ResultLine] = []
    timings: list[Timing] = []
    reasons: list[str] = []
    for node in graph.nodes_by_kind(NodeKind.RESULT, namespace=config.project.namespace):
        target = node.get_field("target")
        if target not in selected:
            continue
        name = node.get_field("name") or ""
        where = f"target {spell(target)}: {node.get_field('source_file') or '?'}"
        where += f":{node.get_field('line')} {name}" if node.get_field("line") else f" {name}"
        status = node.get_field("status")
        outcome = _OUTCOME_OF.get(status or "")
        if outcome is None:
            reasons.append(f"{where}: outcome {status!r} is not passed, failed or skipped")
            continue
        # Implements: REQ-d00329-E
        if node.get_field("match") == "file":
            reasons.append(
                f"{where}: the result is the file-level result of the command's exit "
                f"status, which an Evidence Snapshot does not hold"
            )
            continue
        place = _declared_at(node)
        if place is None:
            reasons.append(f"{where}: the result binds to no single test")
            continue
        file, line = place
        runner = node.get_field("runner_file")
        runner = runner if runner and runner != file else None
        if not file:
            reasons.append(f"{where}: the result names no file")
            continue
        if not _relative(file) or (runner is not None and not _relative(runner)):
            reasons.append(f"{where}: the test lies outside the repository")
            continue
        skip_reason = node.get_field("message") if outcome == "skipped" else None
        results.append(
            ResultLine(
                target=target,
                file=file,
                line=line,
                name=name,
                runner=runner,
                outcome=outcome,
                skip_reason=skip_reason or None,
            )
        )
        timings.append(
            Timing(
                target=target,
                file=file,
                line=line,
                name=name,
                runner=runner,
                duration=float(node.get_field("duration") or 0.0),
                output=node.get_field("output") or "",
            )
        )
    if reasons:
        raise SnapshotRefused(sorted(reasons))

    if tree is None:
        tree = tree_digest(repo_root, exclude=config.scanning.test.evidence)

    def inputs_digest(name: str) -> str:
        manifest = compute_manifest(repo_root, config, by_name[name])
        return manifest_digest({p: d for p, d in manifest.items() if p in tree.paths})

    return Snapshot(
        results=tuple(sorted(results, key=ResultLine.key)),
        tree=tree.digest,
        targets=tuple((name, inputs_digest(name)) for name in sorted(selected)),
        facts=tuple(sorted(facts)),
        elspais=elspais.__version__,
        timings=tuple(sorted(timings, key=Timing.key)),
        report=report,
    )


@dataclass(frozen=True)
class Difference:
    """One way a committed *Evidence Snapshot* differs from a current one.

    ``kind`` is ``outcome``, ``only_committed``, ``only_current``, ``tree``,
    ``fact``, ``target`` or ``report``.
    """

    kind: str
    detail: str


def _test_named(
    identity: tuple[str, str, int | None, str, str | None], spell: Callable[[str], str]
) -> str:
    target, file, line, name, runner = identity
    place = f"{file}:{line}" if line is not None else file
    ran_by = f" ({runner})" if runner else ""
    return f"target {spell(target)}: {place} {name}{ran_by}"


def _pairs_differ(
    kind: str, committed: dict[str, str], current: dict[str, str]
) -> list[Difference]:
    out = []
    for name in sorted(committed.keys() | current.keys()):
        old, new = committed.get(name), current.get(name)
        if old != new:
            before = "absent" if old is None else repr(old)
            after = "absent" if new is None else repr(new)
            out.append(Difference(kind, f"{name}: {before} -> {after}"))
    return out


# Implements: REQ-d00322-H+M
def compare(
    committed: Snapshot, current: Snapshot, *, spell: Callable[[str], str] = str
) -> list[Difference]:
    """Each difference between a committed snapshot and a current one.

    *spell* names a target as the reader selects it.

    A test is identified by its target, file, line, name and runner. Each of
    its runs is counted, so a run present on one side only is a difference
    even where an identical run is on both. Outcomes held on both sides
    cancel first; a remaining pair is an outcome that changed, and what is
    left unpaired is a run on one side only. Durations and printed output
    are never compared. The list is ordered by kind, then detail.
    """
    from collections import Counter

    def runs(snapshot: Snapshot) -> dict[tuple, Counter]:
        out: dict[tuple, Counter] = {}
        for r in snapshot.results:
            identity = (r.target, r.file, r.line, r.name, r.runner)
            out.setdefault(identity, Counter())[r.outcome] += 1
        return out

    differences: list[Difference] = []
    old_runs, new_runs = runs(committed), runs(current)
    for identity in old_runs.keys() | new_runs.keys():
        old = old_runs.get(identity, Counter())
        new = new_runs.get(identity, Counter())
        common = old & new
        left = sorted((old - common).elements())
        right = sorted((new - common).elements())
        test = _test_named(identity, spell)
        for before, after in zip(left, right, strict=False):
            differences.append(Difference("outcome", f"{test}: {before} -> {after}"))
        for outcome in left[len(right) :]:
            differences.append(Difference("only_committed", f"{test}: {outcome}"))
        for outcome in right[len(left) :]:
            differences.append(Difference("only_current", f"{test}: {outcome}"))
    if committed.tree != current.tree:
        differences.append(
            Difference("tree", f"the snapshot describes tree {committed.tree}, not {current.tree}")
        )
    differences += _pairs_differ("fact", dict(committed.facts), dict(current.facts))
    differences += _pairs_differ(
        "target",
        {spell(n): d for n, d in committed.targets},
        {spell(n): d for n, d in current.targets},
    )
    # The file always ends with one line feed, however the report was held.
    if render_files(committed)["TRACEABILITY.md"] != render_files(current)["TRACEABILITY.md"]:
        differences.append(
            Difference("report", "TRACEABILITY.md differs from the report the snapshot renders")
        )
    return sorted(differences, key=lambda d: (d.kind, d.detail))
