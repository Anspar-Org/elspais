# Verifies: REQ-p00004-A, REQ-d00131-P, REQ-p00002-A
"""Tests for first-hash acquisition: a requirement whose *End* marker
carries NO hash at all.

The bulk fix path (``fix_cmd._detect_fixable`` -> ``_fix_parse_dirty``)
and the single-requirement path (``fix_cmd._fix_single``) must agree that
an absent stored hash is a fixable condition, and must stamp the same
value: the computed 8-char hash when there is hashable content, or the
reserved ``N/A`` sentinel when there is not (REQ-d00131-P).

Also pins REQ-p00002-A: ``elspais errors`` must not hide format
violations that the health checks it drills into do report.
"""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures / helpers
# ─────────────────────────────────────────────────────────────────────────────

# normalized-text hash mode is the default. Changelog enforcement is turned
# OFF so the hash defect is isolated: a Draft/Active requirement without a
# changelog must not be flagged for a changelog reason.
CONFIG_TOML = """\
version = 3

[project]
name = "test"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]

[changelog]
hash_current = false
"""

# Changelog enforcement ON, with an author source that resolves without a
# prompt (id_source != "gh" skips the `gh api user` subprocess; the tests
# that use this config also set GIT_AUTHOR_NAME/GIT_AUTHOR_EMAIL, which are
# the highest-precedence lookup source in utilities/changelog_author.py).
CONFIG_TOML_CHANGELOG = """\
version = 3

[project]
name = "test"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]

[changelog]
hash_current = true
id_source = "manual"
"""

# require_hash is stated explicitly so the format rule definitely fires.
CONFIG_TOML_REQUIRE_HASH = """\
version = 3

[project]
name = "test"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]

[changelog]
hash_current = false

[rules.format]
require_hash = true
"""

# Draft requirement WITH assertions and NO hash on the End marker.
# Everything else about it is canonical, so the only fixable condition
# is the absent hash.
REQ_ASSERTIONS_NO_HASH = """\
# REQ-d00001: Hashless Requirement

**Level**: DEV | **Status**: Draft | **Implements**: -

Some body text here.

## Assertions

A. The system shall do something important.

B. The system shall do something else.

*End* *Hashless Requirement*
---
"""

# Draft requirement with NO assertions and NO hash: nothing to hash, so
# the reserved "N/A" sentinel is the correct stamped value.
REQ_NO_ASSERTIONS_NO_HASH = """\
# REQ-d00002: Nothing To Hash

**Level**: DEV | **Status**: Draft | **Implements**: -

Some body text but no assertions section.

*End* *Nothing To Hash*
---
"""

# Active requirement, assertions, no hash, no Changelog section — used for
# the changelog-anchoring test.
REQ_ACTIVE_ASSERTIONS_NO_HASH = """\
# REQ-d00003: Active Hashless Requirement

**Level**: DEV | **Status**: Active | **Implements**: -

Some body text here.

## Assertions

A. The system shall do something important.

B. The system shall do something else.

*End* *Active Hashless Requirement*
---
"""

HASH_RE = re.compile(r"\*\*Hash\*\*: ([0-9a-f]{8})")
END_LINE_RE = re.compile(r"^\*End\*.*$", re.MULTILINE)


def _make_project(
    tmp_path: Path,
    req_content: str,
    config_toml: str = CONFIG_TOML,
    filename: str = "requirements.md",
) -> Path:
    """Create a minimal project with config and a single spec file."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / ".elspais.toml").write_text(config_toml)
    spec_dir = tmp_path / "spec"
    spec_dir.mkdir()
    (spec_dir / filename).write_text(req_content)
    return tmp_path


def _make_fix_args(
    project: Path,
    req_id: str | None,
    *,
    dry_run: bool = False,
    message: str | None = None,
) -> argparse.Namespace:
    """Build an argparse.Namespace matching what fix_cmd.run expects."""
    return argparse.Namespace(
        req_id=req_id,
        dry_run=dry_run,
        spec_dir=project / "spec",
        config=project / ".elspais.toml",
        verbose=False,
        quiet=False,
        message=message,
    )


def _build_graph(project: Path):
    """Build a graph for the test project."""
    from elspais.graph.factory import build_graph

    return build_graph(
        spec_dirs=[project / "spec"],
        config_path=project / ".elspais.toml",
        repo_root=project,
        scan_code=False,
        scan_tests=False,
    )


def _find_node(graph, req_id: str):
    """Find a requirement node by ID."""
    from elspais.graph import NodeKind

    for n in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        if n.id == req_id:
            return n
    return None


def _run_fix(project: Path, args: argparse.Namespace) -> int:
    """Run fix_cmd.run with cwd pinned to the project root."""
    from elspais.commands.fix_cmd import run

    old_cwd = os.getcwd()
    os.chdir(project)
    try:
        return run(args)
    finally:
        os.chdir(old_cwd)


def _end_line(text: str) -> str:
    """Return the requirement's *End* marker line."""
    m = END_LINE_RE.search(text)
    assert m is not None, f"No *End* marker found in:\n{text}"
    return m.group(0)


# ─────────────────────────────────────────────────────────────────────────────
# Tests: first hash acquisition
# ─────────────────────────────────────────────────────────────────────────────


class TestFirstHashAcquisition:
    """Pins the bulk fix path's treatment of an absent stored hash."""

    def test_detect_fixable_flags_requirement_with_no_stored_hash(self, tmp_path):
        """_detect_fixable must report 'hash_mismatch' for a requirement
        that has hashable content but no hash in its End marker.
        """
        from elspais.commands.fix_cmd import _detect_fixable

        project = _make_project(tmp_path, REQ_ASSERTIONS_NO_HASH)

        old_cwd = os.getcwd()
        os.chdir(project)
        try:
            graph = _build_graph(project)
            node = _find_node(graph, "REQ-d00001")
            assert node is not None, "REQ-d00001 not found in graph"
            assert not node.hash, f"Fixture must have no stored hash, got {node.hash!r}"
            hash_mode = getattr(graph, "hash_mode", "full-text")
            reasons = _detect_fixable(node, hash_mode, False)
        finally:
            os.chdir(old_cwd)

        assert "hash_mismatch" in reasons, (
            f"An absent stored hash must register as fixable; got reasons={reasons}"
        )

    def test_bulk_fix_dry_run_reports_requirement_with_no_stored_hash(self, tmp_path, capsys):
        """Bulk fix --dry-run must name a hashless requirement in its
        output, and must not write to the spec file.
        """
        project = _make_project(tmp_path, REQ_ASSERTIONS_NO_HASH)
        spec_file = project / "spec" / "requirements.md"
        before = spec_file.read_bytes()

        rc = _run_fix(project, _make_fix_args(project, None, dry_run=True))
        assert rc == 0, f"dry-run fix should succeed, got exit code {rc}"

        out = capsys.readouterr().out
        after = spec_file.read_bytes()

        assert after == before, "Dry run must not modify the spec file"
        assert "REQ-d00001" in out, (
            f"Bulk dry-run must report the hashless requirement; output was:\n{out}"
        )

    def test_bulk_fix_dry_run_shows_hash_value_that_will_be_written(self, tmp_path, capsys):
        """Bulk fix --dry-run must show the hash value it is about to
        write, not merely name the condition — the same transition the
        single-requirement path already prints.
        """
        preview_project = _make_project(tmp_path / "preview", REQ_ASSERTIONS_NO_HASH)
        applied_project = _make_project(tmp_path / "applied", REQ_ASSERTIONS_NO_HASH)

        rc_preview = _run_fix(preview_project, _make_fix_args(preview_project, None, dry_run=True))
        assert rc_preview == 0, f"dry-run fix should succeed, got exit code {rc_preview}"
        preview_out = capsys.readouterr().out

        # Derive the expected value from what a real bulk fix actually
        # writes, so the test pins "the preview matches the write" rather
        # than any particular digest.
        rc_applied = _run_fix(applied_project, _make_fix_args(applied_project, None))
        assert rc_applied == 0, f"fix should succeed, got exit code {rc_applied}"

        applied_content = (applied_project / "spec" / "requirements.md").read_text()
        written = HASH_RE.search(applied_content)
        assert written is not None, (
            "Real bulk fix must stamp a computed hash for this fixture; "
            f"End line was: {_end_line(applied_content)!r}"
        )
        expected = written.group(1)

        assert expected in preview_out, (
            f"Bulk dry-run must show the hash it will write ({expected!r}); output was:\n"
            f"{preview_out}"
        )

    def test_bulk_fix_writes_computed_hash_for_requirement_with_no_stored_hash(self, tmp_path):
        """Bulk fix must stamp a real 8-hex-char hash on a requirement
        that has assertions but no stored hash.
        """
        project = _make_project(tmp_path, REQ_ASSERTIONS_NO_HASH)
        spec_file = project / "spec" / "requirements.md"

        rc = _run_fix(project, _make_fix_args(project, None))
        assert rc == 0, f"fix should succeed, got exit code {rc}"

        content = spec_file.read_text()
        m = HASH_RE.search(content)
        assert m is not None, (
            "End marker must carry a computed 8-hex-char hash after fix; "
            f"End line was: {_end_line(content)!r}"
        )

    def test_bulk_fix_writes_sentinel_for_requirement_with_nothing_to_hash(self, tmp_path):
        """Bulk fix must stamp the reserved N/A sentinel on a requirement
        with no hashable content and no stored hash (REQ-d00131-P).
        """
        project = _make_project(tmp_path, REQ_NO_ASSERTIONS_NO_HASH)
        spec_file = project / "spec" / "requirements.md"

        rc = _run_fix(project, _make_fix_args(project, None))
        assert rc == 0, f"fix should succeed, got exit code {rc}"

        content = spec_file.read_text()
        assert "**Hash**: N/A" in content, (
            "End marker must carry the N/A sentinel after fix; "
            f"End line was: {_end_line(content)!r}"
        )

    def test_bulk_and_single_agree_on_requirement_with_no_stored_hash(self, tmp_path):
        """The bulk and single fix paths must produce an identical End
        marker for the same hashless requirement.
        """
        bulk_project = _make_project(tmp_path / "bulk", REQ_ASSERTIONS_NO_HASH)
        single_project = _make_project(tmp_path / "single", REQ_ASSERTIONS_NO_HASH)

        rc_bulk = _run_fix(bulk_project, _make_fix_args(bulk_project, None))
        assert rc_bulk == 0, f"bulk fix should succeed, got exit code {rc_bulk}"

        rc_single = _run_fix(single_project, _make_fix_args(single_project, "REQ-d00001"))
        assert rc_single == 0, f"single fix should succeed, got exit code {rc_single}"

        bulk_end = _end_line((bulk_project / "spec" / "requirements.md").read_text())
        single_end = _end_line((single_project / "spec" / "requirements.md").read_text())

        assert bulk_end == single_end, (
            "Bulk and single fix paths disagree on the End marker:\n"
            f"  bulk:   {bulk_end!r}\n"
            f"  single: {single_end!r}"
        )

    def test_first_hash_acquisition_records_computed_hash_in_changelog(self, tmp_path, monkeypatch):
        """The changelog entry written on first hash acquisition must be
        anchored to the newly computed hash, not left blank or stale.
        """
        monkeypatch.setenv("GIT_AUTHOR_NAME", "Test Author")
        monkeypatch.setenv("GIT_AUTHOR_EMAIL", "test@example.com")

        project = _make_project(
            tmp_path,
            REQ_ACTIVE_ASSERTIONS_NO_HASH,
            config_toml=CONFIG_TOML_CHANGELOG,
        )
        spec_file = project / "spec" / "requirements.md"

        rc = _run_fix(project, _make_fix_args(project, None))
        assert rc == 0, f"fix should succeed, got exit code {rc}"

        content = spec_file.read_text()
        end_line = _end_line(content)
        end_match = HASH_RE.search(end_line)
        assert end_match is not None, (
            f"End marker must carry a computed hash after fix; got {end_line!r}"
        )
        stamped = end_match.group(1)

        changelog_hashes = [
            m.group(1)
            for line in content.splitlines()
            if line.lstrip().startswith("- ")
            for m in [re.search(r"\|\s*([0-9a-fA-F]{8}|N/A)\s*\|", line)]
            if m
        ]
        assert changelog_hashes, (
            f"Expected a Changelog entry after first hash acquisition; content:\n{content}"
        )
        assert stamped in changelog_hashes, (
            "Changelog entry must be anchored to the newly acquired hash "
            f"{stamped!r}; changelog carried {changelog_hashes!r}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Tests: errors command status handling
# ─────────────────────────────────────────────────────────────────────────────


class TestErrorsStatusParity:
    """Pins REQ-p00002-A: `errors` must not hide what `checks` counts."""

    def test_errors_reports_format_errors_for_draft_requirements(self, tmp_path):
        """compute_errors' default status handling must not drop format
        violations on Draft requirements — the health checks it drills
        into apply no status filter.
        """
        from elspais.commands.errors import collect_errors, compute_errors
        from elspais.config import get_config

        project = _make_project(
            tmp_path,
            REQ_ASSERTIONS_NO_HASH,
            config_toml=CONFIG_TOML_REQUIRE_HASH,
        )

        old_cwd = os.getcwd()
        os.chdir(project)
        try:
            config = get_config(project / ".elspais.toml")
            graph = _build_graph(project)

            unfiltered = collect_errors(graph, config, exclude_status=set())
            defaulted = compute_errors(graph, config, {})
        finally:
            os.chdir(old_cwd)

        # Control: the violation genuinely exists on this Draft requirement.
        assert any(e.rule == "require_hash" for e in unfiltered.format_errors), (
            "Fixture must produce a require_hash violation; got "
            f"{[(e.req_id, e.rule) for e in unfiltered.format_errors]}"
        )

        assert defaulted["format_errors"], (
            "compute_errors must report the Draft requirement's format error; "
            "the default status handling is hiding what the health checks count"
        )
