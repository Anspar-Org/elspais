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

## What stack sync does

`.github/workflows/stack-sync.yml` runs `tools/stack/sync.py`:

| Event | Repair |
| --- | --- |
| A pull request merges | Each open pull request based on its branch is **retargeted** to the branch it merged into, and **brought up to date** with that branch. Everything stacked above is then brought up to date too. |
| A branch gains commits (a review fix on #A) | Each open pull request based on that branch, and each one stacked above those, **merges the branch below it**, from the bottom up. |

Repairs only ever **add merge commits**. History anyone has reviewed is never
rewritten, and a contributor's checkout of their branch stays valid.

**Squash merges.** This repository squash-merges. A squash commit is unrelated
to the commits it replaced, so a plain `git merge main` into the pull request
above meets the merged work twice. It conflicts with itself wherever the upper
pull request edited lines the lower one introduced. Before bringing `main` in,
stack sync records the merged pull request's last commit as already merged:
`git merge -s ours` on a temporary branch from `main`. The real merge then sees
only what `main` gained beyond it, and the upper pull request's diff shows only
its own changes again.

**Conflicts.** If a merge genuinely conflicts, stack sync aborts it. It leaves
that branch and every branch stacked above it untouched, and comments once on
the pull request with the conflicting files and the commands to resolve it.
After you push the resolution, stack sync carries it up the rest of the stack.

Pull requests from forks are never changed.

To see what stack sync would do without changing anything:

```bash
GH_TOKEN=... python -m tools.stack.sync --repo Anspar-Org/elspais --dry-run pushed --branch my-branch
```

## Working with a stack

1. **Open each pull request against the branch below it.** For example,
   `gh pr create --base <lower-branch>`. Give each one its own `[TEAM-NNN]`
   title; every title becomes a squash commit on `main`.
2. **Fix review comments on the branch that owns the code**, and push. Stack sync
   merges the fix into everything above it.
3. **Merge from the bottom up**, through the merge queue if it is enabled. When
   the bottom pull request merges, the next one is retargeted to `main`
   automatically, and so on.
4. **To bring a whole stack up to date with `main`**, merge `main` into the
   bottom branch and push. Stack sync carries it upward.

The pre-push hook refuses a branch that is behind `origin/main`. In a stack,
update the bottom branch first (step 4). Then pull each upper branch after stack
sync has updated it, before pushing to it.

## Repository settings

These are set by a repository administrator, not by a pull request:

- **Merge queue on `main`**: *Settings → Rules → Rulesets* (or branch
  protection), *Require merge queue*. Use the same required status checks as
  for pull requests. Every check in `ci.yml` and `pr-validation.yml` reports in
  the queue, so any of them can be required.
- **`STACK_SYNC_TOKEN` secret (recommended)**: a fine-grained personal access
  token or a GitHub App token with *Contents*, *Pull requests* and *Workflows*
  read and write access on this repository.
  - GitHub can also refuse a push made with the built-in `GITHUB_TOKEN` when
    it changes files under `.github/workflows/`. In practice a merge whose
    workflow changes already exist elsewhere in the repository has been
    accepted. If a push is refused, the run fails, naming the branch and this
    setting, and leaves that branch and the pull requests above it unchanged.
  - A push made with the workflow's built-in `GITHUB_TOKEN` starts no other
    workflow, so without this secret the pull requests stack sync updates are
    not re-tested until their author's next push.
  - With the secret, stack sync's merges trigger CI like anyone else's.
- **Automatically delete head branches (optional)**: GitHub then also
  retargets dependent pull requests itself. Stack sync does this either way and
  does not depend on the setting.
