# GIT INTEGRATION

## Git Root Auto-Detection

elspais automatically detects the git repository root and operates
from there, so it works identically from any subdirectory.

A git worktree is a working tree like any other: its own root is the
repository root, and a relative associate path (e.g. `../sibling`)
resolves against it, not against the clone the worktree was made from.

Use `-v` to see the root and where each associate path resolved:

  $ elspais -v checks
  Working from repository root: /home/dev/worktrees/feature-x
  Associate sibling: '../sibling' resolved against /home/dev/worktrees/feature-x -> /home/dev/worktrees/sibling

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

The header's edit controls each name the operation they perform:

  Save         Save edits to disk. Writes only the files your edits change.
               A file it writes is written whole, in canonical form; where
               that changed a part you did not edit, the save lists it.
  Checkpoint   git commit saved edits.
  Share        git push the commits. Drag the handle to the right, or focus
               it and hold Enter. A plain click shows how and pushes nothing.

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
be available. Where it comes from depends on who the server is serving,
which is decided by `ELSPAIS_PROXY_SECRET` (the `commands` topic's viewer
section describes the proxied-identity headers, and the `config` topic lists
the variable):

- A server started **with** a proxy secret is answering for whoever the
  proxy names. The credential is the one the request carried as
  `X-Elspais-Git-Token`, believed only when the request also carries the
  secret. There is no fallback: what the machine holds of its own belongs to
  nobody who asked, so a request without a credential is refused rather than
  attributed to the machine.
- A server started **without** one is its operator's own viewer. It uses
  `GH_TOKEN`, else `GITHUB_TOKEN` from its environment, else `gh auth token`
  if the GitHub CLI is installed and signed in.

With no credential the request is refused naming what to supply. A
credential that arrives with a request serves only the operation it arrived
for -- a push, a fetch or a pull request -- and is handed to that one git
process on its own environment, which the operating system shows to the
owning account alone. It is never put on a command line, and never written
to the repository's configuration, to the environment the server was started
from, or to any file. Only an `https` remote is given one: an `ssh` remote
authenticates by key, and a plaintext remote would put the credential on the
wire.

### Pull is fast-forward only

`/api/git/pull` fetches and fast-forwards the current branch from its
remote-tracking ref. Where a fast-forward is not possible it changes
nothing, says so, and tells you to push the branch and finish the work in a
local checkout: elspais does not rebase, merge or resolve conflicts.

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
