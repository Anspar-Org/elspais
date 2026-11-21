"""The files to review after a requirement change, and the review record.

Every test runs against a small git project under pytest's temp directory:
one spec file holding three requirements, code under ``src/`` and tests
under ``tests/`` citing them. The project is committed on ``main``, a branch
changes one *Assertion*, adds another, and edits a title and a rationale, and
the report, the command line and the agent tool are read against it.
"""

from __future__ import annotations

import datetime
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from elspais.cli import main
from elspais.commands.changed import compute_changes
from elspais.graph.factory import build_graph
from elspais.utilities.git import comparison_base
from elspais.utilities.hasher import compute_normalized_hash
from elspais.utilities.review_record import RECORD_PATH, read_record

REVIEWER_NAME = "Rita Reviewer"
REVIEWER_EMAIL = "rita@example.com"
AUTHOR = "Ann Author (<ann@example.com>)"

_CONFIG = """\
version = 5
cli_ttl = 0

[project]
name = "changed-review"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]
skip_files = ["INDEX.md"]

[scanning.code]
directories = ["src"]

[scanning.test]
enabled = true
directories = ["tests"]
file_patterns = ["test_*.py"]

[changelog]
hash_current = false
present = false
"""

# The local state elspais keeps beside the record, ignored the way this
# repository ignores it.
_GITIGNORE = """\
.elspais/daemon.*
.elspais/automatic-save.json
.elspais/daemon-port.json
.elspais/unsaved-changes
.elspais/lost-changes
"""

ALPHA = {
    "A": "The tool SHALL do alpha one.",
    "B": "The tool SHALL do alpha two.",
    "C": "The tool SHALL do alpha three.",
}

# Line 1 cites one Assertion; line 5 cites the whole requirement.
_MOD = """\
# Implements: REQ-d00001-A
def alpha():
    return 1

# Implements: REQ-d00001
def whole():
    return 2
"""

# Line 1 cites A and B by expansion; line 5 cites C, which never changes.
_TEST_ALPHA = """\
# Verifies: REQ-d00001-A+B
def test_alpha():
    pass

# Verifies: REQ-d00001-C
def test_alpha_three():
    pass
"""

_FILES = {
    "src/mod.py": _MOD,
    # B never changes: a citation of it lists nothing.
    "src/other.py": "# Implements: REQ-d00001-B\ndef other():\n    return 3\n",
    # REQ-d00002 shares the spec file with the changed requirement.
    "src/beta.py": "# Implements: REQ-d00002-A\ndef beta():\n    return 4\n",
    # REQ-d00003 has only its title and rationale edited.
    "src/gamma.py": "# Implements: REQ-d00003\ndef gamma():\n    return 5\n",
    "tests/test_alpha.py": _TEST_ALPHA,
}


def _requirement(
    req_id: str,
    title: str,
    assertions: dict[str, str],
    rationale: str = "",
    author: str | None = None,
) -> str:
    """A requirement in canonical form whose recorded hash matches its Assertions."""
    digest = compute_normalized_hash(list(assertions.items()))
    lines = [
        f"## {req_id}: {title}",
        "",
        "**Level**: dev | **Status**: Active | **Implements**: -",
        "",
        "### Assertions",
        "",
    ]
    for label, text in assertions.items():
        lines += [f"{label}. {text}", ""]
    if rationale:
        lines += ["### Rationale", "", rationale, ""]
    if author:
        lines += ["### Changelog", "", f"- 2026-11-01 | {digest} | - | {author} | Authored", ""]
    lines += [f"*End* *{title}* | **Hash**: {digest}", ""]
    return "\n".join(lines) + "\n"


def _spec(
    alpha: dict[str, str] = ALPHA,
    gamma_title: str = "Gamma",
    gamma_rationale: str = "Gamma exists for a reason.",
) -> str:
    return (
        "# Dev Requirements\n\n"
        + _requirement("REQ-d00001", "Alpha", alpha, author=AUTHOR)
        + _requirement("REQ-d00002", "Beta", {"A": "The tool SHALL do beta one."})
        + _requirement(
            "REQ-d00003",
            gamma_title,
            {"A": "The tool SHALL do gamma one."},
            rationale=gamma_rationale,
        )
    )


def _git(root: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True)
    return done.stdout.strip()


def _commit_all(root: Path, message: str) -> None:
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", message)


def _write(root: Path, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _make_project(root: Path, branch: str = "main") -> Path:
    """A committed project on *branch*, nothing changed yet."""
    root.mkdir(parents=True, exist_ok=True)
    _write(root, ".elspais.toml", _CONFIG)
    _write(root, ".gitignore", _GITIGNORE)
    _write(root, "spec/dev.md", _spec())
    for relative, text in _FILES.items():
        _write(root, relative, text)
    _git(root, "init", "-q", "-b", branch)
    _git(root, "config", "user.name", REVIEWER_NAME)
    _git(root, "config", "user.email", REVIEWER_EMAIL)
    _commit_all(root, "init")
    return root


def _change_alpha(root: Path, a_text: str, commit_new_assertion: bool = True) -> None:
    """On a branch: add Assertion D and a test citing it (committed), then
    edit Assertion A and REQ-d00003's title and rationale (uncommitted)."""
    _git(root, "checkout", "-q", "-b", "feature")
    if commit_new_assertion:
        _write(root, "spec/dev.md", _spec({**ALPHA, "D": "The tool SHALL do alpha four."}))
        _write(
            root, "tests/test_delta.py", "# Verifies: REQ-d00001-D\ndef test_delta():\n    pass\n"
        )
        _commit_all(root, "add alpha four")
    _write(
        root,
        "spec/dev.md",
        _spec(
            {**ALPHA, "A": a_text, "D": "The tool SHALL do alpha four."},
            gamma_title="Gamma Renamed",
            gamma_rationale="Gamma exists for a better reason.",
        ),
    )


def _compute(root: Path, base_branch: str = "main") -> dict[str, Any]:
    """compute_changes over a fresh graph of *root*, as JSON would carry it."""
    graph = build_graph(repo_root=root, config_path=root / ".elspais.toml")
    return json.loads(json.dumps(compute_changes(graph, root, base_branch)))


def _changes(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {change["id"]: change for change in report["changes"]}


def _files(change: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {entry["path"]: entry for entry in change["files"]}


def _run(monkeypatch, capsys, root: Path, *argv: str) -> tuple[int, str, str]:
    """``elspais <argv>`` in-process in *root*: (exit code, stdout, stderr)."""
    monkeypatch.chdir(root)
    capsys.readouterr()
    try:
        rc = main(list(argv))
    except SystemExit as exc:
        rc = exc.code if isinstance(exc.code, int) else 2
    captured = capsys.readouterr()
    return rc, captured.out, captured.err


def _reviewer_from_config_only(monkeypatch) -> None:
    """Leave git config as the only source of the reviewer's identity."""
    for name in (
        "GIT_AUTHOR_NAME",
        "GIT_AUTHOR_EMAIL",
        "GIT_COMMITTER_NAME",
        "GIT_COMMITTER_EMAIL",
    ):
        monkeypatch.delenv(name, raising=False)


def _record_text(root: Path) -> str:
    return (root / RECORD_PATH).read_text()


# ---------------------------------------------------------------------------
# One project, changed on a branch, reviewed step by step
# ---------------------------------------------------------------------------


@pytest.fixture(scope="class")
def project(tmp_path_factory) -> Path:
    root = _make_project(tmp_path_factory.mktemp("changed_review") / "repo")
    _change_alpha(root, "The tool SHALL do alpha one, twice.")
    return root


@pytest.fixture(scope="class")
def state() -> dict[str, Any]:
    return {}


@pytest.mark.incremental
class TestReviewWorkflow:
    """A change on a branch, its files to review, and the record of each review."""

    def test_01_changed_and_added_assertions_are_changes(self, project, state):
        state["report"] = report = _compute(project)
        changes = _changes(report)

        assert report["verifiable"] is True
        # Verifies: REQ-d00336-A
        # A's text differs from the base (an uncommitted edit); D is absent there.
        assert changes["REQ-d00001-A"]["kind"] == "assertion"
        assert changes["REQ-d00001-A"]["added"] is False
        assert changes["REQ-d00001-A"]["requirement"] == "REQ-d00001"
        assert changes["REQ-d00001-D"]["added"] is True
        # B and C hold the text they held at the base.
        assert "REQ-d00001-B" not in changes
        assert "REQ-d00001-C" not in changes
        assert [c["id"] for c in report["changes"]] == sorted(changes)

    def test_02_requirement_is_a_change_only_where_its_assertions_moved(self, state):
        changes = _changes(state["report"])

        # Verifies: REQ-d00336-B
        assert changes["REQ-d00001"]["kind"] == "requirement"
        assert changes["REQ-d00001"]["added"] is False
        # Shares the spec file with the changed requirement.
        assert not any(cid.startswith("REQ-d00002") for cid in changes)
        # Only its title and rationale were edited.
        assert not any(cid.startswith("REQ-d00003") for cid in changes)

    def test_03_report_names_the_base_branch_and_commit(self, project, state, monkeypatch, capsys):
        base = comparison_base(project, "main")
        merge_base = _git(project, "merge-base", "HEAD", "main")

        # Verifies: REQ-d00336-C
        # No remote copy exists, so the local base branch is read.
        assert (base.ref, base.commit, base.error) == ("main", merge_base, None)

        # Verifies: REQ-d00336-D
        assert state["report"]["base"] == {"branch": "main", "ref": "main", "commit": merge_base}
        rc, out, _err = _run(monkeypatch, capsys, project, "changed")
        assert rc == 0
        assert "main" in out
        assert merge_base[:7] in out

    def test_04_each_change_lists_the_files_citing_it_with_their_lines(self, state):
        changes = _changes(state["report"])
        listed = {
            cid: {path: entry["lines"] for path, entry in _files(change).items()}
            for cid, change in changes.items()
        }

        # Verifies: REQ-d00336-E
        # A citation naming the changed Assertion, written alone or by expansion.
        assert set(listed["REQ-d00001-A"]) == {"src/mod.py", "tests/test_alpha.py"}
        assert set(listed["REQ-d00001-D"]) == {"tests/test_delta.py"}
        # Verifies: REQ-d00336-F
        # Only the citation naming the whole requirement.
        assert set(listed["REQ-d00001"]) == {"src/mod.py"}
        every_path = {path for files in listed.values() for path in files}
        assert not every_path & {"src/other.py", "src/beta.py", "src/gamma.py"}

        # Verifies: REQ-d00336-G
        # The line of the citation that listed the file, and no other.
        assert listed["REQ-d00001-A"] == {"src/mod.py": [1], "tests/test_alpha.py": [1]}
        assert listed["REQ-d00001"] == {"src/mod.py": [5]}
        assert listed["REQ-d00001-D"] == {"tests/test_delta.py": [1]}
        for change in state["report"]["changes"]:
            assert [f["path"] for f in change["files"]] == sorted(_files(change))

    def test_05_each_listed_file_is_marked_awaiting_review(
        self, project, state, monkeypatch, capsys
    ):
        report = state["report"]
        entries = [entry for change in report["changes"] for entry in change["files"]]

        # Verifies: REQ-d00336-N
        assert entries and {e["status"] for e in entries} == {"awaiting"}
        assert all(e["review"] is None and e["stale"] is False for e in entries)
        assert report["summary"] == {
            "changes": 3,
            "files": 4,
            "awaiting": 4,
            "reviewed": 0,
        }
        assert report["carried"] == []

        rc, out, _err = _run(monkeypatch, capsys, project, "changed")
        assert rc == 0
        for cid in ("REQ-d00001", "REQ-d00001-A", "REQ-d00001-D"):
            assert cid in out
        for path in ("src/mod.py", "tests/test_alpha.py", "tests/test_delta.py"):
            assert any(path in line and "awaiting" in line for line in out.splitlines()), out
        assert any("src/mod.py" in line and "5" in line for line in out.splitlines()), out

    def test_06_agent_tool_reports_what_the_command_reports(self, project, monkeypatch, capsys):
        pytest.importorskip("mcp")
        from elspais.mcp.server import _get_changed_requirements

        rc, out, _err = _run(monkeypatch, capsys, project, "changed", "--format", "json")
        assert rc == 0
        graph = build_graph(repo_root=project, config_path=project / ".elspais.toml")
        tool = json.loads(json.dumps(_get_changed_requirements(graph, project)))

        # Verifies: REQ-d00336-H
        assert json.loads(out) == tool

        # Verifies: REQ-d00336-J
        # Reading the report, from either surface, records nothing.
        assert not (project / RECORD_PATH).exists()

    def test_07_write_record_names_each_awaiting_file_in_a_tracked_file(
        self, project, monkeypatch, capsys
    ):
        rc, _out, err = _run(monkeypatch, capsys, project, "changed", "--write-record")
        assert rc == 0, err
        record_file = project / RECORD_PATH

        # Verifies: REQ-d00336-I
        assert record_file.is_file()
        ignored = subprocess.run(
            ["git", "check-ignore", "-q", str(RECORD_PATH)], cwd=project, check=False
        )
        assert ignored.returncode == 1
        _git(project, "add", str(RECORD_PATH))
        assert _git(project, "ls-files", str(RECORD_PATH)) == str(RECORD_PATH)

        # Verifies: REQ-d00336-O
        text = _record_text(project)
        for path in ("src/mod.py", "tests/test_alpha.py", "tests/test_delta.py"):
            assert path in text
        awaiting = {(a.change_id, a.path) for a in read_record(project).awaiting}
        assert awaiting == {
            ("REQ-d00001", "src/mod.py"),
            ("REQ-d00001-A", "src/mod.py"),
            ("REQ-d00001-A", "tests/test_alpha.py"),
            ("REQ-d00001-D", "tests/test_delta.py"),
        }

        # Verifies: REQ-d00336-J
        # Writing the files awaiting review records no review of them.
        assert read_record(project).reviews == []
        assert {e["status"] for c in _compute(project)["changes"] for e in c["files"]} == {
            "awaiting"
        }

    def test_08_fix_leaves_the_record_as_it_is(self, project, monkeypatch, capsys):
        # A new citation makes the record out of date against the current
        # changes, so a fix that wrote the record would change it.
        extra = project / "tests" / "test_more.py"
        extra.write_text("# Verifies: REQ-d00001-A\ndef test_more():\n    pass\n")
        before = (project / RECORD_PATH).read_bytes()

        rc, out, err = _run(monkeypatch, capsys, project, "fix")
        assert rc == 0, out + err

        # Verifies: REQ-d00336-J
        assert (project / RECORD_PATH).read_bytes() == before
        extra.unlink()

    def test_09_review_records_only_the_change_asked_for(self, project, monkeypatch, capsys):
        _reviewer_from_config_only(monkeypatch)
        rc, _out, err = _run(
            monkeypatch,
            capsys,
            project,
            "changed",
            "--review",
            "src/mod.py",
            "--change",
            "REQ-d00001-A",
        )
        assert rc == 0, err
        changes = _changes(_compute(project))
        under_a = _files(changes["REQ-d00001-A"])
        today = datetime.date.today().isoformat()

        # Verifies: REQ-d00336-N
        assert under_a["src/mod.py"]["status"] == "reviewed"
        assert under_a["src/mod.py"]["stale"] is False
        assert under_a["tests/test_alpha.py"]["status"] == "awaiting"
        # Verifies: REQ-d00336-J
        # The review asked for one change; the same file under another stays awaiting.
        assert _files(changes["REQ-d00001"])["src/mod.py"]["status"] == "awaiting"
        # Verifies: REQ-d00336-K
        assert REVIEWER_NAME in under_a["src/mod.py"]["review"]["reviewer"]
        assert REVIEWER_EMAIL in under_a["src/mod.py"]["review"]["reviewer"]
        # Verifies: REQ-d00336-L
        assert under_a["src/mod.py"]["review"]["date"] == today

    def test_10_the_record_names_each_reviewer_and_date(self, project, monkeypatch, capsys):
        _reviewer_from_config_only(monkeypatch)
        rc, _out, err = _run(monkeypatch, capsys, project, "changed", "--review", "src/mod.py")
        assert rc == 0, err
        text = _record_text(project)
        today = datetime.date.today().isoformat()
        reviews = {(r.change_id, r.path): r for r in read_record(project).reviews}
        changes = _changes(_compute(project))

        assert set(reviews) == {("REQ-d00001-A", "src/mod.py"), ("REQ-d00001", "src/mod.py")}
        assert _files(changes["REQ-d00001"])["src/mod.py"]["status"] == "reviewed"
        # Verifies: REQ-d00336-K
        assert REVIEWER_NAME in text
        assert all(REVIEWER_NAME in r.reviewer for r in reviews.values())
        # Verifies: REQ-d00336-L
        assert today in text
        assert all(r.date == today for r in reviews.values())
        # Verifies: REQ-d00336-O
        # A reviewed file no longer awaits review; the others still do.
        awaiting = {(a.change_id, a.path) for a in read_record(project).awaiting}
        assert awaiting == {
            ("REQ-d00001-A", "tests/test_alpha.py"),
            ("REQ-d00001-D", "tests/test_delta.py"),
        }

    def test_11_a_file_awaiting_no_review_is_refused(self, project, monkeypatch, capsys):
        before = (project / RECORD_PATH).read_bytes()
        rc, out, err = _run(monkeypatch, capsys, project, "changed", "--review", "src/beta.py")

        # Verifies: REQ-d00336-J
        assert rc == 1
        assert "src/beta.py" in out + err
        assert (project / RECORD_PATH).read_bytes() == before

    def test_12_editing_a_reviewed_file_makes_it_await_review(self, project):
        _write(project, "src/mod.py", _MOD + "\n\ndef added_later():\n    return 6\n")
        changes = _changes(_compute(project))

        # Verifies: REQ-d00336-M
        for cid in ("REQ-d00001-A", "REQ-d00001"):
            entry = _files(changes[cid])["src/mod.py"]
            assert (entry["status"], entry["stale"]) == ("awaiting", True), cid

    def test_13_editing_a_reviewed_assertion_makes_its_files_await_review(
        self, project, monkeypatch, capsys
    ):
        _reviewer_from_config_only(monkeypatch)
        rc, _out, err = _run(monkeypatch, capsys, project, "changed", "--review", "src/mod.py")
        assert rc == 0, err
        reviewed = _changes(_compute(project))
        assert _files(reviewed["REQ-d00001-A"])["src/mod.py"]["status"] == "reviewed"

        _write(
            project,
            "spec/dev.md",
            _spec(
                {
                    **ALPHA,
                    "A": "The tool SHALL do alpha one, three times.",
                    "D": "The tool SHALL do alpha four.",
                },
                gamma_title="Gamma Renamed",
                gamma_rationale="Gamma exists for a better reason.",
            ),
        )
        changes = _changes(_compute(project))

        # Verifies: REQ-d00336-M
        # The Assertion moved, and with it the requirement's content.
        for cid in ("REQ-d00001-A", "REQ-d00001"):
            entry = _files(changes[cid])["src/mod.py"]
            assert (entry["status"], entry["stale"]) == ("awaiting", True), cid


# ---------------------------------------------------------------------------
# A remote base branch ahead of the local one, and a change merged past it
# ---------------------------------------------------------------------------


@pytest.fixture(scope="class")
def remote_project(tmp_path_factory) -> Path:
    """A clone whose local ``main`` is behind ``origin/main``, on a branch
    from ``origin/main`` with Assertion A edited.

    Origin's newer commit changes Assertion B, so a comparison against the
    local ``main`` would report B as changed.
    """
    top = tmp_path_factory.mktemp("changed_remote")
    root = _make_project(top / "repo")
    origin = top / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    _git(root, "remote", "add", "origin", str(origin))
    _git(root, "push", "-q", "origin", "main")

    other = top / "other"
    subprocess.run(["git", "clone", "-q", str(origin), str(other)], check=True)
    _git(other, "config", "user.name", "Other Person")
    _git(other, "config", "user.email", "other@example.com")
    _write(other, "spec/dev.md", _spec({**ALPHA, "B": "The tool SHALL do alpha two, upstream."}))
    _commit_all(other, "upstream edits B")
    _git(other, "push", "-q", "origin", "main")

    _git(root, "fetch", "-q", "origin")
    _git(root, "checkout", "-q", "-b", "feature", "origin/main")
    _write(
        root,
        "spec/dev.md",
        _spec(
            {
                **ALPHA,
                "A": "The tool SHALL do alpha one, locally.",
                "B": "The tool SHALL do alpha two, upstream.",
            }
        ),
    )
    return root


@pytest.mark.incremental
class TestRemoteBaseAndCarriedReviews:
    """The base is where the branch meets origin's copy; an unreviewed file
    outlives the change that listed it."""

    def test_01_the_remote_copy_of_the_base_branch_is_compared(self, remote_project):
        root = remote_project
        origin_main = _git(root, "rev-parse", "origin/main")
        assert _git(root, "rev-parse", "main") != origin_main
        base = comparison_base(root, "main")
        report = _compute(root)

        # Verifies: REQ-d00336-C
        assert (base.ref, base.commit, base.error) == ("origin/main", origin_main, None)
        assert report["base"] == {"branch": "main", "ref": "origin/main", "commit": origin_main}
        changes = _changes(report)
        assert "REQ-d00001-A" in changes
        # Changed only in origin's commit, which the local main has not seen.
        assert "REQ-d00001-B" not in changes

    def test_02_an_unreviewed_file_is_reported_after_its_change_merged(
        self, remote_project, monkeypatch, capsys
    ):
        root = remote_project
        rc, _out, err = _run(monkeypatch, capsys, root, "changed", "--write-record")
        assert rc == 0, err
        _commit_all(root, "edit A, with its record")
        _git(root, "checkout", "-q", "main")
        _git(root, "merge", "-q", "--ff-only", "feature")
        _git(root, "push", "-q", "origin", "main")
        report = _compute(root)

        assert report["verifiable"] is True
        assert report["changes"] == []
        # Verifies: REQ-d00336-P
        carried = {(c["id"], c["path"]): c["lines"] for c in report["carried"]}
        assert carried == {
            ("REQ-d00001", "src/mod.py"): [5],
            ("REQ-d00001-A", "src/mod.py"): [1],
            ("REQ-d00001-A", "tests/test_alpha.py"): [1],
        }

    def test_03_a_carried_file_is_reported_until_it_is_reviewed(
        self, remote_project, monkeypatch, capsys
    ):
        root = remote_project
        _reviewer_from_config_only(monkeypatch)
        rc, _out, err = _run(
            monkeypatch, capsys, root, "changed", "--review", "tests/test_alpha.py"
        )
        assert rc == 0, err
        report = _compute(root)

        # Verifies: REQ-d00336-P
        carried = {(c["id"], c["path"]) for c in report["carried"]}
        assert carried == {("REQ-d00001", "src/mod.py"), ("REQ-d00001-A", "src/mod.py")}
        # Verifies: REQ-d00336-K+L
        review = next(r for r in read_record(root).reviews if r.path == "tests/test_alpha.py")
        assert REVIEWER_NAME in review.reviewer
        assert review.date == datetime.date.today().isoformat()


# ---------------------------------------------------------------------------
# A base that cannot be read
# ---------------------------------------------------------------------------


def _no_base_branch(root: Path) -> None:
    _make_project(root, branch="trunk")


def _unrelated_base_branch(root: Path) -> None:
    _make_project(root, branch="trunk")
    _git(root, "checkout", "-q", "--orphan", "main")
    _git(root, "commit", "-q", "-m", "unrelated history")
    _git(root, "checkout", "-q", "trunk")


@pytest.mark.parametrize(
    "shape", [_no_base_branch, _unrelated_base_branch], ids=["no-base-branch", "no-shared-history"]
)
def test_an_unreadable_base_is_reported_unverifiable(tmp_path, monkeypatch, capsys, shape):
    root = tmp_path / "repo"
    shape(root)
    # An edit the report would list, were the base readable.
    _write(root, "spec/dev.md", _spec({**ALPHA, "A": "The tool SHALL do alpha one, again."}))

    base = comparison_base(root, "main")
    report = _compute(root)
    rc, out, err = _run(monkeypatch, capsys, root, "changed")

    # Verifies: REQ-p00004-M
    assert base.commit is None
    assert base.error
    assert report["verifiable"] is False
    assert report["unverifiable_reason"]
    assert report["base"]["commit"] is None
    assert rc == 1
    said = (out + err).lower()
    assert "unverifiable" in said
    assert "no change" not in said


@pytest.mark.parametrize(
    "argv", [("--review", "src/mod.py"), ("--write-record",)], ids=["review", "write-record"]
)
def test_an_unreadable_base_refuses_to_write_the_record(tmp_path, monkeypatch, capsys, argv):
    root = tmp_path / "repo"
    _no_base_branch(root)
    _write(root, "spec/dev.md", _spec({**ALPHA, "A": "The tool SHALL do alpha one, again."}))
    _reviewer_from_config_only(monkeypatch)

    rc, out, err = _run(monkeypatch, capsys, root, "changed", *argv)

    # Verifies: REQ-p00004-M
    assert rc == 1
    assert "unverifiable" in (out + err).lower()
    assert not (root / RECORD_PATH).exists()


# ---------------------------------------------------------------------------
# Review fixes: associates, escaped cells, a record behind, a subdirectory
# ---------------------------------------------------------------------------

_LIB_CONFIG = """\
version = 5
cli_ttl = 0

[project]
name = "lib"
namespace = "LIB"

[scanning.spec]
directories = ["spec"]

[scanning.code]
directories = ["src"]

[changelog]
hash_current = false
present = false
"""

# The same relative path as the root's src/mod.py; its citation is on line 3.
_LIB_MOD = "\n\n# Implements: REQ-d00001-A\ndef lib_alpha():\n    return 7\n"


def _make_federated_project(top: Path) -> Path:
    """A root project declaring an associate whose src/mod.py cites REQ-d00001-A."""
    lib = top / "lib"
    _write(lib, ".elspais.toml", _LIB_CONFIG)
    _write(
        lib, "spec/lib.md", "# Lib\n\n" + _requirement("LIB-d00001", "Lib", {"A": "The lib SHALL."})
    )
    _write(lib, "src/mod.py", _LIB_MOD)
    _git(lib, "init", "-q", "-b", "main")
    _git(lib, "config", "user.name", REVIEWER_NAME)
    _git(lib, "config", "user.email", REVIEWER_EMAIL)
    _commit_all(lib, "init")

    root = _make_project(top / "repo")
    config = (root / ".elspais.toml").read_text()
    _write(
        root,
        ".elspais.toml",
        config + f'\n[associates.lib]\npath = "{lib.as_posix()}"\nnamespace = "LIB"\n',
    )
    _commit_all(root, "declare lib")
    _change_alpha(root, "The tool SHALL do alpha one, twice.")
    return root


def test_an_associate_file_is_listed_under_its_namespace(tmp_path, monkeypatch, capsys):
    root = _make_federated_project(tmp_path)
    listed = _files(_changes(_compute(root))["REQ-d00001-A"])

    # Verifies: REQ-d00336-E
    assert listed["src/mod.py"]["lines"] == [1]
    assert listed["LIB:src/mod.py"]["lines"] == [3]

    _reviewer_from_config_only(monkeypatch)
    rc, _out, err = _run(
        monkeypatch,
        capsys,
        root,
        "changed",
        "--review",
        "LIB:src/mod.py",
        "--change",
        "REQ-d00001-A",
    )
    assert rc == 0, err
    reviewed = _files(_changes(_compute(root))["REQ-d00001-A"])
    assert reviewed["LIB:src/mod.py"]["status"] == "reviewed"
    assert reviewed["src/mod.py"]["status"] == "awaiting"

    _write(tmp_path / "lib", "src/mod.py", _LIB_MOD + "\n\ndef later():\n    return 8\n")
    entry = _files(_changes(_compute(root))["REQ-d00001-A"])["LIB:src/mod.py"]

    # Verifies: REQ-d00336-M
    assert (entry["status"], entry["stale"]) == ("awaiting", True)


def test_a_reviewer_name_holding_a_pipe_reads_back(tmp_path, monkeypatch, capsys):
    root = _make_project(tmp_path / "repo")
    _change_alpha(root, "The tool SHALL do alpha one, twice.")
    name = "Pat | Pipe \\ Slash"
    _git(root, "config", "user.name", name)
    _reviewer_from_config_only(monkeypatch)
    rc, _out, err = _run(monkeypatch, capsys, root, "changed", "--review", "src/mod.py")
    assert rc == 0, err

    rc, out, err = _run(monkeypatch, capsys, root, "changed", "--format", "json")

    # Verifies: REQ-d00336-K
    assert rc == 0, err
    entry = _files(_changes(json.loads(out))["REQ-d00001-A"])["src/mod.py"]
    assert entry["review"]["reviewer"] == f"{name} <{REVIEWER_EMAIL}>"


def test_a_record_behind_the_report_says_so_until_written(tmp_path, monkeypatch, capsys):
    root = _make_project(tmp_path / "repo")
    _change_alpha(root, "The tool SHALL do alpha one, twice.")
    _reviewer_from_config_only(monkeypatch)
    rc, _out, err = _run(monkeypatch, capsys, root, "changed", "--review", "src/mod.py")
    assert rc == 0, err
    _write(root, "src/mod.py", _MOD + "\n\ndef added_later():\n    return 6\n")

    rc, out, _err = _run(monkeypatch, capsys, root, "changed", "--format", "json")
    behind = {(b["id"], b["path"]) for b in json.loads(out)["record_behind"]}
    rc_text, text, _err = _run(monkeypatch, capsys, root, "changed")

    # Verifies: REQ-d00336-O
    assert behind == {("REQ-d00001", "src/mod.py"), ("REQ-d00001-A", "src/mod.py")}
    assert "does not name" in text
    assert "--write-record" in text

    rc, _out, err = _run(monkeypatch, capsys, root, "changed", "--write-record")
    assert rc == 0, err
    assert _compute(root)["record_behind"] == []
    awaiting_section = _record_text(root).split("## Awaiting review")[1].split("## Reviewed")[0]
    assert "src/mod.py" in awaiting_section
    awaiting = {(a.change_id, a.path) for a in read_record(root).awaiting}
    assert {("REQ-d00001", "src/mod.py"), ("REQ-d00001-A", "src/mod.py")} <= awaiting


def test_agent_tool_reads_the_record_at_the_git_root(tmp_path, monkeypatch, capsys):
    pytest.importorskip("mcp")
    from elspais.mcp.server import _get_changed_requirements

    root = _make_project(tmp_path / "repo")
    _change_alpha(root, "The tool SHALL do alpha one, twice.")
    _reviewer_from_config_only(monkeypatch)
    rc, _out, err = _run(monkeypatch, capsys, root, "changed", "--review", "src/mod.py")
    assert rc == 0, err
    graph = build_graph(repo_root=root, config_path=root / ".elspais.toml")
    from_root = json.loads(json.dumps(_get_changed_requirements(graph, root)))
    from_sub = json.loads(json.dumps(_get_changed_requirements(graph, root / "src")))

    # Verifies: REQ-d00336-H
    assert from_sub == from_root
    entry = _files(_changes(from_sub)["REQ-d00001-A"])["src/mod.py"]
    assert entry["status"] == "reviewed"
