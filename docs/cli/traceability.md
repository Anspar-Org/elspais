# TRACEABILITY

## What is Traceability?

Traceability connects requirements to their implementations and tests:

  **Requirement** -> **Assertion** -> **Code** -> **Test** -> **Result**

This answers: "How do we know this requirement is satisfied?"

## Generating Reports

  $ elspais trace                    # Markdown table (default)
  $ elspais trace --format html      # Basic HTML matrix
  $ elspais trace --format csv       # Spreadsheet export
  $ elspais trace --format json      # JSON structured output
  $ elspais viewer                   # Interactive HTML tree (live server)
  $ elspais viewer --static          # Interactive HTML tree (static file)
  $ elspais graph                    # Export graph structure as JSON

## trace Command Options

  `--format {text,markdown,html,json,csv}`  Output format (default: markdown)
  `--preset {minimal,standard,full}`        Column preset
  `--body`                Show requirement body text
  `--assertions`          Show individual assertions
  `--tests`               Show test references
  `--output PATH`         Output file path

## viewer Command Options

  `--static`              Generate static HTML file instead of live server
  `--server`              Start server without opening browser
  `--port PORT`           Server port (default: 5001)
  `--embed-content`       Embed full markdown in HTML (offline viewing)
  `--path DIR`            Path to repository root (default: auto-detect)

## graph Command

Export the full traceability graph as JSON:

  $ elspais graph                    # Print to stdout
  $ elspais graph -o graph.json      # Write to file

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

Reference requirement IDs in test function names:

```python
def test_REQ_d00001_A_bcrypt_cost():
    ...
```

Or with comments:
```python
# Tests: REQ-d00001-A
def test_password_uses_bcrypt():
    ...
```

## Coverage Indicators

In the interactive viewer:
  **None**    - No code implements this assertion
  **Partial** - Some assertions have implementations
  **Full**    - All assertions have implementations
  **Failure** - Test failures detected
  **Changed** - Modified vs main branch

## Understanding the Graph

  $ elspais graph -o graph.json

The graph shows:
- Requirements and their assertions
- Which code files implement which assertions
- Which tests validate which requirements
- Test pass/fail status from JUnit/pytest results
