"""A baseline the selector cannot trust runs the full suite, naming why.

Each case damages a copy of the synthetic baseline (or records a variant)
and makes a real change, so a selection that ignored the damage would come
out narrow rather than full.
"""

from __future__ import annotations

import json
import shutil

import pytest

from tests.tia import _synth as s

DAY = 86400.0


def change(repo):
    s.replace(repo, s.CORE, "product = a * b", "product = b * a")


def assert_full(sel, kind: str) -> None:
    assert sel.mode == "full"
    assert s.kinds(sel) == [kind]
    assert sel.manifest()["pytest_targets"] == ["<full suite>"]


def coverage_file(baseline):
    return baseline / json.loads((baseline / "baseline.json").read_text())["coverage"]["file"]


def edit_json(baseline, edit) -> None:
    path = baseline / "baseline.json"
    data = json.loads(path.read_text())
    edit(data)
    path.write_text(json.dumps(data))


def test_intact_baseline_is_used(repo, baseline):
    # the control for every case below: the same change selects narrowly
    change(repo)
    sel = s.select_now(repo, baseline)
    assert sel.mode == "test-impact"
    assert s.selected(sel) == {s.MUL, s.DOUBLE}


# -- the baseline directory and baseline.json ----------------------------------


def test_missing_baseline_directory(repo, work):
    change(repo)
    assert_full(s.select_now(repo, work / "nowhere"), "baseline-missing")


def test_missing_coverage_data(repo, baseline):
    change(repo)
    coverage_file(baseline).unlink()
    assert_full(s.select_now(repo, baseline), "coverage-missing")


@pytest.mark.parametrize(
    "damage, kind",
    [
        (lambda p: p.write_text("{ not json"), "baseline-malformed"),
        (lambda p: p.write_text("[]"), "baseline-stale"),
    ],
    ids=["invalid-json", "not-an-object"],
)
def test_unreadable_baseline_json(repo, baseline, damage, kind):
    change(repo)
    damage(baseline / "baseline.json")
    assert_full(s.select_now(repo, baseline), kind)


@pytest.mark.parametrize(
    "edit, kind",
    [
        (lambda d: d.pop("tests"), "baseline-malformed"),
        (lambda d: d.pop("identity"), "baseline-malformed"),
        (lambda d: d.update(tests={}), "baseline-malformed"),
        (lambda d: d.update(schema=99), "baseline-stale"),
        (lambda d: d.pop("schema"), "baseline-stale"),
    ],
    ids=["no-tests", "no-identity", "empty-inventory", "wrong-schema", "no-schema"],
)
def test_baseline_json_contents_refused(repo, baseline, edit, kind):
    change(repo)
    edit_json(baseline, edit)
    assert_full(s.select_now(repo, baseline), kind)


def test_baseline_older_than_the_limit_is_stale(repo, baseline):
    change(repo)
    created = json.loads((baseline / "baseline.json").read_text())["created"]
    young = s.select_now(repo, baseline, now=created + 29 * DAY)
    assert young.mode == "test-impact"
    old = s.select_now(repo, baseline, now=created + 31 * DAY)
    assert_full(old, "baseline-stale")
    assert "31.0 days old" in old.fallbacks[0].detail


def test_baseline_tree_not_in_repository(repo, baseline):
    change(repo)
    edit_json(baseline, lambda d: d["identity"].update(tree="1" * 40))
    assert_full(s.select_now(repo, baseline), "baseline-revision-unavailable")


def test_dirty_blob_not_in_repository(repo, baseline):
    change(repo)
    edit_json(baseline, lambda d: d["identity"]["dirty"].update({"README.md": "2" * 40}))
    assert_full(s.select_now(repo, baseline), "baseline-revision-unavailable")


# -- what the recording run reported -------------------------------------------


def _variant(work, **kw):
    dest = work / "variant"
    s.make_baseline(work / "repo", dest, **kw)
    return dest


def test_tree_changed_while_recording(work):
    ident = s.git_identity_of(work / "repo")
    ident["tree"] = "3" * 40
    variant = _variant(work, shard_overrides={"identity_end": ident})
    change(work / "repo")
    assert_full(s.select_now(work / "repo", variant), "baseline-identity")


def test_no_git_identity_recorded(work):
    variant = _variant(
        work,
        shard_overrides={"identity_start": {"error": "boom"}, "identity_end": {"error": "boom"}},
    )
    change(work / "repo")
    assert_full(s.select_now(work / "repo", variant), "baseline-identity")


@pytest.mark.parametrize(
    "overrides",
    [{"errors": ["audit: Traceback ..."]}, {"exitstatus": 2}],
    ids=["recorder-error", "interrupted-run"],
)
def test_incomplete_recording(work, overrides):
    variant = _variant(work, shard_overrides=overrides)
    change(work / "repo")
    assert_full(s.select_now(work / "repo", variant), "baseline-incomplete")


def test_test_that_never_ran(work):
    tests = s.default_tests()
    tests[s.OTHER_A]["outcome"] = None
    variant = _variant(work, tests=tests)
    change(work / "repo")
    sel = s.select_now(work / "repo", variant)
    assert_full(sel, "baseline-incomplete")
    assert "never ran" in sel.fallbacks[0].detail


# -- coverage ------------------------------------------------------------------


def test_coverage_bytes_changed(repo, baseline):
    change(repo)
    with open(coverage_file(baseline), "ab") as fh:
        fh.write(b"\0")
    assert_full(s.select_now(repo, baseline), "coverage-corrupt")


def test_coverage_replaced_by_non_coverage_file(repo, baseline):
    # checksum updated to match, so only the content check can refuse it
    change(repo)
    coverage_file(baseline).write_bytes(b"not sqlite at all")
    from tools.tia.baseline import sha256_file

    digest = sha256_file(str(coverage_file(baseline)))
    edit_json(baseline, lambda d: d["coverage"].update(sha256=digest))
    assert_full(s.select_now(repo, baseline), "coverage-corrupt")


def test_coverage_contexts_name_no_recorded_test(work):
    rename = {n: f"tests/test_gone.py::t{i}" for i, n in enumerate(s.default_tests())}
    variant = _variant(work, context_rename=rename)
    change(work / "repo")
    sel = s.select_now(work / "repo", variant)
    assert_full(sel, "coverage-corrupt")
    assert "no coverage context names a recorded test" in sel.fallbacks[0].detail


# -- environment and forcing ---------------------------------------------------


def _other_env():
    env = s.current_env()
    env["distributions"] = [*env["distributions"], "zz-extra-dist==1.0"]
    return env


def test_environment_change_runs_full_suite(repo, baseline):
    change(repo)
    sel = s.select_now(repo, baseline, current_env=_other_env())
    assert_full(sel, "environment-changed")
    assert "zz-extra-dist" in sel.fallbacks[0].detail


def test_environment_change_only_warns_when_configured(repo, baseline):
    change(repo)
    cfg = s.synth_config(on_environment_change="warn")
    sel = s.select_now(repo, baseline, cfg, current_env=_other_env())
    assert sel.mode == "test-impact"
    assert s.selected(sel) == {s.MUL, s.DOUBLE}
    assert any("environment differs" in w for w in sel.warnings)


def test_forced_full(repo, baseline):
    change(repo)
    sel = s.select_now(repo, baseline, force_full="--full given")
    assert_full(sel, "forced-full")
    assert sel.fallbacks[0].detail == "--full given"


def test_baseline_copied_elsewhere_still_works(repo, baseline, tmp_path):
    # a baseline restored from a cache to another directory is still usable
    moved = tmp_path / "restored"
    shutil.copytree(baseline, moved)
    change(repo)
    assert s.selected(s.select_now(repo, moved)) == {s.MUL, s.DOUBLE}
