"""Health-check surfacing of section header depth issues (REQ-d00250-F)."""

# Verifies: REQ-d00250-F
from pathlib import Path

_CONFIG_TOML = """\
version = 3

[project]
name = "test-section-depth"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]
"""


def _build_graph(tmp_path: Path, spec: str):
    config_path = tmp_path / ".elspais.toml"
    config_path.write_text(_CONFIG_TOML)
    spec_dir = tmp_path / "spec"
    spec_dir.mkdir(exist_ok=True)
    (spec_dir / "f.md").write_text(spec)
    from elspais.graph.factory import build_graph

    return build_graph(
        spec_dirs=[spec_dir],
        config_path=config_path,
        repo_root=tmp_path,
        scan_code=False,
        scan_tests=False,
    )


def test_health_flags_too_shallow_section(tmp_path):
    """check_spec_needs_rewrite picks up section_header_depth as a dirty reason."""
    spec = (
        "## REQ-d00001: T\n\n"
        "**Level**: dev | **Status**: Active | **Implements**: -\n\n"
        "## Assertions\n\n"
        "A. X.\n\n"
        "*End* *T* | **Hash**: -\n"
    )
    graph = _build_graph(tmp_path, spec)
    from elspais.commands.health import check_spec_needs_rewrite

    check = check_spec_needs_rewrite(graph)
    assert not check.passed
    messages = [f.message for f in check.findings]
    assert any(
        "section_header_depth" in m for m in messages
    ), f"Expected section_header_depth in findings; got {messages!r}"


def test_health_flags_h6_unfixable(tmp_path):
    """check_unfixable_issues reports H6 reqs with section blocks."""
    spec = (
        "###### REQ-d00001: T\n\n"
        "**Level**: dev | **Status**: Active | **Implements**: -\n\n"
        "###### Assertions\n\n"
        "A. X.\n\n"
        "*End* *T* | **Hash**: -\n"
    )
    graph = _build_graph(tmp_path, spec)
    from elspais.commands.health import check_unfixable_issues

    check = check_unfixable_issues(graph)
    assert not check.passed
    assert check.severity == "error"
    messages = [f.message for f in check.findings]
    assert any(
        "section_header_depth_unfixable" in m for m in messages
    ), f"Expected section_header_depth_unfixable in findings; got {messages!r}"


def test_health_unfixable_clean_when_no_issues(tmp_path):
    """check_unfixable_issues passes when no unfixable issues exist."""
    spec = (
        "# REQ-d00001: T\n\n"
        "**Level**: dev | **Status**: Active | **Implements**: -\n\n"
        "## Assertions\n\n"
        "A. X.\n\n"
        "*End* *T* | **Hash**: -\n"
    )
    graph = _build_graph(tmp_path, spec)
    from elspais.commands.health import check_unfixable_issues

    check = check_unfixable_issues(graph)
    assert check.passed
