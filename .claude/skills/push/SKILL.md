---
name: push
description: Push the current branch after earning the pre-push hook's unit and e2e verdicts outside the push, so the push itself completes in seconds instead of running a multi-minute test stage while git holds the remote connection open
---

# Push with the unit and e2e verdicts earned first

The pre-push hook re-runs the e2e tier unless `.results/.test-cache-e2e`
holds a verdict for the exact committed tree and environment. Running that
stage inside `git push` holds the git connection open for several minutes —
the remote closes idle connections before it finishes, and in agent
sessions long foreground runs are liable to be killed. Earn the verdict
first; the push then hits the cache.

## Steps

1. Confirm the tree is committed and clean (`git status`). The verdict is
   keyed on `git write-tree`, so uncommitted changes make it describe a
   tree that is not the one being pushed.
2. Run `.githooks/unit-verdict`, backgrounded, and wait for it. Where a
   full commit already verified the tip's tree it returns at once; after a
   checkpoint commit (`ELSPAIS_CHECKPOINT=1`) it runs the unit tier. Then
   run `.githooks/e2e-verdict` the same way. Never run the two at once:
   two pytest processes in one worktree corrupt each other's coverage.
   `.githooks/e2e-verdict` waits several minutes too (several
   minutes). It prefers this tree's `.venv/bin` on PATH, runs the e2e tier,
   and records the verdict only from a real run. If the run is killed
   externally, no verdict is written — run it again.
3. On PASS of both, run `git push`. The hook reports both verdicts as
   cached and completes quickly.
4. Verify the transfer actually happened: `git fetch origin <branch>`, then
   `git log origin/<branch>..HEAD --oneline` must print nothing. A push
   pipeline's exit code is easily masked by `| tail`; the remote ref is the
   evidence.
5. On FAIL, the failing tests are the work. Fix them; do not bypass with
   `--no-verify`, and never write the cache file by hand — a verdict is
   earned by a run, not asserted. `ELSPAIS_UNIT_FORCE=1 .githooks/unit-verdict`
   and `ELSPAIS_E2E_FORCE=1 .githooks/e2e-verdict` re-run a recorded verdict.
6. A refusal is not a FAIL. Where pytest's interpreter cannot reach this
   tree's elspais, the script says so and stops without running the tier
   and without writing a verdict. Build the worktree's venv as the message
   says, then run it again. The tier cannot report on this tree from
   another installation, so there is nothing to bypass here.
