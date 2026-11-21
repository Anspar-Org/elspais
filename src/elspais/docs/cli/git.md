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

`elspais changed` answers "which code and test files must someone review
because a requirement changed". It reports each requirement and each
*Assertion* whose content differs from the comparison base, and for each
change lists every code and test file citing it.

  $ elspais changed                        # Changes and the files to review
  $ elspais changed --format json          # Output as JSON
  $ elspais changed --base-branch develop  # Compare to a different branch
  $ elspais changed --write-record         # Write the awaiting files to the record
  $ elspais changed --review src/auth.py   # Record your review of a file
  $ elspais changed --review tests/test_auth.py --change REQ-d00012-B

## Command Options

  `--base-branch BRANCH`  Branch to compare against (default: main)
  `--format {text,json}`  Output format (default: text)
  `-o, --output PATH`     Write output to file instead of stdout
  `--write-record`        Write the files awaiting review into the record
  `--review PATH ...`     Record your review of these files (repo-relative)
  `--change ID ...`       With `--review`, record it only for these changes

## What 'Changed' Detects

- **Comparison base** - The commit where HEAD meets `origin/BRANCH`, or the
  local `BRANCH` where no remote copy exists. The report names the base ref
  and the commit. The working tree is compared, uncommitted edits included.
- **Changed Assertion** - Its text differs from its text at the base, or it
  is absent at the base.
- **Changed requirement** - The set of its *Assertion* texts differs from the
  set at the base. An edit to a title or a rationale is not a change.

Where the base cannot be read, the report says the changes are unverifiable
and the command exits 1.

## Files to Review

For each change the report lists each code and test file citing it, with the
line of each citation. A citation of an *Assertion* is listed under that
*Assertion*'s change; a citation of the whole requirement is listed under the
requirement's change. Each file is marked `reviewed` (by whom, and when) or
`awaiting review`. Each change also names its expected reviewer: the author
of the requirement's newest changelog entry. A file of another federation
member is named by that member's namespace and its path there, as
`NAMESPACE:path`.

## The Review Record

The record is `.elspais/changes.md`, committed with the work it describes. It
holds two tables:

- **Awaiting review** - Each file citing a change that nobody has reviewed.
- **Reviewed** - Each recorded review: the change, the digest of its content,
  the file, the digest of the file, the reviewer and the date.

`--write-record` writes the files awaiting review into the record and records
no review. `--review PATH` records your review of every awaiting consequence of
each file, under your git identity (`user.name` and `user.email`), the one
the commit of the record carries; `--change ID` narrows it to the named
changes. PATH is the name the report gives the file, or its absolute path.
A file awaiting no review is refused. A later edit to the file, or to
the changed requirement or *Assertion*, makes the file await review again.
The record names only what it held when it was last written, so the report
says when a file awaiting review is missing from it; run `--write-record`
before committing so the record carries every file nobody has reviewed.

The record keeps listing a file as awaiting review, and the report shows it,
until someone reviews it, even after its change has merged and the base has
moved past it. A review is a person's act: `elspais fix` never touches the
record, and no MCP tool records a review.

## Requirements a Change Touches

`elspais changed` reports spec changes. To ask which requirements a set of
changed files bears on -- code, tests and journeys as well as spec files --
hand the paths to `elspais files`:

  $ git diff --name-only main | xargs elspais files

Each file is answered with the requirements it defines, implements,
verifies or validates (see `elspais docs commands`, section `files`).

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
               that changed a part you did not edit, the save lists it. A
               requirement you did not edit keeps its hash: the save does
               not mark a defined term in its assertions (`elspais fix`
               does that, on purpose).
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
4. $ elspais changed  # List the code and test files to review
5. $ elspais changed --review PATH  # Record each review
6. $ elspais changed --write-record  # Name the files still awaiting review
7. Commit, `.elspais/changes.md` included, with a message referencing requirement IDs
