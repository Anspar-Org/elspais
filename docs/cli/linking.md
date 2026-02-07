# LINKING REQUIREMENTS TO CODE AND TESTS

Linking connects your requirements to the code that implements them and the tests that validate them. elspais scans your source files for specific comment patterns and test naming conventions, then builds a traceability graph showing what is covered and what is not.

## Code Linking

Add a comment above or inside any function that implements a requirement:

```python
# Implements: REQ-d00001-A
def hash_password(plain: str) -> str:
    ...
```

```javascript
// Implements: REQ-d00001-A
function hashPassword(plain) { ... }
```

```sql
-- Implements: REQ-d00001-A
CREATE PROCEDURE hash_password ...
```

HTML and CSS use block comments:

```html
<!-- Implements: REQ-d00001-A -->
```

```css
/* Implements: REQ-d00001-A */
```

Multiple requirements on one line:

```python
# Implements: REQ-d00001-A, REQ-d00002-B
```

Use `Refines:` instead of `Implements:` when code partially addresses a requirement without fully satisfying it. Refines edges do not contribute to coverage metrics.

## Code Linking -- Multiline Blocks

When a file implements many requirements, use block syntax:

```python
# IMPLEMENTS REQUIREMENTS:
#   REQ-d00001-A
#   REQ-d00002-B
#   REQ-d00003
```

```javascript
// VALIDATES REQUIREMENTS:
//   REQ-d00010
//   REQ-d00011
```

The block ends at the first line that is not an indented comment with a requirement ID.

## Test Linking -- Function Names

Include requirement IDs in test function names using underscores:

```python
def test_REQ_d00001_A_hashes_with_bcrypt():
    assert hash_password("secret").startswith("$2b$")
```

The parser extracts `REQ-d00001-A` from the function name. Any text before or after the ID is ignored.

Test class methods work the same way:

```python
class TestPasswordHashing:
    """Validates REQ-d00001-A: password hashing"""

    def test_REQ_d00001_A_uses_bcrypt(self):
        ...
```

## Test Linking -- Comments

Use `Tests` or `Validates` comments in test files:

```python
# Tests: REQ-d00001-A
def test_password_hashing():
    ...
```

```python
# Tests: REQ-d00001-A, REQ-d00001-B
def test_full_auth_flow():
    ...
```

The colon is optional for all keywords (`Implements`, `Tests`, `Validates`, `Refines`).

A comment placed before any function definition applies to the entire file:

```python
# Tests: REQ-d00001
# All tests in this file validate password security

def test_bcrypt_cost():
    ...

def test_no_plaintext_storage():
    ...
```

Both tests inherit the file-level `REQ-d00001` link.

## Multi-Assertion Syntax

Reference multiple assertions of the same requirement with a compact syntax:

```python
# Implements: REQ-d00001-A-B-C
```

This expands to three separate references:
  `REQ-d00001-A`, `REQ-d00001-B`, `REQ-d00001-C`

Works in all contexts: `Implements:`, `Refines:`, `Tests:`, and test function names.

```python
def test_REQ_d00001_A_B_C_full_auth():
    ...
```

## Indirect Coverage

When a test imports and exercises a function that has an `Implements:` comment, coverage rolls up automatically:

```python
# src/auth.py
# Implements: REQ-d00001-A
def hash_password(plain: str) -> str:
    ...
```

```python
# tests/test_auth.py
from auth import hash_password

def test_hashing():
    result = hash_password("secret")
    assert result.startswith("$2b$")
```

Even though `test_hashing` has no explicit requirement reference, elspais detects the import chain and creates indirect coverage for `REQ-d00001-A`. No action needed -- this happens during graph construction.

Indirect coverage is tracked separately from direct coverage. Use `elspais trace --view` to see the breakdown.

## When to Use Each Approach

  **Code files**: Always add `# Implements: REQ-xxx` to functions
  that satisfy a requirement. This is the primary link.

  **Acceptance / integration tests**: Use direct linking via function
  names (`test_REQ_xxx`) or comments (`# Tests: REQ-xxx`). These tests
  validate requirements explicitly and should say so.

  **Unit tests**: Indirect linking is acceptable. If the function under
  test already has `# Implements: REQ-xxx`, the coverage rolls up. Add
  direct links only when the test validates something beyond what the
  function signature implies.

  **Refines vs Implements**: Use `Refines:` for partial contributions
  (helper utilities, shared libraries). Use `Implements:` when the code
  directly satisfies the requirement.

## AI Agent Instructions

The following snippet can be added to agent configuration files (e.g., CLAUDE.md) to guide automated linking:

```
When writing code that implements a requirement, add a comment
above the function:  # Implements: REQ-xxx-Y

When writing tests, include the requirement ID in the function
name:  def test_REQ_xxx_Y_description():

Use multi-assertion syntax for compact references:
  # Implements: REQ-xxx-A-B-C

Test classes should include the requirement in their docstring:
  """Validates REQ-xxx-Y: brief description"""
```

## Configuration

Reference parsing is configurable via `.elspais.toml`:

```toml
[references.defaults]
separators = ["-", "_"]
case_sensitive = false
comment_styles = ["#", "//", "--"]

[references.defaults.keywords]
implements = ["Implements", "IMPLEMENTS"]
validates = ["Validates", "Tests", "VALIDATES", "TESTS"]
refines = ["Refines", "REFINES"]
```

Override settings for specific files or directories:

```toml
[[references.overrides]]
match = "*.java"
comment_styles = ["//"]
keywords = { implements = ["@Implements"], validates = ["@Tests"] }
```

See `elspais docs config` for the full configuration reference.
