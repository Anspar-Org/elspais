"""The environment fingerprint, and the installs that make a CI baseline match a venv.

A baseline is accepted only where the fingerprint matches, so these tests
check both halves: what the fingerprint compares, and that the jobs recording
and reading a baseline install what `make setup` installs.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest
import yaml

from tools.tia import recorder
from tools.tia.recorder import INSTALLER_DISTRIBUTIONS, environment_fingerprint

ROOT = Path(__file__).resolve().parents[2]
LOCK = "requirements/dev.lock"


class _Dist:
    def __init__(self, name: str, version: str) -> None:
        self.metadata = {"Name": name}
        self.version = version


def _fingerprint_of(monkeypatch, dists: list[_Dist]) -> dict:
    from importlib import metadata

    monkeypatch.setattr(metadata, "distributions", lambda: iter(dists))
    return recorder.environment_fingerprint()


def test_python_is_compared_as_major_minor():
    assert environment_fingerprint()["python"] == f"{sys.version_info[0]}.{sys.version_info[1]}"


def test_installers_and_this_project_are_left_out(monkeypatch):
    env = _fingerprint_of(
        monkeypatch,
        [
            _Dist("pip", "26.2.1"),
            _Dist("setuptools", "79.0.1"),
            _Dist("Wheel", "0.46.3"),
            _Dist("elspais", "0.1.0"),
            _Dist("Packaging", "26.3"),
            _Dist("pytest", "9.0.0"),
        ],
    )
    assert env["distributions"] == ["packaging==26.3", "pytest==9.0.0"]


def test_another_version_of_a_compared_distribution_changes_the_fingerprint(monkeypatch):
    one = _fingerprint_of(monkeypatch, [_Dist("pytest", "9.0.0"), _Dist("pip", "23.0.1")])
    other = _fingerprint_of(monkeypatch, [_Dist("pytest", "9.0.1"), _Dist("pip", "26.2.1")])
    assert one["distributions"] != other["distributions"]


def _lock_names() -> set[str]:
    names = set()
    for line in (ROOT / LOCK).read_text().splitlines():
        m = re.match(r"([A-Za-z0-9][A-Za-z0-9._-]*)==", line)
        if m:
            names.add(m.group(1).lower())
    return names


def test_the_lock_pins_no_installer():
    """An installer the lock pinned would match everywhere, and belong in the comparison."""
    names = _lock_names()
    assert names, f"{LOCK} pins nothing"
    assert names.isdisjoint(INSTALLER_DISTRIBUTIONS)


def _setup_install() -> tuple[str, list[str]]:
    make = (ROOT / "Makefile").read_text()
    lock = re.search(r"^LOCK := (\S+)$", make, re.M).group(1)
    extras = re.search(r"^TEST_EXTRAS := (.+)$", make, re.M).group(1).split()
    assert re.search(r'^\t\$\(PY\) -m pip install -c \$\(LOCK\) -e "\.\[', make, re.M)
    return lock, extras


def _job_install(workflow: str, job: str) -> str:
    config = yaml.safe_load((ROOT / ".github" / "workflows" / workflow).read_text())
    runs = [s.get("run", "") for s in config["jobs"][job]["steps"]]
    installs = [r for r in runs if "pip install" in r and "-e " in r]
    assert len(installs) == 1, f"{workflow} {job}: expected one project install, found {installs}"
    return installs[0]


@pytest.mark.parametrize(
    "workflow,job",
    [
        ("ci.yml", "test"),
        ("ci.yml", "test-impact"),
        ("tia-calibration.yml", "calibrate"),
    ],
)
def test_baseline_jobs_install_what_make_setup_installs(workflow, job):
    lock, extras = _setup_install()
    assert lock == LOCK
    command = _job_install(workflow, job)
    assert f"-c {LOCK}" in command
    m = re.search(r'-e "\.\[([^\]]*)\]"', command)
    assert m, command
    assert sorted(m.group(1).split(",")) == sorted(extras)
