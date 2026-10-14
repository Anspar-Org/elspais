"""Fetch the baseline a full CI run of main published (`baseline fetch`).

A full CI run of main uploads its baseline as the artifact
`tia-baseline-<commit>`. This module finds the newest such artifact for a
commit on main that this worktree's HEAD descends from, checks that it fits
this worktree, and installs it where the selector reads the baseline. A
worktree's own baseline is kept while it is usable, because a full run of the
worktree's own tree is closer to its code than any run of main.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import tempfile
import zipfile
from collections.abc import Callable

from .baseline import BASELINE_JSON, BaselineError, _remove_superseded, load_baseline
from .gitio import git

ARTIFACT_PREFIX = "tia-baseline-"
# How many commits of main, back from the merge base, are searched for one.
SEARCH_DEPTH = 50
# The repository's artifacts are listed newest first, a page at a time. A
# baseline recorded daily stays within the first few pages.
PAGE_SIZE = 100
MAX_PAGES = 5


class FetchError(Exception):
    pass


def run_gh(args: list[str], root: str) -> bytes:
    """Run `gh` in *root* and return its standard output."""
    try:
        proc = subprocess.run(["gh", *args], cwd=root, capture_output=True)
    except FileNotFoundError as exc:
        raise FetchError("the GitHub CLI `gh` is not on PATH") from exc
    if proc.returncode != 0:
        detail = proc.stderr.decode(errors="replace").strip()
        raise FetchError(f"gh {' '.join(args)}: {detail}")
    return proc.stdout


def fetch_baseline(
    root: str,
    dest: str,
    *,
    current_env: dict,
    max_age_days: float | None,
    force: bool = False,
    remote: str = "origin",
    branch: str = "main",
    depth: int = SEARCH_DEPTH,
    gh: Callable[[list[str], str], bytes] = run_gh,
) -> str:
    """Install the newest usable CI baseline into *dest*; return what happened.

    Raises FetchError where nothing was installed and the local baseline is
    unusable, naming the cause.
    """

    def usable(path: str) -> None:
        load_baseline(
            path,
            root,
            current_env=current_env,
            on_environment_change="full",
            max_age_days=max_age_days,
        ).close()

    if not force:
        try:
            usable(dest)
            return f"kept the usable baseline in {dest}"
        except BaselineError:
            pass

    # Without the commit the baseline names, its tree cannot be diffed. A
    # failed fetch leaves the remote-tracking branch as it was, which may
    # still hold that commit.
    git(root, "fetch", "--quiet", remote, branch, check=False)
    base = git(root, "merge-base", "HEAD", f"{remote}/{branch}", check=False).strip()
    if not base:
        raise FetchError(f"HEAD shares no history with {remote}/{branch}")
    commits = git(root, "rev-list", "--first-parent", f"--max-count={depth}", base).split()

    published = _published_baselines(root, set(commits), gh)
    found = next((sha for sha in commits if sha in published), None)
    if found is None:
        raise FetchError(
            f"CI published no baseline for the last {len(commits)} commits of "
            f"{remote}/{branch} that HEAD descends from"
        )
    sha, artifact = found, published[found]

    archive = gh(["api", f"repos/{{owner}}/{{repo}}/actions/artifacts/{artifact['id']}/zip"], root)
    parent = os.path.dirname(os.path.abspath(dest))
    os.makedirs(parent, exist_ok=True)
    staging = tempfile.mkdtemp(prefix=f".{os.path.basename(dest)}.fetch-", dir=parent)
    try:
        _extract(archive, staging)
        try:
            usable(staging)
        except BaselineError as exc:
            raise FetchError(
                f"the baseline CI published for {sha[:12]} does not fit this worktree "
                f"({exc.kind}: {exc.detail})"
            ) from exc
        _install(staging, dest)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return f"installed the baseline CI published for {sha[:12]} in {dest}"


def _published_baselines(
    root: str, wanted: set[str], gh: Callable[[list[str], str], bytes]
) -> dict[str, dict]:
    """The unexpired baseline artifacts naming a commit in *wanted*, by commit."""
    found: dict[str, dict] = {}
    for page in range(1, MAX_PAGES + 1):
        query = f"repos/{{owner}}/{{repo}}/actions/artifacts?per_page={PAGE_SIZE}&page={page}"
        artifacts = json.loads(gh(["api", query], root)).get("artifacts", [])
        for a in artifacts:
            sha = a.get("name", "").removeprefix(ARTIFACT_PREFIX)
            if a.get("name", "").startswith(ARTIFACT_PREFIX) and sha in wanted:
                if not a.get("expired") and sha not in found:
                    found[sha] = a
        if len(artifacts) < PAGE_SIZE:
            break
    return found


def _extract(archive: bytes, into: str) -> None:
    with zipfile.ZipFile(io.BytesIO(archive)) as zf:
        for name in zf.namelist():
            if os.path.isabs(name) or ".." in name.split("/"):
                raise FetchError(f"the artifact holds an unsafe path: {name}")
        zf.extractall(into)


def _install(staging: str, dest: str) -> None:
    """Move the coverage file into *dest* first and baseline.json last, so a
    reader sees the previous baseline or the new one, never a mixture."""
    with open(os.path.join(staging, BASELINE_JSON), encoding="utf-8") as fh:
        cov_name = json.load(fh)["coverage"]["file"]
    os.makedirs(dest, exist_ok=True)
    os.replace(os.path.join(staging, cov_name), os.path.join(dest, cov_name))
    os.replace(os.path.join(staging, BASELINE_JSON), os.path.join(dest, BASELINE_JSON))
    _remove_superseded(dest, keep=cov_name)
