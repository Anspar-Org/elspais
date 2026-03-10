# Viewer Git Sync — Design Document

**Date:** 2026-03-09
**Status:** Approved
**Scope:** Solo-author workflow for committing and pushing spec edits from the viewer

## Problem

The viewer supports inline editing with save-to-disk, but there is no way to commit and push changes without leaving the browser. Users must switch to a terminal for git operations. This creates friction for quick tweaks and risks forgetting to commit saved changes.

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Target workflow | Solo author, quick tweaks | Not a collaborative review tool |
| Branching | Current branch by default; require new branch if on main | Protect main from accidental commits |
| Branch naming | User-provided, no auto-generated defaults | Keep it explicit |
| Git feedback | Modal with file list + commit message field | Enough context without slowing down |
| What gets staged | All modified spec files (`spec/**`) | Viewer shows combined state of all spec files |
| Conflict resolution | Out of scope — informational warnings only | Elspais never rebases, merges, or resolves conflicts |

## Design

### 1. Branch Awareness & Guardrails

#### On viewer load (main + dirty spec files)

If the viewer opens on main AND spec files have uncommitted changes, a blocking modal appears:

```text
+--------------------------------------+
| Local spec changes detected on main. |
| Enter a branch name to continue.     |
|                                      |
| Branch: [________________________]   |
| [Create Branch]  [Cancel]            |
+--------------------------------------+
```

Action: `git stash` -> `git checkout -b <name>` -> `git stash pop`. Main is restored clean; changes land on the new branch.

#### On edit mode toggle (main, clean working tree)

Same modal, but no stash needed — just `git checkout -b <name>`. Edit mode activates only after the branch is created.

#### Branch indicator

Always visible next to the Edit toggle button:

| State | Color | Icon | Meaning |
|-------|-------|------|---------|
| Feature branch, matches remote | Green | — | Clean, up to date |
| Feature branch, local changes | Blue | — | Unpushed changes |
| Feature branch, main diverged | Green/Blue | `!` | Merge conflicts possible later (informational) |
| Feature branch, remote ahead | Green/Blue | Refresh | Can pull remote changes |
| Main | Red | — | Cannot edit or push |

The `!` warning is informational only and does not block any operations.

### 2. Push Flow

The Push button is:
- **Disabled** when: branch is main OR no changes vs remote
- **Enabled** when: branch is not main AND changes exist vs remote

On click, a modal appears:

```text
+------------------------------+
| Commit & Push                |
|                              |
| Branch: my-feature           |
| Modified spec files:         |
|   spec/prd.md                |
|   spec/dev-auth.md           |
|                              |
| Message: [________________]  |
|                              |
| [Push]  [Cancel]             |
+------------------------------+
```

Sequence:
1. `/api/save` — flush pending mutations to disk
2. `/api/git/push` — stage spec files, commit, push
3. Branch indicator turns green on success

### 3. Refresh (Pull)

The refresh icon appears when the remote branch has commits not in the local branch.

- **Fast-forward possible:** pull succeeds, indicator updates
- **Not fast-forward:** pull aborted, `!` stays, toast: "Cannot fast-forward — resolve differences outside elspais"

Elspais only performs safe, non-destructive git operations. No rebase, no merge, no conflict resolution.

### 4. Unsaved Changes Warning

`beforeunload` fires when either condition is true:
- **Pending mutations:** edits in the viewer not yet saved to disk (existing `/api/dirty`)
- **Uncommitted spec files:** saved to disk but not yet committed/pushed (new `/api/git/status`)

### 5. Backend Endpoints

All git operations delegate to `utilities/git.py`. No subprocess calls in the server layer.

```text
GET  /api/git/status
  Returns: {
    branch: str,
    is_main: bool,
    dirty_spec_files: str[],
    remote_diverged: bool,
    fast_forward_possible: bool
  }

POST /api/git/branch
  Body: { name: str }
  Action: stash (if dirty) -> checkout -b <name> -> stash pop (if stashed)
  Returns: { success: bool, branch: str }

POST /api/git/push
  Body: { message: str }
  Action: git add spec/** -> commit -m <message> -> push -u origin <branch>
  Returns: { success: bool, files_committed: str[], error?: str }

POST /api/git/pull
  Action: fetch -> merge --ff-only
  Returns: { success: bool, reason?: str }
```

### 6. State Flow Summary

```text
  +----------+     dirty spec     +----------------+
  |  main    | ---- files? -----> | Modal: branch  |
  |  (red)   |       yes         | name required   |
  +----------+                    +-------+--------+
       |                                  |
       | clean, toggle edit               v
       v                          +----------------+
  +----------+                    | Feature branch |
  | Modal:   |                    | (blue)         |
  | branch   +------------------> | Edit enabled   |
  | required |                    +-------+--------+
  +----------+                            |
                                   edit + save
                                          |
                                          v
                                  +----------------+
                                  | Push modal     |
                                  | message + files|
                                  +-------+--------+
                                          |
                                       push
                                          |
                                          v
                                  +----------------+
                                  | Feature branch |
                                  | (green)        |
                                  +----------------+
```
