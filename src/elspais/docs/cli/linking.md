# LINKING REQUIREMENTS TO CODE AND TESTS

Linking connects your requirements to the code that implements them and the tests that validate them. elspais scans your source files for specific comment patterns and test naming conventions, then builds a traceability graph showing what is covered and what is not.

## Code Linking

Add a comment above or inside any function that implements a requirement:

```python
# Implements: REQ-d00001-A
def hash_password(plain: str) -> str: ...
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

## Code Linking -- Multiline Lists

When a file implements many requirements, end the line with the list
separator and continue on the next comment line:

```python
# Implements: REQ-d00001-A,
#             REQ-d00002-B,
#             REQ-d00003
```

The separator is what says the list has not ended. Without it, the first line
is a complete list and anything below it is a citation with no keyword of its
own -- reported as an undeclared relationship (`references.undeclared`),
never as part of the list above it and never as a broken reference.

### Legacy: block header

```python
# IMPLEMENTS REQUIREMENTS:
#   REQ-d00001-A
#   REQ-d00002-B
```

This form still parses. The colon is required and the word is plural. Nothing
emits it; prefer the continuation form above.

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

    def test_REQ_d00001_A_uses_bcrypt(self): ...
```

## Test Linking -- Comments

The three recognized keywords (`Implements`, `Verifies`, `Refines`) all
create a VERIFIES edge when used in test files. The recommended keyword
is `Verifies:`:

```python
# Verifies: REQ-d00001-A
def test_password_hashing(): ...
```

```python
# Verifies: REQ-d00001-A, REQ-d00001-B
def test_full_auth_flow(): ...
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


def test_bcrypt_cost(): ...


def test_no_plaintext_storage(): ...
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
def hash_password(plain: str) -> str: ...
```

```python
# tests/test_auth.py
# Tests: REQ-d00001-A
def test_hashing():
    result = hash_password("secret")
    assert result.startswith("$2b$")
```

Indirect coverage is tracked separately from direct coverage. Use `elspais viewer` to see the breakdown.

> **Note:** `elspais link` can recommend which tests should be linked to which requirements by analyzing import chains, function names, and keyword overlap. These are suggestions only -- run `elspais link` to see recommendations, then add explicit links where appropriate.

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

What a reference may look like comes from the identifier configuration, in
`[id-patterns]`. A repository declares its own canonical template, component
style, and the single character separating a requirement from an *Assertion*
label; references are read and written in exactly that form. In a federation
each repository keeps its own, and a reference is understood under the grammar
of whichever repository owns the identifier it names.

```toml
[id-patterns]
canonical = "{namespace}-{level.letter}{component}"

[id-patterns.assertions]
separator = "-"          # between component and label
multi_separator = "+"    # between labels, as in A+B+C
```

There is no list of alternative separators. One spelling is accepted, the one
configured, so a reference written some other way is reported rather than
quietly resolved.

The keyword that introduces a reference in a test file is
`scanning.test.reference_keyword` (default `Verifies`). Comment styles are not
configurable: `#`, `//` and `--` introduce a reference, and a keyword inside a
block comment is not read.

See `elspais docs config` for the full configuration reference.

## What a reference report says

Every reported reference carries a **class** — how far reading it got — and one
or more **codes** naming what is wrong with it. The classes are fixed, because
a project configures a severity per class. The codes are open: a diagnosis
becomes more specific over releases without anything having to be
reconfigured.

Each row below is an input and what the tool reports for it. The identifier
configuration is the default one shown above (`REQ-`, five numeric digits, `-`
before an *Assertion* label, `+` between labels), and the repository holds
`REQ-d00001` with assertions A and B.

| Input | Class | Codes |
|---|---|---|
| `# Implements: REQ-d00001` | — | binds |
| `# Implements: not a reference` | malformed | `E_NOT_AN_IDENTIFIER` |
| `# Implements: REQ-d00001+A` | malformed | `E_WRONG_ASSERTION_SEPARATOR` |
| `# Implements: REQ-d00001-A-B` | malformed | `E_WRONG_MULTI_SEPARATOR` |
| `# Implements: REQ-d00001-1` | malformed | `E_LABEL_OUT_OF_SERIES` |
| `# Implements: REQ-d00001-AB` | malformed | `E_IDENTIFIER_WITH_TRAILING_TEXT` |
| `# Implements: REQ-d00001 (A, C)` | malformed | `E_NOT_AN_IDENTIFIER` on the first item; the second reads as a name no repository claims |
| `# Implements: REQ-d00001,,REQ-d00002` | malformed | `E_EMPTY_ITEM` |
| `# Implements: REQ-d00001,` (nothing follows) | malformed | `E_TRAILING_SEPARATOR` |
| `# Implements:` | malformed | `E_EMPTY_REFERENCE_LIST` |
| `# Implements: WIDGET-42` | unknown_namespace | — |
| `# Implements: REQ-d00099` | unknown_requirement | — |
| `# Implements: REQ-d00001-Z` | unknown_assertion | — |
| `# Implements: REQ-d00001, REQ-d00001` | forbidden | `E_DUPLICATE_ITEM` (both instances) |
| `# Refines: REQ-d00001` (in a code file) | forbidden | — |
| `# Implements: req-d00001` | — | binds; `E_NON_CANONICAL_SPELLING` `E_WRONG_CASE` |
| `# Implements: REQ-d1` | — | binds; `E_NON_CANONICAL_SPELLING` `E_WRONG_PADDING` |
| `#Implements: REQ-d00001` | — | binds; `E_KEYWORD_NO_MARKER_SPACE` |
| `# implements: REQ-d00001` | — | binds; `E_KEYWORD_WRONG_CASE` |
| `# **Implements**: REQ-d00001` (off markdown) | — | binds; `E_KEYWORD_MARKDOWN_EMPHASIS_OFF_MARKDOWN` |
| `#   REQ-d00001` (no keyword above) | — | reported as an undeclared relationship |

The `forbidden` class covers every reference that reads and resolves and whose
relationship is refused anyway. Its description says only what is true of all
of them; which refusal it was is the finding's code.

`E_SYNTAX_ERROR` accompanies every reported fault. Carried *alone* it is the
report that nothing more specific is known — the tool declining to guess, not
the absence of a diagnosis. That is also what an item admitting two accounts of
equal extent carries: a code is issued only where the input determines the
defect it names, so where two accounts each explain the item, neither is
issued and the generic code stands alone.

The last six rows are not reference faults, and none of them costs a
relationship. A reference spelled in a form the configuration admits that is
not the canonical one — different case, different padding, an alias — binds
exactly as the canonical spelling would and is reported under
`references.identifier_form`, carrying `E_NON_CANONICAL_SPELLING` plus
whichever of case and padding the two spellings determine. The finding names
the file and the line; nothing rewrites the annotation for you. A keyword written in a non-canonical form is the same fact about
the keyword rather than the referent, reported under
`references.keyword_form`. And a comment opening with an identifier that no
keyword introduces is a relationship its author appears to intend and has not
spelled; it is reported under `references.undeclared` and produces nothing.
