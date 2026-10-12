# Stacked pull requests and the merge queue

A change too large to review comfortably is split into a **stack**. Each pull
request is based on the branch of the one below it, so each part can be
reviewed, merged or reverted on its own:

```text
main  <-  #A (base: main)  <-  #B (base: A's branch)  <-  #C (base: B's branch)
```

Requirements: REQ-o00066-I/J (CI on pull requests into `main`), L (stacked
pull requests are supported) and M (the merge queue).

## What CI does for a stack

- **Every pull request gets CI, whatever branch it targets.** `ci.yml` and
  `pr-validation.yml` trigger on every pull request, so #B and #C are tested
  and validated like #A. Each one's diff, and its path-filtered tiers (stress,
  browser), cover that pull request's own changes relative to the branch below
  it.
- **The merge queue tests what will actually land.** Both workflows also run on
  `merge_group`, so a merge queue on `main` can be turned on (see
  [Repository settings](#repository-settings)). A queue candidate gets the
  checks a pull request into `main` gets, except that the stress and browser
  tiers always run there instead of only when their paths changed. The queue
  is the last gate before `main`. The title and commit-message checks have
  nothing to read in the queue, so they pass there as not applicable. They
  already ran on the pull request.

## When the pull request below merges

The repository deletes a branch when its pull request merges, and GitHub then
retargets each pull request based on that branch to the branch it merged into.
Nothing more is usually needed.

**Usually: merge it as it is.** CI on a stacked pull request tests it combined
with the one below. When the one below is squash-merged, `main` ends up with
that pull request's final content, so merging the upper pull request gives
exactly the content its CI already tested. Retargeting re-runs only the title
check, not the tests. The pull request's diff on GitHub then also shows the
merged pull request's changes, because git no longer sees them as merged; that
is only how the diff is drawn.

That holds when the upper branch already contains the lower pull request's
last commit. If the lower branch gained a commit the upper one never merged,
bring it up to date as below so CI tests the combination.

**Sometimes: a conflict after a squash merge.** A squash commit is unrelated to
the commits it replaced, so git meets the merged work twice. It reports a
conflict wherever the upper pull request edited lines the lower one introduced,
even though nothing really conflicts. Record the merged pull request's last
commit as already merged, then bring `main` in:

```bash
git fetch origin main refs/pull/<lower-PR-number>/head
git checkout -B stack-repair origin/main
git merge -s ours --no-edit FETCH_HEAD      # the lower PR's last commit, as merged
git checkout <upper-branch>
git merge --no-ff stack-repair               # sees only what main gained beyond it
git push
```

The merge leaves the upper pull request's files as they were. It is a new
commit, so CI runs again. Do the same, one level at a time, for any pull
request stacked above it that then conflicts.

## Working with a stack

1. **Open each pull request against the branch below it.** For example,
   `gh pr create --base <lower-branch>`. Give each one its own `[TEAM-NNN]`
   title; every title becomes a squash commit on `main`.
2. **Fix review comments on the branch that owns the code**, and push. Then
   merge that branch into each branch above it, bottom-up, and push each one,
   so every pull request above is tested with the fix.
3. **Merge from the bottom up**, through the merge queue if it is enabled.
4. **To bring a whole stack up to date with `main`**, merge `main` into the
   bottom branch, then each branch into the one above it, and push each.

Only ever add merge commits to a branch in a stack. Never rebase or
force-push one: a reviewer's or contributor's checkout of it would no longer
be valid. The pre-push hook refuses a branch that is behind `origin/main`, so
update the bottom branch first (step 4).

## Repository settings

These are set by a repository administrator, not by a pull request:

- **Merge queue on `main`**: *Settings → Rules → Rulesets* (or branch
  protection), *Require merge queue*. Use the same required status checks as
  for pull requests. Every check in `ci.yml` and `pr-validation.yml` reports in
  the queue, so any of them can be required.
- **Automatically delete head branches**: on today. GitHub then retargets the
  pull requests stacked on a merged one itself. With it off, retarget each by
  hand (`gh pr edit <number> --base main`).
