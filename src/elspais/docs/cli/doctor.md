# DOCTOR

Diagnose your elspais environment and installation.

## Usage

```
elspais doctor [--format {text,json}] [--verbose]
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
- **Associate paths**: Verifies that every federated project's path exists — including projects reached through an associate's own declarations, not only those this repository names
- **Associate configuration**: Checks that every federated project has a valid `.elspais.toml`, naming the path and the reason for each one that does not
- **Local configuration**: Checks for `.elspais.local.toml` (developer-specific settings)
- **Cross-project paths**: Warns if paths like `../../other-repo` are in the shared config instead of the local config

## Options

| Flag | Description |
|------|-------------|
| `--format {text,json}` | Output format (default: text) |
| `-v`, `--verbose` | Show detailed information for each check |

## Examples

```bash
# Quick setup check
elspais doctor

# JSON output for CI/scripting
elspais doctor --format json

# Detailed output
elspais doctor -v
```

## Exit codes

- `0` - All checks passed
- `1` - One or more checks failed (configuration errors, missing paths, etc.)
