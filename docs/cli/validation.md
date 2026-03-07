# VALIDATION

## Running Health Checks

  $ elspais health                     # Check all rules
  $ elspais health -j                  # Output JSON for tooling
  $ elspais health -v                  # Verbose output

## Command Options

  `--config`       Run configuration checks only
  `--spec`         Run spec file checks only
  `--code`         Run code reference checks only
  `--tests`        Run test mapping checks only
  `-j, --json`     Output as JSON
  `-v, --verbose`  Show additional details

## Auto-Fixing Issues

Use the `fix` command to auto-fix issues:

  $ elspais fix                   # Fix all issues
  $ elspais fix --dry-run         # Preview fixes without applying
  $ elspais fix REQ-p00001        # Fix hash for a specific requirement

## What Can Be Auto-Fixed

The `fix` command automatically corrects:

**Fixable:**

- Missing hash → Computes and inserts from assertion text
- Stale hash → Recomputes from current content
- Missing Status field → Adds default "Active"
- Assertion spacing → Inserts blank lines between consecutive assertion lines
- List spacing → Inserts blank line before list items that follow text

**Not fixable (report only):**

- Broken references to non-existent requirements
- Orphaned requirements (no parent)
- Hierarchy violations

## What Gets Validated

  **Format**      - Header line structure, hash presence
  **Hierarchy**   - Implements relationships follow level rules
  **Links**       - Referenced requirements exist
  **Hashes**      - Content matches stored hash
  **IDs**         - No duplicate requirement IDs

## Common Validation Errors

  **Missing hash**
    Fix: $ elspais fix

  **Stale hash** (content changed)
    Fix: $ elspais fix (after reviewing changes)

  **Broken link** (implements non-existent requirement)
    Fix: Correct the ID or create the missing requirement

  **Hierarchy violation** (PRD implements DEV)
    Fix: Reverse the relationship or change levels

## Suppressing Warnings

For expected issues, add inline suppression:

```markdown
# elspais: expected-broken-links 2
**Implements**: REQ-future-001, REQ-future-002
```

## JSON Output

For tooling and CI integration:

  $ elspais health -j > health-report.json

## CI Integration

Add to your CI pipeline:

```yaml
# .github/workflows/validate.yml
steps:
  - uses: actions/checkout@v4
  - run: pip install elspais
  - run: elspais health
```
