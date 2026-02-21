# doctor

Diagnose your elspais environment and installation.

## Usage

```
elspais doctor [--json] [--verbose]
```

## What it checks

### Configuration

- Configuration file exists and is readable
- Configuration file has valid syntax
- Required settings are present (patterns, spec directories, hierarchy rules)
- ID pattern placeholders are valid
- Spec directories exist on disk
- Project type is properly configured

### Environment

- **Worktree detection**: Shows if you're working in a git worktree and where the main repository is
- **Associate paths**: Verifies that configured associated project paths exist
- **Associate configuration**: Checks that associated projects have valid `.elspais.toml` files
- **Local configuration**: Checks for `.elspais.local.toml` (developer-specific settings)
- **Cross-project paths**: Warns if paths like `../../other-repo` are in the shared config instead of the local config

## Options

| Flag | Description |
|------|-------------|
| `-j`, `--json` | Output results as JSON |
| `-v`, `--verbose` | Show detailed information for each check |

## Examples

```bash
# Quick setup check
elspais doctor

# JSON output for CI/scripting
elspais doctor -j

# Detailed output
elspais doctor -v
```

## Exit codes

- `0` - All checks passed (warnings are OK)
- `1` - One or more checks failed
