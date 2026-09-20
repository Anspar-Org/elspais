# Verifies: REQ-d00297-A+B+C+E
"""Tests for POST /api/git/pr, the route that proposes a pushed branch.

The route is exercised directly against a request built here, with the git
helpers it reads the repository through replaced: what is under test is the
decision the route reaches -- which refusals it makes and what they name,
whose credential it acts with, and which branch it proposes onto -- not
git's own answers.
"""

from __future__ import annotations

import asyncio
import io
import json
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from starlette.datastructures import Headers

from elspais.server import proxy_trust
from elspais.server.proxy_trust import GIT_TOKEN_HEADER, SECRET_HEADER
from elspais.server.routes_git import api_git_pr
from elspais.utilities import git as git_mod

PROXY_SECRET = "shared-with-the-hub"
ENV_TOKEN = "token-held-by-the-server"
SUPPLIED_TOKEN = "token-sent-with-the-request"
CREATED = {"html_url": "https://github.com/anspar/elspais/pull/9", "number": 9}


class _Opener:
    """An opener answering each call from a script, recording what it was sent."""

    def __init__(self, *answers: Any) -> None:
        self._answers = list(answers)
        self.requests: list[urllib.request.Request] = []

    def __call__(self, request: urllib.request.Request, timeout: float) -> Any:
        self.requests.append(request)
        answer = self._answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return SimpleNamespace(read=lambda payload=answer: json.dumps(payload).encode("utf-8"))


def _http_error(code: int, payload: Any) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        url="https://api.github.com/repos/anspar/elspais/pulls",
        code=code,
        msg="rejected",
        hdrs=None,  # type: ignore[arg-type]
        fp=io.BytesIO(json.dumps(payload).encode("utf-8")),
    )


def _request(
    body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    opener: Any = None,
) -> SimpleNamespace:
    """A request as the route reads one: headers, a JSON body, and the state."""
    state = SimpleNamespace(repo_root=Path("/workspace/repo"), config={"project": {"name": "p"}})

    async def _json() -> dict[str, Any]:
        return body or {}

    return SimpleNamespace(
        headers=Headers(headers or {}),
        json=_json,
        app=SimpleNamespace(state=SimpleNamespace(app_state=state, github_opener=opener)),
    )


def _call(request: SimpleNamespace) -> tuple[int, dict[str, Any]]:
    """The status and body the route answered with."""
    response = asyncio.run(api_git_pr(request))  # type: ignore[arg-type]
    return response.status_code, json.loads(bytes(response.body).decode("utf-8"))


@pytest.fixture
def repo(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """A pushed branch on a GitHub remote, with no credential in the environment.

    Each value is what the corresponding git helper answers; a test changes
    one to describe the repository it is about.
    """
    answers: dict[str, Any] = {
        "branch": "feature",
        "remote_url": "https://github.com/anspar/elspais.git",
        "ahead": 0,
        "default_branch": "trunk",
    }
    monkeypatch.setattr(git_mod, "get_current_branch", lambda root: answers["branch"])
    monkeypatch.setattr(git_mod, "get_remote_url", lambda root, *a, **k: answers["remote_url"])
    monkeypatch.setattr(git_mod, "unpushed_commit_count", lambda root, b, **k: answers["ahead"])
    monkeypatch.setattr(
        git_mod, "remote_default_branch", lambda root, *a, **k: answers["default_branch"]
    )
    monkeypatch.setattr(proxy_trust, "_SECRET", PROXY_SECRET)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setenv("GH_TOKEN", ENV_TOKEN)
    return answers


@pytest.fixture
def no_credential_anywhere(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neither the environment nor a credential helper can supply a token.

    The helper is made unreachable rather than merely unconfigured: a machine
    that really can mint one would let the route succeed for the wrong reason.
    """
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    def no_gh(*args: Any, **kwargs: Any) -> Any:
        raise FileNotFoundError("gh")

    monkeypatch.setattr(subprocess, "run", no_gh)


# Verifies: REQ-d00297-A
def test_a_pushed_branch_is_proposed_and_reported_as_a_new_pull_request(
    repo: dict[str, Any],
) -> None:
    """The route opens the pull request and answers with the one it created."""
    opener = _Opener(CREATED)
    status, body = _call(_request({"title": "A proposal", "body": "Why"}, opener=opener))

    assert status == 200
    assert body == {
        "success": True,
        "url": CREATED["html_url"],
        "number": 9,
        "existing": False,
    }
    payload = json.loads(opener.requests[0].data.decode("utf-8"))
    assert payload["head"] == "feature"
    assert payload["title"] == "A proposal"


# Verifies: REQ-d00297-E
def test_an_open_pull_request_for_the_branch_is_the_answer_not_a_refusal(
    repo: dict[str, Any],
) -> None:
    """A branch already proposed is reported as that proposal, with success."""
    existing = {"html_url": "https://github.com/anspar/elspais/pull/2", "number": 2}
    opener = _Opener(_http_error(422, {"message": "Validation Failed"}), [existing])

    status, body = _call(_request({}, opener=opener))

    assert status == 200
    assert body == {
        "success": True,
        "url": existing["html_url"],
        "number": 2,
        "existing": True,
    }


# Verifies: REQ-d00297-B
def test_no_usable_credential_is_refused_naming_what_to_supply(
    repo: dict[str, Any], no_credential_anywhere: None
) -> None:
    """With nothing to act as, the route refuses and names each way of
    supplying a credential rather than acting as the serving machine."""
    status, body = _call(_request({}, opener=_Opener(CREATED)))

    assert status == 400
    assert body["success"] is False
    assert "GH_TOKEN" in body["error"]
    assert "GITHUB_TOKEN" in body["error"]
    assert "gh auth login" in body["error"]


# Verifies: REQ-d00297-C
@pytest.mark.parametrize(
    ("condition", "value", "named"),
    [
        pytest.param("ahead", 3, "push it first", id="commits-not-on-remote"),
        pytest.param("ahead", None, "push it first", id="branch-not-on-remote"),
        pytest.param("branch", None, "detached HEAD", id="detached-head"),
        pytest.param("remote_url", None, "no 'origin' remote", id="no-remote"),
        pytest.param(
            "remote_url",
            "https://gitlab.com/anspar/elspais.git",
            "GitHub",
            id="not-github",
        ),
    ],
)
def test_a_branch_that_cannot_be_proposed_is_refused_naming_the_condition(
    repo: dict[str, Any], condition: str, value: Any, named: str
) -> None:
    """Each condition the tool will not guess past is refused, and the
    refusal names the condition it met."""
    repo[condition] = value
    opener = _Opener(CREATED)

    status, body = _call(_request({}, opener=opener))

    assert status == 400
    assert body["success"] is False
    assert named in body["error"]
    assert opener.requests == []  # Nothing was proposed on GitHub.


# Verifies: REQ-d00297-A+B
def test_a_credential_sent_with_the_request_outranks_the_servers_own(
    repo: dict[str, Any],
) -> None:
    """A pull request is attributed to whoever's credential the session
    supplied, so a supplied one is used in place of the machine's."""
    opener = _Opener(CREATED)
    request = _request(
        {},
        headers={SECRET_HEADER: PROXY_SECRET, GIT_TOKEN_HEADER: SUPPLIED_TOKEN},
        opener=opener,
    )

    status, _ = _call(request)

    assert status == 200
    assert opener.requests[0].get_header("Authorization") == f"Bearer {SUPPLIED_TOKEN}"


# Verifies: REQ-d00297-B
def test_an_untrusted_request_cannot_speak_with_a_credential_of_its_own(
    repo: dict[str, Any],
) -> None:
    """Without the secret shared with the proxy, a token in the headers is
    not a credential the session supplied, so the server's own is used."""
    opener = _Opener(CREATED)
    request = _request({}, headers={GIT_TOKEN_HEADER: SUPPLIED_TOKEN}, opener=opener)

    status, _ = _call(request)

    assert status == 200
    assert opener.requests[0].get_header("Authorization") == f"Bearer {ENV_TOKEN}"


# Verifies: REQ-d00297-A
@pytest.mark.parametrize(
    ("body", "default_branch", "expected_base"),
    [
        pytest.param({"base": "release"}, "trunk", "release", id="asked-for"),
        pytest.param({}, "trunk", "trunk", id="remote-default"),
        pytest.param({}, None, "main", id="no-recorded-default"),
    ],
)
def test_the_branch_proposed_onto_is_the_one_asked_for_or_the_remotes_own(
    repo: dict[str, Any], body: dict[str, Any], default_branch: str | None, expected_base: str
) -> None:
    """A base named in the request wins; otherwise the remote's own default
    is proposed onto, and only where the remote records none does the route
    fall back to a name of its own."""
    repo["default_branch"] = default_branch
    opener = _Opener(CREATED)

    status, _ = _call(_request(body, opener=opener))

    assert status == 200
    assert json.loads(opener.requests[0].data.decode("utf-8"))["base"] == expected_base


# Verifies: REQ-d00297-A
def test_a_proposal_with_no_title_is_named_after_the_branch(repo: dict[str, Any]) -> None:
    """A request naming no title still proposes something identifiable."""
    opener = _Opener(CREATED)

    _call(_request({"title": "   "}, opener=opener))

    assert json.loads(opener.requests[0].data.decode("utf-8"))["title"] == "feature"
