# BASELINE RUNS

A *Baseline Run* is a recorded run of a test target that another tree adopts,
such as the run continuous integration made of the commit a branch started
from. A worktree that adopts one starts with results for every target, and
judges each one fresh or stale exactly as it judges a run it made itself.

`elspais baseline pack` writes the recorded runs of the selected targets into
one archive. `elspais baseline fetch` runs a command the project declares to
obtain such an archive, and adopts each packed run where the tree records
none. How an archive travels, and which run is the right one to fetch, belong
to the project: elspais knows no host, reads no branch and walks no history.

## Packing

```bash
elspais test --targets all                       # run the targets
elspais baseline pack --out baseline.tar.gz --targets all
```

`--targets` selects targets and groups as `elspais test` does, and the
default is the `default` group. The archive is a gzip-compressed tar file. It
holds each target's folder as its run left it -- results, coverage and the
fingerprint -- and the file `elspais-baseline.json`, which states the version
of elspais that packed it, the archive format, the fingerprint format and the
commit the runs executed at.

A pack holds only runs that can serve another tree. It is refused, naming the
target and the reason, with exit 1, where:

- the tree holds changes no commit holds, because a *Baseline Run* is a run of
  a tree identical to a commit;
- a target's run executed in a tree that held such changes, or at another
  commit than the tree is at now;
- a target has no fingerprint, or one of another format;
- a target's run is in progress, or stopped without recording its end, so its
  results may be partial;
- an input of a target changed while its run was going;
- a target's folder holds no results.

A run whose tests failed is packed. Its failures are its results.

Every untracked file that git does not ignore counts as a change no commit
holds. Ignore the output root and `.elspais/` in `.gitignore`, or every pack is
refused.

A selection naming a federation member's targets is refused (exit 2): a pack
holds the runs of one repository.

## Fetching

```toml
[scanning.test.baseline]
fetch_command = "tools/fetch-baseline.sh {dest}"
```

`elspais baseline fetch` creates an empty temporary directory, substitutes its
path for `{dest}`, shell-quoted, and runs the command from the repository
root. The command leaves exactly one archive in that directory. A
configuration whose `fetch_command` does not name `{dest}` is refused when it
is read.

The command decides which run to fetch. For a pull request that is usually
the latest baseline of the branch it targets, and otherwise of the main
branch. Any age is acceptable: a baseline from an older commit is adopted,
and the checks then name the inputs that differ.

elspais then reads the archive. An archive of another format, holding
fingerprints of another format, or holding anything other than files and
directories inside it, is refused whole. Each packed target is then:

- **adopted** where its folder here holds no fingerprint. The folder is
  emptied and filled with the packed one;
- **skipped** where a fingerprint is already recorded here. `--replace`
  replaces it;
- **refused** where this repository declares no target of that name, where
  the pack holds no readable fingerprint for it, or where a run of it is in
  progress here. A run in progress is never replaced, `--replace` or not.

Every target is judged before any folder changes. A fetch command that fails,
or that leaves nothing or more than one entry, is reported, changes nothing and
exits 1. A fetch in which any target was refused exits 1; skips alone exit 0.

## What an Adopted Run Is

An adopted folder is an ordinary recorded run. `elspais checks` judges it by
its fingerprint: its results are fresh while the files, the environment and
the configuration of the target here match the ones it ran against, and stale
otherwise, naming what differs. See `elspais docs test-targets`, *The
environment and configuration of a target*. A stale adopted run is carried,
and `elspais test --stale-only` executes it again.

The fingerprint records the directory the run executed in, so the results
still bind to their tests in a tree checked out elsewhere.
