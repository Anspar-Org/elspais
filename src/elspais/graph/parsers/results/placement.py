"""Where a path a test target's data records lies in the repository.

A results or coverage artifact records source paths relative to an origin:
the repository root or the target's working directory, as its format or the
target declares. Reading such a path, and choosing the origin that applies,
each have one form here, read by the build and by the retained coverage a
run keeps.
"""

from __future__ import annotations

import os
from pathlib import Path


# Implements: REQ-d00327-C
def placed_in_repo(path: str, origin_dir: Path, repo_root: Path) -> str | None:
    """*path* as a repo-relative POSIX path, read from *origin_dir*, or None.

    A relative path is read from *origin_dir*, the origin that applies to the
    data that recorded it. An absolute path is read as it stands. A path that
    lands outside the repository has no repo-relative form.

    The path is placed in the repository as written first, and through
    symbolic links second: a tool may record either spelling.
    """
    root = Path(repo_root).absolute()
    named = Path(os.path.normpath(Path(origin_dir).absolute() / path))
    try:
        rel = named.relative_to(Path(os.path.normpath(root)))
    except ValueError:
        try:
            rel = named.resolve().relative_to(root.resolve())
        except ValueError:
            return None
    return rel.as_posix()


# Implements: REQ-d00327-A+B+F
def origin_dir(
    spec, declared: str, working_dir: Path, repo_root: Path, *, foreign: bool
) -> tuple[str, Path]:
    """The origin that applies to a target's data, and the directory it names.

    The target's declaration replaces the reporter's, except for data in a
    format other than the target's own (an *Evidence Snapshot*), which is
    read by that format's declaration alone.
    """
    from elspais.config.schema import PATH_ORIGIN_CWD

    origin = spec.path_origin if foreign else (declared or spec.path_origin)
    return origin, (working_dir if origin == PATH_ORIGIN_CWD else repo_root)
