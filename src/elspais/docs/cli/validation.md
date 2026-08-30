# VALIDATION

## Running Health Checks

  $ elspais checks                     # Check all rules
  $ elspais checks --format json       # Output JSON for tooling
  $ elspais -v checks                  # Verbose output

## Command Options

  `--spec`         Run spec file checks only
  `--code`         Run code reference checks only
  `--tests`        Run test mapping checks only
  `--format {text,markdown,json,junit,sarif}`  Output format
  `--lenient`      Allow warnings without affecting exit code
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

- Unresolved references to non-existent requirements
- Orphaned requirements (no parent)
- Hierarchy violations

## Fix and Federation Scope

By default, `elspais fix` operates only on the **primary repository**. It
never writes spec files inside associate repos and never folds associate
requirements into the primary `INDEX.md` or `term-index.md`. Read operations
(health checks, cross-repo reference resolution, coverage rollup) always
federate regardless of this default.

When `write_associates` is false, fixable issues found in associate-owned
requirements are reported but not written. The fix report marks those lines
explicitly instead of claiming a fix:

```text
[skipping] CAL-p00001: update hash (associate-owned; write_associates=false)
```

Dry-run output (`--dry-run`) uses the same `[skipping]` prefix in place of
`Would fix` for associate-owned requirements.

To opt in to wider write/generation scope, set flags in `.elspais.toml`:

```toml
[federation]
write_associates = true    # allow fix to write associate repo spec files
index_associates = true    # include associate reqs in INDEX.md / term-index.md
```

See `elspais docs config` for the full `[federation]` reference.

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

  **Unresolved link** (implements non-existent requirement)
    Fix: Correct the ID or create the missing requirement

  **Hierarchy violation** (PRD implements DEV)
    Fix: Reverse the relationship or change levels

  **Unclaimed target** (reference names an identifier no repository claims)
    Fix: Correct the ID, configure the associate that owns it, or move the
    keyword off the front of the comment if no reference was meant

## Where a Reference Is Recognised

Position decides, not the shape of the target. A *Traceability* keyword
introduces a reference only where it is the first content of:

  **a comment**        `# Verifies: REQ-p00001`
  **a metadata line**  `**Implements**: REQ-p00001` (spec files only)

The same keyword anywhere else is ordinary text. None of these introduce a
reference:

```text
value = 1  # what Implements: means here          (not first in the comment)
# The Implements: keyword links code to a REQ     (not first in the comment)
# `Implements: REQ-p00001`                        (inline-quoted)
```

A keyword inside a fenced block is likewise displayed rather than invoked,
so documentation can show reference syntax without minting references.

Metadata lines are a spec-file form. In a code or test file only comment
position counts, so an embedded fixture string containing
`**Implements**: REQ-p00001` stays a string.

Because recognition does not inspect the target, everything after the colon
is the target whatever it looks like -- including an identifier from a
repository this project has not configured, whose namespace need not
resemble your own. Such a reference is reported by
`references.unknown_namespace` at a severity you choose (see
`elspais docs checks`) rather than discarded.

## What a Reference May Introduce

A recognised line still has to say something the tool can read. What a
keyword introduces is a list of references separated by commas, and
nothing else. Each item may name an assertion, and may name several at
once:

```text
# Implements: REQ-p00001
# Implements: REQ-p00001-A
# Implements: REQ-p00001-A+B
# Implements: REQ-p00001, REQ-p00002-A
**Implements**: REQ-p00001-A+B, REQ-p00002
```

The list ends at the first thing that is not a reference, a comma or
whitespace. What the author wrote before that is read; what follows is left
over and binds nothing. So a note needs no marker to be a note -- though a
marker reads the same way:

```text
# Implements: REQ-p00001 the flag path           (binds REQ-p00001; the words are left over)
# Implements: REQ-p00001  # the flag path        (the same reading, with a marker)
```

A target that does not START with a reference resolves to nothing and is
reported, carrying the line as written. No identifier is picked out of the
middle of it: an edge to a requirement you never named would be evidence
filed against the wrong requirement, and nothing would report it. Nor is a
reference read out of a word that runs on past it.

```text
# Verifies: exit code is worst-of-all (REQ-p00001-C)   (prose is not a list)
# Implements: XREQ-d00001                        (not your REQ-d00001)
# Implements: REQ-p00001--A                      (one word; the identifier never ended)
```

Left-over content that names a requirement is reported as an undeclared
relationship, so a second requirement written after the list has ended is
visible rather than silently dropped.

## JSON Output

For tooling and CI integration:

  $ elspais checks --format json > health-report.json

## CI Integration

Add to your CI pipeline:

```yaml
# .github/workflows/validate.yml
steps:
  - uses: actions/checkout@v4
  - run: pip install elspais
  - run: elspais checks
```
