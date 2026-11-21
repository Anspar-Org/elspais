# Implements: REQ-d00336-I, REQ-d00336-K, REQ-d00336-L, REQ-d00336-O
"""The review record: which code and test files await review after a change.

The record is a Markdown file committed with the work it describes. It holds
two tables. *Awaiting review* names each file that cites a changed requirement
or *Assertion* and that nobody has reviewed since. *Reviewed* holds each
review a person recorded: the change, the content of the changed requirement
or *Assertion* and of the file at the time, who reviewed it and when.

This module is the one place the record is read and written. The changed
command decides what goes into it; nothing else writes it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

RECORD_PATH = Path(".elspais/changes.md")

_TITLE = "# Change Reviews"
_INTRO = (
    "elspais writes this file. `elspais changed --write-record` names each code and test "
    "file that cites a changed requirement or *Assertion* and awaits review, and "
    "`elspais changed --review PATH` records a person's review of one. Commit it with "
    "the work it describes."
)
_AWAITING_HEADING = "## Awaiting review"
_REVIEWED_HEADING = "## Reviewed"
_AWAITING_COLUMNS = ("Change", "File", "Lines")
_REVIEWED_COLUMNS = ("Change", "Content", "File", "File content", "Reviewer", "Date")
_NONE = "None."


@dataclass(frozen=True)
class Awaiting:
    """A file that cites a changed requirement or *Assertion*, not yet reviewed."""

    change_id: str
    path: str
    lines: tuple[int, ...] = ()


@dataclass(frozen=True)
class Review:
    """A review a person recorded of one file for one change.

    ``content`` is the digest of the changed requirement or *Assertion* and
    ``file_content`` the digest of the file, each as it stood when the review
    was recorded.
    """

    change_id: str
    content: str
    path: str
    file_content: str
    reviewer: str
    date: str


@dataclass
class ReviewRecord:
    """What the record holds."""

    awaiting: list[Awaiting] = field(default_factory=list)
    reviews: list[Review] = field(default_factory=list)


class ReviewRecordError(ValueError):
    """The record does not read as the tables this module writes."""


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _is_rule(cells: list[str]) -> bool:
    return all(cell and set(cell) <= {"-", ":"} for cell in cells)


def _tables(text: str, path: Path) -> dict[str, list[list[str]]]:
    """The rows of the table beneath each heading of the record."""
    rows: dict[str, list[list[str]]] = {}
    heading: str | None = None
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("## "):
            heading = stripped
            rows.setdefault(heading, [])
            continue
        if not stripped.startswith("|") or heading is None:
            continue
        cells = _cells(stripped)
        if _is_rule(cells):
            continue
        rows[heading].append(cells)
        if len(rows[heading]) == 1:
            continue
        expected = len(rows[heading][0])
        if len(cells) != expected:
            raise ReviewRecordError(
                f"{path}:{number}: a row of {heading!r} has {len(cells)} cells where its "
                f"header has {expected}; correct the row or run `elspais changed --write-record`."
            )
    return rows


def _body(rows: list[list[str]], columns: tuple[str, ...], heading: str, path: Path) -> list:
    if not rows:
        return []
    header, *body = rows
    if tuple(header) != columns:
        raise ReviewRecordError(
            f"{path}: the table under {heading!r} has the columns {', '.join(header)}; "
            f"it must have {', '.join(columns)}."
        )
    return body


def read_record(repo_root: Path) -> ReviewRecord:
    """The record the repository holds; an empty one where it holds none.

    Raises:
        ReviewRecordError: The file exists and does not read as the record.
    """
    path = repo_root / RECORD_PATH
    if not path.is_file():
        return ReviewRecord()
    tables = _tables(path.read_text(encoding="utf-8"), path)
    record = ReviewRecord()
    for change_id, file_path, lines in _body(
        tables.get(_AWAITING_HEADING, []), _AWAITING_COLUMNS, _AWAITING_HEADING, path
    ):
        numbers = tuple(int(n) for n in lines.replace(",", " ").split() if n.isdigit())
        record.awaiting.append(Awaiting(change_id, file_path, numbers))
    for cells in _body(
        tables.get(_REVIEWED_HEADING, []), _REVIEWED_COLUMNS, _REVIEWED_HEADING, path
    ):
        record.reviews.append(Review(*cells))
    return record


def _table(columns: tuple[str, ...], rows: list[tuple[str, ...]]) -> list[str]:
    if not rows:
        return [_NONE]
    widths = [max(len(columns[i]), *(len(row[i]) for row in rows)) for i in range(len(columns))]

    def line(cells: tuple[str, ...]) -> str:
        return "| " + " | ".join(cell.ljust(widths[i]) for i, cell in enumerate(cells)) + " |"

    return [line(columns), line(tuple("-" * w for w in widths)), *(line(row) for row in rows)]


def render_record(record: ReviewRecord) -> str:
    """The record's text: the same record always renders to the same bytes."""
    awaiting = sorted(set(record.awaiting), key=lambda a: (a.change_id, a.path))
    reviews = sorted(set(record.reviews), key=lambda r: (r.change_id, r.path, r.date, r.reviewer))
    lines = [_TITLE, "", _INTRO, "", _AWAITING_HEADING, ""]
    lines += _table(
        _AWAITING_COLUMNS,
        [(a.change_id, a.path, ", ".join(str(n) for n in a.lines)) for a in awaiting],
    )
    lines += ["", _REVIEWED_HEADING, ""]
    lines += _table(
        _REVIEWED_COLUMNS,
        [(r.change_id, r.content, r.path, r.file_content, r.reviewer, r.date) for r in reviews],
    )
    return "\n".join(lines) + "\n"


def write_record(repo_root: Path, record: ReviewRecord) -> Path:
    """Write *record* to the repository's record file and return its path."""
    path = repo_root / RECORD_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_record(record), encoding="utf-8")
    return path
