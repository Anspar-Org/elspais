# Verifies: REQ-d00132-E, REQ-d00253-B
"""What a save does with work it declines to write.

``render_save`` writes only the primary repository's files unless
``federation.write_associates`` says otherwise, and it clears the mutation log
once it has succeeded. The federated log's ``clear()`` reaches into every
member's own log, so a save that held a file back and still called itself a
success destroyed the queued edits for that file and reported nothing: the
caller saw ``success`` and an empty log, and the associate's change was gone.

So a held-back file that carries QUEUED work makes the save a failure, which
is what keeps the log. A file that is merely parse-dirty carries nothing
anybody asked for, so holding it back stays silent -- ``elspais fix`` in a
federation meets that case on every run.

The federation here is two real repositories on disk, mutated through the
FederatedGraph so the federated log records a pointer, because the pointer is
half of what the defect destroyed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from elspais.config import load_config
from elspais.graph.factory import build_graph
from elspais.graph.render import render_save
from tests.federation_repos import make_repo

PRIMARY_REQ = "CORE-d00001"
ASSOCIATE_REQ = "LIB-d00001"

# A status no fixture file starts with, so finding it in a file is evidence
# the queued change reached disk rather than a coincidence of the template.
NEW_STATUS = "draft"

# An associate spec whose two assertions sit on consecutive lines. The build
# marks the requirement parse-dirty for it ("assertion_spacing") without any
# mutation being queued -- the tidy-up `elspais fix` would perform, and the
# one held-back file that must not turn a save into a failure.
UNTIDY_ASSOCIATE_SPEC = """# Spec for lib

## LIB-d00001: A thing in lib

**Status**: active

The system shall do a thing.

## Assertions

A. The system SHALL do one thing.
B. The system SHALL do another thing.

*End*
"""


class Federation:
    """A primary repository and the one associate it declares."""

    def __init__(self, graph, primary: Path, associate: Path) -> None:
        self.graph = graph
        self.primary = primary
        self.associate = associate
        self.primary_spec = primary / "spec" / "reqs.md"
        self.associate_spec = associate / "spec" / "reqs.md"
        self._before = {
            self.primary_spec: self.primary_spec.read_bytes(),
            self.associate_spec: self.associate_spec.read_bytes(),
        }

    def save(self, **kwargs):
        return render_save(self.graph, repo_root=self.primary, **kwargs)

    def untouched(self, path: Path) -> bool:
        return path.read_bytes() == self._before[path]

    def member_log(self, node_id: str):
        """The owning member's OWN mutation log, not the federated view."""
        return self.graph.repo_for(node_id).graph.mutation_log


def _federation(tmp_path: Path, associate_spec: str | None = None) -> Federation:
    associate = make_repo(tmp_path, "lib")
    if associate_spec is not None:
        (associate / "spec" / "reqs.md").write_text(associate_spec, encoding="utf-8")
    primary = make_repo(tmp_path, "core", associates={"lib": str(associate)})

    config_path = primary / ".elspais.toml"
    graph = build_graph(
        config=load_config(config_path),
        config_path=config_path,
        repo_root=primary,
        scan_code=False,
        scan_tests=False,
    )
    assert graph.find_by_id(ASSOCIATE_REQ) is not None, "the associate's requirement must load"
    assert graph.find_by_id(PRIMARY_REQ) is not None, "the primary's requirement must load"
    return Federation(graph, primary, associate)


@pytest.fixture
def federation(tmp_path: Path) -> Federation:
    return _federation(tmp_path)


# Both shapes in which a save meets queued work it will not write: alone, and
# alongside work it will. The associate's edit has to survive either way.
HELD_BACK_SHAPES = [
    pytest.param(True, id="primary-and-associate"),
    pytest.param(False, id="associate-only"),
]


def _queue(federation: Federation, also_primary: bool) -> None:
    """Queue a change to the associate, and optionally one to the primary."""
    if also_primary:
        federation.graph.change_status(PRIMARY_REQ, NEW_STATUS)
    federation.graph.change_status(ASSOCIATE_REQ, NEW_STATUS)


class TestQueuedWorkOutlivesTheSaveThatDeclinedIt:
    """Validates REQ-d00132-E, REQ-d00253-B.

    A save that held back a file somebody had queued work for did not do what
    it was asked, so it does not clear the log and does not report success.
    """

    # Verifies: REQ-d00253-B
    @pytest.mark.parametrize("also_primary", HELD_BACK_SHAPES)
    def test_d00253_B_the_associate_file_is_not_written(self, federation, also_primary):
        """REQ-d00253-B: the write scope holds, whatever else the save wrote."""
        _queue(federation, also_primary)

        federation.save()

        assert federation.untouched(federation.associate_spec), (
            "an associate-owned file was written although write_associates is false"
        )

    # Verifies: REQ-d00132-E
    @pytest.mark.parametrize("also_primary", HELD_BACK_SHAPES)
    def test_d00132_E_the_save_does_not_report_success(self, federation, also_primary):
        """REQ-d00132-E: the log is cleared after a SUCCESSFUL save, so a save
        that left work undone must not be one."""
        _queue(federation, also_primary)

        result = federation.save()

        assert result["success"] is False, (
            "a save that declined to write somebody's queued change reported success"
        )
        assert result["errors"], "the held-back change was not reported to the caller"

    # Verifies: REQ-d00132-E
    @pytest.mark.parametrize("also_primary", HELD_BACK_SHAPES)
    def test_d00132_E_the_held_back_file_is_named_in_skipped(self, federation, also_primary):
        """REQ-d00132-E: the caller is told WHICH file was held back, so it can
        act on work it still holds."""
        _queue(federation, also_primary)

        result = federation.save()

        assert any("LIB" in entry and "spec/reqs.md" in entry for entry in result["skipped"]), (
            f"the held-back associate file is not named in skipped: {result['skipped']}"
        )

    # Verifies: REQ-d00132-E
    @pytest.mark.parametrize("also_primary", HELD_BACK_SHAPES)
    def test_d00132_E_the_federated_log_still_holds_the_work(self, federation, also_primary):
        """REQ-d00132-E: the pointer the federation keeps is still there."""
        _queue(federation, also_primary)
        queued = len(federation.graph.mutation_log)

        federation.save()

        assert len(federation.graph.mutation_log) == queued, (
            "the federated mutation log was cleared by a save that wrote only part of it"
        )
        assert ASSOCIATE_REQ in {
            entry.target_id for entry in federation.graph.mutation_log.iter_entries()
        }, "the associate's queued change was discarded from the federated log"

    # Verifies: REQ-d00132-E
    @pytest.mark.parametrize("also_primary", HELD_BACK_SHAPES)
    def test_d00132_E_the_owning_member_still_holds_the_work(self, federation, also_primary):
        """REQ-d00132-E: and so is the entry it points at.

        ``FederatedMutationLog.clear()`` empties every member's own log too, so
        the pointer surviving proves nothing on its own -- a pointer to an
        entry that is gone resolves to nothing and the change is still lost.
        """
        _queue(federation, also_primary)

        federation.save()

        assert len(federation.member_log(ASSOCIATE_REQ)) == 1, (
            "the associate's own mutation log was emptied, discarding its queued change"
        )

    # Verifies: REQ-d00253-B
    def test_d00253_B_the_primary_file_is_still_written(self, federation):
        """REQ-d00253-B: holding the associate back is not a reason to abandon
        the work that IS in scope."""
        _queue(federation, also_primary=True)

        result = federation.save()

        assert result["saved_count"] == 1, result
        assert NEW_STATUS in federation.primary_spec.read_text(encoding="utf-8"), (
            "the primary repository's queued change never reached disk"
        )

    # Verifies: REQ-d00253-B
    def test_d00253_B_an_associate_only_save_writes_nothing(self, federation):
        """REQ-d00253-B: with nothing in scope, nothing is written -- and the
        refused edit is not diverted into the primary's same-named file."""
        _queue(federation, also_primary=False)

        result = federation.save()

        assert result["saved_count"] == 0, result
        assert result["files_modified"] == []
        assert federation.untouched(federation.primary_spec)
        assert federation.untouched(federation.associate_spec)


class TestSavesThatHeldNothingBack:
    """Validates REQ-d00132-E.

    The condition is "work this save declined to write", not "a federation is
    present". Where there was none, the save succeeds and the log clears.
    """

    # Verifies: REQ-d00132-E
    def test_d00132_E_a_primary_only_save_succeeds_and_clears_the_log(self, federation):
        """REQ-d00132-E: the ordinary case is unchanged."""
        federation.graph.change_status(PRIMARY_REQ, NEW_STATUS)

        result = federation.save()

        assert result["success"] is True, result["errors"]
        assert result["errors"] == []
        assert NEW_STATUS in federation.primary_spec.read_text(encoding="utf-8")
        assert len(federation.graph.mutation_log) == 0, (
            "a successful save left its work queued, so it would be written twice"
        )
        assert len(federation.member_log(PRIMARY_REQ)) == 0

    # Verifies: REQ-d00132-E
    def test_d00132_E_a_save_with_nothing_pending_succeeds(self, federation):
        """REQ-d00132-E: an empty save is a successful save, not a failure with
        an empty error list."""
        result = federation.save()

        assert result["success"] is True, result["errors"]
        assert result["saved_count"] == 0
        assert result["errors"] == []
        assert len(federation.graph.mutation_log) == 0
        assert federation.untouched(federation.primary_spec)
        assert federation.untouched(federation.associate_spec)


class TestAParseDirtyAssociateIsHeldBackSilently:
    """Validates REQ-d00132-E, REQ-d00253-B.

    An associate file the build marked parse-dirty carries formatting the tool
    would tidy, not an edit anybody made. Reporting it would make every
    ``elspais fix`` in a federation a failure over a file the run was never
    going to write.
    """

    @pytest.fixture
    def untidy(self, tmp_path: Path) -> Federation:
        federation = _federation(tmp_path, associate_spec=UNTIDY_ASSOCIATE_SPEC)
        node = federation.graph.find_by_id(ASSOCIATE_REQ)
        assert node.get_field("parse_dirty"), (
            "the associate requirement is not parse-dirty, so this fixture tests nothing"
        )
        assert "stale_hash" not in (node.get_field("parse_dirty_reasons") or []), (
            "a stale hash is not a render_save concern; this must be a structural reason"
        )
        return federation

    # Verifies: REQ-d00132-E
    def test_d00132_E_a_parse_dirty_associate_alone_is_still_a_success(self, untidy):
        """REQ-d00132-E: nothing was queued, so nothing was lost."""
        result = untidy.save()

        assert result["success"] is True, result["errors"]
        assert result["errors"] == []
        assert len(untidy.graph.mutation_log) == 0

    # Verifies: REQ-d00132-E
    def test_d00132_E_a_parse_dirty_associate_does_not_fail_a_real_save(self, untidy):
        """REQ-d00132-E: nor does it spoil a save that had primary work to do --
        the case that would regress ``elspais fix`` in a federation."""
        untidy.graph.change_status(PRIMARY_REQ, NEW_STATUS)

        result = untidy.save()

        assert result["success"] is True, result["errors"]
        assert NEW_STATUS in untidy.primary_spec.read_text(encoding="utf-8")
        assert len(untidy.graph.mutation_log) == 0

    # Verifies: REQ-d00253-B
    def test_d00253_B_a_parse_dirty_associate_is_not_written(self, untidy):
        """REQ-d00253-B: silence is not permission."""
        untidy.save()

        assert untidy.untouched(untidy.associate_spec), (
            "an associate-owned file was tidied although write_associates is false"
        )


class TestWriteAssociatesEnabled:
    """Validates REQ-d00132-E, REQ-d00253-B.

    With associate writes enabled there is nothing to hold back, so the save
    performs the work and clears the log like any other.
    """

    # Verifies: REQ-d00253-B
    def test_d00253_B_the_associate_file_is_written(self, federation):
        """REQ-d00253-B: the setting is what decides, and it decides both ways."""
        _queue(federation, also_primary=False)

        result = federation.save(write_associates=True)

        assert result["success"] is True, result["errors"]
        assert NEW_STATUS in federation.associate_spec.read_text(encoding="utf-8"), (
            "the associate's queued change was not written although it was permitted"
        )

    # Verifies: REQ-d00132-E
    def test_d00132_E_the_log_clears_once_the_work_is_written(self, federation):
        """REQ-d00132-E: the work is on disk, so holding it is now the error."""
        _queue(federation, also_primary=True)

        federation.save(write_associates=True)

        assert len(federation.graph.mutation_log) == 0
        assert len(federation.member_log(ASSOCIATE_REQ)) == 0, (
            "the associate's own log still holds work that has been written"
        )
