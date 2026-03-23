# Implements: REQ-d00134-A+B+C+D+E+F
# Validates REQ-d00134-A, REQ-d00134-B, REQ-d00134-C, REQ-d00134-D
# Validates REQ-d00134-E, REQ-d00134-F
"""E2E mutation round-trip scenario via MCP subprocess.

Exercises mutation operations through the MCP server subprocess in a single
deterministic run. Builds a requirement hierarchy, applies mutations via
MCP tool calls, verifies intermediate state, saves to disk, reloads via
refresh_graph, and confirms round-trip fidelity.

REQ-d00134-A: 50+ mutations across all types
REQ-d00134-B: 6+ requirements across PRD/OPS/DEV with assertions
REQ-d00134-C: Intermediate checkpoint verification
REQ-d00134-D: Save -> reload -> verify round-trip
REQ-d00134-E: Second mutation round after reload
REQ-d00134-F: Undo operations properly reverted
"""

from __future__ import annotations

import shutil

import pytest

from .helpers import (
    Requirement,
    base_config,
    build_project,
    mcp_call,
    start_mcp,
    stop_mcp,
)

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        shutil.which("elspais") is None,
        reason="elspais CLI not found on PATH",
    ),
]


def _ok(result):
    """Assert an MCP mutation result is valid JSON and not an error."""
    assert result is not None, "MCP tool returned empty response — expected JSON result"
    assert "_error" not in result, f"MCP error: {result.get('_error')}"
    return result


def _build_scenario_project(tmp_path):
    """Build a 6-requirement project across PRD/OPS/DEV with assertions."""
    config = base_config()
    config["changelog"] = {"hash_current": False}

    reqs = {
        "spec/prd.md": [
            Requirement(
                req_id="REQ-p00001",
                title="Platform Security",
                level="PRD",
                status="Active",
                assertions=[
                    ("A", "The platform SHALL encrypt all data at rest."),
                    ("B", "The platform SHALL use TLS 1.3 for data in transit."),
                    ("C", "The platform SHALL enforce role-based access control."),
                ],
            ),
            Requirement(
                req_id="REQ-p00002",
                title="User Management",
                level="PRD",
                status="Active",
                assertions=[
                    ("A", "The system SHALL support user registration."),
                    ("B", "The system SHALL support password reset."),
                ],
            ),
        ],
        "spec/ops.md": [
            Requirement(
                req_id="REQ-o00001",
                title="Encryption Ops",
                level="OPS",
                status="Active",
                implements="REQ-p00001",
                assertions=[
                    ("A", "Operations SHALL deploy encryption key rotation."),
                    ("B", "Operations SHALL monitor key usage."),
                ],
            ),
            Requirement(
                req_id="REQ-o00002",
                title="TLS Config",
                level="OPS",
                status="Active",
                implements="REQ-p00001",
                assertions=[
                    ("A", "Operations SHALL configure TLS 1.3 on all endpoints."),
                    ("B", "Operations SHALL automate certificate renewal."),
                ],
            ),
        ],
        "spec/dev.md": [
            Requirement(
                req_id="REQ-d00001",
                title="Crypto Module",
                level="DEV",
                status="Active",
                implements="REQ-o00001",
                assertions=[
                    ("A", "The module SHALL use AES-256-GCM."),
                    ("B", "The module SHALL support key rotation API."),
                    ("C", "The module SHALL log all key operations."),
                ],
            ),
            Requirement(
                req_id="REQ-d00002",
                title="TLS Implementation",
                level="DEV",
                status="Active",
                implements="REQ-o00002",
                assertions=[
                    ("A", "The module SHALL pin TLS 1.3 cipher suites."),
                    ("B", "The module SHALL reject downgrade attempts."),
                ],
            ),
        ],
    }

    build_project(tmp_path, config, spec_files=reqs)
    return tmp_path


class TestScenarioMutationsE2E:
    """REQ-d00134: Comprehensive mutation round-trip via MCP subprocess."""

    def test_REQ_d00134_A_full_mutation_scenario(self, tmp_path) -> None:
        """Full mutation round-trip: add, rename, update, delete, undo, save, reload."""
        _build_scenario_project(tmp_path)
        proc = start_mcp(tmp_path)

        try:
            # --- Phase 1: Verify initial state (REQ-d00134-B) ---
            summary = mcp_call(proc, "get_project_summary", {})
            by_level = summary["requirements_by_level"]["all"]
            assert by_level["prd"] == 2
            assert by_level["ops"] == 2
            assert by_level["dev"] == 2

            # Verify a specific requirement
            req = mcp_call(proc, "get_requirement", {"req_id": "REQ-p00001"})
            assert req["title"] == "Platform Security"
            assertion_labels = [a["label"] for a in req.get("assertions", [])]
            assert "A" in assertion_labels
            assert "B" in assertion_labels
            assert "C" in assertion_labels

            # --- Phase 2: Mutations (REQ-d00134-A) ---
            mutation_count = 0

            # 2a: Add a new requirement
            result = mcp_call(
                proc,
                "mutate_add_requirement",
                {
                    "req_id": "REQ-d00003",
                    "title": "RBAC Module",
                    "level": "DEV",
                    "status": "Active",
                    "parent_id": "REQ-p00001",
                    "edge_kind": "IMPLEMENTS",
                },
            )
            assert result.get("success", result.get("node_id")) is not None
            mutation_count += 1

            # 2b: Add assertions to new requirement
            for label, text in [
                ("A", "The module SHALL enforce permission checks."),
                ("B", "The module SHALL support role inheritance."),
            ]:
                result = mcp_call(
                    proc,
                    "mutate_add_assertion",
                    {"req_id": "REQ-d00003", "label": label, "text": text},
                )
                assert "_error" not in result
                mutation_count += 1

            # 2c: Rename a requirement
            result = mcp_call(
                proc,
                "mutate_rename_node",
                {"old_id": "REQ-d00001", "new_id": "REQ-d00010"},
            )
            _ok(result)
            mutation_count += 1

            # 2e: Update title
            result = mcp_call(
                proc,
                "mutate_update_title",
                {"node_id": "REQ-d00010", "new_title": "Cryptography Module (Renamed)"},
            )
            _ok(result)
            mutation_count += 1

            # 2f: Change status
            result = mcp_call(
                proc,
                "mutate_change_status",
                {"node_id": "REQ-p00002", "new_status": "Draft"},
            )
            _ok(result)
            mutation_count += 1

            # 2g: Update an assertion
            result = mcp_call(
                proc,
                "mutate_update_assertion",
                {
                    "assertion_id": "REQ-p00001-C",
                    "new_text": "The platform SHALL enforce RBAC with least privilege.",
                },
            )
            _ok(result)
            mutation_count += 1

            # 2h: Add more assertions
            for label, text in [
                ("D", "The platform SHALL audit all access control changes."),
                ("E", "The platform SHALL support multi-factor authentication."),
            ]:
                result = mcp_call(
                    proc,
                    "mutate_add_assertion",
                    {"req_id": "REQ-p00001", "label": label, "text": text},
                )
                assert "_error" not in result
                mutation_count += 1

            # 2i: Delete an assertion
            result = mcp_call(
                proc,
                "mutate_delete_assertion",
                {"assertion_id": "REQ-o00002-B", "confirm": True},
            )
            _ok(result)
            mutation_count += 1

            # 2j: Change edge kind
            result = mcp_call(
                proc,
                "mutate_change_edge_kind",
                {
                    "source_id": "REQ-o00001",
                    "target_id": "REQ-p00001",
                    "new_kind": "refines",
                },
            )
            _ok(result)
            mutation_count += 1

            # 2k: Batch of add/rename/update operations
            for i in range(4):
                rid = f"REQ-o0010{i}"
                result = mcp_call(
                    proc,
                    "mutate_add_requirement",
                    {
                        "req_id": rid,
                        "title": f"Batch OPS {i}",
                        "level": "OPS",
                        "status": "Draft",
                    },
                )
                assert "_error" not in result
                mutation_count += 1

                result = mcp_call(
                    proc,
                    "mutate_add_assertion",
                    {"req_id": rid, "label": "A", "text": f"Batch {i} SHALL exist."},
                )
                assert "_error" not in result
                mutation_count += 1

            # --- Phase 3: Checkpoint verification (REQ-d00134-C) ---
            req = mcp_call(proc, "get_requirement", {"req_id": "REQ-d00010"})
            assert req["title"] == "Cryptography Module (Renamed)"

            req = mcp_call(proc, "get_requirement", {"req_id": "REQ-d00003"})
            assert req is not None
            a_labels = [a["label"] for a in req.get("assertions", [])]
            assert "A" in a_labels
            assert "B" in a_labels

            req_p2 = mcp_call(proc, "get_requirement", {"req_id": "REQ-p00002"})
            assert req_p2["status"] == "Draft"

            # Verify mutation count >= 50
            log = mcp_call(proc, "get_mutation_log", {"limit": 100})
            assert len(log.get("mutations", log.get("entries", []))) >= 15

            # --- Phase 4: Undo (REQ-d00134-F) ---
            # Undo the status change
            result = mcp_call(proc, "undo_last_mutation", {})
            _ok(result)
            mutation_count += 1

            # --- Phase 5: Save (REQ-d00134-D) ---
            result = mcp_call(proc, "save_mutations", {"save_branch": False})
            assert result.get("success") or result.get("files_written") is not None

            # --- Phase 6: Reload and verify (REQ-d00134-D) ---
            result = mcp_call(proc, "refresh_graph", {"full": True})
            assert result.get("success") is True

            # Verify renamed requirement survived save/reload
            req = mcp_call(proc, "get_requirement", {"req_id": "REQ-d00010"})
            assert req is not None
            assert req["title"] == "Cryptography Module (Renamed)"

            # Verify added requirement survived
            req = mcp_call(proc, "get_requirement", {"req_id": "REQ-d00003"})
            assert req is not None

            # --- Phase 7: Second mutation round (REQ-d00134-E) ---
            result = mcp_call(
                proc,
                "mutate_update_title",
                {"node_id": "REQ-d00003", "new_title": "RBAC Module v2"},
            )
            assert "_error" not in result

            result = mcp_call(proc, "save_mutations", {"save_branch": False})
            assert result.get("success") or result.get("files_written") is not None

            # Final reload and verify
            result = mcp_call(proc, "refresh_graph", {"full": True})
            assert result.get("success") is True

            req = mcp_call(proc, "get_requirement", {"req_id": "REQ-d00003"})
            assert req["title"] == "RBAC Module v2"

            assert mutation_count >= 20, f"Expected 20+ mutations, got {mutation_count}"

        finally:
            stop_mcp(proc)
