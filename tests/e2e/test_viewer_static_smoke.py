# Verifies: REQ-p00006-A
"""Smoke test: `elspais viewer --static` renders without errors.

Guards CUR-1692. The static viewer's HTMLGenerator crashed with
`TreeRow.__init__() missing 1 required positional argument: 'is_unsaved'`
whenever a TEST node had RESULT children (the RESULT-under-TEST render path),
exiting non-zero and writing an empty file while still printing "Generated:".

The other `viewer --static` e2e tests run on fixtures without test results, and
the browser tests exercise the live server (a different code path with its own
`is_unsaved` handling), so neither covered this path. The steps-all-pass fixture
ingests a JUnit ``results.xml`` linked to its journey-step tests, so building its
graph produces RESULT nodes parented under TEST nodes -- exactly the render path
that regressed.
"""
from __future__ import annotations

import shutil

import pytest

from .conftest import load_fixture, run_elspais

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        shutil.which("elspais") is None,
        reason="elspais CLI not found on PATH",
    ),
]


@pytest.fixture(scope="module")
def results_project(tmp_path_factory):
    """A fixture project whose graph has RESULT nodes parented under TEST nodes."""
    root = tmp_path_factory.mktemp("viewer_static_smoke")
    load_fixture("journey-uat/steps-all-pass", root)
    return root


class TestViewerStaticRunsWithoutErrors:
    # Verifies: REQ-p00006-A
    def test_static_viewer_renders_with_test_results(self, results_project):
        result = run_elspais("viewer", "--static", cwd=results_project)
        assert (
            result.returncode == 0
        ), f"viewer --static exited {result.returncode}: {result.stderr}"
        # `viewer --static` prints "Generated:" even when rendering raised, so a
        # non-empty, HTML-shaped payload is the real success signal.
        assert "<!DOCTYPE html" in result.stdout, "static viewer produced no HTML"
        assert (
            len(result.stdout) > 1000
        ), f"static viewer output suspiciously small ({len(result.stdout)} bytes)"
