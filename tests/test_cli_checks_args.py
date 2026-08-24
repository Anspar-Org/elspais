# Verifies: REQ-d00249-A, REQ-d00249-C
"""Argument-parsing tests for `elspais checks --run-tests/--fail-fast`."""

from __future__ import annotations

import tyro

from elspais.commands.args import ChecksArgs


def test_run_tests_flag_present_and_defaults_false():
    args = tyro.cli(ChecksArgs, args=[])
    assert hasattr(args, "run_tests")
    assert args.run_tests is False


def test_fail_fast_flag_present_and_defaults_false():
    args = tyro.cli(ChecksArgs, args=[])
    assert hasattr(args, "fail_fast")
    assert args.fail_fast is False


def test_run_tests_flag_parses():
    args = tyro.cli(ChecksArgs, args=["--run-tests"])
    assert args.run_tests is True


def test_fail_fast_flag_parses():
    args = tyro.cli(ChecksArgs, args=["--run-tests", "--fail-fast"])
    assert args.fail_fast is True


# Verifies: REQ-d00254-H
def test_targets_flag_present_and_defaults_none():
    args = tyro.cli(ChecksArgs, args=[])
    assert hasattr(args, "targets")
    assert args.targets is None


# Verifies: REQ-d00254-H
def test_targets_flag_parses_space_separated_names():
    args = tyro.cli(ChecksArgs, args=["--run-tests", "--targets", "a", "b"])
    assert args.targets == ["a", "b"]


# ---------------------------------------------------------------------------
# The findings filters, and the flag rename that made room for one of them
# ---------------------------------------------------------------------------


# Verifies: REQ-d00285-G
def test_code_selects_a_diagnostic_code_and_code_checks_selects_the_scope():
    """`--code` names a code; the scope flag it displaced is `--code-checks`.

    Two things wanted the same name: the scope flag that runs the code checks
    alone, and the filter that selects findings by the diagnostic code they
    reached. A reader typing a code types it after `--code`, so the scope flag
    is the one that moved.
    """
    args = tyro.cli(ChecksArgs, args=["--code", "E_IDENTIFIER_WITH_TRAILING_TEXT"])
    assert args.code == ["E_IDENTIFIER_WITH_TRAILING_TEXT"]
    assert args.code_only is False

    scoped = tyro.cli(ChecksArgs, args=["--code-checks"])
    assert scoped.code_only is True
    assert scoped.code is None


# Verifies: REQ-d00285-G
def test_the_filters_compose_with_the_scope_flags():
    args = tyro.cli(
        ChecksArgs,
        args=[
            "--spec",
            "--severity",
            "error",
            "warning",
            "--category",
            "references",
            "--code",
            "E_ONE",
            "E_TWO",
            "--file",
            "spec/*.md",
        ],
    )

    assert args.spec_only is True
    assert args.severity == ["error", "warning"]
    assert args.category == ["references"]
    assert args.code == ["E_ONE", "E_TWO"]
    assert args.file == ["spec/*.md"]


# Verifies: REQ-d00285-G
def test_the_filters_default_to_selecting_nothing_away():
    args = tyro.cli(ChecksArgs, args=[])
    assert args.severity is None
    assert args.category is None
    assert args.code is None
    assert args.file is None
