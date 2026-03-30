# Validates: REQ-p00004-A
"""Tests for _detect_fixable unified fix detection.

Validates REQ-p00004-A: unified fix detection function that inspects
a requirement node and returns a list of reason strings describing
what needs fixing.
"""

from __future__ import annotations

import os
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures / helpers
# ─────────────────────────────────────────────────────────────────────────────

CONFIG_TOML = """\
version = 3

[project]
name = "test"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]

[changelog]
hash_current = true
"""

CONFIG_TOML_NO_CHANGELOG = """\
version = 3

[project]
name = "test"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]
"""

# Active requirement with correct hash placeholder — the hash will be
# computed after the first build so we can create a "clean" version.
REQ_TEMPLATE = """\
# REQ-d00001: Active Requirement

**Level**: DEV | **Status**: Active | **Implements**: -

Some body text here.

## Assertions

A. The system shall do something important.

B. The system shall do something else.

{changelog_section}*End* *Active Requirement* | **Hash**: {hash}
---
"""

CHANGELOG_ENTRY_TEMPLATE = """\
## Changelog

- 2026-01-01 | {hash} | - | Test Author (test@example.com) | Initial

"""


def _make_project(
    tmp_path: Path,
    req_content: str,
    config_toml: str = CONFIG_TOML,
    filename: str = "requirements.md",
) -> Path:
    """Create a minimal project with config and a single spec file."""
    config_path = tmp_path / ".elspais.toml"
    config_path.write_text(config_toml)

    spec_dir = tmp_path / "spec"
    spec_dir.mkdir()

    req_file = spec_dir / filename
    req_file.write_text(req_content)

    return tmp_path


def _build_and_find(project: Path, req_id: str = "REQ-d00001"):
    """Build graph and return the graph, target node, and hash_mode."""
    from elspais.graph import NodeKind
    from elspais.graph.factory import build_graph

    graph = build_graph(
        spec_dirs=[project / "spec"],
        config_path=project / ".elspais.toml",
        repo_root=project,
        scan_code=False,
        scan_tests=False,
    )

    hash_mode = getattr(graph, "hash_mode", "full-text")

    node = None
    for n in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        if n.id == req_id:
            node = n
            break

    assert node is not None, f"{req_id} not found in graph"
    return graph, node, hash_mode


def _compute_correct_hash(project: Path, req_id: str = "REQ-d00001") -> str:
    """Build graph and compute the correct hash for a requirement."""
    from elspais.graph.render import compute_hash_for_node

    _graph, node, hash_mode = _build_and_find(project, req_id)
    return compute_hash_for_node(node, hash_mode) or "N/A"


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestREQ_p00004_A_detect_fixable:
    """Validates REQ-p00004-A: unified fix detection."""

    def test_REQ_p00004_A_clean_node_returns_empty(self, tmp_path):
        """Active requirement with correct hash returns empty list."""
        from elspais.commands.fix_cmd import _detect_fixable

        # First pass: build with wrong hash to discover the correct one
        wrong_hash_content = REQ_TEMPLATE.format(
            hash="placeholder",
            changelog_section="",
        )
        project = _make_project(tmp_path, wrong_hash_content)
        correct_hash = _compute_correct_hash(project)

        # Rebuild with correct hash
        clean_content = REQ_TEMPLATE.format(
            hash=correct_hash,
            changelog_section="",
        )
        (project / "spec" / "requirements.md").write_text(clean_content)

        _graph, node, hash_mode = _build_and_find(project)
        # changelog_enforce=False so missing changelog isn't flagged
        reasons = _detect_fixable(node, hash_mode, changelog_enforce=False)

        assert reasons == [], f"Clean node should have no fixable reasons, got {reasons}"

    def test_REQ_p00004_A_parse_dirty_returns_reasons(self, tmp_path):
        """Node with parse_dirty=True and parse_dirty_reasons returns
        those reasons in the list.
        """
        from elspais.commands.fix_cmd import _detect_fixable

        wrong_hash_content = REQ_TEMPLATE.format(
            hash="placeholder",
            changelog_section="",
        )
        project = _make_project(tmp_path, wrong_hash_content)

        old_cwd = os.getcwd()
        os.chdir(project)
        try:
            _graph, node, hash_mode = _build_and_find(project)

            # Simulate parse-dirty state
            node._content["parse_dirty"] = True
            node._content["parse_dirty_reasons"] = ["duplicate_refs"]

            reasons = _detect_fixable(node, hash_mode, changelog_enforce=False)
        finally:
            os.chdir(old_cwd)

        assert "duplicate_refs" in reasons, f"Expected 'duplicate_refs' in {reasons}"

    def test_REQ_p00004_A_hash_mismatch_detected(self, tmp_path):
        """Node where computed hash differs from stored hash returns
        'hash_mismatch' in the reasons list.
        """
        from elspais.commands.fix_cmd import _detect_fixable

        bad_hash_content = REQ_TEMPLATE.format(
            hash="deadbeef",
            changelog_section="",
        )
        project = _make_project(tmp_path, bad_hash_content)

        old_cwd = os.getcwd()
        os.chdir(project)
        try:
            _graph, node, hash_mode = _build_and_find(project)
            reasons = _detect_fixable(node, hash_mode, changelog_enforce=False)
        finally:
            os.chdir(old_cwd)

        assert "hash_mismatch" in reasons, f"Expected 'hash_mismatch' in {reasons}"

    def test_REQ_p00004_A_changelog_drift_detected(self, tmp_path):
        """Active node where latest changelog hash differs from stored
        hash returns 'changelog_drift'.
        """
        from elspais.commands.fix_cmd import _detect_fixable

        # Build with correct hash first
        wrong_hash_content = REQ_TEMPLATE.format(
            hash="placeholder",
            changelog_section="",
        )
        project = _make_project(tmp_path, wrong_hash_content)
        correct_hash = _compute_correct_hash(project)

        # Now use correct stored hash but a STALE changelog hash
        stale_changelog = CHANGELOG_ENTRY_TEMPLATE.format(hash="oldolold")
        drift_content = REQ_TEMPLATE.format(
            hash=correct_hash,
            changelog_section=stale_changelog,
        )
        (project / "spec" / "requirements.md").write_text(drift_content)

        old_cwd = os.getcwd()
        os.chdir(project)
        try:
            _graph, node, hash_mode = _build_and_find(project)
            reasons = _detect_fixable(node, hash_mode, changelog_enforce=True)
        finally:
            os.chdir(old_cwd)

        assert "changelog_drift" in reasons, f"Expected 'changelog_drift' in {reasons}"

    def test_REQ_p00004_A_missing_changelog_detected(self, tmp_path):
        """Active node with changelog_enforce=True but no changelog
        entries returns 'missing_changelog'.
        """
        from elspais.commands.fix_cmd import _detect_fixable

        # Build with correct hash but no changelog section
        wrong_hash_content = REQ_TEMPLATE.format(
            hash="placeholder",
            changelog_section="",
        )
        project = _make_project(tmp_path, wrong_hash_content)
        correct_hash = _compute_correct_hash(project)

        clean_no_changelog = REQ_TEMPLATE.format(
            hash=correct_hash,
            changelog_section="",
        )
        (project / "spec" / "requirements.md").write_text(clean_no_changelog)

        old_cwd = os.getcwd()
        os.chdir(project)
        try:
            _graph, node, hash_mode = _build_and_find(project)
            reasons = _detect_fixable(node, hash_mode, changelog_enforce=True)
        finally:
            os.chdir(old_cwd)

        assert "missing_changelog" in reasons, f"Expected 'missing_changelog' in {reasons}"
