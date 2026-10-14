"""Fetching the baseline a full CI run of main published.

Each case builds a real baseline in a synthetic repository whose `origin` is a
bare clone, and answers the GitHub API through a stand-in `gh` that lists
canned artifacts and serves each one's zip.
"""

from __future__ import annotations

import io
import json
import os
import re
import zipfile
from pathlib import Path

import pytest
import yaml

from tests.tia import _synth as s
from tools.tia import fetch
from tools.tia.baseline import BASELINE_ENV, load_baseline
from tools.tia.fetch import ARTIFACT_PREFIX, FetchError, fetch_baseline

ROOT = Path(__file__).resolve().parents[2]
_LIST = re.compile(r"repos/\{owner\}/\{repo\}/actions/artifacts\?per_page=(\d+)&page=(\d+)")
_ZIP = re.compile(r"repos/\{owner\}/\{repo\}/actions/artifacts/(\d+)/zip")


@pytest.fixture(autouse=True)
def _no_inherited_git(monkeypatch):
    for var in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", BASELINE_ENV):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def history(repo, work) -> dict[str, str]:
    """Give `repo` an `origin` holding main, one commit ahead of where the
    baseline was recorded, and a local commit main does not hold.

    Returns the commits: `recorded` (the baseline's), `main` (origin's tip,
    the merge base) and `local` (HEAD, unpushed).
    """
    recorded = s.git(repo, "rev-parse", "HEAD").strip()
    origin = work / "origin.git"
    s.git(repo, "clone", "-q", "--bare", ".", str(origin))
    s.git(repo, "remote", "add", "origin", str(origin))
    s.git(repo, "commit", "-q", "--allow-empty", "-m", "on main")
    s.git(repo, "push", "-q", "origin", "main")
    main = s.git(repo, "rev-parse", "HEAD").strip()
    s.git(repo, "commit", "-q", "--allow-empty", "-m", "local work")
    local = s.git(repo, "rev-parse", "HEAD").strip()
    s.git(repo, "fetch", "-q", "origin")
    return {"recorded": recorded, "main": main, "local": local}


class FakeGh:
    """Answers the two API calls `fetch_baseline` makes, and records them."""

    def __init__(self, artifacts: list[dict], archives: dict[int, bytes]):
        self.artifacts = artifacts
        self.archives = archives
        self.calls: list[list[str]] = []

    def __call__(self, args: list[str], root: str) -> bytes:
        self.calls.append(args)
        assert args[0] == "api" and len(args) == 2, args
        m = _LIST.fullmatch(args[1])
        if m:
            per_page, page = int(m.group(1)), int(m.group(2))
            chunk = self.artifacts[(page - 1) * per_page : page * per_page]
            return json.dumps({"total_count": len(self.artifacts), "artifacts": chunk}).encode()
        m = _ZIP.fullmatch(args[1])
        if m:
            return self.archives[int(m.group(1))]
        raise AssertionError(f"unexpected gh call {args}")

    def downloaded(self) -> list[int]:
        return [int(m.group(1)) for a in self.calls if (m := _ZIP.fullmatch(a[1]))]


def _never_called(args, root):
    raise AssertionError(f"gh was called: {args}")


def artifact(id_: int, sha: str, *, expired: bool = False) -> dict:
    return {"id": id_, "name": f"{ARTIFACT_PREFIX}{sha}", "expired": expired}


def zip_of(directory: Path, extra: dict[str, bytes] | None = None) -> bytes:
    """The baseline directory zipped as upload-artifact zips it: flat."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for p in sorted(directory.iterdir()):
            zf.write(p, p.name)
        for name, data in (extra or {}).items():
            zf.writestr(name, data)
    return buf.getvalue()


def published(repo: Path, where: Path, **kw) -> Path:
    """A baseline of `repo` recorded elsewhere, as CI would publish it."""
    s.make_baseline(repo, where, **kw)
    return where


def snapshot(directory: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in sorted(directory.iterdir())}


def staging_left(dest: Path) -> list[str]:
    return [n for n in os.listdir(dest.parent) if n.startswith(f".{dest.name}.fetch-")]


def run(repo: Path, dest: Path, gh, **kw) -> str:
    kw.setdefault("current_env", s.current_env())
    kw.setdefault("max_age_days", None)
    return fetch_baseline(str(repo), str(dest), gh=gh, **kw)


def test_a_usable_local_baseline_is_kept_without_asking_github(repo, baseline):
    before = snapshot(baseline)
    message = run(repo, baseline, _never_called)
    assert message.startswith("kept")
    assert snapshot(baseline) == before


def test_installs_the_newest_baseline_main_holds_for_an_ancestor(repo, work, history):
    art = published(repo, work / "art")
    archive = zip_of(art)
    gh = FakeGh(
        [
            artifact(1, history["local"]),  # HEAD's own commit is not on main
            artifact(2, history["recorded"]),
            {"id": 3, "name": "tia-manifest", "expired": False},
            artifact(4, history["main"]),
            artifact(5, "f" * 40),  # a commit this repository never held
        ],
        {2: archive, 4: archive},
    )
    dest = work / "fetched" / "baseline"
    message = run(repo, dest, gh)
    assert gh.downloaded() == [4]
    assert history["main"][:12] in message
    assert snapshot(dest) == snapshot(art)
    load_baseline(str(dest), str(repo), current_env=s.current_env())
    assert staging_left(dest) == []


def test_an_expired_artifact_is_passed_over_for_an_older_commit(repo, work, history):
    archive = zip_of(published(repo, work / "art"))
    gh = FakeGh(
        [artifact(4, history["main"], expired=True), artifact(2, history["recorded"])],
        {2: archive},
    )
    message = run(repo, work / "dest", gh)
    assert gh.downloaded() == [2]
    assert history["recorded"][:12] in message


@pytest.mark.parametrize(
    "listing",
    [
        pytest.param([], id="nothing-published"),
        pytest.param(["main-expired", "recorded-expired"], id="only-expired"),
        pytest.param(["local", "unknown"], id="only-commits-outside-main"),
    ],
)
def test_nothing_fetchable_is_an_error_and_installs_nothing(repo, work, history, listing):
    shas = {**history, "unknown": "f" * 40}
    artifacts = [
        artifact(i, shas[name.removesuffix("-expired")], expired=name.endswith("-expired"))
        for i, name in enumerate(listing, 1)
    ]
    gh = FakeGh(artifacts, {})
    dest = work / "dest"
    with pytest.raises(FetchError, match="published no baseline"):
        run(repo, dest, gh)
    assert gh.downloaded() == []
    assert not dest.exists()


def test_an_artifact_on_a_later_page_is_found(repo, work, history, monkeypatch):
    monkeypatch.setattr(fetch, "PAGE_SIZE", 2)
    archive = zip_of(published(repo, work / "art"))
    gh = FakeGh(
        [
            {"id": 1, "name": "traceability-x", "expired": False},
            {"id": 2, "name": "tia-manifest", "expired": False},
            artifact(3, history["recorded"]),
        ],
        {3: archive},
    )
    run(repo, work / "dest", gh)
    assert gh.downloaded() == [3]


def test_a_baseline_for_another_environment_is_refused(repo, work, baseline, history):
    """The local baseline is too old to keep, and the published one was
    recorded in another environment: nothing changes."""
    path = baseline / "baseline.json"
    manifest = json.loads(path.read_text())
    manifest["created"] = 0
    path.write_text(json.dumps(manifest))
    before = snapshot(baseline)
    other = {"python": "3.0", "distributions": ["pytest==1.0"]}
    art = published(repo, work / "art", shard_overrides={"environment": other})
    gh = FakeGh([artifact(4, history["main"])], {4: zip_of(art)})
    with pytest.raises(FetchError, match="environment-changed"):
        run(repo, baseline, gh, max_age_days=30)
    assert gh.downloaded() == [4]
    assert snapshot(baseline) == before
    assert staging_left(baseline) == []


@pytest.mark.parametrize("unsafe", ["../escaped.txt", "nested/../../escaped.txt", "/abs.txt"])
def test_an_archive_naming_a_path_outside_it_is_refused(repo, work, history, unsafe):
    archive = zip_of(published(repo, work / "art"), {unsafe: b"payload"})
    gh = FakeGh([artifact(4, history["main"])], {4: archive})
    dest = work / "fetched" / "baseline"
    with pytest.raises(FetchError, match="unsafe path"):
        run(repo, dest, gh)
    assert not dest.exists()
    assert staging_left(dest) == []
    assert not (work / "fetched" / "escaped.txt").exists()
    assert not (work / "escaped.txt").exists()


def test_force_replaces_a_usable_baseline(repo, work, baseline, history):
    narrower = {k: v for k, v in s.default_tests().items() if k in (s.ADD, s.MUL)}
    art = published(repo, work / "art", tests=narrower)
    gh = FakeGh([artifact(4, history["main"])], {4: zip_of(art)})
    assert set(json.loads((baseline / "baseline.json").read_text())["tests"]) != set(narrower)
    message = run(repo, baseline, gh, force=True)
    assert message.startswith("installed")
    assert set(json.loads((baseline / "baseline.json").read_text())["tests"]) == set(narrower)
    load_baseline(str(baseline), str(repo), current_env=s.current_env())


def test_ci_publishes_under_the_name_fetch_looks_for():
    ci = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text())
    names = [
        step["with"]["name"]
        for step in ci["jobs"]["test"]["steps"]
        if str(step.get("uses", "")).startswith("actions/upload-artifact@")
    ]
    assert f"{ARTIFACT_PREFIX}${{{{ github.sha }}}}" in names
