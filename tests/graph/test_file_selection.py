"""What a scan reads, what it declines, and what it never opens.

`elspais.graph.file_selection` is the one place a scan decides which files it
reads. These tests pin the three outcomes it distinguishes, because two
requirements turn on the difference between a file merely not selected
(reportable, REQ-d00241-F) and one a skip pattern named (silent, REQ-d00241-G,
REQ-p00015-H), and they pin the two pattern frames it deliberately keeps
apart: a directory is named from the repository root, a file by a glob over
its name.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from elspais.graph.file_selection import (
    Selection,
    dir_is_skipped,
    file_is_included,
    file_is_skipped,
    select_files,
    within_skipped_dir,
)

# Every file the tree below holds, as repo-relative posix paths.
_TREE = (
    "spec/reqs.md",
    "spec/README.md",
    "spec/secret.md",
    "spec/foo.py",
    "spec/api/foo.py",
    "spec/api/README.md",
    "spec/junk/a/b/deep.md",
    "stuff/other.md",
    "stuff/things/junk/x.md",
    "junk/root.md",
)


def _build_tree(root: Path) -> Path:
    """Write the fixture tree under *root* and return it resolved."""
    for relative in _TREE:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"content of {relative}\n")
    return root.resolve()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A repository holding the fixture tree, resolved as the module resolves."""
    return _build_tree(tmp_path / "repo")


def _relative(root: Path, paths: frozenset[Path]) -> set[str]:
    """A result set as repo-relative posix paths, so failures are readable."""
    return {p.relative_to(root).as_posix() for p in paths}


def _answered(selection: Selection) -> frozenset[Path]:
    """Every file the walk answered for at all, either way."""
    return selection.selected | selection.declined


class TestADirectoryPatternNamesAPathFromTheRepositoryRoot:
    """A directory pattern is read from the repository root and nowhere else.

    The whole point of the frame: `junk` names `junk` at the root of the
    repository, not a directory called `junk` at some depth. `**` is what
    spans depth, and it stands for ZERO or more directories, so `**/junk` is a
    strict superset of `junk` rather than an alternative spelling of it.
    """

    @pytest.mark.parametrize(
        ("skip_dirs", "expected"),
        [
            pytest.param(
                [],
                {"stuff/other.md", "stuff/things/junk/x.md", "junk/root.md"},
                id="nothing-skipped",
            ),
            pytest.param(
                ["stuff/things/junk"],
                {"stuff/other.md", "junk/root.md"},
                id="full-path-names-that-directory",
            ),
            pytest.param(
                ["junk"],
                {"stuff/other.md", "stuff/things/junk/x.md"},
                id="bare-name-is-the-root-directory-only",
            ),
            pytest.param(
                ["**/junk"],
                {"stuff/other.md"},
                id="double-star-spans-any-depth-root-included",
            ),
            pytest.param(
                ["stuff/**"],
                {"junk/root.md"},
                id="trailing-double-star-takes-the-whole-subtree",
            ),
        ],
    )
    def test_the_same_word_skips_different_directories_depending_on_its_frame(
        self, repo: Path, skip_dirs: list[str], expected: set[str]
    ) -> None:
        """One pattern list, one tree, and a result that follows the frame."""
        selection = select_files(repo, ["stuff", "junk"], skip_dirs, [], ["*.md"])
        assert _relative(repo, selection.selected) == expected

    @pytest.mark.parametrize(
        ("relative_dir", "skip_dirs", "skipped"),
        [
            pytest.param("stuff/things/junk", ["stuff/things/junk"], True, id="named-exactly"),
            pytest.param("stuff/things/junk", ["junk"], False, id="bare-name-is-not-a-suffix"),
            pytest.param("junk", ["junk"], True, id="bare-name-at-the-root"),
            pytest.param("stuff/things/junk", ["**/junk"], True, id="double-star-at-depth"),
            pytest.param("junk", ["**/junk"], True, id="double-star-is-zero-or-more"),
            pytest.param("stuff", ["stuff/**"], True, id="trailing-double-star-covers-its-own"),
            pytest.param("stuff/things", ["stuff/**"], True, id="trailing-double-star-descends"),
            pytest.param("spec", ["sp*c"], True, id="a-glob-within-one-segment"),
        ],
    )
    def test_dir_is_skipped_reads_a_pattern_segment_by_segment(
        self, relative_dir: str, skip_dirs: list[str], skipped: bool
    ) -> None:
        """The predicate other surfaces ask, answering under the same frame."""
        assert dir_is_skipped(relative_dir, skip_dirs) is skipped


class TestASkippedDirectoryIsPrunedRatherThanFiltered:
    """A skipped directory is not entered, so nothing below it is reached.

    Filtering after the walk would answer the same for a file sitting
    immediately inside a skipped directory and differently for one nested
    further down. Pruning answers the same for both, and it is what lets the
    module promise nothing inside is ever opened.
    """

    # Verifies: REQ-p00015-H
    def test_a_file_several_levels_below_a_skipped_directory_is_not_reached(
        self, repo: Path
    ) -> None:
        """`spec/junk/a/b/deep.md` sits three levels under the skipped dir."""
        selection = select_files(repo, ["spec"], ["spec/junk"], [], ["*.md"])
        assert repo / "spec/junk/a/b/deep.md" not in _answered(selection)
        assert "spec/reqs.md" in _relative(repo, selection.selected), (
            "the walk still ran, so the absence above is a prune and not an empty scan"
        )

    # Verifies: REQ-p00015-H
    @pytest.mark.parametrize(
        ("relative_path", "skip_dirs", "beneath"),
        [
            pytest.param("junk/a/b/deep.md", ["junk"], True, id="topmost-ancestor-matches"),
            pytest.param("junk/a/b/deep.md", ["junk/a/b"], True, id="immediate-parent-matches"),
            pytest.param("junk/a/b/deep.md", ["junk/a"], True, id="a-middle-ancestor-matches"),
            pytest.param("junk/a/b/deep.md", ["other"], False, id="no-ancestor-matches"),
            pytest.param("junk", ["junk"], False, id="the-last-segment-is-the-file-not-a-dir"),
            pytest.param("a/junk", ["a/junk"], False, id="the-pattern-names-the-file-itself"),
        ],
    )
    def test_within_skipped_dir_asks_about_every_directory_above_the_file(
        self, relative_path: str, skip_dirs: list[str], beneath: bool
    ) -> None:
        """Every ancestor is asked about, not merely the immediate parent.

        A caller naming a file directly never walks to it, so this is the
        question it asks instead; answering only for the immediate parent let
        a deeply nested file escape a skip that covers it.
        """
        assert within_skipped_dir(relative_path, skip_dirs) is beneath

    # Verifies: REQ-p00015-H
    def test_a_skipped_directory_is_never_listed_at_all(
        self, repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Nothing inside a skipped directory is even enumerated.

        Answering "not selected" for each file inside would give the same
        `Selection` while still opening the directory, so the result sets
        cannot tell the two apart. What distinguishes them is whether the walk
        descends, so this watches the listing itself: nothing downstream can
        report on content that was never enumerated (REQ-p00015-H).
        """
        listed: list[str] = []
        real_scandir = os.scandir

        def recording_scandir(path, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN202
            listed.append(str(path))
            return real_scandir(path, *args, **kwargs)

        monkeypatch.setattr(os, "scandir", recording_scandir)
        try:
            select_files(repo, ["spec"], ["spec/junk"], [], ["*.md"])
        finally:
            monkeypatch.undo()

        assert str(repo / "spec" / "api") in listed, (
            "a directory nothing skips is listed, so the recorder saw the walk"
        )
        assert not any(str(repo / "spec" / "junk") in entry for entry in listed), (
            f"the skipped directory or its children were listed: {listed}"
        )

    # Verifies: REQ-p00015-H
    def test_a_directory_that_is_both_scanned_and_skipped_contributes_nothing(
        self, repo: Path
    ) -> None:
        """The directory a walk starts at is a directory like any other."""
        selection = select_files(repo, ["spec"], ["spec"], [], ["*.md"])
        assert selection.selected == frozenset()
        assert selection.declined == frozenset()

    def test_a_scan_directory_that_does_not_exist_is_passed_over_without_error(
        self, repo: Path
    ) -> None:
        """A declared directory absent from this checkout is not a failure."""
        selection = select_files(repo, ["nowhere", "spec"], [], [], ["reqs.md"])
        assert _relative(repo, selection.selected) == {"spec/reqs.md"}


class TestAFilePatternIsAGlobOverTheName:
    """A file pattern says what a file is called, never where it sits.

    The two frames are deliberately not interchangeable, so a name written
    into the directory list matches no file and a directory path written into
    the file list matches no directory.
    """

    # Verifies: REQ-p00015-H
    def test_a_skipped_file_name_is_skipped_at_every_depth(self, repo: Path) -> None:
        """`README.md` names the file wherever in the tree it sits."""
        selection = select_files(repo, ["spec"], [], ["README.md"], ["*.md"])
        answered = _answered(selection)
        assert repo / "spec/README.md" not in answered
        assert repo / "spec/api/README.md" not in answered

    def test_a_file_name_written_as_a_directory_pattern_skips_nothing(self, repo: Path) -> None:
        """As a directory pattern `README.md` names a directory at the root."""
        selection = select_files(repo, ["spec"], ["README.md"], [], ["*.md"])
        assert "spec/README.md" in _relative(repo, selection.selected)

    @pytest.mark.parametrize(
        ("name", "skip_files", "skipped"),
        [
            pytest.param("README.md", ["README.md"], True, id="named-exactly"),
            pytest.param("README.md", ["*.md"], True, id="a-glob-over-the-extension"),
            pytest.param("README.md", ["spec/README.md"], False, id="a-path-is-not-a-name"),
            pytest.param("reqs.md", ["README.md"], False, id="another-name"),
        ],
    )
    def test_file_is_skipped_matches_the_name_alone(
        self, name: str, skip_files: list[str], skipped: bool
    ) -> None:
        """The predicate reads the name, so a path spelling matches nothing."""
        assert file_is_skipped(name, skip_files) is skipped

    # Verifies: REQ-d00212-W
    def test_a_kind_pattern_selects_within_the_directory_that_kind_scans(self, repo: Path) -> None:
        """`api/*.py` selects inside a subdirectory of the scanned directory.

        The frame for an include pattern is the directory being scanned, not
        the repository, because that is what a selection is for: a kind
        declares its directories and these patterns choose among what they
        hold. `spec/foo.py` and `spec/api/foo.py` share a name, so only the
        path-within-the-scanned-directory arm can tell them apart.
        """
        selection = select_files(repo, ["spec"], [], [], ["api/*.py"])
        assert _relative(repo, selection.selected) == {"spec/api/foo.py"}
        assert "spec/foo.py" in _relative(repo, selection.declined)

    @pytest.mark.parametrize(
        ("name", "relative_to_scan_dir", "include_files", "included"),
        [
            pytest.param("foo.py", "api/foo.py", ["*.py"], True, id="name-glob-at-any-depth"),
            pytest.param("foo.py", "api/foo.py", ["api/*.py"], True, id="path-within-scan-dir"),
            pytest.param("foo.py", "foo.py", ["api/*.py"], False, id="outside-the-named-subdir"),
            pytest.param("foo.py", "foo.py", ["*.md"], False, id="another-extension"),
        ],
    )
    def test_file_is_included_reads_the_name_and_the_path_within_the_scan(
        self,
        name: str,
        relative_to_scan_dir: str,
        include_files: list[str],
        included: bool,
    ) -> None:
        """Both arms are offered, so either spelling of a pattern selects."""
        assert file_is_included(name, relative_to_scan_dir, include_files) is included


class TestAWalkTellsThreeOutcomesApart:
    """Selected, declined, and skipped -- the distinction `Selection` exists for.

    A file the kind's patterns do not select was still reached, so a
    *Traceability* keyword in it is reported (REQ-d00241-F). A file a skip
    pattern named was never opened and is reported nowhere (REQ-d00241-G).
    Collapsing the two would make one of those requirements unmeetable.
    """

    @pytest.fixture
    def selection(self, repo: Path) -> Selection:
        """One walk of `spec`, selecting markdown and skipping one file."""
        return select_files(repo, ["spec"], [], ["secret.md"], ["*.md"])

    def test_a_file_the_patterns_select_is_selected(self, repo: Path, selection: Selection) -> None:
        """Matching an include pattern with no skip applying means read it."""
        assert _relative(repo, selection.selected) == {
            "spec/reqs.md",
            "spec/README.md",
            "spec/api/README.md",
            "spec/junk/a/b/deep.md",
        }

    # Verifies: REQ-d00241-F
    def test_a_file_no_pattern_selects_is_declined_rather_than_forgotten(
        self, repo: Path, selection: Selection
    ) -> None:
        """The walk reached it, so it is still there to be reported on."""
        assert _relative(repo, selection.declined) == {"spec/foo.py", "spec/api/foo.py"}

    # Verifies: REQ-d00241-G
    def test_a_skipped_file_is_in_neither_set(self, repo: Path, selection: Selection) -> None:
        """A skipped file is passed over in silence, not merely unselected.

        `secret.md` matches the include pattern, so landing in `declined`
        would be the answer a walk that filtered after selecting gives -- and
        it would make the file reportable, which is exactly what a skip
        forbids.
        """
        assert repo / "spec/secret.md" not in _answered(selection)

    # Verifies: REQ-d00241-G
    def test_nothing_under_a_skipped_directory_is_in_either_set(self, repo: Path) -> None:
        """A skipped directory's contents are silent for the same reason."""
        selection = select_files(repo, ["spec"], ["**/junk"], [], ["*.md"])
        assert repo / "spec/junk/a/b/deep.md" not in _answered(selection)
        assert _relative(repo, selection.selected) == {
            "spec/reqs.md",
            "spec/README.md",
            "spec/secret.md",
            "spec/api/README.md",
        }
        assert _relative(repo, selection.declined) == {"spec/foo.py", "spec/api/foo.py"}

    def test_a_walk_that_does_not_recurse_answers_only_for_the_top_level(self, repo: Path) -> None:
        """`recursive=False` reaches neither subdirectory of `spec`."""
        selection = select_files(repo, ["spec"], [], [], ["*.md"], recursive=False)
        assert _relative(repo, selection.selected) == {
            "spec/reqs.md",
            "spec/README.md",
            "spec/secret.md",
        }
        assert _relative(repo, selection.declined) == {"spec/foo.py"}

    def test_one_file_reached_through_two_scan_directories_is_answered_for_once(
        self, repo: Path
    ) -> None:
        """A `Selection` holds sets, so a nested declared directory is not a
        second answer for the same file."""
        selection = select_files(repo, ["spec", "spec/api"], [], [], ["*.py"])
        assert _relative(repo, selection.selected) == {"spec/foo.py", "spec/api/foo.py"}


class TestOneMechanismDecidesWhetherAFileIsScanned:
    """The walk and the predicates beside it answer as one.

    Surfaces that reach spec files without building a graph ask the predicates
    directly while the build asks `select_files`. Two mechanisms disagreeing
    over one pattern is the defect this module was written to end, so the
    composed walk must reach the verdict the predicates reach.
    """

    # Verifies: REQ-d00212-Q
    def test_the_walk_agrees_with_the_predicates_it_is_composed_from(self, repo: Path) -> None:
        """Every file in the tree, judged both ways, judged alike."""
        skip_dirs = ["**/junk", "stuff/things"]
        skip_files = ["secret.md"]
        include_files = ["*.md"]

        selection = select_files(
            repo, ["spec", "stuff", "junk"], skip_dirs, skip_files, include_files
        )

        for relative in _TREE:
            path = repo / relative
            name = Path(relative).name
            if file_is_skipped(name, skip_files) or within_skipped_dir(relative, skip_dirs):
                assert path not in _answered(selection), (
                    f"{relative} is skipped by the predicates but the walk answered for it"
                )
            else:
                assert path in _answered(selection), (
                    f"{relative} is skipped by nothing but the walk did not answer for it"
                )


class TestWhereARepositorySitsOnDiskDecidesNothing:
    """The same repository answers the same wherever it is checked out.

    A directory pattern names content inside the repository. Matched against
    the absolute path instead, a pattern also matched a directory the checkout
    merely sits under, so a repository cloned beneath `node_modules` scanned
    to nothing. Reading every pattern from the repository root is what makes
    the ancestry above that root none of the walk's business.
    """

    @pytest.mark.parametrize("parent_name", ["node_modules", ".venv", "__pycache__"])
    def test_an_ancestor_matching_a_skip_pattern_excludes_nothing_below_the_root(
        self, tmp_path: Path, parent_name: str
    ) -> None:
        """The only component matching a pattern sits above the repository."""
        repo = _build_tree(tmp_path / parent_name / "repo")
        skip_dirs = [parent_name, f"**/{parent_name}"]

        selection = select_files(repo, ["spec"], skip_dirs, [], ["reqs.md"])

        assert _relative(repo, selection.selected) == {"spec/reqs.md"}

    # Verifies: REQ-p00015-H
    def test_the_same_pattern_still_skips_a_match_inside_the_repository(
        self, tmp_path: Path
    ) -> None:
        """The arm the frame must not weaken: a real match below the root."""
        repo = _build_tree(tmp_path / "node_modules" / "repo")
        vendored = repo / "spec" / "node_modules" / "vendored.md"
        vendored.parent.mkdir(parents=True, exist_ok=True)
        vendored.write_text("vendored\n")

        selection = select_files(repo, ["spec"], ["**/node_modules"], [], ["*.md"])

        assert vendored not in _answered(selection)
        assert "spec/reqs.md" in _relative(repo, selection.selected)
