# Verifies: REQ-d00296-A+C+D+E
"""Tests for trusting request-supplied identity and credentials."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from elspais.server import proxy_trust
from elspais.server.proxy_trust import (
    GIT_TOKEN_HEADER,
    SECRET_ENV_VAR,
    SECRET_HEADER,
    USER_EMAIL_HEADER,
    USER_NAME_HEADER,
    proxied_git_token,
    proxied_identity,
)

SECRET = "shared-with-the-hub"
IDENTITY = {USER_NAME_HEADER: "Alice Smith", USER_EMAIL_HEADER: "alice@co.org"}


def _request(headers: dict[str, str]) -> SimpleNamespace:
    """A request carrying exactly these headers, matched without regard to case."""
    lowered = {k.lower(): v for k, v in headers.items()}

    class _Headers:
        def get(self, key: str, default=None):
            return lowered.get(key.lower(), default)

    return SimpleNamespace(headers=_Headers())


@pytest.fixture
def configured(monkeypatch: pytest.MonkeyPatch) -> str:
    """The process was started with a secret."""
    monkeypatch.setattr(proxy_trust, "_SECRET", SECRET)
    return SECRET


@pytest.fixture
def unconfigured(monkeypatch: pytest.MonkeyPatch) -> None:
    """The process was started with no secret."""
    monkeypatch.setattr(proxy_trust, "_SECRET", None)


class TestProxiedIdentity:
    # Verifies: REQ-d00296-A
    def test_matching_secret_yields_supplied_identity(self, configured: str) -> None:
        request = _request({SECRET_HEADER: configured, **IDENTITY})
        assert proxied_identity(request) == {"name": "Alice Smith", "id": "alice@co.org"}

    # Verifies: REQ-d00296-A
    def test_header_names_match_without_regard_to_case(self, configured: str) -> None:
        request = _request(
            {
                SECRET_HEADER.lower(): configured,
                USER_NAME_HEADER.lower(): "Alice Smith",
                USER_EMAIL_HEADER.lower(): "alice@co.org",
            }
        )
        assert proxied_identity(request) == {"name": "Alice Smith", "id": "alice@co.org"}

    # Verifies: REQ-d00296-C
    @pytest.mark.parametrize(
        "secret_headers",
        [
            pytest.param({}, id="secret-missing"),
            pytest.param({SECRET_HEADER: "not-the-secret"}, id="secret-wrong"),
            pytest.param({SECRET_HEADER: ""}, id="secret-blank"),
            pytest.param({SECRET_HEADER: SECRET + "x"}, id="secret-longer"),
        ],
    )
    def test_identity_without_proof_is_ignored(
        self, configured: str, secret_headers: dict[str, str]
    ) -> None:
        request = _request({**secret_headers, **IDENTITY})
        assert proxied_identity(request) is None

    # Verifies: REQ-d00296-D
    def test_unconfigured_secret_trusts_nothing(self, unconfigured: None) -> None:
        # Even a request that echoes the empty configuration is untrusted:
        # an absent secret is not a secret that happens to be blank.
        for supplied in ("", "anything"):
            request = _request({SECRET_HEADER: supplied, **IDENTITY})
            assert proxied_identity(request) is None

    # Verifies: REQ-d00296-D
    def test_blank_environment_value_is_no_secret(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(SECRET_ENV_VAR, "")
        assert proxy_trust._read_secret() is None
        monkeypatch.setenv(SECRET_ENV_VAR, SECRET)
        assert proxy_trust._read_secret() == SECRET

    # Verifies: REQ-d00296-A
    @pytest.mark.parametrize(
        "identity_headers",
        [
            pytest.param({USER_NAME_HEADER: "Alice Smith"}, id="email-missing"),
            pytest.param({USER_EMAIL_HEADER: "alice@co.org"}, id="name-missing"),
            pytest.param({USER_NAME_HEADER: "", USER_EMAIL_HEADER: ""}, id="both-blank"),
            pytest.param(
                {USER_NAME_HEADER: "  ", USER_EMAIL_HEADER: "alice@co.org"}, id="name-space"
            ),
        ],
    )
    def test_incomplete_identity_is_no_identity(
        self, configured: str, identity_headers: dict[str, str]
    ) -> None:
        request = _request({SECRET_HEADER: configured, **identity_headers})
        assert proxied_identity(request) is None

    # Verifies: REQ-d00296-C
    def test_non_ascii_secret_header_is_untrusted_not_an_error(self, configured: str) -> None:
        request = _request({SECRET_HEADER: "sécrète", **IDENTITY})
        assert proxied_identity(request) is None


class TestProxiedGitToken:
    # Verifies: REQ-d00296-E
    def test_matching_secret_yields_token(self, configured: str) -> None:
        request = _request({SECRET_HEADER: configured, GIT_TOKEN_HEADER: "ghs_abc"})
        assert proxied_git_token(request) == "ghs_abc"

    # Verifies: REQ-d00296-E
    @pytest.mark.parametrize(
        "secret_headers",
        [
            pytest.param({}, id="secret-missing"),
            pytest.param({SECRET_HEADER: "not-the-secret"}, id="secret-wrong"),
        ],
    )
    def test_token_without_proof_is_absent(
        self, configured: str, secret_headers: dict[str, str]
    ) -> None:
        request = _request({**secret_headers, GIT_TOKEN_HEADER: "ghs_abc"})
        assert proxied_git_token(request) is None

    # Verifies: REQ-d00296-E
    def test_unconfigured_secret_yields_no_token(self, unconfigured: None) -> None:
        request = _request({SECRET_HEADER: "", GIT_TOKEN_HEADER: "ghs_abc"})
        assert proxied_git_token(request) is None

    # Verifies: REQ-d00296-E
    def test_trusted_request_without_token_yields_none(self, configured: str) -> None:
        assert proxied_git_token(_request({SECRET_HEADER: configured})) is None
        assert (
            proxied_git_token(_request({SECRET_HEADER: configured, GIT_TOKEN_HEADER: " "})) is None
        )
