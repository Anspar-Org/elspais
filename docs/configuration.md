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

# Project name (REQUIRED; non-empty; used in reports). load_config() rejects
# configs that omit this field or leave it blank. `elspais init` generates a
# starter config with `name` auto-derived from the invocation directory.
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

# Configured test targets - result ingestion and coverage attribution.
# See `elspais docs test-targets` for full documentation.
#
# Note: per-PR selectivity (running/marking only a subset of these targets
# as fresh, e.g. for a PR that only touched one package) is driven entirely
# by the `--targets NAME ...` CLI flag on `checks`/`summary`/`trace` -- there
# is no config field for it. All targets declared here are eligible; which
# ones are "fresh" for a given invocation is a per-command-line decision, not
# a persistent config setting. See `elspais docs test-targets` (Per-PR
# selectivity section).
[[scanning.test.targets]]
name     = "app"
cwd      = "app"                    # relative to repo root; empty = repo root
command  = "flutter test --machine" # omit in CI (tests already ran)
reporter = "flutter-machine"        # stdout-channel reporter
match    = "source"                 # "source" (default) | "aggregate"
coverage = "coverage/lcov.info"     # optional; lcov or coverage.py JSON

# File-channel reporter example (junit XML):
# [[scanning.test.targets]]
# name     = "pytest"
# reporter = "junit"
# results  = "results/*.xml"        # glob relative to cwd
# match    = "source"

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
canonical_form = "warning"    # term used in non-canonical form (case/spelling variant)
changed = "warning"           # definition content changed, pending review

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
#
# Declaring an associate also enables cross-repo template instantiation:
# a downstream `Satisfies: <UPSTREAM>` clones the upstream **Template**
# REQ subtree into this repo with composite IDs (declaring_id::original_id)
# and wires a cross-graph INSTANCE edge to the original. CODE/TEST in the
# upstream repo may target template assertions directly (Implements:,
# Verifies:); that evidence is "cross-cutting" -- it applies to every
# satisfier of the template via the INSTANCE edges, so coverage flows
# automatically without per-instance re-implementation. See
# `elspais docs satisfies` for the full pattern and validation matrix.
#
# Associates also enable top-down `Integrates: <ASSOCIATE-REQ>` references:
# a consumer requirement declares that its implementation is provided by a
# requirement in a linked library. It is external-only (the target must
# resolve to an associate; a same-repo target is a broken reference), the
# library is never modified, and the consumer inherits the library
# requirement's implemented/verified coverage via an INTEGRATES edge wired
# during federation. See `elspais docs graph-model`.
#──────────────────────────────────────────────────────────────────────────────

[associates.callisto]
path = "../callisto"
namespace = "CAL"
# color = "#7c3aed"                  # Optional: badge color for this namespace

[associates.phoenix]
path = "../phoenix"
namespace = "PHX"

#──────────────────────────────────────────────────────────────────────────────
# FEDERATION - Write / generation surface control
# These flags opt in to writing or indexing associate repos during build.
# Read operations (checks, summary, cross-repo resolution) always federate
# regardless of these flags; they only affect write and generation surfaces.
#
#   write_associates  (default: false) — allow `elspais fix` to modify spec
#                     files inside associate repos.
#   index_associates  (default: false) — include associate requirements in
#                     generated artifacts (e.g. traceability matrices, glossary).
#──────────────────────────────────────────────────────────────────────────────

[federation]
write_associates = false
index_associates = false

#──────────────────────────────────────────────────────────────────────────────
# STATUSES - Optional Per-Status Metadata
# Attach color (and future metadata) to status names referenced by
# [rules.format.status_roles]. Unspecified statuses fall back to a
# deterministic hash-derived color.
#──────────────────────────────────────────────────────────────────────────────

[statuses.Active]
color = "#198754"

[statuses.Legacy]
color = "#6c757d"

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

### User Journey UAT Setup

When journey files share the `spec/` directory with requirement files, the spec
scanner would attempt to parse them as requirements. Prevent this by adding the
journey subdirectory to `[scanning.spec].skip_dirs`:

```toml
[scanning.spec]
directories = ["spec"]
file_patterns = ["*.md"]
skip_files = ["README.md", "INDEX.md"]
skip_dirs = ["user-journeys"]   # keep spec scanner out of the journeys folder

[scanning.journey]
directories = ["spec/user-journeys"]
file_patterns = ["*.md"]
```

To feed Playwright (or any JUnit-emitting) test results into journey/step
UAT coverage, add a `[[scanning.test.targets]]` entry with `reporter = "junit"`:

```toml
[scanning.test]
enabled = true
# ...

# Playwright E2E suite writing JUnit XML output
[[scanning.test.targets]]
name     = "playwright"
reporter = "junit"
results  = "test-results/junit.xml"   # glob relative to cwd; empty = repo root
match    = "aggregate"                 # "aggregate" for a whole-suite pass/fail
```

With this in place, a test file that declares `// Verifies: JNY-OQ-Login-01/step-2`
links its results to journey step 2, and the journey verdict rolls up into the
`uat_verified` dimension on any requirement the journey `Validates:`.

For **per-spec** binding instead of a whole-suite verdict, use
`match = "source"` -- but the JUnit XML must carry a per-`<testcase>` `file`
attribute naming each test's real source path, and the specs must be scanned as
TEST nodes (via `[scanning.test].prescan_command`). Playwright's reporter omits
`file`, so the runner injects it before elspais ingests the XML. See
`elspais docs test-targets` (the *Playwright / TypeScript* recipe) for the full
setup.

See `elspais docs graph-model` for the full STEP/JOURNEY model and roll-up rules.
See `elspais docs test-targets` for all `[[scanning.test.targets]]` fields.

### Coverage-Only Target with Per-Test Attribution (dogfood pattern)

elspais's own suite (this repo's `.elspais.toml`) demonstrates a
coverage-only target that still gets per-test line attribution
(`code_tested.direct`) without a machine-readable results file:

```toml
[scanning.test]
# ...

[[scanning.test.targets]]
name     = "elspais-unit"
coverage = ".results/coverage.json"
```

```text
# pyproject.toml
[tool.coverage.json]
show_contexts = true   # export the per-line contexts map

# Do NOT also set [tool.coverage.run] dynamic_context = "test_function" --
# that is coverage.py's own (incompatible) context switcher and silently
# overrides pytest-cov's nodeid-shaped contexts, leaving code_tested.direct
# at 0 everywhere even though contexts are present.
```

The `.githooks/pre-commit` hook runs pytest with `--cov-context=test`
(pytest-cov's per-test dynamic context, keyed by nodeid + `|run`/`|setup`/
`|teardown`) to populate those contexts. No `reporter`/`results` fields are
set because there's no `--json-report`/`--junit-xml` step -- `Verifies:`
wiring comes entirely from source-scanned `# Verifies:` comments in test
files, independent of this target. See `elspais docs test-targets`
(*Python/pytest Recipe*, *Coverage-only target with per-test direct
attribution*) for the full recipe and gotchas.

### Coverage Severity & Theme Colors

`[rules.coverage]` maps each coverage dimension's tier to a severity
(`"ok"`, `"info"`, `"warning"`, or `"error"`), which in turn drives both
health-check exit behavior and the viewer's badge/legend colors:

```toml
[rules.coverage.implemented]
full_direct   = "ok"       # default
full_indirect = "info"     # default
partial       = "warning"  # default
none          = "error"    # default
failing       = "error"    # default

# uat_coverage/uat_verified default none/partial to "info" (UAT gaps are
# lower-priority than code gaps); verified defaults none to "warning".
```

Severity strings are not colors themselves -- the viewer resolves each
severity to a color via a fixed catalog in the packaged `theme.toml`
(`severity.ok`, `severity.info`, `severity.warning`, `severity.error`, each
with a `color_key` such as `green`/`yellow-green`/`yellow`/`red` that maps to
themed CSS custom properties, e.g. `--val-green-bg`, with separate light/dark
values). This catalog is internal (not user-configurable in
`.elspais.toml`); the `[rules.coverage]` severity strings above are the only
per-project lever. A `failing` tier (coverage exists but results are
failing) is a separate overlay checked ahead of the severity map -- it does
not reuse the `error` severity color in the viewer toolbar's coverage filter,
which uses its own hardcoded color for that state. See `elspais docs checks`
(*Dimension tiers*) for the tier model and `graph/aggregation.py` for the
single shared aggregation these severities feed.
