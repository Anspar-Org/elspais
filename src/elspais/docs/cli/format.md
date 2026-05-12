# REQUIREMENT FORMAT REFERENCE

## File Structure

Requirements are Markdown files in `spec/`. Each file can contain
one or more requirements separated by `---` (horizontal rule).

Naming convention: `spec/<level>-<topic>.md`
  Examples: `spec/prd-auth.md`, `spec/dev-api.md`

## Requirement Structure

```
# REQ-p00001: Human-Readable Title

**Level**: PRD | **Status**: Active | **Implements**: none

**Purpose:** One-line description of why this requirement exists.

## Assertions

A. The system SHALL do something specific and testable.
B. The system SHALL NOT do something prohibited.

*End* *Human-Readable Title* | **Hash**: a1b2c3d4
```

## ID Format

  `REQ-<type><number>`

  Types:
    `p` = PRD (Product)     e.g., REQ-p00001
    `o` = OPS (Operations)  e.g., REQ-o00001
    `d` = DEV (Development) e.g., REQ-d00001

  The shorthand `p00001` can be used in displays (without REQ- prefix).

## Header Line Fields

  **Level**:      PRD, OPS, or DEV (determines hierarchy position)
  **Status**:     Active, Draft, Deprecated, or Proposed (configurable)
  **Implements**: Parent requirement ID(s), comma-separated
                  Multi-assertion: REQ-p00001-A+B+C (uses + separator)
  **Refines**:    Parent ID when adding detail without claiming coverage
  **Satisfies**:  Template requirement ID(s) this requirement complies with
                  (e.g., cross-cutting PRD). The template's REQ subtree is
                  cloned as instance nodes under the declaring requirement.
                  Use "REQ-xxx-Y SHALL be NOT APPLICABLE" to exclude
                  template assertions from coverage.

## Hash

The 8-character hash is computed from the requirement body content.
When content changes, the hash changes, triggering review.

  $ elspais fix            # Recompute all hashes
  $ elspais health         # Check for stale hashes

## Changelog

Active requirements track a changelog of content changes. The
`## Changelog` section appears after `## Assertions` (and any other
sections like Rationale) but before the `*End*` marker. It is
excluded from hash computation so adding entries does not alter the
hash.

### Entry Format

```
- YYYY-MM-DD | <hash> | <change-order> | <author> (<id>) | <reason>
```

Each field is separated by ` | `. Example:

```
## Changelog

- 2026-01-15 | 3f8a91c2 | CO-100 | Jane Doe (jdoe@co.com) | First approved version
- 2026-03-07 | b7c4e1d0 | CO-142 | Jane Doe (jdoe@co.com) | Clarify timeout assertion
```

### Lifecycle Rules

| Transition              | Behaviour                                    |
|-------------------------|----------------------------------------------|
| Draft (no change)       | No changelog entry added. Existing preserved |
| Draft to Active         | First entry added: "First approved version"  |
| Active with hash change | New entry required. `fix` fails without `-m` |
| Active missing section  | `## Changelog` auto-added by `fix`           |
| Deprecated              | Hash updated silently, no changelog entry    |

## Multiple Requirements Per File

Separate requirements with a horizontal rule:

```
# REQ-p00001: First Requirement
...
*End* *First Requirement* | **Hash**: ...

---
# REQ-p00002: Second Requirement
...
```

## Section Header Depth Canonicalization

Section headers within a requirement (`## Assertions`, `## Changelog`,
and named sections like `## Rationale`, plus hash-style sub-headings
inside assertion blocks) are canonicalized to sit at
`requirement_heading_level + 1` when shallower than this depth.

When you use `elspais fix`, headers that are too shallow are brought
to the minimum required level. Headers that are already deeper than
the minimum are preserved as-is (e.g., an author writing `### Assertions`
under an H1 requirement keeps the `###`).

**H6 Limitation**: A requirement at heading level H6 (`######`) cannot
have any section blocks and remain fixable. If a requirement at H6
contains an `## Assertions`, `## Changelog`, or other section header,
`fix` will print an error to stderr and exit non-zero:

```
Cannot fix REQ-h60001: heading at H6 — move requirement to shallower level
```

Resolve this by moving the H6 requirement to a shallower heading level
(H1 through H5) so that section headers can fit at H6.
