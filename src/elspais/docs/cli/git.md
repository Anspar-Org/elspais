# GIT INTEGRATION

## Git Root Auto-Detection

elspais automatically detects the git repository root and operates
from there, so it works identically from any subdirectory.

For **git worktrees**, elspais also detects the canonical (main)
repository root. This ensures cross-repo paths (e.g. `../sibling`)
resolve from the main repo, not the worktree location.

Use `-v` to see detected roots:

  $ elspais -v checks
  Working from repository root: /home/dev/worktrees/feature-x
  Canonical root (main repo): /home/dev/my-project

## Detecting Changes

  $ elspais changed                    # Show all spec changes
  $ elspais changed --format json     # Output as JSON
  $ elspais changed -a                # Include non-spec files
  $ elspais changed --base-branch develop  # Compare to different branch

## Command Options

  `--base-branch BRANCH`  Base branch for comparison (default: main)
  `--format {text,json}`  Output format (default: text)
  `-a, --all`             Include all changed files (not just spec)

## What 'Changed' Detects

  **Uncommitted** - Modified/untracked spec files
  **Hash mismatch** - Content changed but hash not updated
  **Moved** - Requirement relocated to different file
  **vs Main** - Changes compared to main/master branch

## In Trace View

The interactive viewer (`elspais viewer`) shows:

  **◆** Changed vs main branch (diamond indicator)
  Filter buttons: `[Uncommitted]` `[Changed vs Main]`

## Git From the Viewer

The viewer's edit mode drives the repository through `/api/git/*`: status,
branch, checkout, checkpoint commit, push, pull and pull request.

  POST /api/git/push   Push the current branch to origin
  POST /api/git/pull   Fast-forward the current branch
  POST /api/git/pr     Open a pull request proposing the pushed branch

`/api/git/pr` takes `{title, body, base?, repo?}`. The base defaults to the
branch the remote points its HEAD at, else `main`. The branch must already
be on the remote: a branch with commits the remote does not have, a detached
HEAD, and a remote that is not GitHub's are each refused naming the
condition. Where an open pull request already proposes the branch, that pull
request is reported rather than the request refused.

### Credentials

A pull request is attributed to whoever's credential opened it, so one must
be available. In order of precedence:

1. `X-Elspais-Git-Token` on the request, believed only when the request also
   carries the proxy secret (see the `concurrency` topic's note on proxied
   identity) -- this is how a server serving many people acts as the person
   who asked.
2. `GH_TOKEN` in the server's environment.
3. `GITHUB_TOKEN` in the server's environment.
4. `gh auth token`, if the GitHub CLI is installed and signed in.

With none of these the request is refused naming what to supply. A
credential that arrives with a request serves only the operation it arrived
for -- a push, a fetch or a pull request -- and is carried on that one
command. It is never written to the repository's configuration, to the
environment the server was started from, or to any file.

### Pull is fast-forward only

`/api/git/pull` fetches and fast-forwards. Where a fast-forward is not
possible, it says so and tells you to push the branch and finish the work in
a local checkout: elspais does not rebase, merge or resolve conflicts.

## Pre-Commit Hook Example

```sh
#!/bin/sh
# .git/hooks/pre-commit
elspais checks || exit 1
```

## Workflow

1. Edit requirements
2. $ elspais checks  # Check format
3. $ elspais fix  # Fix hashes and formatting
4. $ elspais changed  # Review what changed
5. Commit with message referencing requirement IDs
