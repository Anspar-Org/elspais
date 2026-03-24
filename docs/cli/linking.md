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

`Refines:` is not valid in code files. Refines is a requirement-to-requirement
relationship (see `elspais docs graph-model`). Use `Verifies:` in code files
that produce pass/fail result output (e.g., benchmarks writing JUnit XML).

## Code Linking -- Multiline Blocks

When a file implements many requirements, use block syntax:

```python
# IMPLEMENTS REQUIREMENTS:
#   REQ-d00001-A
#   REQ-d00002-B
#   REQ-d00003
```

```javascript
// VERIFIES REQUIREMENTS:
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

The three recognized keywords (`Implements`, `Verifies`, `Refines`) all
create a VERIFIES edge when used in test files. The recommended keyword
is `Verifies:`:

```python
# Verifies: REQ-d00001-A
def test_password_hashing():
    ...
```

```python
# Verifies: REQ-d00001-A, REQ-d00001-B
def test_full_auth_flow():
    ...
```

The colon is optional for all keywords.

> **Note:** Indented reference comments are supported.  Both column-0 and
> indented placements work:
>
> ```python
> class TestAuth:
>     # Implements: REQ-d00001-A
>     def test_hashing(self):
>         ...
> ```

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

Reference multiple assertions of the same requirement with a compact syntax
using the `+` separator:

```python
# Implements: REQ-d00001-A+B+C
```

This expands to three separate references:
  `REQ-d00001-A`, `REQ-d00001-B`, `REQ-d00001-C`

Works in all link comment contexts: `Implements:`, `Refines:`, `Tests:`.

> **Configuration:** The multi-assertion separator defaults to `+` and can be
> changed via `references.defaults.multi_assertion_separator` in `.elspais.toml`.
> Set to `""` to disable compact syntax.

## Indirect Coverage

When a test validates a requirement that is implemented by code with an `Implements:` comment, coverage rolls up through the graph edges:

```python
# src/auth.py
# Implements: REQ-d00001-A
def hash_password(plain: str) -> str:
    ...
```

```python
# tests/test_auth.py
# Tests: REQ-d00001-A
def test_hashing():
    result = hash_password("secret")
    assert result.startswith("$2b$")
```

Indirect coverage is tracked separately from direct coverage. Use `elspais viewer` to see the breakdown.

> **Note:** `elspais link suggest` can recommend which tests should be linked to which requirements by analyzing import chains, function names, and keyword overlap. These are suggestions only -- run `elspais link suggest` to see recommendations, then add explicit links where appropriate.

## When to Use Each Approach

  **Code files**: Add `# Implements: REQ-xxx` to functions that
  satisfy a requirement. Use `# Verifies: REQ-xxx` only for code
  that produces pass/fail result output (e.g., benchmarks). Do not
  use `Refines:` in code files.

  **Test files**: Use `# Verifies: REQ-xxx` or embed the ID in the
  function name (`test_REQ_xxx`). This is the only valid keyword in
  test files.

  **Spec files**: Use `Implements:` for child requirements that fully
  satisfy a parent. Use `Refines:` when a requirement adds detail to
  another or splits an assertion into sub-assertions.

  **Unit tests**: Indirect linking is acceptable. If the function under
  test already has `# Implements: REQ-xxx`, the coverage rolls up. Add
  direct links only when the test validates something beyond what the
  function signature implies.

## AI Agent Instructions

The following snippet can be added to agent configuration files (e.g., CLAUDE.md) to guide automated linking:

```
When writing code that implements a requirement, add a comment
above the function:  # Implements: REQ-xxx-Y

When writing tests, use Verifies (not Implements):
  # Verifies: REQ-xxx-Y
  def test_description():

Or include the requirement ID in the function name:
  def test_REQ_xxx_Y_description():

Use multi-assertion syntax for compact references:
  # Implements: REQ-xxx-A+B+C  (in code files)
  # Verifies: REQ-xxx-A+B+C   (in test files)
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
verifies = ["Verifies", "VERIFIES"]
refines = ["Refines", "REFINES"]
```

Override settings for specific files or directories:

```toml
[[references.overrides]]
match = "*.java"
comment_styles = ["//"]
keywords = { implements = ["@Implements"], verifies = ["@Tests"] }
```

See `elspais docs config` for the full configuration reference.
