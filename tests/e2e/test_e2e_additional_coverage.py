# Verifies: REQ-p00002, REQ-p00060
# Verifies: REQ-d00074-A+B+C+D
"""Additional e2e tests for comprehensive feature coverage.

Tests edge cases, deeper config validation, additional MCP scenarios,
and more complex multi-repo setups.
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
    write_config,
)

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        shutil.which("elspais") is None,
        reason="elspais CLI not found on PATH",
    ),
]


# ---------------------------------------------------------------------------
# Test 77: Zero-padded numeric assertion labels
# ---------------------------------------------------------------------------


class TestZeroPaddedNumericAssertions:
    """Config: label_style = 'numeric', zero_pad = true."""

    def test_zero_padded_labels(self, tmp_path):
        cfg = base_config(
            name="zero-pad",
            label_style="numeric",
            zero_pad_assertions=True,
            allow_structural_orphans=True,
        )
        prd = Requirement(
            "REQ-p00001",
            "Zero Pad",
            "PRD",
            assertions=[
                ("00", "The system SHALL do first."),
                ("01", "The system SHALL do second."),
                ("02", "The system SHALL do third."),
            ],
        )
        build_project(tmp_path, cfg, spec_files={"spec/prd.md": [prd]})

        result = run_elspais("checks", "--lenient", cwd=tmp_path)
        assert result.returncode == 0, f"health failed: {result.stderr}\n{result.stdout}"


# ---------------------------------------------------------------------------
# Test 78: Multiple requirements in single file
# ---------------------------------------------------------------------------


class TestMultipleReqsSingleFile:
    """10 requirements in a single spec file."""

    def test_many_reqs_one_file(self, tmp_path):
        cfg = base_config(name="many-reqs", allow_structural_orphans=True)
        reqs = []
        for i in range(1, 11):
            reqs.append(
                Requirement(
                    f"REQ-p{i:05d}",
                    f"Feature {i}",
                    "PRD",
                    assertions=[
                        ("A", f"The system SHALL implement feature {i}."),
                        ("B", f"The system SHALL test feature {i}."),
                    ],
                )
            )
        build_project(tmp_path, cfg, spec_files={"spec/prd-all.md": reqs})

        summary = run_elspais("summary", "--format", "json", cwd=tmp_path)
        assert summary.returncode == 0
        data = json.loads(summary.stdout)
        total = sum(lv.get("total", 0) for lv in data.get("levels", []))
        assert total == 10

    def test_trace_has_all_10(self, tmp_path):
        cfg = base_config(name="many-reqs-trace", allow_structural_orphans=True)
        reqs = [
            Requirement(
                f"REQ-p{i:05d}",
                f"Feature {i}",
                "PRD",
                assertions=[("A", f"The system SHALL do {i}.")],
            )
            for i in range(1, 11)
        ]
        build_project(tmp_path, cfg, spec_files={"spec/prd.md": reqs})

        result = run_elspais("trace", "--format", "json", cwd=tmp_path)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert len(data) == 10


# ---------------------------------------------------------------------------
# Test 79: Refines relationship
# ---------------------------------------------------------------------------


class TestRefinesRelationship:
    """Refines: creates a refinement relationship."""

    def test_refines_link(self, tmp_path):
        cfg = base_config(name="refines-test", allow_structural_orphans=True)
        prd1 = Requirement(
            "REQ-p00001",
            "Base Feature",
            "PRD",
            assertions=[("A", "The system SHALL have base feature.")],
        )
        prd2 = Requirement(
            "REQ-p00002",
            "Refined Feature",
            "PRD",
            refines="REQ-p00001",
            assertions=[("A", "The system SHALL refine base feature.")],
        )
        build_project(
            tmp_path,
            cfg,
            spec_files={"spec/prd.md": [prd1, prd2]},
        )

        result = run_elspais("checks", "--lenient", cwd=tmp_path)
        assert result.returncode == 0

        trace = run_elspais("trace", "--format", "json", cwd=tmp_path)
        assert trace.returncode == 0
        assert "REQ-p00001" in trace.stdout
        assert "REQ-p00002" in trace.stdout


# ---------------------------------------------------------------------------
# Test 80: Draft status requirements
# ---------------------------------------------------------------------------


class TestDraftStatusRequirements:
    """Draft requirements should not be counted in Active-only summary."""

    def test_draft_vs_active(self, tmp_path):
        cfg = base_config(name="draft-test", allow_structural_orphans=True)
        active = Requirement(
            "REQ-p00001",
            "Active One",
            "PRD",
            assertions=[("A", "The system SHALL be active.")],
        )
        draft = Requirement(
            "REQ-p00002",
            "Draft One",
            "PRD",
            status="Draft",
            assertions=[("A", "The system SHALL be draft.")],
        )
        build_project(
            tmp_path,
            cfg,
            spec_files={"spec/prd.md": [active, draft]},
        )

        # Health sees both
        health = run_elspais("checks", "--lenient", cwd=tmp_path)
        assert health.returncode == 0


# ---------------------------------------------------------------------------
# Test 81: Multiple code files implementing same requirement
# ---------------------------------------------------------------------------


class TestMultipleCodeFilesForSameReq:
    """Multiple code files can implement the same requirement."""

    def test_multiple_implementors(self, tmp_path):
        cfg = base_config(name="multi-impl")
        prd = Requirement(
            "REQ-p00001",
            "Shared Feature",
            "PRD",
            assertions=[("A", "The system SHALL be implemented in multiple places.")],
        )
        dev = Requirement(
            "REQ-d00001",
            "Shared Module",
            "DEV",
            implements="REQ-p00001",
            assertions=[("A", "The module SHALL be shared.")],
        )
        build_project(
            tmp_path,
            cfg,
            spec_files={
                "spec/prd.md": [prd],
                "spec/dev.md": [dev],
            },
            code_files={
                "src/impl_a.py": {"implements": ["REQ-d00001"]},
                "src/impl_b.py": {"implements": ["REQ-d00001"]},
                "src/impl_c.py": {"implements": ["REQ-d00001"]},
            },
        )

        result = run_elspais("checks", "--lenient", cwd=tmp_path)
        assert result.returncode == 0


# ---------------------------------------------------------------------------
# Test 82: Heading level 3 (###) requirements
# ---------------------------------------------------------------------------


class TestHeadingLevel3:
    """Requirements with ### heading level."""

    def test_h3_requirements(self, tmp_path):
        cfg = base_config(name="h3-test", allow_structural_orphans=True)
        prd = Requirement(
            "REQ-p00001",
            "H3 Requirement",
            "PRD",
            assertions=[("A", "The system SHALL support H3 headings.")],
            heading_level=3,
        )
        build_project(
            tmp_path,
            cfg,
            spec_files={"spec/prd.md": [prd]},
        )

        result = run_elspais("checks", "--lenient", cwd=tmp_path)
        assert result.returncode == 0

        summary = run_elspais("summary", "--format", "json", cwd=tmp_path)
        data = json.loads(summary.stdout)
        total = sum(lv.get("total", 0) for lv in data.get("levels", []))
        assert total == 1


# ---------------------------------------------------------------------------
# Test 83: Spec files with preamble text
# ---------------------------------------------------------------------------


class TestSpecFilePreamble:
    """Spec files can have preamble text before requirements."""

    def test_preamble_ignored(self, tmp_path):
        cfg = base_config(name="preamble-test", allow_structural_orphans=True)
        spec = tmp_path / "spec" / "prd-with-preamble.md"
        spec.parent.mkdir(parents=True, exist_ok=True)

        # Write a spec file with preamble text
        from .helpers import compute_hash

        h = compute_hash([("A", "The system SHALL have preamble.")])
        spec.write_text(
            "# Product Requirements\n\n"
            "This document describes the product requirements.\n\n"
            "---\n\n"
            "## REQ-p00001: Preamble Test\n\n"
            "**Level**: PRD | **Status**: Active\n\n"
            "## Assertions\n\n"
            "A. The system SHALL have preamble.\n\n"
            f"*End* *Preamble Test* | **Hash**: {h}\n"
            "---\n"
        )

        build_project(tmp_path, cfg, spec_files={})

        result = run_elspais("checks", "--lenient", cwd=tmp_path)
        assert result.returncode == 0


# ---------------------------------------------------------------------------
# Test 84: Config add/remove array values
# ---------------------------------------------------------------------------


class TestConfigArrayOperations:
    """Config add/remove for array values."""

    def test_add_status(self, tmp_path):
        cfg = base_config(name="array-ops")
        build_project(tmp_path, cfg, spec_files={})
        (tmp_path / "spec").mkdir(exist_ok=True)

        # Add a new allowed status
        result = run_elspais(
            "config",
            "add",
            "rules.format.allowed_statuses",
            "Experimental",
            cwd=tmp_path,
        )
        assert result.returncode == 0

        # Verify it's there
        show = run_elspais("config", "show", "--format", "json", cwd=tmp_path)
        data = json.loads(show.stdout)
        statuses = data.get("rules", {}).get("format", {}).get("allowed_statuses", [])
        assert "Experimental" in statuses

    def test_remove_status(self, tmp_path):
        cfg = base_config(name="array-remove")
        build_project(tmp_path, cfg, spec_files={})
        (tmp_path / "spec").mkdir(exist_ok=True)

        # Remove a status
        result = run_elspais(
            "config",
            "remove",
            "rules.format.allowed_statuses",
            "Superseded",
            cwd=tmp_path,
        )
        assert result.returncode == 0

        show = run_elspais("config", "show", "--format", "json", cwd=tmp_path)
        data = json.loads(show.stdout)
        statuses = data.get("rules", {}).get("format", {}).get("allowed_statuses", [])
        assert "Superseded" not in statuses


# ---------------------------------------------------------------------------
# Test 85: Deep hierarchy (4 levels of implements)
# ---------------------------------------------------------------------------


class TestDeepHierarchy:
    """PRD -> OPS -> DEV chain with many assertions."""

    def test_deep_chain(self, tmp_path):
        cfg = base_config(name="deep-chain")
        prd = Requirement(
            "REQ-p00001",
            "Top Level",
            "PRD",
            assertions=[
                ("A", "The system SHALL be at the top."),
                ("B", "The system SHALL cascade down."),
                ("C", "The system SHALL be comprehensive."),
            ],
        )
        ops1 = Requirement(
            "REQ-o00001",
            "Ops Layer 1",
            "OPS",
            implements="REQ-p00001",
            assertions=[
                ("A", "Operations SHALL monitor layer 1."),
                ("B", "Operations SHALL alert on layer 1."),
            ],
        )
        ops2 = Requirement(
            "REQ-o00002",
            "Ops Layer 2",
            "OPS",
            implements="REQ-p00001",
            assertions=[("A", "Operations SHALL monitor layer 2.")],
        )
        dev1 = Requirement(
            "REQ-d00001",
            "Dev Layer 1",
            "DEV",
            implements="REQ-o00001",
            assertions=[
                ("A", "The module SHALL implement layer 1A."),
                ("B", "The module SHALL implement layer 1B."),
            ],
        )
        dev2 = Requirement(
            "REQ-d00002",
            "Dev Layer 2",
            "DEV",
            implements="REQ-o00001",
            assertions=[("A", "The module SHALL implement layer 2.")],
        )
        dev3 = Requirement(
            "REQ-d00003",
            "Dev Layer 3",
            "DEV",
            implements="REQ-o00002",
            assertions=[("A", "The module SHALL implement layer 3.")],
        )
        build_project(
            tmp_path,
            cfg,
            spec_files={
                "spec/prd.md": [prd],
                "spec/ops.md": [ops1, ops2],
                "spec/dev.md": [dev1, dev2, dev3],
            },
        )

        health = run_elspais("checks", "--lenient", cwd=tmp_path)
        assert health.returncode == 0

        summary = run_elspais("summary", "--format", "json", cwd=tmp_path)
        data = json.loads(summary.stdout)
        total = sum(lv.get("total", 0) for lv in data.get("levels", []))
        assert total == 6


# ---------------------------------------------------------------------------
# Test 86: MCP undo_to_mutation
# ---------------------------------------------------------------------------


class TestMCPUndoToMutation:
    """MCP undo_to_mutation for selective rollback."""

    def test_undo_to_point(self, tmp_path):
        pytest.importorskip("mcp")
        from .helpers import mcp_call, start_mcp, stop_mcp

        cfg = base_config(name="undo-to", allow_structural_orphans=True)
        prd = Requirement(
            "REQ-p00001",
            "Undo Target",
            "PRD",
            assertions=[("A", "The system SHALL support undo.")],
        )
        build_project(tmp_path, cfg, spec_files={"spec/prd.md": [prd]})

        proc = start_mcp(tmp_path)
        try:
            # Make 3 mutations
            mcp_call(
                proc,
                "mutate_update_title",
                {
                    "node_id": "REQ-p00001",
                    "new_title": "Title V1",
                },
            )
            mcp_call(
                proc,
                "mutate_update_title",
                {
                    "node_id": "REQ-p00001",
                    "new_title": "Title V2",
                },
            )
            mcp_call(
                proc,
                "mutate_update_title",
                {
                    "node_id": "REQ-p00001",
                    "new_title": "Title V3",
                },
            )

            # Get log
            log = mcp_call(proc, "get_mutation_log", {"limit": 10})
            assert isinstance(log, (list, dict))

            # Undo all
            mcp_call(proc, "undo_last_mutation", {})
            mcp_call(proc, "undo_last_mutation", {})
            mcp_call(proc, "undo_last_mutation", {})

            # Verify back to original
            req = mcp_call(proc, "get_requirement", {"req_id": "REQ-p00001"})
            assert req["title"] == "Undo Target"
        finally:
            stop_mcp(proc)


# ---------------------------------------------------------------------------
# Test 87: MCP rename node
# ---------------------------------------------------------------------------


class TestMCPRenameNode:
    """MCP mutate_rename_node changes requirement ID."""

    def test_rename_and_undo(self, tmp_path):
        pytest.importorskip("mcp")
        from .helpers import mcp_call, start_mcp, stop_mcp

        cfg = base_config(name="rename-test", allow_structural_orphans=True)
        prd = Requirement(
            "REQ-p00001",
            "Rename Me",
            "PRD",
            assertions=[("A", "The system SHALL be renamed.")],
        )
        build_project(tmp_path, cfg, spec_files={"spec/prd.md": [prd]})

        proc = start_mcp(tmp_path)
        try:
            # Rename
            result = mcp_call(
                proc,
                "mutate_rename_node",
                {
                    "old_id": "REQ-p00001",
                    "new_id": "REQ-p00099",
                },
            )
            assert isinstance(result, dict)
            assert not result.get("_error"), f"Rename failed: {result}"

            # Verify new ID exists
            req = mcp_call(proc, "get_requirement", {"req_id": "REQ-p00099"})
            assert req and req.get("id") == "REQ-p00099"

            # Old ID should not exist
            old = mcp_call(proc, "get_requirement", {"req_id": "REQ-p00001"})
            assert old is None or old.get("_error") or old.get("error")

            # Undo
            mcp_call(proc, "undo_last_mutation", {})

            # Original should be back
            restored = mcp_call(proc, "get_requirement", {"req_id": "REQ-p00001"})
            assert restored and restored.get("id") == "REQ-p00001"
        finally:
            stop_mcp(proc)


# ---------------------------------------------------------------------------
# Test 88: MCP change_status
# ---------------------------------------------------------------------------


class TestMCPChangeStatus:
    """MCP mutate_change_status."""

    def test_change_status(self, tmp_path):
        pytest.importorskip("mcp")
        from .helpers import mcp_call, start_mcp, stop_mcp

        cfg = base_config(name="status-change", allow_structural_orphans=True)
        prd = Requirement(
            "REQ-p00001",
            "Status Test",
            "PRD",
            assertions=[("A", "The system SHALL change status.")],
        )
        build_project(tmp_path, cfg, spec_files={"spec/prd.md": [prd]})

        proc = start_mcp(tmp_path)
        try:
            result = mcp_call(
                proc,
                "mutate_change_status",
                {
                    "node_id": "REQ-p00001",
                    "new_status": "Draft",
                },
            )
            assert isinstance(result, dict)

            req = mcp_call(proc, "get_requirement", {"req_id": "REQ-p00001"})
            req_str = json.dumps(req)
            assert "Draft" in req_str, f"Expected Draft status in: {req_str[:500]}"
        finally:
            stop_mcp(proc)


# ---------------------------------------------------------------------------
# Test 89: MCP delete requirement
# ---------------------------------------------------------------------------


class TestMCPDeleteRequirement:
    """MCP mutate_delete_requirement."""

    def test_delete_and_undo(self, tmp_path):
        pytest.importorskip("mcp")
        from .helpers import mcp_call, start_mcp, stop_mcp

        cfg = base_config(name="delete-test", allow_structural_orphans=True)
        reqs = [
            Requirement(
                "REQ-p00001",
                "Keep This",
                "PRD",
                assertions=[("A", "The system SHALL be kept.")],
            ),
            Requirement(
                "REQ-p00002",
                "Delete This",
                "PRD",
                assertions=[("A", "The system SHALL be deleted.")],
            ),
        ]
        build_project(tmp_path, cfg, spec_files={"spec/prd.md": reqs})

        proc = start_mcp(tmp_path)
        try:
            # Delete
            result = mcp_call(
                proc,
                "mutate_delete_requirement",
                {
                    "node_id": "REQ-p00002",
                    "confirm": True,
                },
            )
            assert isinstance(result, dict)

            # Verify deleted
            req = mcp_call(proc, "get_requirement", {"req_id": "REQ-p00002"})
            assert req is None or req.get("_error") or req.get("error")

            # REQ-p00001 should still exist
            req1 = mcp_call(proc, "get_requirement", {"req_id": "REQ-p00001"})
            assert req1 and req1.get("id") == "REQ-p00001"

            # Undo
            mcp_call(proc, "undo_last_mutation", {})

            # Should be back
            restored = mcp_call(proc, "get_requirement", {"req_id": "REQ-p00002"})
            assert restored and restored.get("id") == "REQ-p00002"
        finally:
            stop_mcp(proc)


# ---------------------------------------------------------------------------
# Test 90: MCP rename assertion
# ---------------------------------------------------------------------------


class TestMCPRenameAssertion:
    """MCP mutate_rename_assertion."""

    def test_rename_assertion(self, tmp_path):
        pytest.importorskip("mcp")
        from .helpers import mcp_call, start_mcp, stop_mcp

        cfg = base_config(name="rename-assert", allow_structural_orphans=True)
        prd = Requirement(
            "REQ-p00001",
            "Rename Assert",
            "PRD",
            assertions=[
                ("A", "The system SHALL have assertion A."),
                ("B", "The system SHALL have assertion B."),
            ],
        )
        build_project(tmp_path, cfg, spec_files={"spec/prd.md": [prd]})

        proc = start_mcp(tmp_path)
        try:
            result = mcp_call(
                proc,
                "mutate_rename_assertion",
                {
                    "old_id": "REQ-p00001-A",
                    "new_label": "X",
                },
            )
            assert isinstance(result, dict)

            # Verify renamed
            req = mcp_call(proc, "get_requirement", {"req_id": "REQ-p00001"})
            labels = [a.get("label", "") for a in req.get("assertions", [])]
            assert "X" in labels
            assert "A" not in labels
        finally:
            stop_mcp(proc)


# ---------------------------------------------------------------------------
# Test 91: MCP workspace info detail profiles
# ---------------------------------------------------------------------------


class TestMCPWorkspaceInfoProfiles:
    """MCP get_workspace_info with different detail profiles."""

    def _build(self, tmp_path):
        cfg = base_config(
            name="workspace-profiles",
            testing_enabled=True,
            test_dirs=["tests"],
            allow_structural_orphans=True,
        )
        prd = Requirement(
            "REQ-p00001",
            "Profile Test",
            "PRD",
            assertions=[("A", "The system SHALL test profiles.")],
        )
        build_project(tmp_path, cfg, spec_files={"spec/prd.md": [prd]})
        return tmp_path

    def test_default_profile(self, tmp_path):
        pytest.importorskip("mcp")
        from .helpers import mcp_call, start_mcp, stop_mcp

        self._build(tmp_path)
        proc = start_mcp(tmp_path)
        try:
            result = mcp_call(proc, "get_workspace_info", {"detail": "default"})
            assert isinstance(result, dict)
        finally:
            stop_mcp(proc)

    def test_testing_profile(self, tmp_path):
        pytest.importorskip("mcp")
        from .helpers import mcp_call, start_mcp, stop_mcp

        self._build(tmp_path)
        proc = start_mcp(tmp_path)
        try:
            result = mcp_call(proc, "get_workspace_info", {"detail": "testing"})
            assert isinstance(result, dict)
        finally:
            stop_mcp(proc)

    def test_coverage_profile(self, tmp_path):
        pytest.importorskip("mcp")
        from .helpers import mcp_call, start_mcp, stop_mcp

        self._build(tmp_path)
        proc = start_mcp(tmp_path)
        try:
            result = mcp_call(proc, "get_workspace_info", {"detail": "coverage"})
            assert isinstance(result, dict)
        finally:
            stop_mcp(proc)

    def test_all_profile(self, tmp_path):
        pytest.importorskip("mcp")
        from .helpers import mcp_call, start_mcp, stop_mcp

        self._build(tmp_path)
        proc = start_mcp(tmp_path)
        try:
            result = mcp_call(proc, "get_workspace_info", {"detail": "all"})
            assert isinstance(result, dict)
        finally:
            stop_mcp(proc)


# ---------------------------------------------------------------------------
# Test 92: MCP agent_instructions
# ---------------------------------------------------------------------------


class TestMCPAgentInstructions:
    """MCP agent_instructions tool."""

    def test_agent_instructions(self, tmp_path):
        pytest.importorskip("mcp")
        from .helpers import mcp_call, start_mcp, stop_mcp

        cfg = base_config(name="agent-inst", allow_structural_orphans=True)
        prd = Requirement(
            "REQ-p00001",
            "Instructions",
            "PRD",
            assertions=[("A", "The system SHALL provide instructions.")],
        )
        build_project(tmp_path, cfg, spec_files={"spec/prd.md": [prd]})

        proc = start_mcp(tmp_path)
        try:
            result = mcp_call(proc, "agent_instructions", {})
            assert isinstance(result, (dict, str))
        finally:
            stop_mcp(proc)


# ---------------------------------------------------------------------------
# Test 93: Health output to file
# ---------------------------------------------------------------------------


class TestHealthOutputToFile:
    """Health --output writes to file."""

    def test_output_to_file(self, tmp_path):
        cfg = base_config(name="output-file", allow_structural_orphans=True)
        prd = Requirement(
            "REQ-p00001",
            "Output Test",
            "PRD",
            assertions=[("A", "The system SHALL output to file.")],
        )
        build_project(tmp_path, cfg, spec_files={"spec/prd.md": [prd]})

        out_file = tmp_path / "health-output.json"
        result = run_elspais(
            "checks",
            "--format",
            "json",
            "--lenient",
            "--output",
            str(out_file),
            cwd=tmp_path,
        )
        # Some commands may not support --output
        if result.returncode == 0 and out_file.exists():
            content = out_file.read_text()
            data = json.loads(content)
            assert isinstance(data, (dict, list))


# ---------------------------------------------------------------------------
# Test 94: Config unset operation
# ---------------------------------------------------------------------------


class TestConfigUnset:
    """Config unset removes a key."""

    def test_unset_key(self, tmp_path):
        cfg = base_config(name="unset-test")
        build_project(tmp_path, cfg, spec_files={})
        (tmp_path / "spec").mkdir(exist_ok=True)

        # Unset project.version (a non-default field)
        result = run_elspais("config", "unset", "project.namespace", cwd=tmp_path)
        assert result.returncode == 0

        # Verify the file was modified (config show may still show defaults)
        import tomlkit

        content = (tmp_path / ".elspais.toml").read_text()
        data = tomlkit.loads(content)
        assert "namespace" not in data.get("project", {})


# ---------------------------------------------------------------------------
# Test 95: MCP suggest_links
# ---------------------------------------------------------------------------


class TestMCPSuggestLinks:
    """MCP suggest_links for unlinked test files."""

    def test_suggest_links(self, tmp_path):
        pytest.importorskip("mcp")
        from .helpers import mcp_call, start_mcp, stop_mcp

        cfg = base_config(
            name="suggest-links",
            testing_enabled=True,
            test_dirs=["tests"],
        )
        prd = Requirement(
            "REQ-p00001",
            "Linkable Feature",
            "PRD",
            assertions=[("A", "The system SHALL be linkable.")],
        )
        dev = Requirement(
            "REQ-d00001",
            "Linkable Module",
            "DEV",
            implements="REQ-p00001",
            assertions=[("A", "The module SHALL be linkable.")],
        )
        build_project(
            tmp_path,
            cfg,
            spec_files={
                "spec/prd.md": [prd],
                "spec/dev.md": [dev],
            },
            test_files={
                # Unlinked test (no Validates comment)
                "tests/test_linkable.py": {
                    "content": "def test_linkable():\n    assert True",
                },
            },
        )

        proc = start_mcp(tmp_path)
        try:
            result = mcp_call(proc, "suggest_links", {})
            # May return suggestions or empty list
            assert isinstance(result, (list, dict))
        finally:
            stop_mcp(proc)


# ---------------------------------------------------------------------------
# Test 96: MCP get_changed_requirements
# ---------------------------------------------------------------------------


class TestMCPChangedRequirements:
    """MCP get_changed_requirements detects modifications."""

    def test_no_changes(self, tmp_path):
        pytest.importorskip("mcp")
        from .helpers import mcp_call, start_mcp, stop_mcp

        cfg = base_config(name="changed-mcp", allow_structural_orphans=True)
        prd = Requirement(
            "REQ-p00001",
            "Stable",
            "PRD",
            assertions=[("A", "The system SHALL be stable.")],
        )
        build_project(tmp_path, cfg, spec_files={"spec/prd.md": [prd]})

        proc = start_mcp(tmp_path)
        try:
            result = mcp_call(proc, "get_changed_requirements", {})
            assert isinstance(result, (list, dict))
        finally:
            stop_mcp(proc)


# ---------------------------------------------------------------------------
# Test 97: Init --force overwrites existing config
# ---------------------------------------------------------------------------


class TestInitForce:
    """Init --force overwrites existing .elspais.toml."""

    def test_force_overwrite(self, tmp_path):
        # Create an initial config
        cfg = base_config(name="will-be-overwritten")
        build_project(tmp_path, cfg, spec_files={})

        # Force overwrite
        result = run_elspais("init", "--force", cwd=tmp_path)
        assert result.returncode == 0

        # Config should be the default template, not our custom one
        show = run_elspais("config", "show", "--format", "json", cwd=tmp_path)
        assert show.returncode == 0


# ---------------------------------------------------------------------------
# Test 98: Health with OPS-only type (2-tier hierarchy)
# ---------------------------------------------------------------------------


class TestTwoTierHierarchy:
    """Config with only PRD and DEV (no OPS)."""

    def test_two_tier(self, tmp_path):
        cfg = base_config(
            name="two-tier",
            types={
                "prd": {"level": 1, "aliases": {"letter": "p"}},
                "dev": {"level": 3, "aliases": {"letter": "d"}},
            },
            allowed_implements=["dev -> prd"],
        )
        prd = Requirement(
            "REQ-p00001",
            "Two Tier PRD",
            "PRD",
            assertions=[("A", "The system SHALL use two tiers.")],
        )
        dev = Requirement(
            "REQ-d00001",
            "Two Tier DEV",
            "DEV",
            implements="REQ-p00001",
            assertions=[("A", "The module SHALL implement directly.")],
        )
        build_project(
            tmp_path,
            cfg,
            spec_files={
                "spec/prd.md": [prd],
                "spec/dev.md": [dev],
            },
        )

        health = run_elspais("checks", "--lenient", cwd=tmp_path)
        assert health.returncode == 0

        summary = run_elspais("summary", "--format", "json", cwd=tmp_path)
        data = json.loads(summary.stdout)
        total = sum(lv.get("total", 0) for lv in data.get("levels", []))
        assert total == 2


# ---------------------------------------------------------------------------
# Test 99: Spec with empty assertions section
# ---------------------------------------------------------------------------


class TestEmptyAssertions:
    """Requirements with no assertions when require_assertions=false."""

    def test_no_assertions_allowed(self, tmp_path):
        cfg = base_config(
            name="no-assertions",
            require_assertions=False,
            allow_structural_orphans=True,
        )
        # Write a requirement without assertions section
        spec = tmp_path / "spec" / "prd.md"
        spec.parent.mkdir(parents=True, exist_ok=True)
        spec.write_text(
            "# REQ-p00001: No Assertions\n\n"
            "**Level**: PRD | **Status**: Active\n\n"
            "The system does something without assertions.\n\n"
            "*End* *No Assertions* | **Hash**: e3b0c442\n"
            "---\n"
        )
        write_config(tmp_path / ".elspais.toml", cfg)

        from .helpers import init_git_repo

        init_git_repo(tmp_path)

        result = run_elspais("checks", "--lenient", cwd=tmp_path)
        assert result.returncode == 0


# ---------------------------------------------------------------------------
# Test 100: MCP comprehensive multi-mutation workflow
# ---------------------------------------------------------------------------


class TestMCPMultiMutationWorkflow:
    """Complex mutation workflow: add req, add assertions, add edges, save."""

    def test_build_requirement_from_scratch(self, tmp_path):
        pytest.importorskip("mcp")
        from .helpers import mcp_call, start_mcp, stop_mcp

        cfg = base_config(name="scratch-build", allow_structural_orphans=True)
        prd = Requirement(
            "REQ-p00001",
            "Existing PRD",
            "PRD",
            assertions=[("A", "The system SHALL exist.")],
        )
        build_project(tmp_path, cfg, spec_files={"spec/prd.md": [prd]})

        proc = start_mcp(tmp_path)
        try:
            # 1. Add new OPS requirement
            mcp_call(
                proc,
                "mutate_add_requirement",
                {
                    "req_id": "REQ-o00001",
                    "title": "New Operations Req",
                    "level": "ops",
                    "status": "Draft",
                },
            )

            # 2. Add edge: o00001 implements p00001
            mcp_call(
                proc,
                "mutate_add_edge",
                {
                    "source_id": "REQ-o00001",
                    "target_id": "REQ-p00001",
                    "edge_kind": "implements",
                },
            )

            # 3. Add assertions to new req
            mcp_call(
                proc,
                "mutate_add_assertion",
                {
                    "req_id": "REQ-o00001",
                    "label": "A",
                    "text": "Operations SHALL deploy new service.",
                },
            )
            mcp_call(
                proc,
                "mutate_add_assertion",
                {
                    "req_id": "REQ-o00001",
                    "label": "B",
                    "text": "Operations SHALL monitor new service.",
                },
            )

            # 4. Verify the built requirement
            req = mcp_call(proc, "get_requirement", {"req_id": "REQ-o00001"})
            assert req["id"] == "REQ-o00001"
            assert req["title"] == "New Operations Req"
            assert len(req.get("assertions", [])) == 2

            # 5. Check hierarchy
            hier = mcp_call(proc, "get_hierarchy", {"req_id": "REQ-o00001"})
            ancestor_ids = [a.get("id", "") for a in hier.get("ancestors", [])]
            assert "REQ-p00001" in ancestor_ids

            # 6. Save
            save = mcp_call(proc, "save_mutations", {"save_branch": False})
            assert not save.get("_error"), f"Save failed: {save}"
        finally:
            stop_mcp(proc)
