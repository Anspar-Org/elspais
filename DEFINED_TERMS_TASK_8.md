# Task 8: Comment Extraction Utilities

**Branch**: defined-terms2
**Ticket**: CUR-1082
**Status**: In Progress

## Description

Create `extract_comments(source, ext)` in `src/elspais/graph/term_scanner.py` that extracts comment text from source code based on file extension. Returns `list[tuple[str, int]]` (text, line_number).

## Applicable Assertions

- REQ-d00236-A: `extract_comments(source, ext)` returns list of (comment_text, line_number) pairs
- REQ-d00236-B: Python files use tokenize for # comments and ast for docstrings
- REQ-d00236-C: Slash-comment languages extract `//` and `/* */` comments
- REQ-d00236-D: Hash-comment languages extract # comments
- REQ-d00236-E: Dash-comment languages extract -- comments
- REQ-d00236-F: Markup languages extract <!-- --> comments
- REQ-d00236-G: Unknown extensions return empty list

## Progress

- [x] Baseline: tests pass (3413 passed)
- [x] Created TASK_FILE
- [x] Found assertions: created REQ-d00236 with assertions A-G
- [ ] Write failing tests
- [ ] Implement
- [ ] Verify
- [ ] Update docs
- [ ] Bump version
- [ ] Commit
