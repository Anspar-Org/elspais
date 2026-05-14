# Implements: REQ-d00212-E, REQ-d00231-E
"""Author resolution for changelog entries.

When changelog enforcement is on, every new changelog entry MUST be
attributable to a real person. This module centralizes the lookup and
the config-driven required-field validation that ``fix_cmd``, ``edit``
and the MCP ``save_mutations`` path all need, so that a missing identity
fails loudly in one place instead of being silently dropped in three.
"""

from __future__ import annotations

import subprocess
from typing import Any

from elspais.config.schema import ChangelogConfig

_FIX_HINT = (
    "To fix: run `gh auth login` (and ensure your GitHub profile has a "
    "public name and email), or set both `git config --global user.name "
    '"<your name>"` and `git config --global user.email '
    '"<you@example.com>"`.'
)


class AuthorResolutionError(Exception):
    """Raised when one or more *required* changelog author fields cannot
    be resolved.

    Attributes:
        missing: Field names that were both required by
            ``ChangelogRequireConfig`` and unavailable from the lookup
            source. Subset of ``{"author_name", "author_id"}``.
    """

    def __init__(self, missing: list[str]) -> None:
        self.missing: list[str] = list(missing)
        super().__init__(self._format(missing))

    @staticmethod
    def _format(missing: list[str]) -> str:
        fields = ", ".join(missing) if missing else "author identity"
        return f"Cannot determine changelog author: missing {fields}. " f"{_FIX_HINT}"


def resolve_changelog_author(
    changelog_cfg: ChangelogConfig | dict[str, Any] | None,
) -> dict[str, str]:
    """Resolve ``{"name", "id"}`` for a changelog entry.

    Honors ``ChangelogRequireConfig.author_name`` and ``author_id``:
    missing fields are tolerated when their corresponding ``require.*``
    flag is False, and only required fields trigger
    ``AuthorResolutionError``.

    Args:
        changelog_cfg: A ``ChangelogConfig``, a plain dict (e.g. the
            ``changelog`` slice of ``load_config()`` output), or ``None``
            (defaults are used).

    Returns:
        ``{"name": <str>, "id": <str>}``. Either value may be the empty
        string when the matching ``require.*`` flag is False.

    Raises:
        AuthorResolutionError: when one or more required fields are
            empty after the lookup.
    """
    id_source, require_name, require_id = _extract(changelog_cfg)
    name, ident = _lookup_raw(id_source)

    missing: list[str] = []
    if require_name and not name:
        missing.append("author_name")
    if require_id and not ident:
        missing.append("author_id")
    if missing:
        raise AuthorResolutionError(missing)
    return {"name": name, "id": ident}


def _extract(
    changelog_cfg: ChangelogConfig | dict[str, Any] | None,
) -> tuple[str, bool, bool]:
    """Pull ``(id_source, require_name, require_id)`` out of any
    accepted config shape.
    """
    if changelog_cfg is None:
        defaults = ChangelogConfig()
        return defaults.id_source, defaults.require.author_name, defaults.require.author_id
    if isinstance(changelog_cfg, ChangelogConfig):
        return (
            changelog_cfg.id_source,
            changelog_cfg.require.author_name,
            changelog_cfg.require.author_id,
        )
    id_source = changelog_cfg.get("id_source", "gh")
    require = changelog_cfg.get("require") or {}
    require_name = require.get("author_name", True)
    require_id = require.get("author_id", True)
    return id_source, require_name, require_id


def _lookup_raw(id_source: str) -> tuple[str, str]:
    """Look up ``(name, id)`` without enforcement.

    Returns empty strings for fields that cannot be resolved. The caller
    decides whether emptiness is fatal.
    """
    name = ""
    ident = ""

    if id_source == "gh":
        try:
            import json as _json

            result = subprocess.run(
                ["gh", "api", "user"],
                capture_output=True,
                text=True,
                check=True,
            )
            data = _json.loads(result.stdout)
            name = data.get("name") or ""
            ident = data.get("email") or ""
        except (subprocess.CalledProcessError, FileNotFoundError, ValueError):
            pass

    if not name:
        name = _git_config("user.name")
    if not ident:
        ident = _git_config("user.email")
    return name, ident


def _git_config(key: str) -> str:
    """Read a single git config value; empty string if unavailable."""
    try:
        result = subprocess.run(
            ["git", "config", key],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""
