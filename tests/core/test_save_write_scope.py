# Verifies: REQ-d00132-E, REQ-d00253-B, REQ-d00253-G
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

A change is not confined to the file its author edited: renaming a
requirement corrects the reference in every file citing it, and those files
may belong to other members. So a save that cannot write every file the work
requires writes NONE of it (REQ-d00253-G). Writing the part the scope reaches
would leave a member citing an identifier that no longer exists -- a reference
broken by the save itself, in a file nobody edited. Every member is left as it
was and the whole change stays pending, so the operator's recourse is to widen
the write scope and save again.

The federation here is two real repositories on disk, mutated through the
FederatedGraph so the federated log records a pointer, because the pointer is
half of what the defect destroyed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from elspais.config import load_config
from elspais.graph.factory import build_graph
from elspais.graph.GraphNode import make_file_id
from elspais.graph.render import _files_with_pending_mutations, render_save
from tests.federation_repos import make_repo, namespace_for

PRIMARY_REQ = "CORE-d00001"
ASSOCIATE_REQ = "LIB-d00001"

# The FILE node a save declines to write. Spelled in full because the
# message has to name it in full: the id carries colons, and a caller
# reading a truncated one cannot find the file it names.
ASSOCIATE_FILE = make_file_id(namespace_for("lib"), "spec/reqs.md")

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

# A journey in the associate that validates the PRIMARY's requirement. It is
# the motivating shape of REQ-d00253-G: renaming the requirement corrects the
# identifier this journey cites, so one rename in the served repository dirties
# a file in a member the write scope does not reach.
ASSOCIATE_JOURNEY = "JNY-Lib-01"
ASSOCIATE_JOURNEY_SPEC = f"""# User Journeys

---

### {ASSOCIATE_JOURNEY}: A lib journey

**Actor**: End User
**Goal**: Do a thing
Validates: {PRIMARY_REQ}

*End* *{ASSOCIATE_JOURNEY}*
"""

# The identifier the primary's requirement is renamed to.
RENAMED_PRIMARY_REQ = "CORE-d00002"


class Federation:
    """A primary repository and the one associate it declares."""

    def __init__(self, graph, primary: Path, associate: Path) -> None:
        self.graph = graph
        self.primary = primary
        self.associate = associate
        self.primary_spec = primary / "spec" / "reqs.md"
        self.associate_spec = associate / "spec" / "reqs.md"
        self.associate_journey = associate / "spec" / "journeys.md"
        self._before = {
            path: path.read_bytes()
            for path in (self.primary_spec, self.associate_spec, self.associate_journey)
            if path.exists()
        }

    def save(self, **kwargs):
        return render_save(self.graph, repo_root=self.primary, **kwargs)

    def untouched(self, path: Path) -> bool:
        return path.read_bytes() == self._before[path]

    def member_log(self, node_id: str):
        """The owning member's OWN mutation log, not the federated view."""
        return self.graph.repo_for(node_id).graph.mutation_log


def _federation(
    tmp_path: Path,
    associate_spec: str | None = None,
    associate_journey: str | None = None,
) -> Federation:
    associate = make_repo(tmp_path, "lib")
    if associate_spec is not None:
        (associate / "spec" / "reqs.md").write_text(associate_spec, encoding="utf-8")
    if associate_journey is not None:
        (associate / "spec" / "journeys.md").write_text(associate_journey, encoding="utf-8")
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
    """Validates REQ-d00132-E, REQ-d00253-B, REQ-d00253-G.

    A save that held back a file somebody had queued work for did not do what
    it was asked, so it does not clear the log and does not report success --
    and under REQ-d00253-G it writes nothing at all, so the work it holds is
    every member's work, still entire.
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
            "the federated mutation log was cleared by a save that wrote none of it"
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

    # Verifies: REQ-d00253-G
    def test_d00253_G_the_in_scope_file_is_not_written_either(self, federation):
        """REQ-d00253-G: holding one member's file back holds all of it back.
        The served repository's change is in scope and still is not written,
        because the change as a whole cannot be."""
        _queue(federation, also_primary=True)

        result = federation.save()

        assert result["saved_count"] == 0, (
            f"the served repository's file was written even though a member was held back: {result}"
        )
        assert result["files_modified"] == [], result
        assert federation.untouched(federation.primary_spec), (
            "the served repository's file was rewritten although the save could not "
            "write the member held back with it"
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


class TestADeclineIsNamedAsOne:
    """Validates REQ-d00253-B.

    A save that held a file back and a save that could not write one both
    arrive as an unsuccessful save. A caller can act on the first -- reach the
    associate's repository from a tool that serves it, or opt in -- and
    repeating the request answers neither, so the result names the decline
    rather than leaving the two looking alike.
    """

    # Verifies: REQ-d00253-B
    @pytest.mark.parametrize("also_primary", HELD_BACK_SHAPES)
    def test_d00253_B_a_decline_carries_its_own_code(self, federation, also_primary):
        """REQ-d00253-B: whether or not the save also had work in scope, what
        it declined is the same answer and carries the same code."""
        _queue(federation, also_primary)

        result = federation.save()

        assert result.get("code") == "write_scope_declined", (
            f"a save that declined to write an associate's file reported {result.get('code')!r}"
        )

    # Verifies: REQ-d00253-B
    def test_d00253_B_the_error_names_the_held_back_file_in_full(self, federation):
        """REQ-d00253-B: the caller is told which file it still holds work for,
        by an id it can use -- namespace and path, not a prefix of one."""
        _queue(federation, also_primary=False)

        result = federation.save()

        assert ASSOCIATE_FILE in result["error"], (
            f"the held-back file is not named in full: {result['error']!r}"
        )

    # Verifies: REQ-d00253-G
    def test_d00253_G_a_decline_writes_nothing_it_could_have_written(self, federation):
        """REQ-d00253-G: a decline is the answer for the whole save, not for
        the one file that provoked it. The served repository's change could
        have been written and deliberately is not, so no member is left
        holding half a change."""
        _queue(federation, also_primary=True)

        result = federation.save()

        assert result.get("code") == "write_scope_declined", result
        assert result["saved_count"] == 0, (
            f"the served repository's file was written even though a member was held back: {result}"
        )
        assert federation.untouched(federation.primary_spec), (
            "the in-scope change reached disk although the save declined the member "
            "whose file the same work touches"
        )

    # Verifies: REQ-d00253-G
    def test_d00253_G_no_file_is_rendered_once_anything_is_held_back(self, federation, monkeypatch):
        """REQ-d00253-G: nothing is written, so nothing is even rendered. A
        renderer that cannot run at all leaves the decline the only answer the
        save can give, which is how a caller knows no write was attempted."""
        _queue(federation, also_primary=True)

        def _explode(*args, **kwargs):
            raise AssertionError("a declined save rendered a file")

        monkeypatch.setattr("elspais.graph.render.render_file", _explode)

        result = federation.save()

        assert result.get("code") == "write_scope_declined", result
        assert result["success"] is False
        assert result["errors"] == result["skipped"], (
            f"a declined save reported something other than what it held back: {result}"
        )


class TestASaveThatDeclinedNothing:
    """Validates REQ-d00253-B.

    The code says something happened. A save that declined nothing must not
    carry it, or a caller mapping it to a refusal refuses a save that worked.
    """

    # Verifies: REQ-d00253-B
    def test_d00253_B_a_successful_save_carries_no_code(self, federation):
        """REQ-d00253-B: nothing was held back, so there is nothing to name."""
        federation.graph.change_status(PRIMARY_REQ, NEW_STATUS)

        result = federation.save()

        assert result["success"] is True, result["errors"]
        assert "code" not in result, result
        assert "error" not in result, result

    # Verifies: REQ-d00253-B
    def test_d00253_B_a_save_with_nothing_pending_carries_no_code(self, federation):
        """REQ-d00253-B: an empty save reaches the early return, which is the
        same return a decline reaches -- and must not borrow its answer."""
        result = federation.save()

        assert result["success"] is True, result["errors"]
        assert "code" not in result, result


class TestAChangeStraddlingTheWriteScopeIsWrittenWhole:
    """Validates REQ-d00253-G.

    The motivating shape: one change in the served repository whose correction
    lands in a member the write scope does not reach. A journey in the
    associate validates the primary's requirement, so renaming that
    requirement corrects the identifier the journey cites. Writing the primary
    alone would leave the associate citing an identifier no repository holds,
    in a file nobody edited -- so the save writes neither, and the pair stays
    consistent.
    """

    @pytest.fixture
    def straddling(self, tmp_path: Path) -> Federation:
        federation = _federation(tmp_path, associate_journey=ASSOCIATE_JOURNEY_SPEC)
        journey = federation.graph.find_by_id(ASSOCIATE_JOURNEY)
        assert journey is not None, "the associate's journey did not load"
        federation.graph.rename_node(PRIMARY_REQ, RENAMED_PRIMARY_REQ)
        pending = {node.id for node in _files_with_pending_mutations(federation.graph)}
        assert pending == {
            make_file_id(namespace_for("core"), "spec/reqs.md"),
            make_file_id(namespace_for("lib"), "spec/journeys.md"),
        }, f"the rename did not straddle the write scope, so this fixture tests nothing: {pending}"
        return federation

    # Verifies: REQ-d00253-G
    def test_d00253_G_the_rename_is_not_written_at_all(self, straddling):
        """REQ-d00253-G: the served repository still names the requirement the
        way every member cites it."""
        result = straddling.save()

        assert result["saved_count"] == 0, result
        assert straddling.untouched(straddling.primary_spec), (
            "the rename reached the served repository's file although the member "
            "holding the citation could not be corrected"
        )
        assert PRIMARY_REQ in straddling.primary_spec.read_text(encoding="utf-8")

    # Verifies: REQ-d00253-G
    def test_d00253_G_the_member_is_left_citing_an_identifier_that_exists(self, straddling):
        """REQ-d00253-G: the reference the save could not correct is a
        reference it must not break either."""
        straddling.save()

        assert straddling.untouched(straddling.associate_journey)
        cited = straddling.associate_journey.read_text(encoding="utf-8")
        assert f"Validates: {PRIMARY_REQ}" in cited, (
            "the associate's journey no longer cites the identifier the served repository holds"
        )

    # Verifies: REQ-d00253-G
    def test_d00253_G_the_whole_rename_stays_pending(self, straddling):
        """REQ-d00253-G: the operator's recourse is to widen the write scope
        and save again, which needs the change still in hand."""
        result = straddling.save()

        assert result.get("code") == "write_scope_declined", result
        assert any(
            entry.operation == "rename_node" and entry.target_id == PRIMARY_REQ
            for entry in straddling.graph.mutation_log.iter_entries()
        ), "the rename was discarded by the save that refused to write it"

    # Verifies: REQ-d00253-G
    def test_d00253_G_widening_the_write_scope_writes_both_members(self, straddling):
        """REQ-d00253-G: what the decline preserved is exactly what the second
        save performs, in both members at once."""
        result = straddling.save(write_associates=True)

        assert result["success"] is True, result["errors"]
        assert RENAMED_PRIMARY_REQ in straddling.primary_spec.read_text(encoding="utf-8")
        assert f"Validates: {RENAMED_PRIMARY_REQ}" in straddling.associate_journey.read_text(
            encoding="utf-8"
        ), "the citation in the member was not corrected although writes were permitted"
