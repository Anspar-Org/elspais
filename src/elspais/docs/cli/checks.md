# CHECKS

The `elspais checks` command performs **traceability verification** — confirming that requirements are properly traced through implementation, tests, and validation results. In FDA CSV (Computer System Validation) terms, this is the automated equivalent of verifying a Requirements Traceability Matrix (RTM).

## Quick Start

```bash
# Run all checks
elspais checks

# Check specific category only
elspais checks --spec      # Spec file checks
elspais checks --code      # Code reference checks
elspais checks --tests     # Test mapping checks
```

## Check Categories

### Configuration Checks

Configuration checks always run as part of traceability verification. For focused configuration and environment diagnostics, use `elspais doctor`.

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
| `spec.no_assertions` | Requirements with no assertions (not testable); default severity: warning |

#### `spec.no_assertions` — Not Testable Requirements

The `spec.no_assertions` check flags requirements that have no assertions defined.
A requirement with no assertions cannot be covered by automated tests or UAT, making
it untraceable at the assertion level.

- **Default severity**: warning (does not cause a non-zero exit by itself)
- **Always on**: this check runs unconditionally, unlike `require_assertions` (which
  is opt-in and produces an error when enabled)
- **Gaps report**: requirements flagged by this check appear in `elspais gaps` with
  the label `NOT TESTABLE (no assertions)` under the `no_assertions` gap type

**Configuration** — adjust severity via `[rules.format]` in `.elspais.toml`:

```toml
[rules.format]
no_assertions_severity = "info"   # or "warning" (default) or "error"
```

**Comparison with `require_assertions`:**

| | `spec.no_assertions` | `require_assertions = true` |
|---|---|---|
| Always runs | Yes | No (opt-in) |
| Default severity | warning | error |
| Purpose | Surface untestable REQs for review | Enforce assertions as a hard rule |

Use `require_assertions = true` when you want assertions to be mandatory for all
requirements. Use `no_assertions_severity` to tune the visibility of the advisory
check that is always present.

### Code Reference Checks (`--code`)

| Check | Description |
|-------|-------------|
| `code.coverage` | Code coverage statistics (informational) |
| `code.unlinked` | Code files with no traceability markers (no `# Implements:` or `# Verifies:` comments); severity: info |
| `code.retired_references` | Code referencing requirements with retired status (Deprecated, Superseded, Rejected); default severity: warning |
| `code.provisional_references` | Code referencing requirements with provisional status (Draft, Proposed); default severity: info |
| `code.aspirational_references` | Code referencing requirements with aspirational status (Roadmap, Future, Idea); default severity: info |

### Test Mapping Checks (`--tests`)

| Check | Description |
|-------|-------------|
| `tests.coverage` | Test coverage statistics with rollup (informational) |
| `tests.unlinked` | Test files with no traceability markers (no REQ-xxx patterns or `Verifies` comments); severity: info |
| `tests.results` | Test pass/fail status from JUnit XML or pytest JSON results |
| `tests.retired_references` | Tests referencing requirements with retired status (Deprecated, Superseded, Rejected); default severity: warning |
| `tests.provisional_references` | Tests referencing requirements with provisional status (Draft, Proposed); default severity: info |
| `tests.aspirational_references` | Tests referencing requirements with aspirational status (Roadmap, Future, Idea); default severity: info |

#### Reference Status Checks — Retired, Provisional, Aspirational

The `*.retired_references`, `*.provisional_references`, and
`*.aspirational_references` checks (for both `code` and `tests` categories)
flag traceability links that target requirements whose status suggests the
reference may be stale or premature:

- **Retired** (Deprecated, Superseded, Rejected) — the requirement is no
  longer valid; code or tests referencing it may need cleanup.
- **Provisional** (Draft, Proposed) — the requirement is not yet approved;
  references are premature but may be intentional during development.
- **Aspirational** (Roadmap, Future, Idea) — the requirement is planned
  but not committed; references are informational.

**`--status` interaction:** Using `--status Draft` promotes Draft requirements
to active-like status, so `code.provisional_references` and
`tests.provisional_references` will not flag Draft references when
`--status Draft` is used.

**Configuration** — adjust severity via `[rules.references]` in `.elspais.toml`:

```toml
[rules.references]
retired = "warning"       # info | warning | error
provisional = "info"      # info | warning | error
aspirational = "info"     # info | warning | error
```

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

The file is a standard CSV with a header row. When present, `elspais checks`
reports pass/fail/skip counts and flags failing journeys.

**Configuration:**

```toml
[scanning.journey]
results_file = "uat-results.csv"   # default
```

## Coverage Dimensions

Coverage checks report six **dimensions**, each tracking how thoroughly
requirements are implemented, tested, and validated. Every dimension has
two tiers of confidence:

- **direct** — the link names specific assertions (high confidence)
- **indirect** — the link targets the whole requirement, implying all assertions (lower confidence)

### The six dimensions

| Dimension | What it measures |
|-----------|-----------------|
| `implemented` | CODE or child-REQ covers assertions |
| `tested` | TEST nodes linked to assertions |
| `verified` | TEST results PASSING for those assertions |
| `uat_coverage` | USER_JOURNEY validates assertions |
| `uat_verified` | USER_JOURNEY results PASSING for those assertions |
| `code_tested` | Implementation source lines hit by line-coverage data |

### How coverage sources map to dimensions

The system classifies *how specifically* coverage was claimed:

| Source | When | Dimension effect |
|--------|------|-----------------|
| `DIRECT` | TEST or CODE names specific assertions (`REQ-xxx-A`) | `implemented.direct`, `tested.direct` |
| `EXPLICIT` | Child REQ names specific assertions (`Implements: REQ-xxx-A+B`) | `implemented.direct` |
| `INFERRED` | Child REQ targets whole parent (`Implements: REQ-xxx`) | `implemented.indirect` only |
| `INDIRECT` | TEST targets whole REQ (no assertion labels) | `tested.indirect` only |
| `UAT_EXPLICIT` | JNY names specific assertions (`Validates: REQ-xxx-A`) | `uat_coverage.direct` |
| `UAT_INFERRED` | JNY targets whole REQ (`Validates: REQ-xxx`) | `uat_coverage.indirect` only |

After collection, `implemented.direct = DIRECT | EXPLICIT` and
`implemented.indirect = DIRECT | EXPLICIT | INFERRED`.

### Roll-up: how RESULT nodes contribute

RESULT nodes do **not** add coverage — they add **verification**. A RESULT
inherits the assertion targets from its parent TEST's edge:

```text
REQ (assertion "A")
  |
  +-- VERIFIES (assertion_targets=["A"]) --> TEST
                                               |
                                               +-- RESULT (status="passed")
```

What gets credited:

- `tested.direct` += "A" — from the VERIFIES edge (assertion-targeted)
- `verified.direct` += "A" — from the RESULT with `status=passed`

If the RESULT is absent or failing, `tested` still gets credit but `verified`
does not. The same pattern applies to UAT: a journey RESULT populates
`uat_verified` but not `uat_coverage`.

### Dimension tiers

Each dimension resolves to a **tier** that drives severity and UI color:

| Tier | Meaning |
|------|---------|
| `none` | No coverage at all |
| `partial` | Some assertions covered, not all |
| `full-indirect` | All assertions covered, but only via indirect links |
| `full-direct` | All assertions covered with assertion-level specificity |
| `failing` | Coverage exists but results are failing |

### `code_tested` — line coverage

Unlike the other five dimensions, `code_tested` counts **source lines** rather
than assertions. It cross-references implementation line ranges (from
`Implements:` edges to CODE nodes) against file-level line-coverage data
(LCOV or coverage.json). `code_tested.direct` is always 0 because per-test
line attribution is not yet implemented.

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
- name: Traceability verification (JUnit)
  run: elspais checks --format junit -o health-results.xml

- name: Publish test results
  uses: dorny/test-reporter@v1
  if: always()
  with:
    name: elspais checks
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
- name: Traceability verification (SARIF)
  run: elspais checks --format sarif -o health-results.sarif
  continue-on-error: true

- name: Upload SARIF
  uses: github/codeql-action/upload-sarif@v3
  if: always()
  with:
    sarif_file: health-results.sarif
    category: elspais-health
```

## Command Options

Run `elspais checks --help` for the full list of flags.  Options are
defined in `commands/args.py:ChecksArgs` — that dataclass is the single
source of truth for flag names and descriptions.

## Error Drill-Down

When `spec.format_rules` or `spec.no_assertions` fails, `elspais checks` directs
you to `elspais errors` for requirement-level detail:

```bash
elspais errors                     # Show all spec errors
elspais errors --format markdown   # Markdown table output
elspais errors --format json       # JSON output
elspais errors --status Draft      # Include Draft requirements
elspais errors -o errors.txt       # Write to file
```

**Example output (text format):**

```text
FORMAT ERRORS (2):
  REQ-d00003           missing_body: Requirement has no body text  spec/dev-spec.md:45
  REQ-p00002           missing_title: Requirement has no title     spec/prd-spec.md:12

NO ASSERTIONS (2):
  REQ-o00005           no_assertions: No assertions — not testable  spec/ops-spec.md:30
  REQ-p00010           no_assertions: No assertions — not testable  spec/prd-spec.md:88
```

**Options:**

  `--format {text,markdown,json}`  Output format (default: text)
  `--status STATUS`                Include additional statuses (repeatable)
  `-o, --output PATH`              Write output to file instead of stdout

**Performance:** Uses daemon-first execution like other drill-down commands.

## Gap Listings

Use standalone gap commands or compose them with checks:

```bash
elspais gaps                      # All gaps
elspais uncovered                 # Requirements without code coverage
elspais untested                  # Requirements without test coverage
elspais unvalidated               # Requirements without UAT coverage
elspais failing                   # Requirements with failing results
elspais checks gaps               # Checklist + all gaps
elspais checks untested           # Checklist + untested gaps
```

Gap commands support `--format text` (default), `--format markdown`, and `--format json`.

## Prospective Reports (What-If Analysis)

By default, `checks` and `gaps` only include requirements with **Active** status
in coverage calculations. Requirements with Draft, Proposed, or other provisional
statuses are excluded.

Use `--status` to include additional statuses and see what traceability gaps
would exist if those requirements were promoted to Active:

```bash
# Show gaps assuming all Draft requirements were active
elspais gaps --status Draft

# Show checks including both Draft and Proposed
elspais checks --status Draft --status Proposed

# Combine with gap subcommands
elspais untested --status Draft
```

This is useful for planning: before promoting a batch of Draft requirements,
run a prospective report to see which ones still need code references, tests,
or UAT validation.

The `--status` flag accepts any configured status name (case-sensitive).
See `elspais docs config` for how status roles are configured.

## Exit Codes

Exit codes use a bitfield so composed reports indicate which sections failed:

| Bit | Value | Section |
|-----|-------|---------|
| 0 | 1 | checks |
| 1 | 2 | summary (reserved) |
| 2 | 4 | trace (reserved) |
| 3 | 8 | changed (reserved) |
| 4 | 16 | gaps (reserved) |

Composed reports OR the bits together. Currently only `checks` returns non-zero (when checks fail). Use `--lenient` to suppress warnings-only failures.

## Severity Levels

- **error**: Configuration or validation issue that causes non-zero exit
- **warning**: Advisory issue (does not affect exit code)
- **info**: Informational (e.g., coverage statistics)

## Use Cases

### CI/CD Pipeline Check

```bash
# Fail pipeline if traceability verification fails
elspais checks || exit 1
```

### Quick Config Validation

```bash
# Just check config and environment setup
elspais doctor
```

### Debugging Reference Issues

```bash
# Verbose output for debugging
elspais -v checks --spec
```

### JSON Processing

```bash
# Get failed checks in CI
elspais checks --format json | jq '.checks | map(select(.passed == false))'
```

## Troubleshooting

### "No requirements found"

This usually means:
- The spec directory doesn't exist
- No `.md` files in the spec directory
- Files don't contain valid requirement format

Run with verbose to see details:
```bash
elspais -v checks --spec
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
