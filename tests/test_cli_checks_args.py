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
