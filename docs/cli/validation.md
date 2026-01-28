# VALIDATION

## Running Validation

  $ elspais validate          # Check all rules
  $ elspais validate --fix    # Auto-fix what's fixable
  $ elspais validate -v       # Verbose output

## What Gets Validated

  **Format**      - Header line structure, hash presence
  **Hierarchy**   - Implements relationships follow level rules
  **Links**       - Referenced requirements exist
  **Hashes**      - Content matches stored hash
  **IDs**         - No duplicate requirement IDs

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

```
# elspais: expected-broken-links 2
**Implements**: REQ-future-001, REQ-future-002
```

## CI Integration

Add to your CI pipeline:

```yaml
# .github/workflows/validate.yml
steps:
  - uses: actions/checkout@v4
  - run: pip install elspais
  - run: elspais validate
```
