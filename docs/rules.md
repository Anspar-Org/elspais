# Validation Rules Reference

elspais validates requirements against configurable rules organized into categories.

## Rule Categories

| Category | Description | Default |
|----------|-------------|---------|
| `hierarchy` | Requirement relationship rules | Enabled |
| `format` | Structure and content rules | Enabled |
| `coverage` | Per-dimension coverage severity | Enabled |
| `references` | Severity of references to non-active requirements | Enabled |

## Hierarchy Rules

Control how requirements can reference each other.

### Which levels may implement which

Allowed "Implements" relationships are not a rule setting. Each level declares
its own `implements` list in its `[levels.<name>]` section:

```toml
[levels.prd]
rank = 1
letter = "p"
implements = ["prd"]        # PRD can implement other PRD

[levels.ops]
rank = 2
letter = "o"
implements = ["ops", "prd"] # OPS can implement OPS or PRD

[levels.dev]
rank = 3
letter = "d"
implements = ["dev", "ops", "prd"]  # DEV can implement anything
```text

**What's forbidden:** anything not listed. With the configuration above,
`prd -> dev` and `prd -> ops` are both rejected.

### `allow_circular`

Control circular dependency chains:

```toml
[rules.hierarchy]
allow_circular = false  # A -> B -> C -> A is forbidden
```text

When `false`, elspais detects and reports cycles like:

```text
REQ-d00001 implements REQ-d00002
REQ-d00002 implements REQ-d00003
REQ-d00003 implements REQ-d00001  ✗ Circular!
```text

### `allow_structural_orphans`

Control nodes that have no FILE ancestor — nodes that failed to wire into the
file structure at all. These indicate build pipeline bugs, not traceability
gaps.

```toml
[rules.hierarchy]
allow_structural_orphans = false
```text

When `false`, the `spec.structural_orphans` check reports any such node as an
error. Requirements that simply have no `Implements:` reference are a separate
concern: they are unlinked, not structural orphans, and are reported by the
`code.unlinked` and `tests.unlinked` checks on the artifact side.

### `cross_repo_implements`

Allow cross-repository references:

```toml
[rules.hierarchy]
cross_repo_implements = true  # Associated can implement core REQs
```text

## Format Rules

Control requirement structure and content.

### `require_hash`

Require hash footer on all requirements:

```toml
[rules.format]
require_hash = true
```text

Expects format:

```markdown
*End* *Requirement Title* | **Hash**: a1b2c3d4
```text

### `require_rationale`

Require Rationale section:

```toml
[rules.format]
require_rationale = true
```text

Expects:

```markdown
**Rationale**: Why this requirement exists...
```text

### `require_assertions` (v0.9.0+)

Require an `## Assertions` section in requirements:

```toml
[rules.format]
require_assertions = true
```text

Expects:

```markdown
## Assertions

A. The system SHALL do something.
B. The system SHALL do another thing.
```text

### `require_status`

Require Status field in header:

```toml
[rules.format]
require_status = true

[rules.format.status_roles]
active = ["Active"]
provisional = ["Draft", "Proposed"]
aspirational = ["Roadmap", "Future", "Idea"]
retired = ["Deprecated", "Superseded", "Rejected"]
```text

Expects:

```markdown
**Level**: Dev | **Status**: Active
```text

The set of accepted statuses is the union of the `status_roles` lists. The
`spec.format_rules` check fails when a status is not among them.

### Assertion labels

Assertion labels must match the configured pattern (`label_style` in
`[id-patterns.assertions]`). A malformed label fails `spec.format_rules`:

```text
❌ ERROR [spec.format_rules] REQ-d00001
   Invalid assertion label format: 1A
```text

## Hash Rules

### `spec.hash_integrity`

When a requirement has a hash footer, the hash is verified against the content. A mismatch indicates the requirement was modified without updating the hash.

```text
⚠️ WARNING [spec.hash_integrity] REQ-d00001
   Hash mismatch: expected a1b2c3d4, found x9y8z7w6
```text

Fix with: `elspais fix REQ-d00001`

## Link Rules

### `spec.broken_references`

Implements references must point to existing requirements. This rule validates that referenced requirement IDs exist.

```text
❌ ERROR [spec.broken_references] REQ-d00001
   Implements reference not found: p99999
```text

## ID Rules

### `spec.no_duplicates`

Detects when the same requirement ID appears multiple times across specification files. The parser keeps the first occurrence and ignores duplicates, surfacing a warning that becomes an error during validation.

```text
❌ ERROR [spec.no_duplicates] REQ-d00001
   Duplicate requirement ID (first seen in spec/dev-impl.md:42)
   File: spec/dev-other.md:15
```text

**How to fix:**

- Rename one of the conflicting requirements to a unique ID
- Remove the duplicate if it was created by mistake

This rule cannot be disabled as duplicate IDs cause ambiguous references.

## Rule Violations

Violations are reported with severity levels:

| Severity | Description | Exit Code |
|----------|-------------|-----------|
| `error` | Must be fixed | 1 |
| `warning` | Should be fixed | 0 |
| `info` | Informational | 0 |

### Example Output

```text
❌ ERROR [spec.no_cycles] REQ-d00001
   Circular dependency detected: d00001 -> d00002 -> d00001
   File: spec/dev-impl.md:42

❌ ERROR [spec.broken_references] REQ-d00005
   Implements reference not found: p99999
   File: spec/dev-impl.md:120

ℹ️ INFO [tests.unlinked] tests/test_widget.py
   Test file has no traceability markers

⚠️ WARNING [spec.hash_integrity] REQ-p00003
   Hash mismatch: expected a1b2c3d4, found x9y8z7w6
   File: spec/prd-core.md:156
```text

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
```text

## Per-Repo Overrides

Associated repositories can override core rules:

**Core repo** (strict):

```toml
[rules.hierarchy]
allow_structural_orphans = false
allow_circular = false

[rules.format]
require_rationale = true
require_assertions = true
```text

**Associated repo** (permissive for innovation):

```toml
[rules.hierarchy]
allow_structural_orphans = true  # Allow experimental requirements

[rules.format]
require_rationale = false  # Not required during development
```text

## Relaxing Rules

Rule categories are sub-tables, not on/off switches — there is no boolean that
disables a whole category. Relax individual settings instead (for example
`allow_structural_orphans = true`, or `require_rationale = false`), or suppress
expected issues with inline comments in spec files.

## Best Practices

1. **Start strict, relax as needed**: Begin with all rules enabled
2. **Use per-repo overrides**: Let associated repos have different rules
3. **Document exceptions**: If disabling rules, document why
4. **Review orphans**: Orphaned requirements may indicate gaps
5. **Check circular dependencies**: They indicate design issues
