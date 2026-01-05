# Validation Rules Reference

elspais validates requirements against configurable rules organized into categories.

## Rule Categories

| Category | Description | Default |
|----------|-------------|---------|
| `hierarchy` | Requirement relationship rules | Enabled |
| `format` | Structure and content rules | Enabled |
| `traceability` | Code-to-requirement linking | Enabled |
| `naming` | Title and naming conventions | Enabled |

## Hierarchy Rules

Control how requirements can reference each other.

### `allowed_implements`

Defines valid "Implements" relationships:

```toml
[rules.hierarchy]
allowed_implements = [
    "dev -> ops, prd",   # DEV can implement OPS or PRD
    "ops -> prd",        # OPS can implement only PRD
    "prd -> prd",        # PRD can implement other PRD
]
```

**Syntax:** `"source_type -> target_type1, target_type2"`

**What's forbidden:**
- Anything not explicitly listed
- `prd -> dev` (PRD cannot implement DEV)
- `prd -> ops` (PRD cannot implement OPS)

### Permissive Example

Allow same-level implementations:

```toml
[rules.hierarchy]
allowed_implements = [
    "dev -> dev, ops, prd",  # DEV can implement anything
    "ops -> ops, prd",       # OPS can implement OPS or PRD
    "prd -> prd",            # PRD can implement PRD
]
```

### `allow_circular`

Control circular dependency chains:

```toml
[rules.hierarchy]
allow_circular = false  # A -> B -> C -> A is forbidden
```

When `false`, elspais detects and reports cycles like:
```
REQ-d00001 implements REQ-d00002
REQ-d00002 implements REQ-d00003
REQ-d00003 implements REQ-d00001  ✗ Circular!
```

### `allow_orphans`

Control orphaned requirements:

```toml
[rules.hierarchy]
allow_orphans = false  # All DEV/OPS must implement something
```

When `false`:
- Root PRD requirements are allowed (they have no parent)
- All DEV requirements must implement at least one other requirement
- All OPS requirements must implement at least one PRD

### `max_depth`

Limit implementation chain depth:

```toml
[rules.hierarchy]
max_depth = 5  # A -> B -> C -> D -> E -> F is forbidden
```

Prevents excessively deep hierarchies.

### `cross_repo_implements`

Allow cross-repository references:

```toml
[rules.hierarchy]
cross_repo_implements = true  # Associated can implement core REQs
```

## Format Rules

Control requirement structure and content.

### `require_hash`

Require hash footer on all requirements:

```toml
[rules.format]
require_hash = true
```

Expects format:
```markdown
*End* *Requirement Title* | **Hash**: a1b2c3d4
```

### `require_rationale`

Require Rationale section:

```toml
[rules.format]
require_rationale = true
```

Expects:
```markdown
**Rationale**: Why this requirement exists...
```

### `require_assertions` (v0.9.0+)

Require an `## Assertions` section in requirements:

```toml
[rules.format]
require_assertions = true
```

Expects:
```markdown
## Assertions

A. The system SHALL do something.
B. The system SHALL do another thing.
```

### `acceptance_criteria` (v0.9.0+)

Control handling of legacy Acceptance Criteria format:

```toml
[rules.format]
acceptance_criteria = "warn"  # "allow" | "warn" | "error"
```

- `allow`: Silently accept old format
- `warn`: Log a warning but continue
- `error`: Fail validation

### `require_shall` (v0.9.0+)

Require SHALL keyword in assertion text:

```toml
[rules.format]
require_shall = true
```

### `labels_sequential` (v0.9.0+)

Require assertion labels to be sequential (A, B, C... not A, C, D):

```toml
[rules.format]
labels_sequential = true
```

### `labels_unique` (v0.9.0+)

Forbid duplicate assertion labels:

```toml
[rules.format]
labels_unique = true
```

### `placeholder_values` (v0.9.0+)

Values indicating removed/deprecated assertions (to maintain label sequence):

```toml
[rules.format]
placeholder_values = ["obsolete", "removed", "deprecated", "N/A", "n/a", "-", "reserved"]
```

Example of a placeholder assertion:
```markdown
## Assertions

A. The system SHALL do something.
B. Removed.
C. The system SHALL do another thing.
```

### `require_status`

Require Status field in header:

```toml
[rules.format]
require_status = true
allowed_statuses = ["Active", "Draft", "Deprecated", "Superseded"]
```

Expects:
```markdown
**Level**: Dev | **Status**: Active
```

Violation `format.status_valid` is raised when status is not in `allowed_statuses`.

### `assertion_label` (v0.9.0+)

Assertion labels must match the configured pattern (`label_style` in `[patterns.assertions]`):

Violation `format.assertion_label` is raised for invalid label formats:
```
❌ ERROR [format.assertion_label] REQ-d00001
   Invalid assertion label format: 1A
```

## Hash Rules

### `hash.mismatch`

When a requirement has a hash footer, the hash is verified against the content. A mismatch indicates the requirement was modified without updating the hash.

```
⚠️ WARNING [hash.mismatch] REQ-d00001
   Hash mismatch: expected a1b2c3d4, found x9y8z7w6
```

Fix with: `elspais hash update REQ-d00001`

## Link Rules

### `link.broken`

Implements references must point to existing requirements. This rule validates that referenced requirement IDs exist.

```
❌ ERROR [link.broken] REQ-d00001
   Implements reference not found: p99999
```

For associated repositories, use `--core-repo` to validate cross-repo references.

## ID Rules

### `id.duplicate` (v0.9.2+)

Detects when the same requirement ID appears multiple times across specification files. The parser keeps the first occurrence and ignores duplicates, surfacing a warning that becomes an error during validation.

```
❌ ERROR [id.duplicate] REQ-d00001
   Duplicate requirement ID (first seen in spec/dev-impl.md:42)
   File: spec/dev-other.md:15
```

**How to fix:**
- Rename one of the conflicting requirements to a unique ID
- Remove the duplicate if it was created by mistake

This rule cannot be disabled as duplicate IDs cause ambiguous references.

## Traceability Rules

Control code-to-requirement linking.

### `require_code_link`

Require DEV requirements to have at least one code reference:

```toml
[rules.traceability]
require_code_link = true
```

elspais scans code for patterns like:
```python
# IMPLEMENTS: REQ-d00001
```

### `scan_for_orphans`

Warn about REQ IDs in code that have no matching spec:

```toml
[rules.traceability]
scan_for_orphans = true
```

Detects:
```python
# IMPLEMENTS: REQ-d99999  # Warning: No such requirement
```

## Naming Rules

Control requirement titles.

### `title_min_length` / `title_max_length`

Enforce title length:

```toml
[rules.naming]
title_min_length = 10
title_max_length = 100
```

### `title_pattern`

Require titles to match a pattern:

```toml
[rules.naming]
title_pattern = "^[A-Z].*"  # Must start with capital letter
```

## Rule Violations

Violations are reported with severity levels:

| Severity | Description | Exit Code |
|----------|-------------|-----------|
| `error` | Must be fixed | 1 |
| `warning` | Should be fixed | 0 |
| `info` | Informational | 0 |

### Example Output

```
❌ ERROR [hierarchy.circular] REQ-d00001
   Circular dependency detected: d00001 -> d00002 -> d00001
   File: spec/dev-impl.md:42

❌ ERROR [link.broken] REQ-d00005
   Implements reference not found: p99999
   File: spec/dev-impl.md:120

⚠️ WARNING [hierarchy.orphan] REQ-d00010
   DEV requirement has no Implements reference
   File: spec/dev-orphan.md:1

⚠️ WARNING [hash.mismatch] REQ-p00003
   Hash mismatch: expected a1b2c3d4, found x9y8z7w6
   File: spec/prd-core.md:156

ℹ️ INFO [naming.title_pattern] REQ-o00007
   Title doesn't start with capital letter
   File: spec/ops-deploy.md:78
```

## Custom Rules (Future)

For advanced use cases, define custom rules:

```toml
[[rules.custom.rule]]
name = "security-review"
description = "Security requirements must have Review status"
condition = "type == 'prd' and 'security' in tags"
constraint = "status in ['Review', 'Active']"
severity = "error"

[[rules.custom.rule]]
name = "deprecated-successor"
description = "Deprecated requirements must have successor"
condition = "status == 'Deprecated'"
constraint = "superseded_by is not null"
severity = "warning"
```

## Per-Repo Overrides

Associated repositories can override core rules:

**Core repo** (strict):
```toml
[rules.hierarchy]
allow_orphans = false
allow_circular = false

[rules.format]
require_rationale = true
require_assertions = true
```

**Associated repo** (permissive for innovation):
```toml
[rules.hierarchy]
allow_orphans = true  # Allow experimental requirements

[rules.format]
require_rationale = false  # Not required during development
```

## Disabling Rules

Disable entire categories:

```toml
[rules]
hierarchy = true
format = true
traceability = false  # Disable traceability checks
naming = false        # Disable naming checks
```

Or use the CLI:

```bash
elspais validate --skip-rule hierarchy.circular
elspais validate --skip-rule format.require_rationale
```

## Best Practices

1. **Start strict, relax as needed**: Begin with all rules enabled
2. **Use per-repo overrides**: Let associated repos have different rules
3. **Document exceptions**: If disabling rules, document why
4. **Review orphans**: Orphaned requirements may indicate gaps
5. **Check circular dependencies**: They indicate design issues
