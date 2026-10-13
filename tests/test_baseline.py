"""Tests for packing the recorded runs of test targets and adopting a fetched pack.

Each test creates a small git repository on disk, records runs of its targets,
and packs them. A second clone of the repository then fetches the pack with a
command that copies it into the directory elspais names.
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import tarfile
from pathlib import Path

import pytest

from elspais.config import validate_config
from elspais.utilities.baseline import (
    PACK_MANIFEST,
    BaselineRefused,
    BaselineUnreadable,
    adopt,
    fetch,
    pack,
    unpack,
)
from elspais.utilities.fingerprint import (
    FINGERPRINT_NAME,
    finish_run,
    forget_probes,
    judge,
    read_fingerprint,
    stale_reason,
    start_run,
    target_folder,
)

_FAILING_JUNIT = (
    '<?xml version="1.0"?><testsuite name="s" tests="1" failures="1">'
    '<testcase classname="t" name="x"><failure message="no"/></testcase></testsuite>\n'
)

_GIT_ENV = {
    **{k: v for k, v in os.environ.items() if not k.startswith("GIT_")},
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.com",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.com",
}


def _git(root: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True, env=_GIT_ENV
    )
    return done.stdout.strip()


def _toml(probe: str = "cat toolchain.txt") -> str:
    return (
        'version = 5\n\n[project]\nname = "base"\nnamespace = "REQ"\n\n'
        "[scanning.test]\nenabled = true\n\n"
        "[scanning.test.baseline]\n"
        'fetch_command = "cp ../baseline.tar.gz {dest}"\n\n'
        '[[scanning.test.targets]]\nname = "unit"\nreporter = "junit"\n'
        'results = "junit.xml"\ninputs = { directories = ["src"] }\n'
        f'environment_probes = [{{ name = "toolchain", command = "{probe}" }}]\n\n'
        '[[scanning.test.targets]]\nname = "other"\nreporter = "junit"\n'
        'results = "junit.xml"\ninputs = { directories = ["src"] }\n'
    )


def _config(root: Path):
    import tomlkit

    document = tomlkit.parse((root / ".elspais.toml").read_text(encoding="utf-8"))
    return validate_config(document.unwrap())


def _repo(tmp_path: Path, name: str = "origin") -> Path:
    root = tmp_path / name
    (root / "src").mkdir(parents=True)
    (root / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
    (root / ".gitignore").write_text(".results/\ntoolchain.txt\n", encoding="utf-8")
    (root / "toolchain.txt").write_text("1.0\n", encoding="utf-8")
    (root / ".elspais.toml").write_text(_toml(), encoding="utf-8")
    _git(root, "init", "-q", "-b", "main")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "first")
    return root


def _clone(tmp_path: Path, origin: Path, name: str = "clone") -> Path:
    clone = tmp_path / name
    _git(tmp_path, "clone", "-q", str(origin), str(clone))
    (clone / "toolchain.txt").write_text("1.0\n", encoding="utf-8")
    return clone


def _record(root: Path, config, name: str = "unit", results: str = _FAILING_JUNIT) -> Path:
    folder = start_run(root, config, name)
    (folder / "junit.xml").write_text(results, encoding="utf-8")
    finish_run(root, config, name, exit_status=1)
    return folder


def _packed(tmp_path: Path) -> tuple[Path, Path]:
    """Record and pack both targets of a fresh repository. Return it and the archive."""
    origin = _repo(tmp_path)
    config = _config(origin)
    _record(origin, config, "unit")
    _record(origin, config, "other")
    archive = tmp_path / "baseline.tar.gz"
    pack(origin, config, ["other", "unit"], archive)
    return origin, archive


@pytest.fixture(autouse=True)
def _fresh_probes():
    forget_probes()
    yield
    forget_probes()


# Packing


# Verifies: REQ-d00333-F
def test_a_failing_run_of_a_committed_tree_is_packed_with_its_manifest(tmp_path):
    origin, archive = _packed(tmp_path)

    with tarfile.open(archive) as packed:
        names = set(packed.getnames())
        manifest = json.load(packed.extractfile(PACK_MANIFEST))

    assert {
        PACK_MANIFEST,
        f"targets/unit/{FINGERPRINT_NAME}",
        "targets/unit/junit.xml",
        f"targets/other/{FINGERPRINT_NAME}",
    } <= names
    assert manifest["commit"] == _git(origin, "rev-parse", "HEAD")
    assert manifest["targets"] == ["other", "unit"]
    assert manifest["fingerprint_version"] == 3
    assert manifest["format"] == 1
    assert manifest["elspais"]


# Verifies: REQ-d00333-F
def test_a_tree_holding_uncommitted_changes_is_refused_naming_them(tmp_path):
    origin = _repo(tmp_path)
    config = _config(origin)
    _record(origin, config)
    (origin / "src" / "b.py").write_text("y = 1\n", encoding="utf-8")

    with pytest.raises(BaselineRefused) as exc:
        pack(origin, config, ["unit"], tmp_path / "b.tar.gz")

    assert any("src/b.py" in r and "no commit holds" in r for r in exc.value.reasons)
    assert not (tmp_path / "b.tar.gz").exists()


# Verifies: REQ-d00333-F
def test_a_run_of_a_tree_that_differed_from_every_commit_is_refused(tmp_path):
    origin = _repo(tmp_path)
    config = _config(origin)
    (origin / "src" / "b.py").write_text("y = 1\n", encoding="utf-8")
    _record(origin, config)
    _git(origin, "add", "-A")
    _git(origin, "commit", "-q", "-m", "second")

    with pytest.raises(BaselineRefused) as exc:
        pack(origin, config, ["unit"], tmp_path / "b.tar.gz")

    assert exc.value.reasons == [
        "target unit: its run executed in a tree that differs from every commit; "
        "commit the tree and run it again"
    ]


# Verifies: REQ-d00333-F
def test_a_run_at_another_commit_is_refused_naming_both(tmp_path):
    origin = _repo(tmp_path)
    config = _config(origin)
    _record(origin, config)
    first = _git(origin, "rev-parse", "HEAD")
    (origin / "src" / "a.py").write_text("x = 2\n", encoding="utf-8")
    _git(origin, "commit", "-q", "-am", "second")

    with pytest.raises(BaselineRefused) as exc:
        pack(origin, config, ["unit"], tmp_path / "b.tar.gz")

    (reason,) = exc.value.reasons
    assert reason.startswith("target unit: its run executed at commit " + first[:12])


# Verifies: REQ-d00333-E, REQ-d00311-N
def test_a_run_in_progress_or_without_an_end_is_refused(tmp_path):
    origin = _repo(tmp_path)
    config = _config(origin)
    folder = start_run(origin, config, "unit")
    (folder / "junit.xml").write_text(_FAILING_JUNIT, encoding="utf-8")

    with pytest.raises(BaselineRefused) as exc:
        pack(origin, config, ["unit"], tmp_path / "b.tar.gz")

    assert exc.value.reasons == [
        "target unit: its run is in progress or recorded no end, so its results may be partial"
    ]


# Verifies: REQ-d00333-F, REQ-d00311-C
def test_a_run_whose_inputs_changed_while_it_ran_is_refused_naming_them(tmp_path):
    origin = _repo(tmp_path)
    config = _config(origin)
    folder = start_run(origin, config, "unit")
    (folder / "junit.xml").write_text(_FAILING_JUNIT, encoding="utf-8")
    (origin / "toolchain.txt").write_text("2.0\n", encoding="utf-8")
    finish_run(origin, config, "unit")

    with pytest.raises(BaselineRefused) as exc:
        pack(origin, config, ["unit"], tmp_path / "b.tar.gz")

    assert exc.value.reasons == [
        "target unit: inputs changed while it ran: environment probe 'toolchain'"
    ]


# Verifies: REQ-d00333-F
@pytest.mark.parametrize("recorded", [False, True], ids=["no-run", "no-results"])
def test_a_target_without_a_run_or_results_is_refused(tmp_path, recorded):
    origin = _repo(tmp_path)
    config = _config(origin)
    if recorded:
        start_run(origin, config, "unit")
        finish_run(origin, config, "unit")

    with pytest.raises(BaselineRefused) as exc:
        pack(origin, config, ["unit"], tmp_path / "b.tar.gz")

    expected = (
        "its output area holds no results"
        if recorded
        else "no Result Fingerprint records a run of it; run it first"
    )
    assert exc.value.reasons == [f"target unit: {expected}"]


# Fetching and adopting


# Verifies: REQ-d00311-H, REQ-d00311-I, REQ-d00311-P
def test_a_fetched_run_is_adopted_and_judged_fresh_in_another_tree(tmp_path):
    origin, _archive = _packed(tmp_path)
    clone = _clone(tmp_path, origin)
    config = _config(clone)

    manifest, outcomes = fetch(clone, config, replace=False)

    assert [(o.target, o.outcome) for o in outcomes] == [("other", "adopted"), ("unit", "adopted")]
    assert manifest["commit"] == _git(clone, "rev-parse", "HEAD")
    folder = target_folder(clone, config, "unit")
    assert (folder / "junit.xml").read_text(encoding="utf-8") == _FAILING_JUNIT
    assert read_fingerprint(folder)["root"] == str(origin.resolve())
    assert judge(clone, config, "unit").state == "fresh"


# Verifies: REQ-d00311-H, REQ-d00311-I, REQ-d00311-R
def test_an_adopted_run_from_another_environment_is_stale_naming_the_probe(tmp_path):
    origin, _archive = _packed(tmp_path)
    clone = _clone(tmp_path, origin)
    (clone / "toolchain.txt").write_text("2.0\n", encoding="utf-8")
    config = _config(clone)

    fetch(clone, config, replace=False)
    verdict = judge(clone, config, "unit")

    assert verdict.state == "stale"
    assert stale_reason(verdict) == "inputs changed since it ran: environment probe 'toolchain'"
    assert judge(clone, config, "other").state == "fresh"


# Verifies: REQ-d00311-H, REQ-d00311-I
def test_a_run_recorded_here_is_kept_unless_replace_is_asked(tmp_path):
    origin, _archive = _packed(tmp_path)
    clone = _clone(tmp_path, origin)
    config = _config(clone)
    local = _record(clone, config, "unit", results="<testsuite/>\n")

    _manifest, outcomes = fetch(clone, config, replace=False)

    assert [(o.target, o.outcome) for o in outcomes] == [("other", "adopted"), ("unit", "skipped")]
    assert (local / "junit.xml").read_text(encoding="utf-8") == "<testsuite/>\n"

    _manifest, outcomes = fetch(clone, config, replace=True)

    assert [(o.target, o.outcome) for o in outcomes] == [("other", "adopted"), ("unit", "adopted")]
    assert (local / "junit.xml").read_text(encoding="utf-8") == _FAILING_JUNIT


# Verifies: REQ-d00311-N
def test_a_run_in_progress_here_is_never_replaced(tmp_path):
    origin, _archive = _packed(tmp_path)
    clone = _clone(tmp_path, origin)
    config = _config(clone)
    folder = start_run(clone, config, "unit")

    _manifest, outcomes = fetch(clone, config, replace=True)

    (unit,) = [o for o in outcomes if o.target == "unit"]
    assert unit.outcome == "refused"
    assert "in progress" in unit.detail
    assert sorted(p.name for p in folder.iterdir()) == [FINGERPRINT_NAME]


# Verifies: REQ-d00311-H
@pytest.mark.parametrize(
    ("command", "says"),
    [
        ("exit 3", "exited 3"),
        ("true", "left nothing"),
        ("touch {dest}/a {dest}/b", "left: a, b"),
    ],
    ids=["fails", "leaves-nothing", "leaves-two"],
)
def test_a_fetch_command_that_yields_no_single_archive_changes_nothing(tmp_path, command, says):
    origin = _repo(tmp_path)
    config = _config(origin)
    raw = config.model_dump(by_alias=True)
    raw["scanning"]["test"]["baseline"]["fetch_command"] = command + " # {dest}"
    config = validate_config(raw)

    with pytest.raises(BaselineRefused, match=says):
        fetch(origin, config, replace=False)

    assert not (origin / ".results").exists()


def _archive(path: Path, members: dict[str, bytes]) -> Path:
    with tarfile.open(path, "w:gz") as out:
        for name, body in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(body)
            out.addfile(info, io.BytesIO(body))
    return path


def _manifest(**changes) -> bytes:
    body = {"format": 1, "fingerprint_version": 3, "elspais": "x", "commit": "c", "targets": []}
    body.update(changes)
    return json.dumps(body).encode()


# Verifies: REQ-d00311-H
@pytest.mark.parametrize(
    ("members", "says"),
    [
        ({PACK_MANIFEST: _manifest(), "../escape.txt": b"x"}, "not a file or directory inside"),
        ({PACK_MANIFEST: _manifest(), "/abs.txt": b"x"}, "not a file or directory inside"),
        ({PACK_MANIFEST: _manifest(fingerprint_version=2)}, "Result Fingerprints of format 2"),
        ({PACK_MANIFEST: _manifest(format=9)}, "packed baseline of format 9"),
        ({"other.txt": b"x"}, f"no readable {PACK_MANIFEST}"),
    ],
    ids=["climbs-out", "absolute", "old-fingerprints", "other-format", "no-manifest"],
)
def test_an_archive_that_is_not_a_baseline_this_elspais_reads_is_refused_whole(
    tmp_path, members, says
):
    archive = _archive(tmp_path / "bad.tar.gz", members)
    staging = tmp_path / "staging"
    staging.mkdir()

    with pytest.raises(BaselineUnreadable, match=says):
        unpack(archive, staging)

    assert not (tmp_path / "escape.txt").exists()


# Verifies: REQ-d00311-H
def test_a_packed_target_this_repository_does_not_declare_is_refused(tmp_path):
    origin, archive = _packed(tmp_path)
    staging = tmp_path / "staging"
    staging.mkdir()
    manifest = unpack(archive, staging)
    manifest["targets"] = [*manifest["targets"], "gone"]

    outcomes = adopt(origin, _config(origin), staging, manifest, replace=True)

    assert [(o.target, o.outcome) for o in outcomes] == [
        ("gone", "refused"),
        ("other", "adopted"),
        ("unit", "adopted"),
    ]


# Verifies: REQ-d00333-E, REQ-d00333-F
@pytest.mark.parametrize(
    ("change", "says"),
    [
        ({"finished_at": ""}, "recorded no end"),
        ({"changed_during_run": ["src/a.py"]}, "inputs changed while it ran: src/a.py"),
        ({"dirty": True}, "differs from every commit"),
    ],
    ids=["no-end", "changed-during-run", "dirty-tree"],
)
def test_a_packed_run_that_cannot_serve_as_a_baseline_is_refused_on_adoption(
    tmp_path, change, says
):
    """An archive assembled by other means holds to the rule a pack holds to."""
    origin, archive = _packed(tmp_path)
    staging = tmp_path / "staging"
    staging.mkdir()
    manifest = unpack(archive, staging)
    recorded = staging / "targets" / "unit" / FINGERPRINT_NAME
    body = json.loads(recorded.read_text(encoding="utf-8"))
    body.update(change)
    recorded.write_text(json.dumps(body), encoding="utf-8")
    clone = _clone(tmp_path, origin)

    outcomes = adopt(clone, _config(clone), staging, manifest, replace=False)

    (unit,) = [o for o in outcomes if o.target == "unit"]
    assert unit.outcome == "refused"
    assert says in unit.detail
    assert not (target_folder(clone, _config(clone), "unit") / FINGERPRINT_NAME).exists()


# The command


# Verifies: REQ-d00333-F, REQ-d00311-H
def test_the_command_packs_fetches_and_reports_each_target(tmp_path, monkeypatch, capsys):
    from elspais.cli import main

    origin = _repo(tmp_path)
    config = _config(origin)
    _record(origin, config, "unit")
    _record(origin, config, "other")
    monkeypatch.chdir(origin)
    archive = tmp_path / "baseline.tar.gz"

    assert main(["baseline", "pack", "--out", str(archive), "--targets", "unit", "other"]) == 0
    assert "packed other, unit" in capsys.readouterr().out

    clone = _clone(tmp_path, origin)
    monkeypatch.chdir(clone)
    assert main(["baseline", "fetch"]) == 0
    out = capsys.readouterr().out
    assert "  other: adopted" in out and "  unit: adopted" in out

    assert main(["baseline", "fetch"]) == 0
    assert "unit: skipped: a Result Fingerprint is already recorded here" in (
        capsys.readouterr().out
    )


# Verifies: REQ-d00333-F
def test_the_command_refuses_a_pack_naming_each_target_and_exits_1(tmp_path, monkeypatch, capsys):
    from elspais.cli import main

    origin = _repo(tmp_path)
    monkeypatch.chdir(origin)

    assert main(["baseline", "pack", "--out", str(tmp_path / "b.tar.gz"), "--targets", "all"]) == 1
    err = capsys.readouterr().err
    assert "target unit: no Result Fingerprint records a run of it" in err
    assert "target other: no Result Fingerprint records a run of it" in err


# Verifies: REQ-d00311-H
def test_the_command_reports_a_failed_fetch_and_exits_1(tmp_path, monkeypatch, capsys):
    from elspais.cli import main

    origin = _repo(tmp_path)
    monkeypatch.chdir(origin)

    assert main(["baseline", "fetch"]) == 1
    err = capsys.readouterr().err
    assert "the fetch command exited" in err
    assert "no output area was changed" in err
