# Verifies: REQ-d00322-F, REQ-d00322-G
"""The `evidence` trace preset lists each assertion's code and tests.

The report an *Evidence Snapshot* holds names every location by its
repository-relative file and line, so it reads the same on every machine.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from elspais.commands._requests import TraceRequest
from elspais.commands.trace import REPORT_PRESETS, preset_from_args, render_trace
from elspais.config import get_config
from tests.core.test_target_ingestion import (
    _RUNNER_A,
    _RUNNER_A_DART,
    _RUNNER_B,
    _RUNNER_B_DART,
    _SHARED_CONFIG,
    _SHARED_DART,
    _SHARED_FILE,
    _SHARED_LINE,
    _SHARED_SPEC,
    _machine_run,
)

_CODE_FILE = "lib/boot.dart"
_CODE = """\
void boot() {
  // Implements: REQ-d00001-A
  identity();
}

void halt() {
  // Implements: REQ-d00002-A
  release();
}
"""
# A second requirement, so the table has more than one row to keep together.
_SPEC = (
    _SHARED_SPEC
    + """
### REQ-d00002: Halt

**Level**: dev | **Status**: Active

## Assertions

A. The system SHALL release the identity.

*End* *Halt*
---
"""
)
_CODE_CONFIG = """
[scanning.code]
directories = ["lib"]
file_patterns = ["*.dart"]
"""


def _project(root: Path, outcome_b: str = "success") -> Path:
    files = {
        ".elspais.toml": _SHARED_CONFIG + _CODE_CONFIG,
        "spec/requirements.md": _SPEC,
        _SHARED_FILE: _SHARED_DART,
        _RUNNER_A: _RUNNER_A_DART,
        _RUNNER_B: _RUNNER_B_DART,
        _CODE_FILE: _CODE,
        ".results/flutter/machine.jsonl": "\n".join(
            [
                _machine_run(root, _RUNNER_A, _SHARED_FILE, "success", 1),
                _machine_run(root, _RUNNER_B, _SHARED_FILE, outcome_b, 3),
            ]
        )
        + "\n",
    }
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def _report(root: Path) -> str:
    from elspais.graph.factory import build_graph

    graph = build_graph(repo_root=root)
    config = get_config(root / ".elspais.toml", start_path=root, quiet=True)
    return render_trace(graph, config, TraceRequest(), "markdown", REPORT_PRESETS["evidence"])


def _evidence_block(report: str) -> list[str]:
    lines = report.splitlines()
    start = lines.index("<details><summary>Evidence</summary>")
    return lines[start : lines.index("</details>", start) + 1]


# Verifies: REQ-d00322-G
def test_each_assertion_names_its_code_and_tests_with_outcomes(tmp_path):
    root = _project(tmp_path, outcome_b="failure")

    block = _evidence_block(_report(root))

    assert block == [
        "<details><summary>Evidence</summary>",
        "",
        "**A**",
        "",
        "Code:",
        "",
        f"- {_CODE_FILE}:2",
        "",
        "Tests:",
        "",
        f"- {_RUNNER_B}:3 -- awaiting a result",
        f"- {_SHARED_FILE}:{_SHARED_LINE} boot two stores share one identity -- failed, passed",
        "",
        "</details>",
    ]


# Verifies: REQ-d00322-G
def test_the_report_holds_no_absolute_path(tmp_path):
    """A `test:` or `code:` id carries an absolute path; the report names none."""
    root = _project(tmp_path)

    report = _report(root)

    assert str(tmp_path) not in report
    assert "test:" not in report
    assert "code:" not in report


# Verifies: REQ-d00322-F
def test_two_renders_of_one_graph_are_identical(tmp_path):
    from elspais.graph.factory import build_graph

    root = _project(tmp_path)
    graph = build_graph(repo_root=root)
    config = get_config(root / ".elspais.toml", start_path=root, quiet=True)
    preset = REPORT_PRESETS["evidence"]

    first = render_trace(graph, config, TraceRequest(), "markdown", preset)
    second = render_trace(graph, config, TraceRequest(), "markdown", preset)

    assert first == second


# Verifies: REQ-d00322-F
def test_the_same_project_in_another_directory_renders_the_same_report(tmp_path):
    """The report depends on the project, never on where its tree sits."""
    first = _report(_project(tmp_path / "one"))
    second = _report(_project(tmp_path / "two"))

    assert first == second


# Verifies: REQ-d00322-F
def test_the_evidence_preset_is_named_on_the_command_line(tmp_path):
    preset = preset_from_args(argparse.Namespace(preset="evidence"))

    assert preset.include_code_refs is True
    assert preset.include_test_refs is True
    assert preset.values == REPORT_PRESETS["evidence"].values


# Verifies: REQ-d00322-G
def test_the_other_presets_list_no_evidence(tmp_path):
    from elspais.graph.factory import build_graph

    root = _project(tmp_path)
    graph = build_graph(repo_root=root)
    config = get_config(root / ".elspais.toml", start_path=root, quiet=True)
    preset = preset_from_args(argparse.Namespace(preset="full", show_tests=True))

    report = render_trace(graph, config, TraceRequest(), "markdown", preset)

    assert "<details><summary>Evidence</summary>" not in report


def _table_rows(report: str) -> list[int]:
    """The line numbers of the report's table lines, asserting they run unbroken."""
    lines = report.splitlines()
    table = [i for i, line in enumerate(lines) if line.startswith("|")]
    assert table == list(range(table[0], table[-1] + 1)), "a non-table line splits the table"
    return table


# Verifies: REQ-d00322-G
def test_the_evidence_follows_one_unbroken_table(tmp_path):
    """Each requirement's evidence is written after the table, in row order, under its name."""
    report = _report(_project(tmp_path))
    lines = report.splitlines()

    table = _table_rows(report)
    # One header, its separator, and one row per requirement.
    assert [lines[i].split(" | ")[0] for i in table[2:]] == ["| REQ-d00001", "| REQ-d00002"]
    assert lines[table[-1] + 1 :].count("## Evidence") == 1
    first = lines.index("### REQ-d00001: Boot")
    second = lines.index("### REQ-d00002: Halt")
    assert table[-1] < lines.index("## Evidence") < first < second
    assert lines[second:].index("<details><summary>Evidence</summary>") >= 0
    assert f"- {_CODE_FILE}:7" in lines[second:]


# Verifies: REQ-d00322-G
def test_the_verbose_test_refs_follow_one_unbroken_table(tmp_path):
    """The verbose detail blocks are held back until the table is whole."""
    from elspais.graph.factory import build_graph

    root = _project(tmp_path)
    graph = build_graph(repo_root=root)
    config = get_config(root / ".elspais.toml", start_path=root, quiet=True)
    preset = preset_from_args(argparse.Namespace(preset="full", verbose=True))

    report = render_trace(graph, config, TraceRequest(), "markdown", preset)
    lines = report.splitlines()

    table = _table_rows(report)
    assert len(table) == 4
    assert table[-1] < lines.index("## Details") < lines.index("### REQ-d00001: Boot")
    assert any(line.startswith("<details><summary>Test Refs") for line in lines[table[-1] :])
