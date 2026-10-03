"""The *Evidence Snapshot*: the normalized results of one test run of one tree.

This module owns the tree digest that binds a snapshot to a tree, the
snapshot's model, the byte form of the files it holds, and reading those
files back.
"""

from __future__ import annotations

import hashlib
import json
import os
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
    """The digest of a tree, and the changes it holds that no commit holds."""

    digest: str
    uncommitted: tuple[str, ...]


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
    for rel in sorted(p for p in list_index_files(repo_root) if not _under(p, prefix)):
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
    return TreeDigest(digest=h.hexdigest(), uncommitted=uncommitted)


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
