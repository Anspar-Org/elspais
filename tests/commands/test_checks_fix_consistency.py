# Verifies: REQ-p00004-A
"""Tests that `checks` passing implies `fix --dry-run` is a no-op.

Per TODO.md acceptance criterion: `elspais checks` passing should be a
reliable predicate for "`elspais fix` is a no-op." For a fixture where
`checks` passes, `fix --dry-run` must print no "Would ..." lines and
`_detect_fixable` must return an empty list for every requirement.

Also verifies that this behavior holds regardless of the current working
directory — library callers (tests, MCP server, viewer) must not be
required to chdir into the project for correctness.
"""

from __future__ import annotations

import argparse
import io
from contextlib import redirect_stdout
from pathlib import Path

CONFIG_TOML = """\
version = 3

[project]
name = "test-checks-fix-consistency"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]

[changelog]
hash_current = true
present = false
"""


def _build_federated_graph(project: Path):
    """Build a FederatedGraph for the fixture project."""
    from elspais.graph.factory import build_graph

    return build_graph(
        spec_dirs=[project / "spec"],
        config_path=project / ".elspais.toml",
        repo_root=project,
        scan_code=False,
        scan_tests=False,
    )


def _write_reqs(project: Path, hashes: dict[str, str], changelogs: dict[str, str]) -> None:
    """Write the spec file with the supplied per-req hashes and changelog sections."""
    (project / "spec" / "requirements.md").write_text(
        f"""\
# REQ-p00001: First Requirement

**Level**: PRD | **Status**: Active

## Assertions

A. The system SHALL do the first thing.

B. The system SHALL do the second thing.

{changelogs['REQ-p00001']}*End* *First Requirement* | **Hash**: {hashes['REQ-p00001']}
---

# REQ-p00002: Second Requirement

**Level**: PRD | **Status**: Active

## Assertions

A. The system SHALL do another thing.

{changelogs['REQ-p00002']}*End* *Second Requirement* | **Hash**: {hashes['REQ-p00002']}
---
"""
    )


def _make_clean_project(tmp_path: Path) -> Path:
    """Build a fixture project where checks pass and fix is a no-op.

    Strategy:
    1. Write the project with placeholder hashes / no changelog.
    2. Build the graph to learn the correct normalized-text hashes.
    3. Rewrite the file with correct hashes and a valid changelog entry
       whose hash matches the stored End-marker hash.
    4. Generate an INDEX.md that is byte-identical to what fix would
       emit.

    Does not chdir: after the ``_classify_node`` fix (use FILE-node
    absolute_path rather than re-resolving repo-relative paths against
    CWD), the fixture is CWD-independent.
    """
    from elspais.commands.index import _build_index_content
    from elspais.graph import NodeKind
    from elspais.graph.render import compute_hash_for_node

    (tmp_path / ".elspais.toml").write_text(CONFIG_TOML)
    spec_dir = tmp_path / "spec"
    spec_dir.mkdir()

    placeholder = {"REQ-p00001": "placeholder", "REQ-p00002": "placeholder"}
    empty_cl = {"REQ-p00001": "", "REQ-p00002": ""}
    _write_reqs(tmp_path, placeholder, empty_cl)

    graph = _build_federated_graph(tmp_path)
    hash_mode = getattr(graph, "hash_mode", "full-text")

    hashes: dict[str, str] = {}
    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        hashes[node.id] = compute_hash_for_node(node, hash_mode) or "N/A"

    changelogs = {
        req_id: (
            "## Changelog\n"
            "\n"
            f"- 2026-01-01 | {hashes[req_id]} | -"
            " | Alice (<a@b.org>) | Initial version\n"
            "\n"
        )
        for req_id in hashes
    }
    _write_reqs(tmp_path, hashes, changelogs)

    graph2 = _build_federated_graph(tmp_path)
    output_path, expected, _rc, _jc = _build_index_content(graph2, [spec_dir])
    output_path.write_text(expected, encoding="utf-8")

    return tmp_path


class TestChecksFixConsistency:
    """Validates REQ-p00004-A: clean fixture -> checks pass AND fix is a no-op."""

    def test_REQ_p00004_A_clean_fixture_checks_pass(self, tmp_path: Path):
        """On a clean fixture, run_spec_checks reports no failing spec checks."""
        from elspais.commands.health import run_spec_checks
        from elspais.config import _merge_configs, config_defaults, get_config

        project = _make_clean_project(tmp_path)

        graph = _build_federated_graph(project)
        config = _merge_configs(config_defaults(), get_config(project / ".elspais.toml"))
        checks = run_spec_checks(graph, config, spec_dirs=[project / "spec"])

        failing = [c for c in checks if not c.passed and c.severity == "error"]
        warnings = [c for c in checks if not c.passed and c.severity == "warning"]

        assert (
            not failing
        ), "Clean fixture should produce no failing spec checks, got: " + ", ".join(
            f"{c.name}: {c.message}" for c in failing
        )
        assert not warnings, "Clean fixture should produce no spec warnings, got: " + ", ".join(
            f"{c.name}: {c.message}" for c in warnings
        )

    def test_REQ_p00004_A_fix_index_dry_run_prints_nothing(self, tmp_path: Path):
        """On a clean fixture, _fix_index(dry_run=True) emits no "Would" lines."""
        from elspais.commands.fix_cmd import _fix_index

        project = _make_clean_project(tmp_path)

        args = argparse.Namespace(
            spec_dir=None,
            config=project / ".elspais.toml",
            git_root=project,
        )

        buf = io.StringIO()
        with redirect_stdout(buf):
            _fix_index(args, dry_run=True)

        out = buf.getvalue()
        assert "Would" not in out, (
            "_fix_index dry-run should emit no 'Would' lines on a clean "
            f"fixture, got stdout: {out!r}"
        )

    def test_REQ_p00004_A_detect_fixable_empty_for_every_req(self, tmp_path: Path):
        """On a clean fixture, _detect_fixable returns [] for every REQUIREMENT."""
        from elspais.commands.fix_cmd import _detect_fixable
        from elspais.graph import NodeKind

        project = _make_clean_project(tmp_path)

        graph = _build_federated_graph(project)
        hash_mode = getattr(graph, "hash_mode", "full-text")

        offenders: dict[str, list[str]] = {}
        total = 0
        for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
            total += 1
            reasons = _detect_fixable(node, hash_mode, changelog_enforce=True)
            if reasons:
                offenders[node.id] = reasons

        assert total >= 1, "Fixture must contain at least one REQUIREMENT"
        assert not offenders, f"Clean fixture should have no fixable requirements, got: {offenders}"

    def test_REQ_p00004_A_checks_cwd_independent(self, tmp_path: Path, monkeypatch):
        """Classification + checks must work when CWD is unrelated to the project.

        Regression guard for the ``_classify_node`` bug where repo-relative
        paths were re-resolved against CWD, causing nodes to fall into the
        "Unknown Source" bucket when library callers hadn't chdir'd.
        """
        from elspais.commands.index import _build_index_content

        project = _make_clean_project(tmp_path)

        # Move CWD somewhere unrelated before invoking any library API.
        outside = tmp_path.parent / "unrelated"
        outside.mkdir()
        monkeypatch.chdir(outside)

        graph = _build_federated_graph(project)
        _out, content, req_count, _jny = _build_index_content(graph, [project / "spec"])

        assert req_count == 2, f"Expected 2 requirements classified, got {req_count}"
        assert "Unknown Source" not in content, (
            "INDEX.md should not contain 'Unknown Source' when classification "
            "is working; _classify_node must use FILE-node absolute_path, not "
            "re-resolve relative paths against CWD"
        )
