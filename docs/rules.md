# Validation Rules Reference

elspais validates requirements against configurable rules organized into categories.

## Rule Categories

| Category | Description | Default |
|----------|-------------|---------|
| `hierarchy` | Requirement relationship rules | Enabled |
| `format` | Structure and content rules | Enabled |
| `coverage` | Per-dimension coverage severity | Enabled |
| `references` | Severity of references to non-active requirements | Enabled |
| `severity` | Severity of every check with no named setting of its own | Empty (each check keeps its default) |

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
`code.uncited_file` and `tests.uncited_file` checks on the artifact side.

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

### `references.unknown_requirement`

Implements references must point to existing requirements. This rule validates that a claimed target -- one matching a configured repository's identifier grammar -- names a requirement that repository holds.

```text
❌ ERROR [references.unknown_requirement] REQ-d00001
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

## Severity

Every check carries a severity, and every severity is a project decision. The
vocabulary is four words, and only these four:

| Severity | Description | Exit Code |
|----------|-------------|-----------|
| `off` | Not reported here — the check shows as skipped and produces no findings | 0 |
| `info` | Informational; never a failure | 0 |
| `warning` | Should be fixed | 1 (0 with `--lenient`) |
| `error` | Must be fixed | 1 |

A value outside those four is refused when the configuration is read, wherever
it is written. `off` withholds the findings as well as the verdict; to keep
seeing them without failing the run, use `info`.

### Where a severity is set

A check reads ONE setting and only one. These checks answer to a setting of
their own:

| Setting | Checks it governs |
|---------|-------------------|
| `[rules.references] <class>` | the `references.*` checks, and the `code.*_references` / `tests.*_references` status checks |
| `[rules.format] no_assertions_severity` | `spec.no_assertions` |
| `[rules.format] no_traceability_severity` | `code.no_traceability` |
| `[rules.coverage] uncredited_evidence` | `tests.uncredited_evidence` |
| `[rules.coverage] external_test_failure` | `tests.external` |
| `[terms.severity] <name>` | the `terms.*` checks |

Every other check is configured under the general `[rules.severity]` table,
keyed by the name the check reports under. Check names contain a dot, so the
key must be quoted:

```toml
[rules.severity]
"spec.parseable" = "off"
"tests.results" = "info"
"docs.config_drift" = "error"
```text

A key naming no check, and a key naming a check that has a named setting of
its own, are both refused when the configuration is read — a check reads one
setting, so putting it here would be read by nothing. `elspais docs checks`
lists every name this table accepts, with each check's default severity and
the route it takes.

Coverage tier severities (`[rules.coverage.<dimension>]`) use the same four
words; `full` defaults to `off`.

## Rule Violations

### Example Output

```text
❌ ERROR [spec.no_cycles] REQ-d00001
   Circular dependency detected: d00001 -> d00002 -> d00001
   File: spec/dev-impl.md:42

❌ ERROR [references.unknown_requirement] REQ-d00005
   Implements reference not found: p99999
   File: spec/dev-impl.md:120

ℹ️ INFO [tests.uncited_file] tests/test_widget.py
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
disables a whole category. Two mechanisms relax a rule, and only these two.

Relax an individual setting (for example `allow_structural_orphans = true`, or
`require_rationale = false`). Where a check reads a severity, `"off"` is one of
the values that severity accepts, and it withholds the check's findings as well
as its verdict; `"info"` keeps the findings visible without failing the run:

```toml
[rules.format]
no_assertions_severity = "info"

[rules.references]
retired = "off"

[terms.severity]
unused = "off"
```text

Or keep the files out of scanning altogether, so nothing in them is examined:
`[scanning] skip` applies to every kind of scan, and each kind's own
`skip_files` / `skip_dirs` narrow one of them.

There is no per-finding waiver: no inline pragma or comment in a spec file
suppresses an issue, and no baseline file records issues as expected. A rule
is relaxed for the whole project, or the file is not scanned.

An individual check is turned off by setting its severity to `off`, through
whichever of the two routes above it reads. That is the sanctioned per-check
disable: the check reports as skipped and produces no findings. Where the
findings are still wanted but the run should not fail on them, `info` is the
setting, not `off`.

## Best Practices

1. **Start strict, relax as needed**: Begin with all rules enabled
2. **Use per-repo overrides**: Let associated repos have different rules
3. **Document exceptions**: If disabling rules, document why
4. **Review orphans**: Orphaned requirements may indicate gaps
5. **Check circular dependencies**: They indicate design issues
