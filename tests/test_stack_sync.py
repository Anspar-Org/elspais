"""Tests for the stacked-pull-request sync tool (REQ-o00080).

The plan is a pure function of an event and the open pull requests, tested
directly. The executor is tested against real git repositories in a temporary
directory -- a bare "origin" and clones of it -- with a fake ``gh`` on PATH that
answers from a JSON file and records what it was asked.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tools.stack.sync import (
    CONFLICT_MARKER,
    Executor,
    PullRequest,
    Retarget,
    Update,
    plan_merged,
    plan_pushed,
)

# --- Pure planning ------------------------------------------------------------


def _order(plan) -> list[tuple[int, str, int | None]]:
    """Each update as (pull request, base it is brought up to date with, parent)."""
    return [(u.pr.number, u.base, u.parent) for u in plan.updates]


class TestPlanMerged:
    # Verifies: REQ-o00080-A
    def test_REQ_o00080_A_each_direct_child_is_retargeted_to_the_merged_base(self):
        merged = PullRequest(1, "main", "a")
        b, c = PullRequest(2, "a", "b"), PullRequest(3, "a", "c")
        unrelated = PullRequest(4, "main", "z")
        plan = plan_merged(merged, "f" * 40, [c, unrelated, b])
        assert plan.retargets == [Retarget(b, "main"), Retarget(c, "main")]

    # Verifies: REQ-o00080-B
    def test_REQ_o00080_B_first_update_carries_the_merged_head(self):
        merged = PullRequest(1, "develop", "a")
        plan = plan_merged(merged, "abc123", [PullRequest(2, "a", "b", "[TOOL-2] B")])
        (update,) = plan.updates
        assert update == Update(
            PullRequest(2, "develop", "b", "[TOOL-2] B"),
            "develop",
            merged_head="abc123",
            merged_pr=1,
        )

    # Verifies: REQ-o00080-B+C
    def test_REQ_o00080_C_three_deep_cascade_is_bottom_up(self):
        merged = PullRequest(1, "main", "a")
        stack = [PullRequest(4, "c", "d"), PullRequest(2, "a", "b"), PullRequest(3, "b", "c")]
        plan = plan_merged(merged, "sha", stack)
        assert _order(plan) == [(2, "main", None), (3, "b", 2), (4, "c", 3)]
        # Only the update directly on the merge records the merged commit.
        assert [u.merged_head for u in plan.updates] == ["sha", None, None]
        assert [r.pr.number for r in plan.retargets] == [2]


class TestPlanPushed:
    # Verifies: REQ-o00080-C
    def test_REQ_o00080_C_branching_stack_is_depth_first_lowest_first(self):
        """Two pull requests on one base: the lower-numbered one and everything
        stacked on it come first, each branch before anything above it."""
        prs = [
            PullRequest(5, "b", "e"),
            PullRequest(3, "a", "c"),
            PullRequest(2, "a", "b"),
            PullRequest(6, "c", "f"),
            PullRequest(9, "main", "other"),
        ]
        plan = plan_pushed("a", prs)
        assert _order(plan) == [(2, "a", None), (5, "b", 2), (3, "a", None), (6, "c", 3)]
        assert plan.retargets == []
        assert all(u.merged_head is None for u in plan.updates)

    # Verifies: REQ-o00080-C
    def test_REQ_o00080_C_branch_nobody_stacks_on_plans_nothing(self):
        plan = plan_pushed("lonely", [PullRequest(2, "a", "b"), PullRequest(3, "b", "c")])
        assert (plan.retargets, plan.updates, plan.skipped) == ([], [], [])


class TestCrossRepository:
    # Verifies: REQ-o00080-F
    @pytest.mark.parametrize("event", ["merged", "pushed"])
    def test_REQ_o00080_F_fork_and_its_descendants_are_not_planned(self, event):
        fork = PullRequest(3, "a", "fork-branch", cross_repository=True)
        prs = [PullRequest(2, "a", "b"), fork, PullRequest(4, "fork-branch", "d")]
        if event == "merged":
            plan = plan_merged(PullRequest(1, "main", "a"), "sha", prs)
            assert [r.pr.number for r in plan.retargets] == [2]
        else:
            plan = plan_pushed("a", prs)
        assert [u.pr.number for u in plan.updates] == [2]
        assert len(plan.skipped) == 1 and plan.skipped[0].startswith("#3:")

    # Verifies: REQ-o00080-F
    def test_REQ_o00080_F_fork_higher_in_stack_is_not_planned(self):
        prs = [
            PullRequest(2, "a", "b"),
            PullRequest(3, "b", "fork-branch", cross_repository=True),
            PullRequest(4, "fork-branch", "d"),
        ]
        plan = plan_pushed("a", prs)
        assert [u.pr.number for u in plan.updates] == [2]
        assert [s.split(":")[0] for s in plan.skipped] == ["#3"]


@pytest.mark.parametrize(
    "title, ticket",
    [
        ("[TOOL-155] Stacked pull requests", "[TOOL-155]"),
        ("Fix things [CUR-7] later", "[CUR-7]"),
        ("No ticket here", ""),
        ("[tool-155] lower case", ""),
        ("[A-1] team too short", ""),
    ],
)
def test_ticket_is_read_from_title(title, ticket):
    assert PullRequest(1, "main", "x", title).ticket == ticket


# --- Execution against real git -----------------------------------------------

_FAKE_GH = """#!{python}
import json, os, sys
state = os.environ["FAKE_GH_STATE"]
args = sys.argv[1:]
with open(os.path.join(state, "calls.jsonl"), "a") as f:
    f.write(json.dumps(args) + "\\n")
comments_path = os.path.join(state, "comments.json")
comments = json.load(open(comments_path)) if os.path.exists(comments_path) else {{}}
if args[:2] == ["pr", "list"]:
    sys.stdout.write(open(os.path.join(state, "prs.json")).read())
elif args[:2] == ["pr", "view"]:
    for body in comments.get(args[2], []):
        print(body)
elif args[:2] == ["pr", "comment"]:
    assert args[args.index("--body-file") + 1] == "-"
    comments.setdefault(args[2], []).append(sys.stdin.read())
    json.dump(comments, open(comments_path, "w"))
elif args[:2] == ["pr", "edit"]:
    pass
else:
    sys.exit("fake gh: unexpected call " + " ".join(args))
"""


def _git(*args: str, cwd: Path) -> str:
    proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    assert proc.returncode == 0, f"git {' '.join(args)}: {proc.stderr}"
    return proc.stdout.strip()


class Forge:
    """A bare origin, a working clone to author branches in, and a fake gh."""

    def __init__(self, root: Path):
        self.root = root
        self.origin = root / "origin.git"
        self.work = root / "work"
        self.state = root / "gh-state"
        self.state.mkdir()
        subprocess.run(
            ["git", "init", "--quiet", "--bare", "-b", "main", str(self.origin)], check=True
        )
        subprocess.run(["git", "clone", "--quiet", str(self.origin), str(self.work)], check=True)
        self.commit("f.txt", "line1\n", "base")
        self.push("main")

    # authoring
    def git(self, *args: str) -> str:
        return _git(*args, cwd=self.work)

    def checkout(self, branch: str, start: str | None = None) -> None:
        if start is None:
            self.git("checkout", "--quiet", branch)
        else:
            self.git("checkout", "--quiet", "-b", branch, start)

    def commit(self, path: str, content: str, message: str) -> str:
        (self.work / path).write_text(content)
        self.git("add", path)
        self.git("commit", "--quiet", "-m", message)
        return self.git("rev-parse", "HEAD")

    def push(self, *branches: str) -> None:
        self.git("push", "--quiet", "--force", "origin", *branches)

    def origin_sha(self, branch: str) -> str:
        return _git("rev-parse", f"refs/heads/{branch}", cwd=self.origin)

    def origin_show(self, branch: str, path: str) -> str:
        return _git("show", f"{branch}:{path}", cwd=self.origin)

    def is_ancestor(self, older: str, newer: str) -> bool:
        proc = subprocess.run(["git", "merge-base", "--is-ancestor", older, newer], cwd=self.origin)
        return proc.returncode == 0

    # the fake forge
    def open_prs(self, *prs: PullRequest) -> list[PullRequest]:
        data = [
            {
                "number": p.number,
                "baseRefName": p.base,
                "headRefName": p.head,
                "title": p.title,
                "isCrossRepository": p.cross_repository,
            }
            for p in prs
        ]
        (self.state / "prs.json").write_text(json.dumps(data))
        return list(prs)

    def comments(self, number: int) -> list[str]:
        path = self.state / "comments.json"
        return json.loads(path.read_text()).get(str(number), []) if path.exists() else []

    def gh_calls(self) -> list[list[str]]:
        path = self.state / "calls.jsonl"
        return [json.loads(ln) for ln in path.read_text().splitlines()] if path.exists() else []

    def checkout_for_sync(self) -> Path:
        """A fresh clone of origin, as the workflow's checkout gives the tool."""
        clone = self.root / f"sync-{len(list(self.root.glob('sync-*')))}"
        subprocess.run(["git", "clone", "--quiet", str(self.origin), str(clone)], check=True)
        return clone


@pytest.fixture
def forge(tmp_path, monkeypatch):
    for name in list(os.environ):
        if name.startswith("GIT_"):
            monkeypatch.delenv(name)
    gitconfig = tmp_path / "gitconfig"
    gitconfig.write_text(
        "[user]\n\tname = Stack Test\n\temail = stack@test.invalid\n"
        "[commit]\n\tgpgsign = false\n[init]\n\tdefaultBranch = main\n"
        "[advice]\n\tdetachedHead = false\n"
    )
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(gitconfig))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_TERMINAL_PROMPT", "0")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(_FAKE_GH.format(python=sys.executable))
    gh.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    root = tmp_path / "forge"
    root.mkdir()
    f = Forge(root)
    monkeypatch.setenv("FAKE_GH_STATE", str(f.state))
    return f


def _sync(forge: Forge, monkeypatch, plan) -> tuple[int, Executor]:
    monkeypatch.chdir(forge.checkout_for_sync())
    ex = Executor("owner/repo")
    return ex.run(plan), ex


@pytest.fixture
def squashed_stack(forge):
    """#1 (a -> main) introduced a line; #2 (b -> a) edited that very line.
    main then gained another commit, and #1 was squash-merged."""
    forge.checkout("a", "main")
    forge.commit("f.txt", "line1\na-line\n", "[TOOL-1] add a-line")
    a_head = forge.commit("a.txt", "a\n", "[TOOL-1] add a.txt")
    forge.checkout("b", "a")
    b_head = forge.commit("f.txt", "line1\na-line edited\n", "[TOOL-2] edit a-line")
    forge.checkout("main")
    other = forge.commit("other.txt", "other\n", "[TOOL-9] unrelated work on main")
    forge.git("merge", "--quiet", "--squash", "a")
    forge.git("commit", "--quiet", "-m", "[TOOL-1] A (#1)")
    forge.push("main", "a", "b")
    # GitHub keeps the merged pull request's head as refs/pull/1/head; the
    # branch itself is deleted on merge.
    _git("update-ref", "refs/pull/1/head", a_head, cwd=forge.origin)
    forge.git("push", "--quiet", "origin", "--delete", "a")
    upper = PullRequest(2, "a", "b", "[TOOL-2] B")
    forge.open_prs(upper)
    return {"a_head": a_head, "b_head": b_head, "other": other, "upper": upper}


class TestSquashMerge:
    # Verifies: REQ-o00080-A+B+D
    def test_REQ_o00080_B_upper_branch_takes_main_without_the_merged_work_again(
        self, forge, squashed_stack, monkeypatch
    ):
        # A plain merge of main into b conflicts: the squash commit is unrelated
        # to the commits it replaced.
        probe = forge.checkout_for_sync()
        _git("checkout", "--quiet", "b", cwd=probe)
        plain = subprocess.run(
            ["git", "merge", "--no-edit", "origin/main"], cwd=probe, capture_output=True
        )
        assert plain.returncode != 0

        plan = plan_merged(
            PullRequest(1, "main", "a"), squashed_stack["a_head"], [squashed_stack["upper"]]
        )
        status, _ = _sync(forge, monkeypatch, plan)

        assert status == 0
        assert ["pr", "edit", "2", "--repo", "owner/repo", "--base", "main"] in forge.gh_calls()
        assert forge.origin_show("b", "f.txt") == "line1\na-line edited"
        assert forge.is_ancestor(squashed_stack["other"], "refs/heads/b")
        diff = _git("diff", "--name-only", "refs/heads/main", "refs/heads/b", cwd=forge.origin)
        assert diff == "f.txt"
        patch = _git("diff", "refs/heads/main", "refs/heads/b", cwd=forge.origin)
        changed = [
            ln for ln in patch.splitlines() if ln[:1] in "+-" and not ln.startswith(("+++", "---"))
        ]
        assert changed == ["-a-line", "+a-line edited"]

    # Verifies: REQ-o00080-D
    def test_REQ_o00080_D_previous_head_is_kept(self, forge, squashed_stack, monkeypatch):
        plan = plan_merged(
            PullRequest(1, "main", "a"), squashed_stack["a_head"], [squashed_stack["upper"]]
        )
        _sync(forge, monkeypatch, plan)
        new_head = forge.origin_sha("b")
        assert new_head != squashed_stack["b_head"]
        assert forge.is_ancestor(squashed_stack["b_head"], new_head)
        # The commit added carries the pull request's ticket, as the commit
        # message check expects.
        subject = _git("log", "-1", "--format=%s", new_head, cwd=forge.origin)
        assert subject.startswith("[TOOL-2] ")


class TestPushCascade:
    # Verifies: REQ-o00080-C+D
    def test_REQ_o00080_C_push_to_bottom_reaches_every_branch_above(self, forge, monkeypatch):
        forge.checkout("a", "main")
        forge.commit("a.txt", "a\n", "a")
        forge.checkout("b", "a")
        forge.commit("b.txt", "b\n", "b")
        forge.checkout("c", "b")
        forge.commit("c.txt", "c\n", "c")
        forge.checkout("d", "c")
        forge.commit("d.txt", "d\n", "d")
        forge.checkout("a")
        fix = forge.commit("a.txt", "a fixed\n", "review fix")
        forge.push("a", "b", "c", "d")
        before = {br: forge.origin_sha(br) for br in "bcd"}
        prs = forge.open_prs(
            PullRequest(2, "a", "b"), PullRequest(3, "b", "c"), PullRequest(4, "c", "d")
        )

        status, _ = _sync(forge, monkeypatch, plan_pushed("a", prs))

        assert status == 0
        for br in "bcd":
            assert forge.is_ancestor(fix, f"refs/heads/{br}"), br
            assert forge.is_ancestor(before[br], f"refs/heads/{br}"), br
            assert forge.origin_show(br, "a.txt") == "a fixed"

    # Verifies: REQ-o00080-C
    def test_REQ_o00080_C_already_up_to_date_pushes_nothing(self, forge, monkeypatch):
        forge.checkout("a", "main")
        forge.commit("a.txt", "a\n", "a")
        forge.checkout("b", "a")
        forge.commit("b.txt", "b\n", "b")
        forge.push("a", "b")
        before = forge.origin_sha("b")
        prs = forge.open_prs(PullRequest(2, "a", "b"))

        status, ex = _sync(forge, monkeypatch, plan_pushed("a", prs))

        assert status == 0
        assert forge.origin_sha("b") == before
        assert _git("rev-parse", "b", cwd=Path.cwd()) == before  # no merge commit made
        assert "  already up to date" in ex.log


class TestConflict:
    @pytest.fixture
    def conflicting(self, forge):
        forge.checkout("a", "main")
        forge.commit("f.txt", "line1\nfrom a\n", "a")
        forge.checkout("b", "a")
        forge.commit("f.txt", "line1\nfrom b\n", "b")
        forge.checkout("c", "b")
        forge.commit("c.txt", "c\n", "c")
        forge.checkout("a")
        forge.commit("f.txt", "line1\nfrom a, revised\n", "a revised")
        forge.push("a", "b", "c")
        prs = forge.open_prs(PullRequest(2, "a", "b"), PullRequest(3, "b", "c"))
        return plan_pushed("a", prs)

    # Verifies: REQ-o00080-E
    def test_REQ_o00080_E_conflict_leaves_stack_unchanged_and_reports_once(
        self, forge, conflicting, monkeypatch
    ):
        before = {br: forge.origin_sha(br) for br in "abc"}

        status, _ = _sync(forge, monkeypatch, conflicting)

        assert status == 1
        assert {br: forge.origin_sha(br) for br in "abc"} == before
        (comment,) = forge.comments(2)
        marker = CONFLICT_MARKER.format(base=before["a"][:12], head=before["b"][:12])
        assert comment.startswith(marker)
        assert "`f.txt`" in comment
        assert forge.comments(3) == []

        status, _ = _sync(forge, monkeypatch, conflicting)

        assert status == 1
        assert len(forge.comments(2)) == 1
        assert {br: forge.origin_sha(br) for br in "abc"} == before
