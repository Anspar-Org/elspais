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
# The {associated} token is optional - renders empty for core repos
# Examples:
#   "{prefix}-{associated}{type}{id}"  -> REQ-p00001 (core) or REQ-CAL-d00001 (associated)
#   "{prefix}-{type}{id}"              -> REQ-p00001 (no associated support)
#   "{type}-{id}"                      -> PRD-00001
#   "{prefix}-{id}"                    -> PROJ-123
id_template = "{prefix}-{associated}{type}{id}"

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

# Assertion label configuration
[patterns.assertions]
label_style = "uppercase"  # "uppercase" [A-Z], "numeric" [00-99], "alphanumeric" [0-Z], "numeric_1based" [1-99]
max_count = 26             # Maximum assertions per requirement
zero_pad = false           # For numeric styles: true = "01", false = "1"

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

# Require Status field
require_status = true

# Allowed status values
allowed_statuses = ["Active", "Draft", "Deprecated", "Superseded"]

# Assertion format rules (new in v0.9.0)
# Require ## Assertions section in requirements
require_assertions = true

# How to handle legacy Acceptance Criteria format
# "allow" = silently accept, "warn" = log warning, "error" = fail validation
acceptance_criteria = "warn"

# Require SHALL keyword in assertion text
require_shall = true

# Labels must be sequential (A, B, C... not A, C, D)
labels_sequential = true

# No duplicate labels allowed
labels_unique = true

# Values that indicate removed/deprecated assertions (preserve label sequence)
placeholder_values = ["obsolete", "removed", "deprecated", "N/A", "n/a", "-", "reserved"]

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
# TESTING (v0.9.0+)
#──────────────────────────────────────────────────────────────────────────────

[testing]
# Enable test mapping and coverage features
enabled = false

# Glob patterns for test directories to scan
test_dirs = [
    "apps/**/test",
    "apps/**/tests",
    "packages/**/test",
    "packages/**/tests",
    "tools/**/tests",
    "tests",
]

# File patterns to match test files
patterns = [
    "*_test.dart",
    "test_*.dart",
    "test_*.py",
    "*_test.py",
    "*_test.sql",
]

# Glob patterns for test result files (JUnit XML, pytest JSON)
result_files = [
    "build-reports/**/TEST-*.xml",
    "build-reports/pytest-results.json",
]

# Regex patterns to extract requirement IDs from test names/comments
reference_patterns = [
    'test_.*(?:REQ[-_])?([pod]\\d{5})(?:_[A-Z])?',
    '(?:IMPLEMENTS|Implements|implements)[:\\s]+(?:REQ[-_])?([pod]\\d{5})(?:-[A-Z])?',
    '\\bREQ[-_]([pod]\\d{5})(?:-[A-Z])?\\b',
]

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
