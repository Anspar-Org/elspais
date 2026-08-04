# tests/core/test_prescan_attribution.py
# Verifies: REQ-d00254-K, REQ-d00254-L, REQ-d00254-M, REQ-d00254-N
"""Per-test attribution: built-in prescan per language, and the external
test-prescan command (transport, capability, and per-file precedence).

Covers:
  K -- every configured framework binds each scanned test to its own identity
       within its source file and to that test's line extent (Python via
       ast_prescan, Dart via dart_prescan, both reached through dispatch_test).
  L -- a configured external prescan command supplies per-test attribution for
       the candidate test files.
  M -- the exchange with that command: candidate file paths on its stdin,
       attribution records on its stdout, each record binding one test to its
       file, its identity in that file, and its starting line.
  N -- records returned for a file take precedence over built-in attribution,
       resolved per file (both routes live in one run).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from elspais.graph.parsers.lark import FileDispatcher
from elspais.graph.parsers.prescan import ast_prescan, dart_prescan
from elspais.utilities.patterns import IdPatternConfig, IdResolver

# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def dispatcher():
    config = IdPatternConfig.from_dict(
        {
            "project": {"namespace": "REQ"},
            "id-patterns": {
                "canonical": "{namespace}-{type.letter}{component}",
                "aliases": {"short": "{type.letter}{component}"},
                "types": {
                    "prd": {"level": 1, "aliases": {"letter": "p"}},
                    "ops": {"level": 2, "aliases": {"letter": "o"}},
                    "dev": {"level": 3, "aliases": {"letter": "d"}},
                },
                "component": {"style": "numeric", "digits": 5, "leading_zeros": True},
                "assertions": {"label_style": "uppercase", "max_count": 26},
            },
        }
    )
    return FileDispatcher(IdResolver(config))


def _numbered(src: str) -> list[tuple[int, str]]:
    return [(i + 1, text) for i, text in enumerate(src.split("\n"))]


def _test_refs(items) -> list:
    return [i for i in items if i.content_type == "test_ref"]


def _identity(parsed_data: dict) -> tuple:
    """The attribution identity a test ref is bound to within its file."""
    return (
        parsed_data.get("class_name"),
        parsed_data.get("function_name"),
        parsed_data.get("function_line"),
    )


# ---------------------------------------------------------------------------
# K -- per-framework identity + line extent
# ---------------------------------------------------------------------------

#  1: def test_alpha():
#  2:     # Verifies: REQ-p00001-A
#  3:     assert True
#  4:
#  5:
#  6: def test_beta():
#  7:     # Verifies: REQ-p00001-B
#  8:     assert True
PY_SRC = """\
def test_alpha():
    # Verifies: REQ-p00001-A
    assert True


def test_beta():
    # Verifies: REQ-p00001-B
    assert True
"""

#  1: void main() {
#  2:   test('alpha', () {
#  3:     // Verifies: REQ-p00001-A
#  4:     expect(1, 1);
#  5:   });
#  6:   test('beta', () {
#  7:     // Verifies: REQ-p00001-B
#  8:     expect(2, 2);
#  9:   });
# 10: }
DART_SRC = """\
void main() {
  test('alpha', () {
    // Verifies: REQ-p00001-A
    expect(1, 1);
  });
  test('beta', () {
    // Verifies: REQ-p00001-B
    expect(2, 2);
  });
}
"""


def _ast_prescan_lines(lines):
    return ast_prescan("\n".join(text for _, text in lines), lines)


# (label, path, source, prescan callable, ref-line -> owning test start,
#  expected (start, end) extent per test)
FRAMEWORKS = [
    pytest.param(
        "tests/test_sample.py",
        PY_SRC,
        _ast_prescan_lines,
        {2: 1, 7: 6},
        {1: (1, 3), 6: (6, 8)},
        id="python-ast_prescan",
    ),
    pytest.param(
        "test/sample_test.dart",
        DART_SRC,
        dart_prescan,
        {3: 2, 7: 6},
        {2: (2, 5), 6: (6, 9)},
        id="dart-dart_prescan",
    ),
]


# Verifies: REQ-d00254-K
@pytest.mark.parametrize("path,src,prescan,ref_to_test,extents", FRAMEWORKS)
def test_each_scanned_test_gets_its_own_identity(
    dispatcher, path, src, prescan, ref_to_test, extents
):
    """Two tests in one file are bound to two distinct identities, each anchored
    at its own test's start line -- not merged into a single unit."""
    refs = _test_refs(dispatcher.dispatch_test(src, file_path=path))
    assert len(refs) == 2, f"expected one test_ref per test, got {len(refs)}"

    by_ref_line = {r.start_line: r.parsed_data for r in refs}
    assert sorted(by_ref_line) == sorted(ref_to_test), f"ref lines {sorted(by_ref_line)}"

    for ref_line, test_start in ref_to_test.items():
        data = by_ref_line[ref_line]
        assert data["verifies"], f"ref at {ref_line} lost its Verifies target"
        assert data["function_line"] == test_start, (
            f"ref at line {ref_line} should bind to the test starting at "
            f"{test_start}, got {data['function_line']}"
        )

    identities = [_identity(d) for d in by_ref_line.values()]
    assert len(set(identities)) == 2, f"tests share one identity: {identities}"


# Verifies: REQ-d00254-K
@pytest.mark.parametrize("path,src,prescan,ref_to_test,extents", FRAMEWORKS)
def test_each_scanned_test_gets_its_own_line_extent(
    dispatcher, path, src, prescan, ref_to_test, extents
):
    """The prescan behind each framework yields a per-test line extent: every
    line of a test resolves to that test's (start, end), and one test's extent
    never reaches into the next test."""
    line_context, all_test_funcs, _first = prescan(_numbered(src))

    assert sorted(f[0] for f in all_test_funcs) == sorted(extents), (
        f"expected one scanned unit per test at {sorted(extents)}, "
        f"got {sorted(f[0] for f in all_test_funcs)}"
    )

    for start, (exp_start, exp_end) in extents.items():
        for line in range(exp_start, exp_end + 1):
            _fn, _cn, got_start, got_end = line_context[line]
            assert (got_start, got_end) == (exp_start, exp_end), (
                f"line {line} of the test starting at {start} resolved to "
                f"extent ({got_start}, {got_end}), expected ({exp_start}, {exp_end})"
            )

    starts = sorted(extents)
    first_end = extents[starts[0]][1]
    assert first_end < starts[1], (
        f"first test's extent ends at {first_end}, at or past the next test's "
        f"start line {starts[1]} -- the two tests were merged"
    )


# ---------------------------------------------------------------------------
# L / M -- the external prescan command exchange
# ---------------------------------------------------------------------------

# A stub prescan command: records the paths it is handed on stdin, then emits
# attribution records on stdout for the file named in EXTERNAL_TARGET only.
STUB_PRESCAN = """\
import json, os, sys

paths = [p for p in sys.stdin.read().splitlines() if p.strip()]
with open(os.environ["PRESCAN_STDIN_CAPTURE"], "w") as fh:
    fh.write("\\n".join(paths))

target = os.environ["PRESCAN_TARGET"]
emit_absolute = os.environ.get("PRESCAN_ABSOLUTE") == "1"
records = []
for path in paths:
    if not path.endswith(target):
        continue
    out_path = os.path.abspath(path) if emit_absolute else path
    records.append({"file": out_path, "function": "scenario_one", "class": "Suite", "line": 1})
    records.append({"file": out_path, "function": "scenario_two", "class": "Suite", "line": 6})
print(json.dumps(records))
"""

FILE_ONE = "tests/test_one.py"
FILE_TWO = "tests/test_two.py"

SRC_ONE = PY_SRC  # test_alpha (line 1) / test_beta (line 6) under built-in scan
SRC_TWO = """\
def test_gamma():
    # Verifies: REQ-p00001-C
    assert True
"""


def _make_project(tmp_path: Path, *, emit_absolute: bool = False) -> tuple[Path, str, Path]:
    """Write a project with two scannable test files, one unscannable helper,
    and a stub prescan command. Returns (repo_root, command, stdin_capture)."""
    project = tmp_path / "project"
    (project / "tests").mkdir(parents=True)
    (project / FILE_ONE).write_text(SRC_ONE, encoding="utf-8")
    (project / FILE_TWO).write_text(SRC_TWO, encoding="utf-8")
    # Does not match ["test_*.py"] -- must not be offered to the command.
    (project / "tests" / "helper.py").write_text("X = 1\n", encoding="utf-8")

    script = project / "prescan_stub.py"
    script.write_text(STUB_PRESCAN, encoding="utf-8")

    capture = project / "stdin_capture.txt"
    env = (
        f'PRESCAN_STDIN_CAPTURE="{capture}" '
        f'PRESCAN_TARGET="test_one.py" '
        f'PRESCAN_ABSOLUTE="{"1" if emit_absolute else "0"}" '
    )
    command = f'{env}"{sys.executable}" "{script}"'
    return project, command, capture


# Verifies: REQ-d00254-M
def test_prescan_command_receives_candidate_paths_on_stdin(tmp_path):
    """The candidate test file paths -- and only those -- are written to the
    command's stdin, one per line, relative to the repo root."""
    from elspais.graph.factory import _run_prescan_command

    project, command, capture = _make_project(tmp_path)

    _run_prescan_command(command, ["tests"], ["test_*.py"], [], project)

    received = capture.read_text(encoding="utf-8").splitlines()
    assert sorted(received) == [FILE_ONE, FILE_TWO], f"stdin carried {received}"


# Verifies: REQ-d00254-M
def test_prescan_command_stdout_records_govern_attribution(tmp_path, dispatcher):
    """Records read from the command's stdout bind one test each to its file,
    its identity in that file, and its starting line -- and those records are
    what the scanned file's tests are then attributed to."""
    from elspais.graph.factory import _run_prescan_command

    project, command, _capture = _make_project(tmp_path)

    prescan_data = _run_prescan_command(command, ["tests"], ["test_*.py"], [], project)

    assert prescan_data is not None, "command produced no attribution"
    assert list(prescan_data) == [FILE_ONE], f"records grouped under {list(prescan_data)}"
    assert [(r["class"], r["function"], r["line"]) for r in prescan_data[FILE_ONE]] == [
        ("Suite", "scenario_one", 1),
        ("Suite", "scenario_two", 6),
    ]

    refs = _test_refs(
        dispatcher.dispatch_test(SRC_ONE, file_path=FILE_ONE, prescan_data=prescan_data)
    )
    assert sorted(_identity(r.parsed_data) for r in refs) == [
        ("Suite", "scenario_one", 1),
        ("Suite", "scenario_two", 6),
    ], "attribution did not follow the records emitted on stdout"


# Verifies: REQ-d00254-M
def test_prescan_command_failure_yields_no_attribution(tmp_path, capsys):
    """A command that exits non-zero produces no attribution (the built-in
    route stays in charge) rather than a partial or crashing read."""
    from elspais.graph.factory import _run_prescan_command

    project, _command, _capture = _make_project(tmp_path)
    failing = f'"{sys.executable}" -c "import sys; sys.exit(3)"'

    assert _run_prescan_command(failing, ["tests"], ["test_*.py"], [], project) is None
    assert "prescan_command failed" in capsys.readouterr().err


# Verifies: REQ-d00254-L
def test_external_command_supplies_per_test_attribution(tmp_path, dispatcher):
    """With a command configured, the file's tests are attributed per the
    command's records -- identities the built-in scan would never produce."""
    from elspais.graph.factory import _run_prescan_command

    project, command, _capture = _make_project(tmp_path)
    prescan_data = _run_prescan_command(command, ["tests"], ["test_*.py"], [], project)

    builtin = _test_refs(dispatcher.dispatch_test(SRC_ONE, file_path=FILE_ONE))
    external = _test_refs(
        dispatcher.dispatch_test(SRC_ONE, file_path=FILE_ONE, prescan_data=prescan_data)
    )

    assert sorted(_identity(r.parsed_data) for r in builtin) == [
        (None, "test_alpha", 1),
        (None, "test_beta", 6),
    ]
    assert sorted(_identity(r.parsed_data) for r in external) == [
        ("Suite", "scenario_one", 1),
        ("Suite", "scenario_two", 6),
    ]


# ---------------------------------------------------------------------------
# N -- per-file precedence, both routes live in one run
# ---------------------------------------------------------------------------


# Verifies: REQ-d00254-N
def test_external_records_take_precedence_per_file(tmp_path, dispatcher):
    """One prescan run, two scanned files: the file the command reported on is
    attributed from its records; the file it said nothing about keeps built-in
    attribution."""
    from elspais.graph.factory import _run_prescan_command

    project, command, _capture = _make_project(tmp_path)
    prescan_data = _run_prescan_command(command, ["tests"], ["test_*.py"], [], project)

    covered = _test_refs(
        dispatcher.dispatch_test(SRC_ONE, file_path=FILE_ONE, prescan_data=prescan_data)
    )
    uncovered = _test_refs(
        dispatcher.dispatch_test(SRC_TWO, file_path=FILE_TWO, prescan_data=prescan_data)
    )

    assert sorted(_identity(r.parsed_data) for r in covered) == [
        ("Suite", "scenario_one", 1),
        ("Suite", "scenario_two", 6),
    ], "external records did not take precedence for the reported file"
    assert [_identity(r.parsed_data) for r in uncovered] == [
        (None, "test_gamma", 1)
    ], "built-in attribution was lost for the file the command did not report on"


def _built_test_node_ids(project: Path, command: str) -> set[str]:
    from elspais.graph.factory import build_graph
    from elspais.graph.GraphNode import NodeKind

    (project / "spec").mkdir(exist_ok=True)
    (project / "spec" / "reqs.md").write_text(
        "## REQ-p00001: Sample\n\n"
        "**Level**: PRD | **Status**: Active\n\n"
        "### Assertions\n\n"
        "A. The system SHALL alpha.\n\n"
        "B. The system SHALL beta.\n\n"
        "C. The system SHALL gamma.\n\n"
        "*End* *Sample* | **Hash**: ________\n",
        encoding="utf-8",
    )
    (project / ".elspais.toml").write_text(
        "version = 3\n\n"
        '[project]\nname = "prescan-fixture"\nnamespace = "REQ"\n\n'
        '[scanning.spec]\ndirectories = ["spec"]\n\n'
        '[scanning.test]\nenabled = true\ndirectories = ["tests"]\n'
        'file_patterns = ["test_*.py"]\n'
        f"prescan_command = {json.dumps(command)}\n",
        encoding="utf-8",
    )
    graph = build_graph(
        config_path=project / ".elspais.toml",
        repo_root=project,
        scan_code=False,
    )
    return {n.id for n in graph.iter_by_kind(NodeKind.TEST)}


# Verifies: REQ-d00254-L+N
def test_external_records_take_precedence_end_to_end(tmp_path):
    """Full build with a prescan command configured: the reported file's TEST
    nodes carry the command's identities, the unreported file's carry the
    built-in ones."""
    project, command, _capture = _make_project(tmp_path)

    assert _built_test_node_ids(project, command) == {
        f"test:{FILE_ONE}::Suite::scenario_one",
        f"test:{FILE_ONE}::Suite::scenario_two",
        f"test:{FILE_TWO}::test_gamma",
    }


# Verifies: REQ-d00254-N
def test_external_records_take_precedence_end_to_end_absolute_paths(tmp_path):
    """Same build, with the command echoing absolute paths (the only path form
    the current wiring accepts): precedence resolves per file."""
    project, command, _capture = _make_project(tmp_path, emit_absolute=True)

    assert _built_test_node_ids(project, command) == {
        f"test:{FILE_ONE}::Suite::scenario_one",
        f"test:{FILE_ONE}::Suite::scenario_two",
        f"test:{FILE_TWO}::test_gamma",
    }
