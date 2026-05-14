# Verifies: REQ-d00212-E, REQ-d00231-E
"""Unit tests for the changelog author resolution helper.

Validates that ``resolve_changelog_author`` honors
``ChangelogRequireConfig.author_name`` / ``author_id`` flags and raises
``AuthorResolutionError`` with a useful message when a required field is
empty.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from elspais.config.schema import ChangelogConfig, ChangelogRequireConfig
from elspais.utilities.changelog_author import (
    AuthorResolutionError,
    resolve_changelog_author,
)


def _cfg(
    *,
    id_source: str = "git",
    require_name: bool = True,
    require_id: bool = True,
) -> ChangelogConfig:
    """Build a ChangelogConfig with the given require flags."""
    return ChangelogConfig(
        id_source=id_source,
        require=ChangelogRequireConfig(
            author_name=require_name,
            author_id=require_id,
        ),
    )


class TestResolveChangelogAuthor:
    """Tests for ``resolve_changelog_author``.

    Validates REQ-d00231-E (author identity resolved server-side via the
    changelog.id_source config) and REQ-d00212-E (``ChangelogRequireConfig``
    drives whether missing fields are fatal).
    """

    @patch(
        "elspais.utilities.changelog_author._lookup_raw",
        return_value=("Alice", "alice@ex.com"),
    )
    def test_returns_name_and_id_when_both_present(self, _mock_lookup):
        result = resolve_changelog_author(_cfg())
        assert result == {"name": "Alice", "id": "alice@ex.com"}

    @patch(
        "elspais.utilities.changelog_author._lookup_raw",
        return_value=("", "a@e"),
    )
    def test_raises_when_name_missing_and_required(self, _mock_lookup):
        with pytest.raises(AuthorResolutionError) as exc:
            resolve_changelog_author(_cfg())
        assert exc.value.missing == ["author_name"]

    @patch(
        "elspais.utilities.changelog_author._lookup_raw",
        return_value=("Alice", ""),
    )
    def test_raises_when_id_missing_and_required(self, _mock_lookup):
        with pytest.raises(AuthorResolutionError) as exc:
            resolve_changelog_author(_cfg())
        assert exc.value.missing == ["author_id"]

    @patch(
        "elspais.utilities.changelog_author._lookup_raw",
        return_value=("", ""),
    )
    def test_raises_with_both_missing(self, _mock_lookup):
        with pytest.raises(AuthorResolutionError) as exc:
            resolve_changelog_author(_cfg())
        assert exc.value.missing == ["author_name", "author_id"]

    @patch(
        "elspais.utilities.changelog_author._lookup_raw",
        return_value=("", "a@e"),
    )
    def test_no_raise_when_name_missing_but_not_required(self, _mock_lookup):
        result = resolve_changelog_author(_cfg(require_name=False))
        assert result == {"name": "", "id": "a@e"}

    @patch(
        "elspais.utilities.changelog_author._lookup_raw",
        return_value=("Alice", ""),
    )
    def test_no_raise_when_id_missing_but_not_required(self, _mock_lookup):
        result = resolve_changelog_author(_cfg(require_id=False))
        assert result == {"name": "Alice", "id": ""}

    @patch(
        "elspais.utilities.changelog_author._lookup_raw",
        return_value=("", "a@e"),
    )
    def test_error_message_names_missing_fields(self, _mock_lookup):
        with pytest.raises(AuthorResolutionError) as exc:
            resolve_changelog_author(_cfg())
        assert "author_name" in str(exc.value)

    @patch(
        "elspais.utilities.changelog_author._lookup_raw",
        return_value=("", ""),
    )
    def test_error_message_includes_fix_hint(self, _mock_lookup):
        with pytest.raises(AuthorResolutionError) as exc:
            resolve_changelog_author(_cfg())
        msg = str(exc.value).lower()
        assert "git config" in msg
        assert "gh auth" in msg

    @patch(
        "elspais.utilities.changelog_author._lookup_raw",
        return_value=("Alice", "alice@ex.com"),
    )
    def test_accepts_dict_input(self, _mock_lookup):
        """Plain dict (as returned by ``load_config``) should work the same
        as a typed ``ChangelogConfig``.
        """
        cfg_dict = {
            "id_source": "git",
            "require": {"author_name": True, "author_id": True},
        }
        result = resolve_changelog_author(cfg_dict)
        assert result == {"name": "Alice", "id": "alice@ex.com"}
