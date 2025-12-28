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
cross_repo_implements = true  # Sponsor can implement core REQs
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

### `require_acceptance`

Require Acceptance Criteria section:

```toml
[rules.format]
require_acceptance = true
```

Expects:
```markdown
**Acceptance Criteria**:
- Criterion 1
- Criterion 2
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

⚠️ WARNING [format.require_rationale] REQ-p00003
   Missing Rationale section
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

Sponsor repositories can override core rules:

**Core repo** (strict):
```toml
[rules.hierarchy]
allow_orphans = false
allow_circular = false

[rules.format]
require_rationale = true
require_acceptance = true
```

**Sponsor repo** (permissive for innovation):
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
2. **Use per-repo overrides**: Let sponsors have different rules
3. **Document exceptions**: If disabling rules, document why
4. **Review orphans**: Orphaned requirements may indicate gaps
5. **Check circular dependencies**: They indicate design issues
