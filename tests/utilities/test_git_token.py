# Verifies: REQ-d00297-D
"""Tests for carrying a credential on one git invocation and nowhere else.

The invariant is what these assert: after a push authenticated with a
supplied token, the token is in the argv of that one process and in no
environment, no configuration and no file the operation left behind.
"""

from __future__ import annotations

import base64
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

from elspais.utilities import git as git_mod
from elspais.utilities.git import push_branch, token_command_prefix

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
        pytest.param(TOKEN, None, id="no-remote"),
    ],
)
def test_nothing_is_carried_where_a_header_would_not_authenticate(
    token: str | None, remote_url: str | None
) -> None:
    """With no token, or a remote that authenticates by key, the command is
    left exactly as it was -- no empty header is invented for it."""
    assert token_command_prefix(token, remote_url) == []


# Verifies: REQ-d00297-D
def test_an_http_remote_carries_the_credential_as_a_one_command_override() -> None:
    """The credential travels as a per-command configuration override
    spelling the basic-auth pair git expects, so it lives for the length of
    that one process."""
    prefix = token_command_prefix(TOKEN, HTTPS_REMOTE)

    assert prefix[0] == "-c"
    assert len(prefix) == 2
    key, _, value = prefix[1].partition("=")
    assert key == "http.extraheader"
    encoded = value.removeprefix("AUTHORIZATION: basic ")
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
def test_a_pushed_credential_reaches_the_command_and_nothing_else(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A push authenticated with a supplied token puts the token in that one
    command's arguments, and leaves it out of the environment the command was
    given, out of the repository's configuration, and out of every file under
    its git directory."""
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
    assert any(encoded in arg for arg in argv), argv
    assert given_env is not None
    assert not any(TOKEN in value or encoded in value for value in given_env.values())

    assert not any(TOKEN in value for value in os.environ.values())

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
