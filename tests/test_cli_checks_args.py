# Verifies: REQ-d00249-A, REQ-d00249-C
"""Argument-parsing tests for `elspais checks --run-tests/--fail-fast`."""

from __future__ import annotations

import pytest
import tyro

from elspais.commands._scope import flag_values
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
def test_targets_flag_present_and_defaults_to_naming_nothing():
    args = tyro.cli(ChecksArgs, args=[])
    assert hasattr(args, "targets")
    assert flag_values(args, "targets") == ()


# Verifies: REQ-d00254-H
def test_targets_flag_parses_space_separated_names():
    args = tyro.cli(ChecksArgs, args=["--run-tests", "--targets", "a", "b"])
    assert flag_values(args, "targets") == ("a", "b")


# Verifies: REQ-d00283-E
def test_targets_accumulates_across_repeats_and_mixes_with_the_spaced_form():
    """A reader may repeat the flag, space-separate behind it, or do both.

    A group is named where a target is named, so one invocation carries both
    spellings; keeping only the last occurrence would put that mixture out of
    reach while looking like the whole invocation had been read.
    """
    args = tyro.cli(
        ChecksArgs,
        args=["--run-tests", "--targets", "uat", "unit", "--targets", "slow"],
    )

    # The parser hands each occurrence over as its own inner list ...
    assert args.targets == [["uat", "unit"], ["slow"]]
    # ... and the one gatherer flattens them into the single list the
    # selection is resolved from.
    assert flag_values(args, "targets") == ("uat", "unit", "slow")


# Verifies: REQ-d00283-E
def test_groups_is_no_longer_a_flag():
    """A group is an alias for a set of targets, named where a target is
    named. There is no second selector to state it through."""
    with pytest.raises(SystemExit):
        tyro.cli(ChecksArgs, args=["--run-tests", "--groups", "all"])

    # And the name it was retired in favour of takes the same word.
    assert flag_values(
        tyro.cli(ChecksArgs, args=["--run-tests", "--targets", "all"]), "targets"
    ) == ("all",)


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
    assert flag_values(args, "code") == ("E_IDENTIFIER_WITH_TRAILING_TEXT",)
    assert args.code_only is False

    scoped = tyro.cli(ChecksArgs, args=["--code-checks"])
    assert scoped.code_only is True
    assert flag_values(scoped, "code") == ()


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
    assert flag_values(args, "severity") == ("error", "warning")
    assert flag_values(args, "category") == ("references",)
    assert flag_values(args, "code") == ("E_ONE", "E_TWO")
    assert flag_values(args, "file") == ("spec/*.md",)


# Verifies: REQ-d00285-G
def test_the_filters_default_to_selecting_nothing_away():
    args = tyro.cli(ChecksArgs, args=[])
    for name in ("severity", "category", "code", "file"):
        assert flag_values(args, name) == (), f"--{name} must narrow nothing unstated"
