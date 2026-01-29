# TRACEABILITY

## What is Traceability?

Traceability connects requirements to their implementations and tests:

  **Requirement** -> **Assertion** -> **Code** -> **Test** -> **Result**

This answers: "How do we know this requirement is satisfied?"

## Generating Reports

  $ elspais trace --view         # Interactive HTML tree
  $ elspais trace --format html  # Basic HTML matrix
  $ elspais trace --format csv   # Spreadsheet export
  $ elspais trace --graph        # Full requirement->code->test graph
  $ elspais trace --graph-json   # Export graph as JSON

## Command Options

  `--format {markdown,html,csv,both}`  Output format
  `--output PATH`           Output file path
  `--view`                  Interactive HTML traceability tree
  `--embed-content`         Embed full markdown in HTML (offline viewing)
  `--graph`                 Use unified traceability graph
  `--graph-json`            Output graph as JSON
  `--report NAME`           Report preset (minimal, standard, full)
  `--depth LEVEL`           Max depth (requirements, assertions, implementation, full)
  `--mode {core,sponsor,combined}`  Report scope
  `--sponsor NAME`          Sponsor name for filtered reports

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

## Coverage Indicators

In trace view:
  **○** None    - No code implements this assertion
  **◐** Partial - Some assertions have implementations
  **●** Full    - All assertions have implementations
  **⚡** Failure - Test failures detected
  **◆** Changed - Modified vs main branch

## Depth Levels

Control how much detail is shown:

  `--depth 0` or `requirements`    Show only requirements
  `--depth 1` or `assertions`      Include assertions
  `--depth 2` or `implementation`  Include code references
  `--depth full`                   Unlimited depth (tests, results)

## Understanding the Graph

  $ elspais trace --graph-json > graph.json

The graph shows:
  - Requirements and their assertions
  - Which code files implement which assertions
  - Which tests validate which requirements
  - Test pass/fail status from JUnit/pytest results
