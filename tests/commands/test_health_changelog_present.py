# Validates: REQ-d00004
"""Tests for check_spec_changelog_present health check."""

from pathlib import Path

from elspais.commands.health import check_spec_changelog_present
from elspais.config import ConfigLoader, get_config
from elspais.graph.factory import build_graph
from elspais.utilities.hasher import compute_normalized_hash


def _make_config(tmp_path: Path, changelog_overrides: dict | None = None) -> Path:
    changelog = {
        "enforce": True,
        "require_present": False,
        "require_reason": True,
        "require_author_name": True,
        "require_author_id": True,
        "require_change_order": False,
    }
    if changelog_overrides:
        changelog.update(changelog_overrides)

    lines = [
        '[project]\nname = "test"\n',
        '[requirements]\nspec_dirs = ["spec"]\n',
        "[requirements.id_pattern]",
        'prefix = "REQ"',
        'separator = "-"',
        'pattern = "REQ-[a-z]\\\\d{5}"\n',
        "[changelog]",
    ]
    for k, v in changelog.items():
        if isinstance(v, bool):
            lines.append(f"{k} = {str(v).lower()}")
        elif isinstance(v, str):
            lines.append(f'{k} = "{v}"')
        else:
            lines.append(f"{k} = {v}")

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
        scan_sponsors=False,
    )


def _load_config(config_path: Path) -> ConfigLoader:
    raw = get_config(config_path)
    return ConfigLoader.from_dict(raw)


class TestChangelogPresent:
    """Tests for check_spec_changelog_present."""

    def test_disabled_by_default_returns_passed_info(self, tmp_path: Path):
        """When require_present is False (default), returns passed with info severity."""
        config_path = _make_config(tmp_path)
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()

        # Active req with no changelog section at all
        req_file = spec_dir / "requirements.md"
        req_file.write_text(
            "# REQ-d00001: Test Req\n"
            "\n"
            "**Level**: DEV | **Status**: Active"
            " | **Implements**: -\n"
            "\n"
            "## Assertions\n"
            "\n"
            "A. The system SHALL do X.\n"
            "\n"
            "*End* *Test Req*\n"
            "---\n"
        )

        graph = _build(tmp_path, config_path)
        config = _load_config(config_path)
        result = check_spec_changelog_present(graph, config)

        assert result.passed is True
        assert result.severity == "info"
        assert result.name == "spec.changelog_present"
        assert "disabled" in result.message.lower()

    def test_enabled_no_active_reqs_passes(self, tmp_path: Path):
        """When enabled but no Active reqs exist, passes."""
        config_path = _make_config(tmp_path, {"require_present": True})
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()

        # Draft req only - no Active requirements
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
        result = check_spec_changelog_present(graph, config)

        assert result.passed is True
        assert result.name == "spec.changelog_present"

    def test_enabled_active_reqs_all_have_changelogs_passes(self, tmp_path: Path):
        """When all Active reqs have changelog entries, passes."""
        config_path = _make_config(tmp_path, {"require_present": True})
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
        result = check_spec_changelog_present(graph, config)

        assert result.passed is True
        assert result.name == "spec.changelog_present"

    def test_enabled_active_req_missing_changelog_fails(self, tmp_path: Path):
        """When an Active req has no changelog entries, fails with findings."""
        config_path = _make_config(tmp_path, {"require_present": True})
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()

        req_file = spec_dir / "requirements.md"
        req_file.write_text(
            "# REQ-d00001: Missing Changelog\n"
            "\n"
            "**Level**: DEV | **Status**: Active"
            " | **Implements**: -\n"
            "\n"
            "## Assertions\n"
            "\n"
            "A. The system SHALL do X.\n"
            "\n"
            "*End* *Missing Changelog*\n"
            "---\n"
        )

        graph = _build(tmp_path, config_path)
        config = _load_config(config_path)
        result = check_spec_changelog_present(graph, config)

        assert result.passed is False
        assert result.severity == "error"
        assert result.name == "spec.changelog_present"
        assert len(result.findings) == 1
        assert result.findings[0].node_id == "REQ-d00001"
        assert "REQ-d00001" in result.message
        assert "REQ-d00001" in result.details["missing"]

    def test_enabled_multiple_active_reqs_some_missing(self, tmp_path: Path):
        """When some Active reqs are missing changelogs, findings list each one."""
        config_path = _make_config(tmp_path, {"require_present": True})
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()

        correct_hash = compute_normalized_hash([("A", "The system SHALL do X.")])

        req_file = spec_dir / "requirements.md"
        req_file.write_text(
            f"# REQ-d00001: Has Changelog\n"
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
            f" | Alice (a@b.org) | Initial\n"
            f"\n"
            f"*End* *Has Changelog* | **Hash**: {correct_hash}\n"
            f"---\n"
            f"\n"
            f"# REQ-d00002: No Changelog\n"
            f"\n"
            f"**Level**: DEV | **Status**: Active"
            f" | **Implements**: -\n"
            f"\n"
            f"## Assertions\n"
            f"\n"
            f"A. The system SHALL do Y.\n"
            f"\n"
            f"*End* *No Changelog*\n"
            f"---\n"
        )

        graph = _build(tmp_path, config_path)
        config = _load_config(config_path)
        result = check_spec_changelog_present(graph, config)

        assert result.passed is False
        assert len(result.findings) == 1
        assert result.findings[0].node_id == "REQ-d00002"
        assert "REQ-d00002" in result.details["missing"]
        assert "REQ-d00001" not in result.details["missing"]

    def test_draft_and_deprecated_reqs_ignored(self, tmp_path: Path):
        """Draft and Deprecated reqs without changelogs don't trigger failure."""
        config_path = _make_config(tmp_path, {"require_present": True})
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
            "\n"
            "# REQ-d00002: Deprecated Req\n"
            "\n"
            "**Level**: DEV | **Status**: Deprecated"
            " | **Implements**: -\n"
            "\n"
            "## Assertions\n"
            "\n"
            "A. The system SHALL do Y.\n"
            "\n"
            "*End* *Deprecated Req*\n"
            "---\n"
        )

        graph = _build(tmp_path, config_path)
        config = _load_config(config_path)
        result = check_spec_changelog_present(graph, config)

        assert result.passed is True
        assert result.name == "spec.changelog_present"
