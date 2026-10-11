"""Fixtures for the TIA selector's tests: one synthetic template, copied per test."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.tia import _synth


@pytest.fixture(scope="session")
def tia_template(tmp_path_factory) -> Path:
    work = tmp_path_factory.mktemp("tia-template")
    _synth.make_template(work)
    return work


@pytest.fixture
def work(tia_template, tmp_path) -> Path:
    """A private copy of the template: `<work>/repo` and `<work>/baseline`."""
    return _synth.clone_work(tia_template, tmp_path / "work")


@pytest.fixture
def repo(work) -> Path:
    return work / "repo"


@pytest.fixture
def baseline(work) -> Path:
    return work / "baseline"
