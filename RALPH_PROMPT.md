# Coverage Improvement Loop

You are improving traceability coverage for the elspais project. Your goal is to add `# Implements: REQ-xxx-Y` comments to source files and `# Validates: REQ-xxx-Y` comments to test files so that the MCP traceability graph reflects actual coverage.

## Rules

1. Only touch Active requirements. Skip Draft review features REQ-d00001 to REQ-d00012 and REQ-p00007 to REQ-p00012.
2. Use the elspais MCP tools: `get_uncovered_assertions`, `get_requirement`, `get_test_coverage` to find gaps.
3. Read the requirement assertion text, then find the source code that implements it and the test that validates it.
4. Add a SINGLE-LINE comment near the relevant code: `# Implements: REQ-xxx-Y` for source or `# Validates: REQ-xxx-Y` for tests.
5. After each batch of additions, run `python -m pytest tests/ -q` to verify nothing breaks.
6. Commit with message format: `[CUR-240] feat: Add traceability markers for REQ-xxx` with co-author line `Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>`.
7. Work through requirements in priority order: partially-covered first, then PRD, then OPS, then DEV.
8. Each iteration: pick 1-3 requirements, add markers, test, commit.
9. Re-check coverage with MCP after each commit.

## Current State

- REQ-p00002: 33 percent covered - A covered, B and C uncovered
- REQ-p00004: 50 percent covered - A covered, B uncovered
- All other Active requirements: 0 percent covered

## When Done

When you have covered all Active requirements you can find implementation or test code for, output:

`COVERAGE COMPLETE`
