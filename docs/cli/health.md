# Health Check Command

The `elspais health` command diagnoses configuration and repository issues, helping you identify problems before they affect your workflow.

## Quick Start

```bash
# Run all health checks
elspais health

# Check specific category only
elspais health --spec      # Spec file checks
elspais health --code      # Code reference checks
elspais health --tests     # Test mapping checks
```

## Check Categories

### Configuration Checks

Configuration checks always run as part of the full health check. For focused configuration and environment diagnostics, use `elspais doctor`.

| Check | Description |
|-------|-------------|
| `config.exists` | Verifies config file exists or using defaults |
| `config.syntax` | Validates TOML syntax is correct |
| `config.required_fields` | Ensures required sections present |
| `config.pattern_tokens` | Validates pattern template tokens |
| `config.hierarchy_rules` | Checks hierarchy rules consistency |
| `config.paths_exist` | Verifies spec directories exist |
| `docs.config_drift` | Compares config schema sections against `docs/configuration.md`; reports undocumented and stale sections (runs in `elspais doctor`) |

### Spec File Checks (`--spec`)

| Check | Description |
|-------|-------------|
| `spec.parseable` | All spec files can be parsed |
| `spec.no_duplicates` | No duplicate requirement IDs |
| `spec.implements_resolve` | All Implements: references resolve |
| `spec.refines_resolve` | All Refines: references resolve |
| `spec.hierarchy_levels` | Requirements follow hierarchy rules |
| `spec.structural_orphans` | No nodes without a FILE ancestor (build bugs) |
| `spec.broken_references` | No edges targeting non-existent nodes |

### Code Reference Checks (`--code`)

| Check | Description |
|-------|-------------|
| `code.coverage` | Code coverage statistics (informational) |
| `code.unlinked` | Code references not linked to any requirement |

### Test Mapping Checks (`--tests`)

| Check | Description |
|-------|-------------|
| `tests.coverage` | Test coverage statistics with rollup (informational) |
| `tests.unlinked` | Tests not linked to any requirement |
| `tests.results` | Test pass/fail status from JUnit XML or pytest JSON results |

### UAT Checks

UAT (User Acceptance Testing) checks run automatically with `--tests` and report
coverage and results from user journey validation.

| Check | Description |
|-------|-------------|
| `uat.coverage` | Requirements validated by USER_JOURNEY nodes (informational) |
| `uat.results` | Journey pass/fail status from a CSV results file |

#### UAT Results CSV Format

Create a `uat-results.csv` file in the repository root (or configure the path
via `scanning.journey.results_file` in `.elspais.toml`):

```csv
journey_id,status
JNY-Onboard-01,pass
JNY-Onboard-02,pass
JNY-Deploy-01,fail
JNY-Deploy-02,skip
```

**Columns:**

| Column | Required | Values |
|--------|----------|--------|
| `journey_id` | Yes | The journey ID (e.g., `JNY-Onboard-01`) |
| `status` | Yes | `pass`/`passed`, `fail`/`failed`, or `skip`/`skipped` |

The file is a standard CSV with a header row. When present, `elspais health`
reports pass/fail/skip counts and flags failing journeys.

**Configuration:**

```toml
[scanning.journey]
results_file = "uat-results.csv"   # default
```

## Output Formats

### Text Output (default)

```
✓ CONFIG (6 passed, 1 skipped)
----------------------------------------
  ✓ config.exists: Config file found: .elspais.toml
  ✓ config.syntax: TOML syntax is valid
  ...

✓ TESTS (1 passed, 2 skipped)
----------------------------------------
  ~ tests.coverage: 82/87 requirements have test coverage (94.3%)
  ✓ tests.unlinked: All tests linked to requirements
  ~ tests.results: No test results found

✓ UAT (2 skipped)
----------------------------------------
  ~ uat.coverage: 25/87 requirements have UAT coverage (28.7%)
  ~ uat.results: No UAT results file found (uat-results.csv)

========================================
HEALTHY: 21/21 checks passed, 8 skipped
========================================
```

### JSON Output (`--format json`)

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

### JUnit XML Output (`--format junit`)

Produces JUnit XML that CI systems (GitHub Actions, Jenkins, GitLab CI) can ingest natively for test reporting dashboards.

**Mapping:**

| Health Concept | JUnit Element |
|----------------|---------------|
| Category (config, spec, code, tests) | `<testsuite>` |
| Individual check | `<testcase>` with `classname="elspais.health.{category}"` |
| Passing check | Empty `<testcase/>` |
| Failed check (error severity) | `<testcase>` with `<failure>` element |
| Failed check (warning severity) | `<testcase>` with `<system-err>` prefixed `WARNING:` |
| Info message | `<testcase>` with `<system-out>` |

```xml
<?xml version="1.0" encoding="UTF-8"?>
<testsuites>
  <testsuite name="config" tests="6" failures="0" errors="0">
    <testcase classname="elspais.health.config" name="config.exists"/>
    <testcase classname="elspais.health.config" name="config.syntax"/>
  </testsuite>
  <testsuite name="spec" tests="6" failures="1" errors="1">
    <testcase classname="elspais.health.spec" name="spec.parseable"/>
    <testcase classname="elspais.health.spec" name="spec.implements_resolve">
      <failure message="2 unresolved Implements references">
        REQ-d99999 referenced by REQ-d00010
      </failure>
    </testcase>
  </testsuite>
</testsuites>
```

**CI Integration Example (GitHub Actions):**

```yaml
- name: Run health checks (JUnit)
  run: elspais health --format junit -o health-results.xml

- name: Publish test results
  uses: dorny/test-reporter@v1
  if: always()
  with:
    name: elspais health
    path: health-results.xml
    reporter: java-junit
```

### SARIF Output (`--format sarif`)

Produces [SARIF v2.1.0](https://docs.oasis-open.org/sarif/sarif/v2.1.0/sarif-v2.1.0.html) JSON for GitHub Code Scanning and other static analysis dashboards. Only failing checks are emitted as results; passing checks are omitted.

**Mapping:**

| Health Concept | SARIF Element |
|----------------|---------------|
| Unique failing check name | `reportingDescriptor` in `tool.driver.rules[]` |
| Individual `HealthFinding` | `result` in `results[]` |
| Severity `error` | `level: "error"` |
| Severity `warning` | `level: "warning"` |
| Severity `info` | `level: "note"` |
| Finding with `file_path` | `physicalLocation` with `artifactLocation.uri` |
| Finding with `line` | `region.startLine` |
| Coverage stats | `run.properties` (`passed`, `failed`, `warnings`) |

```json
{
  "$schema": "https://docs.oasis-open.org/sarif/sarif/v2.1.0/cos02/schemas/sarif-schema-2.1.0.json",
  "version": "2.1.0",
  "runs": [
    {
      "tool": {
        "driver": {
          "name": "elspais",
          "informationUri": "https://github.com/anspar-org/elspais",
          "rules": [
            {
              "id": "spec.implements_resolve",
              "shortDescription": {
                "text": "All Implements references resolve"
              }
            }
          ]
        }
      },
      "results": [
        {
          "ruleId": "spec.implements_resolve",
          "level": "error",
          "message": {
            "text": "REQ-d99999 referenced by REQ-d00010"
          },
          "locations": [
            {
              "physicalLocation": {
                "artifactLocation": {
                  "uri": "spec/dev-spec.md"
                },
                "region": {
                  "startLine": 42
                }
              }
            }
          ]
        }
      ],
      "properties": {
        "passed": 11,
        "failed": 1,
        "warnings": 0
      }
    }
  ]
}
```

**CI Integration Example (GitHub Code Scanning):**

```yaml
- name: Run health checks (SARIF)
  run: elspais health --format sarif -o health-results.sarif
  continue-on-error: true

- name: Upload SARIF
  uses: github/codeql-action/upload-sarif@v3
  if: always()
  with:
    sarif_file: health-results.sarif
    category: elspais-health
```

## Command Options

| Option | Description |
|--------|-------------|
| `--spec` | Run spec file checks only |
| `--code` | Run code reference checks only |
| `--tests` | Run test mapping checks only |
| `--format` | Output format: `text`, `markdown`, `json`, `junit`, `sarif` |
| `--lenient` | Allow warnings without affecting exit code |
| `-v`, `--verbose` | Show additional details |
| `--skip-passing-details` | Hide details for passing checks (default) |
| `--include-passing-details` | Show full details for passing checks |

## Passing Check Detail Control

By default, `elspais health` suppresses verbose detail for passing checks (`--skip-passing-details`). Use `--include-passing-details` to include them. The two flags are mutually exclusive.

The effect varies by output format:

| Format | Default (`--skip-passing-details`) | With `--include-passing-details` |
|--------|-------------------------------------|----------------------------------|
| text | Aggregate summary message only | Adds verbose detail keys for each passing check |
| markdown | Table with aggregate status | Adds a `<details>` block with per-finding list |
| json | Full findings always included | No change |
| junit | Empty `<testcase/>` element | Adds `<system-out>` with finding messages |
| sarif | Omits passing checks always | No change |

JSON and SARIF formats are unaffected by this flag: JSON always includes full findings, and SARIF always omits passing checks.

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All checks passed (healthy) |
| 1 | One or more errors found |

Most configuration issues are classified as errors and cause a non-zero exit.
Only advisory checks (e.g., cross-repo paths in committed config) use warning severity.

## Severity Levels

- **error**: Configuration or validation issue that causes non-zero exit
- **warning**: Advisory issue (does not affect exit code)
- **info**: Informational (e.g., coverage statistics)

## Use Cases

### CI/CD Pipeline Check

```bash
# Fail pipeline if health checks fail
elspais health || exit 1
```

### Quick Config Validation

```bash
# Just check config and environment setup
elspais doctor
```

### Debugging Reference Issues

```bash
# Verbose output for debugging
elspais health --spec -v
```

### JSON Processing

```bash
# Get failed checks in CI
elspais health --format json | jq '.checks | map(select(.passed == false))'
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
