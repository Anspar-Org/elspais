# ELSPAIS QUICK START GUIDE

**elspais** validates requirements and traces them through code to tests.
Requirements live as Markdown files in your `spec/` directory.

## 1. Initialize Your Project

  $ elspais init              # Creates .elspais.toml
  $ elspais init --template   # Also creates example requirement

## 2. Write Your First Requirement

Create `spec/prd-auth.md`:

```
# REQ-p00001: User Authentication

**Level**: PRD | **Status**: Active

**Purpose:** Enable secure user login.

## Assertions

A. The system SHALL authenticate users via email and password.
B. The system SHALL lock accounts after 5 failed login attempts.

*End* *User Authentication* | **Hash**: 00000000
```

## 3. Validate and Update Hashes

  $ elspais validate     # Check format, links, hierarchy
  $ elspais hash update  # Compute content hashes

## 4. Create Implementing Requirements

DEV requirements implement PRD requirements:

```
# REQ-d00001: Password Hashing

**Level**: DEV | **Status**: Active | **Implements**: REQ-p00001-A

## Assertions

A. The system SHALL use bcrypt with cost factor 12.
```

## 5. Generate Traceability Report

  $ elspais trace --view   # Interactive HTML tree
  $ elspais trace --format html -o trace.html

## Next Steps

  $ elspais docs format      # Full format reference
  $ elspais docs hierarchy   # Learn about PRD/OPS/DEV
  $ elspais docs all         # Complete documentation
