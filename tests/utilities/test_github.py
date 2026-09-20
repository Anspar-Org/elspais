# Verifies: REQ-d00297-A+C+E
"""Tests for reading a GitHub remote and opening a pull request on it.

Every call is made through an injected opener, so no test here reaches the
network: what is asserted is the request the module composes and the outcome
it derives from the answer it gets back -- including the one answer that is
not a refusal, an open pull request already proposing the same branch.
"""

from __future__ import annotations

import io
import json
import urllib.error
import urllib.request
from typing import Any

import pytest

from elspais.utilities.github import (
    find_open_pull_request,
    open_pull_request,
    parse_owner_repo,
)

TOKEN = "ghs-token-for-this-one-call"


class _Response:
    """The minimum an opener's answer has to be: bytes that can be read once."""

    def __init__(self, payload: Any) -> None:
        self._body = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._body


def _http_error(code: int, payload: Any) -> urllib.error.HTTPError:
    """GitHub answering with a status and a body explaining it."""
    return urllib.error.HTTPError(
        url="https://api.github.com/repos/o/r/pulls",
        code=code,
        msg="rejected",
        hdrs=None,  # type: ignore[arg-type]
        fp=io.BytesIO(json.dumps(payload).encode("utf-8")),
    )


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
        return answer


# Verifies: REQ-d00297-C
@pytest.mark.parametrize(
    ("remote_url", "expected"),
    [
        pytest.param("https://github.com/anspar/elspais.git", ("anspar", "elspais"), id="https"),
        pytest.param("https://github.com/anspar/elspais", ("anspar", "elspais"), id="https-bare"),
        pytest.param("https://github.com/anspar/elspais/", ("anspar", "elspais"), id="https-slash"),
        pytest.param(
            "https://x-access-token@github.com/anspar/elspais.git",
            ("anspar", "elspais"),
            id="https-userinfo",
        ),
        pytest.param("git@github.com:anspar/elspais.git", ("anspar", "elspais"), id="ssh-scp"),
        pytest.param("ssh://git@github.com/anspar/elspais", ("anspar", "elspais"), id="ssh-url"),
        pytest.param("https://gitlab.com/anspar/elspais.git", None, id="other-host"),
        pytest.param("git@bitbucket.org:anspar/elspais.git", None, id="other-host-ssh"),
        pytest.param("/srv/mirrors/elspais.git", None, id="local-path"),
        pytest.param("", None, id="empty"),
    ],
)
def test_owner_and_repo_are_read_only_from_a_github_remote(
    remote_url: str, expected: tuple[str, str] | None
) -> None:
    """A GitHub remote in any of its spellings names its owner and repository;
    a remote elsewhere names none, which is what the caller refuses on."""
    assert parse_owner_repo(remote_url) == expected


# Verifies: REQ-d00297-A
def test_opening_a_pull_request_sends_the_branch_and_the_credential() -> None:
    """The request carries the proposal (title, body, head, base) and the
    credential it is to be attributed to, and the created pull request is
    reported as new."""
    opener = _Opener(_Response({"html_url": "https://github.com/o/r/pull/7", "number": 7}))

    result = open_pull_request(
        owner="o",
        repo="r",
        head_branch="feature",
        base_branch="main",
        title="A proposal",
        body="Why it should land",
        token=TOKEN,
        opener=opener,
    )

    assert result == {
        "success": True,
        "url": "https://github.com/o/r/pull/7",
        "number": 7,
        "existing": False,
    }
    (sent,) = opener.requests
    assert sent.get_method() == "POST"
    assert sent.full_url == "https://api.github.com/repos/o/r/pulls"
    assert json.loads(sent.data.decode("utf-8")) == {
        "title": "A proposal",
        "body": "Why it should land",
        "head": "feature",
        "base": "main",
    }
    assert sent.get_header("Authorization") == f"Bearer {TOKEN}"


# Verifies: REQ-d00297-E
def test_a_pull_request_already_proposing_the_branch_is_the_outcome() -> None:
    """GitHub refusing a duplicate is answered by reporting the pull request
    that already exists, not by refusing the request."""
    opener = _Opener(
        _http_error(422, {"message": "Validation Failed"}),
        _Response([{"html_url": "https://github.com/o/r/pull/3", "number": 3}]),
    )

    result = open_pull_request(
        owner="o",
        repo="r",
        head_branch="feature",
        base_branch="main",
        title="A proposal",
        body="",
        token=TOKEN,
        opener=opener,
    )

    assert result == {
        "success": True,
        "url": "https://github.com/o/r/pull/3",
        "number": 3,
        "existing": True,
    }
    lookup = opener.requests[1]
    assert lookup.get_method() == "GET"
    assert "head=o%3Afeature" in lookup.full_url or "head=o:feature" in lookup.full_url
    assert "state=open" in lookup.full_url


# Verifies: REQ-d00297-E
def test_a_rejection_with_no_existing_pull_request_reports_what_github_said() -> None:
    """Where nothing already proposes the branch, the rejection stands and
    carries GitHub's own explanation of it."""
    opener = _Opener(
        _http_error(
            422,
            {
                "message": "Validation Failed",
                "errors": [{"message": "No commits between main and feature"}],
            },
        ),
        _Response([]),
    )

    result = open_pull_request(
        owner="o",
        repo="r",
        head_branch="feature",
        base_branch="main",
        title="A proposal",
        body="",
        token=TOKEN,
        opener=opener,
    )

    assert result["success"] is False
    assert "No commits between main and feature" in result["error"]


# Verifies: REQ-d00297-E
@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        pytest.param(_Response([]), None, id="none-open"),
        pytest.param(_Response({"message": "Not Found"}), None, id="not-a-list"),
    ],
)
def test_no_open_pull_request_is_reported_as_none(answer: Any, expected: Any) -> None:
    """An empty answer is 'nothing proposes this branch', which the caller
    distinguishes from a pull request it can report."""
    assert find_open_pull_request("o", "r", "feature", TOKEN, opener=_Opener(answer)) is expected


# Verifies: REQ-d00297-E
def test_a_failed_lookup_is_not_mistaken_for_an_existing_pull_request() -> None:
    """A lookup GitHub refuses yields None rather than an answer invented
    from the failure."""
    opener = _Opener(_http_error(403, {"message": "Forbidden"}))
    assert find_open_pull_request("o", "r", "feature", TOKEN, opener=opener) is None
