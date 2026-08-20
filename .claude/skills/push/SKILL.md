---
name: push
description: Push the current branch after earning the pre-push hook's e2e verdict outside the push, so the push itself completes in seconds instead of running a multi-minute test stage while git holds the remote connection open
---

# Push with the e2e verdict earned first

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
2. Run `.githooks/e2e-verdict`, backgrounded, and wait for it (several
   minutes). It prefers this tree's `.venv/bin` on PATH, runs the e2e tier,
   and records the verdict only from a real run. If the run is killed
   externally, no verdict is written — run it again.
3. On PASS, run `git push`. The hook reports "E2E tests cached" and
   completes quickly.
4. Verify the transfer actually happened: `git fetch origin <branch>`, then
   `git log origin/<branch>..HEAD --oneline` must print nothing. A push
   pipeline's exit code is easily masked by `| tail`; the remote ref is the
   evidence.
5. On FAIL, the failing tests are the work. Fix them; do not bypass with
   `--no-verify`, and never write the cache file by hand — a verdict is
   earned by a run, not asserted. `ELSPAIS_E2E_FORCE=1 .githooks/e2e-verdict`
   re-runs a recorded verdict.
