# Configuration Reference

elspais uses TOML configuration files to customize behavior per repository.

## Configuration Discovery

elspais looks for configuration in this order:

1. `--config PATH` flag (explicit path)
2. `.elspais.toml` in current directory
3. `.elspais.toml` in git root
4. `~/.config/elspais/config.toml` (user defaults)
5. Built-in defaults

For **git worktrees**, elspais detects the canonical (main) repository
root and uses it when resolving relative associate paths. This means
paths like `"../sibling-repo"` in `[associates].paths` resolve from the
main repo, not the worktree location.

## Complete Configuration Reference

```toml
# .elspais.toml - Full configuration reference (v3)

# Config schema version (defaults to 3)
version = 3

# MCP tool usage statistics file path (optional, or set ELSPAIS_STATS env var)
stats = ""

# CLI daemon auto-start TTL (minutes).
#   >0: auto-start daemon, exit after N minutes idle (default: 30)
#    0: never auto-launch daemon from CLI (manual start only)
#   <0: auto-start daemon that never times out
cli_ttl = 30

#──────────────────────────────────────────────────────────────────────────────
# PROJECT
#──────────────────────────────────────────────────────────────────────────────

[project]
# Project namespace (used as the ID prefix, e.g. "REQ" -> REQ-p00001)
namespace = "REQ"

# Project name (used in reports)
name = "my-project"

#──────────────────────────────────────────────────────────────────────────────
# LEVELS - Requirement Hierarchy
# Defines requirement levels with rank, letter, display name, and implements rules.
# Lower rank = higher in hierarchy (PRD=1 is parent of DEV=3).
# The `implements` list declares which levels this level may implement.
#──────────────────────────────────────────────────────────────────────────────

[levels.prd]
rank = 1
letter = "p"
display_name = "Product"
implements = ["prd"]            # PRD can implement other PRD (sub-requirements)

[levels.ops]
rank = 2
letter = "o"
display_name = "Operations"
implements = ["ops", "prd"]     # OPS can implement OPS or PRD

[levels.dev]
rank = 3
letter = "d"
display_name = "Development"
implements = ["dev", "ops", "prd"]  # DEV can implement DEV, OPS, or PRD

#──────────────────────────────────────────────────────────────────────────────
# ID PATTERNS - Requirement ID Format
#──────────────────────────────────────────────────────────────────────────────

[id-patterns]
# Canonical ID template using tokens: {namespace}, {level.letter}, {component}
# Examples:
#   "{namespace}-{level.letter}{component}"  -> REQ-p00001
#   "{level.letter}-{component}"             -> p-00001
canonical = "{namespace}-{level.letter}{component}"

# Separator characters accepted between ID components (e.g., REQ-p00001 or REQ_p00001)
separators = ["-", "_"]

# Whether the namespace prefix (e.g., "REQ") is required for matching
prefix_optional = false

# Named alias patterns for short-form parsing
[id-patterns.aliases]
short = "{level.letter}{component}"

# ID number/name format
[id-patterns.component]
# Style: "numeric" | "alphanumeric" | "named"
style = "numeric"

# For numeric: number of digits (0 = variable length)
digits = 5

# For numeric: pad with leading zeros
leading_zeros = true

# For alphanumeric: regex pattern
# pattern = "[A-Z]{2}[0-9]{3}"

# For named: allowed characters and max length
# max_length = 32

# Assertion label configuration
[id-patterns.assertions]
label_style = "uppercase"  # "uppercase" [A-Z], "numeric" [00-99], "alphanumeric" [0-Z], "numeric_1based" [1-99]
max_count = 26             # Maximum assertions per requirement
# zero_pad = false         # Pad numeric labels with zeros
# multi_separator = "+"    # Separator for multi-assertion syntax (A+B+C)

#──────────────────────────────────────────────────────────────────────────────
# SCANNING - Unified file scanning configuration
# Each kind (spec, code, test, result, journey, docs) has its own sub-section
# with directories, file_patterns, skip_files, and skip_dirs.
# The global `skip` list applies to all kinds.
#──────────────────────────────────────────────────────────────────────────────

[scanning]
# Global skip patterns (applied to all scanning kinds)
skip = [
    "node_modules",
    ".git",
    "build",
    "dist",
    "__pycache__",
    ".venv",
    "venv",
]

# Spec file scanning
[scanning.spec]
directories = ["spec"]
file_patterns = ["*.md"]
skip_files = ["README.md", "requirements-format.md", "INDEX.md"]
skip_dirs = []
index_file = "INDEX.md"

# Code scanning (for REQ references in source code)
[scanning.code]
directories = ["src", "apps", "packages"]
source_roots = []          # Optional: root directories for import resolution

# Test file scanning
[scanning.test]
enabled = false            # Enable test mapping and coverage features
directories = ["tests"]
file_patterns = ["test_*.py", "*_test.py"]
skip_dirs = []
reference_keyword = "Verifies"
# External command for test structure discovery (optional).
# Receives test file paths on stdin (one per line) and outputs JSON on stdout:
#   [{"file": "path", "function": "name", "class": "Name|null", "line": N}]
# prescan_command = "dart run tool/list_tests.dart"

# Test result file scanning (JUnit XML, pytest JSON)
[scanning.result]
file_patterns = ["TEST-*.xml", "pytest-results.json"]
run_meta_file = ""

# User journey file scanning
[scanning.journey]
directories = ["spec"]
file_patterns = ["*.md"]

# Documentation file scanning
[scanning.docs]
directories = ["docs"]
file_patterns = ["*.md"]

#──────────────────────────────────────────────────────────────────────────────
# TERMS - Defined Terms Feature
# Controls glossary generation, term index, and term-related health checks.
#──────────────────────────────────────────────────────────────────────────────

[terms]
# Where generated glossary/index files go (relative to repo root)
output_dir = "spec/_generated"

# Which markdown emphasis delimiters count as "marked" term references
# Default: ["*", "**"] (italic and bold)
markup_styles = ["*", "**"]

# Glob patterns to skip during term reference scanning
exclude_files = []

# Severity levels for defined-terms health checks
# Each value is "error" | "warning" | "off"
[terms.severity]
duplicate = "error"           # same term defined in two locations
undefined = "warning"         # bold/italic token with no definition
unmarked = "warning"          # known term used without markup
unused = "warning"            # defined term never referenced
bad_definition = "error"      # malformed definition block
collection_empty = "warning"  # collection term with no references

#──────────────────────────────────────────────────────────────────────────────
# OUTPUT - Output formats and directory
#──────────────────────────────────────────────────────────────────────────────

[output]
# Output formats to generate (e.g. ["markdown", "html"])
formats = []

# Output directory
dir = ""

#──────────────────────────────────────────────────────────────────────────────
# ASSOCIATES - Cross-Repository Federation
# Each associate is a named entry with `path` and `namespace`.
# Relative paths resolve from the canonical repo root (worktree-safe).
#──────────────────────────────────────────────────────────────────────────────

[associates.callisto]
path = "../callisto"
namespace = "CAL"

[associates.phoenix]
path = "../phoenix"
namespace = "PHX"

#──────────────────────────────────────────────────────────────────────────────
# VALIDATION RULES
#──────────────────────────────────────────────────────────────────────────────

[validation]
# Hash mode for change detection: "full-text" | "normalized-text"
hash_mode = "normalized-text"

# Allow unresolved cross-repo references
allow_unresolved_cross_repo = false

# hash_algorithm = "sha256"         # Hash algorithm
# hash_length = 8                   # Hash truncation length (characters)
# strict_hierarchy = false          # Strict hierarchy validation

#──────────────────────────────────────────────────────────────────────────────
# HIERARCHY RULES
#──────────────────────────────────────────────────────────────────────────────

[rules.hierarchy]
# Forbid circular dependency chains (A -> B -> A)
allow_circular = false

# Allow nodes without a FILE ancestor (structural orphans)
allow_structural_orphans = false

# Allow cross-repository implementations (associated -> core)
cross_repo_implements = true
# allow_orphans = false            # Allow orphaned nodes

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

# Require ## Assertions section in requirements
require_assertions = true

# Severity for the always-on spec.no_assertions health check
# (flags requirements with zero assertions as not testable)
# Values: "info" | "warning" (default) | "error"
no_assertions_severity = "warning"

# Severity for code/test files with no traceability markers
# (Implements:, Verifies:, Validates:). null = use check default ("warning")
# no_traceability_severity = "warning"

# Allowed status values
allowed_statuses = ["Active", "Draft", "Deprecated", "Superseded"]
# content_rules = []               # Additional content validation rules

# Status role classification -- determines behavior in metrics and viewer
# Each role controls how requirements with that status are treated:
#   active:       Counted in coverage and analysis, shown in viewer
#   provisional:  Excluded from coverage, included in analysis, shown in viewer
#   aspirational: Excluded from coverage and analysis, shown in viewer
#   retired:      Excluded from everything, hidden by default in viewer
[rules.format.status_roles]
active = ["Active"]
provisional = ["Draft", "Proposed"]
aspirational = ["Roadmap", "Future"]
retired = ["Deprecated", "Superseded"]

#──────────────────────────────────────────────────────────────────────────────
# CHANGELOG
#──────────────────────────────────────────────────────────────────────────────

[changelog]
# Check current hashes against recorded changelog entries
hash_current = true

# Require changelog section to be present in spec files
present = false

# Author identity source: "gh" (GitHub CLI), "git" (git config)
id_source = "gh"

# Date format: "iso" (YYYY-MM-DD), "us" (MM/DD/YYYY), "eu" (DD/MM/YYYY)
date_format = "iso"

# Author ID format: "email" or "handle"
author_id_format = "email"

# Restrict allowed author IDs: "all" or a list of allowed values
allowed_author_ids = "all"

# Required fields in each changelog entry
[changelog.require]
reason = true
author_name = true
author_id = true
change_order = false

#──────────────────────────────────────────────────────────────────────────────
# KEYWORD SEARCH
#──────────────────────────────────────────────────────────────────────────────

[keywords]
# Minimum keyword length for extraction
min_length = 3
```

## Environment Variable Overrides

Configuration values can be overridden with environment variables:

```bash
# Pattern: ELSPAIS_<SECTION>_<KEY>
# Single underscore (_) separates sections: SECTION_KEY -> section.key
# Double underscore (__) is a literal underscore: KEY__NAME -> key_name
ELSPAIS_PROJECT_NAMESPACE=PRD
ELSPAIS_PROJECT_NAME=my-project

# Booleans are parsed automatically
ELSPAIS_VALIDATION_ALLOW__UNRESOLVED__CROSS__REPO=false

# JSON list values
ELSPAIS_SCANNING_SKIP='["node_modules", ".git"]'
```

## Minimal Configuration Examples

### Simple Repository

```toml
[project]
name = "my-project"
```

### Custom Levels

```toml
[project]
namespace = "PROJ"

[levels.epic]
rank = 1
letter = "e"
display_name = "Epic"
implements = ["epic"]

[levels.story]
rank = 2
letter = "s"
display_name = "Story"
implements = ["story", "epic"]

[levels.task]
rank = 3
letter = "t"
display_name = "Task"
implements = ["task", "story", "epic"]
```

### With Associates (Federation)

```toml
[project]
name = "core-platform"

[associates.callisto]
path = "../callisto"
namespace = "CAL"

[associates.phoenix]
path = "../phoenix"
namespace = "PHX"
```

### Type-Prefix Style Requirements

```toml
[id-patterns]
canonical = "{level.letter}-{component}"

[levels.prd]
rank = 1
letter = "PRD"
implements = ["prd"]

[levels.ops]
rank = 2
letter = "OPS"
implements = ["ops", "prd"]

[levels.dev]
rank = 3
letter = "DEV"
implements = ["dev", "ops", "prd"]

[id-patterns.component]
style = "numeric"
digits = 5
```

### Jira-Style Requirements

```toml
[project]
namespace = "PROJ"

[id-patterns]
canonical = "{namespace}-{component}"

[levels.req]
rank = 1
letter = ""
implements = ["req"]

[id-patterns.component]
style = "numeric"
digits = 0
leading_zeros = false
```
