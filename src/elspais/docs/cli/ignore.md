# IGNORING FILES DURING SCANNING

Scanning skips are configured under the `[scanning]` section of `.elspais.toml`.
There is no `[ignore]` section -- skips live alongside the directories and
file patterns they apply to.

Three lists make up the ignore configuration:

| Config | Scope | Applies to |
|--------|-------|------------|
| `[scanning].skip` | global | Every scan kind (spec, code, test) |
| `[scanning.<kind>].skip_files` | per-kind | That kind's scan only |
| `[scanning.<kind>].skip_dirs` | per-kind | That kind's scan only |

`<kind>` is `spec`, `code`, or `test`. The global `skip` list is checked for
every kind; a kind's `skip_files`/`skip_dirs` are checked only when scanning
that kind.

Every skip pattern is matched by two rules, which agree everywhere except
for a pattern of a single name:

- a pattern holding a `/` is a **path from the repository root**, for a file
  and a directory alike: `**/.coverage` names a file called `.coverage` at any
  depth as surely as `**/.pytest_cache` names that directory at any depth, and
  `gen/out.json` names that one file
- a pattern of a **single name** is read two ways: against a file it is a glob
  over the file's **name**, at any depth (`*.pyc`, `README.md`); against a
  directory it names that directory at the **repository root** only

So write `**/` in front of a name to mean "at any depth" for a file or a
directory, and a path from the root to mean one place. A bare name means "at
any depth" for a file and "at the root" for a directory.

## Ignoring and selecting are different questions

Every kind's scan answers them in one order, and the order matters:

1. **Ignore** -- the three lists above exclude a file or a whole directory.
   An excluded path is never opened, so nothing downstream can say anything
   about it. Ignoring is how you tell the tool a file is none of its business.
2. **Select** -- the kind's `file_patterns` pick, from what survived, the
   files to scan.

A file that survives step 1 but matches nothing in step 2 is not scanned --
and if it carries a *Traceability* keyword anyway, the tool reports it. That
is the difference the two steps buy you: a citation the tool declined to read
is disclosed, while a file you ignored is passed over in silence. If you want
no report about a file, ignore it; narrowing `file_patterns` alone does not
silence it.

```toml
[scanning]
# Global skip patterns (applied to all scan kinds)
skip = ["**/node_modules", "**/.git", "**/__pycache__", "*.pyc", "**/.venv", ".env"]

[scanning.spec]
directories = ["spec"]
skip_files  = ["README.md", "INDEX.md"]
skip_dirs   = ["**/roadmap", "spec/_generated"]

[scanning.code]
directories = ["src", "apps", "packages"]
skip_files  = ["conftest.py"]

[scanning.test]
enabled    = true
directories = ["tests"]
skip_dirs   = ["**/fixtures", "**/__snapshots__"]
```

## Pattern Syntax

### Directory patterns (`skip_dirs`, and `[scanning].skip` where it names a directory)

A directory pattern is a **path, read from the repository root**. It is not a
name matched at any depth.

| pattern | names |
|---------|-------|
| `stuff/things/junk` | that one directory |
| `junk` | `junk` at the repository root -- nothing else |
| `**/junk` | a directory called `junk` at any depth, the root included |
| `stuff/**` | everything under `stuff`, and `stuff` itself |

`**` stands for **zero or more** directories, which is why `**/junk` is a
strict superset of `junk` and never narrower.

A directory a pattern names is **not entered**. Nothing inside it is opened or
even listed, so its sub-directories go with it and nothing downstream can
report on any of it.

A directory that is both scanned and skipped contributes nothing.

### File patterns (`skip_files`, and `[scanning].skip` where it names a file)

A skip pattern of a single name is a glob over a file's **name**, so it applies
at any depth. A skip pattern holding a `/` is a path from the repository root,
read by the directory rules above:

| pattern | skips |
|---------|-------|
| `*.pyc` | every `.pyc` file, at any depth |
| `**/.coverage` | a file called `.coverage` at any depth, the root included |
| `.coverage` | the same: a single name matches a file at any depth |
| `gen/out.json` | that one file, and no `out.json` anywhere else |

`file_patterns` selects rather than skips, and is matched differently: against
the file's name and against its path *within* the directory being scanned, so
`api/*.py` selects inside a subdirectory of a scanned directory.

## Pattern Characters

- `*` matches any characters within a path component
- `**` matches zero or more directories (directory patterns)
- `?` matches a single character

## Common Patterns

| Goal | Where | Pattern | Example Match |
|------|-------|---------|---------------|
| Skip a file everywhere | `[scanning].skip` | `*.pyc` | `src/__pycache__/foo.pyc` |
| Skip a generated file at any depth | `[scanning].skip` | `**/.coverage` | `pkg/sub/.coverage` |
| Skip one file exactly | `[scanning].skip` | `build/report.json` | `build/report.json` |
| Skip a directory at any depth | `[scanning.<kind>].skip_dirs` | `**/roadmap` | `spec/roadmap/plan.md` |
| Skip one directory exactly | `[scanning.<kind>].skip_dirs` | `spec/archive` | `spec/archive/old.md` |
| Skip a file by name | `[scanning.<kind>].skip_files` | `README.md` | `spec/README.md` |

A bare `roadmap` in `skip_dirs` names `roadmap` at the repository root. If you
mean "wherever it appears", write `**/roadmap`.

## Recipe: keep test files out of the code scan

elspais has no built-in code/test de-duplication: a file matched by both
`[scanning.code].directories` and `[scanning.test]` is scanned as *both* a code
node and a test node. This is harmless (same target) but redundant. Exclude it
from the code scan rather than narrowing `[scanning.code].file_patterns`: an
ignored file is passed over in silence, while a merely unselected file that
cites a requirement is reported. Use `[scanning.code].skip_dirs`. For example,
Playwright specs living under `apps/**/e2e/tests` that are already scanned as
test nodes:

```toml
[scanning.code]
directories = ["src", "apps", "packages"]
skip_dirs   = ["**/e2e"]       # keep the code scan out of e2e test dirs
```

Or exclude Python test modules from the code scan:

```toml
[scanning.code]
skip_files = ["*_test.py", "test_*.py", "conftest.py"]
```

These are opt-in -- elspais applies no default code/test exclusions, so add
the patterns your project needs.

## Migration from gitignore-style Patterns

If you're used to gitignore patterns, note these differences:

| gitignore | elspais pattern | Notes |
|-----------|-----------------|-------|
| `roadmap/` | `**/roadmap` (in `skip_dirs`) | A bare `roadmap` names only the one at the root |
| `/roadmap/` | `roadmap` (in `skip_dirs`) | Leading `/` not needed (already anchored) |
| `*.md` | `*.md` | Same behavior for extensions |

See `elspais docs config` for the full `[scanning]` reference.
