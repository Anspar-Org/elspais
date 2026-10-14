"""Line coverage: the one place a coverage file is read, recorded, judged and reported.

A test tool writes its coverage file in the target's output area. When a run
finishes, the measurement is read once and kept in the target's coverage
record, stamped per source file with the content it measured and the run that
measured it. The graph build and the next run's retention read the record;
the reports other tools read are rendered from it.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

RECORD_NAME = ".elspais-coverage.json"
REPORT_NAME = ".elspais-coverage.info"
RECORD_VERSION = 1


class CoverageUnreadable(Exception):
    """A coverage file or record that cannot be read; the message names the remedy."""


@dataclass(frozen=True)
class FileCoverage:
    """One source file's line coverage, and the content and runs it describes."""

    hits: dict[int, int]
    executable: int
    contexts: dict[int, tuple[str, ...]] = field(default_factory=dict)
    digest: str = ""
    measured_in: tuple[dict, ...] = ()
    source_analysed: bool = True


Record = dict[str, FileCoverage]


# Implements: REQ-d00254-F
def read_tool_coverage(repo_root: Path, config: Any, target: Any) -> dict[str, dict]:
    """The target's own coverage file, read in its declared format, keyed repo-relative."""
    from elspais.graph.factory import context_placer
    from elspais.graph.parsers.results.placement import origin_dir, placed_in_repo
    from elspais.graph.parsers.results.registry import get_reporter
    from elspais.utilities.fingerprint import target_folder

    root = Path(repo_root).resolve()
    path = target_folder(root, config, target.name) / target.coverage
    if not path.is_file():
        return {}
    spec = get_reporter(target.coverage_format)
    reader = spec.parser_factory()
    content = "" if getattr(reader, "binary", False) else path.read_text(encoding="utf-8")
    try:
        measured = reader.parse(content, str(path))
    except ImportError as exc:
        raise CoverageUnreadable(
            f"target {target.name!r}: {target.coverage_format} coverage needs the "
            f"'coverage' extra: pip install elspais[coverage] ({exc})"
        ) from exc
    cwd = (root / target.cwd) if target.cwd else root
    _origin, frame = origin_dir(spec, target.coverage_origin, cwd, root, foreign=False)
    place_contexts = context_placer(target, cwd, root)
    placed: dict[str, dict] = {}
    for source, data in measured.items():
        rel = placed_in_repo(source, frame, root)
        if rel is None:
            continue
        if data.get("contexts"):
            data = {**data, "contexts": place_contexts(data["contexts"])}
        placed[rel] = data
    return placed


# Implements: REQ-d00333-J
def measure(repo_root: Path, config: Any, target: Any, run: dict) -> Record:
    """This run's measurement as record entries, each stamped with its file's digest now."""
    from elspais.utilities.fingerprint import file_digest

    root = Path(repo_root).resolve()
    record: Record = {}
    for rel, data in read_tool_coverage(root, config, target).items():
        source = root / rel
        if not source.is_file():
            continue
        record[rel] = FileCoverage(
            hits={int(n): int(h) for n, h in (data.get("line_coverage") or {}).items()},
            executable=int(data.get("executable_lines", 0)),
            contexts={int(n): tuple(c) for n, c in (data.get("contexts") or {}).items()},
            digest=file_digest(source),
            measured_in=(run,),
            source_analysed=bool(data.get("source_analysed", True)),
        )
    return record


# Implements: REQ-d00333-J
def current(record: Record, repo_root: Path) -> Record:
    """The entries whose source file still holds the content that was measured."""
    from elspais.utilities.fingerprint import file_digest

    root = Path(repo_root).resolve()
    kept: Record = {}
    for rel, entry in record.items():
        source = root / rel
        if source.is_file() and file_digest(source) == entry.digest:
            kept[rel] = entry
    return kept


def _merge_one(a: FileCoverage, b: FileCoverage) -> FileCoverage:
    hits = dict(a.hits)
    for line, count in b.hits.items():
        hits[line] = max(hits.get(line, 0), count)
    contexts = {line: tuple(names) for line, names in a.contexts.items()}
    for line, names in b.contexts.items():
        contexts[line] = tuple(sorted(set(contexts.get(line, ())) | set(names)))
    runs = list(a.measured_in)
    runs.extend(r for r in b.measured_in if r not in runs)
    return FileCoverage(
        hits=hits,
        executable=max(a.executable, b.executable),
        contexts=contexts,
        digest=b.digest or a.digest,
        measured_in=tuple(runs),
        source_analysed=a.source_analysed and b.source_analysed,
    )


# Implements: REQ-d00334-A+B
def merge(a: Record, b: Record) -> Record:
    """Two records as one: per file, the larger hit count of each line."""
    out = dict(a)
    for rel, entry in b.items():
        out[rel] = _merge_one(out[rel], entry) if rel in out else entry
    return out


def _atomic_write(path: Path, text: str) -> Path:
    """Write *text* to *path* through a temporary file, so a reader sees one whole file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp, path)
    return path


# Implements: REQ-d00334-A
def write_record(folder: Path, record: Record) -> Path:
    """Write *record* into *folder*. Test names are stored once, in one table."""
    names = sorted({n for e in record.values() for c in e.contexts.values() for n in c})
    index = {n: i for i, n in enumerate(names)}
    files = {
        rel: {
            "hits": {str(n): h for n, h in sorted(e.hits.items())},
            "executable": e.executable,
            "contexts": {str(n): [index[x] for x in c] for n, c in sorted(e.contexts.items())},
            "digest": e.digest,
            "measured_in": list(e.measured_in),
            "source_analysed": e.source_analysed,
        }
        for rel, e in sorted(record.items())
    }
    text = json.dumps(
        {"version": RECORD_VERSION, "contexts": names, "files": files}, sort_keys=True
    )
    return _atomic_write(Path(folder) / RECORD_NAME, text + "\n")


# Implements: REQ-d00334-A
def read_record(folder: Path) -> Record | None:
    """The record in *folder*, or ``None`` where the folder holds none."""
    path = Path(folder) / RECORD_NAME
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise CoverageUnreadable(
            f"{path}: the coverage record does not parse ({exc}); run the target again"
        ) from exc
    if not isinstance(data, dict) or data.get("version") != RECORD_VERSION:
        raise CoverageUnreadable(
            f"{path}: the coverage record is of another version; run the target again"
        )
    names = data.get("contexts") or []
    return {
        rel: FileCoverage(
            hits={int(n): int(h) for n, h in f["hits"].items()},
            executable=int(f["executable"]),
            contexts={
                int(n): tuple(names[i] for i in c) for n, c in (f.get("contexts") or {}).items()
            },
            digest=f["digest"],
            measured_in=tuple(f.get("measured_in") or ()),
            source_analysed=bool(f.get("source_analysed", True)),
        )
        for rel, f in (data.get("files") or {}).items()
    }


# Implements: REQ-d00334-A+B
def render_lcov(record: Record) -> str:
    """*record* as an LCOV report, files sorted by path and lines ascending."""
    out: list[str] = []
    for rel, e in sorted(record.items()):
        out.append(f"SF:{rel}")
        for line, count in sorted(e.hits.items()):
            out.append(f"DA:{line},{count}")
        out.append(f"LF:{len(e.hits)}")
        out.append(f"LH:{sum(1 for c in e.hits.values() if c)}")
        out.append("end_of_record")
    return "".join(line + "\n" for line in out)


# Implements: REQ-d00334-A+B
def write_report(path: Path, record: Record) -> Path:
    """Write *record* as an LCOV report at *path*."""
    return _atomic_write(Path(path), render_lcov(record))
