# Health Check Command

The `elspais health` command diagnoses configuration and repository issues, helping you identify problems before they affect your workflow.

## Quick Start

```bash
# Run all health checks
elspais health

# Check specific category only
elspais health --config    # Configuration checks
elspais health --spec      # Spec file checks
elspais health --code      # Code reference checks
elspais health --tests     # Test mapping checks
```

## Check Categories

### Configuration Checks (`--config`)

> **Note:** Configuration checks are shared with the `doctor` command. The `doctor` command runs these same checks plus additional environment diagnostics (worktree detection, associate path validation). Use `elspais doctor` for a focused setup check.

| Check | Description |
|-------|-------------|
| `config.exists` | Verifies config file exists or using defaults |
| `config.syntax` | Validates TOML syntax is correct |
| `config.required_fields` | Ensures required sections present |
| `config.pattern_tokens` | Validates pattern template tokens |
| `config.hierarchy_rules` | Checks hierarchy rules consistency |
| `config.paths_exist` | Verifies spec directories exist |

### Spec File Checks (`--spec`)

| Check | Description |
|-------|-------------|
| `spec.parseable` | All spec files can be parsed |
| `spec.no_duplicates` | No duplicate requirement IDs |
| `spec.implements_resolve` | All Implements: references resolve |
| `spec.refines_resolve` | All Refines: references resolve |
| `spec.hierarchy_levels` | Requirements follow hierarchy rules |
| `spec.orphans` | No orphan requirements (non-PRD without parents) |

### Code Reference Checks (`--code`)

| Check | Description |
|-------|-------------|
| `code.references_resolve` | Code `# Implements:` comments resolve |
| `code.coverage` | Code coverage statistics (informational) |

### Test Mapping Checks (`--tests`)

| Check | Description |
|-------|-------------|
| `tests.references_resolve` | Test REQ references resolve |
| `tests.results` | Test pass/fail status from results |
| `tests.coverage` | Test coverage statistics (informational) |

## Output Formats

### Text Output (default)

```
✓ CONFIG (6/6 checks passed)
----------------------------------------
  ✓ config.exists: Config file found: .elspais.toml
  ✓ config.syntax: TOML syntax is valid
  ✓ config.required_fields: All required configuration fields present
  ✓ config.pattern_tokens: Pattern template valid: {prefix}-{type}{id}
  ✓ config.hierarchy_rules: Hierarchy rules valid (3 levels configured)
  ✓ config.paths_exist: All spec directories exist (1 found)

✓ SPEC (6/6 checks passed)
----------------------------------------
  ✓ spec.parseable: Parsed 42 requirements with 128 assertions
  ✓ spec.no_duplicates: No duplicate requirement IDs
  ✓ spec.implements_resolve: All Implements references resolve
  ✓ spec.refines_resolve: All Refines references resolve
  ✓ spec.hierarchy_levels: All requirements follow hierarchy rules
  ✓ spec.orphans: No orphan requirements

========================================
✓ HEALTHY: 12 checks passed
========================================
```

### JSON Output (`-j` or `--json`)

```json
{
  "healthy": true,
  "summary": {
    "passed": 12,
    "failed": 0,
    "warnings": 0
  },
  "checks": [
    {
      "name": "config.exists",
      "passed": true,
      "message": "Config file found: .elspais.toml",
      "category": "config",
      "severity": "error",
      "details": {"path": ".elspais.toml"}
    }
  ]
}
```

## Command Options

| Option | Description |
|--------|-------------|
| `--config` | Run configuration checks only |
| `--spec` | Run spec file checks only |
| `--code` | Run code reference checks only |
| `--tests` | Run test mapping checks only |
| `-j`, `--json` | Output as JSON |
| `-v`, `--verbose` | Show additional details |

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All checks passed (healthy) |
| 1 | One or more errors found |

Warnings do not affect the exit code - only errors cause a non-zero exit.

## Severity Levels

- **error**: Critical issue that should be fixed
- **warning**: Issue that may indicate a problem
- **info**: Informational (e.g., coverage statistics)

## Use Cases

### CI/CD Pipeline Check

```bash
# Fail pipeline if health checks fail
elspais health || exit 1
```

### Quick Config Validation

```bash
# Just check config before making changes
elspais health --config
```

### Debugging Reference Issues

```bash
# Verbose output for debugging
elspais health --spec -v
```

### JSON Processing

```bash
# Get failed checks in CI
elspais health -j | jq '.checks | map(select(.passed == false))'
```

## Troubleshooting

### "No requirements found"

This usually means:
- The spec directory doesn't exist
- No `.md` files in the spec directory
- Files don't contain valid requirement format

Run with verbose to see details:
```bash
elspais health --spec -v
```

### "Unresolved Implements references"

A requirement references another that doesn't exist:
1. Check for typos in the requirement ID
2. Ensure the parent requirement exists
3. Check if using assertion syntax (e.g., `REQ-xxx-A`)

### "TOML syntax error"

Your `.elspais.toml` has invalid syntax:
1. Check for unclosed quotes or brackets
2. Validate with a TOML linter
3. Compare against the default config structure
