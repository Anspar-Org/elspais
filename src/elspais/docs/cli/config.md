# CONFIGURATION

## Configuration File

elspais looks for `.elspais.toml` in the current directory
or parent directories up to the git repository root.

  $ elspais init            # Create default config
  $ elspais config path     # Show config location
  $ elspais config show     # View all settings
  $ elspais config schema   # Export JSON Schema

The generated file includes every configuration field with a comment
explaining its purpose, valid values, and effect. Optional fields appear
as commented-out lines that you can uncomment and customize.

## Git Worktree Support

elspais automatically detects git worktrees and resolves cross-repo
paths from the **canonical** (main) repository root. This means
`[associates.<name>].path` like `"../sibling-repo"` resolves correctly
even when working from a worktree in a different directory.

Use `-v` to see which roots were detected:

  $ elspais -v health
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
[associates.sibling]
path = "../sibling-repo"
namespace = "SIB"
```

**Load order:** defaults -> `.elspais.toml` -> `.elspais.local.toml` -> env vars

Each layer deep-merges over the previous one, so you only need to
specify the keys you want to override. Environment variables always win.

## Complete Configuration Reference

### version

```toml
version = 4   # Config schema version (required)
```

### [project] Section

```toml
[project]
namespace = "REQ"          # ID prefix (e.g. "REQ" -> REQ-p00001)
name = "my-project"        # Project name (used in reports)
```

### [levels] Section

Defines requirement levels with rank, letter, display name, and
hierarchy rules. Lower rank = higher in hierarchy.

```toml
[levels.prd]
rank = 1                   # Hierarchy rank (1 = highest)
letter = "p"               # Character in ID (REQ-p00001)
display_name = "Product"   # Display name in reports
implements = ["prd"]       # Which levels this level may implement

[levels.ops]
rank = 2
letter = "o"
display_name = "Operations"
implements = ["ops", "prd"]

[levels.dev]
rank = 3
letter = "d"
display_name = "Development"
implements = ["dev", "ops", "prd"]
```

### [id-patterns] Section

Controls requirement ID format and parsing.

```toml
[id-patterns]
canonical = "{namespace}-{level.letter}{component}"  # ID template
separators = ["-", "_"]    # Accepted separator characters
prefix_optional = false    # Whether namespace prefix is required

[id-patterns.aliases]
short = "{level.letter}{component}"   # Named alias patterns

[id-patterns.component]
style = "numeric"          # "numeric" | "alphanumeric" | "named"
digits = 5                 # Number of digits (0 = variable length)
leading_zeros = true       # Pad with zeros (00001 vs 1)
# pattern = "[A-Z]{2}[0-9]{3}"   # For alphanumeric style
# max_length = 32                 # For named style

[id-patterns.assertions]
label_style = "uppercase"  # "uppercase" | "numeric" | "alphanumeric" | "numeric_1based"
max_count = 26             # Maximum assertions per requirement
# zero_pad = false         # Pad numeric labels with zeros
# multi_separator = "+"    # Separator for multi-assertion syntax (A+B+C)
```

**Template Tokens:**
  `{namespace}`      ID prefix (e.g., "REQ")
  `{level.letter}`   Level character (e.g., "p", "o", "d")
  `{component}`      Numeric or named ID

### [scanning] Section

Unified file scanning configuration. Each kind has its own
sub-section with directories, file_patterns, skip_files, skip_dirs.

```toml
[scanning]
skip = ["node_modules", ".git", "__pycache__", "*.pyc", ".venv", ".env"]

[scanning.spec]
directories = ["spec"]
file_patterns = ["*.md"]
skip_files = ["README.md", "INDEX.md"]
skip_dirs = []
# index_file = "INDEX.md"       # Optional index file for ordering

[scanning.code]
directories = ["src"]
file_patterns = []
skip_files = []
skip_dirs = []
# source_roots = []             # Root directories for import resolution

[scanning.test]
enabled = false                  # Enable test mapping and coverage
directories = ["tests"]
file_patterns = ["test_*.py", "*_test.py"]
skip_files = []
skip_dirs = []
reference_keyword = "Verifies"   # Keyword for test-to-req references
reference_patterns = []          # Additional reference patterns
prescan_command = ""             # External test discovery command
# prescan_command receives file paths on stdin, outputs JSON on stdout:
#   [{"file": "path", "function": "name", "class": "Name|null", "line": N}]

[scanning.result]
directories = []
file_patterns = []               # JUnit XML, pytest JSON patterns
skip_files = []
skip_dirs = []
run_meta_file = ""               # Test run metadata file

[scanning.journey]
directories = ["spec"]
file_patterns = ["*.md"]
skip_files = []
skip_dirs = []

[scanning.docs]
directories = ["docs"]
file_patterns = ["*.md"]
skip_files = []
skip_dirs = []
```

### [rules] Section

Hierarchy and format enforcement rules.

```toml
[rules.hierarchy]
allow_circular = false              # Allow circular dependency chains
allow_structural_orphans = false    # Allow nodes without FILE ancestor
# cross_repo_implements = true      # Allow cross-repo implementations
# allow_orphans = false             # Allow orphaned nodes

[rules.format]
require_hash = true                 # Require hash footer
require_rationale = false           # Require Rationale section
require_assertions = true           # Require Assertions section
require_status = true               # Require Status field
allowed_statuses = ["Active", "Draft", "Deprecated", "Superseded"]
# content_rules = []                # Additional content rules

[rules.format.status_roles]
active = ["Active"]                 # Counted in coverage and analysis
provisional = ["Draft", "Proposed"] # Excluded from coverage
aspirational = ["Roadmap", "Future"]  # Excluded from coverage and analysis
retired = ["Deprecated", "Superseded"]  # Excluded from everything
```

### [validation] Section

```toml
[validation]
hash_mode = "normalized-text"       # "full-text" | "normalized-text"
allow_unresolved_cross_repo = false # Allow unresolved cross-repo refs
# hash_algorithm = "sha256"         # Hash algorithm
# hash_length = 8                   # Hash truncation length
# strict_hierarchy = false          # Strict hierarchy validation
```

### [changelog] Section

Controls changelog enforcement for Active requirements.

```toml
[changelog]
hash_current = true            # Check hashes against changelog entries
present = false                # Require ## Changelog section exists
id_source = "gh"               # Author ID source: "gh" | "git"
date_format = "iso"            # Date format: "iso" | "us" | "eu"
author_id_format = "email"     # Author ID format: "email" | "handle"
allowed_author_ids = "all"     # "all" or list of allowed values

[changelog.require]
reason = true                  # Require reason field
author_name = true             # Require author name
author_id = true               # Require author ID
change_order = false           # Require change order ID
```

### [keywords] Section

```toml
[keywords]
min_length = 3    # Minimum keyword length for extraction
```

### [output] Section

```toml
[output]
formats = []      # Output formats (e.g. ["markdown", "html"])
dir = ""          # Output directory
```

### [associates] Section

Configure associated repositories for combined validation.
Each entry has a name, path, and namespace.

```toml
[associates.callisto]
path = "../callisto"     # Relative to canonical repo root
namespace = "CAL"        # Namespace prefix for this repo

[associates.phoenix]
path = "../phoenix"
namespace = "PHX"
```

Relative paths resolve from the **canonical** repository root,
so they work correctly from git worktrees. Each path must contain
a `.elspais.toml` with its own configuration.

## Config Commands

  $ elspais config show                   # View all settings
  $ elspais config show --section rules
  $ elspais config show --format json     # JSON output
  $ elspais config get scanning.test.enabled
  $ elspais config set project.name "NewName"
  $ elspais config unset changelog.present
  $ elspais config add scanning.spec.directories src/spec
  $ elspais config remove scanning.spec.directories src/spec
  $ elspais config path                   # Show file location
  $ elspais config schema                 # Print JSON Schema to stdout
  $ elspais config schema -o schema.json  # Write JSON Schema to file

### Schema Export

Generate the JSON Schema for `.elspais.toml` configuration:

  $ elspais config schema                 # Print to stdout
  $ elspais config schema --output schema.json

The schema is derived from the Pydantic `ElspaisConfig` model and includes
a `$schema` self-reference for IDE autocompletion. A committed copy lives at
`src/elspais/config/elspais-schema.json` and is kept in sync via CI.

## Environment Variable Overrides

Any config key can be overridden via environment variables:

  ELSPAIS_PROJECT_NAMESPACE=MYREQ elspais health
  ELSPAIS_SCANNING_TEST_ENABLED=true elspais health

**Conversion:**
  `ELSPAIS_PROJECT_NAMESPACE` -> `project.namespace`
  `ELSPAIS_SCANNING_TEST_ENABLED` -> `scanning.test.enabled`

Rule: Remove `ELSPAIS_`, lowercase, single underscores become dots.
Use double underscore (`__`) for a literal underscore in key names.
