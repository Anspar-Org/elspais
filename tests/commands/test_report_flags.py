"""Shared report flags: where they stand, what they render, where they are read.

Every invocation goes through ``elspais.cli.main`` in-process, against one
small git-initialised project. The project sets ``cli_ttl = 0`` so no command
starts a daemon, and it is not inside any other repository, so every command
builds its own graph from the project's files.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from elspais.cli import _lift_global_options, _sections_first, main
from elspais.commands.report import FORMAT_SUPPORT, QUIET_FORMATS

_CONFIG = """\
version = 5
cli_ttl = 0

[project]
name = "report-flags"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]

[scanning.test]
enabled = true
directories = ["tests"]
file_patterns = ["test_*.py"]

[[scanning.test.targets]]
name = "unit"
reporter = "junit"
results = "results.xml"

[[scanning.test.targets]]
name = "integration"
reporter = "junit"
results = "results.xml"

[changelog]
hash_current = false
present = false
"""

_SPEC = """\
# REQ-p00001: Test Requirement

**Level**: PRD | **Status**: Active

The body of the test requirement.

## Assertions

A. The system SHALL do something.

*End* *Test Requirement* | **Hash**: abcd1234
"""

_TEST = """\
# Verifies: REQ-p00001-A
def test_something():
    pass
"""


@pytest.fixture(scope="module")
def project(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("report_flags")
    (root / ".elspais.toml").write_text(_CONFIG)
    (root / "spec").mkdir()
    (root / "spec" / "requirements.md").write_text(_SPEC)
    (root / "tests").mkdir()
    (root / "tests" / "test_one.py").write_text(_TEST)
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.com",
    }
    for cmd in (["init", "-q", "-b", "main"], ["add", "."], ["commit", "-qm", "init"]):
        subprocess.run(["git", *cmd], cwd=root, env=env, check=True)
    return root


@pytest.fixture
def invoke(project, capsys, monkeypatch):
    """Run ``elspais <argv>`` in the project; return (exit code, stdout, stderr)."""
    monkeypatch.chdir(project)

    def _invoke(argv: list[str]) -> tuple[int, str, str]:
        capsys.readouterr()
        try:
            rc = main(list(argv))
        except SystemExit as exc:
            rc = exc.code if isinstance(exc.code, int) else 2
        captured = capsys.readouterr()
        return rc, captured.out, captured.err

    return _invoke


def _lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# Placement: a shared flag means the same thing before or after the sections
# ---------------------------------------------------------------------------

_FLAGS = {
    "-q": ["-q"],
    "--quiet": ["--quiet"],
    "-v": ["-v"],
    "--verbose": ["--verbose"],
    "--lenient": ["--lenient"],
    "--format json": ["--format", "json"],
}

_SINGLE_SECTIONS = ("checks", "summary", "trace", "gaps", "changed", "unresolved", "malformed")

# The sections whose standalone command reads --lenient. Elsewhere it is
# refused, in both placements (test_an_unread_lenient_is_refused_wherever_it_stands).
_LENIENT_SECTIONS = frozenset({"checks", "unresolved", "malformed"})

# A composition of sections that each read the flag.
_COMPOSED = {
    "--lenient": ["checks", "unresolved", "malformed"],
}
_DEFAULT_COMPOSED = ["checks", "summary", "trace"]


def _single_cases():
    for flag in _FLAGS:
        for section in _SINGLE_SECTIONS:
            if flag == "--lenient" and section not in _LENIENT_SECTIONS:
                continue
            if flag == "--format json" and "json" not in FORMAT_SUPPORT[section]:
                continue
            yield pytest.param(flag, section, id=f"{section}[{flag}]")


def _assert_accepted(rc: int, err: str) -> None:
    assert rc != 2, err
    assert "Unrecognized" not in err
    assert "unrecognized arguments" not in err


class TestFlagPlacement:
    """A shared flag has the same effect wherever it stands (REQ-d00085-O)."""

    # Verifies: REQ-d00085-O+D
    @pytest.mark.parametrize(("flag", "section"), list(_single_cases()))
    def test_single_section_reads_the_flag_alike_first_and_last(self, invoke, flag, section):
        spelled = _FLAGS[flag]
        rc_first, out_first, err_first = invoke([*spelled, section])
        rc_last, out_last, err_last = invoke([section, *spelled])

        _assert_accepted(rc_first, err_first)
        _assert_accepted(rc_last, err_last)
        assert out_first.strip(), f"`{flag} {section}` printed nothing"
        assert out_first == out_last
        assert rc_first == rc_last

    # Verifies: REQ-d00085-O+B
    @pytest.mark.parametrize("flag", list(_FLAGS))
    def test_composed_report_reads_the_flag_alike_first_and_last(self, invoke, flag):
        sections = _COMPOSED.get(flag, _DEFAULT_COMPOSED)
        spelled = _FLAGS[flag]
        rc_first, out_first, err_first = invoke([*spelled, *sections])
        rc_last, out_last, err_last = invoke([*sections, *spelled])

        _assert_accepted(rc_first, err_first)
        _assert_accepted(rc_last, err_last)
        assert out_first.strip()
        assert out_first == out_last
        assert rc_first == rc_last

    # Verifies: REQ-d00085-O+Q
    @pytest.mark.parametrize("section", sorted(set(_SINGLE_SECTIONS) - _LENIENT_SECTIONS))
    def test_an_unread_lenient_is_refused_wherever_it_stands(self, invoke, section):
        """A section that does not read --lenient refuses it before and after."""
        rc_first, _out, err_first = invoke(["--lenient", section])
        rc_last, _out, err_last = invoke([section, "--lenient"])
        assert rc_first == rc_last == 2
        assert "--lenient" in err_first and "--lenient" in err_last


# ---------------------------------------------------------------------------
# Quiet: one summary line per section
# ---------------------------------------------------------------------------


def _quiet_cases():
    for section in sorted(FORMAT_SUPPORT):
        for fmt in sorted(QUIET_FORMATS):
            if fmt not in FORMAT_SUPPORT[section]:
                continue
            yield pytest.param(section, fmt, id=f"{section}-{fmt}")


def _machine_format_cases():
    for section in sorted(FORMAT_SUPPORT):
        for fmt in sorted(FORMAT_SUPPORT[section] - QUIET_FORMATS):
            yield pytest.param(section, fmt, id=f"{section}-{fmt}")


class TestQuiet:
    """-q renders each section as one summary line in a format a person reads,
    and leaves a machine format whole (REQ-d00085-F)."""

    # Verifies: REQ-d00085-F
    @pytest.mark.parametrize(("section", "fmt"), list(_quiet_cases()))
    def test_a_quiet_section_prints_exactly_one_line(self, invoke, section, fmt):
        rc, out, err = invoke([section, "-q", "--format", fmt])
        _assert_accepted(rc, err)
        assert len(_lines(out)) == 1, out

    # Verifies: REQ-d00085-F+D
    def test_a_quiet_composed_report_prints_one_line_per_section(self, invoke):
        sections = ["checks", "summary", "trace"]
        rc, out, err = invoke([*sections, "-q"])
        _assert_accepted(rc, err)

        alone = []
        for section in sections:
            _rc, single_out, _err = invoke([section, "-q"])
            alone.extend(_lines(single_out))
        assert _lines(out) == alone
        assert len(alone) == len(sections)

    # Verifies: REQ-d00085-F
    @pytest.mark.parametrize(("section", "fmt"), list(_machine_format_cases()))
    def test_quiet_leaves_a_machine_format_whole(self, invoke, section, fmt):
        """A machine format is read by a program that relies on its shape, so
        -q leaves the document exactly as it is without the flag."""
        rc_quiet, quiet, err = invoke([section, "-q", "--format", fmt])
        _assert_accepted(rc_quiet, err)
        rc_loud, loud, _err = invoke([section, "--format", fmt])
        assert quiet == loud
        assert rc_quiet == rc_loud
        assert len(_lines(quiet)) > 1, f"`{section} --format {fmt}` printed a single line"


# ---------------------------------------------------------------------------
# Verbose: the detail a section withholds by default
# ---------------------------------------------------------------------------


class TestVerbose:
    """-v renders each section with the detail it withholds (REQ-d00085-K)."""

    # Verifies: REQ-d00085-K
    @pytest.mark.parametrize("fmt", ["markdown", "json"])
    def test_verbose_trace_is_the_full_preset_with_every_detail(self, invoke, fmt):
        _rc, verbose, err = invoke(["trace", "-v", "--format", fmt])
        _rc, spelled, _err = invoke(
            ["trace", "--preset", "full", "--body", "--assertions", "--tests", "--format", fmt]
        )
        assert verbose == spelled, err

    # Verifies: REQ-d00085-K
    def test_verbose_trace_states_what_the_default_withholds(self, invoke):
        import json

        _rc, default_md, _err = invoke(["trace"])
        _rc, verbose_md, _err = invoke(["trace", "-v"])
        assert "Test Refs" in verbose_md
        assert "Test Refs" not in default_md

        _rc, default_json, _err = invoke(["trace", "--format", "json"])
        _rc, verbose_json, _err = invoke(["trace", "-v", "--format", "json"])
        default_node = json.loads(default_json)["nodes"][0]
        verbose_node = json.loads(verbose_json)["nodes"][0]
        withheld = {"body", "assertions", "test_refs"}
        assert withheld <= set(verbose_node)
        assert not withheld & set(default_node)
        assert verbose_node["assertions"], "verbose trace states no assertions"

    # Verifies: REQ-d00085-K
    @pytest.mark.parametrize("preset", ["minimal", "standard"])
    def test_verbose_with_a_lighter_preset_is_refused(self, invoke, preset):
        rc, out, err = invoke(["trace", "-v", "--preset", preset])
        assert rc != 0
        assert "--preset" in err
        assert "Traceability Matrix" not in out

    # Verifies: REQ-d00085-K
    def test_verbose_with_the_full_preset_is_accepted(self, invoke):
        rc_v, verbose, _err = invoke(["trace", "-v"])
        rc_full, full, err = invoke(["trace", "-v", "--preset", "full"])
        assert rc_v == rc_full == 0, err
        assert verbose == full

    # Verifies: REQ-d00085-K
    @pytest.mark.parametrize("section", ["summary", "gaps", "changed"])
    def test_verbose_leaves_a_section_with_nothing_withheld_unchanged(self, invoke, section):
        _rc, default, _err = invoke([section])
        _rc, verbose, _err = invoke([section, "-v"])
        assert verbose == default

    # Verifies: REQ-d00085-K+D
    def test_verbose_composed_trace_is_the_verbose_trace_alone(self, invoke):
        _rc, alone, _err = invoke(["trace", "-v"])
        _rc, composed, err = invoke(["summary", "trace", "-v"])
        assert composed.rstrip("\n").endswith(alone.rstrip("\n")), err


# ---------------------------------------------------------------------------
# Test-target selection composed with other sections
# ---------------------------------------------------------------------------


class TestComposedTargets:
    """A target selection marks the same targets fresh alone or composed
    (REQ-d00085-P), and is refused where nothing reads it (REQ-d00085-Q)."""

    # Verifies: REQ-d00085-P
    def test_an_unknown_target_is_refused_alike_alone_and_composed(self, invoke):
        rc_alone, out_alone, err_alone = invoke(["summary", "--targets", "bogus"])
        rc_composed, out_composed, err_composed = invoke(["summary", "trace", "--targets", "bogus"])
        assert rc_alone == rc_composed == 2
        assert err_alone == err_composed
        assert "bogus" in err_alone
        assert out_alone == out_composed == ""

    # Verifies: REQ-d00085-Q
    @pytest.mark.parametrize("sections", [["checks", "unresolved"], ["checks", "gaps"]])
    def test_targets_without_a_section_reading_them_is_refused(self, invoke, sections):
        rc, out, err = invoke([*sections, "--targets", "unit"])
        assert rc == 2
        assert "--targets" in err
        assert out == ""

    # Verifies: REQ-d00085-Q
    @pytest.mark.parametrize(
        ("argv", "flag"),
        [
            (["summary", "trace", "--lenient"], "--lenient"),
            (["checks", "summary", "--preset", "minimal"], "--preset"),
            (["checks", "summary", "--body"], "--body"),
            (["checks", "changed", "--level", "dev"], "--level"),
        ],
        ids=["lenient", "preset", "body", "scope"],
    )
    def test_an_option_no_composed_section_reads_is_refused(self, invoke, argv, flag):
        rc, out, err = invoke(argv)
        assert rc == 2
        assert flag in err
        assert out == ""

    # Verifies: REQ-d00085-Q+P
    @pytest.mark.parametrize(
        "argv",
        [
            ["checks", "summary", "--level", "dev", "-q"],
            ["summary", "trace", "--preset", "minimal", "-q"],
            ["checks", "unresolved", "--lenient", "-q"],
        ],
        ids=["scope-read-by-summary", "preset-read-by-trace", "lenient-read-by-checks"],
    )
    def test_an_option_one_composed_section_reads_is_accepted(self, invoke, argv):
        rc, _out, err = invoke(argv)
        assert rc != 2, err

    # Verifies: REQ-d00085-P+D
    @pytest.mark.parametrize(
        ("targets", "fresh"),
        [("unit", {"unit"}), ("none", set()), ("all", None)],
        ids=["one-target", "reserved-none", "every-target"],
    )
    def test_a_known_selection_marks_the_same_targets_fresh_composed(
        self, invoke, monkeypatch, targets, fresh
    ):
        """`None` is a selection covering every target: a full run, which the
        standalone summary answers without a selective build."""
        import elspais.graph.factory as factory

        real_build = factory.build_graph
        seen: list[object] = []

        def recording_build(*args, **kwargs):
            seen.append(kwargs.get("fresh_targets"))
            return real_build(*args, **kwargs)

        monkeypatch.setattr(factory, "build_graph", recording_build)

        rc_alone, alone, err_alone = invoke(["summary", "--targets", targets])
        alone_fresh = list(seen)
        seen.clear()
        rc_composed, composed, err_composed = invoke(["summary", "trace", "--targets", targets])
        composed_fresh = list(seen)

        assert rc_alone == 0, err_alone
        assert rc_composed == 0, err_composed
        assert composed_fresh == [fresh]
        if fresh is not None:
            assert alone_fresh == [fresh]
        assert composed.startswith(alone.rstrip("\n"))


# ---------------------------------------------------------------------------
# Options no named section reads
# ---------------------------------------------------------------------------


class TestRefusedOptions:
    """An option is accepted only where the invocation reads it (REQ-d00085-Q)."""

    # Verifies: REQ-d00085-Q+B
    @pytest.mark.parametrize(
        "argv",
        [["checks", "summary", "--mode", "core"], ["--mode", "core", "checks", "summary"]],
        ids=["last", "first"],
    )
    def test_mode_is_refused(self, invoke, argv):
        rc, out, err = invoke(argv)
        assert rc == 2
        assert "--mode" in err
        assert out == ""

    # Verifies: REQ-d00283-W, REQ-d00085-Q
    @pytest.mark.parametrize(
        "extra",
        [["--targets", "unit"], ["--fail-fast"], ["--targets", "unit", "--fail-fast"]],
        ids=["targets", "fail-fast", "both"],
    )
    def test_checks_refuses_a_run_selection_without_run_tests(self, invoke, extra):
        rc, out, err = invoke(["checks", *extra])
        assert rc == 2
        assert "--run-tests" in err
        for option in extra:
            if option.startswith("--"):
                assert option in err
        assert out == ""

    # Verifies: REQ-d00085-Q
    def test_checks_refuses_a_removed_group_selector(self, invoke):
        rc, _out, err = invoke(["checks", "--groups", "spec"])
        assert rc == 2
        assert "--groups" in err


# ---------------------------------------------------------------------------
# The argv rewriting that makes placement irrelevant
# ---------------------------------------------------------------------------


class TestArgvRewriting:
    """Units behind REQ-d00085-O: global options lifted, sections put first."""

    # Verifies: REQ-d00085-O
    @pytest.mark.parametrize(
        ("argv", "lifted", "rest"),
        [
            (
                ["--format", "json", "checks", "summary", "-q"],
                ["-q"],
                ["--format", "json", "checks", "summary"],
            ),
            (
                ["-v", "trace", "--verbose", "--no-quiet"],
                ["-v", "--verbose", "--no-quiet"],
                ["trace"],
            ),
            (
                ["checks", "--config", "x.toml", "--spec-dir=spec"],
                ["--config", "x.toml", "--spec-dir=spec"],
                ["checks"],
            ),
            (["checks", "--", "-v", "-q"], [], ["checks", "--", "-v", "-q"]),
        ],
        ids=["switch", "repeated-and-negated", "valued", "after-double-dash"],
    )
    def test_lift_global_options(self, argv, lifted, rest):
        assert _lift_global_options(argv) == (lifted, rest)

    # Verifies: REQ-d00085-O
    @pytest.mark.parametrize(
        ("argv", "expected"),
        [
            (
                ["--format", "json", "checks", "summary", "-q"],
                ["checks", "summary", "--format", "json", "-q"],
            ),
            (["-o", "summary", "checks"], ["checks", "-o", "summary"]),
            (
                ["--targets", "a", "b", "checks", "summary"],
                ["checks", "summary", "--targets", "a", "b"],
            ),
            (["--lenient", "checks"], ["checks", "--lenient"]),
            (["checks", "--format", "json"], ["checks", "--format", "json"]),
            (["--format", "json", "docs"], ["--format", "json", "docs"]),
            (["-o", "summary"], ["-o", "summary"]),
        ],
        ids=[
            "flags-ahead",
            "option-value-is-a-section-name",
            "variadic-value",
            "switch",
            "already-sections-first",
            "not-a-section",
            "no-section-at-all",
        ],
    )
    def test_sections_first(self, argv, expected):
        assert _sections_first(argv) == expected
