"""Auto-fix changelog entries are emitted only for content changes, not
formatting-only canonicalizations (REQ-d00330-E).

A `## Assertions` → `### Assertions` rewrite under an H2 requirement does
not change the requirement's semantic body — the hash is unchanged, the
assertion text is unchanged, only the rendered depth differs. Emitting an
"Auto-fix: canonicalize section header depth" changelog entry on every
such run is noise and produces consecutive-identical duplicate entries
when `fix` runs more than once on partially-canonical content. A changelog
whose latest entry records another hash is brought into agreement even when
the only other change is one of form (REQ-d00330-B).
"""

import argparse
import contextlib
import io
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _fake_author(monkeypatch):
    """Stub git author lookup so the changelog-emitting path works on
    runners (CI, fresh containers) that lack `git config user.name`."""
    fake = {"name": "Test Author", "id": "test@example.com"}
    monkeypatch.setattr(
        "elspais.commands.fix_cmd._get_author",
        lambda _config: fake,
    )


CONFIG_TOML = """\
version = 5

[project]
name = "test-content-aware"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]

[changelog]
hash_current = true
id_source = "elspais"
"""


def _make_project(tmp_path: Path, spec_content: str) -> Path:
    config_path = tmp_path / ".elspais.toml"
    config_path.write_text(CONFIG_TOML)
    spec_dir = tmp_path / "spec"
    spec_dir.mkdir()
    (spec_dir / "f.md").write_text(spec_content)
    return tmp_path


def _run_fix(project: Path, dry_run: bool = False) -> tuple[int, str, str]:
    from elspais.commands.fix_cmd import run

    args = argparse.Namespace(
        spec_dir=project / "spec",
        config=project / ".elspais.toml",
        dry_run=dry_run,
        git_root=project,
        req_id=None,
    )
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = run(args)
    return code, stdout.getvalue(), stderr.getvalue()


def _count_section_depth_entries(content: str) -> int:
    return content.count("Auto-fix: canonicalize section header depth")


def _force_section_depth_violation(project: Path) -> None:
    """After a canonical fix run, downgrade `### Assertions` back to `##` so
    the only outstanding parse_dirty reason on the next run is
    `section_header_depth` (the stored hash is already correct, no other
    dirty reasons fire). Tests the formatting-only partition cleanly."""
    f = project / "spec" / "f.md"
    text = f.read_text()
    # Only rewrite the `### Assertions` we just produced (depth 3) — leave
    # any other `###` lines alone.
    text = text.replace("\n### Assertions\n", "\n## Assertions\n", 1)
    f.write_text(text)


# Verifies: REQ-d00330-E
def test_second_run_does_not_emit_duplicate_changelog(tmp_path):
    """Running fix on a section-depth-only violation a second time must not
    re-add a `canonicalize section header depth` changelog entry.

    The regression that motivated this fix: every `elspais fix` invocation
    on a file with `section_header_depth` parse_dirty emitted a fresh entry,
    so files that were canonicalized over multiple sessions accumulated
    duplicate consecutive entries (68 such duplicates were dedup'd in 56f1769).
    """
    spec = (
        "## REQ-d00001: Test Requirement\n\n"
        "**Level**: dev | **Status**: Active | **Implements**: -\n\n"
        "## Assertions\n\n"
        "A. The system shall do X.\n\n"
        "## Changelog\n\n"
        "- 2026-04-01 | abcdef01 | - | Seed (s@e.com) | initial\n\n"
        "*End* *Test Requirement* | **Hash**: -\n"
    )
    project = _make_project(tmp_path, spec)

    # First run: stamps hash, canonicalizes ## Assertions -> ###.
    # An auto-fix entry is added (hash was missing, so hash_mismatch fired).
    code, _, _ = _run_fix(project, dry_run=False)
    assert code == 0
    after1 = (project / "spec" / "f.md").read_text()
    assert "### Assertions" in after1
    first_entries = _count_section_depth_entries(after1)

    # Downgrade ### Assertions -> ## so that only section_header_depth fires
    # on the next run (stored hash is correct now, no hash_mismatch).
    _force_section_depth_violation(project)

    # Second run: only section_header_depth — must NOT add a new entry.
    code2, _, _ = _run_fix(project, dry_run=False)
    assert code2 == 0
    after2 = (project / "spec" / "f.md").read_text()
    assert "### Assertions" in after2, "Section should be re-canonicalized"
    second_entries = _count_section_depth_entries(after2)
    assert second_entries == first_entries, (
        f"Second formatting-only fix must not add a new "
        f"`canonicalize section header depth` changelog entry. "
        f"Before second run: {first_entries}; after: {second_entries}."
    )


# Verifies: REQ-d00330-E
def test_second_run_is_full_noop(tmp_path):
    """After a clean fix, re-running fix must produce no further changes —
    the file content (including changelog) must be byte-identical."""
    spec = (
        "## REQ-d00001: Test\n\n"
        "**Level**: dev | **Status**: Active | **Implements**: -\n\n"
        "## Assertions\n\n"
        "A. The system shall do X.\n\n"
        "## Changelog\n\n"
        "- 2026-04-01 | abcdef01 | - | Seed (s@e.com) | initial\n\n"
        "*End* *Test* | **Hash**: -\n"
    )
    project = _make_project(tmp_path, spec)

    _run_fix(project, dry_run=False)
    after1 = (project / "spec" / "f.md").read_text()

    # Downgrade depth and re-run; only section_header_depth fires.
    _force_section_depth_violation(project)
    _run_fix(project, dry_run=False)
    after2 = (project / "spec" / "f.md").read_text()

    assert after1 == after2, (
        f"Two-step canonicalize then re-canonicalize must produce "
        f"identical output.\n--- after first ---\n{after1}\n"
        f"--- after second ---\n{after2}"
    )


# Verifies: REQ-d00330-B
def test_content_change_still_adds_changelog_entry(tmp_path):
    """A real content change (hash mismatch) still adds a changelog entry —
    the partition only suppresses formatting-only fixes, not legitimate
    content updates."""
    # H1 req with canonical sections so section_header_depth does NOT fire.
    # The stored hash deliberately disagrees with the body, so hash_mismatch
    # will fire as the sole reason.
    spec = (
        "# REQ-d00001: Test\n\n"
        "**Level**: dev | **Status**: Active | **Implements**: -\n\n"
        "## Assertions\n\n"
        "A. The system shall do X.\n\n"
        "## Changelog\n\n"
        "- 2026-04-01 | abcdef01 | - | Seed (s@e.com) | initial\n\n"
        "*End* *Test* | **Hash**: deadbeef\n"
    )
    project = _make_project(tmp_path, spec)

    code, _, _ = _run_fix(project, dry_run=False)
    assert code == 0

    after = (project / "spec" / "f.md").read_text()
    # End-marker hash should be corrected.
    end_line = next(ln for ln in after.splitlines() if ln.startswith("*End*"))
    assert "deadbeef" not in end_line, f"End-marker hash unchanged: {end_line!r}"
    assert "Auto-fix:" in after, (
        f"A real content change (hash mismatch) must produce an auto-fix "
        f"changelog entry.\nAfter:\n{after}"
    )


def _changelog_lines(content: str) -> list[str]:
    """The changelog entry lines of the one requirement in *content*, newest first."""
    lines = content.splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.endswith(" Changelog"))
    entries = []
    for ln in lines[start + 1 :]:
        if ln.startswith("*End*"):
            break
        if ln.startswith("- "):
            entries.append(ln)
    return entries


def _entry_hash(entry: str) -> str:
    return entry.split(" | ")[1]


def _end_marker_hash(content: str) -> str:
    end_line = next(ln for ln in content.splitlines() if ln.startswith("*End*"))
    return end_line.rsplit("**Hash**: ", 1)[1].strip()


# Verifies: REQ-d00330-B
def test_drifted_changelog_beside_form_only_change_is_synced(tmp_path):
    """A changelog whose latest entry records another hash gains one entry
    recording the requirement's hash, even when the only other change the fix
    makes is to a section heading's depth."""
    spec = (
        "## REQ-d00001: Test\n\n"
        "**Level**: dev | **Status**: Active | **Implements**: -\n\n"
        "## Assertions\n\n"
        "A. The system shall do X.\n\n"
        "## Changelog\n\n"
        "- 2026-04-01 | abcdef01 | - | Seed (s@e.com) | initial\n\n"
        "*End* *Test* | **Hash**: -\n"
    )
    project = _make_project(tmp_path, spec)
    code, _, _ = _run_fix(project, dry_run=False)
    assert code == 0
    canonical = (project / "spec" / "f.md").read_text()
    req_hash = _end_marker_hash(canonical)
    entries_before = _changelog_lines(canonical)
    assert _entry_hash(entries_before[0]) == req_hash

    # The latest entry now records a hash other than the requirement's, and
    # the Assertions heading sits at the requirement heading's own depth.
    f = project / "spec" / "f.md"
    drifted = canonical.replace(entries_before[0], entries_before[0].replace(req_hash, "0badc0de"))
    drifted = drifted.replace("\n### Assertions\n", "\n## Assertions\n", 1)
    f.write_text(drifted)

    code2, _, err2 = _run_fix(project, dry_run=False)
    assert code2 == 0, f"fix failed: {err2}"
    after = f.read_text()
    assert "\n### Assertions\n" in after, f"heading not moved to depth 3:\n{after}"
    assert _end_marker_hash(after) == req_hash
    entries_after = _changelog_lines(after)
    assert len(entries_after) == len(entries_before) + 1, (
        f"expected exactly one new changelog entry.\nAfter:\n{after}"
    )
    assert _entry_hash(entries_after[0]) == req_hash, (
        f"latest changelog entry must record the requirement's hash {req_hash}.\nAfter:\n{after}"
    )
