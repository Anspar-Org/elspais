"""Fix command behavior for section header depth (REQ-d00250-E)."""

# Verifies: REQ-d00250-E
import argparse
import contextlib
import io
from pathlib import Path

CONFIG_TOML = """\
version = 3

[project]
name = "test-section-depth"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]

[changelog]
hash_current = false
"""


def _make_project(tmp_path: Path, spec_content: str) -> Path:
    """Create a minimal project with config and a single spec file."""
    config_path = tmp_path / ".elspais.toml"
    config_path.write_text(CONFIG_TOML)

    spec_dir = tmp_path / "spec"
    spec_dir.mkdir()

    (spec_dir / "f.md").write_text(spec_content)
    return tmp_path


def _run_fix(project: Path, dry_run: bool = False) -> tuple[int, str, str]:
    """Run elspais fix against project; return (exit_code, stdout, stderr)."""
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


def test_fix_dry_run_lists_section_depth_violation(tmp_path):
    spec = (
        "## REQ-d00001: T\n\n"
        "**Level**: dev | **Status**: Active | **Implements**: -\n\n"
        "## Assertions\n\n"
        "A. X.\n\n"
        "*End* *T* | **Hash**: -\n"
    )
    project = _make_project(tmp_path, spec)
    code, out, _ = _run_fix(project, dry_run=True)
    assert code == 0, f"dry-run should succeed, got exit {code}; out={out!r}"
    assert "REQ-d00001" in out
    assert "canonicalize section header depth" in out


def test_fix_canonicalizes_section_depth(tmp_path):
    spec = (
        "## REQ-d00001: T\n\n"
        "**Level**: dev | **Status**: Active | **Implements**: -\n\n"
        "## Assertions\n\n"
        "A. X.\n\n"
        "*End* *T* | **Hash**: -\n"
    )
    project = _make_project(tmp_path, spec)
    code, _, _ = _run_fix(project, dry_run=False)
    assert code == 0
    after = (project / "spec" / "f.md").read_text()
    assert "### Assertions" in after, f"after:\n{after}"
    # Second run is no-op
    code2, out2, _ = _run_fix(project, dry_run=True)
    assert code2 == 0
    assert "section header depth" not in out2


def test_fix_cannot_resolve_h6_req(tmp_path):
    spec = (
        "###### REQ-d00001: T\n\n"
        "**Level**: dev | **Status**: Active | **Implements**: -\n\n"
        "###### Assertions\n\n"
        "A. X.\n\n"
        "*End* *T* | **Hash**: -\n"
    )
    project = _make_project(tmp_path, spec)
    original = (project / "spec" / "f.md").read_text()
    code, _, err = _run_fix(project, dry_run=False)
    assert code == 1, f"expected exit 1 for H6 unfixable; got {code}; stderr={err!r}"
    assert "REQ-d00001" in err
    assert "section header depth" in err
    after = (project / "spec" / "f.md").read_text()
    assert after == original, "H6 file must be untouched on fix"


def test_fix_h6_dry_run_also_reports_unfixable(tmp_path):
    spec = (
        "###### REQ-d00001: T\n\n"
        "**Level**: dev | **Status**: Active | **Implements**: -\n\n"
        "###### Assertions\n\n"
        "A. X.\n\n"
        "*End* *T* | **Hash**: -\n"
    )
    project = _make_project(tmp_path, spec)
    code, _, err = _run_fix(project, dry_run=True)
    assert code == 1
    assert "REQ-d00001" in err
    assert "section header depth" in err


def test_fix_skips_files_containing_unfixable_reqs(tmp_path):
    """A fixable REQ in the same FILE as an unfixable REQ must not be silently
    rewritten — render_save rewrites whole files, so touching such a file
    would canonicalize the unfixable req alongside the fixable siblings."""
    # File contains both:
    #   - REQ-d00001: H6 with section blocks (unfixable)
    #   - REQ-d00002: H2 with H2 ## Assertions (fixable — section_header_depth)
    spec = (
        "###### REQ-d00001: H6 Unfixable\n\n"
        "**Level**: dev | **Status**: Active | **Implements**: -\n\n"
        "###### Assertions\n\n"
        "A. X.\n\n"
        "*End* *H6 Unfixable* | **Hash**: -\n"
        "\n---\n\n"
        "## REQ-d00002: Fixable Sibling\n\n"
        "**Level**: dev | **Status**: Active | **Implements**: -\n\n"
        "## Assertions\n\n"
        "A. Y.\n\n"
        "*End* *Fixable Sibling* | **Hash**: -\n"
    )
    project = _make_project(tmp_path, spec)
    original = (project / "spec" / "f.md").read_text()

    code, _, err = _run_fix(project, dry_run=False)
    assert code == 1, f"expected exit 1; got {code}; stderr={err!r}"
    assert "REQ-d00001" in err  # unfixable cannot-fix line
    # REQ-d00002 is fixable but should be reported as skipped, not applied
    assert "REQ-d00002" in err and "unfixable requirement" in err

    after = (project / "spec" / "f.md").read_text()
    assert after == original, (
        "File containing an unfixable req must be left untouched even when "
        "it has fixable siblings."
    )
