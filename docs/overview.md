# elspais Overview

**elspais** is a requirements validation and traceability tool for software projects. It treats requirements as structured Markdown documents with machine-readable metadata, enabling automated verification that requirements are properly linked, formatted, and tracked through implementation.

## Core Purpose

1. **Requirements as Code** - Requirements live in `spec/` directories as Markdown files, versioned alongside source code
2. **Hierarchy Enforcement** - PRD (Product) → OPS (Operations) → DEV (Development) requirements form a tree where children "implement" parents
3. **Change Detection** - SHA-256 hashes track when requirement content changes, triggering re-verification
4. **Traceability** - Links requirements → assertions → code → tests, answering "what tests verify this requirement?"

---

## Typical Project Lifecycle

### 1. Project Setup

```bash
elspais init              # Creates .elspais.toml config
elspais init --template   # Creates example requirement file
```

### 2. Writing Requirements

Create `spec/REQ-p00001.md`:

```markdown
# REQ-p00001: User Authentication

**Level**: PRD | **Status**: Active | **Implements**: none

## Assertions

A. The system SHALL authenticate users via email/password.
B. The system SHALL lock accounts after 5 failed attempts.

*End* *User Authentication* | **Hash**: a1b2c3d4
```

Then a DEV requirement implementing it (`spec/REQ-d00001.md`):

```markdown
# REQ-d00001: Password Hashing

**Level**: Dev | **Status**: Active | **Implements**: REQ-p00001

## Assertions

A. The system SHALL use bcrypt with cost factor 12.
...
```

### 3. Continuous Validation

```bash
elspais validate          # Check format, hierarchy, broken links
elspais hash update       # Recompute hashes after edits
elspais changed           # Show uncommitted spec changes
```

### 4. Traceability During Development

Tests reference requirements:

```python
def test_password_hashing():
    """REQ-d00001-A: Verify bcrypt usage"""
    ...
```

Code references implementations:

```python
# Implements: REQ-d00001
def hash_password(plain: str) -> str:
    ...
```

Generate traceability matrix:

```bash
elspais trace --format html    # Basic matrix
elspais trace --view           # Interactive HTML with coverage stats
elspais trace --tree           # Full DAG: requirements→assertions→code→tests
```

### 5. Evolution & Change Management

When requirements change:

- Hash changes trigger review (visible in `elspais changed`)
- Old assertions can be marked as "Removed" placeholders to maintain label sequence
- Multi-repo support via sponsors config for associated repositories (e.g., `TTN-REQ-p00001`)

### 6. AI-Assisted Reformatting

Migrate legacy "Acceptance Criteria" format to assertions:

```bash
elspais reformat-with-claude --dry-run
```

---

## Key Concepts

| Concept | Description |
|---------|-------------|
| **Levels** | PRD (1) → OPS (2) → DEV (3) hierarchy |
| **Assertions** | Labeled A-Z, each uses SHALL, unit of verification |
| **Hash** | 8-char SHA-256 of content, detects changes |
| **Implements** | Child references parent(s), never reverse |
| **Conflict** | Duplicate IDs detected and marked |

The tool is zero-dependency (stdlib only), with optional extras for HTML generation (`[trace-view]`) and review server (`[trace-review]`).
