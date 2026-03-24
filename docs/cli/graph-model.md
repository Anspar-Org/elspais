# GRAPH MODEL REFERENCE

elspais builds a directed acyclic graph (DAG) from your project files.
This page documents every node kind and edge kind in the graph, what
creates them, and how they appear in your files.

See also: `elspais docs format` for requirement syntax,
`elspais docs linking` for code/test linking syntax.

## Node Kinds

### REQUIREMENT

A single requirement block parsed from a spec file.

ID format: `REQ-p00001` (prefix and pattern are configurable).

```markdown
## REQ-p00001: User Authentication

**Level**: PRD | **Status**: Active | **Implements**: none

The system must authenticate users before granting access.

## Assertions

A. The system SHALL verify credentials against the identity store.
B. The system SHALL lock accounts after 5 failed attempts.

*End* *User Authentication* | **Hash**: a1b2c3d4
```

### ASSERTION

A lettered testable statement within a requirement.

ID format: `REQ-p00001-A` (parent ID + label).

Assertions live inside the `## Assertions` section of a requirement.
They are not standalone files -- the parser extracts them automatically.

```markdown
## Assertions

A. The system SHALL verify credentials against the identity store.
B. The system SHALL lock accounts after 5 failed attempts.
```

### CODE

A function or scope in a source file that carries an `Implements:` or
`Refines:` comment.

ID format: `code:src/auth/password.py:12`

```python
# Implements: REQ-d00001-A
def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt())
```

```dart
// Implements: REQ-d00042-A+B
void submitOrder(Order order) { ... }
```

```sql
-- Implements: REQ-d00030-A
CREATE PROCEDURE archive_records ...
```

```html
<!-- Implements: REQ-d00050-A -->
```

```css
/* Implements: REQ-d00050-B */
```

### TEST

A test function that verifies a requirement. Created from test file
scanning -- either by naming convention or by comment.

ID format: `test:tests/test_auth.py::TestAuth::test_login`

By function name (underscores replace hyphens):

```python
def test_REQ_d00001_A_hashes_with_bcrypt():
    assert hash_password("secret").startswith("$2b$")
```

By comment -- in test files, all three recognized keywords
(`Implements`, `Verifies`, `Refines`) produce a VERIFIES edge:

```python
# Verifies: REQ-d00001-A, REQ-d00001-B
def test_full_auth_flow():
    ...
```

In code files, the keyword determines the edge kind:
`Implements:` creates IMPLEMENTS, `Verifies:` creates VERIFIES,
`Refines:` creates REFINES.

### RESULT

A test execution outcome (pass/fail/skip) parsed from JUnit XML or
pytest JSON output. Not authored directly -- produced by your test
runner.

```bash
pytest --junitxml=results/report.xml
```

RESULT nodes attach to their parent TEST node via a YIELDS edge.
They contribute to the **verified** coverage dimension (did the test
pass?) but not to the **tested** dimension (is there a test at all?).

### USER_JOURNEY

A user acceptance test scenario parsed from a journey file.

ID format: `JNY-AUTH-01`

```markdown
## JNY-AUTH-01: New User Registration

**Actor**: Anonymous visitor
**Goal**: Create an account and log in

Validates: REQ-p00001, REQ-p00002-A

### Steps

1. Navigate to registration page
2. Fill in email and password
3. Submit form and verify confirmation

*End* *JNY-AUTH-01*
```

### FILE

A source file as a first-class graph node. Created automatically when
elspais scans your directories.

ID format: `file:src/auth/password.py`

FILE nodes are structural roots -- every parsed content node (requirement,
code reference, test, etc.) is connected to its FILE node via a CONTAINS
edge.

Each FILE node has a **FileType** classification:

| FileType | Configured via | Example directories |
|----------|---------------|---------------------|
| `SPEC` | `[scanning.spec]` | `spec/` |
| `JOURNEY` | `[scanning.journey]` | `journeys/` |
| `CODE` | `[scanning.code]` | `src/`, `lib/` |
| `TEST` | `[scanning.test]` | `tests/` |
| `RESULT` | `[scanning.results]` | `results/` |

### REMAINDER

Unclaimed file content that does not match any parser. Two forms:

- **File-level**: Content between requirements (separators, preamble).
  Connected to FILE via CONTAINS.
- **Requirement-level**: Named sections inside a requirement (Rationale,
  Notes, etc.). Connected to the parent REQUIREMENT via STRUCTURES.

REMAINDER preserves non-normative content through parse/render round-trips.

## Edge Kinds

### Traceability Edges (user-authored)

These edges are created from syntax you write in your files. They form
the traceability links that coverage metrics are built on.

#### IMPLEMENTS

Child claims to fully satisfy a parent requirement or assertion.
**Contributes to coverage.**

In spec files (requirement metadata line):

```markdown
**Level**: DEV | **Implements**: REQ-o00010-A+B | **Status**: Active
```

In code files (comment above function):

```python
# Implements: REQ-d00001-A
def hash_password(plain: str) -> str: ...
```

```dart
// Implements: REQ-d00042-A+B+C
void submitOrder(Order order) { ... }
```

```go
// Implements: REQ-d00060-A
func ProcessPayment(ctx context.Context, amt Money) error { ... }
```

#### REFINES

A requirement adds detail to another requirement, or splits an
assertion into sub-assertions. **Valid only in spec files
(requirement-to-requirement).** Not valid in code or test files.
**Does NOT contribute to coverage.**

The refining requirement's assertions completely re-specify the
target assertion. Multiple refinements are cumulative: if B refines A
and C refines A, then A is satisfied when all assertions of B and C
are satisfied.

```markdown
**Level**: DEV | **Refines**: REQ-o00010 | **Status**: Active
```

```markdown
**Level**: DEV | **Refines**: REQ-o00010-A | **Status**: Active
```

#### VERIFIES

Produces pass/fail output applicable to the targeted assertion.
**Contributes to coverage.**

Primarily used in test files. Only `Verifies` is a valid keyword
in test files:

```python
# Verifies: REQ-d00001-A
def test_password_hashing():
    result = hash_password("secret")
    assert result.startswith("$2b$")
```

Also created from function names containing requirement IDs:

```python
def test_REQ_d00001_A_rejects_empty_password():
    with pytest.raises(ValueError):
        hash_password("")
```

Also valid in code files, for code that generates result output
(e.g., a benchmark suite that writes a pass/fail report):

```python
# Verifies: REQ-d00080-A
def run_performance_benchmark():
    """Runs benchmark and writes JUnit XML results."""
    ...

#### VALIDATES

User journey validates a requirement or assertion.
**Contributes to coverage (UAT).**

Written in journey files using the `Validates:` field:

```markdown
## JNY-CHECKOUT-01: Complete Purchase

Validates: REQ-p00005, REQ-p00006-A
```

#### SATISFIES

Declaring requirement complies with a template requirement.
**Does not directly contribute to coverage** -- coverage is computed
on the cloned instance nodes instead.

```markdown
## REQ-d00010: Payment Processing Module

**Level**: DEV | **Status**: Active

Satisfies: REQ-p00099
```

This clones the template's subtree as INSTANCE nodes under the
declaring requirement. See INSTANCE and DEFINES below.

### Keyword Validity by File Type

Not every keyword is valid in every file type. Using the wrong
keyword produces a warning:

| Keyword | Spec files | Code files | Test files | Journey files |
|---------|-----------|------------|------------|---------------|
| `Implements` | IMPLEMENTS edge | IMPLEMENTS edge | **warning** (treated as Verifies) | n/a |
| `Verifies` | n/a | VERIFIES edge | VERIFIES edge | n/a |
| `Refines` | REFINES edge | **warning** (skipped) | **warning** (treated as Verifies) | n/a |
| `Satisfies` | SATISFIES edge | n/a | n/a | n/a |
| `Validates` | n/a | n/a | n/a | VALIDATES edge |

### Structural Edges (automatic)

These edges are created by the build pipeline. You do not author them
directly.

#### CONTAINS

FILE -> content node (REQUIREMENT, USER_JOURNEY, CODE, TEST, REMAINDER).

Represents physical file membership. Every parsed content node is
connected to its source FILE node. Edge metadata includes `start_line`,
`end_line`, and `render_order`.

#### STRUCTURES

REQUIREMENT -> child node (ASSERTION, requirement-level REMAINDER).

Represents internal structure within a requirement block. Assertions
and named sections (Rationale, Notes, preamble) are connected to their
parent requirement.

#### YIELDS

RESULT -> TEST.

Connects a test execution result to the test it reports on. Created
when result files (JUnit XML, pytest JSON) are parsed and matched to
existing TEST nodes.

#### INSTANCE

INSTANCE node -> original TEMPLATE node.

Created during `Satisfies:` expansion. Each cloned node links back
to its original in the template subtree. INSTANCE nodes have no
CONTAINS edge and `file_node()` returns None for them.

#### DEFINES

FILE -> INSTANCE node.

Provides virtual provenance for INSTANCE nodes. Points from the file
containing the declaring requirement to each cloned INSTANCE node,
since INSTANCE nodes have no CONTAINS edge of their own.

## Coverage Classification

Only three edge kinds contribute to coverage metrics:

| Edge Kind | Coverage Dimension |
|-----------|--------------------|
| IMPLEMENTS | `implemented` (code or child-REQ covers assertions) |
| VERIFIES | `tested` / `verified` (test covers / passes assertions) |
| VALIDATES | `uat_coverage` / `uat_verified` (journey covers / passes) |

REFINES, CONTAINS, STRUCTURES, SATISFIES, INSTANCE, DEFINES, and YIELDS
do not contribute to coverage. See `elspais docs checks` for the full
coverage dimensions reference.

## Graph Structure Summary

```text
                        FILE (spec/prd-auth.md)
                         |
                    CONTAINS
                         |
                    REQUIREMENT (REQ-p00001)
                    /         \
              STRUCTURES    STRUCTURES
              /                   \
        ASSERTION (A)         ASSERTION (B)
              ^                     ^
              |                     |
          VERIFIES              IMPLEMENTS
              |                     |
        TEST (test_auth.py)   CODE (auth.py)
              |
           YIELDS
              |
        RESULT (passed)
```

For `Satisfies:` expansion:

```text
    REQUIREMENT (REQ-d00010, declares Satisfies: REQ-p00099)
         |
     SATISFIES
         |
    INSTANCE (REQ-d00010::REQ-p00099)  --INSTANCE-->  REQUIREMENT (REQ-p00099)
         ^
      DEFINES
         |
    FILE (spec/dev-payment.md)
```
