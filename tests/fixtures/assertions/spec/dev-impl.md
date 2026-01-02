# REQ-d00001: Password Hashing

**Level**: Dev | **Status**: Active | **Implements**: REQ-p00001

## Assertions

A. The implementation SHALL use bcrypt with cost factor >= 12.
B. The implementation SHALL NOT store plaintext passwords.
C. Removed - was duplicate of A.

## Rationale

bcrypt is resistant to GPU-based attacks.

*End* *Password Hashing* | **Hash**: c3d4e5f6
---

# REQ-d00002: Session Token Generation

**Level**: Dev | **Status**: Active | **Implements**: REQ-p00002

## Assertions

A. Tokens SHALL be cryptographically random using secure PRNG.
B. Tokens SHALL be at least 256 bits in length.
C. Tokens SHALL be stored hashed in the database.

*End* *Session Token Generation* | **Hash**: d4e5f6g7
---
