# WRITING ASSERTIONS

## What is an Assertion?

An assertion is a single, testable statement about system behavior.
Each assertion:
  - Uses **SHALL** or **SHALL NOT** (normative language)
  - Is labeled A, B, C, etc.
  - Can be independently verified by a test

## Assertion Format

```
## Assertions

A. The system SHALL authenticate users via email and password.
B. The system SHALL lock accounts after 5 failed attempts.
C. The system SHALL NOT store passwords in plain text.
```

## Normative Keywords

  **SHALL**         Absolute requirement (must be implemented)
  **SHALL NOT**     Absolute prohibition (must never happen)
  **SHOULD**        Recommended but not required
  **SHOULD NOT**    Not recommended but not prohibited
  **MAY**           Optional behavior

Most assertions use **SHALL** or **SHALL NOT**.

## Good vs Bad Assertions

**Good** (testable, specific):
  A. The system SHALL respond to API requests within 200ms.
  B. The system SHALL encrypt data at rest using AES-256.

**Bad** (vague, untestable):
  A. The system should be fast.
  B. The system must be secure.

## Referencing Assertions

In implementing requirements:
```
**Implements**: REQ-p00001-A
```

In code comments:
```
# Implements: REQ-p00001-A
```

In tests:
```python
def test_login():
    """REQ-p00001-A: Verify email/password auth"""
```

## Removed Assertions

If you remove an assertion, keep a placeholder to maintain letter sequence:

```
A. The system SHALL do X.
B. [Removed - superseded by REQ-d00005]
C. The system SHALL do Z.
```
