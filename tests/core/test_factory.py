# Implements: REQ-d00054-A
"""Tests for graph factory build_graph() — code directory scanning.

Verifies that build_graph() correctly scans [directories].code in addition
to [traceability].scan_patterns, with de-duplication and ignore filtering.
"""

from pathlib import Path

from elspais.graph import NodeKind
from elspais.graph.factory import build_graph


def _write_spec(spec_dir: Path, req_id: str = "REQ-p00001", title: str = "Test Req") -> None:
    """Write a minimal valid spec file with a single requirement."""
    spec_dir.mkdir(parents=True, exist_ok=True)
    (spec_dir / "reqs.md").write_text(
        f"""\
### {req_id}: {title}

**Level**: PRD | **Status**: Active

The system SHALL do something testable.

*End* *{title}* | **Hash**: ________
""",
        encoding="utf-8",
    )


def _write_code_file(file_path: Path, req_id: str = "REQ-p00001") -> None:
    """Write a Python file with an Implements comment."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(
        f"# Implements: {req_id}\ndef work(): pass\n",
        encoding="utf-8",
    )


class TestCodeDirectoryScanning:
    """Tests for [directories].code scanning in build_graph()."""

    def test_REQ_d00054_A_code_directories_scanned_when_scan_patterns_empty(
        self, tmp_path: Path
    ) -> None:
        """When [directories].code is set but scan_patterns is absent,
        CODE nodes from the code directory still appear in the graph."""
        # Config with code dirs but NO scan_patterns
        config_file = tmp_path / ".elspais.toml"
        config_file.write_text(
            """\
[project]
name = "test-code-dirs"

[directories]
spec = "spec"
code = ["src"]
""",
            encoding="utf-8",
        )

        _write_spec(tmp_path / "spec")
        _write_code_file(tmp_path / "src" / "main.py")

        graph = build_graph(
            config_path=config_file,
            repo_root=tmp_path,
            scan_tests=False,
            scan_sponsors=False,
        )

        code_nodes = list(graph.nodes_by_kind(NodeKind.CODE))
        assert (
            len(code_nodes) > 0
        ), "[directories].code should produce CODE nodes even without scan_patterns"
        # Verify the code node references our requirement
        code_ids = [n.id for n in code_nodes]
        has_ref = any("main.py" in cid for cid in code_ids)
        assert has_ref, f"Expected a CODE node from src/main.py, got: {code_ids}"

    def test_REQ_d00054_A_scan_patterns_and_code_directories_both_work(
        self, tmp_path: Path
    ) -> None:
        """When BOTH scan_patterns and [directories].code are set,
        CODE nodes appear from both sources."""
        config_file = tmp_path / ".elspais.toml"
        config_file.write_text(
            """\
[project]
name = "test-both-sources"

[directories]
spec = "spec"
code = ["lib"]

[traceability]
scan_patterns = ["scripts/*.py"]
""",
            encoding="utf-8",
        )

        _write_spec(tmp_path / "spec")
        _write_code_file(tmp_path / "lib" / "core.py")
        _write_code_file(tmp_path / "scripts" / "deploy.py")

        graph = build_graph(
            config_path=config_file,
            repo_root=tmp_path,
            scan_tests=False,
            scan_sponsors=False,
        )

        code_nodes = list(graph.nodes_by_kind(NodeKind.CODE))
        code_ids = [n.id for n in code_nodes]

        has_lib = any("core.py" in cid for cid in code_ids)
        has_scripts = any("deploy.py" in cid for cid in code_ids)

        assert has_lib, f"Expected CODE node from lib/core.py, got: {code_ids}"
        assert has_scripts, f"Expected CODE node from scripts/deploy.py, got: {code_ids}"

    def test_REQ_d00054_A_duplicate_files_not_double_counted(self, tmp_path: Path) -> None:
        """When a file is matched by BOTH scan_patterns AND [directories].code,
        only one CODE node is created (de-duplication via scanned_code_files set)."""
        config_file = tmp_path / ".elspais.toml"
        config_file.write_text(
            """\
[project]
name = "test-dedup"

[directories]
spec = "spec"
code = ["src"]

[traceability]
scan_patterns = ["src/**/*.py"]
""",
            encoding="utf-8",
        )

        _write_spec(tmp_path / "spec")
        _write_code_file(tmp_path / "src" / "overlap.py")

        graph = build_graph(
            config_path=config_file,
            repo_root=tmp_path,
            scan_tests=False,
            scan_sponsors=False,
        )

        code_nodes = list(graph.nodes_by_kind(NodeKind.CODE))
        # Filter to nodes from overlap.py specifically
        overlap_nodes = [n for n in code_nodes if "overlap.py" in n.id]

        assert len(overlap_nodes) == 1, (
            f"Expected exactly 1 CODE node from overlap.py (de-duplication), "
            f"got {len(overlap_nodes)}: {[n.id for n in overlap_nodes]}"
        )

    def test_REQ_d00054_A_ignore_dirs_respected_for_code_directories(self, tmp_path: Path) -> None:
        """When [directories].ignore lists a subdirectory, files within that
        subdirectory inside a [directories].code path are NOT scanned."""
        config_file = tmp_path / ".elspais.toml"
        config_file.write_text(
            """\
[project]
name = "test-ignore"

[directories]
spec = "spec"
code = ["src"]
ignore = ["vendor"]
""",
            encoding="utf-8",
        )

        _write_spec(tmp_path / "spec")
        # This file is inside src/vendor/ which should be ignored
        _write_code_file(tmp_path / "src" / "vendor" / "foo.py")
        # This file is in src/ top-level which should be scanned
        _write_code_file(tmp_path / "src" / "app.py")

        graph = build_graph(
            config_path=config_file,
            repo_root=tmp_path,
            scan_tests=False,
            scan_sponsors=False,
        )

        code_nodes = list(graph.nodes_by_kind(NodeKind.CODE))
        code_ids = [n.id for n in code_nodes]

        vendor_nodes = [cid for cid in code_ids if "vendor" in cid]
        app_nodes = [cid for cid in code_ids if "app.py" in cid]

        assert len(vendor_nodes) == 0, (
            f"Files in ignored 'vendor' dir should NOT produce CODE nodes, "
            f"but got: {vendor_nodes}"
        )
        assert (
            len(app_nodes) > 0
        ), f"Non-ignored src/app.py should produce CODE node, got: {code_ids}"

    def test_REQ_d00054_A_code_directories_default_src_when_exists(self, tmp_path: Path) -> None:
        """When [directories].code is not set in config, the default 'src'
        directory is still scanned if it exists."""
        config_file = tmp_path / ".elspais.toml"
        config_file.write_text(
            """\
[project]
name = "test-default-src"

[directories]
spec = "spec"
""",
            encoding="utf-8",
        )

        _write_spec(tmp_path / "spec")
        # get_code_directories defaults to ["src"]
        _write_code_file(tmp_path / "src" / "default.py")

        graph = build_graph(
            config_path=config_file,
            repo_root=tmp_path,
            scan_tests=False,
            scan_sponsors=False,
        )

        code_nodes = list(graph.nodes_by_kind(NodeKind.CODE))
        code_ids = [n.id for n in code_nodes]

        has_default = any("default.py" in cid for cid in code_ids)
        assert has_default, f"Default src/ directory should be scanned, got: {code_ids}"

    def test_REQ_d00054_A_nonexistent_code_directory_is_skipped(self, tmp_path: Path) -> None:
        """When [directories].code lists a non-existent directory, build_graph
        does not crash — the directory is silently skipped."""
        config_file = tmp_path / ".elspais.toml"
        config_file.write_text(
            """\
[project]
name = "test-missing-dir"

[directories]
spec = "spec"
code = ["does_not_exist"]
""",
            encoding="utf-8",
        )

        _write_spec(tmp_path / "spec")

        # Should not raise
        graph = build_graph(
            config_path=config_file,
            repo_root=tmp_path,
            scan_tests=False,
            scan_sponsors=False,
        )

        code_nodes = list(graph.nodes_by_kind(NodeKind.CODE))
        assert len(code_nodes) == 0, "Non-existent code directory should produce zero CODE nodes"
