# IGNORING FILES DURING SCANNING

Scanning skips are configured under the `[scanning]` section of `.elspais.toml`.
There is no `[ignore]` section -- skips live alongside the directories and
file patterns they apply to.

Two levers control what gets skipped:

| Config | Scope | Applies to |
|--------|-------|------------|
| `[scanning].skip` | global | Every scan kind (spec, code, test) |
| `[scanning.<kind>].skip_files` | per-kind | That kind's scan only |
| `[scanning.<kind>].skip_dirs` | per-kind | That kind's scan only |

`<kind>` is `spec`, `code`, or `test`. The global `skip` list is checked for
every kind; a kind's `skip_files`/`skip_dirs` are checked only when scanning
that kind. `skip_files` and `skip_dirs` are matched identically (both are just
glob patterns) -- the two names are a readability convention, not different
matching rules.

```toml
[scanning]
# Global skip patterns (applied to all scan kinds)
skip = ["node_modules", ".git", "__pycache__", "*.pyc", ".venv", ".env"]

[scanning.spec]
directories = ["spec"]
skip_files  = ["README.md", "INDEX.md"]
skip_dirs   = ["roadmap", "_generated"]

[scanning.code]
directories = ["src", "apps", "packages"]
skip_files  = ["conftest.py"]

[scanning.test]
enabled    = true
directories = ["tests"]
skip_dirs   = ["fixtures", "__snapshots__"]
```

## Pattern Syntax

Patterns use Python's `fnmatch` module (similar to shell globs).

**Important**: Each pattern is matched against three things: the file/dir
basename, each individual path component, and the full path. A pattern like
`README.md` matches any file named `README.md` at any depth; a pattern like
`roadmap` matches any path component named `roadmap`.

## Pattern Characters

- `*` matches any characters within a path component
- `**` matches across directory separators
- `?` matches a single character

## Common Patterns

| Goal | Where | Pattern | Example Match |
|------|-------|---------|---------------|
| Skip everywhere (all kinds) | `[scanning].skip` | `*.pyc` | `src/__pycache__/foo.pyc` |
| Skip a directory by name | `[scanning.<kind>].skip_dirs` | `roadmap` | `spec/roadmap/plan.md` |
| Skip a directory at a path | `[scanning.<kind>].skip_dirs` | `spec/archive/**` | `spec/archive/old.md` |
| Skip a file by name | `[scanning.<kind>].skip_files` | `README.md` | `spec/README.md` |

## Recipe: keep test files out of the code scan

elspais has no built-in code/test de-duplication: a file matched by both
`[scanning.code].directories` and `[scanning.test]` is scanned as *both* a code
node and a test node. This is harmless (same target) but redundant. To scan a
directory only as tests, exclude it from the code scan via
`[scanning.code].skip_dirs`. For example, Playwright specs living under
`apps/**/e2e/tests` that are already scanned as test nodes:

```toml
[scanning.code]
directories = ["src", "apps", "packages"]
skip_dirs   = ["e2e"]          # keep the code scan out of e2e test dirs
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
| `roadmap/` | `roadmap` (in `skip_dirs`) | Matches the path component at any depth |
| `/roadmap/` | `roadmap/**` | Leading `/` not needed (already anchored) |
| `*.md` | `*.md` | Same behavior for extensions |

See `elspais docs config` for the full `[scanning]` reference.
