# Implements: REQ-d00212-Q+W, REQ-p00015-H, REQ-d00241-G
"""The one place a scan decides which files it reads.

A scan asks one question: which files, under which directories, does this kind
read? Before this module the answer came from two mechanisms that disagreed --
one matched a pattern against the absolute path, the other against the path
relative to the directory being scanned -- so one pattern got two judgements
and neither matched what the documentation promised.

The rules, in full:

* A directory is named by its path from the REPOSITORY ROOT. ``stuff/things``
  names that directory and nothing else. A bare ``junk`` names ``junk`` at the
  root of the repository, NOT a directory called ``junk`` at some depth.
* ``**`` stands for zero or more directories, so ``**/junk`` names a directory
  called ``junk`` anywhere, and ``stuff/**`` names everything under ``stuff``.
* A file is named by a glob over its NAME: ``*.md``, ``README.md``. A file
  pattern says nothing about where the file sits; the directory rules say that.
* A directory a skip pattern names is not descended into. Nothing inside it is
  opened, so nothing downstream can report on it (REQ-p00015-H).
"""

from __future__ import annotations

import fnmatch
import os
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


def _segments(pattern: str) -> list[str]:
    """A directory pattern as its parts, with empties dropped."""
    return [seg for seg in PurePosixPath(pattern.strip("/")).parts if seg not in ("", ".")]


def _match_segments(pattern: Sequence[str], path: Sequence[str]) -> bool:
    """Whether *path* is what *pattern* names, ``**`` spanning directories."""
    if not pattern:
        return not path
    head = pattern[0]
    if head == "**":
        # Zero or more directories, so try every division of what is left.
        return any(_match_segments(pattern[1:], path[i:]) for i in range(len(path) + 1))
    if not path:
        return False
    if not fnmatch.fnmatch(path[0], head):
        return False
    return _match_segments(pattern[1:], path[1:])


def dir_is_skipped(relative_dir: str, skip_dirs: Iterable[str]) -> bool:
    """Whether a repo-relative directory is one the configuration skips."""
    parts = _segments(relative_dir)
    return any(_match_segments(_segments(pattern), parts) for pattern in skip_dirs)


def within_skipped_dir(relative_path: str, skip_dirs: Iterable[str]) -> bool:
    """Whether any directory ABOVE *relative_path* is one the walk would skip.

    A walk prunes a skipped directory and so never reaches what is under it.
    A caller naming a file directly reaches it without walking, so it asks this
    instead: a skipped directory excludes everything beneath it however the
    file was arrived at, not only what sits immediately inside it.
    """
    parts = _segments(relative_path)
    return any(dir_is_skipped("/".join(parts[:i]), skip_dirs) for i in range(1, len(parts)))


def file_is_skipped(name: str, skip_files: Iterable[str]) -> bool:
    """Whether a file's NAME is one the configuration skips.

    A skipped file is passed over in SILENCE. Nothing downstream may report it
    (REQ-d00241-G), which is what makes this a different question from whether
    the kind's patterns select it.
    """
    return any(fnmatch.fnmatch(name, pattern) for pattern in skip_files)


def file_is_included(name: str, relative_to_scan_dir: str, include_files: Iterable[str]) -> bool:
    """Whether this kind's declared patterns select the file.

    Matched against the file's NAME and against its path WITHIN the scanned
    directory, so ``*.py`` selects at any depth and ``api/*.py`` selects inside
    a subdirectory of the directory being scanned.

    The frame is the scanned directory and not the repository, because that is
    what a selection is for: a kind declares the directories it scans, and
    these patterns choose among what those directories hold. A skip pattern
    answers a different question -- which paths in the REPOSITORY are not to be
    entered -- so it is written from the repository root instead. The two are
    not interchangeable and are deliberately not spelled alike.
    """
    return any(
        fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(relative_to_scan_dir, pattern)
        for pattern in include_files
    )


@dataclass(frozen=True)
class Selection:
    """What one walk found, told apart by what the caller owes each file.

    Three outcomes, not two, because two requirements turn on the difference
    between a file passed over in silence and one merely not selected:

    ``selected``
        The kind's patterns select it and no skip pattern names it. Read it.
    ``declined``
        No skip pattern names it, and the kind's patterns do not select it.
        The walk reached it, so a *Traceability* keyword in it is reported
        (REQ-d00241-F). The caller decides what to ask of such a file; the
        walk does not read it.

    A file a skip pattern names is in NEITHER set. It was never opened and is
    reported nowhere (REQ-p00015-H, REQ-d00241-G).
    """

    selected: frozenset[Path]
    declined: frozenset[Path]


# Implements: REQ-p00015-H
def select_files(
    repo_root: Path,
    scan_dirs: Sequence[str],
    skip_dirs: Sequence[str],
    skip_files: Sequence[str],
    include_files: Sequence[str],
    recursive: bool = True,
) -> Selection:
    """What this kind reads, and what it merely declined, as absolute paths.

    Args:
        repo_root: The repository. Every directory pattern is read from here.
        scan_dirs: The directories this kind scans, repo-relative.
        skip_dirs: Directories not to enter, repo-relative.
        skip_files: Globs over a file's name. A file matching one is not read.
        include_files: Globs selecting among what the scanned directories
            hold, matched against a file's name and its path within the
            directory being scanned.
        recursive: Whether to descend below each scanned directory.

    Returns:
        A :class:`Selection`. Sets, so one file is answered for once however
        many declared directories contain it.
    """
    root = Path(repo_root).resolve()
    selected: set[Path] = set()
    declined: set[Path] = set()

    for scan_dir in scan_dirs:
        start = (root / scan_dir).resolve()
        if not start.is_dir():
            continue
        for dir_path, dir_names, file_names in os.walk(start):
            here = Path(dir_path)
            try:
                here_rel = here.relative_to(root).as_posix()
            except ValueError:
                continue
            # The directory a walk starts at is a directory like any other. A
            # pattern naming it skips it and everything under it, so a scan
            # directory a skip pattern also names reads nothing.
            if dir_is_skipped(here_rel, skip_dirs):
                dir_names[:] = []
                continue
            # Prune before descending: a skipped directory is not entered, so
            # nothing inside it is opened or listed.
            dir_names[:] = sorted(
                d
                for d in dir_names
                for rel in [f"{here_rel}/{d}" if here_rel != "." else d]
                if not dir_is_skipped(rel, skip_dirs)
            )
            if not recursive:
                dir_names[:] = []
            for name in file_names:
                # Asked in this order deliberately. A skip pattern answers
                # first and ends the question: such a file is neither read nor
                # reported. Only what survives it can be declined.
                if file_is_skipped(name, skip_files):
                    continue
                rel_to_scan = (here / name).relative_to(start).as_posix()
                if file_is_included(name, rel_to_scan, include_files):
                    selected.add(here / name)
                else:
                    declined.add(here / name)
    return Selection(selected=frozenset(selected), declined=frozenset(declined))
