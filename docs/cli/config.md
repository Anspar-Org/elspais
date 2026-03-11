# CONFIGURATION

## Configuration File

elspais looks for `.elspais.toml` in the current directory
or parent directories up to the git repository root.

  $ elspais init          # Create default config
  $ elspais config path   # Show config location
  $ elspais config show   # View all settings

## Git Worktree Support

elspais automatically detects git worktrees and resolves cross-repo
paths from the **canonical** (main) repository root. This means
`[associates].paths` like `"../sibling-repo"` resolve correctly even
when working from a worktree in a different directory.

Use `-v` to see which roots were detected:

  $ elspais health -v
  Working from repository root: /home/dev/worktrees/feature-x
  Canonical root (main repo): /home/dev/my-project

No configuration is needed -- worktree detection is automatic.

## Local Overrides (.elspais.local.toml)

Place a `.elspais.local.toml` file alongside `.elspais.toml` for
developer-local settings that should not be committed. This file
is deep-merged on top of the base config, following the same pattern
as `docker-compose.override.yml` or `.env.local`.

```toml
# .elspais.local.toml (gitignored)
[associates]
paths = ["../sibling-repo"]
```

**Load order:** defaults -> `.elspais.toml` -> `.elspais.local.toml` -> env vars

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
skip_files = []             # Files to skip (legacy; prefer [ignore].spec)
skip_dirs = []              # Subdirectories to skip (legacy; prefer [ignore].spec)
```

### [rules] Section

Hierarchy relationship rules.

```toml
[rules.hierarchy]
dev = ["ops", "prd"]        # DEV can implement OPS or PRD
ops = ["prd"]               # OPS can implement PRD
prd = []                    # PRD cannot implement anything
```

### [ignore] Section

Controls which files are skipped during scanning. Each scope applies
to a specific scanning context. See `elspais docs ignore` for details.

```toml
[ignore]
global = ["node_modules", ".git", "__pycache__", "*.pyc", ".venv", ".env"]
spec = ["README.md", "INDEX.md"]
code = ["*_test.py", "conftest.py", "test_*.py"]
test = ["fixtures/**", "__snapshots__"]
```

### [testing] Section

Configure test file scanning.

```toml
[testing]
enabled = false                         # Enable test scanning
test_dirs = ["tests"]                   # Directories to scan
patterns = ["test_*.py", "*_test.py"]   # File patterns
result_files = []                       # JUnit XML / pytest JSON paths
reference_patterns = []                 # Additional reference patterns
reference_keyword = "Validates"         # Default reference keyword
```

### [references] Section

Configure how code/test references are parsed.

```toml
[references.defaults]
separators = ["-", "_"]              # ID separators
case_sensitive = false               # Case-sensitive matching
prefix_optional = false              # Allow omitting prefix
comment_styles = ["#", "//", "--"]   # Comment styles to scan
multi_assertion_separator = "+"      # Separator for REQ-xxx-A+B+C syntax

[references.defaults.keywords]
implements = ["Implements", "IMPLEMENTS"]
validates = ["Validates", "Tests", "VALIDATES", "TESTS"]
refines = ["Refines", "REFINES"]

# Override settings for specific file patterns
[[references.overrides]]
match = "*.java"
comment_styles = ["//"]
keywords = { implements = ["@Implements"], validates = ["@Tests"] }
```

### [validation] Section

```toml
[validation]
hash_mode = "normalized-text"   # Hash computation mode
```

### [changelog] Section

Controls changelog enforcement for Active requirements.

```toml
[changelog]
enforce = true                 # Enable changelog enforcement
require_present = false        # Require ## Changelog section exists
id_source = "gh"               # Change order ID source
date_format = "iso"            # Date format (iso = YYYY-MM-DD)
require_change_order = false   # Require change order ID
require_reason = true          # Require reason field
require_author_name = true     # Require author name
require_author_id = true       # Require author ID
author_id_format = "email"     # Author ID format
allowed_author_ids = "all"     # Allowed author IDs ("all" or list)
```

### [keywords] Section

```toml
[keywords]
min_length = 3    # Minimum keyword length for extraction
```

### [graph] Section

```toml
[graph]
satellite_kinds = ["assertion", "result"]   # Kinds collapsed in graph views
```

### [associates] Section

Configure paths to associated repositories for combined validation.

```toml
[associates]
paths = ["../callisto", "../phoenix"]   # Relative to repo root
```

Relative paths resolve from the **canonical** repository root,
so they work correctly from git worktrees. Each path must contain
a `.elspais.toml` with `project.type = "associated"`.

### [associated] Section

For associated (satellite) repositories to declare their identity.

```toml
[associated]
prefix = "TTN"              # Associated repo prefix
id_range = [1, 99999]       # ID range for this repo
```

### [core] Section

For associated repos referencing their core.

```toml
[core]
path = "../core"            # Path to core repository
```

## Config Commands

  $ elspais config show                   # View all settings
  $ elspais config show --section rules
  $ elspais config show --format json     # JSON output
  $ elspais config get patterns.prefix
  $ elspais config set project.name "NewName"
  $ elspais config unset associated.prefix
  $ elspais config add spec.directories src/spec
  $ elspais config remove spec.directories src/spec
  $ elspais config path                   # Show file location

## Environment Variable Overrides

Any config key can be overridden via environment variables:

  ELSPAIS_PATTERNS_PREFIX=MYREQ elspais health
  ELSPAIS_TESTING_ENABLED=true elspais health

**Conversion:**
  `ELSPAIS_PATTERNS_PREFIX` -> `patterns.prefix`
  `ELSPAIS_TESTING_ENABLED` -> `testing.enabled`

Rule: Remove `ELSPAIS_`, lowercase, single underscores become dots.
Use double underscore (`__`) for a literal underscore in key names.

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
