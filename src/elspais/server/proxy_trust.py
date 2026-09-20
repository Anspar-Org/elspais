"""Trust in what a request carries about who sent it.

A server serving many people through a proxy cannot name the person from
its own surroundings, so the proxy supplies the identity in headers. The
headers are believed only when the request also carries the secret the
process shares with its proxy: the daemon binds the local interface and on
a shared host every workspace process is the same OS user, so a flag saying
"trust the headers" would let any local caller speak as any user, and a
value known to every process would let one workspace speak as another's.

This module is the one authority on that trust. The secret is read from
``ELSPAIS_PROXY_SECRET`` once, when the process starts; with none
configured, nothing a request supplies is ever trusted.
"""

from __future__ import annotations

import hmac
import os
from typing import Any

SECRET_ENV_VAR = "ELSPAIS_PROXY_SECRET"
SECRET_HEADER = "X-Elspais-Proxy-Secret"
USER_NAME_HEADER = "X-Elspais-User-Name"
USER_EMAIL_HEADER = "X-Elspais-User-Email"
GIT_TOKEN_HEADER = "X-Elspais-Git-Token"


def _read_secret() -> str | None:
    """The secret this process was started with, or None when there is none.

    A blank value is no secret: the comparison must never succeed against
    an empty header.
    """
    value = os.environ.get(SECRET_ENV_VAR, "")
    return value if value else None


# Read once at process start. Tests replace this attribute rather than the
# environment, so that a secret set after start is not read.
_SECRET: str | None = _read_secret()


def proxy_secret_is_configured() -> bool:
    """Whether this process was started to serve people through a proxy.

    A process with a secret is answering for whoever the proxy names, so
    anything it holds of its own speaks for nobody who asked; a process
    without one is somebody's own viewer, and what it holds is theirs.
    """
    return _SECRET is not None


# Implements: REQ-d00296-C, REQ-d00296-D
def request_is_trusted(request: Any) -> bool:
    """Whether the request carries the secret this process shares with its proxy.

    False whenever no secret is configured, the header is absent, or the two
    differ. The comparison is constant-time so the header cannot be guessed
    by timing.
    """
    if _SECRET is None:
        return False
    supplied = request.headers.get(SECRET_HEADER)
    if not supplied:
        return False
    return hmac.compare_digest(supplied.encode("utf-8"), _SECRET.encode("utf-8"))


# Implements: REQ-d00296-A, REQ-d00296-C
def proxied_identity(request: Any) -> dict[str, str] | None:
    """The identity a trusted proxy supplied with the request, or None.

    Returns ``{"name": ..., "id": ...}`` only when the request is trusted
    and both identity headers carry a value; an identity with either half
    missing is no identity, and an untrusted request supplied none.
    """
    if not request_is_trusted(request):
        return None
    name = (request.headers.get(USER_NAME_HEADER) or "").strip()
    email = (request.headers.get(USER_EMAIL_HEADER) or "").strip()
    if not name or not email:
        return None
    return {"name": name, "id": email}


# Implements: REQ-d00296-E
def proxied_git_token(request: Any) -> str | None:
    """The git credential a trusted proxy supplied with the request, or None.

    Gated exactly as the identity is: an untrusted request supplied no
    credential, whatever its headers say.
    """
    if not request_is_trusted(request):
        return None
    token = (request.headers.get(GIT_TOKEN_HEADER) or "").strip()
    return token if token else None
