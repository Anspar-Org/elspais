"""The recorder plugin, end to end: a tiny project run under ``-p tools.tia.recorder``.

Each test builds the project in pytester's directory, commits it to a fresh
git repository (the recorder fingerprints the tree at session start), runs
pytest over it in a subprocess and reads the shard the recorder wrote.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import pytest
from coverage import CoverageData

from tests.tia import _synth
from tools.tia.baseline import build_baseline

pytest_plugins = ["pytester"]

ELSPAIS = str(Path(__file__).resolve().parents[2])

CONFTEST = """
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="session")
def project_data():
    subprocess.run([sys.executable, "-c", "pass"], check=True)
    with open(os.path.join(ROOT, "data", "a.txt")) as fh:
        return fh.read()


@pytest.fixture
def per_test_data():
    with open(os.path.join(ROOT, "data", "b.txt")) as fh:
        return fh.read()
"""

TESTS = """
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_first_user(project_data):
    assert project_data


def test_second_user(project_data):
    assert project_data


def test_function_fixture(per_test_data):
    assert per_test_data


def test_reads_in_body():
    with open(os.path.join(ROOT, "data", "c.txt")) as fh:
        assert fh.read()


def test_spawns():
    subprocess.run([sys.executable, "-c", "pass"], check=True)


def test_lists():
    assert "a.txt" in os.listdir(os.path.join(ROOT, "data"))


def test_fails():
    assert False


def test_skips():
    pytest.skip("later")


def test_uses_tmp_path(tmp_path):
    assert tmp_path.is_dir()
"""

T = "tests/test_proj.py::"
FIRST, SECOND = T + "test_first_user", T + "test_second_user"
FUNC_FX, BODY, SPAWNS, LISTS = (
    T + "test_function_fixture",
    T + "test_reads_in_body",
    T + "test_spawns",
    T + "test_lists",
)
FAILS, SKIPS = T + "test_fails", T + "test_skips"
K_DATA = "session:tests::project_data"


@pytest.fixture
def project(pytester, monkeypatch) -> Path:
    """The committed project, with a clean git environment for every process."""
    for k in list(os.environ):
        if k.startswith(("GIT_CONFIG_", "COV_CORE_")) or k in (
            "GIT_DIR",
            "GIT_WORK_TREE",
            "GIT_INDEX_FILE",
        ):
            monkeypatch.delenv(k)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "1")
    # The inner run otherwise loads every pytest plugin installed in the venv,
    # and their fixtures enter the shard; it needs none of them.
    monkeypatch.setenv("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
    monkeypatch.setenv(
        "PYTHONPATH", os.pathsep.join(filter(None, [ELSPAIS, os.environ.get("PYTHONPATH")]))
    )
    root = pytester.path
    files = {
        "pytest.ini": "[pytest]\n",
        ".gitignore": "__pycache__/\nrunpytest-*\ntia-out/\nstdout\nstderr\n",
        "notes.txt": "committed\n",
        "data/a.txt": "a\n",
        "data/b.txt": "b\n",
        "data/c.txt": "c\n",
        "tests/conftest.py": CONFTEST,
        "tests/test_proj.py": TESTS,
    }
    for rel, text in files.items():
        _synth.write(root, rel, text)
    _synth.git(root, "init", "-q", "-b", "main")
    for k, v in (("user.name", "tia"), ("user.email", "tia@example.invalid")):
        _synth.git(root, "config", "--local", k, v)
    _synth.git(root, "add", "-A")
    _synth.git(root, "commit", "-q", "-m", "project")
    monkeypatch.setenv("TIA_RECORD_DIR", str(root / "tia-out"))
    return root


def run_recorded(pytester, project: Path) -> dict:
    result = pytester.runpytest_subprocess(
        "-p", "tools.tia.recorder", "-p", "no:cacheprovider", "tests"
    )
    result.assert_outcomes(passed=7, failed=1, skipped=1)
    with open(project / "tia-out" / "tia-shard-main.json", encoding="utf-8") as fh:
        return json.load(fh)


def buckets_with(shard: dict, kind: str, item: str) -> set[str]:
    return {b for b, a in shard["attribution"].items() if item in a.get(kind, ())}


def test_reads_are_attributed_to_the_fixture_or_phase_that_made_them(pytester, project):
    shard = run_recorded(pytester, project)
    assert shard["errors"] == []
    # the session fixture's read belongs to the fixture, not to its first user
    assert buckets_with(shard, "reads", "data/a.txt") == {f"fixture:{K_DATA}"}
    assert buckets_with(shard, "reads", "data/b.txt") == {f"{FUNC_FX}|setup"}
    assert buckets_with(shard, "reads", "data/c.txt") == {f"{BODY}|run"}
    assert buckets_with(shard, "lists", "data") == {f"{LISTS}|run"}
    spawns = shard["attribution"][f"{SPAWNS}|run"]["spawns"]
    assert spawns and all(p.startswith("python") for p in spawns)
    assert shard["attribution"][f"fixture:{K_DATA}"]["spawns"] == spawns


def test_fixtures_defined_outside_the_repository_are_listed_external(pytester, project):
    shard = run_recorded(pytester, project)
    external = shard["external_fixtures"]
    # tmp_path_factory is pytest's; it was set up by the tmp_path user
    assert "session:::tmp_path_factory" in external
    assert K_DATA not in external
    assert not any(k.endswith("::project_data") for k in external)


def test_baseline_folds_fixture_spawns_into_its_users(pytester, project, tmp_path):
    run_recorded(pytester, project)
    cov = tmp_path / ".coverage"
    data = CoverageData(basename=str(cov))
    data.set_context(f"{FIRST}|run")
    data.add_lines({str(project / "tests" / "test_proj.py"): [1]})
    data.write()
    manifest = build_baseline(str(project / "tia-out"), str(tmp_path / "baseline"), str(cov))
    assert manifest["data_reads"]["data/a.txt"] == [f"fixture:{K_DATA}"]
    spawners = {n for n, t in manifest["tests"].items() if t["spawns"]}
    assert spawners == {FIRST, SECOND, SPAWNS}


def test_outcomes_and_shared_fixture_use(pytester, project):
    tests = run_recorded(pytester, project)["tests"]
    assert {n: t["outcome"] for n, t in tests.items() if n in (FAILS, SKIPS, BODY)} == {
        FAILS: "failed",
        SKIPS: "skipped",
        BODY: "passed",
    }
    assert tests[FIRST]["shared_fixtures"] == [K_DATA]
    assert K_DATA in tests[FIRST]["setup_executed"]
    # the second user depends on the fixture without having executed it
    assert tests[SECOND]["shared_fixtures"] == [K_DATA]
    assert K_DATA not in tests[SECOND]["setup_executed"]
    assert tests[FUNC_FX]["shared_fixtures"] == []


def test_identity_overlays_dirty_files_but_not_nested_repositories(pytester, project):
    _synth.write(project, "notes.txt", "edited before the run\n")
    nested = project / "nested"
    _synth.write(nested, "inner.txt", "inside another repository\n")
    _synth.git(nested, "init", "-q", "-b", "main")
    os.symlink("data", project / "datalink")  # untracked link to a directory
    shard = run_recorded(pytester, project)
    start = shard["identity_start"]
    assert start["error"] is None
    assert re.fullmatch(r"[0-9a-f]{40}", start["tree"])
    assert start == shard["identity_end"]
    blob = _synth.git(project, "hash-object", "--", "notes.txt").strip()
    # git stores a symbolic link as a blob of its target string
    link_blob = (
        subprocess.run(
            ["git", "hash-object", "--stdin"],
            cwd=project,
            env=_synth.git_env(),
            input=b"data",
            capture_output=True,
            check=True,
        )
        .stdout.decode()
        .strip()
    )
    assert start["dirty"] == {"notes.txt": blob, "datalink": link_blob}


def test_root_conftest_shared_fixture_read_is_attributed_to_the_fixture(pytester, project):
    (project / "tests" / "conftest.py").rename(project / "conftest.py")
    _synth.replace(
        project,
        "conftest.py",
        "os.path.dirname(os.path.dirname(os.path.abspath(__file__)))",
        "os.path.dirname(os.path.abspath(__file__))",
    )
    _synth.git(project, "add", "-A")
    _synth.git(project, "commit", "-q", "-m", "root conftest")
    shard = run_recorded(pytester, project)
    (key,) = shard["tests"][FIRST]["shared_fixtures"]
    # the key's baseid is the root directory's node id ("." under pytest 9)
    assert key.startswith("session:") and key.endswith("::project_data")
    assert key not in shard["external_fixtures"]
    assert buckets_with(shard, "reads", "data/a.txt") == {f"fixture:{key}"}
