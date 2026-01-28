# CONFIGURATION

## Configuration File

elspais looks for `.elspais.toml` in the current directory
or parent directories.

  $ elspais init          # Create default config
  $ elspais config path   # Show config location
  $ elspais config show   # View all settings

## Basic Configuration

`.elspais.toml`:

```toml
[project]
name = "my-project"
spec_dir = "spec"          # Requirement file location

[patterns]
prefix = "REQ"             # ID prefix (REQ-p00001)
separator = "-"            # ID separator

[rules]
strict_mode = false        # Strict implements semantics

[rules.hierarchy]
allowed = [
    "dev -> ops, prd",     # DEV can implement OPS or PRD
    "ops -> prd"           # OPS can implement PRD
]
```

## Config Commands

  $ elspais config get patterns.prefix
  $ elspais config set project.name "NewName"
  $ elspais config unset rules.strict_mode

## Skip Directories

Exclude directories from scanning:

```toml
[project]
skip_dirs = ["spec/archive", "spec/drafts"]
```

## Multi-Repository

For associated/sponsor repositories:

```toml
[associated]
prefix = "TTN"             # Their ID prefix
repo_path = "../titan-spec"
```
