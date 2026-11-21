# Stacked pull requests and the merge queue

The maintainers and their agents keep one ordered **stack** of open pull
requests in this repository. The first slot builds on `main`. Each later slot
builds on the branch of the slot below it:

```text
main  <-  #A (base: main)  <-  #B (base: A's branch)  <-  #C (base: B's branch)
```

Each pull request holds its own work as one commit, and it lands on `main` as
a merge commit. Its commit therefore keeps its identity on `main`, and git
alone shows whether a branch has merged: `git branch --merged origin/main`
lists it. The first-parent history of `main` (`git log --first-parent main`)
shows one merge commit for each pull request, and the message of that merge
commit is the pull request's title and description.

A pull request from anyone else, or from a dependency bot, does not take a
slot. It targets `main` and lands through the merge queue in the same way.

Requirements: REQ-o00066-I/J (CI on pull requests into `main`), L (stacked
pull requests are supported) and M (the merge queue).

## The rules of the stack

- **The stack is at most three pull requests deep.** A fourth waits until the
  bottom one merges.
- **A pull request takes the next slot only.** Its base is the branch of the
  top slot, or `main` when the stack is empty. A session hook refuses to open,
  or mark ready, a pull request whose base is anything else, whose base is not
  yet merged into its branch, or that would make the stack too deep. The
  refusal states the rule and what to do.
- **A branch takes a slot only when it is verified locally** on every tier CI
  runs: `make test-all` passes on the tree the pull request will hold.
- **After a branch takes its slot, its history only grows.** A review fix is a
  new commit. Nobody rebases, amends or force-pushes a branch in the stack: a
  reviewer's or contributor's checkout of it would no longer be valid, and the
  commits of the pull request must stay the ones that land on `main`.

## Taking a slot

1. **Finish and verify the work.** Commit as often as useful while the branch
   is private. Run `make test-all` and fix what fails.
2. **Bring in the slot below.** Merge the branch of the top slot (or
   `origin/main` when the stack is empty) into the work branch, and run the
   tiers again if the merge changed anything.
3. **Squash the work to one commit**, with the pull request title as its
   subject and the requirement references in its body:

   ```bash
   git fetch origin
   git merge --no-ff origin/<top-slot-branch>    # or origin/main
   git reset --soft origin/<top-slot-branch>      # the same base
   git commit                                     # subject: the PR title
   ```

   The squash does not change the tree, so the verification in step 1 still
   applies. This is the one planned rewrite of a branch. A branch that was
   pushed before it took its slot is pushed under a new name, so no pushed
   branch is rewritten.
4. **Push and open the pull request** against the slot below:
   `gh pr create --base <top-slot-branch>` (or `--base main`). Its title is the
   subject of the commit, and its `[TEAM-NNN]` reference is required.

## What CI does for a stack

- **Every pull request gets CI, whatever branch it targets.** `ci.yml` and
  `pr-validation.yml` trigger on every pull request, so #B and #C are tested
  and validated like #A. Each pull request's diff, and its path-filtered tiers
  (stress, browser), cover its own changes relative to the branch below it.
- **The merge queue tests what will actually land.** Both workflows also run on
  `merge_group`. A queue candidate gets the checks a pull request into `main`
  gets, except that the stress and browser tiers always run there instead of
  only when their paths changed. The queue tests the exact result of each merge
  before `main` changes, so the ruleset does not also require a branch to be up
  to date with `main`. The title and commit-message checks have nothing to read
  in the queue, so they pass there as not applicable. They already ran on the
  pull request.

In the normal case a pull request runs CI once as a pull request and once in
the queue.

## Review fixes

Fix a review comment on the branch that owns the code, as a new commit, and
push it. Then merge that branch into each branch above it, bottom-up, and push
each one, so every pull request above is tested with the fix. Only ever add
commits, including merge commits, to a branch in the stack.

## Landing

Merge from the bottom up. The bottom pull request enters the merge queue
(`gh pr merge <number> --merge`). The queue lands it as a merge commit whose
message is the pull request's title and description.

The repository then deletes the merged branch, and GitHub retargets the pull
request above it to `main`. That branch already contains every commit that
merged, so git sees nothing twice: there is no false conflict and nothing to
repair. Its diff on GitHub shows only its own work. Retargeting runs the
title check again, not the tests. The next pull request in the stack then
enters the queue in the same way.

The pre-push hook refuses a branch that is behind `origin/main`. Before the
next push to a branch whose base has merged, merge `origin/main` into it; to
bring a whole stack up to date, merge `origin/main` into the bottom branch,
then each branch into the one above it, and push each.

## Repository settings

These are set by a repository administrator, not by a pull request. The flow
above holds once they are in place:

- **Merge method**: merge commits only. The repository allows neither squash
  nor rebase merges, and the `main` ruleset permits only the merge method.
- **Merge commit message**: the pull request title and description
  (*Default commit message*: *Pull request title and description*).
- **Merge queue on `main`**: *Settings -> Rules -> Rulesets*, *Require merge
  queue*, merge method *Merge commit*. It uses the same required status checks
  as pull requests. Every check in `ci.yml` and `pr-validation.yml` reports in
  the queue, so any of them can be required.
- **Up-to-date branches**: not required. The merge queue gives the same
  protection without a CI run on every open pull request after each merge.
- **Automatically delete head branches**: on. GitHub then retargets the pull
  requests stacked on a merged one itself.
