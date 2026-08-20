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


def namespace_for(name: str) -> str:
    """Return the namespace a repo named `name` declares by default.

    A namespace answers whose identifiers these are, so no two repositories
    in one federation may declare the same one.  Deriving it from the repo's
    name gives every repo a distinct namespace without each test having to
    invent one.
    """
    return name.upper()


def make_repo(
    base: Path,
    name: str,
    *,
    namespace: str | None = None,
    associates: dict[str, str] | None = None,
    associate_namespaces: dict[str, str] | None = None,
    req_id: str | None = None,
    config_text: str | None = None,
    origin: str | None = None,
    dirname: str | None = None,
) -> Path:
    """Create a minimal, valid, git-backed elspais repo under `base`.

    `namespace` defaults to `namespace_for(name)` and `req_id` to that
    namespace's first dev identifier, so repos built for one federation are
    distinct by construction.  `associates` maps an associate name to the
    path recorded in the config (relative to this repo's root).
    `associate_namespaces` overrides the namespace recorded for a named
    associate, which otherwise derives from the associate's name the same
    way.  `config_text` replaces the generated TOML wholesale, for the
    malformed-config cases.

    A `req_id` outside the repo's own namespace is refused: the requirement
    would not parse under the repo's canonical pattern, and the repo would
    silently contribute nothing.
    """
    namespace = namespace or namespace_for(name)
    req_id = req_id or f"{namespace}-d00001"
    # Only the generated config is answered for here; `config_text` carries
    # its own identifier grammar, including one that does not spell the
    # namespace into the identifier at all.
    if config_text is None and not req_id.startswith(f"{namespace}-"):
        raise ValueError(
            f"req_id '{req_id}' is outside repo '{name}' namespace '{namespace}'; "
            f"it would not parse and the repo would hold no requirements."
        )

    repo = base / (dirname or name)
    (repo / "spec").mkdir(parents=True)

    if config_text is None:
        text = _MIN_TOML.format(name=name, namespace=namespace)
        for assoc_name, assoc_path in (associates or {}).items():
            assoc_ns = (associate_namespaces or {}).get(assoc_name) or namespace_for(assoc_name)
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
