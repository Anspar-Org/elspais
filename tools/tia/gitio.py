"""Baseline-vs-current file contents through git.

The baseline is identified by a git *tree* (``git write-tree`` at the time
the baseline run started) plus an overlay of the files that differed from it
in the worktree (``dirty``: path -> blob id, or None for a deleted file). That
pair names exactly the bytes the baseline run tested, whether it ran on a
clean commit (CI) or on a staged tree in a pre-commit hook.

The current side is always the working tree, untracked files included: the
change under test is everything between what the baseline tested and what is
on disk now.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass


class GitError(RuntimeError):
    pass


def git(root: str, *args: str, binary: bool = False, check: bool = True):
    proc = subprocess.run(["git", *args], cwd=root, capture_output=True)
    if check and proc.returncode != 0:
        raise GitError(f"git {' '.join(args)}: {proc.stderr.decode(errors='replace').strip()}")
    return proc.stdout if binary else proc.stdout.decode("utf-8", errors="surrogateescape")


def object_exists(root: str, oid: str, kind: str) -> bool:
    proc = subprocess.run(
        ["git", "cat-file", "-e", f"{oid}^{{{kind}}}"], cwd=root, capture_output=True
    )
    return proc.returncode == 0


def repo_root(start: str = ".") -> str:
    return git(start, "rev-parse", "--show-toplevel").strip()


@dataclass(frozen=True)
class FileChange:
    path: str
    status: str  # "added" | "deleted" | "modified"
    base_blob: str | None
    current_blob: str | None


class BaselineTree:
    """Reads files as the baseline run saw them."""

    def __init__(self, root: str, tree: str, dirty: dict[str, str | None]):
        self.root = root
        self.tree = tree
        self.dirty = dict(dirty)
        self._entries: dict[str, str] | None = None

    def entries(self) -> dict[str, str]:
        """path -> blob id for every file in the baseline tree, overlay applied."""
        if self._entries is None:
            out = git(self.root, "ls-tree", "-r", "-z", "--full-tree", self.tree)
            entries = {}
            for rec in out.split("\0"):
                if not rec:
                    continue
                meta, path = rec.split("\t", 1)
                mode, kind, oid = meta.split()
                if kind == "blob":
                    entries[path] = oid
            for path, oid in self.dirty.items():
                if oid is None:
                    entries.pop(path, None)
                else:
                    entries[path] = oid
            self._entries = entries
        return self._entries

    def blob(self, path: str) -> str | None:
        return self.entries().get(path)

    def read(self, path: str) -> bytes | None:
        oid = self.blob(path)
        if oid is None:
            return None
        return git(self.root, "cat-file", "blob", oid, binary=True)


def hash_symlink(root: str, path: str, write: bool = False) -> str:
    """The blob git stores for a symbolic link: the bytes of its target."""
    target = os.fsencode(os.readlink(os.path.join(root, path)))
    args = ["git", "hash-object", "--no-filters", "--stdin"] + (["-w"] if write else [])
    out = subprocess.run(args, cwd=root, input=target, capture_output=True, check=True).stdout
    return out.decode().strip()


def hash_worktree_files(root: str, paths: list[str]) -> dict[str, str | None]:
    """Blob ids of worktree files (None for absent ones), as git would hash them."""
    links = [p for p in paths if os.path.islink(os.path.join(root, p))]
    present = [p for p in paths if p not in links and os.path.isfile(os.path.join(root, p))]
    result: dict[str, str | None] = dict.fromkeys(paths)
    for p in links:
        result[p] = hash_symlink(root, p)
    # --no-filters keeps this a pure function of the bytes on disk; the
    # baseline's dirty blobs were hashed the same way.
    for i in range(0, len(present), 500):
        chunk = present[i : i + 500]
        out = git(root, "hash-object", "--no-filters", "--", *chunk).split()
        for p, oid in zip(chunk, out, strict=True):
            result[p] = oid
    return result


def changed_files(base: BaselineTree) -> list[FileChange]:
    """Every file whose current bytes differ from the baseline's."""
    root = base.root
    tracked = git(root, "diff", "--name-only", "--no-renames", "-z", base.tree, "--").split("\0")
    untracked = git(root, "ls-files", "--others", "--exclude-standard", "-z").split("\0")
    # "dir/" entries are embedded repositories, not files of this tree.
    candidates = sorted(
        {p for p in tracked + untracked + list(base.dirty) if p and not p.endswith("/")}
    )
    current = hash_worktree_files(root, candidates)
    changes = []
    for path in candidates:
        b, c = base.blob(path), current[path]
        if b == c:
            continue
        status = "added" if b is None else "deleted" if c is None else "modified"
        changes.append(FileChange(path, status, b, c))
    return changes


def read_current(root: str, path: str) -> bytes | None:
    try:
        with open(os.path.join(root, path), "rb") as fh:
            return fh.read()
    except (FileNotFoundError, IsADirectoryError):
        return None
