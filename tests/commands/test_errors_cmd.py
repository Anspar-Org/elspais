# Validates: REQ-p00002-A
"""Tests for the ``elspais errors`` command.

Validates REQ-p00002-A: error listing for spec format violations and missing
assertions.

Covers:
- collect_errors() returning format violations and no-assertion entries
- render_error_text() plain-text rendering
- render_error_markdown() table rendering
- run() CLI entry point with text output
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

CONFIG_REQUIRE_HASH = """\
version = 3

[project]
name = "test"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]

[rules.format]
require_hash = true
"""

# Requirement that VIOLATES require_hash (no hash in footer).
REQ_MISSING_HASH = """\
# REQ-d00001: Missing Hash Req

**Level**: DEV | **Status**: Draft | **Implements**: -

Body text.

## Assertions

A. The system shall do something.

*End* *Missing Hash Req*
---
"""

# Requirement with NO assertions (triggers no_assertions).
REQ_NO_ASSERTIONS = """\
# REQ-d00002: No Assertions Req

**Level**: DEV | **Status**: Draft | **Implements**: -

Body text but no assertions section.

*End* *No Assertions Req* | **Hash**: abcd1234
---
"""

# A well-formed requirement (should produce NO errors with default rules).
REQ_GOOD = """\
# REQ-d00003: Good Req

**Level**: DEV | **Status**: Draft | **Implements**: -

Body text.

## Assertions

A. The system shall work correctly.

*End* *Good Req* | **Hash**: 12345678
---
"""


def _make_project(
    tmp_path: Path,
    *req_contents: str,
    config_toml: str = CONFIG_REQUIRE_HASH,
    filename: str = "requirements.md",
) -> Path:
    """Create a minimal project with config and spec file(s)."""
    config_path = tmp_path / ".elspais.toml"
    config_path.write_text(config_toml)

    spec_dir = tmp_path / "spec"
    spec_dir.mkdir()

    combined = "\n".join(req_contents)
    (spec_dir / filename).write_text(combined)

    return tmp_path


def _build_graph(project: Path):
    """Build a FederatedGraph for the test project."""
    from elspais.graph.factory import build_graph

    return build_graph(
        spec_dirs=[project / "spec"],
        config_path=project / ".elspais.toml",
        repo_root=project,
        scan_code=False,
        scan_tests=False,
    )


def _load_config(project: Path) -> dict[str, Any]:
    """Load configuration from a test project."""
    from elspais.config import get_config

    return get_config(config_path=project / ".elspais.toml")


# ---------------------------------------------------------------------------
# Tests: collect_errors
# ---------------------------------------------------------------------------


class TestCollectErrors:
    """Tests for errors.collect_errors().

    Validates REQ-p00002-A: format error and no-assertion collection.
    """

    def test_REQ_p00002_A_collect_format_errors(self, tmp_path: Path) -> None:
        """A requirement violating require_hash should appear in format_errors."""
        project = _make_project(tmp_path, REQ_MISSING_HASH)
        graph = _build_graph(project)
        config = _load_config(project)

        from elspais.commands.errors import collect_errors

        data = collect_errors(graph, config, exclude_status=set())

        assert (
            len(data.format_errors) >= 1
        ), f"Expected at least 1 format error, got {len(data.format_errors)}"

        ids = [e.req_id for e in data.format_errors]
        assert "REQ-d00001" in ids, f"REQ-d00001 should have a format error, got {ids}"

        entry = next(e for e in data.format_errors if e.req_id == "REQ-d00001")
        assert entry.rule == "require_hash"
        assert entry.file_path is not None

    def test_REQ_p00002_A_collect_no_assertions(self, tmp_path: Path) -> None:
        """A requirement with zero assertions should appear in no_assertions."""
        project = _make_project(tmp_path, REQ_NO_ASSERTIONS)
        graph = _build_graph(project)
        config = _load_config(project)

        from elspais.commands.errors import collect_errors

        data = collect_errors(graph, config, exclude_status=set())

        assert (
            len(data.no_assertions) >= 1
        ), f"Expected at least 1 no-assertions entry, got {len(data.no_assertions)}"

        ids = [e.req_id for e in data.no_assertions]
        assert "REQ-d00002" in ids, f"REQ-d00002 should be flagged, got {ids}"

        entry = next(e for e in data.no_assertions if e.req_id == "REQ-d00002")
        assert entry.rule == "no_assertions"
        assert "not testable" in entry.message.lower()

    def test_REQ_p00002_A_collect_good_req_no_errors(self, tmp_path: Path) -> None:
        """A well-formed requirement should produce no errors."""
        project = _make_project(tmp_path, REQ_GOOD)
        graph = _build_graph(project)
        config = _load_config(project)

        from elspais.commands.errors import collect_errors

        data = collect_errors(graph, config, exclude_status=set())

        good_format = [e for e in data.format_errors if e.req_id == "REQ-d00003"]
        good_noassert = [e for e in data.no_assertions if e.req_id == "REQ-d00003"]
        assert good_format == [], f"Good req should have no format errors: {good_format}"
        assert good_noassert == [], f"Good req should have no no-assertion entries: {good_noassert}"

    def test_REQ_p00002_A_collect_excludes_status(self, tmp_path: Path) -> None:
        """Requirements with excluded status should be skipped."""
        project = _make_project(tmp_path, REQ_MISSING_HASH)
        graph = _build_graph(project)
        config = _load_config(project)

        from elspais.commands.errors import collect_errors

        data = collect_errors(graph, config, exclude_status={"Draft"})

        draft_errors = [e for e in data.format_errors if e.req_id == "REQ-d00001"]
        assert draft_errors == [], "Draft status should be excluded"


# ---------------------------------------------------------------------------
# Tests: render_error_text
# ---------------------------------------------------------------------------


class TestRenderErrorText:
    """Tests for errors.render_error_text().

    Validates REQ-p00002-A: text rendering of error sections.
    """

    def test_REQ_p00002_A_render_text_format(self, tmp_path: Path) -> None:
        """Text rendering should include section header, count, req IDs, and rules."""
        project = _make_project(tmp_path, REQ_MISSING_HASH, REQ_NO_ASSERTIONS)
        graph = _build_graph(project)
        config = _load_config(project)

        from elspais.commands.errors import collect_errors, render_error_text

        data = collect_errors(graph, config, exclude_status=set())

        text_fmt = render_error_text("format_errors", data)
        assert "FORMAT ERRORS" in text_fmt
        assert "REQ-d00001" in text_fmt
        assert "require_hash" in text_fmt

        text_na = render_error_text("no_assertions", data)
        assert "NO ASSERTIONS" in text_na
        assert "REQ-d00002" in text_na
        assert "no_assertions" in text_na

    def test_REQ_p00002_A_render_text_empty_section(self) -> None:
        """An empty error type should render 'none'."""
        from elspais.commands.errors import ErrorData, render_error_text

        data = ErrorData()
        text = render_error_text("format_errors", data)
        assert "none" in text.lower()


# ---------------------------------------------------------------------------
# Tests: render_error_markdown
# ---------------------------------------------------------------------------


class TestRenderErrorMarkdown:
    """Tests for errors.render_error_markdown().

    Validates REQ-p00002-A: markdown table rendering of error sections.
    """

    def test_REQ_p00002_A_render_markdown_format(self, tmp_path: Path) -> None:
        """Markdown rendering should produce a table with header and data rows."""
        project = _make_project(tmp_path, REQ_MISSING_HASH, REQ_NO_ASSERTIONS)
        graph = _build_graph(project)
        config = _load_config(project)

        from elspais.commands.errors import collect_errors, render_error_markdown

        data = collect_errors(graph, config, exclude_status=set())

        md_fmt = render_error_markdown("format_errors", data)
        assert "## FORMAT ERRORS" in md_fmt
        assert "| Requirement |" in md_fmt
        assert "REQ-d00001" in md_fmt

        md_na = render_error_markdown("no_assertions", data)
        assert "## NO ASSERTIONS" in md_na
        assert "| Requirement |" in md_na
        assert "REQ-d00002" in md_na

    def test_REQ_p00002_A_render_markdown_empty_section(self) -> None:
        """An empty error type should render 'No errors found'."""
        from elspais.commands.errors import ErrorData, render_error_markdown

        data = ErrorData()
        md = render_error_markdown("format_errors", data)
        assert "No errors found" in md


# ---------------------------------------------------------------------------
# Tests: run (CLI entry point)
# ---------------------------------------------------------------------------


class TestRunCommand:
    """Tests for errors.run() CLI entry point.

    Validates REQ-p00002-A: end-to-end errors command with text output.
    """

    def test_REQ_p00002_A_errors_run_text_output(self, tmp_path: Path, capsys) -> None:
        """Running errors with text format should print format errors and no-assertions."""
        project = _make_project(tmp_path, REQ_MISSING_HASH, REQ_NO_ASSERTIONS)

        args = argparse.Namespace(
            format="text",
            spec_dir=project / "spec",
            config=project / ".elspais.toml",
            status=["Draft"],
            output=None,
            verbose=False,
            quiet=False,
        )

        from elspais.commands import _engine
        from elspais.commands.errors import run

        # Clear engine cache so it picks up our test project
        _engine._local_graph = None
        _engine._local_config = None

        old_cwd = os.getcwd()
        os.chdir(project)
        try:
            rc = run(args)
        finally:
            os.chdir(old_cwd)
            # Clear cache again to avoid polluting other tests
            _engine._local_graph = None
            _engine._local_config = None

        assert rc == 0

        captured = capsys.readouterr()
        assert "FORMAT ERRORS" in captured.out
        assert "REQ-d00001" in captured.out
        assert "NO ASSERTIONS" in captured.out
        assert "REQ-d00002" in captured.out
