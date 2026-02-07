# MASTER PLAN — Linking Convention Documentation

**Branch**: feature/CUR-240-viewtrace-port
**Ticket**: CUR-240
**CURRENT_ASSERTIONS**: (populate via WORKFLOW_STATE.md "Identify Assertions" step before implementation)

## Goal

Define a clear, authoritative convention for requirement linking that developers and AI agents follow. This is a documentation-only change that establishes the linking patterns already supported by the tooling.

## Principle: Conventions should be documented where users can find them

The codebase already supports multiple linking patterns (`# Implements:`, `REQ-xxx` in test names, multi-assertion syntax), but there's no single reference document describing when and how to use each approach.

## Implementation Steps

### Step 1: Linking convention documentation

**Files**: `docs/cli/linking.md` (new documentation topic for `elspais docs linking`)

- [ ] **Code files**: Use `# Implements: REQ-xxx` (or language-appropriate comment) above or inside the function that implements the requirement
- [ ] **Test files — direct**: Use `# Tests REQ-xxx` comment or include `REQ_xxx` in test function names (`test_REQ_p00001_A_validates_input`)
- [ ] **Test files — indirect**: Import and exercise a function that has `# Implements: REQ-xxx`; coverage rolls up automatically
- [ ] **Multi-assertion syntax**: `# Implements: REQ-p00001-A-B-C` expands to individual assertion references
- [ ] **When to use each approach**: Decision tree — direct linking for acceptance/integration tests, indirect linking acceptable for unit tests of implementation functions
- [ ] **AI agent instructions**: Snippet suitable for inclusion in agent prompts (CLAUDE.md, etc.) describing the linking convention

## Files to Modify

| File | Change |
|------|--------|
| **NEW** `docs/cli/linking.md` | Linking convention documentation |

## What Stays the Same

- Everything. This is documentation only.

## Commit Strategy

1 commit:
1. **Linking convention docs** (Step 1)

## Verification

1. `elspais docs linking` displays the convention documentation
2. Documentation covers all supported linking patterns
3. AI agent snippet is self-contained and accurate

## Archive

- [ ] Mark phase complete in MASTER_PLAN.md
- [ ] Archive completed plan: `mv MASTER_PLAN.md ~/archive/YYYY-MM-DD/MASTER_PLANx.md`
- [ ] Promote next plan: `mv MASTER_PLAN[lowest].md MASTER_PLAN.md`
- **CLEAR**: Reset checkboxes for next phase
