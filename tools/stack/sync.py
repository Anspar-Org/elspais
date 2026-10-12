"""Keep a stack of pull requests consistent when one merges or gains commits.

A stack is a chain of pull requests, each based on the branch of the one below
it. Two events need repair (REQ-o00066-L):

* ``merged``: a pull request merged. Each open pull request based on its branch
  is retargeted to the branch it merged into. That is all, when the pull
  request already holds the merged one's last commit and merges cleanly into
  its new base: its CI ran on that same content, so the result still applies
  and it can be merged at once. Otherwise it is brought up to date with its new
  base, and everything stacked above it after it.
* ``pushed``: a branch gained commits. Each open pull request based on it, and
  each one stacked above those, is brought up to date with the branch below.

Bringing a branch up to date is always a merge commit added on top. This
repository squash-merges, and a squash commit is unrelated to the commits it
replaced, so before bringing the new base in, the merged pull request's last
commit is recorded as already merged (``git merge -s ours`` on a temporary
branch from the base). The real merge then sees only what the base gained beyond
the merged pull request, and cannot conflict with that pull request's own
changes appearing a second time.

A merge that conflicts is aborted: that branch and everything above it are left
untouched, and the conflict is reported on the pull request once. Pull
requests whose branch lives in another repository are never changed.

The plan is a pure function of the event and the open pull requests
(``plan_merged``, ``plan_pushed``), so it is tested without git or GitHub; the
``Executor`` carries a plan out with ``git`` and the ``gh`` CLI.

Usage (from .github/workflows/stack-sync.yml):

    python -m tools.stack.sync merged --pr N --base main --head feature-a --head-sha SHA
    python -m tools.stack.sync pushed --branch feature-a
    (add --dry-run to print the plan without changing anything)
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field

TICKET = re.compile(r"\[[A-Z]{2,10}-[0-9]+\]")
CONFLICT_MARKER = "<!-- stack-sync:conflict:{base}:{head} -->"


@dataclass(frozen=True)
class PullRequest:
    number: int
    base: str
    head: str
    title: str = ""
    cross_repository: bool = False

    @property
    def ticket(self) -> str:
        m = TICKET.search(self.title)
        return m.group(0) if m else ""


@dataclass(frozen=True)
class Retarget:
    pr: PullRequest
    new_base: str


@dataclass(frozen=True)
class Update:
    """Bring ``pr``'s branch up to date with ``base``.

    ``merged_head`` is set on the first update after a merge: the merged pull
    request's last commit, recorded as merged before ``base`` is brought in.
    ``parent`` is the update this one stacks on: if that one cannot be made,
    neither can this one.
    """

    pr: PullRequest
    base: str
    merged_head: str | None = None
    merged_pr: int | None = None
    parent: int | None = None


@dataclass
class Plan:
    retargets: list[Retarget] = field(default_factory=list)
    updates: list[Update] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def _children(branch: str, open_prs: list[PullRequest]) -> list[PullRequest]:
    return sorted((p for p in open_prs if p.base == branch), key=lambda p: p.number)


def _stack_above(
    branch: str, open_prs: list[PullRequest], plan: Plan, parent: int | None, seen: set[int]
) -> None:
    """Depth-first, lowest pull request first: each branch is updated before
    anything stacked on it, so the merge into a child always brings the parent's
    new commits."""
    for child in _children(branch, open_prs):
        if child.number in seen:
            continue  # a cycle in base/head names; GitHub forbids it, but never loop
        seen.add(child.number)
        if child.cross_repository:
            plan.skipped.append(f"#{child.number}: branch lives in another repository")
            continue
        plan.updates.append(Update(child, branch, parent=parent))
        _stack_above(child.head, open_prs, plan, child.number, seen)


def plan_merged(merged: PullRequest, merged_head_sha: str, open_prs: list[PullRequest]) -> Plan:
    plan = Plan()
    seen: set[int] = set()
    for child in _children(merged.head, open_prs):
        seen.add(child.number)
        if child.cross_repository:
            plan.skipped.append(f"#{child.number}: branch lives in another repository")
            continue
        plan.retargets.append(Retarget(child, merged.base))
        retargeted = PullRequest(child.number, merged.base, child.head, child.title)
        plan.updates.append(
            Update(retargeted, merged.base, merged_head=merged_head_sha, merged_pr=merged.number)
        )
        _stack_above(child.head, open_prs, plan, child.number, seen)
    return plan


def plan_pushed(branch: str, open_prs: list[PullRequest]) -> Plan:
    plan = Plan()
    _stack_above(branch, open_prs, plan, None, set())
    return plan


# -- execution ---------------------------------------------------------------


class Executor:
    """Carries a plan out with git (in a full clone) and the gh CLI."""

    def __init__(self, repo: str, dry_run: bool = False) -> None:
        self.repo = repo
        self.dry_run = dry_run
        self.log: list[str] = []
        self.updated: set[str] = set()  # branches this run moved locally

    def _run(self, *cmd: str, check: bool = True, input: str | None = None) -> str:
        proc = subprocess.run(cmd, capture_output=True, text=True, input=input)
        if check and proc.returncode != 0:
            raise RuntimeError(f"{' '.join(cmd)} failed: {proc.stderr.strip()}")
        return proc.stdout

    def say(self, line: str) -> None:
        self.log.append(line)
        print(line, flush=True)

    def open_prs(self) -> list[PullRequest]:
        out = self._run(
            "gh",
            "pr",
            "list",
            "--repo",
            self.repo,
            "--state",
            "open",
            "--limit",
            "500",
            "--json",
            "number,baseRefName,headRefName,title,isCrossRepository",
        )
        return [
            PullRequest(
                p["number"], p["baseRefName"], p["headRefName"], p["title"], p["isCrossRepository"]
            )
            for p in json.loads(out)
        ]

    def retargeted_by_github(
        self, merged: PullRequest, merged_head_sha: str, open_prs: list[PullRequest]
    ) -> list[PullRequest]:
        """The open pull requests GitHub itself already moved off the merged
        branch. When a repository deletes merged branches, GitHub retargets the
        pull requests based on one to its base before this run lists them, so
        they no longer name the merged branch. One that targets the merged pull
        request's base and holds its last commit was stacked on it; each is
        returned based on the merged branch again, so it is planned as a pull
        request stacked there."""
        self._run(
            "git", "fetch", "--quiet", "origin", f"refs/pull/{merged.number}/head", check=False
        )
        known = subprocess.run(
            ["git", "cat-file", "-e", f"{merged_head_sha}^{{commit}}"], capture_output=True
        )
        if known.returncode != 0:
            self.say(
                f"cannot read #{merged.number}'s last commit {merged_head_sha[:12]}; pull requests"
                f" GitHub already retargeted to {merged.base} are not checked"
            )
            return []
        found = []
        for p in open_prs:
            if p.base != merged.base or p.cross_repository or p.head == merged.head:
                continue
            holds = subprocess.run(
                ["git", "merge-base", "--is-ancestor", merged_head_sha, f"origin/{p.head}"],
                capture_output=True,
            )
            if holds.returncode == 0:
                found.append(PullRequest(p.number, merged.head, p.head, p.title))
        return found

    def run(self, plan: Plan) -> int:
        for line in plan.skipped:
            self.say(f"skip {line}")
        for r in plan.retargets:
            self.say(f"retarget #{r.pr.number}: {r.pr.base} -> {r.new_base}")
            if not self.dry_run:
                self._run(
                    "gh", "pr", "edit", str(r.pr.number), "--repo", self.repo, "--base", r.new_base
                )
        if not self.dry_run:
            self._run("git", "fetch", "--quiet", "origin")
        blocked: set[int] = set()
        kept: set[int] = set()
        conflicts = 0
        for u in plan.updates:
            if u.parent in blocked:
                blocked.add(u.pr.number)
                self.say(f"#{u.pr.number}: left unchanged; #{u.parent} below it was not updated")
                continue
            if u.parent in kept:
                kept.add(u.pr.number)
                self.say(f"#{u.pr.number}: left as is; #{u.parent} below it did not change")
                continue
            if u.merged_head and self._still_tested(u):
                kept.add(u.pr.number)
                self.say(
                    f"#{u.pr.number} ({u.pr.head}) holds #{u.merged_pr}'s last commit and merges"
                    f" cleanly into {u.base}; left as is, so its CI result still applies"
                )
                continue
            self.say(f"update #{u.pr.number} ({u.pr.head}) with {u.base}")
            if self.dry_run:
                continue
            outcome = self._update(u)
            self.say(f"  {outcome}")
            if outcome.startswith(("conflict", "refused")):
                conflicts += 1
                blocked.add(u.pr.number)
        return 1 if conflicts else 0

    def _still_tested(self, u: Update) -> bool:
        """Whether a pull request retargeted after a merge can be merged as it
        stands: its branch holds the merged pull request's last commit, so its
        CI ran on the content that is now in the base, and it merges into the
        base without conflict. A squash merge leaves the base with exactly that
        content, so merging the pull request gives the content its CI tested."""
        if u.merged_pr is not None:
            self._run(
                "git", "fetch", "--quiet", "origin", f"refs/pull/{u.merged_pr}/head", check=False
            )
        head = f"origin/{u.pr.head}"
        holds = subprocess.run(
            ["git", "merge-base", "--is-ancestor", u.merged_head or "", head], capture_output=True
        )
        if holds.returncode != 0:
            return False
        # Exit 0 is a clean merge, 1 a conflict; anything else is an error, and
        # an error is treated as a conflict, so the pull request is updated.
        clean = subprocess.run(
            ["git", "merge-tree", "--write-tree", self._base_ref(u.base), head],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return clean.returncode == 0

    def _base_ref(self, base: str) -> str:
        """The base as this run left it: a branch this run updated is read
        locally (it may carry a merge not yet visible on origin); anything else,
        including a local `main` the checkout created, is read from origin."""
        return base if base in self.updated else f"origin/{base}"

    def _update(self, u: Update) -> str:
        head, ticket = u.pr.head, u.pr.ticket
        prefix = f"{ticket} " if ticket else ""
        base_ref = self._base_ref(u.base)
        self._run("git", "checkout", "--quiet", "-B", head, f"origin/{head}")
        before = self._run("git", "rev-parse", "HEAD").strip()
        incoming = base_ref
        if u.merged_head:
            # Record the merged pull request's last commit as merged, on a
            # temporary branch from the base, so the squash commit and the
            # commits it replaced are not both brought in. The merged branch
            # may already be deleted, so its last commit is fetched by number.
            if u.merged_pr is not None:
                self._run("git", "fetch", "--quiet", "origin", f"refs/pull/{u.merged_pr}/head")
            self._run("git", "checkout", "--quiet", "-B", "stack-sync-base", base_ref)
            self._run(
                "git",
                "merge",
                "--quiet",
                "-s",
                "ours",
                "--no-edit",
                "-m",
                f"{prefix}Record {u.merged_head[:12]} as merged into {u.base} "
                f"(stack sync)\n\nREQ-o00066-L",
                u.merged_head,
            )
            self._run("git", "checkout", "--quiet", head)
            incoming = "stack-sync-base"
        merge = subprocess.run(
            [
                "git",
                "merge",
                "--no-ff",
                "--no-edit",
                "-m",
                f"{prefix}Merge {u.base} into {head} (stack sync)\n\nREQ-o00066-L",
                incoming,
            ],
            capture_output=True,
            text=True,
        )
        if merge.returncode != 0:
            subprocess.run(["git", "merge", "--abort"], capture_output=True)
            self._run("git", "checkout", "--quiet", "-B", head, f"origin/{head}")
            self._report_conflict(u, merge.stdout + merge.stderr)
            return f"conflict merging {u.base}; left unchanged, reported on #{u.pr.number}"
        after = self._run("git", "rev-parse", "HEAD").strip()
        self.updated.add(head)
        if after == before:
            return "already up to date"
        push = subprocess.run(
            ["git", "push", "--quiet", "origin", f"{head}:{head}"], capture_output=True, text=True
        )
        if push.returncode != 0:
            self._run("git", "checkout", "--quiet", "-B", head, f"origin/{head}")
            self.updated.discard(head)
            hint = ""
            if "workflow" in push.stderr.lower():
                hint = (
                    " The merge changes files under .github/workflows/, which the workflow's"
                    " own GITHUB_TOKEN may not push: set a STACK_SYNC_TOKEN secret with"
                    " Contents, Pull requests and Workflows write access"
                    " (docs/stacked-pull-requests.md)."
                )
            return f"refused: push to {head} failed: {push.stderr.strip()}{hint}"
        return f"pushed {after[:12]}"

    def _report_conflict(self, u: Update, detail: str) -> None:
        base_sha = self._run("git", "rev-parse", self._base_ref(u.base)).strip()
        head_sha = self._run("git", "rev-parse", f"origin/{u.pr.head}").strip()
        marker = CONFLICT_MARKER.format(base=base_sha[:12], head=head_sha[:12])
        existing = self._run(
            "gh",
            "pr",
            "view",
            str(u.pr.number),
            "--repo",
            self.repo,
            "--json",
            "comments",
            "--jq",
            ".comments[].body",
        )
        if marker in existing:
            return  # reported once
        files = sorted(
            {
                ln.split("Merge conflict in ", 1)[1].strip()
                for ln in detail.splitlines()
                if "Merge conflict in " in ln
            }
        )
        body = (
            f"{marker}\n**Stack sync could not bring this branch up to date with "
            f"`{u.base}`**: the merge conflicts"
            + (" in " + ", ".join(f"`{f}`" for f in files) if files else "")
            + ". The branch was left unchanged, and so were the pull requests stacked on it.\n\n"
            f"To resolve: `git fetch origin && git checkout {u.pr.head} && "
            f"git merge origin/{u.base}`, fix the conflicts, commit and push. Stack sync "
            "then carries the result up the stack. See docs/stacked-pull-requests.md."
        )
        self._run(
            "gh",
            "pr",
            "comment",
            str(u.pr.number),
            "--repo",
            self.repo,
            "--body-file",
            "-",
            input=body,
        )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="python -m tools.stack.sync",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--repo", required=True, help="owner/name")
    p.add_argument("--dry-run", action="store_true")
    sub = p.add_subparsers(dest="event", required=True)
    m = sub.add_parser("merged")
    m.add_argument("--pr", type=int, required=True)
    m.add_argument("--base", required=True)
    m.add_argument("--head", required=True)
    m.add_argument("--head-sha", required=True)
    s = sub.add_parser("pushed")
    s.add_argument("--branch", required=True)
    args = p.parse_args(argv)

    ex = Executor(args.repo, dry_run=args.dry_run)
    prs = ex.open_prs()
    if args.event == "merged":
        merged = PullRequest(args.pr, args.base, args.head)
        moved = {p.number: p for p in ex.retargeted_by_github(merged, args.head_sha, prs)}
        prs = [moved.get(p.number, p) for p in prs]
        plan = plan_merged(merged, args.head_sha, prs)
    else:
        plan = plan_pushed(args.branch, prs)
    if not plan.retargets and not plan.updates and not plan.skipped:
        print("stack sync: no pull request is stacked on this branch; nothing to do")
        return 0
    return ex.run(plan)


if __name__ == "__main__":
    sys.exit(main())
