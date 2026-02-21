# GAPS: Requirement Verification Workflow

This document describes capabilities that are **NOT available** in elspais but are needed for a complete requirement verification workflow.

## Overview

elspais provides hash-based verification of requirement content, but lacks the higher-level workflow features needed to track which requirements need implementation re-verification after changes.

## Current elspais Capabilities

| Command | Purpose |
| --- | --- |
| `elspais validate` | Check if hashes match current content |
| `elspais fix` | Fix hashes and formatting in spec files |
| `elspais changed` | Show git-level changes to spec files |
| `elspais trace` | Generate traceability matrix |
| `elspais analyze hierarchy` | Show requirement hierarchy |

## Missing Capabilities

### 1. Changed Requirements Detection

**Gap**: No command to compare INDEX.md hashes with current requirement content to identify which specific requirements changed.

**Current workaround**: External script `detect-changes.py` that:
- Reads hashes from INDEX.md
- Computes current hashes using `elspais validate`
- Compares and reports differences

**Proposed elspais command**:
```bash
elspais changed-requirements    # Compare INDEX.md hashes with current
```

---

### 2. Outdated Implementations Tracking

**Gap**: No mechanism to persist a list of requirements that need implementation verification after content changes.

**Current workaround**: External JSON file `outdated-implementations.json` tracking:
- Requirement ID
- Old hash (from INDEX.md)
- New hash (current content)
- Detection timestamp

**Proposed elspais command**:
```bash
elspais verify status           # Show requirements needing re-verification
```

---

### 3. Mark Verified Command

**Gap**: No command to mark a requirement as "verified" after implementation review.

**Current workaround**: External script `mark-verified.py` that:
- Removes requirement from tracking file
- Records verification timestamp and user

**Proposed elspais commands**:
```bash
elspais verify mark REQ-xxx     # Mark single requirement as verified
elspais verify mark --all       # Mark all as verified
```

---

### 4. Post-Commit Integration

**Gap**: No git hook integration to auto-detect requirement changes after commits.

**Current workaround**: External post-commit hook that:
- Runs change detection after each commit
- Adds changed requirements to tracking file
- Notifies user of new outdated implementations

**Proposed elspais feature**:
```bash
elspais hooks install           # Install git hooks for auto-detection
```

---

### 5. Validate "Implements:" Claims

**Gap**: No command to verify that code claiming to implement a requirement actually does so.

**Current status**: Not implemented anywhere (neither elspais nor local scripts).

**Proposed elspais command**:
```bash
elspais verify implements REQ-xxx   # Find files claiming to implement REQ
elspais verify coverage             # Report implementation coverage
```

---

## Workflow Comparison

### With elspais only (current)

```bash
# Manual process - no tracking
elspais validate      # See which hashes changed
# ... manually remember what needs verification ...
elspais fix           # Fix hashes when done
```

### With external scripts (current workaround)

```bash
# Automated tracking workflow
python3 detect-changes.py          # Find changed requirements
cat outdated-implementations.json  # See what needs verification
# ... review implementation ...
python3 mark-verified.py REQ-xxx   # Mark as verified
```

### Desired elspais workflow (future)

```bash
# Integrated tracking workflow
elspais verify status              # See what needs verification
# ... review implementation ...
elspais verify mark REQ-xxx        # Mark as verified
```

---

## Feature Request Summary

| Priority | Feature | Command |
| --- | --- | --- |
| High | Show outdated implementations | `elspais verify status` |
| High | Mark requirement verified | `elspais verify mark REQ-xxx` |
| Medium | Compare with INDEX.md | `elspais changed-requirements` |
| Medium | Install git hooks | `elspais hooks install` |
| Low | Validate implements claims | `elspais verify implements REQ-xxx` |

---

## References

- Local scripts location: `tools/anspar-cc-plugins/plugins/simple-requirements/scripts/`
- Tracking file: `untracked-notes/outdated-implementations.json`
- Related: INDEX.md hash format documentation
