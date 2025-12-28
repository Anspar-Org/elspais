# Configuration Reference

elspais uses TOML configuration files to customize behavior per repository.

## Configuration Discovery

elspais looks for configuration in this order:

1. `--config PATH` flag (explicit path)
2. `.elspais.toml` in current directory
3. `.elspais.toml` in git root
4. `~/.config/elspais/config.toml` (user defaults)
5. Built-in defaults

## Complete Configuration Reference

```toml
# .elspais.toml - Full configuration reference

#──────────────────────────────────────────────────────────────────────────────
# PROJECT
#──────────────────────────────────────────────────────────────────────────────

[project]
# Project name (used in reports)
name = "my-project"

# Repository type: "core" for primary repository, "associated" for extensions
type = "core"  # "core" | "associated"

#──────────────────────────────────────────────────────────────────────────────
# DIRECTORIES
#──────────────────────────────────────────────────────────────────────────────

[directories]
# Directory containing requirement specifications
spec = "spec"

# Documentation output directory
docs = "docs"

# Database directory (for traceability scanning)
database = "database"

# Code directories to scan for REQ references
code = [
    "apps",
    "packages",
    "server",
    "tools",
    "src",
]

# Directories to ignore entirely
ignore = [
    "node_modules",
    ".git",
    "build",
    "dist",
    ".dart_tool",
    "__pycache__",
    ".venv",
    "venv",
]

#──────────────────────────────────────────────────────────────────────────────
# SPEC FILES
#──────────────────────────────────────────────────────────────────────────────

[spec]
# Index file name
index_file = "INDEX.md"

# README file name
readme_file = "README.md"

# Format guide file name
format_guide = "requirements-format.md"

# Files to skip during validation
skip_files = ["README.md", "requirements-format.md", "INDEX.md"]

# Map file patterns to requirement types
[spec.file_patterns]
"prd-*.md" = "prd"
"ops-*.md" = "ops"
"dev-*.md" = "dev"

#──────────────────────────────────────────────────────────────────────────────
# PATTERNS - Requirement ID Format
#──────────────────────────────────────────────────────────────────────────────

[patterns]
# ID template using tokens: {prefix}, {associated}, {type}, {id}
# Examples:
#   "{prefix}-{type}{id}"              -> REQ-p00001
#   "{type}-{id}"                      -> PRD-00001
#   "{prefix}-{associated}-{type}{id}" -> REQ-CAL-d00001
#   "{prefix}-{id}"                    -> PROJ-123
id_template = "{prefix}-{type}{id}"

# Base prefix (used when {prefix} token is in template)
prefix = "REQ"

# Requirement types with their identifiers and hierarchy levels
# Lower level = higher in hierarchy (PRD=1 is parent of DEV=3)
[patterns.types]
prd = { id = "p", name = "Product Requirement", level = 1 }
ops = { id = "o", name = "Operations Requirement", level = 2 }
dev = { id = "d", name = "Development Requirement", level = 3 }

# ID number/name format
[patterns.id_format]
# Style: "numeric" | "alphanumeric" | "named"
style = "numeric"

# For numeric: number of digits (0 = variable length)
digits = 5

# For numeric: pad with leading zeros
leading_zeros = true

# For alphanumeric: regex pattern
# pattern = "[A-Z]{2}[0-9]{3}"

# For named: allowed characters and max length
# allowed_chars = "A-Za-z0-9-"
# max_length = 32

# Associated repository namespace configuration
[patterns.associated]
# Enable associated prefixes in IDs
enabled = false

# Position in ID: "after_prefix" | "before_type" | "none"
position = "after_prefix"

# Format: "uppercase" | "lowercase" | "mixed"
format = "uppercase"

# Fixed length (null for variable)
length = 3

# Separator between associated and rest
separator = "-"

#──────────────────────────────────────────────────────────────────────────────
# CORE REPOSITORY (for associated repos)
#──────────────────────────────────────────────────────────────────────────────

[core]
# Path to core repository (relative or absolute)
path = "../core-repo"

# Or specify remote URL for fetching
# remote = "git@github.com:org/core-repo.git"

#──────────────────────────────────────────────────────────────────────────────
# ASSOCIATED CONFIGURATION (when type = "associated")
#──────────────────────────────────────────────────────────────────────────────

[associated]
# Associated repo prefix (e.g., CAL for Callisto)
prefix = "CAL"

# Allowed ID range for this associated repo
id_range = [1, 99999]

#──────────────────────────────────────────────────────────────────────────────
# VALIDATION RULES
#──────────────────────────────────────────────────────────────────────────────

[validation]
# Enforce strict hierarchy (PRD -> OPS -> DEV)
strict_hierarchy = true

# Hash algorithm for change detection
hash_algorithm = "sha256"

# Hash length (number of characters)
hash_length = 8

#──────────────────────────────────────────────────────────────────────────────
# HIERARCHY RULES
#──────────────────────────────────────────────────────────────────────────────

[rules]
# Enable/disable rule categories
hierarchy = true
format = true
traceability = true

[rules.hierarchy]
# Define allowed "Implements" relationships
# Format: "source_type -> allowed_target_types"
allowed_implements = [
    "dev -> ops, prd",   # DEV can implement OPS or PRD
    "ops -> prd",        # OPS can implement PRD
    "prd -> prd",        # PRD can implement other PRD (sub-requirements)
]

# Forbid circular dependency chains (A -> B -> A)
allow_circular = false

# Require all requirements to implement something (except root PRD)
allow_orphans = false

# Maximum implementation chain depth
max_depth = 5

# Allow cross-repository implementations (associated -> core)
cross_repo_implements = true

#──────────────────────────────────────────────────────────────────────────────
# FORMAT RULES
#──────────────────────────────────────────────────────────────────────────────

[rules.format]
# Require hash footer on all requirements
require_hash = true

# Require Rationale section
require_rationale = false

# Require Acceptance Criteria section
require_acceptance = true

# Require Status field
require_status = true

# Allowed status values
allowed_statuses = ["Active", "Draft", "Deprecated", "Superseded"]

#──────────────────────────────────────────────────────────────────────────────
# TRACEABILITY RULES
#──────────────────────────────────────────────────────────────────────────────

[rules.traceability]
# Require at least one code reference for DEV requirements
require_code_link = false

# Warn about REQ IDs in code that have no matching spec
scan_for_orphans = true

#──────────────────────────────────────────────────────────────────────────────
# NAMING RULES
#──────────────────────────────────────────────────────────────────────────────

[rules.naming]
# Minimum title length
title_min_length = 10

# Maximum title length
title_max_length = 100

# Title must match pattern (regex)
title_pattern = "^[A-Z].*"  # Must start with capital letter

#──────────────────────────────────────────────────────────────────────────────
# TRACEABILITY MATRIX
#──────────────────────────────────────────────────────────────────────────────

[traceability]
# Output formats to generate
output_formats = ["markdown", "html"]

# Output directory
output_dir = "."

# File patterns to scan for implementation references
scan_patterns = [
    "database/**/*.sql",
    "apps/**/*.dart",
    "packages/**/*.dart",
    "server/**/*.dart",
    "tools/**/*.py",
    "src/**/*.py",
    ".github/workflows/**/*.yml",
]

# Patterns to detect implementation references in code
impl_patterns = [
    "IMPLEMENTS.*REQ-",
    "Implements:\\s*REQ-",
    "Fixes:\\s*REQ-",
]

#──────────────────────────────────────────────────────────────────────────────
# INDEX FILE
#──────────────────────────────────────────────────────────────────────────────

[index]
# Automatically regenerate INDEX.md on validation
auto_regenerate = false

#──────────────────────────────────────────────────────────────────────────────
# GIT HOOKS
#──────────────────────────────────────────────────────────────────────────────

[hooks]
# Run validation in pre-commit hook
pre_commit = true

# Validate REQ references in commit-msg hook
commit_msg = true
```

## Environment Variable Overrides

Configuration values can be overridden with environment variables:

```bash
# Pattern: ELSPAIS_<SECTION>_<KEY>
ELSPAIS_DIRECTORIES_SPEC=requirements
ELSPAIS_PATTERNS_PREFIX=PRD
ELSPAIS_ASSOCIATED_PREFIX=CAL
ELSPAIS_VALIDATION_STRICT_HIERARCHY=false
```

## Minimal Configuration Examples

### Core Repository

```toml
[project]
name = "my-core-project"
type = "core"
```

### Associated Repository

```toml
[project]
name = "associated-cal"
type = "associated"

[associated]
prefix = "CAL"

[core]
path = "../core-repo"
```

### Type-Prefix Style Requirements

```toml
[patterns]
id_template = "{type}-{id}"

[patterns.types]
PRD = { id = "PRD", level = 1 }
OPS = { id = "OPS", level = 2 }
DEV = { id = "DEV", level = 3 }

[patterns.id_format]
style = "numeric"
digits = 5
```

### Jira-Style Requirements

```toml
[patterns]
id_template = "{prefix}-{id}"
prefix = "PROJ"

[patterns.types]
req = { id = "", level = 1 }

[patterns.id_format]
style = "numeric"
digits = 0
leading_zeros = false
```
