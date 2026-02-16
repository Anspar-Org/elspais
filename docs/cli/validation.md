# VALIDATION

## Running Validation

  $ elspais validate                   # Check all rules
  $ elspais validate --fix             # Auto-fix what's fixable
  $ elspais validate --fix --dry-run   # Preview fixes without applying
  $ elspais validate -v                # Verbose output

## Command Options

  `--fix`               Auto-fix hashes and formatting issues
  `--dry-run`           Preview fixes without modifying files (use with --fix)
  `--skip-rule RULE`    Skip validation rules (repeatable)
  `-j, --json`          Output requirements as JSON

## What Can Be Auto-Fixed

The `--fix` flag automatically corrects:

**Fixable:**

- Missing hash → Computes and inserts from assertion text
- Stale hash → Recomputes from current content
- Missing Status field → Adds default "Active"
- Assertion spacing → Inserts blank lines between consecutive assertion lines

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

## Skip Rule Patterns

Skip specific validation rules:

  $ elspais validate --skip-rule hash.missing
  $ elspais validate --skip-rule 'hash.*'     # All hash rules
  $ elspais validate --skip-rule hierarchy.*  # All hierarchy rules

**Available Patterns:**

  `hash.missing`                Hash footer is missing
  `hash.mismatch`              Hash doesn't match content
  `hash.*`                     All hash rules
  `hierarchy.*`                All hierarchy rules
  `format.*`                   All format rules
  `format.assertion_spacing`   Consecutive assertions need blank line separation

## Common Validation Errors

  **Missing hash**
    Fix: $ elspais hash update

  **Stale hash** (content changed)
    Fix: $ elspais hash update after reviewing changes

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

  $ elspais validate -j > requirements.json

## CI Integration

Add to your CI pipeline:

```yaml
# .github/workflows/validate.yml
steps:
  - uses: actions/checkout@v4
  - run: pip install elspais
  - run: elspais validate
```
