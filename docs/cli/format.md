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
  **Status**:     Active, Draft, Deprecated, or Proposed
  **Implements**: Parent requirement ID(s), comma-separated
  **Refines**:    Parent ID when adding detail without claiming coverage

## Hash

The 8-character hash is computed from the requirement body content.
When content changes, the hash changes, triggering review.

  $ elspais fix            # Recompute all hashes
  $ elspais validate       # Check for stale hashes

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
