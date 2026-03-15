# Validates: REQ-d00085
"""E2E test verifying health check names in JSON output.

Ensures the new traceability check names are present and the old
renamed check names are absent.
"""
from __future__ import annotations

import json
import shutil

import pytest

from .helpers import (
    Requirement,
    base_config,
    build_project,
    run_elspais,
)

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        shutil.which("elspais") is None,
        reason="elspais CLI not found on PATH",
    ),
]


class TestHealthCheckNames:
    """Verify health --json output includes the correct check names."""

    def _build(self, tmp_path):
        cfg = base_config(
            name="check-names",
            testing_enabled=True,
            test_dirs=["tests"],
        )
        prd = Requirement(
            "REQ-p00001",
            "Feature",
            "PRD",
            assertions=[("A", "The system SHALL exist.")],
        )
        dev = Requirement(
            "REQ-d00001",
            "Impl",
            "DEV",
            implements="REQ-p00001",
            assertions=[("A", "The module SHALL implement the feature.")],
        )
        build_project(
            tmp_path,
            cfg,
            spec_files={
                "spec/prd.md": [prd],
                "spec/dev.md": [dev],
            },
            code_files={
                "src/feature.py": {"implements": ["REQ-d00001"]},
            },
            test_files={
                "tests/test_feature.py": {"validates": ["REQ-d00001"]},
            },
        )
        return tmp_path

    def test_REQ_d00085_new_check_names_present(self, tmp_path) -> None:
        """health --json includes the new traceability check names."""
        self._build(tmp_path)
        result = run_elspais("health", "--format", "json", "--lenient", cwd=tmp_path)
        assert result.returncode == 0, f"health failed: {result.stderr}"
        data = json.loads(result.stdout)
        check_names = {c["name"] for c in data.get("checks", [])}

        expected_present = {
            "spec.structural_orphans",
            "spec.broken_references",
            "tests.unlinked",
            "code.unlinked",
        }
        for name in expected_present:
            assert name in check_names, f"Expected check '{name}' not found in {check_names}"

    def test_REQ_d00085_old_check_names_absent(self, tmp_path) -> None:
        """health --json does NOT include the old renamed check names."""
        self._build(tmp_path)
        result = run_elspais("health", "--format", "json", "--lenient", cwd=tmp_path)
        assert result.returncode == 0, f"health failed: {result.stderr}"
        data = json.loads(result.stdout)
        check_names = {c["name"] for c in data.get("checks", [])}

        expected_absent = {
            "spec.orphans",
            "tests.references_resolve",
            "code.references_resolve",
        }
        for name in expected_absent:
            assert name not in check_names, f"Old check name '{name}' should not be present"
