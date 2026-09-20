# Verifies: REQ-d00297-D
"""Tests for carrying a credential on one git invocation and nowhere else.

The invariant is what these assert: after a push authenticated with a
supplied token, the token is readable only by the account that owns the git
child, and in particular is absent from the command line the operating
system publishes to every local account, from the repository's
configuration, and from every file the operation left behind.
"""

from __future__ import annotations

import base64
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

from elspais.utilities import git as git_mod
from elspais.utilities.git import push_branch, token_git_env

TOKEN = "s3cret-token-value"
HTTPS_REMOTE = "https://github.com/anspar/elspais.git"


# Verifies: REQ-d00297-D
@pytest.mark.parametrize(
    ("token", "remote_url"),
    [
        pytest.param(None, HTTPS_REMOTE, id="no-token"),
        pytest.param("", HTTPS_REMOTE, id="blank-token"),
        pytest.param(TOKEN, "git@github.com:anspar/elspais.git", id="ssh-remote"),
        pytest.param(TOKEN, "ssh://git@github.com/anspar/elspais", id="ssh-url-remote"),
        pytest.param(TOKEN, "http://github.com/anspar/elspais.git", id="plaintext-remote"),
        pytest.param(TOKEN, None, id="no-remote"),
    ],
)
def test_nothing_is_carried_where_a_header_would_not_authenticate_in_confidence(
    token: str | None, remote_url: str | None
) -> None:
    """With no token, a remote that authenticates by key, or a remote that
    would carry the header in clear, the invocation is left exactly as it
    was -- no header is invented for it."""
    assert token_git_env(token, remote_url) == {}


# Verifies: REQ-d00297-D
def test_an_https_remote_carries_the_credential_on_the_child_environment() -> None:
    """The credential travels as a configuration override on the child's own
    environment, spelling the basic-auth pair git expects, so it is readable
    by the account owning that one process and by nobody else."""
    entries = token_git_env(TOKEN, HTTPS_REMOTE)

    assert entries["GIT_CONFIG_COUNT"] == "1"
    assert entries["GIT_CONFIG_KEY_0"] == "http.extraheader"
    encoded = entries["GIT_CONFIG_VALUE_0"].removeprefix("AUTHORIZATION: basic ")
    assert base64.b64decode(encoded).decode("utf-8") == f"x-access-token:{TOKEN}"


def _init_repo_with_remote(root: Path, env: dict[str, str]) -> None:
    """A real repository whose origin is an https GitHub URL."""
    subprocess.run(["git", "init", "-q", str(root)], check=True, env=env, capture_output=True)
    subprocess.run(
        ["git", "remote", "add", "origin", HTTPS_REMOTE],
        cwd=root,
        check=True,
        env=env,
        capture_output=True,
    )


# Verifies: REQ-d00297-D
def test_a_pushed_credential_is_absent_from_the_published_command_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A push authenticated with a supplied token leaves the token out of
    that command's arguments -- which the operating system publishes to every
    local account -- out of this process's environment, out of the
    repository's configuration, and out of every file under its git
    directory, while the child that needs it is given it."""
    env = git_mod._clean_git_env()
    root = tmp_path / "repo"
    root.mkdir()
    _init_repo_with_remote(root, env)

    real_run = subprocess.run
    pushes: list[tuple[list[str], dict[str, str] | None]] = []

    def fake_run(cmd: Any, **kwargs: Any) -> Any:
        """Run everything for real except the push, which never leaves here."""
        if isinstance(cmd, list) and "push" in cmd:
            pushes.append((list(cmd), kwargs.get("env")))
            return subprocess.CompletedProcess(cmd, 1, "", "remote rejected")
        return real_run(cmd, **kwargs)

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = push_branch(root, "feature", token=TOKEN)
    monkeypatch.undo()

    assert result["success"] is False  # No network: the outcome is not the point.
    (argv, given_env) = pushes[0]
    encoded = base64.b64encode(f"x-access-token:{TOKEN}".encode()).decode("ascii")

    assert not any(TOKEN in arg or encoded in arg for arg in argv), argv

    assert given_env is not None
    assert given_env["GIT_CONFIG_VALUE_0"] == f"AUTHORIZATION: basic {encoded}"

    assert not any(TOKEN in value for value in os.environ.values())
    assert "GIT_CONFIG_VALUE_0" not in os.environ

    config = real_run(
        ["git", "config", "--list", "--show-origin"],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert TOKEN not in config.stdout
    assert encoded not in config.stdout

    for path in (root / ".git").rglob("*"):
        if path.is_file():
            content = path.read_bytes()
            assert TOKEN.encode() not in content, path
            assert encoded.encode() not in content, path
