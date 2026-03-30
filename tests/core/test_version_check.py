# Validates CUR-883: version check and upgrade instructions
"""Tests for elspais.utilities.version_check."""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from elspais.utilities.version_check import (
    check_for_updates,
    detect_install_method,
    fetch_latest_version,
    get_upgrade_command,
    is_newer,
    parse_version_tuple,
)


class TestParseVersionTuple:
    # Implements: REQ-d00213-A
    @pytest.mark.parametrize(
        ("version_str", "expected"),
        [
            ("0.58.0", (0, 58, 0)),
            ("1", (1,)),
            ("1.2", (1, 2)),
            ("1.0.0a1", (1, 0, 0)),
            ("1.0.0b2", (1, 0, 0)),
            ("1.0.0rc1", (1, 0, 0)),
            ("0.58.0+local", (0, 58, 0)),
            ("0.58.0.dev1", (0, 58, 0)),
            ("unknown", (0,)),
        ],
        ids=[
            "simple",
            "major_only",
            "two_part",
            "prerelease_alpha",
            "prerelease_beta",
            "prerelease_rc",
            "local",
            "dev",
            "unknown_fallback",
        ],
    )
    def test_parse_version_tuple(self, version_str: str, expected: tuple) -> None:
        assert parse_version_tuple(version_str) == expected


class TestIsNewer:
    # Implements: REQ-d00213-B
    @pytest.mark.parametrize(
        ("latest", "current", "expected"),
        [
            ("0.58.1", "0.58.0", True),
            ("0.59.0", "0.58.0", True),
            ("1.0.0", "0.58.0", True),
            ("0.58.0", "0.58.0", False),
            ("0.57.0", "0.58.0", False),
        ],
        ids=["newer_patch", "newer_minor", "newer_major", "same_version", "older"],
    )
    def test_is_newer(self, latest: str, current: str, expected: bool) -> None:
        assert is_newer(latest, current) is expected


class TestDetectInstallMethod:
    # Implements: REQ-d00213-C
    def test_pipx(self):
        fake_path = (
            "/home/user/.local/pipx/venvs/elspais/lib/python3.10/site-packages/elspais/__init__.py"
        )
        with patch("elspais.utilities.version_check.Path") as mock_path:
            mock_path.return_value.resolve.return_value = fake_path
            import elspais

            with patch.object(elspais, "__file__", fake_path):
                assert detect_install_method() == "pipx"

    # Implements: REQ-d00213-C
    def test_brew_apple_silicon(self):
        fake_path = "/opt/homebrew/lib/python3.12/site-packages/elspais/__init__.py"
        import elspais

        with patch.object(elspais, "__file__", fake_path):
            assert detect_install_method() == "brew"

    # Implements: REQ-d00213-C
    def test_brew_intel(self):
        fake_path = (
            "/usr/local/Cellar/elspais/0.58.0/lib/python3.12/site-packages/elspais/__init__.py"
        )
        import elspais

        with patch.object(elspais, "__file__", fake_path):
            assert detect_install_method() == "brew"

    # Implements: REQ-d00213-C
    def test_editable(self):
        fake_path = "/home/user/projects/elspais/src/elspais/__init__.py"
        import elspais

        with patch.object(elspais, "__file__", fake_path):
            assert detect_install_method() == "editable"

    # Implements: REQ-d00213-C
    def test_user_install(self):
        fake_path = "/home/user/.local/lib/python3.10/site-packages/elspais/__init__.py"
        import sys

        import elspais

        with (
            patch.object(elspais, "__file__", fake_path),
            patch.object(sys, "prefix", "/usr"),
            patch.object(sys, "base_prefix", "/usr"),
        ):
            assert detect_install_method() == "user"

    # Implements: REQ-d00213-C
    def test_venv(self):
        fake_path = "/home/user/myproject/.venv/lib/python3.12/site-packages/elspais/__init__.py"
        import sys

        import elspais

        with (
            patch.object(elspais, "__file__", fake_path),
            patch.object(sys, "prefix", "/home/user/myproject/.venv"),
            patch.object(sys, "base_prefix", "/usr"),
        ):
            assert detect_install_method() == "venv"


class TestGetUpgradeCommand:
    # Implements: REQ-d00213-D
    def test_pipx_command(self):
        assert get_upgrade_command("pipx") == "pipx upgrade elspais"

    # Implements: REQ-d00213-D
    def test_brew_command(self):
        assert get_upgrade_command("brew") == "brew upgrade elspais"

    # Implements: REQ-d00213-D
    def test_venv_command(self):
        assert "pip install --upgrade" in get_upgrade_command("venv")

    # Implements: REQ-d00213-D
    def test_editable_command(self):
        # Implements: REQ-d00213-D
        assert "git pull" in get_upgrade_command("editable")


class TestFetchLatestVersion:
    # Implements: REQ-d00213-E
    def test_success(self):
        fake_response = json.dumps({"info": {"version": "1.0.0"}}).encode()
        with patch("elspais.utilities.version_check.urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value.__enter__ = lambda s: s
            mock_urlopen.return_value.__exit__ = lambda s, *a: None
            mock_urlopen.return_value.read.return_value = fake_response
            assert fetch_latest_version() == "1.0.0"

    # Implements: REQ-d00213-E
    def test_network_failure(self):
        import urllib.error

        with patch(
            "elspais.utilities.version_check.urllib.request.urlopen",
            side_effect=urllib.error.URLError("no network"),
        ):
            assert fetch_latest_version() is None

    # Implements: REQ-d00213-E
    def test_bad_json(self):
        with patch("elspais.utilities.version_check.urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value.__enter__ = lambda s: s
            mock_urlopen.return_value.__exit__ = lambda s, *a: None
            mock_urlopen.return_value.read.return_value = b"not json"
            assert fetch_latest_version() is None


class TestCheckForUpdates:
    # Implements: REQ-d00213-F
    def test_up_to_date(self, capsys):
        with patch("elspais.utilities.version_check.fetch_latest_version", return_value="0.58.0"):
            result = check_for_updates("0.58.0")
            assert result == 0
            output = capsys.readouterr().out
            assert "up to date" in output

    # Implements: REQ-d00213-F
    def test_update_available(self, capsys):
        with (
            patch("elspais.utilities.version_check.fetch_latest_version", return_value="0.59.0"),
            patch("elspais.utilities.version_check.detect_install_method", return_value="pipx"),
        ):
            result = check_for_updates("0.58.0")
            assert result == 0
            output = capsys.readouterr().out
            assert "update available" in output
            assert "0.59.0" in output
            assert "pipx upgrade elspais" in output

    # Implements: REQ-d00213-F
    def test_network_failure(self, capsys):
        with patch("elspais.utilities.version_check.fetch_latest_version", return_value=None):
            result = check_for_updates("0.58.0")
            assert result == 1
            captured = capsys.readouterr()
            assert "Could not reach PyPI" in captured.err
