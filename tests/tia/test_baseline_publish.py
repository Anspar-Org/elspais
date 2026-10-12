"""Where the baseline lives, and how a run publishes one there.

Each worktree has its own baseline, recorded by its own passing full run.
Publishing is atomic for a concurrent reader, and a run that did not pass
publishes nothing.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from tests.tia import _synth as s
from tools.tia import __main__ as cli
from tools.tia.baseline import BASELINE_ENV, BaselineError, baseline_dir, build_baseline

REPO = Path(__file__).resolve().parents[2]


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    ).stdout.strip()


@pytest.fixture
def clone(tmp_path, monkeypatch) -> tuple[Path, Path]:
    """A main checkout and a linked worktree of it."""
    for var in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", BASELINE_ENV, "TIA_BASELINE"):
        monkeypatch.delenv(var, raising=False)
    main = tmp_path / "main"
    main.mkdir()
    _git(main, "init", "-q", "--initial-branch=main")
    (main / "f.txt").write_text("x\n")
    _git(main, "add", "f.txt")
    _git(main, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "init")
    linked = tmp_path / "linked"
    _git(main, "worktree", "add", "-q", "-b", "other", str(linked))
    return main, linked


def _coverage_file(baseline: Path) -> Path:
    manifest = json.loads((baseline / "baseline.json").read_text())
    return baseline / manifest["coverage"]["file"]


def _snapshot(directory: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in sorted(directory.iterdir())}


def _staging_dirs(baseline: Path) -> list[str]:
    return [n for n in os.listdir(baseline.parent) if n.startswith(f".{baseline.name}.tmp-")]


# -- location ------------------------------------------------------------------


def _own(worktree: Path) -> str:
    return os.path.join(os.path.realpath(worktree), ".results", "tia", "baseline")


def test_each_worktree_resolves_its_own_baseline(clone):
    main, linked = clone
    assert os.path.realpath(baseline_dir(str(main))) == _own(main)
    assert os.path.realpath(baseline_dir(str(linked))) == _own(linked)
    assert _own(main) != _own(linked)


def test_a_subdirectory_resolves_its_worktree_root_baseline(clone):
    main, linked = clone
    for worktree in (main, linked):
        sub = worktree / "sub"
        sub.mkdir()
        assert os.path.realpath(baseline_dir(str(sub))) == _own(worktree)


def test_the_environment_names_another_baseline(clone, monkeypatch, tmp_path):
    main, _ = clone
    monkeypatch.setenv(BASELINE_ENV, str(tmp_path / "elsewhere"))
    assert baseline_dir(str(main)) == str(tmp_path / "elsewhere")


def test_an_empty_environment_variable_names_nothing(clone, monkeypatch):
    main, _ = clone
    monkeypatch.setenv(BASELINE_ENV, "")
    assert os.path.realpath(baseline_dir(str(main))) == _own(main)


def test_the_command_line_reads_the_same_location(clone, monkeypatch, capsys, tmp_path):
    _, linked = clone
    monkeypatch.chdir(linked)
    assert cli.main(["baseline", "path"]) == 0
    assert os.path.realpath(capsys.readouterr().out.strip()) == _own(linked)
    # an explicit --baseline wins over both the environment and the default
    monkeypatch.setenv(BASELINE_ENV, str(tmp_path / "from-env"))
    assert cli.main(["baseline", "path"]) == 0
    assert capsys.readouterr().out.strip() == str(tmp_path / "from-env")
    assert cli.main(["baseline", "path", "--baseline", str(tmp_path / "flag")]) == 0
    assert capsys.readouterr().out.strip() == str(tmp_path / "flag")


def test_the_unprefixed_variable_is_refused(clone, monkeypatch, capsys, tmp_path):
    _, linked = clone
    monkeypatch.chdir(linked)
    monkeypatch.setenv("TIA_BASELINE", str(tmp_path / "b"))
    assert cli.main(["baseline", "path"]) == 2
    assert BASELINE_ENV in capsys.readouterr().err


# -- publishing ----------------------------------------------------------------


def test_a_new_baseline_replaces_the_previous_one_whole(work, baseline):
    before = _coverage_file(baseline)
    s.make_baseline(work / "repo", work / "scratch")  # a second, independent run
    manifest = build_baseline(str(work / "scratch-run"), str(baseline))
    after = _coverage_file(baseline)
    assert manifest["coverage"]["file"] == after.name
    assert after.is_file()
    # the previous coverage file is kept for a reader still holding the
    # previous baseline.json; it is only removed once it is old
    assert before.is_file() or before == after
    assert _staging_dirs(baseline) == []
    assert s.select_now(work / "repo", baseline).fallbacks == []


def test_a_superseded_coverage_file_is_removed_once_old(work, baseline):
    stale = baseline / "coverage-0000000000000000.db"
    stale.write_bytes(b"left by an earlier baseline")
    os.utime(stale, (0, 0))
    fresh = baseline / "coverage-1111111111111111.db"
    fresh.write_bytes(b"published moments ago by another writer")
    s.make_baseline(work / "repo", work / "scratch")
    build_baseline(str(work / "scratch-run"), str(baseline))
    assert not stale.exists()
    assert fresh.exists()


def test_a_build_that_fails_leaves_the_published_baseline_untouched(work, baseline, monkeypatch):
    before = _snapshot(baseline)
    s.make_baseline(work / "repo", work / "scratch")

    def broken(_db):
        raise RuntimeError("the coverage data could not be read")

    monkeypatch.setattr("tools.tia.baseline._context_count", broken)
    with pytest.raises(RuntimeError):
        build_baseline(str(work / "scratch-run"), str(baseline))
    assert _snapshot(baseline) == before
    assert _staging_dirs(baseline) == []


@pytest.mark.parametrize(
    "overrides",
    [
        {"exitstatus": 1},
        {"errors": ["audit: Traceback ..."]},
        {"identity_end": {"tree": "3" * 40, "dirty": {}}},
    ],
    ids=["tests-failed", "recorder-error", "tree-changed"],
)
def test_a_run_that_did_not_pass_publishes_nothing(work, baseline, overrides):
    before = _snapshot(baseline)
    s.make_baseline(work / "repo", work / "scratch", shard_overrides=overrides)
    with pytest.raises(BaselineError) as exc:
        build_baseline(str(work / "scratch-run"), str(baseline), only_if_passed=True)
    assert exc.value.kind == "baseline-not-published"
    assert _snapshot(baseline) == before
    assert _staging_dirs(baseline) == []


def test_a_passing_run_publishes_when_only_a_pass_may(work, baseline):
    s.make_baseline(work / "repo", work / "scratch")
    manifest = build_baseline(str(work / "scratch-run"), str(baseline), only_if_passed=True)
    assert json.loads((baseline / "baseline.json").read_text()) == manifest


@pytest.mark.parametrize("pytest_rc", [0, 1])
def test_the_unit_tier_publishes_through_the_pass_gate(tmp_path, pytest_rc):
    """A recording run hands the build to `--only-if-passed`, at the default location.

    Stand-in ``pytest`` and ``python`` record their arguments, so no tier runs.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "calls"
    for name, rc in (("pytest", pytest_rc), ("python", 0)):
        stub = bin_dir / name
        stub.write_text(f'#!/bin/sh\necho "{name} $*" >> "{calls}"\nexit {rc}\n')
        stub.chmod(0o755)
    env = {k: v for k, v in os.environ.items() if k != BASELINE_ENV}
    env.update(
        PATH=f"{bin_dir}{os.pathsep}{env.get('PATH', '')}",
        ELSPAIS_TEST_WORKERS="1",
        ELSPAIS_TIA_RECORD="1",
    )
    result = subprocess.run(
        ["bash", str(REPO / ".githooks" / "run-unit-tier"), str(tmp_path / "out")],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == pytest_rc, result.stderr
    build = [c for c in calls.read_text().splitlines() if c.startswith("python ")]
    assert len(build) == 1
    assert "-m tools.tia baseline build --only-if-passed" in build[0]
    assert "--baseline" not in build[0]
