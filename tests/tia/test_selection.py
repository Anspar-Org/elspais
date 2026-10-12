"""What the selector picks for each kind of change, against a synthetic repo.

Every test edits a private copy of the synthetic repository (see
`_synth.py`) and asks the selector what to run against the synthetic
baseline recorded for the unedited tree.
"""

from __future__ import annotations

import pytest

from tests.tia import _synth as s
from tests.tia._synth import (
    ADD,
    CAPPED,
    CORE,
    DOUBLE,
    FIRST,
    GET,
    K_EMPTY_BASEID,
    K_EXTERNAL,
    K_PROJECT,
    K_SCALED,
    MUL,
    OTHER_A,
    OTHER_B,
    SAMPLE,
    SECOND,
    USER_A,
    USER_B,
)

#: Tests covering any line of core.py (FIRST covers it in setup; SECOND
#: shares that session fixture).
CORE_FILE = {ADD, MUL, GET, DOUBLE, FIRST, SECOND}
#: Plus the tests covering util.py, which imports core.
CORE_MODULE = CORE_FILE | {CAPPED}


def assert_impact(sel, expected: set[str]) -> None:
    assert s.kinds(sel) == []
    assert sel.mode == "test-impact"
    assert s.selected(sel) == expected


def mul_change(repo):
    s.replace(repo, CORE, "product = a * b", "product = b * a")


# -- production Python: function scope ---------------------------------------


def test_line_edit_in_function_selects_only_its_tests(repo, baseline):
    mul_change(repo)
    sel = s.select_now(repo, baseline)
    assert_impact(sel, {MUL, DOUBLE})
    rep = s.report_for(sel, CORE)
    assert rep.category == "production-python"
    assert rep.tests_selected == 2


def test_insertion_shifting_lines_selects_as_the_edit_alone(work, tia_template, tmp_path):
    alone_work = s.clone_work(tia_template, tmp_path / "alone")
    mul_change(alone_work / "repo")
    alone = s.select_now(alone_work / "repo", alone_work / "baseline")

    repo, baseline = work / "repo", work / "baseline"
    base_src = s.read(repo, CORE)
    lo, hi = s.def_span(base_src, "mul")
    s.write(repo, CORE, "".join(f"# filler {i}\n" for i in range(10)) + base_src)
    mul_change(repo)
    assert s.def_span(s.read(repo, CORE), "mul") == (lo + 10, hi + 10)
    shifted = s.select_now(repo, baseline)

    assert_impact(shifted, s.selected(alone))
    assert s.selected(shifted) == {MUL, DOUBLE}
    # the region is named in BASELINE coordinates, where the coverage lives
    assert s.report_for(shifted, CORE).regions == [f"{CORE}:{lo}-{hi} mul changed"]


def test_comment_block_at_top_selects_nothing(repo, baseline):
    s.write(repo, CORE, "# a\n# comment\n# block\n\n" + s.read(repo, CORE))
    sel = s.select_now(repo, baseline)
    assert_impact(sel, set())
    assert s.report_for(sel, CORE).regions == []


def test_deleted_lines_inside_function_select_its_tests(repo, baseline):
    s.replace(repo, CORE, "    total = int(total)\n", "")
    assert_impact(s.select_now(repo, baseline), {ADD})


def test_signature_change_selects_its_tests(repo, baseline):
    s.replace(repo, CORE, "def mul(a, b):", "def mul(a, b, unit=1):")
    sel = s.select_now(repo, baseline)
    assert_impact(sel, {MUL, DOUBLE})
    assert ADD not in s.selected(sel)


def test_shared_fixture_setup_coverage_selects_every_fixture_user(repo, baseline):
    # only FIRST's *setup* executed scale(); SECOND shares the session fixture
    s.replace(
        repo, CORE, "out = [v * factor for v in values]", "out = [factor * v for v in values]"
    )
    sel = s.select_now(repo, baseline)
    assert_impact(sel, {FIRST, SECOND})
    assert any("uses shared fixture 'scaled'" in r for r in sel.tests[SECOND])


def test_shared_fixture_teardown_coverage_selects_every_fixture_user(work):
    tests = s.default_tests()
    first = tests[FIRST]
    first["cover"] = {"teardown": first["cover"].pop("setup")}
    first["teardown_finalized"], first["setup_executed"] = first["setup_executed"], []
    dest = work / "variant"
    s.make_baseline(work / "repo", dest, tests)
    s.replace(
        work / "repo",
        CORE,
        "out = [v * factor for v in values]",
        "out = [factor * v for v in values]",
    )
    assert_impact(s.select_now(work / "repo", dest), {FIRST, SECOND})


def test_run_phase_hit_is_not_widened_to_fixture_users(work):
    # FIRST executes the fixture in setup, but here the hit is in its run phase
    tests = s.default_tests()
    tests[FIRST]["cover"] = {"run": tests[FIRST]["cover"].pop("setup")}
    dest = work / "variant"
    s.make_baseline(work / "repo", dest, tests)
    s.replace(
        work / "repo",
        CORE,
        "out = [v * factor for v in values]",
        "out = [factor * v for v in values]",
    )
    assert_impact(s.select_now(work / "repo", dest), {FIRST})


# -- production Python: widened scopes ---------------------------------------


def test_uncovered_function_change_widens_to_the_file(repo, baseline):
    s.replace(repo, CORE, "doubled = x * 2", "doubled = x + x")
    sel = s.select_now(repo, baseline)
    assert_impact(sel, CORE_FILE)
    assert any("widened to the file" in n for n in s.report_for(sel, CORE).notes)


def test_whole_function_deleted_is_module_scope(repo, baseline):
    s.replace(repo, CORE, "def unused(x):\n    doubled = x * 2\n    return doubled\n\n\n", "")
    sel = s.select_now(repo, baseline)
    assert_impact(sel, CORE_MODULE)
    assert any("removed or renamed" in r for r in s.report_for(sel, CORE).regions)


def test_module_constant_change_reaches_importers(repo, baseline):
    s.replace(repo, CORE, "LIMIT = 10", "LIMIT = 20")
    sel = s.select_now(repo, baseline)
    assert_impact(sel, CORE_MODULE)
    assert CAPPED in s.selected(sel)  # covers only util.py, which imports core
    assert not s.selected(sel) & {OTHER_A, OTHER_B, SAMPLE, USER_A, USER_B}


def test_new_top_level_function_is_file_scope(repo, baseline):
    s.write(repo, CORE, s.read(repo, CORE) + "\n\ndef brand_new_helper():\n    return 1\n")
    sel = s.select_now(repo, baseline)
    assert_impact(sel, CORE_FILE)
    assert CAPPED not in s.selected(sel)


def test_new_unimported_module_selects_directory_listers_only(repo, baseline):
    # src/pkg was listed by OTHER_B in the baseline: directory discovery
    s.write(repo, "src/pkg/extra.py", "def fresh():\n    return 1\n")
    sel = s.select_now(repo, baseline)
    assert_impact(sel, {OTHER_B})
    rep = s.report_for(sel, "src/pkg/extra.py")
    assert rep.status == "added"
    assert rep.category == "production-python"


def test_new_unimported_module_nobody_lists_selects_nothing(work):
    tests = s.default_tests()
    tests[OTHER_B]["lists"] = {}
    dest = work / "variant"
    s.make_baseline(work / "repo", dest, tests)
    s.write(work / "repo", "src/pkg/extra.py", "def fresh():\n    return 1\n")
    # no test can reach the module yet, and that is not a reason to run everything
    assert_impact(s.select_now(work / "repo", dest), set())


def test_new_subpackage_selects_listers_of_its_parent(repo, baseline):
    s.write(repo, "src/pkg/sub/__init__.py", "")
    s.write(repo, "src/pkg/sub/extra.py", "def fresh():\n    return 1\n")
    assert_impact(s.select_now(repo, baseline), {OTHER_B})


def test_new_module_imported_by_unchanged_module_is_module_scope(repo, baseline):
    # util.load_plugin() imports pkg.plugin lazily; util itself is unchanged
    s.write(repo, "src/pkg/plugin.py", 'NAME = "plugin"\n')
    sel = s.select_now(repo, baseline)
    assert_impact(sel, {DOUBLE, CAPPED, OTHER_B})
    notes = s.report_for(sel, "src/pkg/plugin.py").notes
    assert any("imported by unchanged modules: pkg.util" in n for n in notes)


# -- test-side changes ---------------------------------------------------------


def test_new_test_file_is_run(repo, baseline):
    s.write(repo, "tests/test_new.py", "def test_fresh():\n    assert True\n")
    sel = s.select_now(repo, baseline)
    assert_impact(sel, set())
    assert sel.new_test_files == ["tests/test_new.py"]
    assert "tests/test_new.py" in sel.manifest()["pytest_targets"]


def test_new_test_file_is_a_target_at_file_granularity(repo, baseline):
    s.write(repo, "tests/test_new.py", "def test_fresh():\n    assert True\n")
    sel = s.select_now(repo, baseline, s.synth_config(granularity="file"))
    assert sel.manifest()["pytest_targets"] == ["tests/test_new.py"]


def test_new_test_in_modified_file_runs_at_test_granularity(repo, baseline, tmp_path, monkeypatch):
    from types import SimpleNamespace

    from tools.tia import pytest_select
    from tools.tia.runner import pytest_command

    s.write(repo, "tests/test_util.py", s.read(repo, "tests/test_util.py") + TRIPLED)
    sel = s.select_now(repo, baseline)
    assert s.selected(sel) == {DOUBLE, CAPPED}
    out = tmp_path / "out"
    out.mkdir()
    cmd = pytest_command(sel, str(repo), str(out), [])
    assert "tests/test_util.py" in cmd

    # what pytest would collect from the targets, filtered by the plugin
    collected = [SimpleNamespace(nodeid=n) for n in (DOUBLE, CAPPED, NEW_TRIPLED)]
    deselected = []
    config = SimpleNamespace(
        hook=SimpleNamespace(pytest_deselected=lambda items: deselected.extend(items))
    )
    monkeypatch.setenv(pytest_select.ENV, str(out / "selection.json"))
    pytest_select.pytest_collection_modifyitems(None, config, collected)
    assert {i.nodeid for i in collected} == {DOUBLE, CAPPED, NEW_TRIPLED}


TRIPLED = "\n\ndef test_tripled():\n    assert util.double(3) == 6\n"
NEW_TRIPLED = "tests/test_util.py::test_tripled"


def test_modified_test_file_selects_all_its_tests_only(repo, baseline):
    s.replace(repo, "tests/test_util.py", "== 10", "== 10, 'capped'")
    sel = s.select_now(repo, baseline)
    assert_impact(sel, {DOUBLE, CAPPED})
    assert s.report_for(sel, "tests/test_util.py").category == "test"


def test_deleted_test_file_selects_nothing(repo, baseline):
    (repo / "tests/test_other.py").unlink()
    sel = s.select_now(repo, baseline)
    assert_impact(sel, set())
    assert s.report_for(sel, "tests/test_other.py").status == "deleted"


@pytest.mark.parametrize("granularity", ["file", "test"])
def test_tests_of_a_deleted_file_are_not_pytest_targets(repo, baseline, granularity):
    (repo / "tests/test_core.py").unlink()
    mul_change(repo)  # MUL (deleted) and DOUBLE (still present) cover mul
    sel = s.select_now(repo, baseline, s.synth_config(granularity=granularity))
    assert sel.mode == "test-impact"
    assert DOUBLE in s.selected(sel)
    missing = [f for f in sel.run_files if not (repo / f).exists()]
    assert missing == []


def test_helper_change_selects_importing_test_modules(repo, baseline):
    s.replace(repo, "tests/helpers.py", "return 3", "return 1 + 2")
    assert_impact(s.select_now(repo, baseline), {DOUBLE, CAPPED})


def test_helper_nobody_imports_runs_full_suite(repo, baseline):
    s.replace(repo, "tests/orphan_helper.py", "return None", "return 0")
    sel = s.select_now(repo, baseline)
    assert sel.mode == "full"
    assert s.kinds(sel) == ["test-support-unknown"]
    assert sel.fallbacks[0].path == "tests/orphan_helper.py"


def test_conftest_change_selects_every_test(repo, baseline):
    s.write(repo, "tests/conftest.py", s.read(repo, "tests/conftest.py") + "\n# tweak\n")
    sel = s.select_now(repo, baseline)
    assert s.selected(sel) == set(s.default_tests())
    assert sel.mode == "full"
    assert s.kinds(sel) == ["selection-near-full"]


# -- data and configuration ----------------------------------------------------


def test_unrelated_file_selects_nothing(repo, baseline):
    s.write(repo, "README.md", "# synthetic\n\nEdited.\n")
    sel = s.select_now(repo, baseline)
    assert_impact(sel, set())
    assert s.report_for(sel, "README.md").category == "data"


def test_data_file_read_by_a_test_selects_it(repo, baseline):
    s.write(repo, "tests/data/sample.txt", "changed\n")
    assert_impact(s.select_now(repo, baseline), {SAMPLE})


def test_data_read_in_shared_fixture_setup_selects_every_fixture_user(repo, baseline):
    # the default baseline attributes the read to the `fixture:<key>` bucket
    s.write(repo, "tests/data/shared.txt", "changed\n")
    sel = s.select_now(repo, baseline)
    assert_impact(sel, {USER_A, USER_B})
    for user in (USER_A, USER_B):
        assert any("uses shared fixture 'shared_project'" in r for r in sel.tests[user])


def _shared_read_variant(work, phase: str, *, finalized: bool = False):
    """USER_A reads shared.txt in its own `phase` bucket; no fixture bucket."""

    def edit(tests):
        tests[USER_A]["reads"] = {phase: ["tests/data/shared.txt"]}
        if finalized:
            tests[USER_A]["teardown_finalized"] = [K_PROJECT]

    tests = s.default_tests()
    edit(tests)
    dest = work / "variant"
    s.make_baseline(work / "repo", dest, tests, fixture_attribution={})
    s.write(work / "repo", "tests/data/shared.txt", "changed\n")
    return s.select_now(work / "repo", dest)


def test_function_fixture_setup_read_selects_only_that_test(work):
    # USER_A executed the shared fixture in its setup, but a `<nodeid>|setup`
    # read was made outside it (by a function-scoped fixture): no widening
    assert_impact(_shared_read_variant(work, "setup"), {USER_A})


def test_teardown_read_widens_through_finalized_fixtures(work):
    assert_impact(_shared_read_variant(work, "teardown", finalized=True), {USER_A, USER_B})


@pytest.mark.parametrize(
    "key, expected",
    [(K_EXTERNAL, {FIRST}), (K_SCALED, {FIRST, SECOND}), (K_EMPTY_BASEID, {FIRST, SECOND})],
    ids=[
        "external-fixture-not-widened",
        "repo-fixture-widened",
        "empty-baseid-repo-fixture-widened",
    ],
)
def test_setup_coverage_widens_only_through_repo_defined_fixtures(work, key, expected):
    tests = s.default_tests()
    for nodeid in (FIRST, SECOND):
        tests[nodeid]["shared_fixtures"] = [key]
    tests[FIRST]["setup_executed"] = [key]
    dest = work / "variant"
    s.make_baseline(work / "repo", dest, tests)
    s.replace(
        work / "repo",
        CORE,
        "out = [v * factor for v in values]",
        "out = [factor * v for v in values]",
    )
    assert_impact(s.select_now(work / "repo", dest), expected)


def test_fixture_spawn_makes_every_fixture_user_opaque(work):
    dest = work / "variant"
    attribution = s.default_fixture_attribution()
    attribution[K_PROJECT]["spawns"] = ["python -m elspais"]
    manifest = s.make_baseline(work / "repo", dest, fixture_attribution=attribution)
    # the fixture's spawn is folded into each user's, and nobody else's
    assert {n for n, t in manifest["tests"].items() if t["spawns"]} == {USER_A, USER_B}
    mul_change(work / "repo")
    sel = s.select_now(work / "repo", dest)
    assert_impact(sel, {MUL, DOUBLE, USER_A, USER_B})
    for user in (USER_A, USER_B):
        assert any(r.startswith("spawns python -m elspais") for r in sel.tests[user])


def test_package_data_selects_tests_of_modules_naming_it(repo, baseline):
    # core.py's TEMPLATE literal names data/template.txt
    s.write(repo, "src/pkg/data/template.txt", "Goodbye {name}\n")
    sel = s.select_now(repo, baseline)
    assert_impact(sel, CORE_FILE)
    assert f"loaded by {CORE}" in s.report_for(sel, "src/pkg/data/template.txt").regions


def test_pyproject_dependency_change_runs_full_suite(repo, baseline):
    s.replace(repo, "pyproject.toml", "tomlkit>=0.12", "tomlkit>=0.13")
    sel = s.select_now(repo, baseline)
    assert sel.mode == "full"
    assert s.kinds(sel) == ["broad-impact-file"]
    assert sel.fallbacks[0].path == "pyproject.toml"


def test_pyproject_version_bump_is_not_full(repo, baseline):
    s.replace(repo, "pyproject.toml", 'version = "1.0.0"', 'version = "1.0.1"')
    sel = s.select_now(repo, baseline)
    assert_impact(sel, set())
    assert s.report_for(sel, "pyproject.toml").category == "manifest (ignored keys only)"


def test_no_change_selects_nothing(repo, baseline):
    sel = s.select_now(repo, baseline)
    assert_impact(sel, set())
    assert sel.changed == []
    assert sel.manifest()["skipped_tests"] == len(s.default_tests())


# -- always-on additions -------------------------------------------------------


def _variant_baseline(work, edit) -> object:
    tests = s.default_tests()
    edit(tests)
    dest = work / "variant"
    s.make_baseline(work / "repo", dest, tests)
    return dest


def test_non_passing_baseline_tests_are_selected_on_any_change(work):
    def edit(tests):
        tests[OTHER_A]["outcome"] = "failed"
        tests[SAMPLE]["outcome"] = "skipped"

    variant = _variant_baseline(work, edit)
    repo = work / "repo"
    assert_impact(s.select_now(repo, variant), set())  # nothing changed

    s.write(repo, "README.md", "edited\n")
    sel = s.select_now(repo, variant)
    assert_impact(sel, {OTHER_A, SAMPLE})
    assert any("baseline outcome was 'failed'" in r for r in sel.tests[OTHER_A])


@pytest.mark.parametrize(
    "edit_path, old, new, expect_spawner",
    [
        (CORE, "product = a * b", "product = b * a", True),
        ("tests/test_util.py", "== 10", "== 10, 'capped'", False),
    ],
    ids=["production-change", "test-only-change"],
)
def test_opaque_spawner_selected_for_non_test_changes(work, edit_path, old, new, expect_spawner):
    def edit(tests):
        tests[OTHER_A]["spawns"] = {"run": ["python -m elspais"]}

    variant = _variant_baseline(work, edit)
    s.replace(work / "repo", edit_path, old, new)
    sel = s.select_now(work / "repo", variant)
    assert sel.mode == "test-impact"
    assert (OTHER_A in s.selected(sel)) is expect_spawner


def test_always_run_is_selected(repo, baseline):
    mul_change(repo)
    sel = s.select_now(repo, baseline, s.synth_config(always_run=["tests/test_other.py"]))
    assert_impact(sel, {MUL, DOUBLE, OTHER_A, OTHER_B})


# -- granularity and determinism -----------------------------------------------


def test_file_granularity_runs_whole_files(repo, baseline):
    mul_change(repo)
    sel = s.select_now(repo, baseline, s.synth_config(granularity="file"))
    assert_impact(sel, {ADD, MUL, GET, DOUBLE, CAPPED})
    assert sel.run_files == ["tests/test_core.py", "tests/test_util.py"]


def test_selection_is_deterministic(repo, baseline):
    mul_change(repo)
    s.write(repo, "tests/data/shared.txt", "changed\n")
    s.write(repo, "src/pkg/plugin.py", 'NAME = "plugin"\n')

    def manifest():
        m = s.select_now(repo, baseline).manifest()
        m.pop("selection_seconds")
        return m

    first = manifest()
    assert first["selected_tests"] > 0
    assert manifest() == first


# -- a baseline recorded over unstaged edits ------------------------------------


def test_dirty_baseline_diffs_against_what_was_tested(work):
    repo = work / "repo"
    committed = s.read(repo, "tests/data/sample.txt")
    s.write(repo, "tests/data/sample.txt", "edited before recording\n")
    dest = work / "dirty-baseline"
    manifest = s.make_baseline(repo, dest)
    assert "tests/data/sample.txt" in manifest["identity"]["dirty"]

    # the file still holds the content the baseline tested: no change
    sel = s.select_now(repo, dest)
    assert_impact(sel, set())
    assert sel.changed == []

    # back to the committed bytes: that IS a change relative to the baseline
    s.write(repo, "tests/data/sample.txt", committed)
    sel = s.select_now(repo, dest)
    assert_impact(sel, {SAMPLE})
    assert [r.path for r in sel.changed] == ["tests/data/sample.txt"]


# -- further production and test-package cases ---------------------------------


def test_deleted_module_selects_its_tests_and_importers(repo, baseline):
    (repo / "src/pkg/other.py").unlink()
    sel = s.select_now(repo, baseline)
    assert_impact(sel, {OTHER_A, OTHER_B})
    assert s.report_for(sel, "src/pkg/other.py").status == "deleted"


def test_package_init_change_reaches_every_importer(repo, baseline):
    s.write(repo, "src/pkg/__init__.py", '"""Synthetic package."""\n\nFLAG = True\n')
    sel = s.select_now(repo, baseline)
    # nobody covered __init__.py's lines; its importers' tests stand in
    assert_impact(sel, {ADD, MUL, GET, DOUBLE, CAPPED, OTHER_A, OTHER_B})


def test_module_nothing_executes_or_imports_runs_full_suite(repo, baseline):
    # FUNCTION (uncovered) -> FILE (uncovered) -> MODULE (no importers)
    s.replace(repo, "src/pkg/lonely.py", "return x", "return -x")
    sel = s.select_now(repo, baseline)
    assert sel.mode == "full"
    assert s.kinds(sel) == ["unmeasured-module"]
    notes = s.report_for(sel, "src/pkg/lonely.py").notes
    assert any("widened to the file" in n for n in notes)
    assert any("widened to its importers" in n for n in notes)


def test_new_test_package_file_runs_full_suite(repo, baseline):
    s.write(repo, "tests/sub/__init__.py", "")
    sel = s.select_now(repo, baseline)
    assert sel.mode == "full"
    assert s.kinds(sel) == ["new-test-package"]


def test_file_read_before_any_test_runs_full_suite(work):
    dest = work / "variant"
    s.make_baseline(
        work / "repo", dest, extra_attribution={"session": {"reads": ["tests/data/sample.txt"]}}
    )
    s.write(work / "repo", "tests/data/sample.txt", "changed\n")
    sel = s.select_now(work / "repo", dest)
    assert sel.mode == "full"
    assert s.kinds(sel) == ["session-read"]


def test_file_read_during_collection_selects_that_module(work):
    dest = work / "variant"
    s.make_baseline(
        work / "repo",
        dest,
        extra_attribution={"collect:tests/test_other.py": {"reads": ["README.md"]}},
    )
    s.write(work / "repo", "README.md", "changed\n")
    assert_impact(s.select_now(work / "repo", dest), {OTHER_A, OTHER_B})
