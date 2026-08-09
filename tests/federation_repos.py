"""On-disk repository fixtures for federation tests.

One builder for every test that needs a real, git-backed elspais repository
tree, so the shape a federation is exercised against is the same everywhere.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

_MIN_TOML = """version = 3

[project]
name = "{name}"
namespace = "{namespace}"

[levels.prd]
rank = 1
implements = []

[levels.dev]
rank = 2
implements = ["prd", "dev"]
"""

_SPEC = """# Spec for {name}

## {req_id}: A thing in {name}

**Status**: active

The system shall do a thing.

*End*
"""


def _git_env():
    env = os.environ.copy()
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["HOME"] = env.get("HOME", "/tmp")
    env.pop("GIT_DIR", None)
    env.pop("GIT_WORK_TREE", None)
    return env


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        env=_git_env(),
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def make_repo(
    base: Path,
    name: str,
    *,
    namespace: str = "REQ",
    associates: dict[str, str] | None = None,
    associate_namespaces: dict[str, str] | None = None,
    req_id: str = "REQ-d00001",
    config_text: str | None = None,
    origin: str | None = None,
    dirname: str | None = None,
) -> Path:
    """Create a minimal, valid, git-backed elspais repo under `base`.

    `associates` maps an associate name to the path recorded in the config
    (relative to this repo's root).  `associate_namespaces` overrides the
    namespace recorded for a named associate, which otherwise repeats this
    repo's own.  `config_text` replaces the generated TOML wholesale, for the
    malformed-config cases.
    """
    repo = base / (dirname or name)
    (repo / "spec").mkdir(parents=True)

    if config_text is None:
        text = _MIN_TOML.format(name=name, namespace=namespace)
        for assoc_name, assoc_path in (associates or {}).items():
            assoc_ns = (associate_namespaces or {}).get(assoc_name, namespace)
            text += (
                f'\n[associates.{assoc_name}]\npath = "{assoc_path}"\nnamespace = "{assoc_ns}"\n'
            )
    else:
        text = config_text
    (repo / ".elspais.toml").write_text(text, encoding="utf-8")
    (repo / "spec" / "reqs.md").write_text(_SPEC.format(name=name, req_id=req_id), encoding="utf-8")

    _git(repo.parent, "init", "-b", "main", str(repo))
    _git(repo, "config", "user.email", "test@test.com")
    _git(repo, "config", "user.name", "Test")
    if origin is not None:
        _git(repo, "remote", "add", "origin", origin)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "init")
    return repo
