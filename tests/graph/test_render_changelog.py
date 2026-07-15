"""Changelog entry rendering — MD034-safe author emails (CUR-1716)."""

# Verifies: REQ-d00131-K

from elspais.graph.render import format_changelog_entry


def _entry(author_id: str) -> dict[str, str]:
    return {
        "date": "2026-07-15",
        "hash": "abcd1234",
        "change_order": "-",
        "author_name": "Dev",
        "author_id": author_id,
        "reason": "test entry",
    }


def test_email_author_id_wrapped_in_angle_brackets():
    line = format_changelog_entry(_entry("dev@example.com"))
    assert "(<dev@example.com>)" in line
    assert line == ("- 2026-07-15 | abcd1234 | - | Dev (<dev@example.com>) | test entry")


def test_non_email_author_id_stays_bare():
    line = format_changelog_entry(_entry("octocat"))
    assert "(octocat)" in line
    assert "<" not in line


def test_prebracketed_email_not_double_wrapped():
    line = format_changelog_entry(_entry("<dev@example.com>"))
    assert "(<dev@example.com>)" in line
    assert "<<" not in line
