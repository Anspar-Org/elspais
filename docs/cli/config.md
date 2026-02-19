# CONFIGURATION

## Configuration File

elspais looks for `.elspais.toml` in the current directory
or parent directories up to the git repository root.

  $ elspais init          # Create default config
  $ elspais config path   # Show config location
  $ elspais config show   # View all settings

## Local Overrides (.elspais.local.toml)

Place a `.elspais.local.toml` file alongside `.elspais.toml` for
developer-local settings that should not be committed. This file
is deep-merged on top of the base config, following the same pattern
as `docker-compose.override.yml` or `.env.local`.

```toml
# .elspais.local.toml (gitignored)
[associates]
paths = ["/home/dev/other-repo"]
```

**Load order:** defaults → `.elspais.toml` → `.elspais.local.toml` → env vars

Each layer deep-merges over the previous one, so you only need to
specify the keys you want to override. Environment variables always win.

## Complete Configuration Reference

### [project] Section

```toml
[project]
name = "my-project"        # Project name (optional)
type = "core"              # "core" or "associated"
```

### [patterns] Section

Controls requirement ID format and type definitions.

```toml
[patterns]
id_template = "{prefix}-{type}{id}"   # ID template with tokens
prefix = "REQ"                         # ID prefix

# Type definitions (PRD, OPS, DEV levels)
[patterns.types.prd]
id = "p"           # Character in ID (REQ-p00001)
name = "PRD"       # Display name
level = 1          # Hierarchy level (1=highest)

[patterns.types.ops]
id = "o"
name = "OPS"
level = 2

[patterns.types.dev]
id = "d"
name = "DEV"
level = 3

# ID number formatting
[patterns.id_format]
style = "numeric"      # Format style
digits = 5             # Number of digits (0 = variable)
leading_zeros = true   # Pad with zeros (00001 vs 1)
```

**Template Tokens:**
  `{prefix}`     ID prefix (e.g., "REQ")
  `{type}`       Type character (e.g., "p", "o", "d")
  `{associated}` Associated repo prefix (if enabled)
  `{id}`         Numeric ID

### [patterns.associated] Section

For multi-repository setups with associated requirement IDs.

```toml
[patterns.associated]
enabled = true              # Enable associated repo IDs
position = "after_prefix"   # Position in ID
format = "uppercase"        # Format style
length = 3                  # Prefix length
separator = "-"             # Separator character
```

### [spec] Section

Controls spec file discovery.

```toml
[spec]
directories = ["spec"]      # Directories to scan
patterns = ["*.md"]         # File patterns to include
skip_files = ["README.md"]  # Files to skip
skip_dirs = ["archive"]     # Subdirectories to skip
index_file = "INDEX.md"     # Index file name

# Map file patterns to levels (optional)
[spec.file_patterns]
"prd-*.md" = "prd"
"ops-*.md" = "ops"
"dev-*.md" = "dev"
```

### [directories] Section

Override directory paths.

```toml
[directories]
spec = "spec"               # Spec directory (string or array)
code = ["src", "lib"]       # Code directories for traceability
docs = "docs"               # Documentation directory
ignore = ["node_modules"]   # Directories to ignore globally
```

### [rules] Section

Validation and hierarchy rules.

```toml
[rules]
strict_mode = false         # Strict implements semantics

# Hierarchy relationship rules
[rules.hierarchy]
dev = ["ops", "prd"]        # DEV can implement OPS or PRD
ops = ["prd"]               # OPS can implement PRD
prd = []                    # PRD cannot implement anything

# Alternative syntax (human-readable)
allowed = [
    "dev -> ops, prd",
    "ops -> prd"
]

allow_circular = false      # Allow circular dependencies
allow_orphans = false       # Allow requirements with no parent

# Format validation rules
[rules.format]
require_hash = true         # Require hash footer
require_rationale = false   # Require rationale section
require_assertions = true   # Require assertions
require_status = true       # Require status field
allowed_statuses = [        # Valid status values
    "Active",
    "Draft",
    "Deprecated",
    "Superseded"
]

# Content rule modules (advanced)
[rules.content_rules]
modules = []                # Module paths for custom rules
```

### [validation] Section

Hash and validation settings.

```toml
[validation]
strict_hierarchy = true     # Strict hierarchy checking
hash_algorithm = "sha256"   # Hash algorithm
hash_length = 8             # Hash length in characters
```

### [traceability] Section

Code and test scanning for traceability reports.

```toml
[traceability]
output_formats = ["markdown", "html"]   # Default output formats
output_dir = "."                         # Output directory

# Code files to scan for implementations
scan_patterns = [
    "database/**/*.sql",
    "src/**/*.py",
    "apps/**/*.dart",
]

# Test result file locations
test_results = [
    "test-results/*.xml",    # JUnit XML
    "pytest-report.json",    # pytest JSON
]
```

### [associated] Section

For associated (satellite) repositories.

```toml
[associated]
prefix = "TTN"              # Associated repo prefix
id_range = [1, 99999]       # ID range for this repo
path = "../titan-spec"      # Path to associated repo
```

### [core] Section

For associated repos referencing their core.

```toml
[core]
path = "../core"            # Path to core repository
```

## Config Commands

  $ elspais config show                # View all settings
  $ elspais config show --section rules
  $ elspais config show -j             # JSON output
  $ elspais config get patterns.prefix
  $ elspais config set project.name "NewName"
  $ elspais config set rules.strict_mode true
  $ elspais config unset rules.strict_mode
  $ elspais config add directories.code src/lib
  $ elspais config remove directories.code src/lib
  $ elspais config path                # Show file location

## Environment Variable Overrides

Any config key can be overridden via environment variables:

  ELSPAIS_PATTERNS_PREFIX=MYREQ elspais validate
  ELSPAIS_RULES_STRICT_MODE=true elspais validate

**Conversion:**
  `ELSPAIS_PATTERNS_PREFIX` -> `patterns.prefix`
  `ELSPAIS_RULES_STRICT_MODE` -> `rules.strict_mode`

Rule: Remove `ELSPAIS_`, lowercase, underscores become dots.

## Skip Directories

Exclude directories from scanning:

```toml
[spec]
skip_dirs = ["archive", "drafts"]

[directories]
ignore = ["node_modules", ".git"]
```

## Multi-Repository Setup

**Core Repository (.elspais.toml):**

```toml
[project]
name = "core-product"
type = "core"

[patterns]
prefix = "REQ"
```

**Associated Repository (.elspais.toml):**

```toml
[project]
name = "titan-extension"
type = "associated"

[associated]
prefix = "TTN"

[core]
path = "../core-product"
```
