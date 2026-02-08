# Ignore Configuration

The `[ignore]` section in `.elspais.toml` controls which files are skipped during scanning.

## Pattern Syntax

Patterns use Python's `fnmatch` module (similar to shell globs).

**Important**: Patterns match from the START of the path, not anywhere. This differs from gitignore behavior.

## Pattern Characters

- `*` matches any characters within a path component
- `**` matches across directory separators
- `?` matches a single character

## Examples

```toml
[ignore]
# Skip files named "README.md" or "INDEX.md" (basename match)
spec = ["README.md", "INDEX.md"]

# Skip a directory at any depth - use **/ prefix
spec = ["**/roadmap/**"]

# Skip a specific path from repo root
spec = ["spec/archive/**"]

# Skip by extension (anywhere)
global = ["*.pyc", "*.tmp"]
```

## Common Patterns

| Goal | Pattern | Example Match |
|------|---------|---------------|
| Skip directory anywhere | `**/dirname/**` | `spec/dirname/file.md` |
| Skip specific path | `spec/archive/**` | `spec/archive/old.md` |
| Skip by filename | `README.md` | `spec/README.md` |
| Skip by extension | `*.pyc` | `src/__pycache__/foo.pyc` |

## Scopes

Each scope applies to a specific scanning context:

| Scope | When Applied |
|-------|--------------|
| `global` | All scanning operations |
| `spec` | Scanning spec directories for requirements |
| `code` | Scanning code directories for `# Implements:` references |
| `test` | Scanning test directories for REQ references |

## Default Patterns

```toml
[ignore]
global = ["node_modules", ".git", "__pycache__", "*.pyc", ".venv", ".env"]
spec = ["README.md", "INDEX.md"]
code = ["*_test.py", "conftest.py", "test_*.py"]
test = ["fixtures/**", "__snapshots__"]
```

## Migration from gitignore-style Patterns

If you're used to gitignore patterns, note these differences:

| gitignore | elspais [ignore] | Notes |
|-----------|------------------|-------|
| `roadmap/` | `**/roadmap/**` | Must use `**/` for "anywhere" |
| `/roadmap/` | `roadmap/**` | Leading `/` not needed (already anchored) |
| `*.md` | `*.md` | Same behavior for extensions |
