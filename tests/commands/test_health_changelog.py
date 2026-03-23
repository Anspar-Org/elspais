# Verifies: REQ-p00004
"""Tests for changelog-related health checks."""

from pathlib import Path

from elspais.commands.health import (
    check_spec_changelog_current,
    check_spec_changelog_format,
)
from elspais.config import _merge_configs, config_defaults, get_config
from elspais.graph.factory import build_graph
from elspais.utilities.hasher import compute_normalized_hash


def _make_config(tmp_path: Path, changelog_overrides: dict | None = None) -> Path:
    changelog = {
        "hash_current": True,
    }
    changelog_require = {
        "reason": True,
        "author_name": True,
        "author_id": True,
        "change_order": False,
    }
    if changelog_overrides:
        if "require" in changelog_overrides:
            changelog_require.update(changelog_overrides.pop("require"))
        changelog.update(changelog_overrides)

    def _fmt(v):
        if isinstance(v, bool):
            return str(v).lower()
        elif isinstance(v, str):
            return f'"{v}"'
        return str(v)

    lines = [
        'version = 3\n[project]\nname = "test"\nnamespace = "REQ"\n',
        '[scanning.spec]\ndirectories = ["spec"]\n',
        "[changelog]",
    ]
    for k, v in changelog.items():
        lines.append(f"{k} = {_fmt(v)}")
    lines.append("")
    lines.append("[changelog.require]")
    for k, v in changelog_require.items():
        lines.append(f"{k} = {_fmt(v)}")

    config_path = tmp_path / ".elspais.toml"
    config_path.write_text("\n".join(lines) + "\n")
    return config_path


def _build(tmp_path: Path, config_path: Path):
    return build_graph(
        spec_dirs=[tmp_path / "spec"],
        config_path=config_path,
        repo_root=tmp_path,
        scan_code=False,
        scan_tests=False,
    )


def _load_config(config_path: Path) -> dict:
    raw = get_config(config_path)
    return _merge_configs(config_defaults(), raw)


class TestChangelogCurrent:
    """Tests for check_spec_changelog_current."""

    def test_REQ_p00004_A_changelog_current_passes_when_hash_matches(self, tmp_path: Path):
        """Active req with matching changelog hash passes."""
        config_path = _make_config(tmp_path)
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()

        correct_hash = compute_normalized_hash([("A", "The system SHALL do X.")])

        req_file = spec_dir / "requirements.md"
        req_file.write_text(
            f"# REQ-d00001: Test Req\n"
            f"\n"
            f"**Level**: DEV | **Status**: Active"
            f" | **Implements**: -\n"
            f"\n"
            f"## Assertions\n"
            f"\n"
            f"A. The system SHALL do X.\n"
            f"\n"
            f"## Changelog\n"
            f"\n"
            f"- 2026-03-06 | {correct_hash} | -"
            f" | Alice (a@b.org) | Some reason\n"
            f"\n"
            f"*End* *Test Req* | **Hash**: {correct_hash}\n"
            f"---\n"
        )

        graph = _build(tmp_path, config_path)
        config = _load_config(config_path)
        result = check_spec_changelog_current(graph, config)

        assert result.passed is True
        assert result.name == "spec.changelog_current"

    def test_REQ_p00004_A_changelog_current_fails_when_hash_mismatch(self, tmp_path: Path):
        """Active req with mismatched changelog hash fails."""
        config_path = _make_config(tmp_path)
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()

        correct_hash = compute_normalized_hash([("A", "The system SHALL do X.")])

        req_file = spec_dir / "requirements.md"
        req_file.write_text(
            f"# REQ-d00001: Test Req\n"
            f"\n"
            f"**Level**: DEV | **Status**: Active"
            f" | **Implements**: -\n"
            f"\n"
            f"## Assertions\n"
            f"\n"
            f"A. The system SHALL do X.\n"
            f"\n"
            f"## Changelog\n"
            f"\n"
            f"- 2026-03-06 | deadbeef | -"
            f" | Alice (a@b.org) | Some reason\n"
            f"\n"
            f"*End* *Test Req* | **Hash**: {correct_hash}\n"
            f"---\n"
        )

        graph = _build(tmp_path, config_path)
        config = _load_config(config_path)
        result = check_spec_changelog_current(graph, config)

        assert result.passed is False
        assert result.severity == "error"
        assert result.name == "spec.changelog_current"

    def test_REQ_p00004_A_changelog_current_skips_draft(self, tmp_path: Path):
        """Draft req with no changelog is ignored."""
        config_path = _make_config(tmp_path)
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()

        req_file = spec_dir / "requirements.md"
        req_file.write_text(
            "# REQ-d00001: Draft Req\n"
            "\n"
            "**Level**: DEV | **Status**: Draft"
            " | **Implements**: -\n"
            "\n"
            "## Assertions\n"
            "\n"
            "A. The system SHALL do X.\n"
            "\n"
            "*End* *Draft Req*\n"
            "---\n"
        )

        graph = _build(tmp_path, config_path)
        config = _load_config(config_path)
        result = check_spec_changelog_current(graph, config)

        assert result.passed is True
        assert result.name == "spec.changelog_current"


class TestChangelogFormat:
    """Tests for check_spec_changelog_format."""

    def test_REQ_p00004_A_changelog_format_passes_valid_entries(self, tmp_path: Path):
        """Valid changelog entries with all required fields pass."""
        config_path = _make_config(tmp_path)
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()

        correct_hash = compute_normalized_hash([("A", "The system SHALL do X.")])

        req_file = spec_dir / "requirements.md"
        req_file.write_text(
            f"# REQ-d00001: Test Req\n"
            f"\n"
            f"**Level**: DEV | **Status**: Active"
            f" | **Implements**: -\n"
            f"\n"
            f"## Assertions\n"
            f"\n"
            f"A. The system SHALL do X.\n"
            f"\n"
            f"## Changelog\n"
            f"\n"
            f"- 2026-03-06 | {correct_hash} | -"
            f" | Alice (a@b.org) | Initial version\n"
            f"\n"
            f"*End* *Test Req* | **Hash**: {correct_hash}\n"
            f"---\n"
        )

        graph = _build(tmp_path, config_path)
        config = _load_config(config_path)
        result = check_spec_changelog_format(graph, config)

        assert result.passed is True
        assert result.name == "spec.changelog_format"

    def test_REQ_p00004_A_changelog_format_fails_missing_reason(self, tmp_path: Path):
        """Entry with empty reason when require.reason=true fails."""
        config_path = _make_config(tmp_path)
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()

        correct_hash = compute_normalized_hash([("A", "The system SHALL do X.")])

        # Build a spec where the changelog entry has an empty-ish reason.
        # The parser regex requires non-empty groups, so we use a
        # placeholder that the check should treat as missing.
        # We'll use "-" as the reason which semantically means empty.
        req_file = spec_dir / "requirements.md"
        req_file.write_text(
            f"# REQ-d00001: Test Req\n"
            f"\n"
            f"**Level**: DEV | **Status**: Active"
            f" | **Implements**: -\n"
            f"\n"
            f"## Assertions\n"
            f"\n"
            f"A. The system SHALL do X.\n"
            f"\n"
            f"## Changelog\n"
            f"\n"
            f"- 2026-03-06 | {correct_hash} | -"
            f" | Alice (a@b.org) | -\n"
            f"\n"
            f"*End* *Test Req* | **Hash**: {correct_hash}\n"
            f"---\n"
        )

        graph = _build(tmp_path, config_path)
        config = _load_config(config_path)
        result = check_spec_changelog_format(graph, config)

        assert result.passed is False
        assert result.name == "spec.changelog_format"
