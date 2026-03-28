# ELSPAIS QUICK START GUIDE

**elspais** is a requirements traceability tool. It validates that product
requirements are traced through implementation code and tests — the automated
equivalent of maintaining a Requirements Traceability Matrix (RTM).

## The Traceability Chain

Requirements form a hierarchy. Product requirements (PRD) describe *what* the
system must do. Development requirements (DEV) describe *how*, and refine the
PRD assertions into implementable specifications. Code implements DEV
assertions; tests verify them.

```text
PRD-p00001: User Authentication
  |
  +-- DEV-d00001: Password Hashing          (Refines PRD-p00001-A)
  |     +-- src/auth/hash.py                (Implements DEV-d00001-A)
  |     +-- tests/test_hash.py              (Verifies DEV-d00001-A)
  |
  +-- DEV-d00002: Account Lockout           (Refines PRD-p00001-B)
        +-- src/auth/lockout.py             (Implements DEV-d00002-A)
        +-- tests/test_lockout.py           (Verifies DEV-d00002-A)
```

`elspais checks` verifies this chain is complete — every requirement has
assertions, every assertion is implemented, every implementation is tested.

## 1. Initialize Your Project

```shell
elspais init              # Creates .elspais.toml
elspais init --template   # Also creates an example requirement
```

## 2. Write a Product Requirement

An **assertion** is a testable statement about system behavior — a single
claim that can be independently verified (cf. ISO/IEC/IEEE 29148:2018,
"requirement ... statement which translates ... needs into ... a set of
... testable ... criteria").

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

Each assertion (A, B) is an independently traceable claim.

## 3. Create a Development Requirement

DEV requirements **refine** PRD assertions into technical specifications:

```
# REQ-d00001: Password Hashing

**Level**: DEV | **Status**: Active | **Refines**: REQ-p00001-A

**Purpose:** Specify the password hashing algorithm.

## Assertions

A. The system SHALL use bcrypt with cost factor 12.
B. The system SHALL reject passwords shorter than 8 characters.

*End* *Password Hashing* | **Hash**: 00000000
```

The `Refines: REQ-p00001-A` declaration traces this DEV requirement back to
assertion A of the PRD.

## 4. Reference from Code

In your source files, declare which assertions the code implements:

```python
# Implements: REQ-d00001-A
def hash_password(plaintext: str) -> str:
    return bcrypt.hashpw(plaintext.encode(), bcrypt.gensalt(rounds=12))
```

## 5. Reference from Tests

Tests declare which assertions they verify:

```python
# Verifies: REQ-d00001-A
def test_password_uses_bcrypt():
    hashed = hash_password("secure123")
    assert hashed.startswith(b"$2b$12$")
```

## 6. Validate and Fix

```shell
elspais checks       # Verify traceability, find gaps
elspais fix          # Fix hashes and formatting
elspais gaps         # List requirements missing coverage
```

## 7. Explore the Traceability Graph

```shell
elspais viewer                   # Interactive HTML viewer (live server)
elspais viewer --static          # Interactive HTML viewer (static file)
elspais trace --format html -o trace.html  # Basic HTML traceability table
```

## Next Steps

```shell
elspais docs format      # Full requirement format reference
elspais docs hierarchy   # PRD / OPS / DEV hierarchy rules
elspais docs checks      # Traceability verification details
elspais docs all         # Complete documentation
```
