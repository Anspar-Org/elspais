"""Tests for list spacing canonicalization at parse time.

Validates REQ-d00131-D: REMAINDER content is canonicalized for list spacing.
"""

from pathlib import Path

from elspais.graph import NodeKind
from elspais.graph.factory import build_graph
from elspais.graph.relations import EdgeKind

CONFIG_TOML = """\
version = 3

[project]
name = "test"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]
"""

# Spec file with list items missing preceding blank line
SPEC_NO_LIST_SPACING = """\
## REQ-d00001: Test Requirement

**Level**: dev | **Status**: Active | **Implements**: -

Body text here.
- Item one
- Item two

## Assertions

A. First assertion text

*End* *Test Requirement* | **Hash**: 00000000
---
"""

# Spec file with proper list spacing
SPEC_GOOD_LIST_SPACING = """\
## REQ-d00001: Test Requirement

**Level**: dev | **Status**: Active | **Implements**: -

Body text here.

- Item one
- Item two

## Assertions

A. First assertion text

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


class TestREQ_d00131_D_list_spacing_canonicalization:
    """Validates REQ-d00131-D: list spacing in REMAINDER is canonicalized at build time."""

    def test_REQ_d00131_D_missing_list_spacing_marked_dirty(self, tmp_path):
        """List items without preceding blank line should mark requirement dirty."""
        project = _make_project(tmp_path, SPEC_NO_LIST_SPACING)
        graph = build_graph(
            spec_dirs=[project / "spec"],
            config_path=project / ".elspais.toml",
            repo_root=project,
        )
        node = graph.find_by_id("REQ-d00001")
        assert node is not None
        reasons = node.get_field("parse_dirty_reasons") or []
        assert "list_spacing" in reasons, f"Expected 'list_spacing' in {reasons}"

    def test_REQ_d00131_D_proper_list_spacing_not_dirty(self, tmp_path):
        """Lists with proper spacing should not trigger list_spacing dirty."""
        project = _make_project(tmp_path, SPEC_GOOD_LIST_SPACING)
        graph = build_graph(
            spec_dirs=[project / "spec"],
            config_path=project / ".elspais.toml",
            repo_root=project,
        )
        node = graph.find_by_id("REQ-d00001")
        assert node is not None
        reasons = node.get_field("parse_dirty_reasons") or []
        assert "list_spacing" not in reasons

    def test_REQ_d00131_D_render_save_fixes_list_spacing(self, tmp_path):
        """render_save should produce canonical list spacing."""
        from elspais.graph.render import render_save

        project = _make_project(tmp_path, SPEC_NO_LIST_SPACING)
        graph = build_graph(
            spec_dirs=[project / "spec"],
            config_path=project / ".elspais.toml",
            repo_root=project,
        )
        render_save(graph)

        # Re-read the file and check that list items have blank line before them
        content = (project / "spec" / "test.md").read_text(encoding="utf-8")
        lines = content.split("\n")
        for i in range(1, len(lines)):
            if (
                lines[i].startswith("- ")
                and lines[i - 1].strip()
                and not lines[i - 1].startswith("- ")
            ):
                raise AssertionError(
                    f"List item at line {i + 1} missing blank line before it: "
                    f"{lines[i - 1]!r} -> {lines[i]!r}"
                )

    def test_REQ_d00131_D_remainder_text_canonicalized(self, tmp_path):
        """REMAINDER node text should have canonical list spacing after build."""
        project = _make_project(tmp_path, SPEC_NO_LIST_SPACING)
        graph = build_graph(
            spec_dirs=[project / "spec"],
            config_path=project / ".elspais.toml",
            repo_root=project,
        )
        node = graph.find_by_id("REQ-d00001")
        assert node is not None
        # Find the preamble REMAINDER child
        for child in node.iter_children(edge_kinds={EdgeKind.STRUCTURES}):
            if child.kind == NodeKind.REMAINDER and child.get_field("heading") == "preamble":
                text = child.get_field("text") or ""
                text_lines = text.split("\n")
                for j in range(1, len(text_lines)):
                    if (
                        text_lines[j].startswith("- ")
                        and text_lines[j - 1].strip()
                        and not text_lines[j - 1].startswith("- ")
                    ):
                        raise AssertionError(
                            f"REMAINDER text has uncanonicalized list at line {j}: "
                            f"{text_lines[j - 1]!r} -> {text_lines[j]!r}"
                        )
                break
