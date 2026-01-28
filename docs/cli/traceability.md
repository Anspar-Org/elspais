# TRACEABILITY

## What is Traceability?

Traceability connects requirements to their implementations and tests:

  **Requirement** -> **Assertion** -> **Code** -> **Test** -> **Result**

This answers: "How do we know this requirement is satisfied?"

## Marking Code as Implementing

In Python, JavaScript, Go, etc., use comments:

```python
# Implements: REQ-d00001-A
def hash_password(plain: str) -> str:
    ...
```

Or:
```javascript
// Implements: REQ-d00001
function hashPassword(plain) { ... }
```

## Marking Tests as Validating

Reference requirement IDs in test docstrings or names:

```python
def test_password_uses_bcrypt():
    """REQ-d00001-A: Verify bcrypt with cost 12"""
    ...
```

Or in test names:
```python
def test_REQ_d00001_A_bcrypt_cost():
```

## Generating Reports

  $ elspais trace --view         # Interactive HTML tree
  $ elspais trace --format html  # Basic HTML matrix
  $ elspais trace --format csv   # Spreadsheet export
  $ elspais trace --graph        # Full requirement->code->test graph

## Coverage Indicators

In trace view:
  **○** None    - No code implements this assertion
  **◐** Partial - Some assertions have implementations
  **●** Full    - All assertions have implementations
  **⚡** Failure - Test failures detected

## Understanding the Graph

  $ elspais trace --graph-json  # Export as JSON

The graph shows:
  - Requirements and their assertions
  - Which code files implement which assertions
  - Which tests validate which requirements
  - Test pass/fail status from JUnit/pytest results
