"""Tests for assertion spacing canonicalization at parse time.

Validates REQ-d00131-B: assertion rendering produces canonical blank-line spacing.
"""

from pathlib import Path

from elspais.graph.factory import build_graph

CONFIG_TOML = """\
version = 3

[project]
name = "test"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]
"""

# Spec file with consecutive assertions (no blank lines between them)
SPEC_NO_SPACING = """\
## REQ-d00001: Test Requirement

**Level**: dev | **Status**: Active | **Implements**: -

Body text here.

## Assertions

A. First assertion text
B. Second assertion text
C. Third assertion text

*End* *Test Requirement* | **Hash**: 00000000
---
"""

# Spec file with proper assertion spacing
SPEC_GOOD_SPACING = """\
## REQ-d00001: Test Requirement

**Level**: dev | **Status**: Active | **Implements**: -

Body text here.

## Assertions

A. First assertion text

B. Second assertion text

C. Third assertion text

*End* *Test Requirement* | **Hash**: 00000000
---
"""


def _make_project(tmp_path: Path, spec_content: str) -> Path:
    """Create a minimal project with config and a single spec file."""
    config_path = tmp_path / ".elspais.toml"
    config_path.write_text(CONFIG_TOML)
    spec_dir = tmp_path / "spec"
    spec_dir.mkdir()
    (spec_dir / "test.md").write_text(spec_content)
    return tmp_path


class TestREQ_d00131_B_assertion_spacing_canonicalization:
    """Validates REQ-d00131-B: assertion spacing is canonicalized at parse time."""

    def test_REQ_d00131_B_consecutive_assertions_marked_dirty(self, tmp_path):
        """Consecutive assertions without blank lines should mark requirement dirty."""
        project = _make_project(tmp_path, SPEC_NO_SPACING)
        graph = build_graph(
            spec_dirs=[project / "spec"],
            config_path=project / ".elspais.toml",
            repo_root=project,
        )
        node = graph.find_by_id("REQ-d00001")
        assert node is not None
        reasons = node.get_field("parse_dirty_reasons") or []
        assert "assertion_spacing" in reasons, f"Expected 'assertion_spacing' in {reasons}"

    def test_REQ_d00131_B_proper_spacing_not_dirty(self, tmp_path):
        """Assertions with proper blank-line spacing should not trigger spacing dirty."""
        project = _make_project(tmp_path, SPEC_GOOD_SPACING)
        graph = build_graph(
            spec_dirs=[project / "spec"],
            config_path=project / ".elspais.toml",
            repo_root=project,
        )
        node = graph.find_by_id("REQ-d00001")
        assert node is not None
        reasons = node.get_field("parse_dirty_reasons") or []
        assert "assertion_spacing" not in reasons

    def test_REQ_d00131_B_render_save_fixes_spacing(self, tmp_path):
        """render_save on dirty file should produce canonical assertion spacing."""
        from elspais.graph.render import render_save

        project = _make_project(tmp_path, SPEC_NO_SPACING)
        graph = build_graph(
            spec_dirs=[project / "spec"],
            config_path=project / ".elspais.toml",
            repo_root=project,
        )
        render_save(graph)

        # Re-read the file and check spacing
        content = (project / "spec" / "test.md").read_text(encoding="utf-8")
        lines = content.split("\n")
        # Find assertion lines (e.g. "A. ...", "B. ...", "C. ...")
        assertion_indices = [
            i
            for i, line in enumerate(lines)
            if len(line) >= 3 and line[0].isupper() and line[1] == "." and line[2] == " "
        ]
        assert len(assertion_indices) == 3, f"Expected 3 assertions, found {assertion_indices}"
        for i in range(len(assertion_indices) - 1):
            idx = assertion_indices[i]
            next_idx = assertion_indices[i + 1]
            has_blank = any(lines[j].strip() == "" for j in range(idx + 1, next_idx))
            assert (
                has_blank
            ), f"No blank line between assertions at lines {idx + 1} and {next_idx + 1}"
