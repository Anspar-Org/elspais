# Agent Design Principles

**Read this file at the start of each session and after each compact event.**

## Core Architecture Principles

- There is ONE main graph data structure; DO NOT create parallel data structures.
- There is ONE config system; DO NOT parse configuration separately.
- DO NOT change the structure of Graph, GraphTrace, or GraphBuilder.
- DO NOT violate existing encapsulation.
- DO NOT consult git history for context.

## API Usage

- ALWAYS use existing graph API functions instead of reimplementing logic.
- ALWAYS use aggregate functions from `graph/annotators.py` for statistics.
- ALWAYS use graph methods (e.g., `orphan_count()`) instead of materializing iterators.
- ALWAYS use iterator-only API methods for traversal.
- ALWAYS use `graph.find_by_id()` for O(1) lookups instead of iterating.
- DO NOT manually iterate to compute statistics that have dedicated aggregate functions.
- DO NOT materialize iterators when a count method exists.

## Testing

- ALWAYS include assertion references in test names.
- Test names MUST reference a specific assertion (e.g., `test_REQ_xxx_A_description`).
- Tests without assertion references will not link to requirements in the traceability graph.
- ALWAYS use a sub-agent to write tests.
- Run `pytest tests/test_doc_sync.py` before committing doc changes.

## Workflow

- ALWAYS update the version in `pyproject.toml` before each commit.
- ALWAYS update `CHANGELOG.md` with new features.
- ALWAYS update `CLAUDE.md` with architectural changes.
- ALWAYS use a sub-agent to update `docs/` files and `--help` CLI commands.
- Commit after each phase; DO NOT batch multiple phases into one commit.

## Implementation

- Search the codebase for existing functionality before implementing.
- Reuse existing modules in `src/elspais/`.
- New interface layers MUST consume existing APIs directly without intermediate data structures.
- Centralize statistical logic in aggregate functions for reuse.
- MCP tools MUST delegate to graph methods, not implement mutation logic directly.

## Architecture Review

- After implementing a feature, ALWAYS have a sub-agent evaluate architectural soundness.
- The review MUST check if implementation uses existing APIs appropriately.
- The review MUST check if aggregate functions or graph methods are being overlooked.
- The review MUST verify compliance with specification requirements.
- Use `feature-dev:code-reviewer` agent for post-implementation review.

## Specification Compliance

- Implementation MUST comply with specification assertions.
- When a spec says "SHALL use aggregate functions," DO NOT manually iterate.
- When a spec says "SHALL delegate to graph methods," DO NOT implement logic in the interface layer.
- Cross-reference implementation against spec assertions before committing.

## Sub-Agent Usage

- Use sub-agents for SPEC, TEST, IMPL, DEBUG, and COMMIT phases.
- Provide sub-agents with: workflow file path, plan file path, current phase, current step.
- Sub-agents should also read this file and the refactor workflow file.

## Recovery

- After `/clear` or compact event, read `MASTER_PLAN.md` for current work.
- Continue from last incomplete checkbox in plan files.
- Verify understanding of current state before proceeding.
