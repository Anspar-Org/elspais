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
elspais checks --terms     # Defined-term checks
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
| `config.associate_paths` | Validates that every federated repository — those declared here and those reached through an associate's own `[associates]` declarations — loads and contains spec files, reporting each failure with its path and reason; severity: error |
| `config.no_requirements` | Flags when no requirements are found (likely config issue); severity: warning |
| `config.governed_rules` | Discloses each governed setting (coverage rules, reference severities, status roles) a federated member would judge by differently from the repository the run was invoked from — whether the member declared it or kept a default the invoking project overrode — naming the setting, both values and the member; never fails a run; severity: info |
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
| `references.malformed` | No reference fails to read as a reference at all; default severity: warning |
| `references.unknown_namespace` | No reference names a target no configured repository claims; default severity: info |
| `references.unknown_requirement` | No claimed reference names a requirement that repository does not hold; default severity: error |
| `references.unknown_assertion` | No claimed reference names an assertion label its requirement lacks; default severity: error |
| `references.forbidden` | No reference that reads and resolves has its relationship refused — a keyword the file kind may not use, or a target the list names twice; default severity: error |
| `references.keyword_form` | No keyword is written in a non-canonical case, spacing, or markdown-emphasis form; default severity: warning (never costs the edge its keyword introduces) |
| `references.identifier_form` | No reference is spelled in a non-canonical form the configuration admits; default severity: warning (never costs the relationship it names) |
| `references.undeclared` | No comment opens with an identifier that no keyword introduces; default severity: warning (produces no relationship) |
| `spec.needs_rewrite` | Flags requirements that will be rewritten on next save (duplicate refs, stale hash); severity: warning |
| `spec.hash_integrity` | Flags Satisfies-linked requirements for review when their template hash is stale; severity: warning |
| `spec.changelog_present` | Active requirements must have at least one changelog entry (when `changelog.present = true`); severity: warning |
| `spec.changelog_current` | Active requirements' latest changelog hash must match content hash (when `changelog.hash_current = true`); severity: error |
| `spec.changelog_format` | Changelog entries must include required fields (reason, author, etc.); severity: error |
| `spec.index_current` | INDEX.md must be up to date with current requirements and journeys; severity: warning |
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

#### `spec.changelog_*` — Changelog Enforcement

Three checks enforce changelog discipline on Active requirements when enabled
in `[changelog]` config:

- **`spec.changelog_present`** — requires at least one changelog entry.
  Enabled when `changelog.present = true`.
- **`spec.changelog_current`** — the latest entry's hash must match the
  requirement's current content hash. Enabled when `changelog.hash_current = true`.
- **`spec.changelog_format`** — entries must include fields marked as required
  in `[changelog.require]` (reason, author_name, author_id, change_order).

**Configuration:**

```toml
[changelog]
present = true          # require changelog section on Active REQs
hash_current = true     # latest entry hash must match content

[changelog.require]
reason = false          # require a reason in each entry
author_name = false     # require author name
author_id = false       # require author ID
change_order = false    # require change order number
```

**Follow-up:** Run `elspais fix` to add missing changelog entries or update
stale hashes.

#### `spec.index_current` — INDEX.md Staleness

Checks that `INDEX.md` lists exactly the requirements and journeys in the
current graph. Reports missing IDs, extra IDs, or both.

**Follow-up:** Run `elspais fix` to rebuild INDEX.md.

#### `spec.needs_rewrite` — Pending Rewrites

Flags requirements that have been parsed with differences from their on-disk
format (duplicate references, stale hashes). These will be rewritten on the
next `elspais fix`, or when pending in-memory changes are saved from
the viewer or by an agent.

#### `spec.hash_integrity` — Template Hash Review

When a template requirement's content changes (stale hash), all requirements
that declare `Satisfies:` pointing to it are flagged for review. This ensures
that changes to cross-cutting requirements are propagated to their consumers.

### Code Reference Checks (`--code`)

| Check | Description |
|-------|-------------|
| `code.coverage` | Code coverage statistics (informational) |
| `code.unlinked` | Code files with no traceability markers (no `# Implements:` or `# Verifies:` comments); severity: info |
| `code.no_traceability` | Code files with no traceability markers at all (test files are covered separately by `tests.unlinked`); default severity: info |
| `code.retired_references` | Code referencing requirements with retired status (Deprecated, Superseded, Rejected); default severity: warning |
| `code.provisional_references` | Code referencing requirements with provisional status (Draft, Proposed); default severity: info |
| `code.aspirational_references` | Code referencing requirements with aspirational status (Roadmap, Future, Idea); default severity: info |

### Test Mapping Checks (`--tests`)

| Check | Description |
|-------|-------------|
| `tests.coverage` | Test coverage statistics with rollup (informational) |
| `tests.unlinked` | Test files with no traceability markers -- either no test functions found, or no test in the file links to any requirement (a file with at least one linked test is not flagged); severity: info |
| `tests.uncredited_evidence` | Evidence naming an assertion its dimension does not count -- a test on an assertion nothing implements -- so it reaches no coverage figure; configured by `[rules.coverage] uncredited_evidence`, default severity: error |
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

### `--treat-active` interaction

Naming a status with `--treat-active` promotes those requirements to
active-like status, so `code.provisional_references` and
`tests.provisional_references` stop flagging references to them —
`--treat-active Draft` silences the Draft references specifically.

**Configuration** — adjust severity via `[rules.references]` in `.elspais.toml`:

```toml
[rules.references]
retired = "warning"            # info | warning | error
provisional = "info"           # info | warning | error
aspirational = "info"          # info | warning | error
malformed = "warning"          # ok | info | warning | error
unknown_namespace = "info"     # ok | info | warning | error
unknown_requirement = "error"  # ok | info | warning | error
unknown_assertion = "error"    # ok | info | warning | error
forbidden = "error"            # ok | info | warning | error
keyword_form = "warning"       # ok | info | warning | error
identifier_form = "warning"    # ok | info | warning | error
undeclared = "warning"         # ok | info | warning | error
```

#### The Five Reference Checks — How Far Reading Got

A reference is recognised by *where* it is written, not by what it names: a
*Traceability* keyword opening a comment, or opening a metadata line in a
spec file, introduces a reference, and everything after the colon is its
target. Reading that target proceeds through stages, and a fault is
reported under exactly one check — the furthest stage reading it reached,
never a later one:

| Check | What reading found |
|---|---|
| `references.malformed` | The text never read as a reference at all (bad syntax, wrong separator, an empty item). |
| `references.unknown_namespace` | The text reads, but no configured repository's identifier grammar claims it. |
| `references.unknown_requirement` | A repository claims the identifier format, but holds no such requirement. |
| `references.unknown_assertion` | The requirement exists, but not that assertion label. |
| `references.forbidden` | The reference reads and resolves, but the relationship it declares is refused — its keyword is not valid for this file kind (e.g. `Refines:` in a code file), or the list names the same target more than once. |

A target no repository claims is by definition outside every configured ID
pattern, so its shape says nothing about whether the author meant a
reference — only its position can, which is why documentation may show a
keyword inside backticks or a fenced block without invoking one.

Two consequences worth knowing. A section banner such as
`# Verifies: how the parser handles blank lines` is a reference to a target
named "how the parser handles blank lines" — reword it or move the keyword
off the front of the comment. And a reference whose target lives in a repo
you have not configured is reported under `references.unknown_namespace`
rather than discarded, so a federation assembled from a partial checkout
still tells you what it could not read. Set `unknown_namespace = "ok"` to
silence expected cross-repository references entirely.

A keyword written in a non-canonical case, spacing, or markdown-emphasis
form is reported separately, under `references.keyword_form` — a style
finding never costs the edge its keyword introduces, so it does not join a
check that counts references that failed to bind. `references.identifier_form`
says the same thing about the referent: a reference spelled in a form the
configuration admits but that is not the canonical one — different case,
different padding, an alias — produces the relationship it names, and its
spelling is reported rather than charged to it. The report names the file and
the line so the spelling can be brought into line by hand; nothing rewrites a
code or test annotation for you.

#### `references.undeclared` — A Relationship Meant, Not Declared

Opening a comment with an identifier and then explaining, in prose, why the
code below answers to it — `# REQ-d00252-F: covered through the associate,
so not a gap` — is a natural way to write, and an author doing it means the
relationship. Nothing about the line is malformed, so reporting it as a
malformed reference would name a defect the author does not have. It is
reported under `references.undeclared` instead, with the message that
saying it with a keyword would make it count.

It produces no relationship. An informal citation is evidence of intent,
and inferring an edge from intent would credit a requirement nobody
declared. Two comments are excluded, because neither is a citation: one a
*Traceability* keyword introduces is already a declaration, and one
continuing a reference list is an item of that list.

Where prose citations are house style, set `undeclared = "ok"` — the
findings still appear, and the run does not fail on them.

**Follow-up:** Run `elspais broken` to list every unresolved reference,
across every class.

### UAT Checks

UAT (User Acceptance Testing) checks run automatically with `--tests` and report
coverage and results from user journey validation.

| Check | Description |
|-------|-------------|
| `uat.coverage` | UAT coverage for requirements at levels that set `expects_validation = true`. Such a requirement with no validating USER_JOURNEY is flagged as a gap. Levels without `expects_validation` are not counted; when no level expects validation the check passes trivially. |
| `uat.results` | Journey pass/fail status from a CSV results file |

### Terms Checks (`--terms`)

| Check | Description |
|-------|-------------|
| `terms.duplicates` | Same term defined in two locations; default severity: error |
| `terms.undefined` | Bold/italic token with no matching definition; default severity: warning |
| `terms.unmarked` | Indexed term used without markup or with wrong markup; default severity: warning |
| `terms.unused` | Defined term with zero references; default severity: warning |
| `terms.bad_definition` | Term with blank or trivial definition text; default severity: error |
| `terms.collection_empty` | Collection term with no references; default severity: warning |
| `terms.canonical_form` | Term references must use canonical casing and markup; default severity: warning |

Severity for each check is configurable via `[terms.severity]` in `.elspais.toml`. See `elspais docs terms` for full configuration details.

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
| `missing` | No coverage at all (grey/neutral when the denominator is empty; a red gap only when in-scope) |
| `partial` | Some assertions covered, not all |
| `full` | All assertions covered (the direct/indirect distinction is shown as a `~` marker, not a separate tier) |
| `failing` | Coverage exists but results are failing |

Tier, per-assertion standing, and bucket share this one vocabulary
(`full` / `partial` / `failing` / `missing`).

**Relative denominators.** `Tested` and `Passing` are measured against their
*own* denominator, not the whole spec: `Tested` counts tested / **implemented**
assertions, and `Passing` counts passing / **tested** assertions. An empty
denominator (nothing implemented, or nothing tested) resolves to `missing` at
neutral severity (grey) rather than a red gap -- you cannot test what is not
built. A failing in-denominator label is always `failing` (red), regardless of
the fraction.

**Which evidence credits a tier.** A tier is scored on the total measure: each
assertion counted once, at the greatest of what a citation named here, what
whole-requirement evidence reached, and what `Refines:` conduction carried up.
The `[rules.coverage] allow_indirect` setting no longer selects a footing --
nothing reads it, and the key is scheduled for removal. Work-list surfaces
(`gaps`, `untested`, `unvalidated`) are the strict counterpart: they count only
evidence that named the assertion, so they can report work a tier calls done.

**Evidence outside the denominator.** Measuring over the prior link means
evidence can name an assertion the dimension does not count -- a test on an
assertion nothing implements. It credits nothing, and `tests.uncredited_evidence`
reports it rather than letting it vanish into a denominator it was never in:
the assertion named, the dimension not reached, and the file and line the
evidence was written on. Where the evidence carries a verdict of its own the
finding says so -- "A test names", "A passing test names" and "A failing test
names" are three different reports, and a test that failed against an assertion
nothing implements is the sharpest form of the defect. It is an `error` by default (`[rules.coverage]
uncredited_evidence`) because the condition has only two explanations and both
are defects -- a missing `Implements:` reference, or a test aimed at an
assertion it does not exercise. Only assertion-targeted evidence names an
assertion: a whole-requirement `Verifies: REQ-xxx` names the requirement, so it
is never reported against an individual assertion — it is reported against the
requirement, and only where the dimension counts no assertion of it at all,
which is one finding rather than one per assertion. What the dimension counts
is read from the same definition the coverage tier uses, so a finding and the
figure beside it cannot disagree.

### `code_tested` — line coverage

Unlike the other five dimensions, `code_tested` counts **source lines** rather
than assertions. It cross-references implementation line ranges (from
`Implements:` edges to CODE nodes) against file-level line-coverage data
(LCOV or coverage.json). `code_tested.indirect` counts any covered
implementation line, regardless of which test covered it.

`code_tested.direct` additionally counts implementation lines whose recorded
test **context** names a test that `Verifies:` the requirement (Python only,
via coverage.py's per-test dynamic contexts). A `coverage.json` produced with
pytest-cov's `--cov-context=test` *and* `show_contexts = true` under
`[tool.coverage.json]` carries a per-line `contexts` array of strings like
`"tests/test_x.py::TestClass::test_method|run"` (or `"...::test_func|run"`
with no class). Only the `|run` phase credits direct attribution --
`|setup`/`|teardown` fixture-phase execution is not evidence the test itself
exercised the line. Coverage formats without a `contexts` map (LCOV, or
coverage.json exported without `show_contexts`) always report
`code_tested.direct == 0`.

Do not set `[tool.coverage.run] dynamic_context = "test_function"` alongside
`--cov-context=test`: that is coverage.py's own (incompatible) context
switcher and silently overrides pytest-cov's nodeid-shaped contexts. See
`elspais docs test-targets` for the full recipe and gotcha.

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

`elspais checks --run-tests` executes each configured
`[[scanning.test.targets]]` entry before evaluating checks. `--targets NAME
...` restricts `--run-tests` to a named subset (an unknown name is exit
code 2); it only affects execution here. Per-PR selectivity rendering
(`(baseline)` for carried results, `—` for no baseline) is produced by
`summary --targets` / `trace --targets`, not by `checks`. See `elspais docs
test-targets` for the full model.

## Error Drill-Down

When `spec.format_rules` or `spec.no_assertions` fails, `elspais checks` directs
you to `elspais errors` for requirement-level detail:

```bash
elspais errors                     # Show all spec errors
elspais errors --format markdown   # Markdown table output
elspais errors --format json       # JSON output
elspais errors -o errors.txt       # Write to file
```

The drill-down weighs every requirement whatever its status, so it accounts for
exactly what the two checks above counted. It takes no status option: format
rules bind a requirement whatever its status, so there is no baseline to widen.

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

An assertion listed in a gap can carry a `— N% direct` annotation
(text/markdown) or a `fraction` field (json). A gap is decided on one measure:
a citation named the assertion and the evidence is attached to it. A fraction
of `0` (no annotation) means nothing names it at all; `0 < fraction < 1` means
the evidence naming it is itself partial, still a gap but distinguishable from
zero. Whole-requirement evidence and coverage conducted up a `Refines:` chain
are counted by the summary and viewer figures but never close a gap here (see
`elspais docs graph-model` for the conduction model).

## Prospective Reports (What-If Analysis)

By default, `checks` and `gaps` only include requirements with **Active** status
in coverage calculations. Requirements with Draft, Proposed, or other provisional
statuses are excluded.

Use `--treat-active` to count additional statuses as committed and see what
traceability gaps would exist if those requirements were promoted to Active:

```bash
# Show gaps assuming all Draft requirements were active
elspais gaps --treat-active Draft

# Show checks counting both Draft and Proposed
elspais checks --treat-active Draft Proposed

# Combine with gap subcommands
elspais untested --treat-active Draft
```

This is useful for planning: before promoting a batch of Draft requirements,
run a prospective report to see which ones still need code references, tests,
or UAT validation.

A promoted status is counted in the coverage numerator and denominator and is
correspondingly absent from the trailing `[... excluded]` note — the counts and
the note always agree. Under the hood `--treat-active <S>` is an overlay that
forces `expects_implementation = true` for `<S>`, so it is exactly equivalent to
setting `[statuses.<S>] expects_implementation = true` in `.elspais.toml` for the
duration of the run (and composes with any such config already present).

`--treat-active` accepts any configured status name (case-insensitive; the name
is title-cased before matching). See `elspais docs config` for how status roles
are configured.

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
